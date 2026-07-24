# Traceability Git Hooks

Run these once to set up the hooks:

## 1. pre-commit hook（軽量・推奨）

```bash
ln -sf ../../.agents/scripts/pre-commit.sh .git/hooks/pre-commit
```

コミットごとに自動実行:
- ✅ Trace snapshot update (`check_drift.py --snapshot`)
- ✅ Missing `@impl` tag check (`extract_tags.py --check-missing`)

フルチェックを有効にするには（全9チェックを含む）:
```bash
TRACE_FULL=1 git commit -m "message"
```
またはエイリアス設定:
```bash
git config alias.c "commit -a -S"
git config alias.cf "!TRACE_FULL=1 git commit"
```

## 2. pre-push hook（本格チェック・opt-in）

```bash
ln -sf ../../.agents/scripts/pre-push.sh .git/hooks/pre-push
```

プッシュごとに3段階のトレーサビリティチェックを実行:
1. ❌ Trace Completeness Gate — 全9チェック（`check-trace-completeness.py`）
2. ❌ Drift Check — コードと仕様書の乖離検出（`check_drift.py --diff --gate`）
3. ✅ Impact Summary — 影響範囲レポート（参考、非ブロッキング）

全て通過でプッシュ続行、失敗で中断。

スキップする場合:
```bash
SKIP_TRACE=1 git push
```

## 削除

```bash
rm .git/hooks/pre-commit
rm .git/hooks/pre-push
```
