"""
Render HTML visit card for a household using Jinja2.
"""
import json
from pathlib import Path
from typing import Optional

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from ..io.database import get_conn
from ..compute.metrics import months_sql_filter

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "visit_cards"

GENDER_MAP = {"1": "男", "2": "女"}
RELATION_MAP = {
    "1": "户主", "2": "配偶", "3": "子/女", "4": "父/母",
    "5": "孙子/女", "6": "其他亲属", "7": "其他",
}
EDU_MAP = {
    "1": "未上学", "2": "小学", "3": "初中", "4": "高中/中专",
    "5": "大专", "6": "本科", "7": "研究生及以上",
}
EMPLOYED_MAP = {"1": "在业", "2": "不在业"}
PERMANENT_MAP = {"1": "常住", "2": "非常住"}
WORK_AREA_MAP = {
    "1": "本乡镇", "2": "本县区", "3": "本市其他", "4": "本省其他", "5": "外省", "6": "境外",
}
INSURANCE_MAP = {"1": "参保", "2": "未参保"}
COACHING_LABEL = {"A": "常规辅导", "B": "常规辅导", "C": "关注辅导", "D": "重点辅导"}
ACNTTYPE_MAP = {"0": "纸质记账", "1": "电子记账", "2": "多人记账", 0: "纸质记账", 1: "电子记账", 2: "多人记账"}
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


def _make_period_label(months: list) -> str:
    if not months:
        return ""
    if len(months) == 1:
        y, m = months[0]
        return f"{y}年{m}月"
    sy, sm = months[0]
    ey, em = months[-1]
    return f"{sy}年{sm}月—{ey}年{em}月"


def _get_household_context(hhid: str, months: list) -> dict:
    conn = get_conn()
    ref_year = months[-1][0] if months else 2026

    household = pd.read_sql(
        "SELECT h.*, v.counname, v.townname, v.vname, r.haddr, r.intcode "
        "FROM raw_households h "
        "LEFT JOIN raw_villages v ON h.vcode=v.vcode AND h.coun=v.coun "
        "LEFT JOIN raw_houses r ON h.hcode=r.hcode "
        "WHERE h.hhid=? LIMIT 1",
        conn, params=(hhid,),
    )

    surveyb = pd.read_sql(
        "SELECT * FROM raw_surveyb WHERE sid=? LIMIT 1",
        conn, params=(hhid,),
    )

    members = pd.read_sql(
        "SELECT * FROM raw_members WHERE sid=? ORDER BY coln",
        conn, params=(hhid,),
    )

    metrics_row = pd.read_sql(
        "SELECT * FROM household_metrics WHERE hhid=?",
        conn, params=(hhid,),
    )

    labels_row = pd.read_sql(
        "SELECT * FROM household_labels WHERE hhid=?",
        conn, params=(hhid,),
    )

    audit_rows = pd.read_sql(
        "SELECT * FROM audit_results WHERE hhid=? "
        "ORDER BY CASE rule_priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END LIMIT 5",
        conn, params=(hhid,),
    )

    all_metrics = pd.read_sql("SELECT * FROM household_metrics", conn)
    all_labels = pd.read_sql("SELECT * FROM household_labels", conn)

    snap = pd.read_sql(
        "SELECT * FROM current_snapshot WHERE hhid=?", conn, params=(hhid,)
    )

    large_rows = _get_large_ledger(conn, hhid, months)

    notes = pd.read_sql(
        "SELECT * FROM notes WHERE hhid=? ORDER BY created_at DESC",
        conn, params=(hhid,),
    )
    conn.close()

    hh = household.iloc[0].to_dict() if not household.empty else {}
    m = metrics_row.iloc[0].to_dict() if not metrics_row.empty else {}
    lb = labels_row.iloc[0].to_dict() if not labels_row.empty else {}
    sn = snap.iloc[0].to_dict() if not snap.empty else {}
    sb = surveyb.iloc[0].to_dict() if not surveyb.empty else {}

    member_list = []
    for _, mem in members.iterrows():
        age = _calc_age(str(mem.get("a105_birth", "")), ref_year)
        member_list.append({
            "coln": mem.get("coln", ""),
            "name": mem.get("a101_name", ""),
            "relation": RELATION_MAP.get(str(mem.get("a103_relation", "")), ""),
            "gender": GENDER_MAP.get(str(mem.get("a104_gender", "")), ""),
            "age": age,
            "edu": EDU_MAP.get(str(mem.get("a113_edu", "")), ""),
            "employed": EMPLOYED_MAP.get(str(mem.get("a204_employed", "")), ""),
            "work_area": WORK_AREA_MAP.get(str(mem.get("a209_work_area", "")), ""),
            "permanent": PERMANENT_MAP.get(str(mem.get("a119_permanent", "")), ""),
            "medical": INSURANCE_MAP.get(str(mem.get("a111_medical", "")), "-"),
            "pension": INSURANCE_MAP.get(str(mem.get("a202_pension", "")), "-"),
        })

    audit_list = []
    for _, ar in audit_rows.iterrows():
        ctx = {}
        try:
            ctx = json.loads(ar.get("trigger_context", "{}") or "{}")
        except Exception:
            pass
        audit_list.append({
            "rule_id": ar.get("rule_id", ""),
            "rule_group": ar.get("rule_group", ""),
            "rule_priority": ar.get("rule_priority", ""),
            "advice_text": RULE_COACHING.get(ar.get("rule_id", ""), ar.get("advice_text", "")),
            "context": ctx,
        })

    income_total = float(m.get("income_total", 0) or 0)
    consume_total = float(m.get("consume_total", 0) or 0)

    income_items = [
        ("工资性收入", m.get("income_wage", 0) or 0),
        ("经营总收入", m.get("income_business_gross", 0) or 0),
        ("经营成本", m.get("income_business_cost", 0) or 0),
        ("财产净收入", m.get("income_property", 0) or 0),
        ("转移净收入", m.get("income_transfer", 0) or 0),
    ]
    for i, (name, val) in enumerate(income_items):
        pct = round(float(val) / income_total * 100, 1) if income_total > 0 else 0
        income_items[i] = (name, round(float(val), 2), pct)

    consume_cats = [
        ("食品烟酒", m.get("consume_food", 0) or 0),
        ("衣着", m.get("consume_clothing", 0) or 0),
        ("居住", m.get("consume_housing", 0) or 0),
        ("生活用品及服务", m.get("consume_daily", 0) or 0),
        ("交通通信", m.get("consume_transport", 0) or 0),
        ("教育文化娱乐", m.get("consume_edu", 0) or 0),
        ("医疗保健", m.get("consume_medical", 0) or 0),
        ("其他用品及服务", m.get("consume_other", 0) or 0),
    ]
    for i, (name, val) in enumerate(consume_cats):
        pct = round(float(val) / consume_total * 100, 1) if consume_total > 0 else 0
        consume_cats[i] = (name, round(float(val), 2), pct)

    consume_rate = round(consume_total / income_total * 100, 1) if income_total > 0 else 0
    peer_count, income_pct, consume_pct, savings_pct = _peer_compare(m, lb, all_metrics, all_labels)

    label_colors = {
        "工薪型": "#4e79a7", "经营型": "#f28e2b", "转移型": "#76b7b2",
        "混合型": "#59a14f", "无收入记录": "#bab0ac",
        "单人户": "#e15759", "幼儿家庭": "#af7aa1", "学龄家庭": "#ff9da7",
        "中青年核心家庭": "#9c755f", "老年家庭": "#bab0ac",
        "三代同堂": "#edc948", "夫妻户": "#b07aa1", "其他": "#bab0ac",
        "全家常住": "#59a14f", "半流动": "#f28e2b", "整户外出": "#e15759",
        "A": "#4caf50", "B": "#8bc34a", "C": "#ff9800", "D": "#f44336",
    }

    housing_area = sb.get("b105_housing_area")
    housing_value = sb.get("b118_housing_value")
    car_count = sb.get("b201_car")

    period_label = _make_period_label(months)
    rolling_consume = sn.get("rolling_consume", 0) or 0
    rolling_income = sn.get("rolling_income", 0) or 0

    return {
        "hhid": hhid,
        "period_label": period_label,
        "hname": hh.get("hname", ""),
        "phone": hh.get("phone", ""),
        "coun": hh.get("coun", ""),
        "counname": hh.get("counname", ""),
        "townname": hh.get("townname", ""),
        "vname": hh.get("vname", ""),
        "haddr": hh.get("haddr", ""),
        "urban_rural": hh.get("urban_rural", ""),
        "intcode": hh.get("intcode", ""),
        "acnttype": ACNTTYPE_MAP.get(hh.get("acnttype"), ACNTTYPE_MAP.get(str(hh.get("acnttype", "")), "未知")),
        "acnttype_label": ACNTTYPE_MAP.get(hh.get("acnttype"), ACNTTYPE_MAP.get(str(hh.get("acnttype", "")), "未知")),
        "opendate": str(hh.get("opendate", ""))[:10],
        "portrait_summary": lb.get("portrait_summary") or "画像摘要待生成",
        "coaching_level": COACHING_LABEL.get(lb.get("label_quality", ""), "常规辅导"),
        "peer_count": peer_count,
        "income_pct": income_pct,
        "consume_pct": consume_pct,
        "savings_pct": savings_pct,
        "member_list": member_list,
        "housing_area": f"{housing_area:.1f}" if housing_area else "",
        "housing_value": f"{housing_value:,.0f}" if housing_value else "",
        "car_count": int(car_count) if car_count else 0,
        "metrics": m,
        "labels": lb,
        "label_colors": label_colors,
        "income_total": income_total,
        "consume_total": consume_total,
        "consume_rate": consume_rate,
        "income_items": income_items,
        "consume_cats": consume_cats,
        "rolling_consume": rolling_consume,
        "rolling_income": rolling_income,
        "audit_list": audit_list,
        "large_ledger": large_rows,
        "notes": notes.to_dict("records"),
        "visit_priority_score": sn.get("visit_priority_score", ""),
    }


def _get_large_ledger(conn, hhid: str, months: list) -> list:
    if not months:
        return []

    snap = pd.read_sql(
        "SELECT rolling_income FROM current_snapshot WHERE hhid=?", conn, params=(hhid,)
    )
    income_ref = float(snap.iloc[0]["rolling_income"]) if not snap.empty else 0

    floor = max(1000, income_ref * 0.01)
    where_clause, where_params = months_sql_filter(months)

    ledger = pd.read_sql(
        f"SELECT * FROM raw_ledger WHERE sid=? AND amount>? AND {where_clause} "
        "ORDER BY record_date DESC LIMIT 30",
        conn, params=[hhid, floor] + where_params,
    )

    result = []
    for _, row in ledger.iterrows():
        result.append({
            "record_date": row.get("record_date", ""),
            "amount": row.get("amount", ""),
            "item_name": row.get("item_name", ""),
            "code": row.get("code", ""),
            "person_code": row.get("person_code", ""),
        })
    return result


def _percentile(series, value):
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty or pd.isna(value):
        return None
    return int(round((clean <= value).mean() * 100))


def _peer_compare(metrics: dict, labels: dict, all_metrics: pd.DataFrame, all_labels: pd.DataFrame):
    if all_metrics.empty or all_labels.empty:
        return 0, "-", "-", "-"
    peer = all_labels.merge(all_metrics, on="hhid", how="left")
    same = peer[
        (peer["label_income"] == labels.get("label_income")) &
        (peer["label_lifecycle"] == labels.get("label_lifecycle"))
    ].copy()
    if len(same) < 5:
        return len(same), "-", "-", "-"
    same["savings_rate"] = same.apply(
        lambda r: (float(r.get("income_total") or 0) - float(r.get("consume_total") or 0)) / float(r.get("income_total") or 1)
        if float(r.get("income_total") or 0) > 0 else 0,
        axis=1,
    )
    income = float(metrics.get("income_total", 0) or 0)
    consume = float(metrics.get("consume_total", 0) or 0)
    savings = (income - consume) / income if income > 0 else 0
    return (
        len(same),
        _percentile(same["income_total"], income),
        _percentile(same["consume_total"], consume),
        _percentile(same["savings_rate"], savings),
    )


def _calc_age(birth_yyyymm: str, ref_year: int) -> Optional[int]:
    if not birth_yyyymm or len(birth_yyyymm) < 4:
        return None
    try:
        return ref_year - int(birth_yyyymm[:4])
    except (ValueError, TypeError):
        return None


def render_visit_card(hhid: str, months: list) -> str:
    ctx = _get_household_context(hhid, months)
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    tmpl = env.get_template("visit_card.html.j2")
    html = tmpl.render(**ctx)

    period_str = f"{months[0][0]}_{months[0][1]:02d}-{months[-1][0]}_{months[-1][1]:02d}" if months else "unknown"
    out_dir = OUTPUT_DIR / period_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{hhid}.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


def render_all_visit_cards(months: list, hhid_list: Optional[list] = None) -> list:
    conn = get_conn()
    if hhid_list is None:
        rows = pd.read_sql("SELECT DISTINCT hhid FROM household_metrics", conn)
        hhid_list = rows["hhid"].tolist()
    conn.close()

    paths = []
    for hhid in hhid_list:
        try:
            path = render_visit_card(hhid, months)
            paths.append(path)
        except Exception:
            pass
    return paths
