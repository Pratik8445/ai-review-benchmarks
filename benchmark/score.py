"""Score captured AI review findings against the pre-registered ground-truth rubric."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CaseGrade:
    provider: str
    case_id: str
    terminal_outcome: str
    isolation_status: str
    has_defect: bool
    defect_caught: bool = False
    true_positives: int = 0
    false_positives: int = 0
    valid_extra_warnings: int = 0
    ambiguous_findings: int = 0
    finding_notes: list[dict[str, Any]] = field(default_factory=list)


def match_finding_to_defect(finding: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Check whether a finding identifies the target file, required terms, and defect mechanism."""
    expected_file = expected["file"]
    finding_path = finding.get("path")
    if finding_path and finding_path != expected_file:
        return False

    text = f"{finding.get('path') or ''} {finding.get('body') or ''}".lower()
    required_all = [kw.lower() for kw in expected.get("required_all", [])]
    if any(req not in text for req in required_all):
        return False

    keywords = [kw.lower() for kw in expected.get("keywords", [])]
    hits = sum(1 for kw in keywords if kw in text)
    return hits >= 2


def stable_finding_key(finding: dict[str, Any]) -> str:
    """Return a deterministic, order-independent identifier for manual adjudications."""
    return f"{finding.get('source_type')}:{finding.get('source_id')}"


def score_observation(
    obs: dict[str, Any],
    case_spec: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> CaseGrade:
    """Score one (provider, case) observation against its ground-truth specification."""
    provider = obs["provider"]
    case_id = obs["case_id"]
    outcome = obs["terminal_outcome"]
    isolation_status = obs.get("isolation_status", "isolated")
    has_defect = bool(case_spec["has_defect"])

    grade = CaseGrade(
        provider=provider,
        case_id=case_id,
        terminal_outcome=outcome,
        isolation_status=isolation_status,
        has_defect=has_defect,
    )

    if outcome != "completed":
        return grade

    override_key = f"{provider}:{case_id}"
    case_override = (overrides or {}).get(override_key, {})
    expected = case_spec.get("expected_defect")

    for idx, finding in enumerate(obs.get("findings", [])):
        fkey = stable_finding_key(finding)
        if fkey in case_override:
            label = case_override[fkey]["label"]
            reason = case_override[fkey]["reason"]
        elif has_defect and expected and match_finding_to_defect(finding, expected):
            label = "true_positive"
            reason = f"Matched ground-truth defect in {expected['file']}"
        elif not has_defect:
            label = "false_positive"
            reason = "Flagged an issue on a verified clean control PR"
        else:
            label = "false_positive"
            reason = "Did not match ground-truth defect criteria"

        if label == "true_positive":
            if not grade.defect_caught:
                grade.defect_caught = True
                grade.true_positives += 1
            else:
                label = "duplicate_tp"
        elif label == "false_positive":
            grade.false_positives += 1
        elif label == "valid_extra":
            grade.valid_extra_warnings += 1
        elif label == "ambiguous":
            grade.ambiguous_findings += 1

        grade.finding_notes.append(
            {
                "finding_index": idx,
                "finding_key": fkey,
                "source_id": finding.get("source_id"),
                "path": finding.get("path"),
                "line": finding.get("line"),
                "label": label,
                "reason": reason,
                "excerpt": (finding.get("body") or "")[:180].replace("\n", " "),
            }
        )

    return grade


def build_summary_markdown(
    grades: list[CaseGrade],
    providers: list[str],
    case_ids: list[str],
) -> str:
    """Render coverage matrix and precision/recall denominator tables in Markdown."""
    by_pair = {(g.provider, g.case_id): g for g in grades}

    lines = [
        "# Benchmark Results & Denominator Report",
        "",
        "## 1. Provider-by-Case Coverage Matrix",
        "",
        "| Provider | " + " | ".join(f"Case {c}" for c in case_ids) + " | Completed |",
        "| --- | " + " | ".join("---" for _ in case_ids) + " | --- |",
    ]

    for p in providers:
        cells = []
        completed_count = 0
        for c in case_ids:
            g = by_pair.get((p, c))
            if g is None or g.terminal_outcome in ("unattempted", "requested_no_response"):
                cells.append(g.terminal_outcome.upper() if g else "UNATTEMPTED")
            elif g.terminal_outcome != "completed":
                cells.append(g.terminal_outcome.upper())
            else:
                completed_count += 1
                if g.has_defect:
                    status = "CAUGHT (TP)" if g.defect_caught else "MISSED (FN)"
                else:
                    status = "QUIET (TN)" if g.false_positives == 0 else f"NOISE ({g.false_positives} FP)"
                if g.false_positives > 0 and g.has_defect:
                    status += f" + {g.false_positives} FP"
                if g.valid_extra_warnings > 0:
                    status += f" (+{g.valid_extra_warnings} valid_extra)"
                if g.isolation_status != "isolated":
                    status += " [non-blind]"
                cells.append(status)
        lines.append(f"| **{p}** | " + " | ".join(cells) + f" | {completed_count}/{len(case_ids)} |")

    lines.extend(
        [
            "",
            "## 2. Accuracy & Denominator Summary (Completed Reviews Only)",
            "",
            "| Provider | Completed Pairs | Strictly Isolated Pairs | Defects Caught (Recall) | Finding Precision (Strict) | Valid Extra Operational Warnings | Clean Control Pass Rate |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for p in providers:
        p_grades = [by_pair[(p, c)] for c in case_ids if (p, c) in by_pair and by_pair[(p, c)].terminal_outcome == "completed"]
        isolated_count = sum(1 for g in p_grades if g.isolation_status == "isolated")
        defect_cases = [g for g in p_grades if g.has_defect]
        clean_cases = [g for g in p_grades if not g.has_defect]

        caught = sum(1 for g in defect_cases if g.defect_caught)
        tp = sum(g.true_positives for g in p_grades)
        fp = sum(g.false_positives for g in p_grades)
        ve = sum(g.valid_extra_warnings for g in p_grades)
        clean_pass = sum(1 for g in clean_cases if g.false_positives == 0)

        recall_str = f"{caught}/{len(defect_cases)} ({(100 * caught / len(defect_cases)):.1f}%)" if defect_cases else "N/A"
        prec_denom = tp + fp
        prec_str = f"{tp}/{prec_denom} ({(100 * tp / prec_denom):.1f}%)" if prec_denom else "N/A (0 findings)"
        clean_str = f"{clean_pass}/{len(clean_cases)}" if clean_cases else "N/A"

        lines.append(
            f"| **{p}** | {len(p_grades)}/{len(case_ids)} | {isolated_count}/{len(p_grades)} | "
            f"{recall_str} | {prec_str} | {ve} | {clean_str} |"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Score captured AI review results.")
    parser.add_argument("--rubric", type=Path, default=Path("rubric/cases.json"))
    parser.add_argument("--raw-dir", type=Path, default=Path("results/raw"))
    parser.add_argument("--overrides", type=Path, default=Path("rubric/adjudications.json"))
    parser.add_argument("--report-out", type=Path, default=Path("results/BENCHMARK_RESULTS.md"))
    parser.add_argument("--json-out", type=Path, default=Path("results/scored.json"))
    args = parser.parse_args()

    rubric = json.loads(args.rubric.read_text(encoding="utf-8"))
    overrides = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides.exists() else {}
    providers = ["proofline", "coderabbit", "greptile", "copilot"]
    case_ids = [c["case_id"] for c in rubric["cases"]]

    all_grades: list[CaseGrade] = []
    for p in providers:
        for case_spec in rubric["cases"]:
            cid = case_spec["case_id"]
            obs_path = args.raw_dir / p / f"case_{cid}.json"
            if not obs_path.exists():
                continue
            obs = json.loads(obs_path.read_text(encoding="utf-8"))
            all_grades.append(score_observation(obs, case_spec, overrides=overrides))

    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(build_summary_markdown(all_grades, providers, case_ids), encoding="utf-8")
    args.json_out.write_text(
        json.dumps([g.__dict__ for g in all_grades], indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {args.report_out} and {args.json_out}")


if __name__ == "__main__":
    main()
