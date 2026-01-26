# MCP Connection Issue - Context7 Not Connected

## Problem

When testing Context7 MCP, it appears **not to be connected** even though:
- ✅ Configuration is correct in `~/.claude.json`
- ✅ Cursor has been restarted
- ✅ Network connectivity is working

## Evidence

When you asked: *"Using context7, show me the pandas DataFrame.groupby() documentation"*

**Result**: I don't have access to Context7 MCP tools. I can only fetch documentation via web fetch, not through Context7's specialized tools.

## Possible Causes

1. **Node.js not available to Cursor**
   - Cursor may not have Node.js in its runtime path
   - MCP servers require Node.js to run `npx` commands

2. **MCP server failed to initialize**
   - Check Cursor's Output panel for errors
   - View → Output → Select "MCP" or "Claude"

3. **Configuration issue**
   - The package name might be incorrect
   - We used: `@upstash/context7-mcp@latest`
   - Documentation shows: `@context-labs/mcp-server-context7`

## Solution: Fix Configuration

The MCP-SETUP.md shows a different package name than what we installed:

**What we installed:**
```json
"args": ["-y", "@upstash/context7-mcp@latest"]
```

**What documentation shows:**
```json
"args": ["-y", "@context-labs/mcp-server-context7"]
```

## Next Steps

1. **Check Cursor Output Panel** for MCP connection errors
2. **Try the alternative package name** from documentation
3. **Install Node.js** if Cursor doesn't have it: `brew install node`
4. **Check Cursor Settings** → MCP Servers for connection status

## Quick Fix

Try updating the configuration to use the package name from the documentation:

```bash
claude mcp remove context7
claude mcp add context7 -- npx -y @context-labs/mcp-server-context7
```

Then restart Cursor again.
