import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "portrait.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate_to_new_schema(conn):
    """Detect old year+quarter schema and drop+recreate affected tables."""
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(raw_households)").fetchall()]
    except Exception:
        cols = []
    if "year" in cols:
        conn.executescript("""
            DROP TABLE IF EXISTS raw_households;
            DROP TABLE IF EXISTS raw_villages;
            DROP TABLE IF EXISTS raw_houses;
            DROP TABLE IF EXISTS raw_members;
            DROP TABLE IF EXISTS raw_surveyb;
            DROP TABLE IF EXISTS household_metrics;
            DROP TABLE IF EXISTS household_labels;
            DROP TABLE IF EXISTS audit_results;
            DROP TABLE IF EXISTS current_snapshot;
            DROP TABLE IF EXISTS notes;
            DROP TABLE IF EXISTS import_log;
        """)
    # Migration: add wage_earner_count column if missing
    try:
        metrics_cols = [r[1] for r in conn.execute("PRAGMA table_info(household_metrics)").fetchall()]
        if "wage_earner_count" not in metrics_cols:
            conn.execute("ALTER TABLE household_metrics ADD COLUMN wage_earner_count INTEGER DEFAULT 0")
    except Exception:
        pass
    # Migration: add generated one-line portrait summary if missing
    try:
        label_cols = [r[1] for r in conn.execute("PRAGMA table_info(household_labels)").fetchall()]
        if label_cols and "portrait_summary" not in label_cols:
            conn.execute("ALTER TABLE household_labels ADD COLUMN portrait_summary TEXT")
    except Exception:
        pass
    # Also fix import_log independently
    try:
        log_cols = [r[1] for r in conn.execute("PRAGMA table_info(import_log)").fetchall()]
    except Exception:
        log_cols = []
    if log_cols and "month" in log_cols and "quarter" not in log_cols:
        conn.execute("DROP TABLE IF EXISTS import_log")


def init_db():
    conn = get_conn()
    _migrate_to_new_schema(conn)
    with conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS raw_households (
    hhid TEXT PRIMARY KEY,
    coun TEXT,
    vcode TEXT,
    hcode TEXT,
    urban_rural TEXT,
    hname TEXT,
    hhstatus INTEGER,
    hhchange INTEGER,
    contact INTEGER,
    opendate TEXT,
    exitdate TEXT,
    acnttype INTEGER,
    surveytype INTEGER,
    phone TEXT,
    import_time DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_villages (
    vcode TEXT,
    coun TEXT,
    counname TEXT,
    townname TEXT,
    vname TEXT,
    level_code TEXT,
    PRIMARY KEY (vcode, coun)
);

CREATE TABLE IF NOT EXISTS raw_houses (
    hcode TEXT PRIMARY KEY,
    coun TEXT,
    vcode TEXT,
    haddr TEXT,
    intcode TEXT,
    hstatus INTEGER
);

CREATE TABLE IF NOT EXISTS raw_members (
    sid TEXT,
    coln INTEGER,
    a101_name TEXT,
    a103_relation INTEGER,
    a104_gender INTEGER,
    a105_birth TEXT,
    a111_medical INTEGER,
    a113_edu INTEGER,
    a114_marriage INTEGER,
    a119_permanent INTEGER,
    a201_retired INTEGER,
    a202_pension INTEGER,
    a203_disabled INTEGER,
    a204_employed INTEGER,
    a205_work_type INTEGER,
    a206_industry TEXT,
    a208_work_duration REAL,
    a209_work_area INTEGER,
    PRIMARY KEY (sid, coln)
);

CREATE TABLE IF NOT EXISTS raw_surveyb (
    sid TEXT PRIMARY KEY,
    coln INTEGER,
    b105_housing_area REAL,
    b118_housing_value REAL,
    b201_car INTEGER
);

CREATE TABLE IF NOT EXISTS raw_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sid TEXT,
    year INTEGER,
    month INTEGER,
    quarter INTEGER,
    page_no TEXT,
    row_no TEXT,
    code TEXT,
    amount REAL,
    qty REAL,
    person_code TEXT,
    is_online TEXT,
    acnt_method TEXT,
    item_name TEXT,
    issue_type TEXT,
    record_date TEXT,
    create_time TEXT,
    update_time TEXT,
    device_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_ledger_sid ON raw_ledger(sid);
CREATE INDEX IF NOT EXISTS idx_ledger_sid_ym ON raw_ledger(sid, year, month);
CREATE INDEX IF NOT EXISTS idx_ledger_code ON raw_ledger(code);

CREATE TABLE IF NOT EXISTS household_metrics (
    hhid TEXT PRIMARY KEY,
    period_start TEXT,
    period_end TEXT,
    income_wage REAL,
    income_business_gross REAL,
    income_business_cost REAL,
    income_property REAL,
    income_transfer REAL,
    income_total REAL,
    consume_food REAL,
    consume_clothing REAL,
    consume_housing REAL,
    consume_daily REAL,
    consume_transport REAL,
    consume_edu REAL,
    consume_medical REAL,
    consume_other REAL,
    consume_total REAL,
    in_kind_total REAL,
    nonconsume_total REAL,
    family_size_permanent INTEGER,
    family_size_registered INTEGER,
    employed_count INTEGER,
    wage_earner_count INTEGER,
    retired_count INTEGER,
    migrant_count INTEGER,
    min_age INTEGER,
    max_age INTEGER,
    avg_age REAL,
    has_child_0_6 INTEGER,
    has_child_7_17 INTEGER,
    has_elder_60 INTEGER,
    ledger_count INTEGER,
    ledger_consume_count INTEGER,
    ledger_record_days INTEGER,
    max_gap_days INTEGER,
    month_end_ratio REAL,
    mobile_ratio REAL,
    online_ratio REAL,
    category_coverage INTEGER,
    issue_count INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS household_labels (
    hhid TEXT PRIMARY KEY,
    period_start TEXT,
    period_end TEXT,
    label_income TEXT,
    label_lifecycle TEXT,
    label_mobility TEXT,
    label_quality TEXT,
    quality_score INTEGER,
    portrait_summary TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hhid TEXT,
    period_start TEXT,
    period_end TEXT,
    rule_id TEXT,
    rule_group TEXT,
    rule_priority TEXT,
    trigger_context TEXT,
    advice_text TEXT,
    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_hhid ON audit_results(hhid);

CREATE TABLE IF NOT EXISTS current_snapshot (
    hhid TEXT PRIMARY KEY,
    period_start TEXT,
    period_end TEXT,
    latest_metrics_json TEXT,
    latest_labels_json TEXT,
    rolling_consume REAL,
    rolling_income REAL,
    last_visit_date TEXT,
    visit_priority_score REAL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hhid TEXT,
    note_text TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER,
    quarter INTEGER,
    file_type TEXT,
    file_name TEXT,
    row_count INTEGER,
    import_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT
);
""")
    conn.close()
