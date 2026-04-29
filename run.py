"""
CLI entry point for batch operations.

Usage:
  python run.py import --dir data/raw/
  python run.py compute --months 2025-12 2026-01 2026-02 2026-03 2026-04
  python run.py audit   --months 2025-12 2026-01 ...
  python run.py score   --months 2025-12 2026-01 ...
  python run.py report  --months 2025-12 2026-01 ... --hhid XXX
  python run.py report  --months ... --all
  python run.py snapshot
  python run.py pipeline --months 2025-12 2026-01 ... --dir data/raw/
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.io.database import init_db
from src.io.importer import auto_import
from src.compute.metrics import compute_metrics, rebuild_snapshot
from src.compute.scorer import compute_scores
from src.compute.classifier import classify_all
from src.compute.auditor import run_audit
from src.report.renderer import render_visit_card, render_all_visit_cards
from src.report.exporter import export_summary


def _parse_months(month_strings: list[str]) -> list[tuple[int, int]]:
    """Parse ['2025-12', '2026-1'] into [(2025,12), (2026,1)]."""
    months = []
    for s in month_strings:
        m = re.match(r"(\d{4})-(\d{1,2})", s)
        if not m:
            raise ValueError(f"Invalid month format: {s}. Expected YYYY-MM.")
        months.append((int(m.group(1)), int(m.group(2))))
    return sorted(months)


def cmd_import(args):
    init_db()
    raw_dir = Path(args.dir)
    csv_files = list(raw_dir.glob("*.csv"))
    if not csv_files:
        print(f"[ERROR] No CSV files found in {raw_dir}")
        return

    for csv_path in sorted(csv_files):
        try:
            result = auto_import(str(csv_path))
            print(f"[OK] {csv_path.name} → {result['file_type']} · {result['row_count']} rows")
        except Exception as e:
            print(f"[ERR] {csv_path.name}: {e}")


def cmd_compute(args):
    months = _parse_months(args.months)
    n = compute_metrics(months)
    print(f"[OK] compute_metrics: {n} households")


def cmd_score(args):
    months = _parse_months(args.months)
    n1 = compute_scores(months)
    print(f"[OK] compute_scores: {n1} households")
    n2 = classify_all(months)
    print(f"[OK] classify_all: {n2} households")


def cmd_audit(args):
    months = _parse_months(args.months)
    n = run_audit(months)
    print(f"[OK] run_audit: {n} rule events")


def cmd_snapshot(_args):
    n = rebuild_snapshot()
    print(f"[OK] rebuild_snapshot: {n} records")


def cmd_report(args):
    months = _parse_months(args.months)
    if args.all:
        paths = render_all_visit_cards(months)
        print(f"[OK] Generated {len(paths)} visit cards")
    elif args.hhid:
        path = render_visit_card(args.hhid, months)
        print(f"[OK] Generated: {path}")
    else:
        print("[ERROR] Specify --hhid or --all")


def cmd_export(args):
    months = _parse_months(args.months)
    path = export_summary(months)
    print(f"[OK] Export: {path}")


def cmd_pipeline(args):
    init_db()
    months = _parse_months(args.months)
    period_str = f"{months[0][0]}-{months[0][1]:02d} ~ {months[-1][0]}-{months[-1][1]:02d}"
    print(f"[pipeline] Starting for {period_str}")
    n1 = compute_metrics(months)
    print(f"[1/5] compute_metrics: {n1}")
    n2 = compute_scores(months)
    print(f"[2/5] compute_scores: {n2}")
    n3 = classify_all(months)
    print(f"[3/5] classify_all: {n3}")
    n4 = run_audit(months)
    print(f"[4/5] run_audit: {n4}")
    n5 = rebuild_snapshot()
    print(f"[5/5] rebuild_snapshot: {n5}")
    print("[pipeline] Done.")


def main():
    parser = argparse.ArgumentParser(description="记账户画像系统 CLI")
    sub = parser.add_subparsers(dest="command")

    # import
    p_import = sub.add_parser("import", help="导入 CSV 文件")
    p_import.add_argument("--dir", default="data/raw/")

    # compute
    p_compute = sub.add_parser("compute", help="计算收支指标")
    p_compute.add_argument("--months", nargs="+", required=True)

    # score
    p_score = sub.add_parser("score", help="计算评分与标签")
    p_score.add_argument("--months", nargs="+", required=True)

    # audit
    p_audit = sub.add_parser("audit", help="执行审核规则")
    p_audit.add_argument("--months", nargs="+", required=True)

    # export
    p_export = sub.add_parser("export", help="导出 Excel 汇总")
    p_export.add_argument("--months", nargs="+", required=True)

    # snapshot
    sub.add_parser("snapshot", help="重建当前快照")

    # report
    p_report = sub.add_parser("report", help="生成访户核对单")
    p_report.add_argument("--months", nargs="+", required=True)
    p_report.add_argument("--hhid", default=None)
    p_report.add_argument("--all", action="store_true")

    # pipeline
    p_pipe = sub.add_parser("pipeline", help="完整流水线 import→compute→score→audit→snapshot")
    p_pipe.add_argument("--months", nargs="+", required=True)
    p_pipe.add_argument("--dir", default="data/raw/")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    dispatch = {
        "import": cmd_import,
        "compute": cmd_compute,
        "score": cmd_score,
        "audit": cmd_audit,
        "export": cmd_export,
        "snapshot": cmd_snapshot,
        "report": cmd_report,
        "pipeline": cmd_pipeline,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
