# Traceability Scripts

コードと仕様書のトレーサビリティ（追跡可能性）を維持するためのスクリプト群。

## クイックスタート

```bash
# 1. 初回スナップショットを保存（ベースライン）
python3 .agents/scripts/check_drift.py --snapshot

# 2. コード変更後にドリフトをチェック
python3 .agents/scripts/check_drift.py --check

# 3. 特定要件の影響範囲を確認
python3 .agents/scripts/impact.py --spec-id 1.1

# 4. コード変更がどの仕様に影響するか
python3 .agents/scripts/impact.py --file strands-chat/ui/chat.py
```

## セットアップ手順

### 1. pre-commit hook（推奨）

コミットのたびにスナップショットを自動更新する。

```bash
# .git/hooks/ にリンク
ln -sf ../../.agents/scripts/pre-commit.sh .git/hooks/pre-commit
```

設定後は、`git commit` のたびに以下が自動実行される:
- コード変更をスナップショットに記録
- 新しい `@impl` タグの有無をチェック

### 2. CI/CD ゲート（GitHub Actions の場合） — 3段階

テンプレートファイルをプロジェクトにコピーするだけで有効になる:

```bash
cp tools/cc-sdd/templates/shared/.github/workflows/traceability-check.yml \
  .github/workflows/traceability-check.yml
```

プッシュ / PR のたびに以下を自動実行（pip install pyyaml が必要）:

| ジョブ | ゲート | 内容 |
|-------|:------:|------|
| **trace-completeness** | ❌ Block | 全9チェック（@impl/@spec/@verifies の網羅性） |
| **drift-check** | ❌ Block | コードと仕様書の乖離検出 |
| **impact-report** | ✅ Info | PRの影響範囲レポート（非ブロッキング） |

yaml 全文は `.github/workflows/traceability-check.yml` を参照。

### 2b. ローカルCIチェック（opt-in）

CIと同じチェックをコミット前にローカルで実行:

```bash
# インストール（ワンタイム）
cp tools/cc-sdd/templates/shared/scripts/ci-check.sh .agents/scripts/ci-check.sh
chmod +x .agents/scripts/ci-check.sh

# 手動実行
bash .agents/scripts/ci-check.sh

# または pre-push hook として（任意）
ln -sf ../../.agents/scripts/ci-check.sh .git/hooks/pre-push
```

### 3. Hermes cron 定期監視

毎朝6時にコードと仕様書のドリフトを自動チェックする。

```bash
# Hermes Agent の場合:
# 以下の内容で cron job を作成
```

<details>
<summary>Hermes cron 設定例（展開して表示）</summary>

**cron プロンプト:**
```
昨日のコード変更で仕様書（design.md, requirements.md）とのドリフトがあれば、
.agents/scripts/impact.py と .agents/scripts/check_drift.py を使って
影響範囲を特定し、結果を報告してください。
```

**Hermes コマンド:**
```bash
hermes cron create \
  --schedule "0 6 * * *" \
  --prompt "$(cat cron-prompt.md)" \
  --skills "spec-traceability" \
  --name "traceability-daily-check"
```

または `cronjob` tool で:
```
action=create
schedule=0 6 * * *
name=daily-traceability-check
prompt=昨日のコード変更で仕様書とのドリフトがあれば検出し、影響範囲を報告してください。
```
</details>

### 4. 初回セットアップ手順（一括）

```bash
# (1) スナップショット保存
python3 .agents/scripts/check_drift.py --snapshot

# (2) pre-commit hook
ln -sf ../../.agents/scripts/pre-commit.sh .git/hooks/pre-commit

# (3) 全マッピング確認
python3 .agents/scripts/impact.py --list
```

## スクリプト一覧

| スクリプト | 役割 | 使用タイミング |
|-----------|------|--------------|
| `extract_tags.py` | コードから `@impl`/`@module`/`@feature`/`@verifies`、仕様書から `@spec`/`@design`/`@satisfies` タグを抽出 | 調査・分析時 |
| `impact.py` | 仕様↔コードの双方向影響分析（`--quick` で .trace-mapping.yaml 不要） | 変更前に影響範囲を確認 |
| `check_drift.py` | スナップショットベースのドリフト検出 | CI / pre-commit / cron |
| `pre-commit.sh` | pre-commit hook（スナップショット自動更新） | コミット時 |
| `check-trace-completeness.py` | 包括的トレーサビリティ完全性チェック（@impl, code.files, code.symbols, @module, _Requirements:_, _Depends:_, @spec, @design, @satisfies, @verifies） | 実装完了時 / CI |

## よくある使い方

```bash
# 全マッピング一覧
python3 .agents/scripts/impact.py --list

# 仕様IDから影響コードをトレース
python3 .agents/scripts/impact.py --spec-id 6.1

# コード変更から影響仕様をトレース
python3 .agents/scripts/impact.py --file strands-chat/conversation/store.py

# git diff から一括トレース
python3 .agents/scripts/impact.py --diff

# CRG 連携（code-review-graph MCP が利用可能な場合）
python3 .agents/scripts/impact.py --spec-id 1.1 --crg

# ドリフト検出（スナップショット比較）
python3 .agents/scripts/check_drift.py --check

# ドリフト検出（git diff ベース、CI ゲートモード）
python3 .agents/scripts/check_drift.py --diff --gate

# @impl タグが欠けてるファイルを警告
python3 .agents/scripts/extract_tags.py --check-missing

# .trace-mapping.yaml 追記形式でタグ出力
python3 .agents/scripts/extract_tags.py --trace-mapping

# 簡易影響分析（.trace-mapping.yaml 不要）
python3 .agents/scripts/impact.py --quick --file src/auth/login.py
python3 .agents/scripts/impact.py --quick --spec-id 1.1
python3 .agents/scripts/impact.py --quick --diff
```

## アーキテクチャ

```
.trace-mapping.yaml         ← 仕様↔コードの対応表（真実の源泉）
.agents/scripts/            ← 分析スクリプト群
strands-chat/**/*.py        ← @impl タグが埋め込まれたコード
.git/hooks/pre-commit       ← pre-commit hook（check_drift.py --snapshot）
GitHub Actions / cron       ← 定期監視（オプション）
```

データフロー:

```
コード変更
  → pre-commit hook がスナップショットを更新
  → CI/cron が check_drift.py --diff --gate を実行
  → ドリフト検出 → 影響分析（impact.py）→ 報告
```

## 注意事項

- `.trace-mapping.yaml` は手動でメンテナンスする。`extract_tags.py --trace-mapping` が追記用の出力を生成する。
- スナップショット `.trace-snapshot.json` は gitignore 対象。CI では毎回 `--snapshot` してから `--check` するか、`--diff --gate` を使う。
- CRG MCP が利用できない環境では `--crg` オプションはスタブとして動作し、影響分析は `.trace-mapping.yaml` の直接マッピングのみに基づく。
