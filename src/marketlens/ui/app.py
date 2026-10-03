"""Run with: streamlit run src/marketlens/ui/app.py --server.address 127.0.0.1."""

import json
import os
import sqlite3
from pathlib import Path

import altair as alt
import streamlit as st

from marketlens.config import ConfigurationError
from marketlens.contracts import AnalysisRequest, Review
from marketlens.storage.sqlite import RunStore
from marketlens.ui.controller import cited_ids, export_report, sample_bytes, uploaded_dataset
from marketlens.workflow.demo import DemoAgents
from marketlens.workflow.service import AnalysisService

STAGES = {
    "start": "准备分析",
    "planner": "规划分析范围",
    "collect": "导入并整理评论",
    "semantic": "识别情绪与主题",
    "aggregate": "统计与预算筛选",
    "analyst": "生成证据洞察",
    "visualization": "准备图表",
    "finalize": "完成报告",
}
STATUS = {
    "complete": "分析完成",
    "partial": "部分结果",
    "failed": "分析失败",
    "insufficient_data": "评论不足",
    "running": "进行中",
}
KINDS = {
    "strength": "优势",
    "weakness": "不足",
    "pain_point": "痛点",
    "feature_request": "改进建议",
}


def evidence_for(report, ids, store):
    if st.session_state.get("active_run") == report["run_id"]:
        values = st.session_state.get("evidence", {})
        if all(i in values for i in ids):
            return [Review.model_validate_json(values[i]) for i in ids]
    if store is None:
        raise ValueError("evidence unavailable")
    return store.evidence(report["run_id"], ids)


def render_report(report, store):
    st.subheader("反馈分析报告")
    st.caption(report["request"]["product"] + " · " + STATUS[report["status"]])
    if report["request"]["dataset_id"] == "demo-sample":
        st.info("合成评论样例：用于验证流程，不代表真实消费者反馈。")
    if report["mode"] == "demo":
        st.warning("演示报告：语义标签与洞察来自模拟数据，不可用于产品决策。")
    if not report["persisted"]:
        st.warning("报告尚未保存到本地历史，请及时下载。")
    for warning in report["warnings"]:
        if warning["code"] != "demo_mode":
            st.warning(warning["message"])
    for error in report["errors"]:
        st.error(error["message"])
    count = report["review_count"]
    selected = len(report["selected_ids"])
    columns = st.columns(4)
    for column, label, value in zip(
        columns,
        ["有效评论", "原始评论", "进入分析的评论", "证据洞察"],
        [count, report["raw_count"], selected, len(report["insights"])],
        strict=True,
    ):
        column.metric(label, value)
    st.caption(
        f"独立评论入选比例：{selected / count * 100 if count else 0:.1f}% · 严格低于 30% · "
        "主题计数可重叠；证据数量仅代表所选样本。"
    )
    if report["statistics"] and report["statistics"]["low_sample"]:
        st.info("样本少于 20 条，结论仅供探索。请增加评论并核查证据。")
    if report["analyst_result"]:
        st.write(report["analyst_result"]["summary"])
        for limitation in report["analyst_result"]["limitations"]:
            st.caption(limitation)
    tabs = st.tabs(["洞察与证据", "反馈分布", "报告导出"], key="report_tabs", on_change="rerun")
    with tabs[0]:
        if not report["insights"]:
            st.info("暂无证据洞察。评论数量、筛选预算或分析失败可能影响结果；仍可查看统计。")
        for insight in report["insights"]:
            with st.container(border=True):
                st.caption(KINDS[insight["kind"]] + f" · {insight['evidence_count']} 条样本证据")
                st.subheader(insight["title"])
                st.write(insight["summary"])
                if insight["hypothesis"]:
                    st.caption("待验证假设：" + insight["hypothesis"])
                with st.expander("查看原始评论证据"):
                    try:
                        for review in evidence_for(report, insight["evidence_ids"], store):
                            st.text(review.text)
                            st.caption("评论 ID：" + review.review_id)
                    except (ValueError, sqlite3.Error, OSError):
                        st.warning("原始证据暂不可读取，请保留报告引用。")
    with tabs[1]:
        for chart in report["charts"]:
            st.write(chart["title"])
            data = alt.Data(values=chart["data"])
            if chart["chart"] == "donut":
                plot = (
                    alt.Chart(data)
                    .mark_arc(innerRadius=55)
                    .encode(
                        theta=alt.Theta("count:Q", title="评论数"),
                        color=alt.Color("label:N", title="分类"),
                        tooltip=[
                            alt.Tooltip("label:N", title="分类"),
                            alt.Tooltip("count:Q", title="评论数"),
                        ],
                    )
                )
            else:
                plot = (
                    alt.Chart(data)
                    .mark_bar(color="#138878", cornerRadiusEnd=4)
                    .encode(
                        x=alt.X("count:Q", title="评论数", axis=alt.Axis(tickMinStep=1)),
                        y=alt.Y("label:N", title=None, sort=None),
                        tooltip=[
                            alt.Tooltip("label:N", title="分类"),
                            alt.Tooltip("count:Q", title="评论数"),
                        ],
                    )
                )
            st.altair_chart(
                plot.properties(height=max(180, len(chart["data"]) * 34)), width="stretch"
            )
        if not report["charts"]:
            st.info("尚无可绘制的统计数据。")
    with tabs[2]:
        include = st.checkbox("导出时附带已引用的评论正文", key="include_evidence")
        try:
            evidence = evidence_for(report, cited_ids(report), store) if include else None
            st.caption("本次导出附带评论正文" if include else "本次导出仅含证据引用")
            st.download_button(
                "下载 JSON 报告",
                data=export_report(report, evidence),
                file_name=f"marketlens-{report['run_id']}.json",
                mime="application/json",
                on_click="ignore",
            )
        except (ValueError, sqlite3.Error, OSError):
            st.warning("证据读取失败，请取消附带正文后下载报告。")
        st.caption("默认仅导出统计、洞察和证据引用。报告保存在本机，不包含 API 密钥。")


def main():
    st.set_page_config(page_title="MarketLens AI · 产品反馈", page_icon="◈", layout="wide")
    st.markdown(
        """<style>
    .stApp {background:#f5f8f7;color:#18332e}
    html, body, input, textarea, button, p, h1, h2, h3 {
      font-family:"Microsoft YaHei","Segoe UI",sans-serif!important
    }
    .block-container {max-width:1280px;padding-top:2.5rem}
    h1 {letter-spacing:-1.5px;font-weight:750!important}
    [data-testid="stMetric"] {background:white;padding:16px;border-radius:12px}
    [data-testid="stSidebar"] {background:#edf3f0}
    @media (max-width:760px) {
      .block-container {padding:1.5rem 1rem}
      [data-testid="stHorizontalBlock"] {flex-wrap:wrap}
      [data-testid="stColumn"] {min-width:min(280px,100%)!important;flex:1 1 280px!important}
      h1 {font-size:2rem!important}
    }
    </style>""",
        unsafe_allow_html=True,
    )
    root = Path(os.environ.get("MARKETLENS_DATA_DIR", ".local"))
    try:
        store = RunStore(root / "marketlens.sqlite3")
    except (sqlite3.Error, OSError):
        store = None
        st.warning("本地历史存储不可用，本次结果仍可下载。")
    st.caption("MARKETLENS AI  /  产品反馈研究")
    st.title("让每一条反馈都有据可查")
    st.write("从评论中发现优势、痛点与改进机会，用原始证据核查每一项洞察。")
    with st.sidebar:
        st.subheader("本地分析历史")
        try:
            history = store.history() if store else []
        except sqlite3.Error:
            history = []
            st.warning("历史记录暂不可读取。")
        records = {r["run_id"]: r for r in history}
        selected_history = st.selectbox(
            "选择历史报告",
            [None, *records],
            format_func=lambda i: (
                "选择一份已保存的报告"
                if i is None
                else records[i]["product"] + " · " + STATUS.get(records[i]["status"], "进行中")
            ),
        )
        if st.button("查看报告", disabled=selected_history is None):
            try:
                saved = store.report(selected_history)
                if saved is None:
                    st.warning("本次运行没有最终报告，不能视为任务已恢复。")
                else:
                    st.session_state["report"] = saved.model_dump(mode="json")
            except (ValueError, sqlite3.Error):
                st.warning("历史报告暂不可读取。")
        confirm = st.checkbox("确认删除所选运行及其证据")
        if st.button("删除记录", disabled=not confirm or selected_history is None):
            try:
                store.delete_run(selected_history)
                if st.session_state.get("report", {}).get("run_id") == selected_history:
                    st.session_state.pop("report", None)
                    st.session_state.pop("evidence", None)
                st.rerun()
            except (sqlite3.Error, OSError):
                st.warning("删除未完成，请稍后重试。")
        st.caption("历史仅保存在本机。刷新后可查看报告，未完成的运行不会自动恢复。")
    inputs, guide = st.columns([1.3, 1], gap="large")
    with inputs, st.container(border=True):
        st.subheader("开始一次分析")
        data_source = st.radio("评论数据", ["演示样例", "上传文件"], horizontal=True)
        mode = st.radio("分析模式", ["演示模式", "真实分析"], horizontal=True)
        if mode == "真实分析":
            st.caption("使用本地 GLiNER2 与已配置 LLM，会产生 API 用量。")
        with st.form("analysis"):
            product = st.text_input("产品名称", value="iPhone 17", max_chars=200)
            goal = st.text_area(
                "分析目标", value="发现用户最关心的体验问题与改进机会。", max_chars=2000
            )
            upload = st.file_uploader(
                "上传 CSV / JSONL 评论",
                type=["csv", "jsonl"],
                max_upload_size=10,
                disabled=data_source == "演示样例",
            )
            limit = st.number_input("最多分析评论数", min_value=1, max_value=1000, value=1000)
            submitted = st.form_submit_button(
                "开始分析",
                type="primary",
                disabled=st.session_state.get("running", False),
                width="stretch",
            )
    with guide:
        st.subheader("从评论到洞察")
        st.markdown(
            "**01 · 整理评论**  \n导入、去重，记录实际样本覆盖。\n\n"
            "**02 · 识别与筛选**  \n识别情绪和主题，限制进入 LLM 的独立评论数量。\n\n"
            "**03 · 核查结论**  \n每项洞察附带原始证据，支持下载与复查。"
        )
        st.info("淘宝商品评论采集将在下一阶段接入。当前支持本地导入。")
        st.caption("上传文件限 10 MiB。至少包含 text 字段；可附带来源、日期与评分。")
    if submitted:
        st.session_state["running"] = True
        try:
            if data_source == "上传文件" and upload is None:
                st.error("请选择评论文件，或切换到演示样例。")
            else:
                data = sample_bytes() if data_source == "演示样例" else upload.getvalue()
                name = "demo.jsonl" if data_source == "演示样例" else upload.name
                request = AnalysisRequest(
                    product=product,
                    goal=goal,
                    sources=["local"],
                    dataset_id="demo-sample" if data_source == "演示样例" else "upload",
                    product_urls=[],
                    max_reviews=int(limit),
                    report_language="zh-CN",
                )
                with uploaded_dataset(data, name, root) as uploaded:
                    datasets = {request.dataset_id: uploaded["upload"]}
                    service = (
                        AnalysisService.real(datasets, store=store)
                        if mode == "真实分析"
                        else AnalysisService(datasets, DemoAgents(), store=store)
                    )
                    with st.status("正在分析评论", expanded=True) as progress:
                        for event in service.stream(request):
                            st.write(STAGES.get(event["stage"], "分析中"))
                            if "report" in event:
                                st.session_state["report"] = event["report"]
                        final = st.session_state["report"]
                        st.session_state["active_run"] = final["run_id"]
                        st.session_state["evidence"] = {
                            r["review_id"]: Review.model_validate_json(
                                json.dumps(r)
                            ).model_dump_json()
                            for r in service.last_state["reviews"]
                        }
                        progress.update(
                            label=STATUS[final["status"]],
                            state="error" if final["status"] == "failed" else "complete",
                            expanded=False,
                        )
        except (ValueError, ConfigurationError):
            st.error("输入或配置无效。请检查产品、目标、文件大小及本机 LLM 配置。")
        except ImportError:
            st.error("缺少运行依赖。真实分析需安装 workflow、llm、nlp extras。")
        except (sqlite3.Error, OSError):
            st.error("本地文件操作失败，请检查运行数据目录是否可写。")
        finally:
            st.session_state["running"] = False
    if st.session_state.get("report"):
        st.divider()
        render_report(st.session_state["report"], store)


if __name__ == "__main__":
    main()
