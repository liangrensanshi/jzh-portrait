"""画像分群页"""
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from ..io.database import get_conn
from ._utils import norm_counname, period_display

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
COACHING_SHORT = {"A": "常规", "B": "常规", "C": "关注", "D": "重点"}


@st.cache_data(ttl=30)
def _load_segments_config():
    with open(CONFIG_DIR / "segments.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f).get("segments", [])


@st.cache_data(ttl=30)
def _load_segment_data():
    conn = get_conn()
    metrics = pd.read_sql("SELECT * FROM household_metrics", conn)
    labels = pd.read_sql("SELECT * FROM household_labels", conn)
    households = pd.read_sql(
        "SELECT h.hhid, h.hname, h.coun, h.vcode, h.acnttype, h.opendate, "
        "v.counname, v.townname, v.vname "
        "FROM raw_households h "
        "LEFT JOIN raw_villages v ON h.vcode=v.vcode AND h.coun=v.coun",
        conn,
    )
    conn.close()
    return metrics, labels, households


def _apply_segment_filter(df: pd.DataFrame, filter_def: dict) -> pd.DataFrame:
    view = df.copy()
    for key, value in (filter_def or {}).items():
        if key.endswith("_gt"):
            col = key[:-3]
            view = view[pd.to_numeric(view[col], errors="coerce").fillna(0) > float(value)]
        elif key.endswith("_lt"):
            col = key[:-3]
            view = view[pd.to_numeric(view[col], errors="coerce").fillna(0) < float(value)]
        else:
            view = view[view[key].fillna("").astype(str) == str(value)]
    return view


def _fmt_money(value):
    if pd.isna(value):
        return ""
    return f"{float(value):,.0f}"


def _prepare_data(filters):
    metrics, labels, households = _load_segment_data()
    if metrics.empty or labels.empty:
        return pd.DataFrame()

    labels_f = labels.copy()
    if filters.get("quality_levels"):
        labels_f = labels_f[labels_f["label_quality"].isin(filters["quality_levels"])]

    df = (
        labels_f
        .merge(metrics, on="hhid", how="left", suffixes=("", "_metric"))
        .merge(households, on="hhid", how="left")
    )
    df["counname"] = df["counname"].apply(norm_counname)
    df["coaching_level"] = df["label_quality"].map(COACHING_SHORT).fillna("常规")
    df["consume_rate"] = df.apply(
        lambda r: float(r.get("consume_total") or 0) / float(r.get("income_total") or 1)
        if float(r.get("income_total") or 0) > 0 else 0,
        axis=1,
    )
    return df


def _render_feature_distribution(seg_df: pd.DataFrame, all_df: pd.DataFrame):
    if seg_df.empty:
        st.info("该分群暂无住户。")
        return

    c1, c2, c3 = st.columns(3)

    with c1:
        bins = [-1, 0, 10000, 30000, 60000, float("inf")]
        names = ["无收入", "1万以下", "1-3万", "3-6万", "6万以上"]
        income_bins = pd.cut(
            pd.to_numeric(seg_df["income_total"], errors="coerce").fillna(0),
            bins=bins,
            labels=names,
        )
        st.markdown("**收入水平区间**")
        st.dataframe(
            income_bins.value_counts().reindex(names, fill_value=0).rename_axis("区间").reset_index(name="户数"),
            use_container_width=True,
            hide_index=True,
            height=230,
        )

    with c2:
        consume_cols = {
            "食品烟酒": "consume_food",
            "衣着": "consume_clothing",
            "居住": "consume_housing",
            "生活用品": "consume_daily",
            "交通通信": "consume_transport",
            "教育文娱": "consume_edu",
            "医疗保健": "consume_medical",
            "其他": "consume_other",
        }
        sums = {
            name: float(pd.to_numeric(seg_df[col], errors="coerce").fillna(0).sum())
            for name, col in consume_cols.items()
        }
        total = max(sum(sums.values()), 1)
        consume_view = pd.DataFrame({
            "类别": list(sums.keys()),
            "金额": [round(v, 0) for v in sums.values()],
            "占比": [f"{v / total * 100:.1f}%" for v in sums.values()],
        }).sort_values("金额", ascending=False)
        st.markdown("**主要消费类别**")
        st.dataframe(consume_view, use_container_width=True, hide_index=True, height=230)

    with c3:
        seg_income = float(seg_df["income_total"].fillna(0).mean())
        all_income = float(all_df["income_total"].fillna(0).mean())
        seg_consume = float(seg_df["consume_total"].fillna(0).mean())
        all_consume = float(all_df["consume_total"].fillna(0).mean())
        seg_rate = float(seg_df["consume_rate"].fillna(0).mean())
        all_rate = float(all_df["consume_rate"].fillna(0).mean())
        diff = pd.DataFrame({
            "指标": ["户均收入", "户均消费", "平均消费率"],
            "本群体": [_fmt_money(seg_income), _fmt_money(seg_consume), f"{seg_rate * 100:.1f}%"],
            "全样本": [_fmt_money(all_income), _fmt_money(all_consume), f"{all_rate * 100:.1f}%"],
        })
        st.markdown("**与全样本相比**")
        st.dataframe(diff, use_container_width=True, hide_index=True, height=230)


def _render_household_list(seg_df: pd.DataFrame):
    view = seg_df.copy()
    display = pd.DataFrame({
        "户主": view["hname"].fillna(""),
        "一句话画像": view["portrait_summary"].fillna("画像摘要待生成"),
        "县区": view["counname"].fillna(""),
        "收入": view["income_total"].apply(_fmt_money),
        "消费": view["consume_total"].apply(_fmt_money),
        "关注度": view["coaching_level"].fillna("常规"),
    })
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=min(520, 44 + len(display) * 35),
    )

    if seg_df.empty:
        return
    options = seg_df["hhid"].tolist()
    name_map = dict(zip(seg_df["hhid"], seg_df["hname"].fillna("")))
    selected = st.selectbox(
        "打开个体画像",
        options,
        format_func=lambda h: f"{name_map.get(h, '')}（{h}）",
    )
    if st.button("进入住户详情", type="primary"):
        st.session_state["selected_hhid"] = selected
        st.session_state["nav_target"] = "住户详情"
        st.rerun()


def render(months: list, filters: dict):
    period = period_display(months)
    st.markdown(
        f'<div class="page-header"><h2>画像分群</h2><p>{period}</p></div>',
        unsafe_allow_html=True,
    )

    df = _prepare_data(filters)
    if df.empty:
        st.info("当前暂无画像分群数据，请先运行计算。")
        return

    segments = _load_segments_config()
    counts = {
        seg["id"]: len(_apply_segment_filter(df, seg.get("filter", {})))
        for seg in segments
    }
    ids = [seg["id"] for seg in segments]
    default_id = st.session_state.get("selected_segment_id")
    default_idx = ids.index(default_id) if default_id in ids else 0

    selected_name = st.radio(
        "分群",
        [seg["name"] for seg in segments],
        index=default_idx,
        horizontal=True,
    )
    selected_seg = next(seg for seg in segments if seg["name"] == selected_name)
    st.session_state["selected_segment_id"] = selected_seg["id"]

    seg_df = _apply_segment_filter(df, selected_seg.get("filter", {})).copy()
    seg_df = seg_df.sort_values(
        ["label_quality", "consume_rate", "income_total"],
        ascending=[False, True, False],
    )

    st.markdown(
        f"""
<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;
padding:20px 24px;margin-bottom:18px;box-shadow:0 1px 3px rgba(15,23,42,.03)">
  <div style="font-size:22px;font-weight:800;color:#0F172A">
    {selected_seg['name']} · {counts.get(selected_seg['id'], 0)} 户
  </div>
  <div style="font-size:13px;color:#64748B;margin-top:8px;line-height:1.7">
    {selected_seg.get('desc', '')}
  </div>
  <div style="font-size:13px;color:#334155;margin-top:10px;line-height:1.7">
    <b>辅导要点：</b>{selected_seg.get('coaching_focus', '')}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-label">子画像</div>', unsafe_allow_html=True)
    _render_feature_distribution(seg_df, df)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">户列表</div>', unsafe_allow_html=True)
    _render_household_list(seg_df)
