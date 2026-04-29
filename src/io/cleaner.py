import pandas as pd
import re


def clean_string_fields(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip().str.replace("\t", "", regex=False)
    df = df.replace({"": None, "nan": None, "NaN": None, "NULL": None})
    return df


def month_to_quarter(month: int) -> int:
    if month in (12, 1, 2):
        return 1
    elif month in (3, 4, 5):
        return 2
    elif month in (6, 7, 8):
        return 3
    else:
        return 4


def safe_int(val):
    try:
        return int(float(str(val))) if val is not None else None
    except (ValueError, TypeError):
        return None


def safe_float(val):
    try:
        return float(str(val)) if val is not None else None
    except (ValueError, TypeError):
        return None


def cast_household(df: pd.DataFrame) -> pd.DataFrame:
    int_cols = ["hhstatus", "hhchange", "contact", "acnttype", "surveytype"]
    for c in int_cols:
        if c in df.columns:
            df[c] = df[c].apply(safe_int)
    return df


def cast_village(df: pd.DataFrame) -> pd.DataFrame:
    return df


def cast_house(df: pd.DataFrame) -> pd.DataFrame:
    if "hstatus" in df.columns:
        df["hstatus"] = df["hstatus"].apply(safe_int)
    return df


def cast_survey_a(df: pd.DataFrame) -> pd.DataFrame:
    int_cols = [
        "coln", "a103_relation", "a104_gender",
        "a111_medical", "a113_edu", "a114_marriage", "a119_permanent",
        "a201_retired", "a202_pension", "a203_disabled", "a204_employed",
        "a205_work_type", "a209_work_area",
    ]
    for c in int_cols:
        if c in df.columns:
            df[c] = df[c].apply(safe_int)
    if "a208_work_duration" in df.columns:
        df["a208_work_duration"] = df["a208_work_duration"].apply(safe_float)
    return df


def cast_survey_b(df: pd.DataFrame) -> pd.DataFrame:
    for c in ["coln", "b201_car"]:
        if c in df.columns:
            df[c] = df[c].apply(safe_int)
    for c in ["b105_housing_area", "b118_housing_value"]:
        if c in df.columns:
            df[c] = df[c].apply(safe_float)
    return df


def cast_ledger(df: pd.DataFrame) -> pd.DataFrame:
    for c in ["year", "month"]:
        if c in df.columns:
            df[c] = df[c].apply(safe_int)
    for c in ["amount", "qty"]:
        if c in df.columns:
            df[c] = df[c].apply(safe_float)
    return df
