"""
辅导清单页
"""
import io
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from ..io.database import get_conn
from ..report.renderer import render_visit_card
from ._utils import norm_counname, period_display

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "visit_cards"

RULES_INFO = {
    "R01": {
        "name": "月末集中补记",
        "desc": "某月超过一半的记录是在 21 日之后录入的，说明住户可能在月底才统一补记，而非每天记账。",
        "tip":  "提醒住户养成每日记账习惯，或询问是否有漏记情况。",
        "group": "记账习惯", "priority": "medium",
    },
    "R02": {
        "name": "连续 5 天没有消费记录",
        "desc": "在所选区间内，连续 5 天都没有任何消费类记录，正常家庭几乎每天都有食品等基本消费。",
        "tip":  "核实这几天是否真的没有消费，还是漏记了。",
        "group": "记账习惯", "priority": "medium",
    },
    "R03": {
        "name": "连续 10 天没有消费记录",
        "desc": "连续 10 天没有消费记录，时间较长，漏记可能性较大。",
        "tip":  "重点入户辅导，必要时请住户补充记录。",
        "group": "记账习惯", "priority": "high",
    },
    "R04": {
        "name": "整期没有食品支出",
        "desc": "整个分析区间没有任何食品烟酒类（编码 31xx）的记录，任何家庭都不可能这么长时间没有餐饮食品支出。",
        "tip":  "可能存在较多漏记，需重点入户辅导。",
        "group": "记账习惯", "priority": "high",
    },
    "R07": {
        "name": "消费金额明显偏低",
        "desc": "本期消费总额不足收入总额的 30%，消费率异常低，可能存在漏记消费。",
        "tip":  "询问是否有大额支出未记录，如租房、购物等。",
        "group": "记账习惯", "priority": "medium",
    },
    "R10": {
        "name": "整月没有记录",
        "desc": "区间内某整个月账页记录数为零，正常家庭不会整月没有任何收支。",
        "tip":  "核实该月是否确无收支，或是否整月漏记。",
        "group": "记账习惯", "priority": "high",
    },
    "L01": {
        "name": "有学龄孩子但教育支出极少",
        "desc": "家中有 3-17 岁成员，但本期教育类支出不足 500 元，学习用品、培训、学费等均未体现。",
        "tip":  "询问孩子上学相关费用是否有记录，如学杂费、补习费等。",
        "group": "逻辑核查", "priority": "high",
    },
    "L04": {
        "name": "有离退休人员但养老金记录偏少",
        "desc": "家中有离退休成员，但转移性收入（养老金等）偏低，低于预期水平。",
        "tip":  "核实养老金、退休工资是否按实际金额记录。",
        "group": "逻辑核查", "priority": "high",
    },
    "L05": {
        "name": "没有在职成员但有工资收入",
        "desc": "问卷显示家中没有在业人员，但账页有工资性收入记录，两者矛盾。",
        "tip":  "核实就业情况填写是否有误，或收入编码是否记错。",
        "group": "逻辑核查", "priority": "medium",
    },
    "L08": {
        "name": "收入和支出相差悬殊",
        "desc": "收入总额与（消费支出 + 非消费支出）的差距超过收入的 50%，说明可能有重大收支未被记录。",
        "tip":  "检查是否有大额收入或支出遗漏。",
        "group": "逻辑核查", "priority": "medium",
    },
    "L09": {
        "name": "人均日食品支出过低",
        "desc": "常住人口有 2 人及以上，但人均每天食品消费不足 10 元，低于基本生活水平。",
        "tip":  "询问日常买菜、外出用餐等是否有记录。",
        "group": "逻辑核查", "priority": "medium",
    },
    "N01": {
        "name": "有单笔异常大额记录",
        "desc": "存在单笔金额超过 5000 元、且超过期内收入 10% 的记录，可能是误录或单位填错。",
        "tip":  "核实该笔记录的金额和类型是否正确。",
        "group": "数据异常", "priority": "medium",
    },
    "N02": {
        "name": "某类消费占比过高",
        "desc": "某一类消费占消费总额超过 70%，比例过于集中，其他类别可能有漏记。",
        "tip":  "询问其他消费类别（如医疗、交通等）是否有遗漏。",
        "group": "数据异常", "priority": "medium",
    },
    "Q01": {
        "name": "大额记录缺少品名",
        "desc": "有 3 条及以上金额超过 200 元的记录没有填写具体品名，影响数据审核。",
        "tip":  "提醒住户补充这些记录的具体商品或服务名称。",
        "group": "录入质量", "priority": "low",
    },
}

PRI_COLOR = {"high":"#EF4444","medium":"#F59E0B","low":"#10B981"}
PRI_BG    = {"high":"#FEF2F2","medium":"#FFFBEB","low":"#ECFDF5"}
PRI_BORDER= {"high":"#FECACA","medium":"#FDE68A","low":"#A7F3D0"}
PRI_ZH    = {"high":"重要","medium":"一般","low":"提示"}

QUALITY_COLOR_MAP = {"A":"#10B981","B":"#3B82F6","C":"#F59E0B","D":"#EF4444"}


@st.cache_data(ttl=30)
def _load_audit_data():
    conn = get_conn()
    audit_df = pd.read_sql(
        "SELECT ar.*, h.hname, h.coun, v.counname, s.visit_priority_score "
        "FROM audit_results ar "
        "LEFT JOIN raw_households h ON ar.hhid=h.hhid "
        "LEFT JOIN raw_villages v ON h.vcode=v.vcode AND h.coun=v.coun "
        "LEFT JOIN current_snapshot s ON ar.hhid=s.hhid",
        conn,
    )
    labels_df = pd.read_sql(
        "SELECT hhid, label_quality, quality_score FROM household_labels", conn
    )
    snap_df = pd.read_sql("SELECT hhid, visit_priority_score FROM current_snapshot", conn)
    conn.close()
    return audit_df, labels_df, snap_df


@st.cache_data(ttl=30)
def _load_households_for_audit():
    conn = get_conn()
    households = pd.read_sql(
        "SELECT h.hhid, h.hname, h.coun, v.counname, v.vname "
        "FROM raw_households h "
        "LEFT JOIN raw_villages v ON h.vcode=v.vcode AND h.coun=v.coun",
        conn,
    )
    conn.close()
    return households


def render(months: list, filters: dict):
    period = period_display(months)
    st.markdown(
        f'<div class="page-header">'
        f'<h2>辅导清单</h2>'
        f'<p>{period}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    audit_df, labels_df, snap_df = _load_audit_data()

    if audit_df.empty:
        st.info("暂无辅导提示数据，请先在【导入数据】中运行计算流水线。")
        return

    audit_df["counname"] = audit_df["counname"].apply(norm_counname)

    if filters.get("coun_list"):
        audit_df = audit_df[audit_df["coun"].isin(filters["coun_list"])]
    if filters.get("quality_levels"):
        valid = labels_df[labels_df["label_quality"].isin(filters["quality_levels"])]["hhid"]
        audit_df = audit_df[audit_df["hhid"].isin(valid)]

    tab1, tab2, tab3 = st.tabs(["辅导优先户", "按辅导提示查看", "辅导提示说明"])

    with tab1:
        _render_priority(snap_df, labels_df, audit_df, months)
    with tab2:
        _render_by_rule(audit_df)
    with tab3:
        _render_rule_manual()


def _render_priority(snap_df, labels_df, audit_df, months: list):
    households = _load_households_for_audit().copy()
    households["counname"] = households["counname"].apply(norm_counname)

    merged = (
        snap_df
        .merge(labels_df, on="hhid", how="left")
        .merge(households, on="hhid", how="left")
    )
    merged = merged.sort_values("visit_priority_score", ascending=False, na_position="last").reset_index(drop=True)

    priority_order = {"high": 0, "medium": 1, "low": 2}
    rows_summary = []
    for hhid_s, grp in audit_df.groupby("hhid"):
        sorted_rules = grp.sort_values(
            "rule_priority", key=lambda s: s.map(priority_order)
        )["rule_id"].tolist()
        n_high = int((grp["rule_priority"] == "high").sum())
        names = "、".join(RULES_INFO.get(r, {}).get("name", r) for r in sorted_rules)
        rows_summary.append({"hhid": hhid_s, "辅导提示摘要": names, "_n_high": n_high})
    rule_summary = pd.DataFrame(rows_summary) if rows_summary else pd.DataFrame(
        columns=["hhid", "辅导提示摘要", "_n_high"])

    merged = merged.merge(rule_summary, on="hhid", how="left")
    merged["_n_high"] = merged["_n_high"].fillna(0).astype(int)

    n     = len(merged)
    top_n = max(1, int(n * 0.2))

    n_urgent  = int((merged.index < top_n).sum())
    n_has_tip = int(merged["辅导提示摘要"].notna().sum())
    n_routine = n - n_has_tip

    c1, c2, c3 = st.columns(3)
    stats = [
        (c1, n_urgent,  "建议优先入户", "#EF4444", "#FEF2F2", "#FECACA"),
        (c2, n_has_tip, "有辅导提示", "#F59E0B", "#FFFBEB", "#FDE68A"),
        (c3, n_routine, "常规辅导", "#10B981", "#ECFDF5", "#A7F3D0"),
    ]
    for col, val, label, color, bg, border in stats:
        col.markdown(
            f'<div style="background:#FFFFFF;border:1px solid {border};'
            f'border-radius:12px;padding:18px 22px;'
            f'box-shadow:0 1px 3px rgba(15,23,42,.03)">'
            f'<div style="font-size:30px;font-weight:700;color:{color};'
            f'letter-spacing:-0.02em;line-height:1">{val}</div>'
            f'<div style="font-size:13px;color:#64748B;margin-top:6px;font-weight:500">{label}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    fc1, fc2, fc3 = st.columns([2, 2, 2])
    coun_opts = ["全部"] + sorted(merged["counname"].dropna().unique().tolist())
    sel_coun  = fc1.selectbox("县区", coun_opts, label_visibility="visible")
    qual_opts = fc2.multiselect("辅导关注度", ["A","B","C","D"],
                                default=["A","B","C","D"], label_visibility="visible")
    show_opts = fc3.radio("显示范围", ["仅优先入户（前20%）","全部有提示","全部"],
                          label_visibility="visible")

    view = merged.copy()
    if sel_coun != "全部":
        view = view[view["counname"] == sel_coun]
    if qual_opts:
        view = view[view["label_quality"].isin(qual_opts)]
    if show_opts == "仅优先入户（前20%）":
        view = view[view.index < top_n]
    elif show_opts == "全部有提示":
        view = view[view["辅导提示摘要"].notna()]

    view = view.reset_index(drop=True)

    display = pd.DataFrame({
        "排名":   view.index + 1,
        "户主":   view["hname"].fillna(""),
        "县区":   view["counname"].fillna(""),
        "调查点": view["vname"].fillna(""),
        "关注度": view["label_quality"].map({"A": "常规", "B": "常规", "C": "关注", "D": "重点"}).fillna("常规"),
        "质量分": view["quality_score"].apply(
            lambda x: int(round(float(x))) if pd.notna(x) and x != "" else ""),
        "辅导提示": view["辅导提示摘要"].fillna("无"),
    })

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=min(40 + len(display) * 35, 520),
        column_config={
            "排名":   st.column_config.NumberColumn(width="small"),
            "质量分": st.column_config.NumberColumn(width="small"),
            "关注度": st.column_config.TextColumn(width="small"),
            "辅导提示": st.column_config.TextColumn(width="large"),
        },
    )
    st.caption(f"共 {len(view)} 户")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    hhid_options = view["hhid"].tolist() if "hhid" in view.columns else merged["hhid"].tolist()
    name_map = dict(zip(view["hhid"], view["hname"])) if "hhid" in view.columns else {}
    selected = st.multiselect(
        "选择住户生成访户核对单",
        hhid_options,
        default=view["hhid"].head(5).tolist() if "hhid" in view.columns else [],
        format_func=lambda h: f"{name_map.get(h, h)}（{h}）",
    )

    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button("批量生成", type="primary") and selected:
            bar = st.progress(0)
            done = []
            for i, hhid in enumerate(selected):
                try:
                    render_visit_card(hhid, months)
                    done.append(hhid)
                except Exception:
                    pass
                bar.progress((i + 1) / len(selected))
            st.success(f"已生成 {len(done)} 份，保存在 output/visit_cards/")

    with btn_col2:
        if st.button("打包下载 ZIP") and selected:
            zipped = io.BytesIO()
            with zipfile.ZipFile(zipped, "w") as zf:
                for hhid in selected:
                    try:
                        p = render_visit_card(hhid, months)
                        if Path(p).exists():
                            zf.write(p, arcname=Path(p).name)
                    except Exception:
                        continue
            period_str = f"{months[0][0]}_{months[0][1]:02d}" if months else "unknown"
            st.download_button(
                "下载 ZIP",
                data=zipped.getvalue(),
                file_name=f"visit_cards_{period_str}.zip",
                mime="application/zip",
            )


def _render_by_rule(audit_df):
    rule_stats = (
        audit_df.groupby(["rule_id","rule_priority"])
        .agg(户数=("hhid","nunique")).reset_index()
        .sort_values(["rule_priority","rule_id"],
                     key=lambda s: s.map({"high":0,"medium":1,"low":2})
                     if s.name == "rule_priority" else s)
    )

    GROUP_NAMES = {
        "记账习惯": "记账习惯类",
        "逻辑核查": "逻辑一致性类",
        "数据异常": "数据异常类",
        "录入质量": "录入质量类",
    }

    for g in ["记账习惯","逻辑核查","数据异常","录入质量"]:
        rules_in_g = [rid for rid, info in RULES_INFO.items()
                      if info["group"] == g and rid in rule_stats["rule_id"].values]
        if not rules_in_g:
            continue

        st.markdown(
            f'<div style="font-size:11px;font-weight:600;color:#94A3B8;'
            f'text-transform:uppercase;letter-spacing:0.06em;'
            f'margin:24px 0 10px;padding-bottom:8px;border-bottom:1px solid #E2E8F0">'
            f'{GROUP_NAMES.get(g,g)}</div>',
            unsafe_allow_html=True,
        )

        for rid in rules_in_g:
            info = RULES_INFO.get(rid, {})
            row  = rule_stats[rule_stats["rule_id"]==rid].iloc[0] \
                   if rid in rule_stats["rule_id"].values else None
            if row is None:
                continue
            count = int(row["户数"])
            pri   = row["rule_priority"]
            color = PRI_COLOR.get(pri,"#94A3B8")
            bg    = PRI_BG.get(pri, "#F8FAFC")
            border= PRI_BORDER.get(pri, "#E2E8F0")

            with st.expander(
                f"{info.get('name',rid)}  ·  {count} 户需要辅导"
            ):
                st.markdown(
                    f'<div style="background:#F8FAFC;border-radius:10px;padding:14px 18px;'
                    f'margin-bottom:12px;border:1px solid #E2E8F0">'
                    f'<div style="font-size:13px;color:#475569;line-height:1.7">'
                    f'<b style="color:#0F172A">什么情况：</b>{info.get("desc","")}</div>'
                    f'<div style="font-size:13px;color:#475569;margin-top:8px;line-height:1.7">'
                    f'<b style="color:#0F172A">建议处理：</b>{info.get("tip","")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                hhids_triggered = audit_df[audit_df["rule_id"]==rid][
                    ["hhid","hname","counname","visit_priority_score","advice_text"]
                ].drop_duplicates("hhid").copy()
                hhids_triggered["visit_priority_score"] = hhids_triggered["visit_priority_score"].apply(
                    lambda x: round(float(x),3) if pd.notna(x) else ""
                )
                hhids_triggered.columns = ["HHID","户主姓名","县区","优先级","系统建议"]
                st.dataframe(hhids_triggered, use_container_width=True, hide_index=True)


def _render_rule_manual():
    st.markdown(
        '<div style="color:#64748B;font-size:14px;margin-bottom:16px">'
        '系统共设置了以下辅导提示，帮助调查员识别需要重点沟通的记账情形。</div>',
        unsafe_allow_html=True,
    )

    GROUP_NAMES = {
        "记账习惯": ("记账习惯", "检查住户的记录频率和完整性"),
        "逻辑核查": ("逻辑一致性", "对照问卷信息检查账页记录的合理性"),
        "数据异常": ("数据异常", "识别金额或结构上的异常情况"),
        "录入质量": ("录入质量", "检查记录信息是否填写完整"),
    }

    for group, (title, subtitle) in GROUP_NAMES.items():
        st.markdown(
            f'<div style="display:flex;align-items:baseline;gap:10px;'
            f'margin:28px 0 12px;padding-bottom:8px;border-bottom:1px solid #E2E8F0">'
            f'<span style="font-size:14px;font-weight:600;color:#0F172A">{title}</span>'
            f'<span style="font-size:12px;color:#94A3B8">{subtitle}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        rules = {rid: info for rid, info in RULES_INFO.items() if info["group"] == group}

        for rid, info in rules.items():
            pri   = info["priority"]
            color = PRI_COLOR.get(pri,"#94A3B8")
            bg    = PRI_BG.get(pri, "#F8FAFC")
            border= PRI_BORDER.get(pri, "#E2E8F0")
            priZH = PRI_ZH.get(pri,"")
            st.markdown(
                f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;'
                f'border-radius:12px;padding:16px 20px;margin-bottom:10px;'
                f'box-shadow:0 1px 3px rgba(15,23,42,.03)">'
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
                f'<span style="font-size:14px;font-weight:600;color:#0F172A">{info["name"]}</span>'
                f'<span style="padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;'
                f'background:{bg};color:{color};border:1px solid {border}">{priZH}</span>'
                f'<span style="font-size:11px;color:#CBD5E1;margin-left:auto">{rid}</span>'
                f'</div>'
                f'<div style="font-size:13px;color:#64748B;line-height:1.7">'
                f'<b style="color:#0F172A">检查逻辑：</b>{info["desc"]}</div>'
                f'<div style="font-size:13px;color:#64748B;margin-top:6px;line-height:1.7">'
                f'<b style="color:#0F172A">建议操作：</b>{info["tip"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
