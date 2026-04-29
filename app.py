import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import streamlit as st
from src.io.database import get_conn, init_db
from src.ui._styles import get_global_css

st.set_page_config(
    page_title="记账户画像辅导工具",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><text y='14' font-size='14'>▪</text></svg>",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(get_global_css(), unsafe_allow_html=True)

init_db()


@st.cache_data(ttl=30)
def _get_available_months():
    try:
        conn = get_conn()
        df = pd.read_sql(
            "SELECT DISTINCT year, month FROM raw_ledger ORDER BY year, month", conn
        )
        conn.close()
        return [(int(r["year"]), int(r["month"])) for _, r in df.iterrows()]
    except Exception:
        return []


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="padding:28px 20px 20px">'
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">'
        '<div style="width:28px;height:28px;background:rgba(59,130,246,0.2);'
        'border-radius:8px;display:flex;align-items:center;justify-content:center">'
        '<i class="bi bi-bar-chart-line" style="font-size:14px;color:#60A5FA"></i>'
        '</div>'
        '<div style="font-size:14px;font-weight:700;color:#FFFFFF;letter-spacing:0.01em">'
        '记账户画像辅导</div>'
        '</div>'
        '<div style="font-size:12px;color:#64748B;margin-left:38px;letter-spacing:0.01em">'
        '泰州调查队</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr>', unsafe_allow_html=True)

    PAGES = {
        "导入数据": "导入数据",
        "画像总览": "画像总览",
        "画像分群": "画像分群",
        "辅导清单": "辅导清单",
        "住户详情": "住户详情",
    }
    if "nav_page" not in st.session_state:
        st.session_state["nav_page"] = "画像总览"
    if "nav_target" in st.session_state:
        target = st.session_state.pop("nav_target")
        if target in PAGES:
            st.session_state["nav_widget"] = target
    elif "nav_widget" not in st.session_state:
        st.session_state["nav_widget"] = st.session_state["nav_page"]
    page_label = st.radio(
        "导航",
        list(PAGES.keys()),
        key="nav_widget",
        label_visibility="collapsed",
    )
    st.session_state["nav_page"] = page_label
    page = PAGES[page_label]

    st.markdown('<hr>', unsafe_allow_html=True)

    month_list = _get_available_months()
    if month_list:
        month_labels = [f"{y}年{m}月" for y, m in month_list]
        start_i = st.selectbox(
            "开始月份", range(len(month_list)),
            format_func=lambda i: month_labels[i],
            key="start_month",
        )
        end_i = st.selectbox(
            "结束月份", range(len(month_list)),
            index=len(month_list) - 1,
            format_func=lambda i: month_labels[i],
            key="end_month",
        )
        lo, hi = min(start_i, end_i), max(start_i, end_i)
        months_sel = month_list[lo:hi + 1]
    else:
        months_sel = []
        st.caption("请先在「导入数据」中上传账页")

    st.markdown('<hr>', unsafe_allow_html=True)

    quality_filter = st.multiselect(
        "辅导关注度",
        ["A 常规", "B 常规", "C 关注", "D 重点"],
        default=["A 常规", "B 常规", "C 关注", "D 重点"],
    )
    quality_levels = [q[0] for q in quality_filter]

filters = {"coun_list": [], "quality_levels": quality_levels}

# ── 路由 ───────────────────────────────────────────────────────────────────────
if page == "导入数据":
    from src.ui.data_mgmt import render
    render(months_sel)
elif page == "画像总览":
    from src.ui.overview import render
    render(months_sel, filters)
elif page == "画像分群":
    from src.ui.segments import render
    render(months_sel, filters)
elif page == "住户详情":
    from src.ui.household_detail import render
    render(months_sel)
elif page == "辅导清单":
    from src.ui.audit_center import render
    render(months_sel, filters)
