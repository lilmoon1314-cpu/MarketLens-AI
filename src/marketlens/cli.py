"""Explicit demo or real command; no silent model execution."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from pydantic import ValidationError

from marketlens.config import ConfigurationError
from marketlens.contracts import AnalysisRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MarketLens AI 离线工作流")
    parser.add_argument("command", choices=["analyze"])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--max-reviews", type=int, default=1000)
    parser.add_argument("--data-dir", type=Path, default=Path(".local"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true", help="明确使用模拟Agent")
    mode.add_argument(
        "--real", action="store_true", help="使用本地GLiNER2和已配置LLM，会产生API用量"
    )
    args = parser.parse_args(argv)
    try:
        from marketlens.storage.sqlite import RunStore
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
        datasets = {"cli-input": args.input}
        storage_unavailable = False
        try:
            store = RunStore(args.data_dir / "marketlens.sqlite3")
        except (sqlite3.Error, OSError):
            store = None
            storage_unavailable = True
        service = (
            AnalysisService.real(datasets, store=store)
            if args.real
            else AnalysisService(datasets, DemoAgents(), store=store)
        )
        report = service.run(request)
        if storage_unavailable:
            report["warnings"].append(
                {
                    "code": "storage_unavailable",
                    "stage": "start",
                    "message": "存储初始化失败，请导出当前报告",
                }
            )
    except ImportError:
        print("请安装对应依赖；真实模式需workflow、llm、nlp extras。", file=sys.stderr)
        return 2
    except ValidationError:
        print("分析请求无效，请检查参数长度和评论上限。", file=sys.stderr)
        return 2
    except ConfigurationError:
        print("LLM配置无效，请检查忽略的.env或环境变量。", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
