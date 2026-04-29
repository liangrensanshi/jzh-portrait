"""Global CSS for the Streamlit app."""


def get_global_css() -> str:
    return """
<style>
@import url('https://cdn.bootcdn.net/ajax/libs/bootstrap-icons/1.11.3/font/bootstrap-icons.min.css');

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Base  */
/* ════════════════════════════════════════════════════════════════════════════ */
html, body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    background: #F8FAFC !important;
}
.stApp {
    background: #F8FAFC !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif !important;
}

/* Main content area */
.block-container {
    padding: 32px 40px 48px !important;
    max-width: 1440px !important;
    background: transparent !important;
}
@media (max-width: 900px) {
    .block-container { padding: 20px 20px 32px !important; }
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Sidebar  */
/* ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stSidebar"] > div:first-child {
    background: #0F172A !important;
}
[data-testid="stSidebar"] {
    background: #0F172A !important;
}
[data-testid="stSidebar"] section {
    background: #0F172A !important;
}
[data-testid="stSidebar"] * { color: #94A3B8 !important; }
[data-testid="stSidebar"] hr {
    border-color: rgba(148,163,184,0.15) !important;
    margin: 16px 0 !important;
}

/* Nav radio */
[data-testid="stSidebar"] .stRadio > label { display: none; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
    gap: 4px !important;
    display: flex !important;
    flex-direction: column !important;
}
[data-testid="stSidebar"] .stRadio label {
    padding: 10px 14px !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    letter-spacing: 0.01em !important;
    cursor: pointer !important;
    border: none !important;
    display: block !important;
    transition: all 0.2s ease !important;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(255,255,255,0.08) !important;
    color: #E2E8F0 !important;
}
[data-testid="stSidebar"] .stRadio label[aria-checked="true"],
[data-testid="stSidebar"] .stRadio label[data-checked="true"] {
    background: rgba(59,130,246,0.15) !important;
    color: #60A5FA !important;
    font-weight: 600 !important;
}

/* Sidebar controls */
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: rgba(255,255,255,0.06) !important;
    border-color: rgba(148,163,184,0.2) !important;
    border-radius: 10px !important;
}
[data-testid="stSidebar"] [data-baseweb="multi-select"] > div {
    background: rgba(255,255,255,0.06) !important;
    border-color: rgba(148,163,184,0.2) !important;
    border-radius: 10px !important;
}
[data-testid="stSidebar"] [data-baseweb="tag"] {
    background: rgba(59,130,246,0.2) !important;
    color: #93C5FD !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stMultiSelect label {
    color: #64748B !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Page header  */
/* ════════════════════════════════════════════════════════════════════════════ */
.page-header {
    padding: 0 0 8px;
    margin-bottom: 12px;
}
.page-header h2 {
    font-size: 20px !important;
    font-weight: 700 !important;
    color: #0F172A !important;
    margin: 0 0 6px !important;
    letter-spacing: -0.02em !important;
    line-height: 1.2 !important;
}
.page-header p {
    font-size: 14px !important;
    color: #94A3B8 !important;
    margin: 0 !important;
}
.page-header p b {
    color: #475569 !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Section label  */
/* ════════════════════════════════════════════════════════════════════════════ */
.section-label {
    font-size: 11px;
    font-weight: 600;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 0 0 14px;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  KPI card  */
/* ════════════════════════════════════════════════════════════════════════════ */
.kpi-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 22px 22px 18px;
    height: 100%;
    box-shadow: 0 1px 3px rgba(15,23,42,.03), 0 4px 12px rgba(15,23,42,.02);
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.kpi-card:hover {
    box-shadow: 0 4px 6px rgba(15,23,42,.04), 0 10px 20px rgba(15,23,42,.03);
    transform: translateY(-1px);
}
.kpi-card .kpi-icon {
    font-size: 18px;
    color: #CBD5E1;
    margin-bottom: 14px;
    display: block;
}
.kpi-card .kpi-label {
    font-size: 11px;
    font-weight: 600;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 8px;
}
.kpi-card .kpi-value {
    font-size: 36px;
    font-weight: 700;
    color: #0F172A;
    line-height: 1;
    letter-spacing: -0.03em;
    margin-bottom: 8px;
}
.kpi-card .kpi-sub {
    font-size: 12px;
    color: #94A3B8;
    line-height: 1.4;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Generic card  */
/* ════════════════════════════════════════════════════════════════════════════ */
.card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 22px 26px;
    box-shadow: 0 1px 3px rgba(15,23,42,.03);
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Quality badges  */
/* ════════════════════════════════════════════════════════════════════════════ */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.01em;
}
.q-A { background: #ECFDF5; color: #059669; border: 1px solid #A7F3D0; }
.q-B { background: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; }
.q-C { background: #FFFBEB; color: #D97706; border: 1px solid #FDE68A; }
.q-D { background: #FEF2F2; color: #DC2626; border: 1px solid #FECACA; }

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Rule cards  */
/* ════════════════════════════════════════════════════════════════════════════ */
.rule-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 3px solid #CBD5E1;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    box-shadow: 0 1px 2px rgba(15,23,42,.03);
    transition: box-shadow 0.15s ease;
}
.rule-card:hover {
    box-shadow: 0 2px 8px rgba(15,23,42,.05);
}
.rule-card.high   { border-left-color: #EF4444; }
.rule-card.medium { border-left-color: #F59E0B; }
.rule-card.low    { border-left-color: #10B981; }
.rule-card .rule-name { font-size: 14px; font-weight: 600; color: #0F172A; margin-bottom: 4px; }
.rule-card .rule-desc { font-size: 13px; color: #64748B; line-height: 1.6; }

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Buttons  */
/* ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stBaseButton-primary"],
.stButton > button[kind="primary"] {
    background: #3B82F6 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    letter-spacing: 0.01em !important;
    box-shadow: 0 1px 2px rgba(59,130,246,.2) !important;
    transition: all 0.15s ease !important;
}
[data-testid="stBaseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover {
    background: #2563EB !important;
    box-shadow: 0 4px 12px rgba(59,130,246,.25) !important;
    transform: translateY(-1px);
}

[data-testid="stBaseButton-secondary"],
.stButton > button:not([kind="primary"]) {
    background: #FFFFFF !important;
    color: #1E293B !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    box-shadow: 0 1px 2px rgba(15,23,42,.03) !important;
    transition: all 0.15s ease !important;
}
[data-testid="stBaseButton-secondary"]:hover,
.stButton > button:not([kind="primary"]):hover {
    background: #F8FAFC !important;
    border-color: #CBD5E1 !important;
    box-shadow: 0 2px 4px rgba(15,23,42,.04) !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Tabs  */
/* ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid #E2E8F0 !important;
    gap: 0 !important;
    background: transparent !important;
    display: flex !important;
    justify-content: space-evenly !important;
}
[data-testid="stTabs"] [role="tab"] {
    font-size: 15px !important;
    font-weight: 500 !important;
    color: #94A3B8 !important;
    padding: 12px 32px !important;
    border-radius: 0 !important;
    border-bottom: 2.5px solid transparent !important;
    background: transparent !important;
    transition: all 0.15s ease !important;
    flex: 1 !important;
    text-align: center !important;
    justify-content: center !important;
    position: relative !important;
}
[data-testid="stTabs"] [role="tab"]:not(:last-child)::after {
    content: "" !important;
    position: absolute !important;
    right: 0 !important;
    top: 20% !important;
    height: 60% !important;
    width: 1px !important;
    background: #E2E8F0 !important;
}
[data-testid="stTabs"] [role="tab"]:hover {
    color: #64748B !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #3B82F6 !important;
    border-bottom-color: #3B82F6 !important;
    font-weight: 600 !important;
}
[data-testid="stTabContent"] {
    padding-top: 20px !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Expander  */
/* ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stExpander"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px rgba(15,23,42,.03) !important;
    margin-bottom: 8px !important;
    background: #FFFFFF !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    font-size: 14px !important;
    font-weight: 500 !important;
    color: #1E293B !important;
    padding: 12px 18px !important;
}
[data-testid="stExpander"] summary:hover {
    background: #F8FAFC !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Dataframe  */
/* ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stDataFrame"] {
    background: #FFFFFF;
    border-radius: 12px;
    border: 1px solid #E2E8F0;
    overflow: hidden;
}
[data-testid="stDataFrame"] thead th {
    background: #F8FAFC !important;
    color: #64748B !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    border-bottom: 1px solid #E2E8F0 !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Inputs  */
/* ════════════════════════════════════════════════════════════════════════════ */
[data-baseweb="input"] > div {
    border-color: #E2E8F0 !important;
    border-radius: 10px !important;
    background: #FFFFFF !important;
}
[data-baseweb="input"] > div:focus-within {
    border-color: #3B82F6 !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,.08) !important;
}
[data-baseweb="select"] > div {
    border-color: #E2E8F0 !important;
    border-radius: 10px !important;
    background: #FFFFFF !important;
}
[data-baseweb="select"] > div:focus-within {
    border-color: #3B82F6 !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,.08) !important;
}
.stTextInput label, .stSelectbox label, .stMultiSelect label {
    font-size: 11px !important;
    font-weight: 600 !important;
    color: #94A3B8 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  File uploader  */
/* ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stFileUploader"] {
    background: #F8FAFC !important;
    border: 1.5px dashed #CBD5E1 !important;
    border-radius: 10px !important;
    transition: border-color 0.15s ease !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: #94A3B8 !important;
}
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] p,
[data-testid="stFileUploaderDropzone"] span {
    display: none !important;
}
[data-testid="stFileUploaderDropzone"] {
    text-align: center !important;
}
[data-testid="stFileUploaderDropzone"] button {
    margin: 0 auto !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Divider  */
/* ════════════════════════════════════════════════════════════════════════════ */
hr { border-color: #E2E8F0 !important; margin: 28px 0 !important; }

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Alerts  */
/* ════════════════════════════════════════════════════════════════════════════ */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    font-size: 14px !important;
    border-width: 1px !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Progress bar  */
/* ════════════════════════════════════════════════════════════════════════════ */
.stProgress > div > div {
    background: #3B82F6 !important;
    border-radius: 6px !important;
}

/* ════════════════════════════════════════════════════════════════════════════ */
/*  Misc  */
/* ════════════════════════════════════════════════════════════════════════════ */
footer, #MainMenu { display: none !important; }
header[data-testid="stHeader"] { background: transparent !important; box-shadow: none !important; }
[data-testid="stSpinner"] > div { border-top-color: #3B82F6 !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
</style>
"""
