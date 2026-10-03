"""Local import behavior, provenance, and bounded failure cases."""

from datetime import timedelta

import pytest

from marketlens.tools.collection import (
    MAX_UPLOAD_BYTES,
    DatasetError,
    load_local_reviews,
    normalize_reviews,
)


def test_normalization_identity_and_privacy():
    first = normalize_reviews(
        [{"text": " Ａ\n 好用  ", "author": "private", "source": "taobao"}]
    ).reviews[0]
    second = normalize_reviews([{"text": "A 好用"}]).reviews[0]
    assert first == second
    assert first.source == "local"
    assert first.text == "A 好用"
    assert first.time is None
    assert "author" not in first.model_dump()
    assert len(first.review_id) == 64


def test_first_duplicate_and_product_scope():
    result = normalize_reviews(
        [
            {"text": "不错", "source_id": "r1", "product_id": "p1"},
            {"text": " 不错 ", "source_id": "r2", "product_id": "p1"},
            {"text": "不错", "product_id": "p2"},
            {"text": "不同正文", "source_id": "r1", "product_id": "p1"},
        ]
    )
    assert len(result.reviews) == 2
    assert result.reviews[0].source_id == "r1"
    assert result.rejected_counts == {"duplicate": 2}


def test_source_id_stays_stable_when_text_changes():
    one = normalize_reviews([{"text": "第一次", "source_id": "1"}]).reviews[0]
    two = normalize_reviews([{"text": "更新正文", "source_id": "1"}]).reviews[0]
    assert one.review_id == two.review_id


def test_utc_conversion():
    review = normalize_reviews([{"text": "好用", "time": "2026-10-03T08:00:00+08:00"}]).reviews[0]
    assert review.time.isoformat() == "2026-10-03T00:00:00+00:00"
    assert review.time.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "record",
    [
        None,
        [],
        {"text": 12},
        {},
        {"text": "好", "time": "2026-10-03"},
        {"text": "好", "time": "bad"},
        {"text": "好", "url": "file:///secret"},
        {"text": "好", "product_id": 1},
    ],
)
def test_invalid_records_are_isolated(record):
    result = normalize_reviews([record, {"text": "有效"}])
    assert result.raw_count == 2
    assert len(result.reviews) == 1
    assert result.rejected_counts == {"invalid_record": 1}


def test_empty_limit_and_count_accounting():
    result = normalize_reviews(
        [{"text": " "}, {"text": "a"}, {"text": "b"}, {"text": "b"}], limit=1
    )
    assert result.rejected_counts == {"empty_text": 1, "over_limit": 1, "duplicate": 1}
    assert result.raw_count == len(result.reviews) + sum(result.rejected_counts.values())
    assert result.status == "partial"
    assert normalize_reviews([]).status == "complete"


@pytest.mark.parametrize("limit", [0, 1001, True, 1.0])
def test_invalid_limits(limit):
    with pytest.raises(ValueError):
        normalize_reviews([], limit)


def test_thousand_review_cap():
    result = normalize_reviews({"text": f"评论 {i}"} for i in range(1002))
    assert len(result.reviews) == 1000
    assert result.raw_count == 1002
    assert result.rejected_counts == {"over_limit": 2}


def test_csv_bom_multiline_bad_rows_and_nullable_metadata(tmp_path):
    path = tmp_path / "reviews.csv"
    path.write_text(
        'text,time,source_id\n"好用\n方便",2026-10-03T00:00:00Z,r1\n有效,,\n多余,,id,extra\n缺少\n',
        encoding="utf-8-sig",
    )
    result = load_local_reviews("demo", {"demo": path})
    assert [review.text for review in result.reviews] == ["好用 方便", "有效"]
    assert result.raw_count == 4
    assert result.rejected_counts == {"invalid_record": 2}


def test_jsonl_bad_lines_and_objects(tmp_path):
    path = tmp_path / "reviews.jsonl"
    path.write_text('{"text":"好"}\n{bad}\n\n[]\n{"text":"好"}\n', encoding="utf-8")
    result = load_local_reviews("demo", {"demo": path})
    assert len(result.reviews) == 1
    assert result.raw_count == 5
    assert result.rejected_counts == {"invalid_record": 1, "duplicate": 1, "invalid_json": 2}


@pytest.mark.parametrize("content", ["other\na\n", "text,text\na,b\n", 'text\n"unclosed'])
def test_invalid_csv_structure(tmp_path, content):
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DatasetError):
        load_local_reviews("demo", {"demo": path})


def test_no_path_selection_or_unsupported_formats(tmp_path):
    path = tmp_path / "reviews.txt"
    path.write_text("text", encoding="utf-8")
    with pytest.raises(DatasetError, match="unknown"):
        load_local_reviews(str(path), {"demo": path})
    with pytest.raises(DatasetError, match="only CSV"):
        load_local_reviews("demo", {"demo": path})


def test_size_encoding_and_missing_file(tmp_path):
    path = tmp_path / "reviews.jsonl"
    for data, message in [(b"x" * (MAX_UPLOAD_BYTES + 1), "10 MiB"), (b"\xff", "UTF-8")]:
        path.write_bytes(data)
        with pytest.raises(DatasetError, match=message):
            load_local_reviews("demo", {"demo": path})
    with pytest.raises(DatasetError, match="readable"):
        load_local_reviews("demo", {"demo": tmp_path / "missing.csv"})


def test_empty_jsonl(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_bytes(b"")
    result = load_local_reviews("empty", {"empty": path})
    assert result.raw_count == 0
    assert result.reviews == []
