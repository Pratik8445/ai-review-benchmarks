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

FOREIGN_BOT_LOGINS = {
    "prooflinedev[bot]",
    "coderabbitai[bot]",
    "greptile-apps[bot]",
    "copilot-pull-request-reviewer[bot]",
    "github-copilot[bot]",
}


def gh_api_json(endpoint: str, paginate: bool = False) -> Any:
    """Call `gh api` (with optional pagination) and parse JSON output."""
    cmd = ["gh", "api"]
    if paginate:
        cmd.extend(["--paginate", "--slurp"])
    cmd.append(endpoint)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh api {endpoint} failed: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    if paginate and isinstance(data, list):
        flattened: list[Any] = []
        for page in data:
            if isinstance(page, list):
                flattened.extend(page)
            else:
                flattened.append(page)
        return flattened
    return data


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
    """Ignore bot status/acknowledgment replies that are not substantive findings."""
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
    provider: str = "",
) -> str:
    """Classify terminal outcome without confusing triggers or code findings with quota errors."""
    provider_events = [
        item
        for item in (all_reviews + all_inline + all_issue)
        if (item.get("user") or {}).get("login", "") in bot_logins
    ]
    if not provider_events:
        # Check if an explicit trigger comment was posted without any provider reply
        trigger_tokens = {
            "coderabbit": "@coderabbitai",
            "greptile": "@greptileai",
        }
        tok = trigger_tokens.get(provider)
        if tok and any(tok in (ic.get("body") or "").lower() for ic in all_issue):
            return "requested_no_response"
        return "unattempted"

    # Only check status banners / summary comments (not inline code findings) for quota/error notices
    status_texts = [
        (item.get("body") or "").lower()
        for item in provider_events
        if not item.get("path")
    ]
    combined_status = "\n".join(status_texts)
    if any(tok in combined_status for tok in ("quota exceeded", "rate limit exceeded", "upgrade your plan", "credits exhausted")):
        return "quota_stopped"
    if any(tok in combined_status for tok in ("internal error", "failed to review", "timed out")):
        return "error"

    # Require at least one submitted review or non-banner comment before marking completed
    has_review_submission = any(
        (r.get("user") or {}).get("login", "") in bot_logins for r in all_reviews
    )
    has_substantive_comment = any(
        not is_status_banner((item.get("body") or "")) for item in provider_events
    )
    if has_review_submission or has_substantive_comment:
        return "completed"
    return "requested_no_response"


def detect_prior_foreign_reviews(
    all_reviews: list[dict[str, Any]],
    all_inline: list[dict[str, Any]],
    bot_logins: set[str],
) -> list[str]:
    """Detect if another AI review bot posted on the PR (violating strict blind isolation)."""
    foreign = sorted(
        {
            (item.get("user") or {}).get("login", "")
            for item in (all_reviews + all_inline)
            if (item.get("user") or {}).get("login", "") in (FOREIGN_BOT_LOGINS - bot_logins)
        }
    )
    return foreign


def capture_case(
    provider_cfg: dict[str, Any],
    case_num: int,
    out_dir: Path,
    resume: bool = False,
) -> dict[str, Any]:
    """Capture one (provider, case) observation unit and write immutable snapshot + latest file."""
    case_id = f"{case_num:02d}"
    provider = provider_cfg["provider"]
    repo = provider_cfg["repo"]
    bot_logins = set(provider_cfg["bot_logins"])

    latest_file = out_dir / provider / f"case_{case_id}.json"
    if resume and latest_file.exists():
        existing = json.loads(latest_file.read_text(encoding="utf-8"))
        if existing.get("terminal_outcome") == "completed":
            return existing

    pr = gh_api_json(f"repos/{repo}/pulls/{case_num}")
    reviews = gh_api_json(f"repos/{repo}/pulls/{case_num}/reviews", paginate=True)
    inline_comments = gh_api_json(f"repos/{repo}/pulls/{case_num}/comments", paginate=True)
    issue_comments = gh_api_json(f"repos/{repo}/issues/{case_num}/comments", paginate=True)

    outcome = classify_terminal_outcome(
        reviews, inline_comments, issue_comments, bot_logins, provider=provider
    )
    findings = extract_atomic_findings(reviews, inline_comments, issue_comments, bot_logins)
    foreign_reviewers = detect_prior_foreign_reviews(reviews, inline_comments, bot_logins)
    captured_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    observation = {
        "run_id": f"{provider}-case-{case_id}-{pr['head']['sha'][:7]}-{captured_ts}",
        "provider": provider,
        "repo": repo,
        "case_id": case_id,
        "pr_number": case_num,
        "pr_url": pr["html_url"],
        "base_sha": pr["base"]["sha"],
        "head_sha": pr["head"]["sha"],
        "context_condition": "code+snapshot" if case_num in (4, 5, 6) else "code-only",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "isolation_status": "non_blind_prior_bot_visible" if foreign_reviewers else "isolated",
        "prior_foreign_reviewers": foreign_reviewers,
        "terminal_outcome": outcome,
        "findings": findings,
        "raw": {
            "reviews": reviews,
            "inline_comments": inline_comments,
            "issue_comments": issue_comments,
        },
    }

    # Write immutable timestamped snapshot plus latest pointer for scoring
    snapshot_dir = out_dir / provider / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = snapshot_dir / f"case_{case_id}_{captured_ts}.json"
    payload = json.dumps(observation, indent=2)
    snapshot_file.write_text(payload, encoding="utf-8")

    latest_file.parent.mkdir(parents=True, exist_ok=True)
    latest_file.write_text(payload, encoding="utf-8")
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
                f"outcome={obs['terminal_outcome']} isolation={obs['isolation_status']} "
                f"findings={len(obs['findings'])}"
            )


if __name__ == "__main__":
    main()
