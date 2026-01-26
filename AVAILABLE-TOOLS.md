# Available Tools: Skills, Agents & MCP Servers

**Last Updated**: 2026-01-25  
**Status**: All systems operational

---

## 🎯 Skills (2 Project Skills + 6 Superpowers)

### Project-Specific Skills

#### 1. **backtest-patterns**
- **Location**: `.claude/skills/backtest-patterns/SKILL.md`
- **Purpose**: Backtesting code, signal generation, performance analysis
- **When to Use**: Implementing backtesting code, signal generation, or performance analysis
- **Key Principles**:
  - No look-ahead bias
  - Realistic execution (slippage, commissions)
  - Survivorship awareness
  - Reproducibility

#### 2. **ui-ux-pro-max**
- **Location**: `.claude/skills/ui-ux-pro-max/SKILL.md`
- **Purpose**: UI/UX design intelligence
- **When to Use**: Plan, build, create, design, implement, review, fix, improve UI/UX code
- **Features**:
  - 50+ styles, 21 palettes, 50 font pairings
  - 20 chart types, 9 tech stacks
  - Searchable database with priority-based recommendations
  - Supports: React, Next.js, Vue, Svelte, SwiftUI, React Native, Flutter, Tailwind, shadcn/ui

### Superpowers Skills (Referenced in CLAUDE.md)

#### 3. **superpowers:test-driven-development**
- **Purpose**: RED-GREEN-REFACTOR cycle
- **When to Use**: Write tests before implementation
- **Features**: Enforces true TDD, YAGNI, DRY principles

#### 4. **superpowers:systematic-debugging**
- **Purpose**: 4-phase root cause process
- **When to Use**: Debug data issues methodically
- **Features**: Root-cause-tracing, defense-in-depth, condition-based-waiting

#### 5. **superpowers:brainstorm**
- **Purpose**: Interactive design refinement
- **When to Use**: Before coding, refine rough ideas through questions

#### 6. **superpowers:write-plan**
- **Purpose**: Create detailed implementation plans
- **When to Use**: After design approval, break work into bite-sized tasks

#### 7. **superpowers:execute-plan**
- **Purpose**: Execute plans in batches with checkpoints
- **When to Use**: With approved plan, dispatch subagents per task

#### 8. **superpowers:requesting-code-review**
- **Purpose**: Review code against plan before completion
- **When to Use**: Between tasks, review against plan and report issues

**Note**: Superpowers skills require plugin installation:
```bash
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

---

## 🤖 Agents (7 Agents + 1 Orchestrator)

Event-driven multi-agent system for alpha testing. All agents inherit from `Agent` base class.

### Core Agents

#### 1. **MomentumResearcher**
- **File**: `agents/momentum_researcher.py`
- **Clearance**: `RESEARCH`
- **Role**: Generate alpha signals
- **AFML Techniques**: `triple_barrier()`, `regime_200ma()`
- **Responsibilities**:
  - Generate alpha signals using momentum
  - Apply triple barrier labeling
  - Check regime context (200-day MA)
  - Emit `alpha.ready` events

#### 2. **BacktestUnit**
- **File**: `agents/backtest_unit.py`
- **Clearance**: `VALIDATION`
- **Role**: Validate strategies with cross-validation
- **AFML Techniques**: `purged_kfold()`
- **Responsibilities**:
  - Run purged K-fold cross-validation
  - Validate signals against historical data
  - Emit `backtest.passed` or `backtest.failed` events

#### 3. **StatisticalAgent**
- **File**: `agents/statistical_agent.py`
- **Clearance**: `VALIDATION`
- **Role**: Compute PSR, approve/reject strategies
- **AFML Techniques**: `deflated_sharpe()`, `sample_uniqueness()`
- **Responsibilities**:
  - Compute Probability Sharpe Ratio (PSR)
  - Check if PSR > 0.95 threshold
  - Emit `alpha.success` or `alpha.rejected` events

#### 4. **ProjectManager**
- **File**: `agents/project_manager.py`
- **Clearance**: `INFRASTRUCTURE`
- **Role**: Evaluate data requests, coordinate workflow
- **Responsibilities**:
  - Evaluate `data.missing` requests
  - Approve/reject based on feasibility
  - Propose alternatives when data unavailable
  - Emit `pm.approved` or `pm.rejected` events

#### 5. **DataPipelineAgent**
- **File**: `agents/data_pipeline.py`
- **Clearance**: `PIPELINE`
- **Role**: Implement data fetching, add provider methods
- **Responsibilities**:
  - Add provider methods for data sources
  - Add Parquet columns as needed
  - Fetch data when approved by PM
  - Emit `data.available` events

#### 6. **Scribe**
- **File**: `agents/scribe.py`
- **Clearance**: `INFRASTRUCTURE`
- **Role**: Record all events
- **Responsibilities**:
  - Log all events to files
  - Maintain event history
  - Generate reports from event logs

### Coordination

#### 7. **Orchestrator**
- **File**: `agents/orchestrator.py`
- **Role**: Main coordinator, manages agent lifecycle
- **Responsibilities**:
  - Manage agent lifecycle (start/stop)
  - Route events between agents
  - Track workflow state
  - Handle human approval gates

### Agent Clearance Hierarchy

```
RESEARCH < VALIDATION < INFRASTRUCTURE < PIPELINE < ADMIN
```

### Event Flow

```
Momentum Researcher
  │ alpha.ready
  ▼
Backtest Unit ───────── purged k-fold validation
  │ backtest.passed
  ▼
Statistical Agent ────── PSR check (>= 0.95?)
  ├── alpha.success ──→ ✅ DONE
  └── alpha.rejected ──→ Momentum Researcher (adjust strategy)
```

---

## 🔌 MCP Servers (2 Connected)

### 1. **Context7 MCP** ✅ Connected
- **Package**: `@upstash/context7-mcp@latest`
- **Status**: ✓ Connected
- **Type**: stdio
- **Purpose**: Live documentation for libraries
- **Features**:
  - Fetches up-to-date documentation
  - Perfect for pandas, numpy, yfinance, DuckDB docs
  - No token required
- **Usage**: Ask Claude to look up documentation for any library
- **Example**: "Using context7, show me the pandas DataFrame.groupby() documentation"

### 2. **GitHub MCP** ✅ Connected
- **Package**: `@modelcontextprotocol/server-github`
- **Status**: ✓ Connected
- **Type**: stdio
- **Purpose**: Repository management, PRs, issues, CI/CD
- **Features**:
  - Repository management
  - Issue tracking
  - Pull request operations
  - Branch management
  - File operations
  - Search capabilities
- **Token Required**: ⚠️ Yes (needs `GITHUB_PERSONAL_ACCESS_TOKEN` in `.env`)
- **Usage**: After adding token, manage repos, create PRs, track issues
- **Example**: "Show me open issues in this repository"

### MCP Configuration

- **Config File**: `~/.claude.json`
- **Project Path**: `/Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research`
- **Verification**: Run `claude mcp list` to check status

---

## 📊 Summary

| Category | Count | Status |
|----------|-------|--------|
| **Project Skills** | 2 | ✅ Active |
| **Superpowers Skills** | 6 | ⚠️ Requires plugin |
| **Agents** | 7 | ✅ Implemented |
| **Orchestrator** | 1 | ✅ Implemented |
| **MCP Servers** | 2 | ✅ Connected |

---

## 🚀 Quick Reference

### Using Skills
- Project skills auto-load when relevant
- Superpowers skills: Install plugin first, then reference in CLAUDE.md
- Skills trigger automatically based on context

### Using Agents
- Agents run via `Orchestrator`
- Event-driven workflow
- All agents use AFML techniques (mandatory)

### Using MCP Servers
- Context7: Works immediately (no token)
- GitHub: Add token to `.env`, then restart Cursor
- Test with: `claude mcp list`

---

## 📝 Notes

- **Superpowers Plugin**: Install via `/plugin install superpowers@superpowers-marketplace`
- **GitHub Token**: Generate at https://github.com/settings/tokens
- **MCP Status**: Both servers show as connected via CLI
- **Agent Workflow**: See `CLAUDE.md` for complete event flow documentation

---

*For detailed documentation, see:*
- Skills: `.claude/skills/*/SKILL.md`
- Agents: `agents/*.py`
- MCP Setup: `MCP-SETUP-STATUS.md`
- Workflow: `CLAUDE.md`
