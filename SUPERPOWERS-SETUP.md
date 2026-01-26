# Superpowers Skills Setup Guide

## Overview

Superpowers is an agentic skills framework for Claude Code that provides structured workflow skills for systematic development practices. It enforces disciplined coding workflows through slash commands.

## Installation Steps

### Step 1: Register the Marketplace

In Cursor/Claude Code, open the chat and run:

```
/plugin marketplace add obra/superpowers-marketplace
```

This registers the superpowers marketplace as a source for plugins.

### Step 2: Install Superpowers Plugin

After registering the marketplace, install the plugin:

```
/plugin install superpowers@superpowers-marketplace
```

### Step 3: Verify Installation

Check that commands are available:

```
/help
```

You should see these commands in the list:
- `/superpowers:brainstorm` - Interactive design refinement
- `/superpowers:write-plan` - Create implementation plan
- `/superpowers:execute-plan` - Execute plan in batches

## Available Superpowers Skills

Once installed, the following skills are available (already referenced in `CLAUDE.md`):

### 1. **test-driven-development**
- **Command**: `/superpowers:test-driven-development` or reference in code
- **Purpose**: RED-GREEN-REFACTOR cycle
- **Features**: 
  - Enforces true TDD (write tests first)
  - YAGNI (You Aren't Gonna Need It)
  - DRY (Don't Repeat Yourself)
  - Deletes code written before tests

### 2. **systematic-debugging**
- **Purpose**: 4-phase root cause process
- **Features**:
  - Root-cause-tracing
  - Defense-in-depth
  - Condition-based-waiting techniques

### 3. **brainstorm**
- **Command**: `/superpowers:brainstorm`
- **Purpose**: Interactive design refinement
- **When**: Activates before writing code
- **Features**: 
  - Refines rough ideas through questions
  - Explores alternatives
  - Presents design in sections for validation
  - Saves design document

### 4. **write-plan**
- **Command**: `/superpowers:write-plan`
- **Purpose**: Create detailed implementation plans
- **When**: Activates with approved design
- **Features**:
  - Breaks work into bite-sized tasks (2-5 minutes each)
  - Every task has exact file paths
  - Complete code specifications
  - Verification steps

### 5. **execute-plan**
- **Command**: `/superpowers:execute-plan`
- **Purpose**: Execute plans in batches with checkpoints
- **When**: Activates with plan
- **Features**:
  - Dispatches fresh subagent per task
  - Two-stage review (spec compliance, then code quality)
  - Human checkpoints between batches

### 6. **requesting-code-review**
- **Purpose**: Review code against plan before completion
- **When**: Activates between tasks
- **Features**:
  - Reviews against plan
  - Reports issues by severity
  - Critical issues block progress

## Additional Superpowers Skills (Available but not yet referenced)

### 7. **using-git-worktrees**
- **When**: Activates after design approval
- **Features**: Creates isolated workspace on new branch

### 8. **subagent-driven-development**
- **When**: Activates with plan
- **Features**: Fast iteration with two-stage review

### 9. **finishing-a-development-branch**
- **When**: Activates when tasks complete
- **Features**: Verifies tests, presents merge/PR options

### 10. **verification-before-completion**
- **Purpose**: Ensure it's actually fixed
- **Features**: Verification checklist

### 11. **receiving-code-review**
- **Purpose**: Responding to feedback
- **Features**: Address review comments systematically

### 12. **dispatching-parallel-agents**
- **Purpose**: Concurrent subagent workflows
- **Features**: Parallel task execution

### 13. **writing-skills**
- **Purpose**: Create new skills following best practices
- **Features**: Includes testing methodology

### 14. **using-superpowers**
- **Purpose**: Introduction to the skills system
- **Features**: Overview and usage guide

## How Superpowers Works

### Automatic Activation

Skills trigger automatically based on context:
- **Before coding**: `brainstorm` activates to refine ideas
- **After design approval**: `write-plan` creates implementation plan
- **During implementation**: `test-driven-development` enforces TDD
- **Between tasks**: `requesting-code-review` reviews code
- **When debugging**: `systematic-debugging` provides structured approach

### Workflow Example

1. **Brainstorm** → Refine rough idea into design
2. **Write Plan** → Break design into tasks
3. **Execute Plan** → Run tasks with checkpoints
4. **Code Review** → Review against plan
5. **TDD** → Write tests first, always
6. **Debug** → Use systematic approach when issues arise

## Current Status

### ✅ Already Configured
- References added to `CLAUDE.md`
- Skills documented in `AVAILABLE-TOOLS.md`
- Ready to use once plugin is installed

### ⏳ Pending Installation
- Plugin needs to be installed via Cursor commands
- Marketplace needs to be registered

## Quick Start After Installation

Once installed, try:

1. **Start a new feature**:
   ```
   /superpowers:brainstorm
   ```
   Then describe what you want to build.

2. **Create a plan**:
   ```
   /superpowers:write-plan
   ```
   After design is approved.

3. **Execute the plan**:
   ```
   /superpowers:execute-plan
   ```
   To start implementation.

## Troubleshooting

### Plugin Not Found
- Ensure marketplace is registered: `/plugin marketplace add obra/superpowers-marketplace`
- Check marketplace list: `/plugin marketplace list`

### Commands Not Appearing
- Verify installation: `/plugin list`
- Restart Cursor after installation
- Check `/help` for available commands

### Skills Not Triggering
- Skills auto-trigger based on context
- You can also reference them explicitly: `superpowers:test-driven-development`
- Ensure plugin is enabled in Cursor settings

## Updating Superpowers

To update to the latest version:

```
/plugin update superpowers
```

## Resources

- **Repository**: https://github.com/obra/superpowers
- **Marketplace**: https://github.com/obra/superpowers-marketplace
- **Documentation**: See repository README
- **Blog Post**: https://blog.fsck.com/2025/10/09/superpowers/

## Philosophy

Superpowers enforces:
- **Test-Driven Development** - Write tests first, always
- **Systematic over ad-hoc** - Process over guessing
- **Complexity reduction** - Simplicity as primary goal
- **Evidence over claims** - Verify before declaring success

---

**Next Step**: Install the plugin using the commands above, then the skills will be available automatically!
