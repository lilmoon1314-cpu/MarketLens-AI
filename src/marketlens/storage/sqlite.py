"""Transactional snapshots; runtime dependencies and credentials never enter SQLite."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from marketlens.contracts import AnalysisReport, Review, SemanticReview


def fingerprint(value: object) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def semantic_cache_key(text: str, metadata: dict) -> str:
    return fingerprint({"text_hash": sha256(text.encode()).hexdigest(), "version": metadata})


class RunStore:
    def __init__(self, path: Path):
        self.path = path
        self.checkpoint_path = path.with_name(path.stem + "-checkpoints.sqlite3")
        self.enabled = True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise ValueError("unsupported storage schema version")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, status TEXT NOT NULL, stage TEXT NOT NULL,
                    updated_at TEXT NOT NULL, input_hash TEXT NOT NULL, state_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    review_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,review_id));
                CREATE TABLE IF NOT EXISTS annotations (
                    run_id TEXT NOT NULL, review_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id,review_id), FOREIGN KEY(run_id,review_id)
                    REFERENCES reviews(run_id,review_id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS reports (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cache_refs (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    cache_key TEXT NOT NULL REFERENCES semantic_cache(cache_key) ON DELETE CASCADE,
                    PRIMARY KEY(run_id,cache_key));
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_state(self, state: dict) -> None:
        if not self.enabled:
            return
        run_id = state["run_id"]
        reviews = [Review.model_validate_json(json.dumps(item)) for item in state["reviews"]]
        annotations = [SemanticReview.model_validate(item) for item in state["annotations"]]
        report = (
            AnalysisReport.model_validate_json(json.dumps(state["report"]))
            if state["report"]
            else None
        )
        input_hash = fingerprint(
            {
                "request": state["request"],
                "reviews": sorted(state["reviews"], key=lambda item: item["review_id"]),
                "raw_count": state["metrics"].get("raw_count", 0),
                "rejected": state["rejected_counts"],
            }
        )
        with self.connection() as db:
            db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET "
                "status=excluded.status,stage=excluded.stage,updated_at=excluded.updated_at,"
                "input_hash=excluded.input_hash,state_json=excluded.state_json",
                (
                    run_id,
                    state["status"],
                    state["stage"],
                    datetime.now(UTC).isoformat(),
                    input_hash,
                    json.dumps(state, ensure_ascii=False),
                ),
            )
            db.execute("DELETE FROM reviews WHERE run_id=?", (run_id,))
            db.executemany(
                "INSERT INTO reviews VALUES (?,?,?)",
                [(run_id, r.review_id, r.model_dump_json()) for r in reviews],
            )
            db.executemany(
                "INSERT INTO annotations VALUES (?,?,?)",
                [(run_id, a.review_id, a.model_dump_json()) for a in annotations],
            )
            metadata = state["metrics"].get("semantic_cache")
            by_id = {r.review_id: r for r in reviews}
            if metadata:
                for annotation in annotations:
                    if annotation.processed:
                        key = semantic_cache_key(by_id[annotation.review_id].text, metadata)
                        db.execute(
                            "INSERT INTO semantic_cache VALUES (?,?) ON CONFLICT(cache_key) "
                            "DO UPDATE SET payload=excluded.payload",
                            (key, annotation.model_dump_json()),
                        )
                        db.execute("INSERT OR IGNORE INTO cache_refs VALUES (?,?)", (run_id, key))
            if report is not None:
                db.execute(
                    "INSERT INTO reports VALUES (?,?) ON CONFLICT(run_id) "
                    "DO UPDATE SET payload=excluded.payload",
                    (run_id, report.model_dump_json()),
                )

    def cached(self, text: str, metadata: dict, review_id: str) -> SemanticReview | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT payload FROM semantic_cache WHERE cache_key=?",
                (semantic_cache_key(text, metadata),),
            ).fetchone()
        if row is None:
            return None
        try:
            annotation = SemanticReview.model_validate_json(row[0])
            return (
                annotation.model_copy(update={"review_id": review_id})
                if annotation.processed
                else None
            )
        except ValueError:
            return None

    def report(self, run_id: str) -> AnalysisReport | None:
        with self.connection() as db:
            row = db.execute("SELECT payload FROM reports WHERE run_id=?", (run_id,)).fetchone()
        return AnalysisReport.model_validate_json(row[0]) if row else None

    def state(self, run_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT state_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def history(self, limit: int = 50) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("history limit must be 1—100")
        with self.connection() as db:
            rows = db.execute(
                "SELECT run_id,status,stage,updated_at,input_hash,state_json FROM runs "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "run_id": row[0],
                "status": row[1],
                "stage": row[2],
                "updated_at": row[3],
                "input_hash": row[4],
                "product": json.loads(row[5])["request"]["product"],
            }
            for row in rows
        ]

    def evidence(self, run_id: str, ids: list[str], for_llm: bool = False) -> list[Review]:
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate evidence IDs")
        state = self.state(run_id)
        if state is None or for_llm and not set(ids) <= set(state["selected_ids"]):
            raise ValueError("evidence outside run or fixed LLM selection")
        with self.connection() as db:
            values = {
                row[0]: row[1]
                for row in db.execute(
                    "SELECT review_id,payload FROM reviews WHERE run_id=?", (run_id,)
                )
            }
        if not set(ids) <= values.keys():
            raise ValueError("evidence outside run")
        return [Review.model_validate_json(values[review_id]) for review_id in ids]

    def delete_run(self, run_id: str) -> None:
        if self.checkpoint_path.exists():
            from langgraph.checkpoint.sqlite import SqliteSaver

            with SqliteSaver.from_conn_string(str(self.checkpoint_path)) as saver:
                saver.delete_thread(run_id)
        with self.connection() as db:
            db.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            db.execute(
                "DELETE FROM semantic_cache WHERE NOT EXISTS (SELECT 1 FROM cache_refs "
                "WHERE cache_refs.cache_key=semantic_cache.cache_key)"
            )
