"""
Rule engine: reads audit_rules.yaml, evaluates each rule per household,
writes results to audit_results and updates visit_priority_score in current_snapshot.
"""
import calendar
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..io.database import get_conn
from .metrics import months_sql_filter, months_to_date_range, _period_label

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}


def _load_rules() -> list:
    with open(CONFIG_DIR / "audit_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_advice_templates() -> dict:
    with open(CONFIG_DIR / "advice_templates.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_thresholds() -> dict:
    with open(CONFIG_DIR / "thresholds.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _eval_condition(value: Any, op: str, threshold: Any) -> bool:
    if value is None:
        return False
    try:
        if op == "eq":
            return value == threshold
        elif op == "ne":
            return value != threshold
        elif op == "gt":
            return float(value) > float(threshold)
        elif op == "gte":
            return float(value) >= float(threshold)
        elif op == "lt":
            return float(value) < float(threshold)
        elif op == "lte":
            return float(value) <= float(threshold)
        elif op == "between":
            return float(threshold[0]) <= float(value) <= float(threshold[1])
        elif op == "in":
            return value in threshold
        elif op == "not_in":
            return value not in threshold
        elif op == "exists":
            return value is not None and str(value).strip() != ""
        elif op == "not_exists":
            return value is None or str(value).strip() == ""
    except (TypeError, ValueError):
        return False
    return False


def _eval_conditions(conditions: list, metrics: dict) -> bool:
    for cond in conditions:
        field = cond["field"]
        op = cond["op"]
        threshold = cond.get("value")
        val = metrics.get(field)
        if not _eval_condition(val, op, threshold):
            return False
    return True


def check_month_end_ratio(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    if ledger_grp.empty:
        return False, {}
    thr = thresholds["audit"]["R01_month_end_ratio"]
    months_triggered = []
    for month, mgrp in ledger_grp.groupby(pd.to_datetime(ledger_grp["create_time"], errors="coerce").dt.month):
        if len(mgrp) == 0:
            continue
        after = (pd.to_datetime(mgrp["create_time"], errors="coerce").dt.day >= 21).sum()
        ratio = after / len(mgrp)
        if ratio > thr:
            months_triggered.append(str(int(month)))

    if not months_triggered:
        return False, {}
    ratio_pct = round(
        (pd.to_datetime(ledger_grp["create_time"], errors="coerce").dt.day >= 21).sum()
        / len(ledger_grp) * 100, 1
    )
    return True, {"trigger_months": "、".join(months_triggered), "ratio_pct": ratio_pct}


def check_gap_days(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict, min_gap: int) -> tuple:
    if ledger_grp.empty or "code" not in ledger_grp.columns:
        return False, {}
    consume = ledger_grp[ledger_grp["code"].fillna("").astype(str).str.startswith("3")]
    if consume.empty:
        return True, {"gap_days": "整个区间", "gap_start": "", "gap_end": ""}

    dates = pd.to_datetime(consume["record_date"], errors="coerce").dropna().dt.date
    if dates.empty:
        return False, {}

    date_set = set(dates)
    months_list = metrics.get("_months_list", [])
    if not months_list:
        return False, {}

    overall_max = 0
    best_start = None
    best_end = None
    triggered_months = []

    data_end = metrics.get("_data_end_date")
    for year, month in months_list:
        _, last_day = calendar.monthrange(year, month)
        m_start = date(year, month, 1)
        m_end = date(year, month, last_day)
        if data_end and m_end > data_end:
            m_end = data_end
        cur = m_start
        current_gap = 0
        m_gap_start = None
        month_max = 0
        m_best_start = None
        m_best_end = None
        while cur <= m_end:
            if cur in date_set:
                if current_gap > month_max:
                    month_max = current_gap
                    m_best_start = m_gap_start
                    m_best_end = cur - timedelta(days=1)
                current_gap = 0
                m_gap_start = None
            else:
                if m_gap_start is None:
                    m_gap_start = cur
                current_gap += 1
            cur += timedelta(days=1)
        if current_gap > month_max:
            month_max = current_gap
            m_best_start = m_gap_start
            m_best_end = m_end

        if month_max >= min_gap:
            triggered_months.append(str(month))
        if month_max > overall_max:
            overall_max = month_max
            best_start = m_best_start
            best_end = m_best_end

    if overall_max >= min_gap:
        return True, {
            "gap_days": overall_max,
            "gap_start": str(best_start) if best_start else "",
            "gap_end": str(best_end) if best_start else "",
            "trigger_months": "、".join(triggered_months),
        }
    return False, {}


def check_month_missing(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    months_list = metrics.get("_months_list", [])
    month_nums = [m for _, m in months_list]
    if ledger_grp.empty or "month" not in ledger_grp.columns:
        return True, {"missing_months": "、".join(str(m) for m in month_nums)}
    present = set(ledger_grp["month"].dropna().astype(int).tolist())
    missing = [m for m in month_nums if m not in present]
    if missing:
        return True, {"missing_months": "、".join(str(m) for m in missing)}
    return False, {}


def check_child_edu(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    thr = thresholds["audit"]
    has_717 = metrics.get("has_child_7_17", 0) or 0
    has_06 = metrics.get("has_child_0_6", 0) or 0
    edu = metrics.get("consume_edu", 0) or 0
    if (has_717 or has_06) and edu < thr["L01_edu_threshold"]:
        min_a = metrics.get("min_age", "")
        max_a = metrics.get("max_age", "")
        return True, {
            "consume_edu": round(edu, 2),
            "child_age_range": f"{min_a}-{max_a}",
        }
    return False, {}


def check_retired_pension(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    retired = metrics.get("retired_count", 0) or 0
    transfer = metrics.get("income_transfer", 0) or 0
    pension_per = thresholds["audit"]["L04_pension_per_person"]
    if retired >= 1 and transfer < pension_per * retired:
        per_capita = round(transfer / retired, 2) if retired > 0 else 0
        return True, {
            "retired_count": retired,
            "income_transfer": round(transfer, 2),
            "per_capita": per_capita,
        }
    return False, {}


def check_income_consume_balance(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    income = metrics.get("income_total", 0) or 0
    consume = metrics.get("consume_total", 0) or 0
    nonconsume = metrics.get("nonconsume_total", 0) or 0
    dev = thresholds["audit"]["L08_balance_deviation"]
    if income > 0:
        balance = income - consume - nonconsume
        deviation = abs(balance) / income
        if deviation > dev:
            return True, {
                "income_total": round(income, 2),
                "consume_total": round(consume, 2),
                "nonconsume_total": round(nonconsume, 2),
                "balance": round(balance, 2),
                "deviation_pct": round(deviation * 100, 1),
            }
    return False, {}


def check_food_per_capita(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    perm = metrics.get("family_size_permanent", 0) or 0
    food = metrics.get("consume_food", 0) or 0
    total_days = metrics.get("_total_days", 90)
    floor = thresholds["audit"]["L09_food_per_capita_per_day"]
    if perm >= 2 and total_days > 0 and perm > 0:
        per_day = food / total_days / perm
        if per_day < floor:
            return True, {
                "family_size_permanent": perm,
                "consume_food": round(food, 2),
                "food_per_day": round(per_day, 2),
            }
    return False, {}


def check_large_single_amount(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    if ledger_grp.empty or "amount" not in ledger_grp.columns:
        return False, {}
    income = metrics.get("income_total", 0) or 0
    thr = thresholds["audit"]
    floor = thr["N01_amount_min"]
    ratio = thr["N01_income_ratio"]
    amounts = pd.to_numeric(ledger_grp["amount"], errors="coerce").fillna(0)
    large = amounts[(amounts > floor) & (income > 0) & (amounts > income * ratio)]
    if not large.empty:
        idx = large.idxmax()
        row = ledger_grp.loc[idx]
        return True, {
            "large_item": row.get("item_name", ""),
            "large_amount": round(float(large.max()), 2),
            "ratio_pct": round(float(large.max()) / income * 100, 1) if income > 0 else 0,
        }
    return False, {}


def check_consume_income_ratio(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    income = metrics.get("income_total", 0) or 0
    consume = metrics.get("consume_total", 0) or 0
    ratio_thr = thresholds["audit"]["R07_consume_income_ratio"]
    if income > 0 and consume / income < ratio_thr:
        return True, {
            "income_total": round(income, 2),
            "consume_total": round(consume, 2),
            "ratio_pct": round(consume / income * 100, 1),
        }
    return False, {}


def check_single_category_ratio(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    consume_total = metrics.get("consume_total", 0) or 0
    if consume_total <= 0:
        return False, {}
    cats = {
        "食品烟酒": metrics.get("consume_food", 0) or 0,
        "衣着": metrics.get("consume_clothing", 0) or 0,
        "居住": metrics.get("consume_housing", 0) or 0,
        "生活用品及服务": metrics.get("consume_daily", 0) or 0,
        "交通通信": metrics.get("consume_transport", 0) or 0,
        "教育文化娱乐": metrics.get("consume_edu", 0) or 0,
        "医疗保健": metrics.get("consume_medical", 0) or 0,
        "其他用品及服务": metrics.get("consume_other", 0) or 0,
    }
    ratio_thr = thresholds["audit"]["N02_single_category_ratio"]
    for cat_name, val in cats.items():
        ratio = val / consume_total
        if ratio > ratio_thr:
            return True, {
                "top_category": cat_name,
                "top_amount": round(val, 2),
                "ratio_pct": round(ratio * 100, 1),
            }
    return False, {}


def check_missing_item_name(metrics: dict, ledger_grp: pd.DataFrame, thresholds: dict) -> tuple:
    if ledger_grp.empty or "amount" not in ledger_grp.columns:
        return False, {}
    thr = thresholds["audit"]
    amounts = pd.to_numeric(ledger_grp["amount"], errors="coerce").fillna(0)
    no_name = (amounts > thr["Q01_no_name_amount_min"]) & (
        ledger_grp["item_name"].fillna("").str.strip() == ""
    )
    count = int(no_name.sum())
    if count >= thr["Q01_no_name_count_min"]:
        return True, {"count": count}
    return False, {}


CUSTOM_FUNCS = {
    "check_month_end_ratio": check_month_end_ratio,
    "check_gap_5_days": lambda m, l, t: check_gap_days(m, l, t, t["audit"]["R02_gap_days"]),
    "check_gap_10_days": lambda m, l, t: check_gap_days(m, l, t, t["audit"]["R03_gap_days"]),
    "check_month_missing": check_month_missing,
    "check_child_edu": check_child_edu,
    "check_retired_pension": check_retired_pension,
    "check_income_consume_balance": check_income_consume_balance,
    "check_food_per_capita": check_food_per_capita,
    "check_large_single_amount": check_large_single_amount,
    "check_single_category_ratio": check_single_category_ratio,
    "check_missing_item_name": check_missing_item_name,
    "check_consume_income_ratio": check_consume_income_ratio,
}


def _render_advice(template_key: str, context: dict, templates: dict) -> str:
    tmpl = templates.get(template_key, "")
    try:
        return tmpl.format(**context)
    except (KeyError, ValueError):
        return tmpl


def run_audit(months: list) -> int:
    if not months:
        return 0

    rules = _load_rules()
    templates = _load_advice_templates()
    thresholds = _load_thresholds()
    period_start, period_end = _period_label(months)

    where_clause, where_params = months_sql_filter(months)
    start_date, end_date, total_days = months_to_date_range(months)

    conn = get_conn()
    metrics_df = pd.read_sql("SELECT * FROM household_metrics", conn)
    ledger_df = pd.read_sql(
        f"SELECT * FROM raw_ledger WHERE {where_clause}",
        conn, params=where_params,
    )
    conn.close()

    if metrics_df.empty:
        return 0

    # 数据实际截止日期（而非月末），用于断记检测等场景
    if not ledger_df.empty and "record_date" in ledger_df.columns:
        max_record = pd.to_datetime(ledger_df["record_date"], errors="coerce").max()
        data_end = max_record.date() if pd.notna(max_record) else end_date
        actual_total_days = (data_end - start_date).days + 1
    else:
        data_end = end_date
        actual_total_days = total_days

    ledger_by_sid = {sid: grp for sid, grp in ledger_df.groupby("sid")}
    enabled_rules = [r for r in rules if r.get("enabled", False)]

    result_rows = []
    priority_scores = {}

    for _, m_row in metrics_df.iterrows():
        hhid = m_row["hhid"]
        m = m_row.to_dict()
        m["_months_list"] = months
        m["_start_date"] = start_date
        m["_end_date"] = data_end
        m["_data_end_date"] = data_end
        m["_total_days"] = actual_total_days

        ledger_grp = ledger_by_sid.get(hhid, pd.DataFrame())

        risk_score = 0.0

        for rule in enabled_rules:
            rule_id = rule["id"]
            triggered = False
            ctx = {}

            if "custom_func" in rule:
                func = CUSTOM_FUNCS.get(rule["custom_func"])
                if func:
                    triggered, ctx = func(m, ledger_grp, thresholds)
            elif "conditions" in rule:
                triggered = _eval_conditions(rule["conditions"], m)
                if triggered:
                    ctx = {c["field"]: m.get(c["field"]) for c in rule["conditions"]}

            if triggered:
                advice = _render_advice(rule.get("advice_template", rule_id), ctx, templates)
                result_rows.append({
                    "hhid": hhid,
                    "period_start": period_start,
                    "period_end": period_end,
                    "rule_id": rule_id,
                    "rule_group": rule.get("group", ""),
                    "rule_priority": rule.get("priority", "medium"),
                    "trigger_context": json.dumps(ctx, ensure_ascii=False, default=str),
                    "advice_text": advice,
                })
                risk_score += PRIORITY_WEIGHT.get(rule.get("priority", "medium"), 2)

        priority_scores[hhid] = risk_score

    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM audit_results")
        if result_rows:
            pd.DataFrame(result_rows).to_sql(
                "audit_results", conn, if_exists="append", index=False
            )

        labels_df = pd.read_sql(
            "SELECT hhid, quality_score FROM household_labels", conn
        )
        score_lookup = {row["hhid"]: row["quality_score"] or 50 for _, row in labels_df.iterrows()}
        thr = thresholds["visit_priority"]

        for hhid, risk in priority_scores.items():
            quality = score_lookup.get(hhid, 50)
            priority = (
                risk / max(1, max(priority_scores.values())) * thr["weight_risk"]
                + (1 - quality / 100) * thr["weight_quality"]
            )
            conn.execute(
                "INSERT INTO current_snapshot (hhid, period_start, period_end, visit_priority_score) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(hhid) DO UPDATE SET visit_priority_score=excluded.visit_priority_score",
                (hhid, period_start, period_end, round(priority, 4)),
            )
    conn.close()
    return len(result_rows)
