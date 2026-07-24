# cc-sdd-graph

[cc-sdd](https://github.com/gotalab/cc-sdd) をフォークし、**code-review-graph (CRG)** による双方向の仕様↔コードトレーサビリティを統合したバージョンです。`@impl` タグによる要件とコードの自動追跡、影響範囲分析、仕様ドリフト検出を提供します。

## クイックスタート

### macOS / Linux
```bash
bash <(curl -s https://raw.githubusercontent.com/nekolife1984/cc-sdd-graph/main/scripts/quickstart.sh)
```

### Windows (PowerShell)
```powershell
Invoke-WebRequest -Uri https://raw.githubusercontent.com/nekolife1984/cc-sdd-graph/main/scripts/quickstart.ps1 -OutFile quickstart.ps1
.\quickstart.ps1
```

このスクリプトが以下を自動で行います:
1. cc-sdd-graph スキルのインストール（エージェント・言語を選択）
2. code-review-graph のインストールと MCP 設定
3. コードグラフの初回ビルド
4. `.trace-mapping.yaml` の初期化
5. pre-commit hook のセットアップ（コミット時にスナップショット自動更新）
6. 初回スナップショットの保存

## 個別セットアップ

```bash
# スキルのみ
npx github:nekolife1984/cc-sdd-graph

# CRG のみ（スキルインストール後）
bash .agents/scripts/setup-crg.sh --yes
```

## 特徴

### 20の kiro スキル
| フェーズ | スキル |
|---------|--------|
| 企画 | `kiro-discovery`, `kiro-steering` |
| 仕様定義 | `kiro-spec-init`, `kiro-spec-requirements`, `kiro-spec-design`, `kiro-spec-tasks` |
| 一括生成 | `kiro-spec-batch`, `kiro-spec-quick` |
| 実装 | `kiro-impl` |
| レビュー | `kiro-review`, `kiro-validate-design`, `kiro-validate-gap`, `kiro-validate-impl` |
| デバッグ | `kiro-debug` |
| 完了検証 | `kiro-verify-completion` |
| 進捗 | `kiro-spec-status` |
| **CRG トレーサビリティ** | **`kiro-trace`**, **`kiro-impact`**, **`kiro-validate-boundary`** |

### CRG 対応スキル（20中15）
ほとんどのスキルが code-review-graph と連携し、コードグラフを活用した分析・検証を実行します:

| スキル | CRG 連携 |
|--------|---------|
| `kiro-discovery` | 既存拡張時に影響範囲を自動表示 |
| `kiro-spec-design` | コードグラフ分析で設計を強化 |
| `kiro-spec-tasks` | `_Boundary:_` を CRG で機械検証 |
| `kiro-spec-init` | `.trace-mapping.yaml` スケルトン自動生成 |
| `kiro-spec-batch` | `.trace-mapping.yaml` 一括生成 |
| `kiro-review` | CRG 強化された境界検証 |
| `kiro-impl` | `@impl` タグ自動スキャン + `.trace-mapping.yaml` 更新 |
| `kiro-validate-impl` | CRG フロー検証 |
| `kiro-debug` | CRG グラフ調査 |
| `kiro-verify-completion` | CRG アーキテクチャ整合性チェック |
| `kiro-validate-design` | 設計書コンポーネントの実在検証 |
| `kiro-validate-gap` | `@impl` タグ vs コードのギャップ検出 |
| `kiro-trace` | 仕様ID → コード影響トレース |
| `kiro-impact` | コード変更 → 仕様影響トレース |
| `kiro-validate-boundary` | `_Boundary:_` と CRG グラフの機械検証 |

### その他
- **8エージェント対応**: Claude Code, Codex, Cursor, Copilot, Gemini CLI, Windsurf, OpenCode, Antigravity
- **13言語対応**: `--lang` でテンプレートを選択可能
- **日本語テンプレート**: `--lang ja` で要件定義書・設計書・タスク計画を日本語で生成
- **pre-commit hook**: `setup-crg.sh` がコミット時のスナップショット自動更新を設定
- **CI/CD ゲート**: `python3 .agents/scripts/check_drift.py --diff --gate` で仕様ドリフトを自動検出

## ドキュメント

- [Package README (English)](./tools/cc-sdd/README.md)
- [Package README (日本語)](./tools/cc-sdd/README_ja.md)
- [Package README (繁體中文)](./tools/cc-sdd/README_zh-TW.md)
- [セットアップガイド](./.agents/scripts/README.md)

## ライセンス

MIT
