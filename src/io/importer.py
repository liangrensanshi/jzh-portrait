import re
import pandas as pd
from pathlib import Path
from typing import Optional

import yaml

from .database import get_conn, init_db
from .cleaner import (
    clean_string_fields, month_to_quarter,
    cast_household, cast_village, cast_house,
    cast_survey_a, cast_survey_b, cast_ledger,
)

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _load_mapping(file_type: str) -> dict:
    with open(CONFIG_DIR / "field_mapping.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f).get(file_type, {})


def _rename_columns(df: pd.DataFrame, file_type: str) -> pd.DataFrame:
    mapping = _load_mapping(file_type)
    rename = {k: v for k, v in mapping.items() if k in df.columns}
    return df.rename(columns=rename)


def _detect_file_type(filename: str) -> Optional[str]:
    name = filename.lower()
    if "住户" in filename and "问卷" not in filename:
        return "household"
    if "小区" in filename:
        return "village"
    if "住宅" in filename:
        return "house"
    if "问卷a" in name or "问卷_a" in name or ("问卷" in filename and "a" in name):
        return "survey_a"
    if "问卷b" in name or "问卷_b" in name or ("问卷" in filename and "b" in name):
        return "survey_b"
    if "账页" in filename:
        return "ledger"
    return None


def _parse_ledger_year_quarter(filename: str):
    """Parse year and quarter from ledger filename like '账页-2026-q1.csv'."""
    m = re.search(r"账页[-_]?(\d{4})[-_]?[qQ](\d)", filename)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _log_import(conn, year, quarter, file_type, file_name, row_count, status):
    conn.execute(
        "INSERT INTO import_log (year, quarter, file_type, file_name, row_count, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (year, quarter, file_type, file_name, row_count, status),
    )


def import_household(file_path: str) -> int:
    init_db()
    df = pd.read_csv(file_path, encoding="gb18030", dtype=str, keep_default_na=False)
    df = clean_string_fields(df)
    df = _rename_columns(df, "household")
    df = cast_household(df)

    keep = ["hhid", "coun", "vcode", "urban_rural", "hcode", "hname",
            "hhstatus", "hhchange", "contact", "opendate", "exitdate",
            "acnttype", "surveytype", "phone"]
    df = df[[c for c in keep if c in df.columns]].copy()

    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM raw_households")
        df.to_sql("raw_households", conn, if_exists="append", index=False)
        _log_import(conn, None, None, "household", Path(file_path).name, len(df), "success")
    conn.close()
    return len(df)


def import_village(file_path: str) -> int:
    init_db()
    df = pd.read_csv(file_path, encoding="gb18030", dtype=str, keep_default_na=False)
    df = clean_string_fields(df)
    df = _rename_columns(df, "village")
    df = cast_village(df)

    keep = ["vcode", "coun", "counname", "townname", "vname", "level_code"]
    df = df[[c for c in keep if c in df.columns]].copy()

    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM raw_villages")
        df.to_sql("raw_villages", conn, if_exists="append", index=False)
        _log_import(conn, None, None, "village", Path(file_path).name, len(df), "success")
    conn.close()
    return len(df)


def import_house(file_path: str) -> int:
    init_db()
    df = pd.read_csv(file_path, encoding="gb18030", dtype=str, keep_default_na=False)
    df = clean_string_fields(df)
    df = _rename_columns(df, "house")
    df = cast_house(df)

    keep = ["hcode", "coun", "vcode", "haddr", "intcode", "hstatus"]
    df = df[[c for c in keep if c in df.columns]].copy()

    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM raw_houses")
        df.to_sql("raw_houses", conn, if_exists="append", index=False)
        _log_import(conn, None, None, "house", Path(file_path).name, len(df), "success")
    conn.close()
    return len(df)


def import_survey_a(file_path: str) -> int:
    init_db()
    df = pd.read_csv(file_path, encoding="gb18030", dtype=str, keep_default_na=False)
    df = clean_string_fields(df)
    df = _rename_columns(df, "survey_a")
    df = cast_survey_a(df)

    keep = [
        "sid", "coln", "a101_name", "a103_relation", "a104_gender",
        "a105_birth", "a111_medical", "a113_edu", "a114_marriage", "a119_permanent",
        "a201_retired", "a202_pension", "a203_disabled", "a204_employed",
        "a205_work_type", "a206_industry", "a208_work_duration", "a209_work_area",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()

    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM raw_members")
        df.to_sql("raw_members", conn, if_exists="append", index=False)
        _log_import(conn, None, None, "survey_a", Path(file_path).name, len(df), "success")
    conn.close()
    return len(df)


def import_survey_b(file_path: str) -> int:
    init_db()
    df = pd.read_csv(file_path, encoding="gb18030", dtype=str, keep_default_na=False)
    df = clean_string_fields(df)
    df = _rename_columns(df, "survey_b")
    df = cast_survey_b(df)

    keep = ["sid", "coln", "b105_housing_area", "b118_housing_value", "b201_car"]
    df = df[[c for c in keep if c in df.columns]].copy()

    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM raw_surveyb")
        df.to_sql("raw_surveyb", conn, if_exists="append", index=False)
        _log_import(conn, None, None, "survey_b", Path(file_path).name, len(df), "success")
    conn.close()
    return len(df)


def import_ledger(file_path: str, year: int, quarter: int) -> int:
    init_db()
    df = pd.read_csv(file_path, encoding="gb18030", dtype=str, keep_default_na=False)
    df = clean_string_fields(df)
    df = _rename_columns(df, "ledger")
    df = cast_ledger(df)

    keep = [
        "sid", "year", "month", "page_no", "row_no", "code", "amount", "qty",
        "person_code", "is_online", "acnt_method", "item_name", "issue_type",
        "record_date", "create_time", "update_time", "device_id",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()

    df["quarter"] = df["month"].apply(lambda m: month_to_quarter(int(m)) if m is not None else None)
    df["year"] = df["year"].apply(lambda x: int(x) if x is not None else None)

    conn = get_conn()
    with conn:
        # Delete by actual (year, month, sid) found in CSV to handle cross-year quarters correctly
        ym_sids = df[["year", "month", "sid"]].drop_duplicates()
        for _, r in ym_sids.iterrows():
            conn.execute(
                "DELETE FROM raw_ledger WHERE year=? AND month=? AND sid=?",
                (r["year"], r["month"], r["sid"]),
            )
        df.to_sql("raw_ledger", conn, if_exists="append", index=False)
        _log_import(conn, year, quarter, "ledger", Path(file_path).name, len(df), "success")
    conn.close()
    return len(df)


def auto_import(
    file_path: str,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    original_filename: Optional[str] = None,
) -> dict:
    """Detect file type and dispatch to the appropriate import function."""
    filename = original_filename or Path(file_path).name
    file_type = _detect_file_type(filename)
    if file_type is None:
        raise ValueError(f"无法识别文件类型: {filename}")

    if file_type == "ledger":
        detected_year, detected_quarter = _parse_ledger_year_quarter(filename)
        year = detected_year or year
        quarter = detected_quarter or quarter
        if year is None or quarter is None:
            raise ValueError("账页文件名格式应为'账页-YYYY-qN.csv'，或手动指定年度和季度")
        row_count = import_ledger(file_path, year, quarter)
        return {"file_type": file_type, "year": year, "quarter": quarter, "row_count": row_count}

    dispatch = {
        "household": import_household,
        "village": import_village,
        "house": import_house,
        "survey_a": import_survey_a,
        "survey_b": import_survey_b,
    }
    row_count = dispatch[file_type](file_path)
    return {"file_type": file_type, "row_count": row_count}
