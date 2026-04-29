"""
数据管理页
"""
import tempfile
from pathlib import Path

import streamlit as st

from ..io.importer import (
    import_household, import_village, import_house,
    import_survey_a, import_survey_b, import_ledger,
    _parse_ledger_year_quarter,
)
from ..io.database import get_conn, init_db
from ..compute.metrics import compute_metrics, rebuild_snapshot
from ..compute.scorer import compute_scores
from ..compute.classifier import classify_all
from ..compute.auditor import run_audit

QUARTER_NAMES = ["", "一季度", "二季度", "三季度", "四季度"]


@st.cache_data(ttl=30)
def _get_counts() -> dict:
    conn = get_conn()
    queries = {
        "住户": "SELECT COUNT(*) FROM raw_households",
        "小区": "SELECT COUNT(*) FROM raw_villages",
        "住宅": "SELECT COUNT(*) FROM raw_houses",
        "A表":  "SELECT COUNT(*) FROM raw_members",
        "B表":  "SELECT COUNT(*) FROM raw_surveyb",
    }
    counts = {}
    for label, sql in queries.items():
        try:
            counts[label] = conn.execute(sql).fetchone()[0]
        except Exception:
            counts[label] = 0
    # 账页按季度分列，取最新年份
    try:
        latest_year = conn.execute("SELECT MAX(year) FROM raw_ledger").fetchone()[0]
        for q in range(1, 5):
            cnt = conn.execute(
                "SELECT COUNT(*) FROM raw_ledger WHERE year=? AND quarter=?",
                (latest_year, q),
            ).fetchone()[0] if latest_year else 0
            counts[f"Q{q}账页"] = cnt
    except Exception:
        for q in range(1, 5):
            counts[f"Q{q}账页"] = 0
    conn.close()
    return counts


def _group_header(name, icon, color):
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:center;'
        f'gap:6px;margin-bottom:6px">'
        f'<div style="width:22px;height:22px;background:{color}18;border-radius:6px;'
        f'display:flex;align-items:center;justify-content:center">'
        f'<i class="bi bi-{icon}" style="font-size:12px;color:{color}"></i>'
        f'</div>'
        f'<span style="font-size:15px;font-weight:600;color:#1E293B">{name}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _count_card(col, label, color, counts, count_keys, compact=False):
    lookup = count_keys.get(label, label)
    cnt = counts.get(lookup, 0)
    accent = color if cnt > 0 else "#CBD5E1"
    pad = "6px 4px" if compact else "10px 6px"
    col.markdown(
        f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;'
        f'border-top:3px solid {accent};border-radius:8px;'
        f'padding:{pad};text-align:center;'
        f'box-shadow:0 1px 3px rgba(15,23,42,.03)">'
        f'<div style="font-size:13px;color:#334155;margin-bottom:2px;'
        f'font-weight:600">{label}</div>'
        f'<div style="font-size:20px;font-weight:700;color:#0F172A;'
        f'letter-spacing:-0.02em">{cnt:,}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _show_counts():
    counts = _get_counts()
    count_keys = {"一季度": "Q1账页", "二季度": "Q2账页", "三季度": "Q3账页", "四季度": "Q4账页"}

    groups_def = [
        ("样本", "buildings", "#3B82F6", [("小区", "#2563EB"), ("住宅", "#3B82F6"), ("住户", "#60A5FA")], False),
        ("问卷", "file-earmark-text", "#10B981", [("A表", "#10B981"), ("B表", "#F59E0B")], False),
        ("账页", "journal-text", "#EF4444", [("一季度", "#EF4444"), ("二季度", "#F59E0B"),
                                              ("三季度", "#3B82F6"), ("四季度", "#10B981")], True),
    ]

    # 标题行：三等分，自然顶部对齐
    hcols = st.columns(3)
    for col, (gname, icon, gcolor, items, is_grid) in zip(hcols, groups_def):
        with col:
            _group_header(gname, icon, gcolor)

    # 卡片行：三等分 + 分隔线，垂直居中
    ccols = st.columns([1, 0.07, 1, 0.07, 1], vertical_alignment="center")
    for idx, (gname, icon, gcolor, items, is_grid) in enumerate(groups_def):
        with ccols[idx * 2]:
            if is_grid:
                for row_items in [items[:2], items[2:]]:
                    inner = st.columns(2)
                    for ic, (label, color) in zip(inner, row_items):
                        _count_card(ic, label, color, counts, count_keys, compact=True)
            else:
                inner = st.columns(len(items))
                for ic, (label, color) in zip(inner, items):
                    _count_card(ic, label, color, counts, count_keys)

    # 分隔线
    for di in [1, 3]:
        with ccols[di]:
            st.markdown(
                '<div style="width:0;height:130px;border-left:2px solid #CBD5E1;margin:0 auto"></div>',
                unsafe_allow_html=True,
            )


def _run_pipeline(months: list):
    if not months:
        st.warning("请先在侧边栏选择月份区间，并确保已导入账页数据。")
        return
    with st.spinner("计算中…"):
        bar = st.progress(0)
        n1 = compute_metrics(months);  bar.progress(20)
        n2 = compute_scores(months);   bar.progress(40)
        n3 = classify_all(months);     bar.progress(60)
        n4 = run_audit(months);        bar.progress(80)
        n5 = rebuild_snapshot();       bar.progress(100)
    st.success("计算完成")
    _get_counts.clear()
    st.cache_data.clear()


def _upload_card(icon: str, title: str, key: str, import_func, accent_color: str = "#3B82F6") -> bool:
    st.markdown(
        f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;'
        f'padding:18px 20px 12px;">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
        f'<div style="width:32px;height:32px;background:{accent_color}15;border-radius:8px;'
        f'display:flex;align-items:center;justify-content:center">'
        f'<i class="bi bi-{icon}" style="font-size:16px;color:{accent_color}"></i>'
        f'</div>'
        f'<span style="font-size:14px;font-weight:600;color:#0F172A">{title}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader("f", type=["csv"], key=key, label_visibility="collapsed")
    imported = False
    if st.button("导入", key=f"btn_{key}", disabled=(uploaded is None), use_container_width=True):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        try:
            n = import_func(tmp_path)
            st.success(f"✓ {n:,} 条")
            _get_counts.clear()
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"✗ {e}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    st.markdown("</div>", unsafe_allow_html=True)
    return imported


def _ledger_quarter_card(quarter: int, key: str, accent_color: str) -> bool:
    """Upload card for a specific quarter's ledger CSV."""
    title = f"{QUARTER_NAMES[quarter]}账页"
    st.markdown(
        f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;'
        f'padding:18px 20px 12px;">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
        f'<div style="width:32px;height:32px;background:{accent_color}15;border-radius:8px;'
        f'display:flex;align-items:center;justify-content:center">'
        f'<span style="font-size:15px;font-weight:700;color:{accent_color}">Q{quarter}</span>'
        f'</div>'
        f'<span style="font-size:14px;font-weight:600;color:#0F172A">{title}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader("f", type=["csv"], key=key, label_visibility="collapsed")
    ledger_year = None
    if uploaded is not None:
        py, pq = _parse_ledger_year_quarter(uploaded.name)
        if py:
            ledger_year = py
            st.caption(f"识别到 {py} 年 Q{quarter}")
        else:
            st.caption(f"文件名格式：账页-YYYY-q{quarter}.csv")
    imported = False
    if st.button("导入", key=f"btn_{key}", disabled=(uploaded is None), use_container_width=True):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        try:
            # Use detected year, fallback to latest year in DB
            if ledger_year is None:
                conn = get_conn()
                row = conn.execute("SELECT MAX(year) FROM raw_ledger").fetchone()
                conn.close()
                ledger_year = row[0] if row and row[0] else None
            if ledger_year is None:
                st.error("无法识别年份，请检查文件名格式（账页-YYYY-qN.csv）")
            else:
                n = import_ledger(tmp_path, ledger_year, quarter)
                st.success(f"✓ {n:,} 条（{ledger_year}年Q{quarter}）")
                _get_counts.clear()
                st.cache_data.clear()
                st.rerun()
        except Exception as e:
            st.error(f"✗ {e}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    st.markdown("</div>", unsafe_allow_html=True)
    return imported


def render(months: list):
    st.markdown(
        '<div class="page-header">'
        '<h2>数据详情</h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    init_db()
    _show_counts()

    # ── 一键计算按钮，2/3 宽度居中 ──
    _, c, _ = st.columns([1, 2, 1])
    with c:
        if st.button("一键计算", type="primary", use_container_width=True, key="btn_pipeline"):
            _run_pipeline(months)

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    # ── 导入数据模块标题 ──
    st.markdown(
        '<div style="font-size:15px;font-weight:600;color:#1E293B;margin-bottom:6px">导入数据</div>',
        unsafe_allow_html=True,
    )

    tab_sample, tab_survey, tab_ledger = st.tabs(["样本", "问卷", "账页"])

    with tab_sample:
        c1, c2, c3 = st.columns(3)
        with c1:
            _upload_card("building", "小区", "up_village", import_village, "#2563EB")
        with c2:
            _upload_card("buildings", "住宅", "up_house", import_house, "#3B82F6")
        with c3:
            _upload_card("house", "住户", "up_household", import_household, "#60A5FA")

    with tab_survey:
        c1, c2 = st.columns(2)
        with c1:
            _upload_card("file-earmark-text", "A表（成员问卷）", "up_survey_a", import_survey_a, "#10B981")
        with c2:
            _upload_card("file-earmark-spreadsheet", "B表（住房问卷）", "up_survey_b", import_survey_b, "#F59E0B")

    with tab_ledger:
        q_colors = {1: "#EF4444", 2: "#F59E0B", 3: "#3B82F6", 4: "#10B981"}
        c1, c2, c3, c4 = st.columns(4)
        for col, q in [(c1, 1), (c2, 2), (c3, 3), (c4, 4)]:
            with col:
                _ledger_quarter_card(q, f"up_ledger_q{q}", q_colors[q])
