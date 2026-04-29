"""画像总览页"""
from html import escape
from pathlib import Path
from textwrap import dedent

import pandas as pd
import streamlit as st
import yaml

from ..io.database import get_conn
from ._utils import norm_counname, period_display

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

QUALITY_COLOR = {"A": "#0EA870", "B": "#2F6FDB", "C": "#D98A00", "D": "#D93A35"}
QUALITY_LABEL = {"A": "优秀", "B": "良好", "C": "需关注", "D": "需核查"}
COACHING_LABEL = {"A": "常规辅导", "B": "常规辅导", "C": "关注辅导", "D": "重点辅导"}
COACHING_SHORT = {"A": "常规", "B": "常规", "C": "关注", "D": "重点"}
COACHING_TONE = {"常规": "normal", "关注": "watch", "重点": "key"}
ACNTTYPE_MAP = {"0": "纸质", "1": "电子", "2": "多人", 0: "纸质", 1: "电子", 2: "多人"}

RULE_COACHING = {
    "R01": "建议提醒住户尽量随手记录，减少月底集中补记。",
    "R02": "本户记账规律性偏弱，建议提醒保持日常消费连续记录。",
    "R03": "本户存在较长生活记录空档，建议入户核实并辅导补记。",
    "R04": "本期食品烟酒记录缺失，建议重点核实日常买菜、餐饮等消费。",
    "R07": "消费率偏低，建议核实日常消费和大额支出是否漏记。",
    "R10": "本户某月生活轨迹缺失，建议核实该月实际收支并补记。",
    "L01": "本户有学龄子女，建议核实学习用品、培训费、伙食费等记录。",
    "L04": "本户有离退休成员，建议核实养老金和医疗支出记录。",
    "L05": "建议同步核实就业情况和工资收入记录口径。",
    "L08": "收支差距较大，建议核实大额收入、支出或非消费支出是否完整。",
    "L09": "食品支出偏低，建议核实日常买菜、外食等是否完整记录。",
    "N01": "有大额收支记录，建议确认金额、品名和收支类别。",
    "N02": "消费结构较集中，建议询问其他生活类别是否有漏记。",
    "Q01": "建议补充大额记录的具体品名，方便后续回忆和复核。",
}


@st.cache_data(ttl=30)
def _load_overview_data():
    conn = get_conn()
    metrics = pd.read_sql("SELECT * FROM household_metrics", conn)
    labels = pd.read_sql("SELECT * FROM household_labels", conn)
    households = pd.read_sql(
        "SELECT h.hhid, h.coun, h.vcode, h.hname, h.acnttype, h.opendate "
        "FROM raw_households h",
        conn,
    )
    villages = pd.read_sql(
        "SELECT vcode, coun, counname, townname, vname FROM raw_villages", conn
    )
    audit_df = pd.read_sql(
        "SELECT rule_id, rule_priority, hhid, advice_text FROM audit_results", conn
    )
    snapshot = pd.read_sql(
        "SELECT hhid, visit_priority_score FROM current_snapshot", conn
    )
    conn.close()
    return metrics, labels, households, villages, audit_df, snapshot


@st.cache_data(ttl=30)
def _load_segments_config():
    path = CONFIG_DIR / "segments.yaml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f).get("segments", [])


def _fmt(value, digits=0):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.{digits}f}" if digits else f"{float(value):,.0f}"


def _update_date(labels: pd.DataFrame, metrics: pd.DataFrame) -> str:
    vals = []
    for df in (labels, metrics):
        if "updated_at" in df.columns and df["updated_at"].notna().any():
            vals.append(pd.to_datetime(df["updated_at"], errors="coerce").max())
    vals = [v for v in vals if pd.notna(v)]
    if vals:
        return max(vals).strftime("%Y-%m-%d")
    return pd.Timestamp.today().strftime("%Y-%m-%d")


def _coaching_short(q):
    return COACHING_SHORT.get(str(q), "常规")


def _acnttype_label(value):
    return ACNTTYPE_MAP.get(value, ACNTTYPE_MAP.get(str(value), "未知"))


def _percent_rows(series: pd.Series, order=None, names=None) -> list[tuple[str, int, float]]:
    clean = series.fillna("未分类").astype(str)
    counts = clean.value_counts()
    if order:
        counts = counts.reindex(order, fill_value=0)
        counts = counts[counts > 0]
    total = max(int(counts.sum()), 1)
    rows = []
    for name, count in counts.items():
        label = names.get(name, name) if names else name
        rows.append((str(label), int(count), int(count) / total * 100))
    return rows


def _distribution_card(title, rows, note, tone="blue"):
    chips = []
    for name, count, pct in rows[:5]:
        chips.append(
            f'<div class="portrait-mini-row"><span>{escape(name)}</span>'
            f'<b>{pct:.0f}%</b><em>{count}户</em></div>'
        )
    if not chips:
        chips.append('<div class="portrait-empty">暂无数据</div>')
    return dedent(f"""
    <div class="portrait-card {tone}">
      <div class="portrait-card-title">{escape(title)}</div>
      <div class="portrait-card-body">{''.join(chips)}</div>
      <div class="portrait-card-note">{escape(note)}</div>
    </div>
    """).strip()


def _distribution_note(rows, default):
    if not rows:
        return default
    top_name, _, top_pct = rows[0]
    return f"以{top_name}为主，占比约 {top_pct:.0f}%。"


def _apply_segment_filter(df: pd.DataFrame, filter_def: dict) -> pd.DataFrame:
    view = df.copy()
    for key, value in (filter_def or {}).items():
        if key.endswith("_gt"):
            col = key[:-3]
            view = view[pd.to_numeric(view.get(col), errors="coerce").fillna(0) > float(value)]
        elif key.endswith("_lt"):
            col = key[:-3]
            view = view[pd.to_numeric(view.get(col), errors="coerce").fillna(0) < float(value)]
        else:
            view = view[view.get(key).fillna("").astype(str) == str(value)]
    return view


def _segment_counts(df: pd.DataFrame, segments: list) -> dict:
    return {
        seg["id"]: len(_apply_segment_filter(df, seg.get("filter", {})))
        for seg in segments
    }


def _quality_ring(q_counts, total):
    acc = 0.0
    stops = []
    for level in ["A", "B", "C", "D"]:
        count = int(q_counts.get(level, 0))
        pct = count / total * 100 if total else 0
        start, end = acc, acc + pct
        stops.append(f"{QUALITY_COLOR[level]} {start:.2f}% {end:.2f}%")
        acc = end
    ring_bg = ", ".join(stops) if stops else "#E5E7EB 0 100%"
    rows = []
    for level in ["A", "B", "C", "D"]:
        count = int(q_counts.get(level, 0))
        pct = count / total * 100 if total else 0
        rows.append(
            f'<div class="quality-row"><span style="background:{QUALITY_COLOR[level]}"></span>'
            f'<b>{level} {QUALITY_LABEL[level]}</b><em>{pct:.1f}%</em><strong>{count}</strong></div>'
        )
    return dedent(f"""
    <div class="quality-wrap">
      <div class="quality-ring" style="background:conic-gradient({ring_bg})">
        <div><b>{total:,}</b><span>户</span></div>
      </div>
      <div class="quality-list">{''.join(rows)}</div>
    </div>
    """).strip()


def _county_quality_table(merged: pd.DataFrame, audit_f: pd.DataFrame):
    if merged.empty or not merged["counname"].notna().any():
        st.caption("暂无县区信息。")
        return
    issue_by_hh = audit_f.groupby("hhid").size().rename("辅导提示数").reset_index()
    county = (
        merged.merge(issue_by_hh, on="hhid", how="left")
        .assign(辅导提示数=lambda d: d["辅导提示数"].fillna(0))
        .groupby("counname")
        .agg(
            户数=("hhid", "count"),
            平均质量分=("quality_score", "mean"),
            有提示户=("辅导提示数", lambda s: int((s > 0).sum())),
        )
        .reset_index()
        .rename(columns={"counname": "县区"})
    )
    county["平均质量分"] = county["平均质量分"].round(1)
    county["提示覆盖率"] = (county["有提示户"] / county["户数"] * 100).round(1)
    county = county.sort_values("平均质量分", ascending=False)
    st.dataframe(county, use_container_width=True, hide_index=True, height=260)


def _render_quality_expander(merged, labels_f, audit_f):
    total = len(labels_f)
    avg_score = float(labels_f["quality_score"].dropna().mean()) if total else 0
    q_counts = labels_f["label_quality"].value_counts().reindex(["A", "B", "C", "D"], fill_value=0)
    good_pct = (q_counts["A"] + q_counts["B"]) / total * 100 if total else 0
    issue_hhs = audit_f["hhid"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("记账户数", f"{total:,}")
    c2.metric("平均质量分", f"{avg_score:.1f}")
    c3.metric("A/B 占比", f"{good_pct:.1f}%")
    c4.metric("有辅导提示户", f"{issue_hhs:,}")

    left, right = st.columns([1, 1.25])
    with left:
        st.markdown(_quality_ring(q_counts, total), unsafe_allow_html=True)
    with right:
        st.markdown("**区县质量排名**")
        _county_quality_table(merged, audit_f)

    if not audit_f.empty:
        st.markdown("**高频辅导提示**")
        stats = (
            audit_f.groupby(["rule_id", "rule_priority"])
            .agg(户数=("hhid", "nunique"))
            .reset_index()
            .sort_values("户数", ascending=False)
            .head(8)
        )
        stats["辅导提示"] = stats["rule_id"].map(RULE_COACHING).fillna(stats["rule_id"])
        st.dataframe(
            stats[["rule_id", "rule_priority", "户数", "辅导提示"]],
            use_container_width=True,
            hide_index=True,
            height=310,
        )


def _render_segment_buttons(df: pd.DataFrame, segments: list):
    counts = _segment_counts(df, segments)
    cols = st.columns(3)
    for idx, seg in enumerate(segments):
        with cols[idx % 3]:
            label = f"{seg['name']}（{counts.get(seg['id'], 0)}户）"
            if st.button(label, key=f"segment_jump_{seg['id']}", use_container_width=True):
                st.session_state["selected_segment_id"] = seg["id"]
                st.session_state["nav_target"] = "画像分群"
                st.rerun()
            st.caption(seg.get("coaching_focus", ""))


def _top_coaching_rows(df: pd.DataFrame, audit_f: pd.DataFrame, limit=10):
    priority = {"D": 3, "C": 2, "B": 1, "A": 1}
    base = df.copy()
    audit_count = audit_f.groupby("hhid").size().rename("audit_count").reset_index()
    first_rule = (
        audit_f.sort_values(
            "rule_priority",
            key=lambda s: s.map({"high": 0, "medium": 1, "low": 2}).fillna(9),
        )
        .drop_duplicates("hhid")[["hhid", "rule_id"]]
        if not audit_f.empty else pd.DataFrame(columns=["hhid", "rule_id"])
    )
    base = base.merge(audit_count, on="hhid", how="left").merge(first_rule, on="hhid", how="left")
    base["audit_count"] = base["audit_count"].fillna(0)
    base["_level_sort"] = base["label_quality"].map(priority).fillna(0)
    base["visit_priority_score"] = pd.to_numeric(base.get("visit_priority_score"), errors="coerce").fillna(0)
    base = base.sort_values(
        ["_level_sort", "visit_priority_score", "audit_count", "quality_score"],
        ascending=[False, False, False, True],
    )
    return base.head(limit)


def _render_coaching_list(df: pd.DataFrame, audit_f: pd.DataFrame):
    rows = _top_coaching_rows(df, audit_f)
    if rows.empty:
        st.info("暂无需要重点辅导的住户。")
        return
    for _, row in rows.iterrows():
        q = row.get("label_quality", "A")
        level = _coaching_short(q)
        tone = COACHING_TONE.get(level, "normal")
        advice = RULE_COACHING.get(row.get("rule_id"), "保持现有辅导节奏，关注本期收支记录是否完整。")
        summary = row.get("portrait_summary") or "画像摘要待生成"
        left, right = st.columns([6, 1])
        with left:
            st.markdown(
                dedent(f"""
                <div class="coaching-row {tone}">
                  <div class="coaching-icon">{escape(level)}</div>
                  <div class="coaching-main">
                    <div><b>{escape(str(row.get('hname') or '未命名住户'))}</b>
                    <span>{escape(str(row.get('hhid') or ''))}</span></div>
                    <p>{escape(str(summary))}</p>
                    <em>{escape(advice)}</em>
                  </div>
                </div>
                """).strip(),
                unsafe_allow_html=True,
            )
        with right:
            if st.button("查看", key=f"open_hh_{row.get('hhid')}", use_container_width=True):
                st.session_state["selected_hhid"] = row.get("hhid")
                st.session_state["nav_target"] = "住户详情"
                st.rerun()


def _css():
    return """
<style>
.block-container { max-width: 1480px !important; padding-top: 30px !important; }
.portrait-page {
  --ink:#102033; --muted:#6B778C; --line:#D9E1EA; --panel:#FFFFFF;
  --paper:#F6F8FB; --green:#14885F; --blue:#2F6FDB; --gold:#C57A00; --red:#CF3B35;
  color:var(--ink); font-family:"Aptos","Segoe UI","Microsoft YaHei",sans-serif;
}
.portrait-page * { box-sizing:border-box; }
.portrait-head { margin-bottom:18px; padding-bottom:12px; border-bottom:1px solid #E2E8F0; }
.portrait-head h1 { margin:0 0 8px; font-size:30px; line-height:1.15; letter-spacing:0; color:#07111F; }
.portrait-head p { margin:0; color:#718096; font-size:14px; }
.portrait-section-title { margin:22px 0 12px; display:flex; align-items:flex-end; justify-content:space-between; gap:12px; }
.portrait-section-title h2 { margin:0; font-size:18px; color:#07111F; letter-spacing:0; }
.portrait-section-title span { color:#7D8A9D; font-size:12px; }
.portrait-grid { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:12px; }
.portrait-card {
  min-height:218px; background:#FFFFFF; border:1px solid var(--line); border-radius:12px;
  padding:16px; box-shadow:0 10px 28px rgba(16,32,51,.045); position:relative; overflow:hidden;
}
.portrait-card:before { content:""; position:absolute; inset:0 0 auto; height:4px; background:#2F6FDB; }
.portrait-card.green:before { background:#14885F; }
.portrait-card.gold:before { background:#C57A00; }
.portrait-card.red:before { background:#CF3B35; }
.portrait-card-title { font-size:14px; font-weight:900; color:#0F172A; margin-bottom:14px; }
.portrait-mini-row {
  display:grid; grid-template-columns:minmax(0,1fr) 44px 44px; gap:8px; align-items:center;
  min-height:28px; border-bottom:1px solid #EEF2F7;
}
.portrait-mini-row:last-child { border-bottom:0; }
.portrait-mini-row span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; color:#263345; }
.portrait-mini-row b { text-align:right; font-size:14px; color:#07111F; }
.portrait-mini-row em { text-align:right; font-style:normal; font-size:11px; color:#8A97A8; }
.portrait-card-note { margin-top:12px; color:#7D8A9D; font-size:12px; line-height:1.55; }
.portrait-empty { color:#9AA6B5; font-size:13px; padding:20px 0; }
.segment-panel {
  background:#FFFFFF; border:1px solid #D9E1EA; border-radius:12px; padding:16px 18px;
  box-shadow:0 10px 28px rgba(16,32,51,.04);
}
.coaching-row {
  min-height:86px; display:grid; grid-template-columns:64px 1fr; gap:14px; align-items:center;
  background:#FFFFFF; border:1px solid #DCE3EC; border-left:4px solid #2F6FDB;
  border-radius:12px; padding:12px 14px; margin-bottom:10px; box-shadow:0 8px 22px rgba(16,32,51,.035);
}
.coaching-row.watch { border-left-color:#C57A00; }
.coaching-row.key { border-left-color:#CF3B35; }
.coaching-icon {
  width:52px; height:52px; border-radius:10px; display:grid; place-items:center;
  background:#EEF4FF; color:#2F6FDB; font-size:13px; font-weight:900;
}
.coaching-row.watch .coaching-icon { background:#FFF7E8; color:#C57A00; }
.coaching-row.key .coaching-icon { background:#FFF0EF; color:#CF3B35; }
.coaching-main div { display:flex; gap:10px; align-items:baseline; }
.coaching-main b { font-size:15px; color:#07111F; }
.coaching-main span { font-size:12px; color:#94A3B8; }
.coaching-main p { margin:5px 0 4px; color:#263345; font-size:13px; }
.coaching-main em { color:#6B778C; font-style:normal; font-size:12px; line-height:1.45; }
.quality-wrap { display:grid; grid-template-columns:220px 1fr; gap:18px; align-items:center; }
.quality-ring { width:200px; height:200px; border-radius:50%; display:grid; place-items:center; margin:auto; }
.quality-ring > div { width:124px; height:124px; border-radius:50%; background:#fff; display:grid; place-items:center; align-content:center; box-shadow:0 10px 26px rgba(16,32,51,.08); }
.quality-ring b { font-size:30px; line-height:1; }
.quality-ring span { color:#7D8A9D; font-size:12px; }
.quality-row { display:grid; grid-template-columns:12px 1fr 58px 46px; align-items:center; gap:8px; min-height:34px; border-bottom:1px solid #EDF2F7; }
.quality-row span { width:8px; height:8px; border-radius:50%; }
.quality-row b { font-size:13px; }
.quality-row em { text-align:right; color:#8090A4; font-size:12px; font-style:normal; }
.quality-row strong { text-align:right; font-size:13px; }
@media (max-width: 1280px) { .portrait-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) { .portrait-grid, .quality-wrap { grid-template-columns:1fr; } }
</style>
"""


def render(months: list, filters: dict):
    metrics, labels, households, villages, audit_df, snapshot = _load_overview_data()
    st.markdown(_css(), unsafe_allow_html=True)

    if metrics.empty or labels.empty:
        st.info("当前暂无画像数据，请先在「导入数据」中上传账页并运行计算。")
        return

    if filters.get("coun_list"):
        households = households[households["coun"].isin(filters["coun_list"])]

    labels_f = labels.copy()
    if filters.get("quality_levels"):
        labels_f = labels_f[labels_f["label_quality"].isin(filters["quality_levels"])]

    filtered_hhids = set(households["hhid"]).intersection(set(labels_f["hhid"]))
    labels_f = labels_f[labels_f["hhid"].isin(filtered_hhids)].copy()
    if labels_f.empty:
        st.warning("当前筛选条件下没有画像数据。")
        return

    merged = (
        labels_f
        .merge(households[["hhid", "coun", "vcode", "hname", "acnttype", "opendate"]], on="hhid", how="left")
        .merge(villages[["vcode", "coun", "counname", "townname", "vname"]].drop_duplicates(), on=["vcode", "coun"], how="left")
        .merge(metrics, on="hhid", how="left", suffixes=("", "_metric"))
        .merge(snapshot, on="hhid", how="left")
    )
    merged["counname"] = merged["counname"].apply(norm_counname)
    merged["acnttype_label"] = merged["acnttype"].apply(_acnttype_label)
    merged["coaching_level"] = merged["label_quality"].apply(_coaching_short)
    merged["consume_rate"] = merged.apply(
        lambda r: float(r.get("consume_total") or 0) / float(r.get("income_total") or 1)
        if float(r.get("income_total") or 0) > 0 else 0,
        axis=1,
    )

    audit_f = audit_df[audit_df["hhid"].isin(filtered_hhids)].copy()
    total = len(labels_f)
    period = period_display(months)

    st.markdown(
        dedent(f"""
        <div class="portrait-page">
          <section class="portrait-head">
            <h1>泰州样本户画像总览</h1>
            <p>当前期 {escape(period)}　|　{total:,} 户　|　数据更新 {_update_date(labels_f, metrics)}</p>
          </section>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )

    income_rows = _percent_rows(
        merged["label_income"],
        order=["工薪型", "经营型", "转移型", "混合型", "无收入记录"],
    )
    life_rows = _percent_rows(
        merged["label_lifecycle"],
        order=["单人户", "夫妻户", "中青年核心家庭", "三代同堂", "老年家庭", "幼儿家庭", "学龄家庭", "其他"],
        names={"中青年核心家庭": "中青年", "幼儿家庭": "有幼儿", "学龄家庭": "有学生"},
    )
    mobility_rows = _percent_rows(merged["label_mobility"], order=["全家常住", "半流动", "整户外出"])
    acnt_rows = _percent_rows(merged["acnttype_label"], order=["电子", "纸质", "多人", "未知"])
    coaching_rows = _percent_rows(merged["coaching_level"], order=["常规", "关注", "重点"])

    st.markdown(
        '<div class="portrait-page"><div class="portrait-section-title">'
        '<h2>画像分布</h2><span>从辅导工作需要出发看样本户结构</span></div></div>',
        unsafe_allow_html=True,
    )
    cards = [
        _distribution_card("收入结构", income_rows, _distribution_note(income_rows, "按主要收入来源划分。"), "blue"),
        _distribution_card("家庭生命周期", life_rows, _distribution_note(life_rows, "按成员年龄和家庭结构划分。"), "green"),
        _distribution_card("流动状态", mobility_rows, _distribution_note(mobility_rows, "关注外出带来的记账连续性。"), "gold"),
        _distribution_card("记账方式", acnt_rows, _distribution_note(acnt_rows, "来自住户 ACNTTYPE 字段。"), "blue"),
        _distribution_card("辅导关注度", coaching_rows, _distribution_note(coaching_rows, "由质量等级翻译为辅导语言。"), "red"),
    ]
    st.markdown(f'<div class="portrait-page"><section class="portrait-grid">{"".join(cards)}</section></div>', unsafe_allow_html=True)

    segments = _load_segments_config()
    st.markdown(
        '<div class="portrait-page"><div class="portrait-section-title">'
        '<h2>画像分群快速入口</h2><span>点击进入该群体画像列表</span></div>'
        '<div class="segment-panel">',
        unsafe_allow_html=True,
    )
    _render_segment_buttons(merged, segments)
    st.markdown("</div></div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="portrait-page"><div class="portrait-section-title">'
        '<h2>辅导关注清单</h2><span>按本期辅导紧迫度展示前 10 户</span></div></div>',
        unsafe_allow_html=True,
    )
    _render_coaching_list(merged, audit_f)

    with st.expander("数据质量概况（管理视角）", expanded=False):
        _render_quality_expander(merged, labels_f, audit_f)
