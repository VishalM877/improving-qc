"""
enhanced_biomarker_qc.py
------------------------
Standalone QC module for biomarker TSV files.

This version keeps the original checks and adds the Week 3-6 curation checks:
missing directionality, missing evidence, conflicting values inside a biomarker
group, accession/entity/type mismatches, likely biomarker typos, and cross-field
biomarker/entity disagreements.
"""

from __future__ import print_function

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path


REQUIRED_FIELDS = [
    "biomarker_id",
    "biomarker",
    "assessed_biomarker_entity",
    "assessed_biomarker_entity_id",
    "assessed_entity_type",
    "best_biomarker_role",
    "evidence_source",
    "evidence",
]

EVIDENCE_SOURCE_DELIMITER = ":"

DIRECTIONAL_TERMS = {
    "increased",
    "increase",
    "elevated",
    "high",
    "higher",
    "upregulated",
    "up-regulated",
    "decreased",
    "decrease",
    "reduced",
    "low",
    "lower",
    "downregulated",
    "down-regulated",
    "presence",
    "present",
    "absence",
    "absent",
    "differential",
    "methylation",
    "mutation",
}

TYPE_BY_PREFIX = {
    "UPKB": "protein",
    "PRO": "protein complex",
    "CO": "cell",
    "CL": "cell",
    "CHEBI": "metabolite",
    "GTC": "glycan",
    "MRB": "RNA",
    "RNAC": "RNA",
}

# Targeted accession labels for known high-value rows in this curation batch.
# These allow the script to catch cross-field copy/paste errors without trying
# to query external vocabularies at runtime.
KNOWN_ACCESSION_SYMBOLS = {
    "NCBI:3569": "IL6",
    "NCBI:3082": "HGF",
    "UPKB:P05231": "IL6",
    "UPKB:P0DJI8": "SAA1",
    "NCBI:6288": "SAA1",
    "CO:CL_0000542": "LYMP",
    "CO:CL_0000233": "PLAT",
}

LIKELY_BIOMARKER_TYPOS = {
    "LMYP": "LYMP",
    "TNFΑ": "TNF-alpha",
    "TNF-Α": "TNF-alpha",
}


class QCReport(object):
    def __init__(self):
        self.issues = []

    def add(self, level, category, row, field, current_value, message, proposed_value=""):
        self.issues.append(
            {
                "level": level,
                "category": category,
                "row": row,
                "field": field,
                "current_value": current_value,
                "proposed_value": proposed_value,
                "message": message,
            }
        )

    def error(self, category, message, row=None, field=None, current_value="", proposed_value=""):
        self.add("ERROR", category, row, field, current_value, message, proposed_value)

    def warning(self, category, message, row=None, field=None, current_value="", proposed_value=""):
        self.add("WARNING", category, row, field, current_value, message, proposed_value)

    def info(self, category, message, row=None, field=None, current_value="", proposed_value=""):
        self.add("INFO", category, row, field, current_value, message, proposed_value)

    def print_summary(self, file=sys.stdout):
        counts = defaultdict(int)
        for issue in self.issues:
            counts[issue["level"]] += 1

        print("", file=file)
        print("=" * 80, file=file)
        print(
            "QC SUMMARY - {0} errors, {1} warnings, {2} info".format(
                counts["ERROR"], counts["WARNING"], counts["INFO"]
            ),
            file=file,
        )
        print("=" * 80, file=file)

        for issue in self.issues:
            loc = "row {0}".format(issue["row"]) if issue["row"] is not None else "file"
            field = " [{0}]".format(issue["field"]) if issue["field"] else ""
            proposed = (
                " Proposed: {0}".format(issue["proposed_value"])
                if issue.get("proposed_value")
                else ""
            )
            print(
                "[{0}] {1} ({2}){3}: {4}{5}".format(
                    issue["level"],
                    issue["category"],
                    loc,
                    field,
                    issue["message"],
                    proposed,
                ),
                file=file,
            )
        print("=" * 80, file=file)

    def write_text(self, path):
        with path.open("w", encoding="utf-8") as handle:
            self.print_summary(file=handle)

    def write_csv(self, path):
        fields = [
            "level",
            "category",
            "row",
            "field",
            "current_value",
            "proposed_value",
            "message",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for issue in self.issues:
                writer.writerow(issue)


def clean(value):
    return (value or "").strip()


def row_number(index):
    return index + 2


def normalize_token(value):
    value = clean(value).upper()
    value = value.replace("Α", "A")
    value = value.replace("Α", "A")
    value = value.replace("Β", "B")
    value = value.replace(" ", "")
    return re.sub(r"[^A-Z0-9]+", "", value)


def biomarker_head(value):
    text = clean(value)
    words = text.split()
    if words and words[0].lower() in DIRECTIONAL_TERMS:
        words = words[1:]
    if not words:
        return ""
    if words[0].lower() in {"copy", "number"}:
        match = re.search(r"\bof\s+([A-Za-z0-9+\-αΑβΒ]+)", text)
        if match:
            return normalize_token(match.group(1))
    return normalize_token(words[0])


def has_directionality(row):
    biomarker = clean(row.get("biomarker"))
    vocab_pattern = clean(row.get("vocab_pattern")).lower()
    controlled = clean(row.get("biomarker_controlled_vocab")).lower()
    first_word = biomarker.split()[0].lower() if biomarker.split() else ""
    return (
        first_word in DIRECTIONAL_TERMS
        or "change_type:" in vocab_pattern
        or controlled.startswith(("increased ", "decreased ", "presence ", "differential "))
    )


def check_required_fields(rows, report):
    for index, row in enumerate(rows):
        for field in REQUIRED_FIELDS:
            if not clean(row.get(field)):
                report.error(
                    "required_field",
                    "Required field '{0}' is empty.".format(field),
                    row=row_number(index),
                    field=field,
                    current_value="",
                )


def check_name_id_consistency(rows, report):
    checks = [
        ("condition_id", "condition"),
        ("assessed_biomarker_entity_id", "assessed_biomarker_entity"),
        ("exposure_agent_id", "exposure_agent"),
        ("specimen_id", "specimen"),
    ]

    for id_field, name_field in checks:
        grouped = defaultdict(lambda: defaultdict(list))
        for index, row in enumerate(rows):
            id_value = clean(row.get(id_field))
            name_value = clean(row.get(name_field))
            if id_value:
                grouped[id_value][name_value].append(row_number(index))

        for id_value, names in grouped.items():
            if len(names) <= 1:
                continue
            summary = "; ".join(
                "{0}: rows {1}".format(name or "<blank>", row_list[:12])
                for name, row_list in sorted(names.items())
            )
            for name, row_list in names.items():
                for row_num in row_list:
                    report.warning(
                        "name_id_consistency",
                        "{0} '{1}' is paired with multiple {2} values: {3}".format(
                            id_field, id_value, name_field, summary
                        ),
                        row=row_num,
                        field=name_field,
                        current_value=name,
                    )


def check_evidence_sources(rows, report):
    for index, row in enumerate(rows):
        src = clean(row.get("evidence_source"))
        if not src:
            continue
        parts = src.split(EVIDENCE_SOURCE_DELIMITER)
        if len(parts) < 2 or not parts[0].strip() or not parts[-1].strip():
            report.error(
                "evidence_source_format",
                "evidence_source does not match expected DATABASE:ACCESSION format.",
                row=row_number(index),
                field="evidence_source",
                current_value=src,
            )


def check_duplicates(rows, report):
    seen = {}
    for index, row in enumerate(rows):
        key = tuple(sorted((key, clean(value)) for key, value in row.items()))
        if key in seen:
            report.warning(
                "duplicate_row",
                "Exact duplicate of row {0}.".format(seen[key]),
                row=row_number(index),
            )
        else:
            seen[key] = row_number(index)


def check_group_conflicts(rows, report):
    keys = ["biomarker_id", "component_group"]
    fields = [
        "biomarker",
        "assessed_biomarker_entity",
        "assessed_biomarker_entity_id",
        "assessed_entity_type",
        "best_biomarker_role",
        "specimen",
        "specimen_id",
        "biomarker_controlled_vocab",
    ]

    seen_conflicts = set()

    for key_field in keys:
        if key_field not in rows[0]:
            continue
        grouped = defaultdict(list)
        for index, row in enumerate(rows):
            key = clean(row.get(key_field))
            if key:
                grouped[key].append((row_number(index), row))

        for key, members in grouped.items():
            if len(members) <= 1:
                continue
            for field in fields:
                values = defaultdict(list)
                for row_num, row in members:
                    values[clean(row.get(field))].append(row_num)
                non_blank_values = {value: nums for value, nums in values.items() if value}
                if len(non_blank_values) <= 1:
                    continue
                conflict_signature = (
                    field,
                    tuple(row_num for row_num, _row in members),
                    tuple(
                        (value, tuple(nums))
                        for value, nums in sorted(non_blank_values.items())
                    ),
                )
                if conflict_signature in seen_conflicts:
                    continue
                seen_conflicts.add(conflict_signature)
                summary = "; ".join(
                    "{0}: rows {1}".format(value, nums[:12])
                    for value, nums in sorted(non_blank_values.items())
                )
                for value, nums in non_blank_values.items():
                    for row_num in nums:
                        report.warning(
                            "group_conflict",
                            "{0} '{1}' has conflicting {2} values: {3}".format(
                                key_field, key, field, summary
                            ),
                            row=row_num,
                            field=field,
                            current_value=value,
                        )


def check_missing_directionality(rows, report):
    for index, row in enumerate(rows):
        if has_directionality(row):
            continue
        report.warning(
            "missing_directionality",
            "Biomarker lacks explicit directionality/change_type; infer from verified evidence before correcting.",
            row=row_number(index),
            field="biomarker",
            current_value=clean(row.get("biomarker")),
            proposed_value="needs evidence review",
        )


def check_likely_typos(rows, report):
    for index, row in enumerate(rows):
        biomarker = clean(row.get("biomarker"))
        normalized = normalize_token(biomarker)
        for typo, correction in LIKELY_BIOMARKER_TYPOS.items():
            if typo in normalized:
                report.warning(
                    "likely_biomarker_typo",
                    "Biomarker appears to contain likely typo '{0}'.".format(typo),
                    row=row_number(index),
                    field="biomarker",
                    current_value=biomarker,
                    proposed_value=biomarker.replace(typo, correction),
                )


def check_accession_type(rows, report):
    for index, row in enumerate(rows):
        accession = clean(row.get("assessed_biomarker_entity_id"))
        entity_type = clean(row.get("assessed_entity_type")).lower()
        if ":" not in accession:
            continue
        prefix = accession.split(":", 1)[0]
        expected = TYPE_BY_PREFIX.get(prefix)
        if not expected:
            continue
        ok = entity_type == expected or (
            expected == "RNA" and entity_type in {"rna", "mrna", "mirna"}
        )
        if not ok:
            report.warning(
                "accession_type_mismatch",
                "Accession prefix '{0}' usually maps to assessed_entity_type '{1}'.".format(
                    prefix, expected
                ),
                row=row_number(index),
                field="assessed_entity_type",
                current_value=clean(row.get("assessed_entity_type")),
                proposed_value=expected,
            )


def check_cross_field_entity_agreement(rows, report):
    for index, row in enumerate(rows):
        row_num = row_number(index)
        biomarker = clean(row.get("biomarker"))
        entity = clean(row.get("assessed_biomarker_entity"))
        accession = clean(row.get("assessed_biomarker_entity_id"))
        controlled = clean(row.get("biomarker_controlled_vocab"))

        head = biomarker_head(biomarker)
        known_symbol = KNOWN_ACCESSION_SYMBOLS.get(accession)
        entity_norm = normalize_token(entity)
        controlled_norm = normalize_token(controlled)

        if known_symbol:
            known_norm = normalize_token(known_symbol)
            if head and head != known_norm and head not in entity_norm:
                report.warning(
                    "cross_field_mismatch",
                    "Biomarker term appears to refer to '{0}', but accession '{1}' maps to '{2}'.".format(
                        head, accession, known_symbol
                    ),
                    row=row_num,
                    field="assessed_biomarker_entity_id",
                    current_value=accession,
                    proposed_value="review accession/entity against biomarker",
                )
            if controlled and known_norm not in controlled_norm:
                report.warning(
                    "controlled_vocab_mismatch",
                    "Controlled vocabulary text does not contain the expected symbol for the accession.",
                    row=row_num,
                    field="biomarker_controlled_vocab",
                    current_value=controlled,
                    proposed_value="include {0}/{1}".format(known_symbol, accession),
                )


def check_disease_label_placeholders(rows, report):
    for index, row in enumerate(rows):
        condition = clean(row.get("condition"))
        condition_id = clean(row.get("condition_id"))
        if condition.lower() in {"disease", "cancer"} or condition_id == "DOID:4":
            report.warning(
                "generic_condition",
                "Condition is generic; review whether the source supports a more specific disease label.",
                row=row_number(index),
                field="condition",
                current_value=condition,
                proposed_value="needs curator review",
            )


def run_qc(tsv_path):
    report = QCReport()
    with tsv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)

    if not rows:
        report.error("file_format", "No rows found in TSV.")
        return report

    check_required_fields(rows, report)
    check_name_id_consistency(rows, report)
    check_evidence_sources(rows, report)
    check_duplicates(rows, report)
    check_group_conflicts(rows, report)
    check_missing_directionality(rows, report)
    check_likely_typos(rows, report)
    check_accession_type(rows, report)
    check_cross_field_entity_agreement(rows, report)
    check_disease_label_placeholders(rows, report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Enhanced QC checker for biomarker TSV files.")
    parser.add_argument("tsv", type=Path, help="Path to input TSV file.")
    parser.add_argument("--report", type=Path, default=None, help="Optional text report path.")
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV issue log path.")
    args = parser.parse_args()

    if not args.tsv.exists():
        sys.exit("File not found: {0}".format(args.tsv))

    report = run_qc(args.tsv)
    report.print_summary()
    if args.report:
        report.write_text(args.report)
    if args.csv:
        report.write_csv(args.csv)

    errors = sum(1 for issue in report.issues if issue["level"] == "ERROR")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
