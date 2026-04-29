"""
Four-dimension label classifier for each household.
"""
import pandas as pd
from pathlib import Path

import yaml

from ..io.database import get_conn
from .metrics import _period_label

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _load_thresholds() -> dict:
    with open(CONFIG_DIR / "thresholds.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_income_wage_dominant(m: dict, thresholds: dict) -> bool:
    total = m.get("income_total", 0) or 0
    wage = m.get("income_wage", 0) or 0
    ratio = thresholds["income_structure"]["wage_ratio_workers"]
    return total > 0 and (wage / total) >= ratio


def check_income_business_dominant(m: dict, thresholds: dict) -> bool:
    total = m.get("income_total", 0) or 0
    gross = m.get("income_business_gross", 0) or 0
    cost = m.get("income_business_cost", 0) or 0
    net = gross - cost
    ratio1 = thresholds["income_structure"]["business_ratio"]
    ratio2 = thresholds["income_structure"]["business_gross_ratio"]
    if total <= 0:
        return False
    return (net / total >= ratio1) or (gross / total >= ratio2)


def check_income_transfer_dominant(m: dict, thresholds: dict) -> bool:
    total = m.get("income_total", 0) or 0
    transfer = m.get("income_transfer", 0) or 0
    ratio = thresholds["income_structure"]["transfer_ratio_retired"]
    return total > 0 and (transfer / total) >= ratio


def classify_income(m: dict, thresholds: dict) -> str:
    total = m.get("income_total", 0) or 0
    if total == 0:
        return "无收入记录"
    if check_income_wage_dominant(m, thresholds):
        return "工薪型"
    if check_income_business_dominant(m, thresholds):
        return "经营型"
    if check_income_transfer_dominant(m, thresholds):
        return "转移型"
    return "混合型"


def classify_lifecycle(m: dict) -> str:
    size = m.get("family_size_registered", 0) or 0
    has_06 = m.get("has_child_0_6", 0) or 0
    has_717 = m.get("has_child_7_17", 0) or 0
    has_elder = m.get("has_elder_60", 0) or 0
    min_age = m.get("min_age")
    max_age = m.get("max_age")

    if size <= 0:
        return "其他"
    if size == 1:
        return "单人户"

    # 有未成年 + 有老人 → 三代同堂
    has_minor = has_06 or has_717 or (min_age is not None and min_age < 18)
    if has_minor and has_elder:
        return "三代同堂"

    if has_06:
        return "幼儿家庭"
    if has_717:
        return "学龄家庭"

    # 有老人但无未成年 → 老年家庭（不要求全员≥60）
    if has_elder:
        return "老年家庭"

    # 全员18-59，无老人无小孩 → 中青年核心家庭
    if min_age is not None and max_age is not None and min_age >= 18 and max_age <= 59:
        return "中青年核心家庭"

    if size == 2:
        return "夫妻户"
    return "其他"


def classify_mobility(m: dict) -> str:
    perm = m.get("family_size_permanent", 0) or 0
    reg = m.get("family_size_registered", 0) or 0
    migrant = m.get("migrant_count", 0) or 0

    if reg <= 0:
        return "全家常住"
    if perm >= reg:
        return "全家常住"
    if migrant >= reg:
        return "整户外出"
    return "半流动"


def classify_quality(score: int) -> str:
    if score >= 80:
        return "A"
    elif score >= 60:
        return "B"
    elif score >= 40:
        return "C"
    else:
        return "D"


def _clean_count(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def generate_portrait_summary(metrics, labels, members_df=None) -> str:
    """Generate a one-line household portrait from deterministic labels and metrics."""
    n = _clean_count(metrics.get("family_size_permanent")) or _clean_count(
        metrics.get("family_size_registered")
    )
    lifecycle = labels.get("label_lifecycle") or "家庭"
    income = labels.get("label_income") or ""
    mobility = labels.get("label_mobility") or ""

    parts = []
    if n > 0:
        parts.append(f"{n}口{lifecycle}")
    else:
        parts.append(lifecycle)

    if income == "无收入记录":
        parts.append("本期未记录收入")
    elif income == "混合型":
        parts.append("收入来源较多元")
    elif income:
        parts.append(f"以{income.replace('型', '')}收入为主")

    retired_count = _clean_count(metrics.get("retired_count"))
    if retired_count >= 1:
        parts.append(f"{retired_count}人离退休")
    if _clean_count(metrics.get("has_child_7_17")):
        parts.append("有学龄子女")
    if _clean_count(metrics.get("has_child_0_6")):
        parts.append("有幼儿")

    if mobility and mobility != "全家常住":
        parts.append(mobility)

    return "，".join(str(p) for p in parts if p)


def classify_all(months: list) -> int:
    if not months:
        return 0

    thresholds = _load_thresholds()
    period_start, period_end = _period_label(months)

    conn = get_conn()
    metrics_df = pd.read_sql("SELECT * FROM household_metrics", conn)
    labels_df = pd.read_sql(
        "SELECT hhid, quality_score FROM household_labels", conn
    )
    members_df = pd.read_sql("SELECT * FROM raw_members", conn)
    conn.close()

    if metrics_df.empty:
        return 0

    score_lookup = {}
    for _, row in labels_df.iterrows():
        score_lookup[row["hhid"]] = row.get("quality_score", 50) or 50

    rows = []
    for _, m in metrics_df.iterrows():
        hhid = m["hhid"]
        score = score_lookup.get(hhid, 50)

        label_income = classify_income(m.to_dict(), thresholds)
        label_lifecycle = classify_lifecycle(m.to_dict())
        label_mobility = classify_mobility(m.to_dict())
        label_quality = classify_quality(score)
        labels_dict = {
            "label_income": label_income,
            "label_lifecycle": label_lifecycle,
            "label_mobility": label_mobility,
            "label_quality": label_quality,
        }
        portrait_summary = generate_portrait_summary(
            m.to_dict(),
            labels_dict,
            members_df[members_df["sid"] == hhid] if not members_df.empty else None,
        )

        rows.append({
            "hhid": hhid,
            "period_start": period_start,
            "period_end": period_end,
            "label_income": label_income,
            "label_lifecycle": label_lifecycle,
            "label_mobility": label_mobility,
            "label_quality": label_quality,
            "quality_score": score,
            "portrait_summary": portrait_summary,
        })

    labels = pd.DataFrame(rows)
    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM household_labels")
        labels.to_sql("household_labels", conn, if_exists="append", index=False)
    conn.close()
    return len(labels)
