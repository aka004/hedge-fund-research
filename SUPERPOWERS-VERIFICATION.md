# Superpowers Marketplace Verification

## Checking Registration Status

After running `/plugin marketplace add obra/superpowers-marketplace`, the marketplace should be registered.

### How to Verify

1. **Check in Cursor**: Look for a confirmation message
2. **List marketplaces**: Run `/plugin marketplace list` in Cursor
3. **Check config file**: The marketplace should appear in `~/.claude/plugins/known_marketplaces.json`

### Expected Result

The `known_marketplaces.json` file should contain:
```json
{
  "claude-plugins-official": { ... },
  "obra-superpowers-marketplace": {
    "source": {
      "source": "github",
      "repo": "obra/superpowers-marketplace"
    },
    ...
  }
}
```

### If Not Registered

If the marketplace doesn't appear:
1. Check Cursor's output panel for errors
2. Verify internet connection
3. Check repository exists: https://github.com/obra/superpowers-marketplace
4. Try the command again

### Next Step After Registration

Once registered, install the plugin:

```
/plugin install superpowers@superpowers-marketplace
```

---

**Note**: Marketplace registration happens in Cursor's plugin system. The command you ran should register it. If you see a success message, proceed to installation!
