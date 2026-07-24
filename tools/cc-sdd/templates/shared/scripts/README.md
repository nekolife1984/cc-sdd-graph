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

フルチェック（全9チェック + check-trace-completeness.py）を有効にするには:
```bash
TRACE_FULL=1 git commit -m "message"
```

### 1b. pre-push hook（opt-in）

プッシュ前に3段階のフルチェックを実行する（`.agents/scripts/ci-check.sh` 相当）。

```bash
ln -sf ../../.agents/scripts/pre-push.sh .git/hooks/pre-push
```

プッシュ時に以下を自動実行:
1. ❌ Trace Completeness Gate — 全9チェック
2. ❌ Drift Check — コードと仕様書の乖離検出
3. ✅ Impact Summary — 影響範囲レポート（参考）

スキップ: `SKIP_TRACE=1 git push`

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

### 5. 影響度バンド（Green/Amber/Gray）

`impact.py` は各成果物の関連強度を3段階のバンドで分類する:

```bash
# バンド表示付きで実行（自動）
python3 .agents/scripts/impact.py --spec-id 1.1

# 特定バンド以上の項目だけ表示
python3 .agents/scripts/impact.py --spec-id 1.1 --band green
python3 .agents/scripts/impact.py --spec-id 1.1 --band amber+
python3 .agents/scripts/impact.py --quick --diff --band amber+
```

| バンド | スコア | 意味 | CIでの扱い |
|:-----:|:------:|------|:----------:|
| 🟢 GREEN | ≥50 | .trace-mapping + @impl + テスト等の強い証拠 | 自動通過OK |
| 🟡 AMBER | ≥20 | 一部の証拠のみ（CRG推移的、quick grep等） | 要レビュー |
| ⚪ GRAY | <20 | 弱い一致（参考程度） | 無視可 |

証拠の重み:

| 証拠タイプ | 重み | 説明 |
|-----------|:----:|------|
| `.trace-mapping.yaml` | 40 | 設計者が明示的にリンク |
| `@impl` タグ | 25 | 実装者がコードにタグ付け |
| `@verifies` タグ | 20 | テストが要件を検証 |
| CRG 直接（1 hop） | 15 | import/呼び出し関係 |
| CRG 推移的（2+ hop） | 5 | 推移的依存 |
| quick grep | 10 | タグベースの全文検索 |

JSON出力には `banded` キーにバンド別の詳細と内訳が含まれる:

```bash
python3 .agents/scripts/impact.py --spec-id 1.1 --json | jq '.band_summary'
# {
#   "green": 2,
#   "amber": 1,
#   "gray": 0
# }
```

## スクリプト一覧

| スクリプト | 役割 | 使用タイミング |
|-----------|------|--------------|
| `extract_tags.py` | コードから `@impl`/`@module`/`@feature`/`@verifies`、仕様書から `@spec`/`@design`/`@satisfies` タグを抽出 | 調査・分析時 |
| `impact.py` | 仕様↔コードの双方向影響分析（`--quick` で .trace-mapping.yaml 不要） | 変更前に影響範囲を確認 |
| `check_drift.py` | スナップショットベースのドリフト検出 | CI / pre-commit / cron |
| `pre-commit.sh` | pre-commit hook（スナップショット自動更新） | コミット時 |
|| `check-trace-completeness.py` | 包括的トレーサビリティ完全性チェック（9標準 + 2 P0 false-green） | 実装完了時 / CI |

## False-Green ベクター品質管理

`quality/` ディレクトリに false-green 対策の設計書と検出状況を管理している:

```bash
# プロジェクトにコピーして使う
cp -r tools/cc-sdd/templates/shared/quality/ .kiro/quality/
```

| ファイル | 内容 |
|---------|------|
| `false_green_vectors.yaml` | 機械可読なベクターカタログ（P0/P1/P2分類、invariant、mutation） |
| `false_green_matrix.md` | 検出状況マトリクス + saturation 充足度 |

### P0 ベクターチェック（出荷済み）

`check-trace-completeness.py` に組み込み済み:

```bash
# @impl コードのカバレッジ確認（coverage.json または .coverage が必要）
python3 .agents/scripts/check-trace-completeness.py --check coverage

# @verifies ファイルの実アサーションチェック
python3 .agents/scripts/check-trace-completeness.py --check assertions

# .trace-mapping.yaml 参照コードの鮮度チェック（90日ルール）
python3 .agents/scripts/check-trace-completeness.py --check stale

# CI/CD で全P0チェックと一緒に実行
python3 .agents/scripts/check-trace-completeness.py --check coverage,assertions,stale

# または一発ゲート
bash .agents/scripts/check-gate.sh
```

| チェック | ベクター | 検出ロジック | 準備 |
|---------|:--------:|-------------|------|
| `coverage` | P0-1 @impl orphan | @impl ファイルが coverage.json/.coverage にヒットしているか | `pytest --cov --cov-report=json` |
| `assertions` | P0-2 空アサーション | @verifies ファイルに assert/expect/should があるか | なし（静的解析） |
| `stale` | P0-3 stale mapping | 参照コードが90日以上未変更か | git 管理下であること |

### P0-4: CI ゲートバイパス検知（出荷済み）

`check-ci-bypass.py` が CI ゲートのバイパスを検出する:

```bash
# 基本チェック
python3 .agents/scripts/check-ci-bypass.py

# 詳細表示
python3 .agents/scripts/check-ci-bypass.py --verbose

# 確認期間を30日に延ばす
CI_BYPASS_LOOKBACK=30 python3 .agents/scripts/check-ci-bypass.py

# bypass を許可する（エラーにしない）
SKIP_TRACE_ALLOWED=1 python3 .agents/scripts/check-ci-bypass.py
```

チェック内容:

| # | チェック | 検出するもの | 備考 |
|:-:|---------|-------------|------|
| 1 | pre-push hook | hook が未設置 / 権限なし / 別の hook で上書き | 常に実行 |
| 2 | git log | 直近のコミットでの `SKIP_TRACE` 使用 | デフォルト14日間 |
| 3 | GitHub Actions | CI の失敗・スキップ履歴 | `gh` CLI が必要（opt-in） |

cron 定期実行との組み合わせ:

```yaml
# .github/workflows/daily-bypass-check.yml または Hermes cron
action: create
schedule: 0 6 * * *
name: daily-ci-bypass-check
prompt: .agents/scripts/check-ci-bypass.py --verbose を実行し、結果を報告してください
skills: [spec-traceability, ci-gate-monitor]
```

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
