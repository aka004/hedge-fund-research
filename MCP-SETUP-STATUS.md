# MCP Server Setup Status

## ✅ Installed MCP Servers

### 1. Context7 MCP
- **Status**: ✅ Configured
- **Purpose**: Live documentation for pandas, numpy, yfinance, and other libraries
- **Command**: `npx -y @upstash/context7-mcp@latest`
- **Configuration**: `/Users/yung004/.claude.json`

**Usage**: Ask Claude to look up documentation for any library, and it will fetch the latest docs via Context7.

**Example**:
- "Using context7, show me the pandas DataFrame.groupby() documentation"
- "What's the latest API for yfinance.download()?"

### 2. GitHub MCP
- **Status**: ✅ Configured (⚠️ Token needed)
- **Purpose**: Repository management, PRs, issues, CI/CD
- **Command**: `npx -y @modelcontextprotocol/server-github`
- **Configuration**: `/Users/yung004/.claude.json`

**Setup Required**: 
1. Generate a GitHub Personal Access Token:
   - Go to: https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Required scopes: `repo`, `read:org`, `read:user`
   - Copy the token (starts with `ghp_`)

2. Add to your `.env` file:
   ```bash
   GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here
   ```

3. **Restart Cursor** to load the environment variable

**Usage** (after token is set):
- "Create a new branch for feature X"
- "Show me open PRs in this repo"
- "Create an issue about Y"

## 🔄 Next Steps

1. **Restart Cursor** to activate the MCP servers
   - The "Failed to connect" status is normal until Cursor restarts
   - After restart, MCP servers will initialize automatically

2. **Verify Setup** (after restart):
   ```bash
   claude mcp list
   ```
   Should show both servers as connected (✓)

3. **Optional: Add GitHub Token**
   - If you want to use GitHub MCP features, follow the setup steps above
   - Context7 works immediately without any tokens

## 📋 Current Configuration

Both MCP servers are configured in:
- **Config File**: `~/.claude.json`
- **Project**: `/Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research`

The configuration will persist across Cursor sessions.

## 🎯 Recommended Usage

### Context7 (Ready to Use)
- ✅ **No setup needed** - works immediately after Cursor restart
- Best for: Looking up library documentation, API references, code examples
- Perfect for this project: pandas, numpy, yfinance, DuckDB docs

### GitHub (Optional)
- ⚠️ **Requires token** - add `GITHUB_PERSONAL_ACCESS_TOKEN` to `.env`
- Best for: Managing repos, creating PRs, tracking issues
- Useful if you want to automate GitHub workflows

## 🔍 Troubleshooting

If MCP servers don't connect after restart:

1. **Check Node.js is installed**:
   ```bash
   node --version
   npx --version
   ```

2. **Check network connectivity**:
   ```bash
   ping -c 2 registry.npmjs.org
   ```

3. **Manually test MCP server**:
   ```bash
   npx -y @upstash/context7-mcp@latest
   ```

4. **Check Cursor logs** for MCP connection errors

---

**Last Updated**: 2026-01-25
**Status**: Both servers configured, restart Cursor to activate
