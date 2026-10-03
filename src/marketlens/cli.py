"""Explicit demo command; no default real model execution."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from marketlens.contracts import AnalysisRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MarketLens AI 离线工作流")
    parser.add_argument("command", choices=["analyze"])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--max-reviews", type=int, default=1000)
    parser.add_argument("--demo", action="store_true", required=True, help="明确使用模拟Agent")
    args = parser.parse_args(argv)
    try:
        from marketlens.workflow.demo import DemoAgents
        from marketlens.workflow.service import AnalysisService

        request = AnalysisRequest(
            product=args.product,
            goal=args.goal,
            sources=["local"],
            dataset_id="cli-input",
            product_urls=[],
            max_reviews=args.max_reviews,
            report_language="zh-CN",
        )
        report = AnalysisService({"cli-input": args.input}, DemoAgents()).run(request)
    except ImportError:
        print(
            "请先安装workflow依赖：uv sync --locked --extra workflow --group dev", file=sys.stderr
        )
        return 2
    except ValidationError:
        print("分析请求无效，请检查参数长度和评论上限。", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
