"""Bounded temporary uploads and exports without credentials or review bodies by default."""

import json
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from marketlens.contracts import AnalysisReport, Review
from marketlens.tools.collection import MAX_UPLOAD_BYTES

SAMPLE = [
    "拍照颜色自然，夜景细节不错。",
    "一天重度使用电量不够，下午需要充电。",
    "握持舒服，但单手操作顶部按钮有点难。",
    "配送及时，包装完好。",
    "开视频会议时间长了会发热。",
    "屏幕亮度高，户外看得清。",
    "希望相机能记住上次选择的参数。",
    "声音清楚，通话听感不错。",
    "价格偏高，如果配件能包含充电器就更好。",
    "运行流畅，多应用切换没有卡顿。",
    "颜色和图片一致，外观很好看。",
    "系统更新后电量掉得快，希望优化后台耗电。",
]


def sample_bytes() -> bytes:
    return "\n".join(json.dumps({"text": text}, ensure_ascii=False) for text in SAMPLE).encode()


@contextmanager
def uploaded_dataset(data: bytes, name: str, root: Path):
    suffix = Path(name).suffix.lower()
    if suffix not in {".csv", ".jsonl"} or not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("请提供非空 CSV/JSONL 文件，大小不超过 10 MiB")
    directory = root / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (str(uuid4()) + suffix)
    try:
        path.write_bytes(data)
        yield {"upload": path}
    finally:
        path.unlink(missing_ok=True)


def export_report(report: dict, evidence: list[Review] | None = None) -> bytes:
    clean = AnalysisReport.model_validate_json(json.dumps(report)).model_dump(mode="json")
    if evidence is not None:
        allowed = {item for insight in clean["insights"] for item in insight["evidence_ids"]}
        if {r.review_id for r in evidence} != allowed or len(evidence) != len(allowed):
            raise ValueError("export evidence must exactly match cited references")
        clean["evidence"] = [r.model_dump(mode="json") for r in evidence]
    return json.dumps(clean, ensure_ascii=False, indent=2).encode("utf-8")


def cited_ids(report: dict) -> list[str]:
    return list(dict.fromkeys(i for insight in report["insights"] for i in insight["evidence_ids"]))
