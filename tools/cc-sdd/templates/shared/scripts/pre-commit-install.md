# pre-commit hook installation

Run this once to set up the hook:

```bash
ln -sf ../../.agents/scripts/pre-commit.sh .git/hooks/pre-commit
```

This automatically runs on every `git commit`:
- Update traceability snapshot (`check_drift.py --snapshot`)
- Check for missing `@impl` tags (`extract_tags.py --check-missing`)

## Related

- **`ci-check.sh`** (opt-in): CIと同じ3段階チェック（全9チェック＋ドリフト＋影響分析）を
  コミット前にローカルで実行。`cp .agents/scripts/ci-check.sh` して `bash ci-check.sh`。
  pre-push hook としても使えます: `ln -sf ../../.agents/scripts/ci-check.sh .git/hooks/pre-push`
- See `.agents/scripts/README.md` for full setup guide including:
  - CI/CD gate configuration
  - Hermes cron monitoring setup
  - Detailed script usage
