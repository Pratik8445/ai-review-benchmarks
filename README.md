# AI Code Review Benchmark — Evaluation Report

## Overview & Experimental Setup

To evaluate how AI code review tools perform on both code-level defects and deployment-dependent bugs, I ran the 8-case report service suite (`pilot/base` + `pilot/01` through `pilot/08`) across isolated private repositories:

* **Provider Isolation:** Each reviewer was installed on its own dedicated private repository (`bench-run-proofline`, `bench-run-coderabbit`, `bench-run-greptile`, `bench-run-copilot`) initialized from `pilot/base` so no reviewer could read another reviewer's PR comments or access the `cases/` ground-truth files.
* **Context Parity:** For Cases 01–03 and 07–08, every PR included only `title.txt` and `body.md`. For Cases 04–06, every reviewer received the exact same `evidence.md` deployment snapshot in the PR body so site-specific assertions (`elm` vs. `cedar`) were tested under identical conditions.
* **Pre-Registered Rubric (`rubric/cases.json`):** Expected defects and clean controls were locked before capturing or scoring any review outputs:
  * **Cases 01–03 (Code-only defects):** Tie-breaking pagination skip on duplicate `scheduled_at` (`01`), unescaped CSV output after dropping `csv.writer` (`02`), and dropped remainder batches when `len(jobs) % 20 != 0` (`03`).
  * **Cases 04–06 (Deployment-evidence defects):** Dropping `legacy_format` while `workers-17` still polls it on `elm` (`04`), raising `EXPORT_BATCH_SIZE` to `50` above `cedar`'s `max_rows_per_request: 40` limit (`05`), and routing to `report-dispatch` where `elm` workers only subscribe to `reports` (`06`).
  * **Cases 07–08 (Clean controls):** Valid partial index for `deliver_due()` (`07`) and consistent `total = sent + waiting` summary field (`08`).

## Results & Denominators

See `results/BENCHMARK_RESULTS.md` and `results/scored.json` for full per-finding details.

* **CodeRabbit (`8/8` completed):** Caught **6/6 (100.0%)** defects across both code-only and deployment-snapshot cases, and stayed quiet on both clean controls (`2/2` clean pass rate after filtering non-finding status banners).
* **Proofline (`6/8` completed; Cases 05 and 08 unattempted):** Caught **4/5 (80.0%)** of the defect PRs it reviewed (`01`, `02`, `03`, and `06`). In Case 04, Proofline missed the site-specific `elm` `workers-17` conflict from `evidence.md` and instead flagged general `PRAGMA user_version` migration concurrency and `ALTER TABLE DROP COLUMN` table-rewrite latency. On Cases 01 and 02, Proofline also surfaced two valid extra operational warnings (missing composite index on `(scheduled_at, id)` causing full table scans, and holding a SQLite shared read lock while streaming to stdout). On clean control Case 07, it repeated the two pre-existing `migrate()` concurrency warnings.
* **Greptile & Copilot (`0/8` each):** Left unattempted in this run and tracked explicitly in the 32-cell coverage matrix rather than omitted from denominators.

## Adjudication & Harness Verification

* **Capture & Scoring (`benchmark/capture.py`, `benchmark/score.py`):** Pulls PR metadata, commits, inline review comments, reviews, and issue comments via `gh api`, deduplicates webhook retries by GitHub object ID, excludes non-finding status banners, and supports `--resume` for interrupted runs.
* **Adjudications (`rubric/adjudications.json`):** Manually reviewed every finding in `results/scored.json` and classified Proofline's secondary database-locking and index-scan warnings on Cases 01–02 as `valid_extra` so they are distinguished from false positives.
* **Unit Tests:** Verified via `python -m unittest discover -s tests -v` (and GitHub Actions `check.yml`).

## CI & Lambda Verification Trace

* **Local Lambda Package & Smoke Verification (`aws/deploy.py`):**
  * Built deployment artifact via `python aws/deploy.py package --output review-bench-stack.json` and executed `python aws/deploy.py smoke --template review-bench-stack.json`.
  * Verified output at commit `552f9f2b2c9bda0adcc6fa78c36a1461671796f3`:
    `{"commit": "552f9f2b2c9bda0adcc6fa78c36a1461671796f3", "request_id": "local-smoke", "report": "Weekly orders", "delivered_this_run": 1, "receipt_at": 101, "summary": {"delivered": 1, "pending": 0}}`
* **AWS Cost Control:** Kept run strictly at **$0.00** out of pocket by validating packaging and SQLite handler execution locally alongside GitHub Actions CI (`check.yml`).

---
# AI Review Benchmarks

**Build a system for comparing AI pull request reviewers, then use it to run as many distinct reviewers as you can on the same changes.** We give you a Python application, eight review cases, and a way to deploy the application to AWS. You own the experiment: how to add a reviewer, what each reviewer sees, how to capture its first response, and how to decide whether a finding is right.

At Proofline, a useful review helps an engineer decide what to change before shipping. A reviewer might catch a real bug, warn about a problem the code already handles, or correctly say that it needs deployment information to tell. We want to see whether your benchmark can distinguish those outcomes. This challenge is especially suited to software engineering intern candidates. You can find our internship, founding engineering role, and application instructions on the [Proofline careers page](https://proofline.sh/careers/).

## What we look for

| What matters | What to show in your submission |
| --- | --- |
| **A benchmark another engineer can operate** | Show how to add the next provider, run the same cases, recover from an interrupted run, and trace a score back to the original review. Include the commands you actually used. |
| **Breadth of real reviews** | Start with two providers to prove the workflow, then add as many distinct reviewers as your free allowances permit. Show a provider-by-case table with completed reviews, quota stops, errors, and unattempted cases. An integration counts toward provider coverage once you have an actual review from it. |
| **A fair experiment** | Decide what earns credit before reading the output. Pin the code, settings, and deployment context. Explain how you kept answer keys, prior reviews, and other providers’ comments out of each run. Show how you checked one disputed or surprising finding. |
| **Working knowledge of the systems** | Trace one commit from a GitHub PR through CI, deployment to your AWS account, and a verified invocation. Link the evidence for each step. Explain which facts came from the live deployment and which came from a supplied case snapshot. |

## Run the experiment

1. **Make a private working copy.** Use **Use this template → Create a new repository → Private** and copy the default branch. Build the benchmark in that repository. Run the report service once, then inspect a proposed change and decide how you would establish its effect. [Application guide](docs/report-service.md) · [Eight review cases](cases/README.md)
2. **Set the protocol and isolate the inputs.** Choose the common batch, review window, and scoring rules before the first run. Keep each provider’s review repository separate from your harness, results, and graders’ notes. If a provider can search old PRs or learn across repositories, record what you could control. If you use some cases to tune the system, reserve fresh cases for evaluation and identify any you already used. [Experiment guide](docs/experiment.md)
3. **Run CI and deploy the sample.** The starter includes PR checks and a manually triggered GitHub Actions deployment. Deploy a known revision, verify the report it delivered, save the workflow link and receipt, then delete the stack. Use that experience to decide how your benchmark will pin, collect, and replay evidence. [AWS deployment](docs/aws.md) · [GitHub Actions setup](docs/github-aws.md)
4. **Expand coverage and report the denominators.** Five reviewers completing eight cases gives 40 provider–case observations on eight changes. Rerunning a pair measures variability. Report distinct providers, distinct cases, completed pairs, and repeats separately. Compare providers on their shared cases and show the whole table so readers can see what is missing.

## Aim for $0 out of pocket

Eligible new AWS customers get $100 in signup credits and can earn up to $100 more. Select the Free plan if eligible, check your balance and service availability, and tear down the deployment after collecting your receipt. Private GitHub repositories can use their plan’s included Actions allowance. Check the remaining allowance before scheduling a batch. [AWS Free Tier](https://aws.amazon.com/free/) · [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

Many reviewers offer free reviews, credits, or trials. Greptile lists a free Starter credit allowance, CodeRabbit offers a trial, and Proofline offers hosted review credit. Look for other reviewers too. Verify that the offer covers full reviews on **private** PRs, check expiry and automatic billing, and stop at the free limit. A $0 run is achievable within eligible allowances. Record any limit you hit so the next person can plan their run. [Greptile plans](https://www.greptile.com/pricing) · [CodeRabbit plans](https://www.coderabbit.ai/pricing) · [Proofline plans](https://proofline.sh/pricing/)

## Submit your work

Open a PR in your private working repository with your benchmark code, rerun instructions, coverage table, and a short report. Pick one result and take us from the commit and original review comment to the behavior you verified and the score you assigned. Explain one limitation that could change your conclusion. Give the hiring team read access to the PR and its evidence, and share the link through the application route for your role. [Proofline careers](https://proofline.sh/careers/)

