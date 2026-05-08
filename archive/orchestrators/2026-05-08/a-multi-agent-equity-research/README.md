# Orchestrator A — Multi-Agent Equity Research (archived)

**Active:** 2026-01 → 2026-02-06
**Archived:** 2026-05-08

## What it was

Multi-Agent Equity Research Orchestrator v6 — an Anthropic-SDK-driven Python orchestrator that produced an investment memo for a single ticker by dispatching role-specialised agents in four phases:

- **Phase 1 — Data Collection:** `01-DATA-AGENT` populates `data_corpus.json` (the source of truth).
- **Phase 2 — Analysis:** `02-QUANT-AGENT`, `03-RISK-AGENT`, `04-COMPETITIVE-AGENT`, `05-QUALITATIVE-AGENT` produce per-domain JSON.
- **Phase 3 — Verification:** quant-verifier / risk-verifier / moat-verifier cross-check claims against `data_corpus`.
- **Phase 4 — Synthesis:** `06-SYNTHESIS-AGENT` writes `final_memo.md` from the verified summaries.

Entry point: `python research/orchestrator.py <TICKER> <COMPANY_NAME>`. CLI wrapper: `scripts/test_research.py`. Quickstart: `research/QUICKSTART.md`. The system used `agent_tools.py` for shared tool plumbing (web fetch, SEC EDGAR, etc.) and `claim_verifier.py` for the verification phase. An ETF-specific variant (`orchestrator_etf.py` + `research/etf/` agent prompts) handled fund-level memos.

## Why archived

Superseded by the v0.1 slash-command-driven design developed on `claude/funny-agnesi-3eddfc` (2026-05-08): the new orchestrator runs as a `/research <TICKER>` Claude Code slash command dispatching subagents (`research-skeleton-gatherer`, four parallel `research-section-writer` instances, `research-verifier`, `research-synthesizer`) with deterministic Python helpers (`research/coverage_merge.py`, `research/memo_validate.py`) for the gates. The new design replaces the bespoke Anthropic-SDK orchestrator entrypoint with subagent dispatch, and replaces ad-hoc claim verification with a structured coverage log + verification report.

## Last-known runs

`sandbox/test_output/AAPL_20260127_*` directories contain final memos and per-agent JSON from three AAPL test runs on 2026-01-27.

## Archive contents

- `research/` — orchestrator, agent prompts (00–09), tools, verifiers, ETF variant
- `scripts/test_research.py` — CLI wrapper (only caller)
- `sandbox/test_output/AAPL_*` — three test-run outputs
