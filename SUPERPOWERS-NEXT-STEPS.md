# Superpowers Installation - Next Steps

## Step 1 Status: Marketplace Registration

You've run: `/plugin marketplace add obra/superpowers-marketplace`

**What should happen:**
- Cursor should show a confirmation message
- The marketplace should be registered
- You can verify with: `/plugin marketplace list`

**If successful**, you should see `obra/superpowers-marketplace` in the list.

---

## Step 2: Install the Plugin

Once the marketplace is registered, run:

```
/plugin install superpowers@superpowers-marketplace
```

**What this does:**
- Downloads and installs the superpowers plugin
- Makes all superpowers skills available
- Enables auto-triggering based on context

---

## Step 3: Verify Installation

After installation completes, verify with:

```
/help
```

**Look for these commands:**
- `/superpowers:brainstorm`
- `/superpowers:write-plan`
- `/superpowers:execute-plan`

If you see these, installation was successful! ✅

---

## Troubleshooting

### If marketplace add didn't work:
1. Check Cursor's output panel for error messages
2. Try again: `/plugin marketplace add obra/superpowers-marketplace`
3. Check your internet connection
4. Verify the repository exists: https://github.com/obra/superpowers-marketplace

### If install fails:
1. Ensure marketplace was registered: `/plugin marketplace list`
2. Check Cursor output panel for errors
3. Try: `/plugin install superpowers@superpowers-marketplace` again
4. Restart Cursor and try again

---

## After Installation

Once installed, superpowers will:
- ✅ Auto-trigger skills when you code (as configured in CLAUDE.md)
- ✅ Enforce TDD, systematic debugging, structured workflows
- ✅ Provide slash commands for manual activation

**Test it:**
```
/superpowers:brainstorm
```

Then describe a feature you want to build!

---

**Current Status**: Waiting for Step 1 confirmation, then proceed to Step 2
