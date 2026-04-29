"""
Compute quality score (0-100) for each household based on ledger behavior.
"""
import pandas as pd
from pathlib import Path

import yaml

from ..io.database import get_conn
from .metrics import months_sql_filter, _period_label

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _load_thresholds() -> dict:
    with open(CONFIG_DIR / "thresholds.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def score_household(m: dict, thresholds: dict) -> int:
    rules = thresholds["scoring"]["rules"]
    score = 100

    missing_months = m.get("_missing_months", 0) or 0
    r10 = rules.get("R10_month_missing", {})
    r10_deduct = min(
        missing_months * r10.get("deduction_per_trigger", 15),
        r10.get("max_points", 15),
    )
    score -= r10_deduct

    consume_food = m.get("consume_food", 0) or 0
    if consume_food == 0:
        score -= rules.get("R04_food_missing", {}).get("deduction", 10)

    mer = m.get("month_end_ratio", 0) or 0
    r01 = rules.get("R01_month_end", {})
    if mer > 0.5:
        excess = int((mer - 0.5) * 100 / 10)
        r01_deduct = min(
            excess * r01.get("deduction_per_10_percent", 3),
            r01.get("max_points", 15),
        )
        score -= r01_deduct

    max_gap = m.get("max_gap_days", 0) or 0
    if 5 <= max_gap < 10:
        score -= rules.get("R02_gap_5", {}).get("deduction", 8)
    if max_gap >= 10:
        score -= rules.get("R03_gap_10", {}).get("deduction", 15)

    issue_count = m.get("issue_count", 0) or 0
    if issue_count > 0:
        r_q02 = rules.get("Q02_system_issue", {})
        q02_deduct = min(
            issue_count * r_q02.get("deduction_per_record", 3),
            r_q02.get("max_points", 15),
        )
        score -= q02_deduct

    income_total = m.get("income_total", 0) or 0
    consume_total = m.get("consume_total", 0) or 0
    if income_total > 0 and consume_total / income_total < 0.3:
        score -= rules.get("R07_consume_low", {}).get("deduction", 5)

    return max(0, min(100, score))


def compute_scores(months: list) -> int:
    if not months:
        return 0

    thresholds = _load_thresholds()
    where_clause, where_params = months_sql_filter(months)
    period_start, period_end = _period_label(months)

    conn = get_conn()
    metrics_df = pd.read_sql("SELECT * FROM household_metrics", conn)
    ledger_df = pd.read_sql(
        f"SELECT sid, month FROM raw_ledger WHERE {where_clause}",
        conn, params=where_params,
    )
    conn.close()

    if metrics_df.empty:
        return 0

    month_set = set(m for _, m in months)

    missing_map = {}
    for sid, grp in ledger_df.groupby("sid"):
        present_months = set(grp["month"].dropna().astype(int).tolist())
        missing = [m for m in month_set if m not in present_months]
        missing_map[sid] = len(missing)

    rows = []
    for _, m in metrics_df.iterrows():
        hhid = m["hhid"]
        m_dict = m.to_dict()
        m_dict["_missing_months"] = missing_map.get(hhid, 0)
        score = score_household(m_dict, thresholds)
        rows.append({
            "hhid": hhid,
            "period_start": period_start,
            "period_end": period_end,
            "quality_score": score,
        })

    score_df = pd.DataFrame(rows)

    conn = get_conn()
    with conn:
        for _, row in score_df.iterrows():
            existing = conn.execute(
                "SELECT 1 FROM household_labels WHERE hhid=?", (row["hhid"],)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE household_labels SET quality_score=?, period_start=?, period_end=? WHERE hhid=?",
                    (row["quality_score"], period_start, period_end, row["hhid"]),
                )
            else:
                conn.execute(
                    "INSERT INTO household_labels (hhid, period_start, period_end, quality_score) VALUES (?, ?, ?, ?)",
                    (row["hhid"], period_start, period_end, row["quality_score"]),
                )
    conn.close()
    return len(score_df)
