"""住户详情页：个体画像与辅导建议"""
from html import escape
from textwrap import dedent

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..compute.metrics import months_sql_filter
from ..io.database import get_conn
from ..report.renderer import render_visit_card
from ._utils import norm_counname, period_display

GENDER_MAP = {"1": "男", "2": "女"}
RELATION_MAP = {"1": "户主", "2": "配偶", "3": "子/女", "4": "父/母", "5": "孙子/女", "6": "亲属", "7": "其他"}
EDU_MAP = {"1": "未上学", "2": "小学", "3": "初中", "4": "高中/中专", "5": "大专", "6": "本科", "7": "研究生"}
EMPLOYED_MAP = {"1": "在业", "2": "不在业"}
PERM_MAP = {"1": "常住", "2": "非常住"}
URBAN_RURAL_MAP = {"1": "城镇", "2": "农村", 1: "城镇", 2: "农村"}
ACNTTYPE_MAP = {"0": "纸质记账", "1": "电子记账", "2": "多人记账", 0: "纸质记账", 1: "电子记账", 2: "多人记账"}

COACHING_LABEL = {"A": "常规辅导", "B": "常规辅导", "C": "关注辅导", "D": "重点辅导"}
COACHING_TONE = {"A": "normal", "B": "normal", "C": "watch", "D": "key"}

RULE_COACHING = {
    "R01": "本户存在月末集中记录现象，建议提醒住户尽量随手记录，减少月底统一回忆补记。",
    "R02": "本户记账规律性低于同类型户中位水平，建议提醒保持日常消费连续记录。",
    "R03": "本户存在较长生活记录空档，建议入户核实空档期实际收支情况并辅导补记。",
    "R04": "本期未体现食品烟酒支出，建议重点核实买菜、餐饮、粮油等日常消费是否完整记录。",
    "R07": "本户消费率偏低，辅导时建议核实日常消费、大额购物、居住等支出是否漏记。",
    "R10": "本户某月生活轨迹缺失，建议入户核实该月实际收支情况并补记。",
    "L01": "本户有学龄子女，但教育文化娱乐支出偏低，辅导时建议核实学习用品、培训费、伙食费等是否完整记录。",
    "L04": "本户有离退休成员，建议核实养老金、退休工资和医疗保健支出是否完整记录。",
    "L05": "本户就业信息与工资收入记录不完全一致，建议同步核实就业状态和收入编码。",
    "L08": "本户收支差距较大，建议核实大额收入、消费支出或非消费支出是否完整记录。",
    "L09": "本户人均食品支出偏低，建议核实日常买菜、外出就餐、单位食堂等记录是否完整。",
    "N01": "本户存在大额收支记录，建议确认金额、品名和收支类别是否准确。",
    "N02": "本户消费结构较集中，建议询问其他生活类别是否存在漏记。",
    "Q01": "本户部分大额记录缺少具体品名，建议辅导补充商品或服务名称。",
}


def _section(title, note=""):
    sub = f"<span>{escape(note)}</span>" if note else ""
    st.markdown(
        f'<div class="portrait-detail-section"><h3>{escape(title)}</h3>{sub}</div>',
        unsafe_allow_html=True,
    )


def _mask_name(name):
    text = str(name or "")
    if not text:
        return ""
    if len(text) == 1:
        return "*"
    return text[0] + "*" * (len(text) - 1)


def _age(birth, ref_year):
    try:
        return ref_year - int(str(birth)[:4])
    except Exception:
        return ""


def _money(value):
    try:
        return f"{float(value or 0):,.0f}"
    except Exception:
        return "0"


def _acnttype_label(value):
    return ACNTTYPE_MAP.get(value, ACNTTYPE_MAP.get(str(value), "未知记账方式"))


def _css():
    return """
<style>
.portrait-detail {
  --ink:#07111F; --muted:#718096; --line:#DCE3EC; --panel:#FFFFFF;
  --blue:#2F6FDB; --green:#0EA870; --gold:#D98A00; --red:#D93A35;
  color:var(--ink); font-family:"Aptos","Segoe UI","Microsoft YaHei",sans-serif;
}
.portrait-detail * { box-sizing:border-box; }
.detail-hero {
  background:#FFFFFF; border:1px solid #DCE3EC; border-radius:14px;
  padding:24px 28px; margin-bottom:14px; box-shadow:0 12px 30px rgba(7,17,31,.045);
}
.detail-hero h1 { margin:0; font-size:30px; line-height:1.1; letter-spacing:0; color:#07111F; }
.detail-hero .addr { margin-top:8px; color:#64748B; font-size:13px; line-height:1.6; }
.portrait-summary {
  margin-top:16px; padding:14px 16px; background:#F7F9FC; border:1px solid #E4EAF2;
  border-radius:10px; color:#415168; font-size:15px; font-style:italic;
}
.tag-cloud { display:flex; gap:8px; flex-wrap:wrap; margin:14px 0 20px; }
.tag-cloud span {
  display:inline-flex; align-items:center; height:30px; padding:0 12px; border-radius:8px;
  background:#FFFFFF; border:1px solid #DCE3EC; color:#263345; font-size:12px; font-weight:800;
}
.tag-cloud .normal { border-color:#BFEAD8; background:#F0FBF6; color:#0A7A52; }
.tag-cloud .watch { border-color:#F6D391; background:#FFF8EA; color:#B46A00; }
.tag-cloud .key { border-color:#F4B8B5; background:#FFF1F0; color:#C22F2A; }
.portrait-detail-section {
  margin:24px 0 12px; padding-bottom:8px; border-bottom:1px solid #E6ECF3;
  display:flex; align-items:baseline; justify-content:space-between; gap:12px;
}
.portrait-detail-section h3 { margin:0; font-size:17px; color:#07111F; letter-spacing:0; }
.portrait-detail-section span { color:#8090A4; font-size:12px; }
.info-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
.info-tile {
  background:#FFFFFF; border:1px solid #DCE3EC; border-radius:10px; padding:14px 16px;
}
.info-tile b { display:block; font-size:16px; color:#07111F; margin-bottom:6px; }
.info-tile span { color:#718096; font-size:12px; line-height:1.5; }
.peer-card {
  display:grid; grid-template-columns:1.2fr repeat(3,1fr); gap:12px; align-items:stretch;
  background:#0B1320; border-radius:14px; padding:18px; color:#FFFFFF; margin-bottom:10px;
}
.peer-card .peer-note { color:#AFC0D6; font-size:13px; line-height:1.7; }
.peer-metric { border:1px solid rgba(255,255,255,.15); border-radius:12px; padding:14px; background:rgba(255,255,255,.06); }
.peer-metric b { display:block; font-size:28px; line-height:1; margin-bottom:8px; }
.peer-metric span { color:#AFC0D6; font-size:12px; }
.suggestion {
  background:#FFFFFF; border:1px solid #DCE3EC; border-left:4px solid #2F6FDB;
  border-radius:10px; padding:14px 16px; margin-bottom:10px;
}
.suggestion.high { border-left-color:#D93A35; }
.suggestion.medium { border-left-color:#D98A00; }
.suggestion.low { border-left-color:#0EA870; }
.suggestion b { color:#07111F; font-size:13px; }
.suggestion p { margin:6px 0 0; color:#526174; font-size:13px; line-height:1.65; }
@media (max-width: 900px) {
  .info-grid, .peer-card { grid-template-columns:1fr; }
}
</style>
"""


@st.cache_data(ttl=30)
def _load_households():
    conn = get_conn()
    df = pd.read_sql(
        "SELECT h.hhid, h.hname, h.coun, h.vcode, v.counname, v.vname "
        "FROM raw_households h "
        "LEFT JOIN raw_villages v ON h.vcode=v.vcode AND h.coun=v.coun",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=30)
def _load_household_data(hhid: str, months: list):
    conn = get_conn()
    household = pd.read_sql(
        "SELECT h.*, v.counname, v.townname, v.vname, r.haddr, r.intcode "
        "FROM raw_households h "
        "LEFT JOIN raw_villages v ON h.vcode=v.vcode AND h.coun=v.coun "
        "LEFT JOIN raw_houses r ON h.hcode=r.hcode "
        "WHERE h.hhid=? LIMIT 1",
        conn, params=(hhid,),
    )
    members = pd.read_sql("SELECT * FROM raw_members WHERE sid=? ORDER BY coln", conn, params=(hhid,))
    metrics_row = pd.read_sql("SELECT * FROM household_metrics WHERE hhid=?", conn, params=(hhid,))
    labels_row = pd.read_sql("SELECT * FROM household_labels WHERE hhid=?", conn, params=(hhid,))
    audit_rows = pd.read_sql(
        "SELECT * FROM audit_results WHERE hhid=? "
        "ORDER BY CASE rule_priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END",
        conn, params=(hhid,),
    )
    notes = pd.read_sql("SELECT * FROM notes WHERE hhid=? ORDER BY created_at DESC", conn, params=(hhid,))
    all_metrics = pd.read_sql("SELECT * FROM household_metrics", conn)
    all_labels = pd.read_sql("SELECT * FROM household_labels", conn)
    if months:
        where_clause, where_params = months_sql_filter(months)
        ledger = pd.read_sql(
            f"SELECT * FROM raw_ledger WHERE sid=? AND {where_clause}",
            conn,
            params=[hhid] + where_params,
        )
    else:
        ledger = pd.DataFrame()
    conn.close()
    return household, members, metrics_row, labels_row, audit_rows, notes, all_metrics, all_labels, ledger


def render(months: list):
    st.markdown(_css(), unsafe_allow_html=True)
    period = period_display(months)
    st.markdown(
        f'<div class="page-header"><h2>住户详情</h2><p>{period}</p></div>',
        unsafe_allow_html=True,
    )

    households = _load_households()
    if households.empty:
        st.info("暂无数据，请先导入并计算。")
        return

    households["counname"] = households["counname"].apply(norm_counname).fillna("（未知县区）")
    households["vname"] = households["vname"].fillna("（未知调查点）")

    selected_hhid = st.session_state.get("selected_hhid")
    if selected_hhid in set(households["hhid"]):
        selected = households[households["hhid"] == selected_hhid].iloc[0]
        default_coun = selected["counname"]
        default_vname = selected["vname"]
    else:
        default_coun = households.iloc[0]["counname"]
        default_vname = households[households["counname"] == default_coun].iloc[0]["vname"]

    col1, col2, col3 = st.columns(3)
    coun_list = sorted(households["counname"].unique().tolist())
    sel_coun = col1.selectbox("县区", coun_list, index=coun_list.index(default_coun))

    hh_coun = households[households["counname"] == sel_coun]
    vname_list = sorted(hh_coun["vname"].unique().tolist())
    v_index = vname_list.index(default_vname) if default_vname in vname_list else 0
    sel_vname = col2.selectbox("调查点", vname_list, index=v_index)

    hh_vname = hh_coun[hh_coun["vname"] == sel_vname].reset_index(drop=True)
    if selected_hhid in set(hh_vname["hhid"]):
        default_hh_idx = int(hh_vname.index[hh_vname["hhid"] == selected_hhid][0])
    else:
        default_hh_idx = 0
    sel_hh_idx = col3.selectbox(
        "记账户",
        range(len(hh_vname)),
        index=default_hh_idx,
        format_func=lambda i: hh_vname.iloc[i]["hname"],
    )
    selected_hhid = hh_vname.iloc[sel_hh_idx]["hhid"]
    st.session_state["selected_hhid"] = selected_hhid

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    _render_household(selected_hhid, months)


def _render_household(hhid: str, months: list):
    ref_year = months[-1][0] if months else 2026
    household, members, metrics_row, labels_row, audit_rows, notes, all_metrics, all_labels, ledger = _load_household_data(hhid, months)

    if household.empty:
        st.warning("未找到该住户。")
        return

    household["counname"] = household["counname"].apply(norm_counname)
    hh = household.iloc[0].to_dict()
    m = metrics_row.iloc[0].to_dict() if not metrics_row.empty else {}
    lb = labels_row.iloc[0].to_dict() if not labels_row.empty else {}

    qkey = str(lb.get("label_quality", "A") or "A")
    coaching = COACHING_LABEL.get(qkey, "常规辅导")
    acnttype_label = _acnttype_label(hh.get("acnttype"))
    location = " / ".join(str(p) for p in [hh.get("counname"), hh.get("townname"), hh.get("vname")] if p)
    address = hh.get("haddr") or ""
    summary = lb.get("portrait_summary") or "画像摘要待生成，请重新运行计算流水线。"

    st.markdown(
        dedent(f"""
        <div class="portrait-detail">
          <section class="detail-hero">
            <h1>{escape(str(hh.get('hname', '')))}</h1>
            <div class="addr">{escape(location)}{f' · {escape(str(address))}' if address else ''}<br>{escape(hhid)}</div>
            <div class="portrait-summary">{escape(str(summary))}</div>
          </section>
          <div class="tag-cloud">
            <span>{escape(str(lb.get('label_income', '-')))}</span>
            <span>{escape(str(lb.get('label_lifecycle', '-')))}</span>
            <span>{escape(str(lb.get('label_mobility', '-')))}</span>
            <span>{escape(acnttype_label)}</span>
            <span class="{COACHING_TONE.get(qkey, 'normal')}">{escape(coaching)}</span>
          </div>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )

    _section("家庭情况", "调查员辅导前优先掌握")
    _render_family(members, hh, ref_year, acnttype_label)

    _section("本期收支", "按收入来源和八大消费类别查看")
    _render_income_consume(m, all_metrics, all_labels, lb)

    _section("同类对比", "同收入结构 + 同家庭生命周期")
    _render_peer_compare(hhid, m, lb, all_metrics, all_labels)

    if len(months) > 1:
        _section("月度趋势", "收入与消费走势")
        _render_monthly_trend(ledger)

    _section("本期辅导建议", "由规则结果翻译为辅导语言")
    _render_coaching_suggestions(audit_rows)

    _section("访户记录")
    _render_visit_actions(hhid, hh, months, notes)


def _render_family(members, hh, ref_year, acnttype_label):
    if not members.empty:
        rows = []
        for _, r in members.iterrows():
            rows.append({
                "姓名": _mask_name(r.get("a101_name", "")),
                "关系": RELATION_MAP.get(str(r.get("a103_relation", "")), ""),
                "性别": GENDER_MAP.get(str(r.get("a104_gender", "")), ""),
                "年龄": _age(r.get("a105_birth", ""), ref_year),
                "学历": EDU_MAP.get(str(r.get("a113_edu", "")), ""),
                "就业": EMPLOYED_MAP.get(str(r.get("a204_employed", "")), ""),
                "常住状态": PERM_MAP.get(str(r.get("a119_permanent", "")), ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(300, 38 + len(rows) * 35))

    st.markdown(
        dedent(f"""
        <div class="portrait-detail">
          <div class="info-grid">
            <div class="info-tile"><b>{escape(str(hh.get('haddr') or '未填地址'))}</b><span>居住地址</span></div>
            <div class="info-tile"><b>{escape(str(URBAN_RURAL_MAP.get(hh.get('urban_rural'), hh.get('urban_rural') or '未填')))}</b><span>城乡属性</span></div>
            <div class="info-tile"><b>{escape(acnttype_label)}</b><span>记账方式</span></div>
            <div class="info-tile"><b>{escape(str(hh.get('opendate') or '未填'))[:10]}</b><span>开户时间</span></div>
          </div>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )


def _render_income_consume(m, all_metrics, all_labels, lb):
    income_total = float(m.get("income_total", 0) or 0)
    consume_total = float(m.get("consume_total", 0) or 0)
    income_items = [
        ("工资性收入", m.get("income_wage", 0) or 0),
        ("经营总收入", m.get("income_business_gross", 0) or 0),
        ("经营成本", m.get("income_business_cost", 0) or 0),
        ("财产净收入", m.get("income_property", 0) or 0),
        ("转移净收入", m.get("income_transfer", 0) or 0),
    ]
    consume_items = [
        ("食品烟酒", m.get("consume_food", 0) or 0),
        ("衣着", m.get("consume_clothing", 0) or 0),
        ("居住", m.get("consume_housing", 0) or 0),
        ("生活用品及服务", m.get("consume_daily", 0) or 0),
        ("交通通信", m.get("consume_transport", 0) or 0),
        ("教育文化娱乐", m.get("consume_edu", 0) or 0),
        ("医疗保健", m.get("consume_medical", 0) or 0),
        ("其他用品及服务", m.get("consume_other", 0) or 0),
    ]

    c1, c2 = st.columns([1, 1.25])
    with c1:
        st.markdown("**收入结构**")
        income_df = pd.DataFrame({
            "项目": [x[0] for x in income_items],
            "金额": [_money(x[1]) for x in income_items],
            "占比": [f"{float(x[1] or 0) / income_total * 100:.1f}%" if income_total > 0 else "0.0%" for x in income_items],
        })
        st.dataframe(income_df, use_container_width=True, hide_index=True, height=230)

        consume_rate = consume_total / income_total * 100 if income_total > 0 else 0
        peer = all_labels.merge(all_metrics, on="hhid", how="left")
        same = peer[
            (peer["label_income"] == lb.get("label_income")) &
            (peer["label_lifecycle"] == lb.get("label_lifecycle"))
        ].copy()
        if len(same) >= 5:
            same["consume_rate"] = same.apply(
                lambda r: float(r.get("consume_total") or 0) / float(r.get("income_total") or 1)
                if float(r.get("income_total") or 0) > 0 else 0,
                axis=1,
            )
            peer_rate = same["consume_rate"].mean() * 100
            compare = f"同类均值 {peer_rate:.1f}%"
        else:
            compare = "同类样本不足"
        st.metric("消费率（消费/收入）", f"{consume_rate:.1f}%", compare)

    with c2:
        st.markdown("**消费结构**")
        consume_df = pd.DataFrame({
            "类别": [x[0] for x in consume_items],
            "金额": [float(x[1] or 0) for x in consume_items],
        })
        consume_df["占比"] = consume_df["金额"].apply(
            lambda v: f"{v / consume_total * 100:.1f}%" if consume_total > 0 else "0.0%"
        )
        chart_col, table_col = st.columns([1, 1])
        with chart_col:
            nonzero = consume_df[consume_df["金额"] > 0]
            if nonzero.empty:
                st.caption("本期无消费记录。")
            else:
                fig = go.Figure(go.Pie(
                    labels=nonzero["类别"],
                    values=nonzero["金额"],
                    hole=0.56,
                    marker=dict(line=dict(color="#FFFFFF", width=3)),
                    textinfo="percent",
                ))
                fig.update_layout(
                    template="none",
                    height=260,
                    margin=dict(l=0, r=0, t=8, b=8),
                    showlegend=False,
                    font=dict(family="Microsoft YaHei", size=11),
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with table_col:
            show_df = consume_df.copy()
            show_df["金额"] = show_df["金额"].apply(_money)
            st.dataframe(show_df, use_container_width=True, hide_index=True, height=260)


def _percentile(series, value):
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty or pd.isna(value):
        return None
    return int(round((clean <= value).mean() * 100))


def _render_peer_compare(hhid, m, lb, all_metrics, all_labels):
    peer = all_labels.merge(all_metrics, on="hhid", how="left")
    same = peer[
        (peer["label_income"] == lb.get("label_income")) &
        (peer["label_lifecycle"] == lb.get("label_lifecycle"))
    ].copy()
    if len(same) < 5:
        st.caption("同类样本不足，暂不展示分位数对比。")
        return

    same["savings_rate"] = same.apply(
        lambda r: (float(r.get("income_total") or 0) - float(r.get("consume_total") or 0)) / float(r.get("income_total") or 1)
        if float(r.get("income_total") or 0) > 0 else 0,
        axis=1,
    )
    income = float(m.get("income_total", 0) or 0)
    consume = float(m.get("consume_total", 0) or 0)
    savings = (income - consume) / income if income > 0 else 0
    income_pct = _percentile(same["income_total"], income)
    consume_pct = _percentile(same["consume_total"], consume)
    savings_pct = _percentile(same["savings_rate"], savings)

    st.markdown(
        dedent(f"""
        <div class="portrait-detail">
          <div class="peer-card">
            <div class="peer-note">
              <b>在同类家庭中</b><br>
              同收入结构 + 同家庭生命周期，共 {len(same)} 户。
            </div>
            <div class="peer-metric"><b>P{income_pct}</b><span>收入水平</span></div>
            <div class="peer-metric"><b>P{consume_pct}</b><span>消费水平</span></div>
            <div class="peer-metric"><b>P{savings_pct}</b><span>储蓄率</span></div>
          </div>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )


def _render_monthly_trend(ledger: pd.DataFrame):
    if ledger.empty:
        st.caption("暂无月度账页记录。")
        return
    ledger = ledger.copy()
    ledger["code"] = ledger["code"].fillna("").astype(str)
    ledger["amount"] = pd.to_numeric(ledger["amount"], errors="coerce").fillna(0)
    rows = []
    for (year, month), grp in ledger.groupby(["year", "month"]):
        code = grp["code"]
        amount = grp["amount"]
        income = float(amount[code.str.startswith(("21", "12", "22", "23", "24"))].sum())
        consume = float(amount[code.str.startswith("3")].sum())
        rows.append({"月份": f"{int(year)}-{int(month):02d}", "收入": income, "消费": consume})
    trend = pd.DataFrame(rows).sort_values("月份")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=trend["月份"], y=trend["收入"], mode="lines+markers", name="收入"))
    fig.add_trace(go.Scatter(x=trend["月份"], y=trend["消费"], mode="lines+markers", name="消费"))
    fig.update_layout(
        template="none",
        height=300,
        margin=dict(l=40, r=20, t=20, b=40),
        hovermode="x unified",
        font=dict(family="Microsoft YaHei", size=12),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_coaching_suggestions(audit_rows: pd.DataFrame):
    if audit_rows.empty:
        st.markdown(
            '<div style="background:#ECFDF5;border:1px solid #A7F3D0;border-radius:10px;'
            'padding:16px 20px;color:#059669;font-weight:600">本期记录总体平稳，按常规节奏辅导即可。</div>',
            unsafe_allow_html=True,
        )
        return
    for _, ar in audit_rows.iterrows():
        rid = ar.get("rule_id", "")
        pri = ar.get("rule_priority", "medium")
        text = RULE_COACHING.get(rid) or ar.get("advice_text", "")
        st.markdown(
            f'<div class="portrait-detail"><div class="suggestion {escape(str(pri))}">'
            f'<b>{escape(str(rid))} · 辅导提示</b>'
            f'<p>{escape(str(text))}</p>'
            f'</div></div>',
            unsafe_allow_html=True,
        )


def _render_visit_actions(hhid, hh, months, notes):
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("生成访户核对单", type="primary", use_container_width=True):
            try:
                path = render_visit_card(hhid, months)
                with open(path, encoding="utf-8") as f:
                    html_content = f.read()
                st.components.v1.html(html_content, height=900, scrolling=True)
                period_str = f"{months[0][0]}_{months[0][1]:02d}" if months else "unknown"
                st.download_button(
                    "下载 HTML",
                    data=html_content.encode("utf-8"),
                    file_name=f"{hh.get('hname', hhid)}_{period_str}.html",
                    mime="text/html",
                )
            except Exception as e:
                st.error(f"生成失败: {e}")
    with c2:
        add = st.button("添加访户记录", use_container_width=True)
    with c3:
        show_history = st.button("历史记录", use_container_width=True)

    if add:
        st.session_state["show_note_editor"] = True
    if show_history:
        st.session_state["show_note_history"] = True

    if st.session_state.get("show_note_editor"):
        note = st.text_area("记录内容", height=100, placeholder="填写本次访户情况、辅导重点或需补录事项")
        if st.button("保存访户记录"):
            if note.strip():
                conn = get_conn()
                with conn:
                    conn.execute(
                        "INSERT INTO notes (hhid, note_text, created_by) VALUES (?, ?, ?)",
                        (hhid, note.strip(), "调查员"),
                    )
                conn.close()
                st.cache_data.clear()
                st.success("已保存访户记录")
                st.session_state["show_note_editor"] = False
                st.rerun()
            else:
                st.warning("请先填写记录内容。")

    if st.session_state.get("show_note_history"):
        if notes.empty:
            st.caption("暂无历史访户记录。")
        else:
            st.dataframe(
                notes[["created_at", "created_by", "note_text"]].rename(
                    columns={"created_at": "时间", "created_by": "记录人", "note_text": "内容"}
                ),
                use_container_width=True,
                hide_index=True,
            )
