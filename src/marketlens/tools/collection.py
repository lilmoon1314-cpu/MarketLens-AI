"""Bounded, registered local datasets; no model or network access."""

import csv
import io
import json
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from marketlens.contracts import Review

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class DatasetError(ValueError):
    """Dataset cannot be read safely or its file structure is invalid."""


@dataclass
class CollectionResult:
    reviews: list[Review] = field(default_factory=list)
    raw_count: int = 0
    rejected_counts: dict[str, int] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "partial" if self.rejected_counts else "complete"


def _optional_text(record: Mapping[str, object], key: str) -> str | None:
    value = record.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("metadata must be strings")
    return value.strip() or None


def _review(record: Mapping[str, object]) -> Review:
    text = record.get("text")
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    text = " ".join(unicodedata.normalize("NFKC", text).split())
    if not text:
        raise LookupError("empty text")
    source_id = _optional_text(record, "source_id")
    product_id = _optional_text(record, "product_id")
    raw_time = _optional_text(record, "time")
    time = None
    if raw_time is not None:
        time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        if time.tzinfo is None or time.utcoffset() is None:
            raise ValueError("time requires an explicit timezone")
        time = time.astimezone(UTC)
    identity = ["local", "source_id", source_id] if source_id else ["local", product_id, text]
    review_id = sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()
    return Review(
        review_id=review_id,
        text=text,
        source="local",
        source_id=source_id,
        product_id=product_id,
        url=_optional_text(record, "url"),
        time=time,
    )


def normalize_reviews(records: Iterable[object], limit: int = 1000) -> CollectionResult:
    """Normalize and keep first unique review; count every input once, even past the cap."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    result = CollectionResult()
    rejected: Counter[str] = Counter()
    ids: set[str] = set()
    texts: set[tuple[str | None, str]] = set()
    for record in records:
        result.raw_count += 1
        if not isinstance(record, Mapping):
            rejected["invalid_record"] += 1
            continue
        try:
            review = _review(record)
        except LookupError:
            rejected["empty_text"] += 1
            continue
        except (ValueError, TypeError, ValidationError):
            rejected["invalid_record"] += 1
            continue
        text_key = (review.product_id, review.text)
        if review.review_id in ids or text_key in texts:
            rejected["duplicate"] += 1
            continue
        ids.add(review.review_id)
        texts.add(text_key)
        if len(result.reviews) >= limit:
            rejected["over_limit"] += 1
            continue
        result.reviews.append(review)
    result.rejected_counts = dict(rejected)
    return result


def load_local_reviews(
    dataset_id: str, datasets: Mapping[str, Path], limit: int = 1000
) -> CollectionResult:
    """Resolve only an exact registered ID, never an agent-supplied filesystem path."""
    if dataset_id not in datasets:
        raise DatasetError("unknown dataset_id")
    path = Path(datasets[dataset_id])
    suffix = path.suffix.lower()
    if suffix not in {".csv", ".jsonl"}:
        raise DatasetError("only CSV and JSONL datasets are supported")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise DatasetError("dataset exceeds 10 MiB")
        content = data.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise DatasetError("dataset must be readable UTF-8") from exc
    records: list[object] = []
    malformed = 0
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
        try:
            headers = reader.fieldnames
            if not headers or "text" not in headers or len(headers) != len(set(headers)):
                raise DatasetError("CSV requires unique headers including text")
            for row in reader:
                records.append(row if None not in row and None not in row.values() else None)
        except csv.Error as exc:
            # Broken quoting can swallow subsequent rows: reject file rather than fabricate rows.
            raise DatasetError("malformed CSV quoting or oversized field") from exc
    else:
        for line in content.splitlines():
            try:
                records.append(json.loads(line))
            except (ValueError, RecursionError):
                malformed += 1
    result = normalize_reviews(records, limit)
    result.raw_count += malformed
    if malformed:
        result.rejected_counts["invalid_json"] = malformed
    return result
