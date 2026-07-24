# cc-sdd-graph

cc-sdd をフォークし、**code-review-graph (CRG)** による仕様↔コードのトレーサビリティを統合したバージョン。

## Quick Start

```bash
# ワンコマンドで全部入り
bash <(curl -s https://raw.githubusercontent.com/nekolife1984/cc-sdd-graph/main/scripts/quickstart.sh)
```

このスクリプトが以下を自動で行います:
1. cc-sdd-graph スキルのインストール（エージェント・言語を選択）
2. code-review-graph のインストールと MCP 設定
3. コードグラフの初回ビルド
4. `.trace-mapping.yaml` の初期化
5. 初回スナップショットの保存

## 個別セットアップ

```bash
# スキルのみ
npx github:nekolife1984/cc-sdd-graph

# CRG のみ（スキルインストール後）
bash .agents/scripts/setup-crg.sh --yes
```

## 特徴

- **17の kiro スキル**: discovery / spec / design / tasks / impl / review / debug / validate
- **CRG トレーサビリティ**: `kiro-trace`, `kiro-impact`, `kiro-validate-boundary`
- **8エージェント対応**: Claude Code, Codex, Cursor, Copilot, Gemini CLI, Windsurf, OpenCode, Antigravity
- **多言語**: English / 日本語 / 繁體中文 など13言語
- **日本語テンプレート**: `--lang ja` で日本語の要件定義書・設計書・タスク計画を生成

## ドキュメント

- [Package README (English)](./tools/cc-sdd/README.md)
- [Package README (日本語)](./tools/cc-sdd/README_ja.md)
- [Package README (繁體中文)](./tools/cc-sdd/README_zh-TW.md)
- [セットアップスクリプト](./scripts/quickstart.sh)
- [CRG セットアップ詳細](./.agents/scripts/README.md)

## License

MIT
