# pre-commit hook installation

Run this once to set up the hook:

```bash
ln -sf ../../.agents/scripts/pre-commit.sh .git/hooks/pre-commit
```

This automatically runs on every `git commit`:
- Update traceability snapshot (`check_drift.py --snapshot`)
- Check for missing `@impl` tags (`extract_tags.py --check-missing`)

## Related

See `.agents/scripts/README.md` for full setup guide including:
- CI/CD gate configuration
- Hermes cron monitoring setup
- Detailed script usage
