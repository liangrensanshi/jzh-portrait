"""
Multi-quarter trend page (v1 placeholder).
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..io.database import get_conn


def render():
    st.markdown(
        '<div class="page-header">'
        '<h2>历史对比</h2>'
        '<p>多季度趋势分析</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.info("本页面为 v1 占位版，仅显示指定住户的季度得分变化。完整聚合分析将在 v2 完善。")

    conn = get_conn()
    households = pd.read_sql(
        "SELECT DISTINCT h.hhid, h.hname FROM raw_households h", conn
    )
    conn.close()

    if households.empty:
        st.warning("暂无数据")
        return

    options = households.apply(
        lambda r: f"{r['hhid']} · {r['hname']}", axis=1
    ).tolist()
    sel_idx = st.selectbox("选择住户", range(len(options)), format_func=lambda i: options[i])
    hhid = households.iloc[sel_idx]["hhid"]

    conn = get_conn()
    history = pd.read_sql(
        "SELECT m.year, m.quarter, m.income_total, m.consume_total, "
        "m.ledger_count, m.max_gap_days, l.quality_score, l.label_quality "
        "FROM household_metrics m "
        "LEFT JOIN household_labels l ON m.hhid=l.hhid AND m.year=l.year AND m.quarter=l.quarter "
        "WHERE m.hhid=? ORDER BY m.year, m.quarter",
        conn, params=(hhid,),
    )
    conn.close()

    if history.empty:
        st.info("该住户暂无历史数据")
        return

    history["期次"] = history.apply(
        lambda r: f"{int(r['year'])} Q{int(r['quarter'])}", axis=1
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=history["期次"], y=history["income_total"].astype(float),
        name="收入总额", mode="lines+markers",
        line=dict(color="#3B82F6", width=2.5),
        marker=dict(size=8, color="#3B82F6", line=dict(color="#FFFFFF", width=2)),
    ))
    fig.add_trace(go.Scatter(
        x=history["期次"], y=history["consume_total"].astype(float),
        name="消费总额", mode="lines+markers",
        line=dict(color="#0F172A", width=2.5),
        marker=dict(size=8, color="#0F172A", line=dict(color="#FFFFFF", width=2)),
    ))
    if "quality_score" in history.columns:
        fig.add_trace(go.Scatter(
            x=history["期次"], y=history["quality_score"].fillna(0).astype(float),
            name="质量分", mode="lines+markers", yaxis="y2",
            line=dict(dash="dot", color="#F59E0B", width=2),
            marker=dict(size=7, color="#F59E0B", line=dict(color="#FFFFFF", width=2)),
        ))
    fig.update_layout(
        title=dict(text=f"{hhid} 季度趋势", font=dict(size=16, color="#0F172A")),
        yaxis=dict(title="金额（元）", gridcolor="#F1F5F9", tickfont=dict(color="#94A3B8")),
        yaxis2=dict(title="质量分", overlaying="y", side="right", range=[0, 100],
                    tickfont=dict(color="#94A3B8")),
        xaxis=dict(gridcolor="#F1F5F9", tickfont=dict(color="#64748B")),
        height=400,
        hovermode="x unified",
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font=dict(family="Inter, Microsoft YaHei", size=11, color="#64748B"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=0, r=0, t=60, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        history[["期次", "income_total", "consume_total", "ledger_count",
                 "max_gap_days", "quality_score", "label_quality"]].rename(columns={
            "income_total": "收入总额", "consume_total": "消费总额",
            "ledger_count": "记账条数", "max_gap_days": "最长断记天数",
            "quality_score": "质量分", "label_quality": "质量等级",
        }),
        use_container_width=True, hide_index=True,
    )
