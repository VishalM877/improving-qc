"""
biomarker-qc.py
---------------
Standalone QC module for biomarker TSV files.

Checks performed:
  1. Required-field completeness per row
  2. Condition name consistency (TSV name vs. condition_id namespace)
  3. Assessed-biomarker-entity name consistency (TSV name vs. entity_id namespace)
  4. Evidence-source format
  5. Duplicate row detection

Usage:
    python biomarker-qc.py oncomx.tsv
    python biomarker-qc.py oncomx.tsv --report qc_report.txt
"""

import csv
import sys
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fields that must be non-empty on every row
REQUIRED_FIELDS: list[str] = [
    "biomarker_id",
    "biomarker",
    "assessed_biomarker_entity",
    "assessed_biomarker_entity_id",
    "assessed_entity_type",
    "best_biomarker_role",
    "evidence_source",
    "evidence",
]

# Each evidence_source should look like  DATABASE:ACCESSION  (e.g. PubMed:12345678)
EVIDENCE_SOURCE_DELIMITER = ":"


# ---------------------------------------------------------------------------
# Issue collector
# ---------------------------------------------------------------------------

class QCReport:
    def __init__(self) -> None:
        self.issues: list[dict] = []

    def add(self, level: str, row: int | None, field: str | None, message: str) -> None:
        self.issues.append({
            "level": level,        # "ERROR" | "WARNING" | "INFO"
            "row": row,
            "field": field,
            "message": message,
        })

    def error(self, message: str, row: int | None = None, field: str | None = None) -> None:
        self.add("ERROR", row, field, message)

    def warning(self, message: str, row: int | None = None, field: str | None = None) -> None:
        self.add("WARNING", row, field, message)

    def info(self, message: str, row: int | None = None, field: str | None = None) -> None:
        self.add("INFO", row, field, message)

    def print_summary(self, file=sys.stdout) -> None:
        errors   = [i for i in self.issues if i["level"] == "ERROR"]
        warnings = [i for i in self.issues if i["level"] == "WARNING"]
        infos    = [i for i in self.issues if i["level"] == "INFO"]

        print(f"\n{'='*60}", file=file)
        print(f"QC SUMMARY  —  {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info", file=file)
        print(f"{'='*60}", file=file)

        for issue in self.issues:
            loc = f"row {issue['row']}" if issue["row"] is not None else "file"
            fld = f" [{issue['field']}]" if issue["field"] else ""
            print(f"[{issue['level']}] ({loc}){fld}: {issue['message']}", file=file)

        print(f"{'='*60}\n", file=file)

    def write(self, path: Path) -> None:
        with path.open("w") as f:
            self.print_summary(file=f)


# ---------------------------------------------------------------------------
# 1. Required-field completeness
# ---------------------------------------------------------------------------

def check_required_fields(rows: list[dict], report: QCReport) -> None:
    """Flag rows where a required field is missing or blank."""
    for row_num, row in enumerate(rows, start=2):  # row 1 = header
        for field in REQUIRED_FIELDS:
            if not row.get(field, "").strip():
                report.error(
                    f"Required field '{field}' is empty.",
                    row=row_num,
                    field=field,
                )


# ---------------------------------------------------------------------------
# 2 & 3. Name-vs-ID consistency checks
#         (condition name, assessed biomarker entity name)
# ---------------------------------------------------------------------------

def check_name_id_consistency(rows: list[dict], report: QCReport) -> None:
    """Detect rows where the same ID is paired with different display names.

    Groups rows by ID and flags whenever the associated name varies — which
    almost always means a typo or stale name.

    Fields checked
    --------------
    condition_id                 → condition
    assessed_biomarker_entity_id → assessed_biomarker_entity
    exposure_agent_id            → exposure_agent
    specimen_id                  → specimen
    """
    checks = [
        ("condition_id",                  "condition"),
        ("assessed_biomarker_entity_id",  "assessed_biomarker_entity"),
        ("exposure_agent_id",             "exposure_agent"),
        ("specimen_id",                   "specimen"),
    ]

    for id_field, name_field in checks:
        id_to_names: dict[str, set[str]] = {}
        id_to_rows: dict[str, list[int]] = {}

        for row_num, row in enumerate(rows, start=2):
            id_val   = row.get(id_field, "").strip()
            name_val = row.get(name_field, "").strip()
            if not id_val:
                continue
            id_to_names.setdefault(id_val, set()).add(name_val)
            id_to_rows.setdefault(id_val, []).append(row_num)

        for id_val, names in id_to_names.items():
            if len(names) > 1:
                report.warning(
                    f"ID '{id_val}' ({id_field}) is paired with multiple "
                    f"names in '{name_field}': {sorted(names)}  "
                    f"(rows: {id_to_rows[id_val]})",
                    field=name_field,
                )


# ---------------------------------------------------------------------------
# 4. Evidence-source format
# ---------------------------------------------------------------------------

def check_evidence_sources(rows: list[dict], report: QCReport) -> None:
    """Verify evidence_source entries follow DATABASE:ACCESSION format."""
    for row_num, row in enumerate(rows, start=2):
        src = row.get("evidence_source", "").strip()
        if not src:
            continue  # already caught by required-field check
        parts = src.split(EVIDENCE_SOURCE_DELIMITER)
        if len(parts) < 2 or not parts[0].strip() or not parts[-1].strip():
            report.error(
                f"evidence_source '{src}' does not match expected "
                f"'DATABASE{EVIDENCE_SOURCE_DELIMITER}ACCESSION' format.",
                row=row_num,
                field="evidence_source",
            )


# ---------------------------------------------------------------------------
# 5. Duplicate row detection
# ---------------------------------------------------------------------------

def check_duplicates(rows: list[dict], report: QCReport) -> None:
    """Flag exact duplicate rows (ignoring leading/trailing whitespace)."""
    seen: dict[tuple, int] = {}
    for row_num, row in enumerate(rows, start=2):
        key = tuple(sorted((k, v.strip()) for k, v in row.items()))
        if key in seen:
            report.warning(
                f"Row {row_num} is an exact duplicate of row {seen[key]}.",
                row=row_num,
            )
        else:
            seen[key] = row_num


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_qc(tsv_path: Path) -> QCReport:
    report = QCReport()

    with tsv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)

    check_required_fields(rows, report)
    check_name_id_consistency(rows, report)
    check_evidence_sources(rows, report)
    check_duplicates(rows, report)

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="QC checker for biomarker TSV files."
    )
    parser.add_argument("tsv", type=Path, help="Path to the input TSV file.")
    parser.add_argument(
        "--report", type=Path, default=None,
        help="Optional path to write the QC report (plain text).",
    )
    args = parser.parse_args()

    if not args.tsv.exists():
        sys.exit(f"File not found: {args.tsv}")

    report = run_qc(args.tsv)
    report.print_summary()

    if args.report:
        report.write(args.report)
        print(f"Report written to {args.report}")

    errors = sum(1 for i in report.issues if i["level"] == "ERROR")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
