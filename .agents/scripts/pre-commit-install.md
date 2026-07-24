# pre-commit hook installation

Run this once to set up the hook:

```bash
ln -sf ../../.agents/scripts/pre-commit.sh .git/hooks/pre-commit
```

This automatically runs on every `git commit`:
1. **`@impl` tag completeness check** — verifies that `.trace-mapping.yaml` entries have corresponding `@impl` tags in the code (blocks commit if missing)
2. **Traceability snapshot update** — records code changes for drift detection

## Verification

After installation, test the hook:

```bash
# Try committing — should show the checks
git add -A && git commit -m "test pre-commit hook"

# On first run with existing code, you may see @impl warnings.
# Fix those, or bypass once with:
git commit --no-verify -m "bypass hook temporarily"
```

## Bypassing

Use `--no-verify` sparingly — only when you're mid-work and know the
checks are noise. Make a habit of running the gate manually afterward:

```bash
python3 .agents/scripts/check-impl-completeness.py
```

## Related

See `.agents/scripts/README.md` for full setup guide including:
- CI/CD gate configuration
- Hermes cron monitoring setup
- Detailed script usage
