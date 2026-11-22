"""Capture raw PR review observations from isolated provider repositories via GitHub CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PROVIDERS = [
    {
        "provider": "proofline",
        "repo": "Pratik8445/bench-run-proofline",
        "bot_logins": ["prooflinedev[bot]"],
    },
    {
        "provider": "coderabbit",
        "repo": "Pratik8445/bench-run-coderabbit",
        "bot_logins": ["coderabbitai[bot]"],
    },
    {
        "provider": "greptile",
        "repo": "Pratik8445/bench-run-greptile",
        "bot_logins": ["greptile-apps[bot]"],
    },
    {
        "provider": "copilot",
        "repo": "Pratik8445/bench-run-copilot",
        "bot_logins": ["copilot-pull-request-reviewer[bot]", "github-copilot[bot]"],
    },
]


def gh_api_json(endpoint: str) -> Any:
    """Call `gh api` and parse JSON output."""
    proc = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh api {endpoint} failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def deduplicate_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate webhook retry deliveries by GitHub object ID while preserving order."""
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        item_id = item.get("id")
        if item_id is not None and item_id in seen:
            continue
        if item_id is not None:
            seen.add(item_id)
        unique.append(item)
    return unique


def is_status_banner(body: str) -> bool:
    """Ignore bot status/acknowledgment replies that are not review findings."""
    low = body.lower()
    if "<!-- proofline:review-comment -->" in low:
        return True
    if "<!-- coderabbit review command invocation:" in low:
        return True
    if "walkthrough" in low and "<!-- walkthrough_start -->" in low:
        return True
    return False


def extract_atomic_findings(
    reviews: list[dict[str, Any]],
    inline_comments: list[dict[str, Any]],
    issue_comments: list[dict[str, Any]],
    bot_logins: set[str],
) -> list[dict[str, Any]]:
    """Normalize provider-specific GitHub review objects into atomic findings."""
    findings: list[dict[str, Any]] = []

    for c in deduplicate_by_id(inline_comments):
        author = (c.get("user") or {}).get("login", "")
        if author not in bot_logins:
            continue
        body = (c.get("body") or "").strip()
        if not body or is_status_banner(body):
            continue
        findings.append(
            {
                "source_type": "inline_comment",
                "source_id": c.get("id"),
                "author": author,
                "path": c.get("path"),
                "line": c.get("line") or c.get("original_line"),
                "created_at": c.get("created_at"),
                "body": body,
            }
        )

    for r in deduplicate_by_id(reviews):
        author = (r.get("user") or {}).get("login", "")
        if author not in bot_logins:
            continue
        body = (r.get("body") or "").strip()
        if not body or is_status_banner(body):
            continue
        findings.append(
            {
                "source_type": "review_summary",
                "source_id": r.get("id"),
                "author": author,
                "state": r.get("state"),
                "path": None,
                "line": None,
                "created_at": r.get("submitted_at"),
                "body": body,
            }
        )

    for ic in deduplicate_by_id(issue_comments):
        author = (ic.get("user") or {}).get("login", "")
        if author not in bot_logins:
            continue
        body = (ic.get("body") or "").strip()
        if not body or is_status_banner(body):
            continue
        findings.append(
            {
                "source_type": "issue_comment",
                "source_id": ic.get("id"),
                "author": author,
                "path": None,
                "line": None,
                "created_at": ic.get("created_at"),
                "body": body,
            }
        )

    return findings


def classify_terminal_outcome(
    all_reviews: list[dict[str, Any]],
    all_inline: list[dict[str, Any]],
    all_issue: list[dict[str, Any]],
    bot_logins: set[str],
) -> str:
    """Determine whether the provider completed a review, hit a quota/error, or never ran."""
    provider_events = [
        item
        for item in (all_reviews + all_inline + all_issue)
        if (item.get("user") or {}).get("login", "") in bot_logins
    ]
    if not provider_events:
        return "unattempted"

    combined_text = "\n".join((item.get("body") or "") for item in provider_events).lower()
    if any(tok in combined_text for tok in ("quota", "rate limit", "upgrade your plan", "credits exhausted")):
        return "quota_stopped"
    if any(tok in combined_text for tok in ("internal error", "failed to review", "timed out")):
        return "error"
    return "completed"


def capture_case(
    provider_cfg: dict[str, Any],
    case_num: int,
    out_dir: Path,
    resume: bool = False,
) -> dict[str, Any]:
    """Capture one (provider, case) observation unit and write immutable JSON."""
    case_id = f"{case_num:02d}"
    provider = provider_cfg["provider"]
    repo = provider_cfg["repo"]
    bot_logins = set(provider_cfg["bot_logins"])

    target_file = out_dir / provider / f"case_{case_id}.json"
    if resume and target_file.exists():
        existing = json.loads(target_file.read_text(encoding="utf-8"))
        if existing.get("terminal_outcome") == "completed":
            return existing

    pr = gh_api_json(f"repos/{repo}/pulls/{case_num}")
    reviews = gh_api_json(f"repos/{repo}/pulls/{case_num}/reviews")
    inline_comments = gh_api_json(f"repos/{repo}/pulls/{case_num}/comments")
    issue_comments = gh_api_json(f"repos/{repo}/issues/{case_num}/comments")

    outcome = classify_terminal_outcome(reviews, inline_comments, issue_comments, bot_logins)
    findings = extract_atomic_findings(reviews, inline_comments, issue_comments, bot_logins)

    observation = {
        "run_id": f"{provider}-case-{case_id}-{pr['head']['sha'][:7]}",
        "provider": provider,
        "repo": repo,
        "case_id": case_id,
        "pr_number": case_num,
        "pr_url": pr["html_url"],
        "base_sha": pr["base"]["sha"],
        "head_sha": pr["head"]["sha"],
        "context_condition": "code+snapshot" if case_num in (4, 5, 6) else "code-only",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "terminal_outcome": outcome,
        "findings": findings,
        "raw": {
            "reviews": reviews,
            "inline_comments": inline_comments,
            "issue_comments": issue_comments,
        },
    }

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(json.dumps(observation, indent=2), encoding="utf-8")
    return observation


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture raw AI code review observations.")
    parser.add_argument("--out-dir", type=Path, default=Path("results/raw"))
    parser.add_argument("--resume", action="store_true", help="Skip already completed observations.")
    parser.add_argument("--provider", help="Capture only one named provider.")
    args = parser.parse_args()

    configs = [
        p for p in DEFAULT_PROVIDERS if args.provider is None or p["provider"] == args.provider
    ]
    for cfg in configs:
        for case_num in range(1, 9):
            obs = capture_case(cfg, case_num, args.out_dir, resume=args.resume)
            print(
                f"[{obs['provider']}] case {obs['case_id']}: "
                f"outcome={obs['terminal_outcome']} findings={len(obs['findings'])}"
            )


if __name__ == "__main__":
    main()
