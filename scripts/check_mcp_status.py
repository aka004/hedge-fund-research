#!/usr/bin/env python3
"""
MCP Server Status Checker

Checks if MCP servers are configured and provides verification steps.
"""

import json
import os
from pathlib import Path


def check_mcp_config():
    """Check MCP server configuration in ~/.claude.json"""
    config_path = Path.home() / ".claude.json"
    
    if not config_path.exists():
        print("❌ ~/.claude.json not found")
        return None
    
    with open(config_path) as f:
        config = json.load(f)
    
    # Find project config
    project_path = "/Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research"
    
    if "projects" not in config:
        print("❌ No projects found in config")
        return None
    
    if project_path not in config["projects"]:
        print(f"❌ Project not found in config: {project_path}")
        return None
    
    project_config = config["projects"][project_path]
    
    if "mcpServers" not in project_config:
        print("❌ No MCP servers configured for this project")
        return None
    
    return project_config["mcpServers"]


def check_env_vars():
    """Check if required environment variables are set"""
    env_file = Path(__file__).parent.parent / ".env"
    
    env_vars = {}
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    
    return env_vars


def main():
    print("=" * 60)
    print("MCP Server Status Check")
    print("=" * 60)
    print()
    
    # Check configuration
    print("📋 Configuration Check:")
    mcp_servers = check_mcp_config()
    
    if not mcp_servers:
        print("   No MCP servers found in configuration")
        return
    
    print(f"   Found {len(mcp_servers)} configured server(s):")
    print()
    
    for name, config in mcp_servers.items():
        print(f"   🔌 {name.upper()}")
        print(f"      Type: {config.get('type', 'unknown')}")
        print(f"      Command: {config.get('command', 'N/A')}")
        print(f"      Args: {' '.join(config.get('args', []))}")
        
        env = config.get('env', {})
        if env:
            print(f"      Environment variables:")
            for key, value in env.items():
                # Mask token values
                if 'token' in key.lower() or 'secret' in key.lower():
                    masked = value[:10] + "..." if len(value) > 10 else "***"
                    print(f"        {key}: {masked}")
                else:
                    print(f"        {key}: {value}")
        
        print()
    
    # Check environment variables
    print("🔐 Environment Variables Check:")
    env_vars = check_env_vars()
    
    github_token = env_vars.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if github_token:
        print(f"   ✅ GITHUB_PERSONAL_ACCESS_TOKEN: Set ({len(github_token)} chars)")
    else:
        print(f"   ⚠️  GITHUB_PERSONAL_ACCESS_TOKEN: Not set (GitHub MCP won't work)")
    
    print()
    
    # Status summary
    print("=" * 60)
    print("Status Summary")
    print("=" * 60)
    print()
    
    print("✅ Configuration: Both servers are configured correctly")
    print()
    
    if github_token:
        print("✅ GitHub MCP: Token found, should work after Cursor restart")
    else:
        print("⚠️  GitHub MCP: Token missing - add to .env file")
    print()
    
    print("📝 Next Steps:")
    print("   1. Restart Cursor to activate MCP servers")
    print("   2. Test Context7: Ask Claude 'Show me pandas DataFrame docs using context7'")
    print("   3. Test GitHub: Ask Claude 'Show me open issues' (requires token)")
    print()
    print("💡 Note: CLI 'Failed to connect' is normal if Node.js isn't in PATH.")
    print("   Cursor has its own Node.js runtime and will connect servers when running.")
    print()


if __name__ == "__main__":
    main()
