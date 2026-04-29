"""
Compute household_metrics from raw_ledger + raw_members.
"""
import calendar
import json
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from ..io.database import get_conn


def months_to_date_range(months: list) -> tuple:
    """Return (start_date, end_date, total_days) for a list of (year, month) tuples."""
    start = date(months[0][0], months[0][1], 1)
    last_y, last_m = months[-1]
    last_day = calendar.monthrange(last_y, last_m)[1]
    end = date(last_y, last_m, last_day)
    total_days = (end - start).days + 1
    return start, end, total_days


def months_sql_filter(months: list) -> tuple:
    """Return (where_clause, params) for filtering raw_ledger by months list."""
    if not months:
        return "1=0", []
    conditions = " OR ".join("(year=? AND month=?)" for _ in months)
    params = [v for ym in months for v in ym]
    return f"({conditions})", params


def _period_label(months: list) -> tuple:
    """Return (period_start, period_end) as 'YYYY-MM' strings."""
    start = f"{months[0][0]}-{months[0][1]:02d}"
    end = f"{months[-1][0]}-{months[-1][1]:02d}"
    return start, end


def compute_metrics(months: list):
    """Compute metrics for all households over the given list of (year, month) tuples."""
    if not months:
        return 0

    where_clause, where_params = months_sql_filter(months)
    period_start, period_end = _period_label(months)

    conn = get_conn()
    ledger = pd.read_sql(
        f"SELECT * FROM raw_ledger WHERE {where_clause}",
        conn, params=where_params,
    )
    members = pd.read_sql("SELECT * FROM raw_members", conn)
    conn.close()

    ref_year = months[-1][0] if months else date.today().year
    ledger_metrics = _aggregate_ledger(ledger, months)
    member_metrics = _aggregate_members(members, ref_year)

    all_hhids = set(ledger_metrics["hhid"]).union(set(member_metrics["hhid"]))
    if not all_hhids:
        return 0

    ldf = ledger_metrics.set_index("hhid")
    mdf = member_metrics.set_index("hhid")
    combined = ldf.join(mdf, how="outer").reset_index()
    combined = combined.rename(columns={"index": "hhid"}) if "index" in combined.columns else combined
    combined["period_start"] = period_start
    combined["period_end"] = period_end

    for col in combined.select_dtypes(include="float").columns:
        combined[col] = combined[col].fillna(0)
    for col in combined.select_dtypes(include="Int64").columns:
        combined[col] = combined[col].fillna(0)

    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM household_metrics")
        combined.to_sql("household_metrics", conn, if_exists="append", index=False)
    conn.close()
    return len(combined)


def _aggregate_ledger(ledger: pd.DataFrame, months: list) -> pd.DataFrame:
    if ledger.empty:
        return pd.DataFrame(columns=["hhid"])

    rows = []

    for sid, grp in ledger.groupby("sid"):
        code = grp["code"].fillna("").astype(str)
        amount = pd.to_numeric(grp["amount"], errors="coerce").fillna(0)

        def code_sum(prefixes):
            mask = code.apply(lambda c: any(c.startswith(p) for p in prefixes))
            return float(amount[mask].sum())

        income_wage = code_sum(["21"])
        income_business_gross = code_sum(["12", "22"])
        income_business_cost = code_sum(["13", "14", "15"])
        income_property = code_sum(["23"])
        income_transfer = code_sum(["24"])
        income_total = income_wage + income_business_gross + income_property + income_transfer

        consume_food = code_sum(["31"])
        consume_clothing = code_sum(["32"])
        consume_housing = code_sum(["33"])
        consume_daily = code_sum(["34"])
        consume_transport = code_sum(["35"])
        consume_edu = code_sum(["36"])
        consume_medical = code_sum(["37"])
        consume_other = code_sum(["38"])
        consume_total = code_sum(["3"])
        in_kind_total = code_sum(["4"])
        nonconsume_total = code_sum(["5"])

        ledger_count = len(grp)
        ledger_consume_count = int((code.str.startswith("3")).sum())
        ledger_record_days = grp["record_date"].nunique()

        max_gap_days = _calc_max_gap(grp, months)
        month_end_ratio = _calc_month_end_ratio(grp)

        if ledger_count > 0:
            mobile_ratio = float(
                (grp["acnt_method"].fillna("").str.contains("移动")).sum()
            ) / ledger_count
            online_ratio = float(
                (grp["is_online"].fillna("").str.contains("是")).sum()
            ) / ledger_count
        else:
            mobile_ratio = 0.0
            online_ratio = 0.0

        cats = [
            code.str.startswith("31"), code.str.startswith("32"),
            code.str.startswith("33"), code.str.startswith("34"),
            code.str.startswith("35"), code.str.startswith("36"),
            code.str.startswith("37"), code.str.startswith("38"),
        ]
        category_coverage = int(sum(1 for c in cats if c.sum() > 0))

        issue_count = int(
            (~grp["issue_type"].fillna("无问题").str.strip().eq("无问题")).sum()
        )

        rows.append({
            "hhid": sid,
            "income_wage": income_wage,
            "income_business_gross": income_business_gross,
            "income_business_cost": income_business_cost,
            "income_property": income_property,
            "income_transfer": income_transfer,
            "income_total": income_total,
            "consume_food": consume_food,
            "consume_clothing": consume_clothing,
            "consume_housing": consume_housing,
            "consume_daily": consume_daily,
            "consume_transport": consume_transport,
            "consume_edu": consume_edu,
            "consume_medical": consume_medical,
            "consume_other": consume_other,
            "consume_total": consume_total,
            "in_kind_total": in_kind_total,
            "nonconsume_total": nonconsume_total,
            "ledger_count": ledger_count,
            "ledger_consume_count": ledger_consume_count,
            "ledger_record_days": ledger_record_days,
            "max_gap_days": max_gap_days,
            "month_end_ratio": month_end_ratio,
            "mobile_ratio": mobile_ratio,
            "online_ratio": online_ratio,
            "category_coverage": category_coverage,
            "issue_count": issue_count,
        })

    return pd.DataFrame(rows)


def _calc_max_gap(grp: pd.DataFrame, months: list) -> int:
    consume = grp[grp["code"].fillna("").astype(str).str.startswith("3")]
    if consume.empty:
        return max(calendar.monthrange(y, m)[1] for y, m in months)

    dates = pd.to_datetime(consume["record_date"], errors="coerce").dropna()
    if dates.empty:
        return max(calendar.monthrange(y, m)[1] for y, m in months)

    date_set = set(dates.dt.date)
    overall_max = 0

    for year, month in months:
        _, last_day = calendar.monthrange(year, month)
        m_start = date(year, month, 1)
        m_end = date(year, month, last_day)
        cur = m_start
        current_gap = 0
        month_max = 0
        while cur <= m_end:
            if cur in date_set:
                month_max = max(month_max, current_gap)
                current_gap = 0
            else:
                current_gap += 1
            cur += timedelta(days=1)
        month_max = max(month_max, current_gap)
        overall_max = max(overall_max, month_max)

    return overall_max


def _calc_month_end_ratio(grp: pd.DataFrame) -> float:
    ct = pd.to_datetime(grp["create_time"], errors="coerce").dropna()
    if ct.empty:
        ct = pd.to_datetime(grp["record_date"], errors="coerce").dropna()
    if ct.empty:
        return 0.0
    after_21 = (ct.dt.day >= 21).sum()
    return float(after_21) / len(ct)


def _calc_age(birth_yyyymm: str, ref_year: int) -> Optional[int]:
    if not birth_yyyymm or len(str(birth_yyyymm)) < 4:
        return None
    try:
        birth_year = int(str(birth_yyyymm)[:4])
        return ref_year - birth_year
    except (ValueError, TypeError):
        return None


def _aggregate_members(members: pd.DataFrame, ref_year: int) -> pd.DataFrame:
    if members.empty:
        return pd.DataFrame(columns=["hhid"])

    rows = []
    for sid, grp in members.groupby("sid"):
        ages = [_calc_age(b, ref_year) for b in grp["a105_birth"].fillna("").astype(str)]
        ages = [a for a in ages if a is not None]

        family_size_registered = len(grp)
        permanent_mask = grp["a119_permanent"].apply(
            lambda x: int(float(x)) == 1 if pd.notna(x) else False
        )
        family_size_permanent = int(permanent_mask.sum())

        employed_mask = grp["a204_employed"].apply(
            lambda x: int(float(x)) == 1 if pd.notna(x) else False
        )
        employed_count = int(employed_mask.sum())

        # 工资收入者: a205=2(公职人员) 3(事业单位) 4(国企雇员) 5(其他雇员)
        wage_earner_mask = grp["a205_work_type"].apply(
            lambda x: int(float(x)) in (2, 3, 4, 5) if pd.notna(x) else False
        )
        wage_earner_count = int(wage_earner_mask.sum())

        retired_mask = grp["a201_retired"].apply(
            lambda x: int(float(x)) in (1, 2) if pd.notna(x) else False
        )
        retired_count = int(retired_mask.sum())

        def is_migrant(row):
            def _int_val(val):
                try:
                    return int(float(val))
                except (TypeError, ValueError):
                    return 0
            perm = _int_val(row.get("a119_permanent", 0))
            emp = _int_val(row.get("a204_employed", 0))
            area = _int_val(row.get("a209_work_area", 0))
            return perm != 1 and emp == 1 and area >= 3

        migrant_count = int(grp.apply(is_migrant, axis=1).sum())

        min_age = int(min(ages)) if ages else None
        max_age = int(max(ages)) if ages else None
        avg_age = float(sum(ages) / len(ages)) if ages else None

        has_child_0_6 = int(any(a is not None and 0 <= a <= 6 for a in ages))
        has_child_7_17 = int(any(a is not None and 7 <= a <= 17 for a in ages))
        has_elder_60 = int(any(a is not None and a >= 60 for a in ages))

        rows.append({
            "hhid": sid,
            "family_size_permanent": family_size_permanent,
            "family_size_registered": family_size_registered,
            "employed_count": employed_count,
            "wage_earner_count": wage_earner_count,
            "retired_count": retired_count,
            "migrant_count": migrant_count,
            "min_age": min_age,
            "max_age": max_age,
            "avg_age": avg_age,
            "has_child_0_6": has_child_0_6,
            "has_child_7_17": has_child_7_17,
            "has_elder_60": has_elder_60,
        })

    return pd.DataFrame(rows)


def rebuild_snapshot():
    """Rebuild current_snapshot from current household_metrics and household_labels."""
    conn = get_conn()

    metrics_df = pd.read_sql("SELECT * FROM household_metrics", conn)
    labels_df = pd.read_sql("SELECT * FROM household_labels", conn)

    if metrics_df.empty:
        conn.close()
        return 0

    rows = []
    for _, m_row in metrics_df.iterrows():
        hhid = m_row["hhid"]
        lb_row = labels_df[labels_df["hhid"] == hhid]
        labels_dict = lb_row.iloc[0].to_dict() if not lb_row.empty else {}

        rows.append({
            "hhid": hhid,
            "period_start": m_row.get("period_start"),
            "period_end": m_row.get("period_end"),
            "latest_metrics_json": json.dumps(m_row.to_dict(), ensure_ascii=False, default=str),
            "latest_labels_json": json.dumps(labels_dict, ensure_ascii=False, default=str),
            "rolling_consume": float(m_row.get("consume_total") or 0),
            "rolling_income": float(m_row.get("income_total") or 0),
            "last_visit_date": None,
            "visit_priority_score": None,
        })

    snap_df = pd.DataFrame(rows)
    with conn:
        conn.execute("DELETE FROM current_snapshot")
        snap_df.to_sql("current_snapshot", conn, if_exists="append", index=False)
    conn.close()
    return len(snap_df)
