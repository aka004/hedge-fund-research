# Orchestrator B — Alpha Testing Event Loop (archived)

**Active:** 2026-01-25 → 2026-01-27
**Archived:** 2026-05-08

## What it was

Event-driven multi-agent workflow for testing alpha generation strategies. An `Orchestrator` class managed a pub/sub `EventBus` between role-specialised agents:

| Agent | Role | Key AFML hooks |
|---|---|---|
| `MomentumResearcher` | Generate alpha signal candidates | `triple_barrier()`, `regime_200ma()` |
| `BacktestUnit` | Validate signals via cross-validation | `purged_kfold()` |
| `StatisticalAgent` | PSR/DSR check, approve or reject | `deflated_sharpe()`, `sample_uniqueness()` |
| `ProjectManager` | Evaluate `data.missing` requests | — |
| `DataPipelineAgent` | Fulfil approved data requests | — |
| `Scribe` | Append-only event log | — |

**Main flow:** `MomentumResearcher` emits `alpha.ready` → `BacktestUnit` runs purged k-fold and emits `backtest.passed` → `StatisticalAgent` checks PSR ≥ 0.95 → `alpha.success` (done) or `alpha.rejected` (researcher tries again).

**Side flow:** any agent can emit `data.missing` → `ProjectManager` either approves (pipeline fetches data, retry) or rejects (researcher proposes alternative → human approval → implement).

Entry point: `python scripts/run_agents.py` with `--data-test` / `--alpha-workflow` modes.

## Why archived

The active EOD research loop (`scripts/auto_research_loop.py` + `scripts/alpha_gpt.py`) does NOT use this event bus. The live loop drives strategy discovery via direct LLM calls and shells out to the backtest engine — never importing from `agents/`. After three months of parallel existence with no integration, this scaffolding became dead code: `agents/__init__.py`'s only consumer was `scripts/run_agents.py`, and nothing in the running pipeline depended on the package.

## Archive contents

- `agents/` — orchestrator + 8 agent classes + `__init__.py` (full package re-exports)
- `scripts/run_agents.py` — only caller (CLI for manual workflow runs)
