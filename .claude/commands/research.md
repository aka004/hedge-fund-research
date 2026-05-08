---
description: Run the multi-agent equity research orchestrator for a ticker. Produces a 21-section investment memo with citations, verification, and decision-rule gates.
argument-hint: <TICKER>
---

You are the orchestrator for the multi-agent equity research system. The user has invoked `/research $ARGUMENTS`. The argument is the stock ticker.

## Step 0 — Set up the working directory

1. Determine `TICKER = $ARGUMENTS` (uppercase it).
2. Determine `RUN_DATE = today in YYYY-MM-DD format`.
3. Determine `WORKING_DIR = output/research/<TICKER>/<RUN_DATE>/`.
4. Create the directory and a `sections/` subdirectory inside it. Use Bash:
   ```
   mkdir -p output/research/<TICKER>/<RUN_DATE>/sections
   ```
5. Create an empty `run_log.jsonl` file (the audit trail). You will append to it after each subagent invocation.

## Step 1 — Skeleton gather (foreground, blocking)

Dispatch ONE subagent: `research-skeleton-gatherer`. Prompt it with the ticker and the absolute working directory path. Wait for it to complete.

After it finishes:
- Confirm `<WORKING_DIR>/coverage_core.json` exists and parses as valid JSON.
- Append a line to `run_log.jsonl` with `{agent, started_at, ended_at, exit_status, output_files}`.

If `coverage_core.json` is missing or invalid, retry the subagent ONCE. If still missing, log the failure, stop here, and tell the user the run failed with a pointer to `run_log.jsonl`.

## Step 2 — Fan out the four section writers (parallel)

Dispatch FOUR subagents in a SINGLE message — all four `Agent` tool calls in one message so they run in parallel. Each is a `research-section-writer` instance with one of these payloads:

- `cluster_name="A"`, sections=[2, 3, 4, 5, 6, 7] — Market & Demand
- `cluster_name="B"`, sections=[8, 9, 10, 11] — Revenue & Economics
- `cluster_name="C"`, sections=[12, 13, 17, 18, 19] — Financials & Risk
- `cluster_name="D"`, sections=[14, 15, 16, 20] — Differentiation & Valuation

Pass each writer the ticker, the working directory, its cluster letter, its section list, and the path to `coverage_core.json`.

After all four return:
- Confirm `<WORKING_DIR>/sections/<X>.md` and `<WORKING_DIR>/coverage_<X>.json` exist for each X in {A, B, C, D}.
- For any cluster whose files are missing, retry that single writer ONCE. If still missing, note it for the degradation banner — do NOT abort.
- Append one `run_log.jsonl` line per writer.

## Step 3 — Merge coverage and run validator (Bash, deterministic)

Run:
```
python scripts/merge_coverage.py <WORKING_DIR>
```

Confirm exit 0. Confirm `<WORKING_DIR>/coverage_log.json` and `<WORKING_DIR>/coverage_validator.json` exist.

Read `coverage_validator.json`. If any rule has `status: FAIL`, mark a degradation banner for the synthesizer ("Coverage gate failed: <which rules>"). Do NOT abort — continue.

Append a `run_log.jsonl` line for the merge step.

## Step 4 — Verifier (foreground, blocking)

Dispatch ONE `research-verifier` subagent. Pass it the working directory. Wait for completion.

Confirm `verification_report.json` exists. If not, retry once; if still missing, mark a banner ("Verification pass did not complete").

Append a `run_log.jsonl` line.

## Step 5 — Synthesizer (foreground, blocking)

Dispatch ONE `research-synthesizer` subagent. Pass it the ticker and the working directory. Wait for completion.

Confirm `memo.md` and `appendix.md` exist. If `memo.md` is missing, retry once; if still missing, the run has failed — surface the failure with a pointer to `run_log.jsonl`.

Append a `run_log.jsonl` line.

## Step 6 — Structural validation (Bash, deterministic)

Run:
```
python scripts/validate_memo.py <WORKING_DIR>
```

If the script exits non-zero, the memo is structurally malformed. Tell the user clearly which structural check failed and that the memo is not spec-compliant.

## Step 7 — Print summary

Tell the user:
- Path to `<WORKING_DIR>/memo.md`
- Total source count (rows in `coverage_log.json`)
- Validator pass/fail line count
- % of Fact paragraphs that were VERIFIED vs UNSUPPORTED (from `verification_report.json`)
- Final rating (extract the gate header line from `memo.md`)
- Which gates passed/failed
- Wall-clock duration per subagent (from `run_log.jsonl`)

Do not embed the memo in your response — just point to the file.

## Operating rules

- The orchestrator contains NO analyst logic. All analysis is in the subagent definitions and in the `research/` Python modules. If you find yourself reasoning about a company, you are doing the wrong thing — dispatch a subagent.
- Step 2 MUST dispatch all four writers in a single message. Sequential dispatch defeats the speed goal of this design.
- Steps 3 and 6 MUST go through the Bash tool to the deterministic Python scripts. Do not have an LLM perform the merge or the structural validation.
