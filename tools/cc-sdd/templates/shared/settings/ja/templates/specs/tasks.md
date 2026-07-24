# 実装計画

## タスク形式テンプレート

タスクの構造に応じて適切なパターンを使用する:

### メジャータスクのみ
- [ ] {{NUMBER}}. {{TASK_DESCRIPTION}}{{PARALLEL_MARK}}
  - {{DETAIL_ITEM_1}} *(必要な場合のみ詳細を記載。タスクが単独で完結する場合は箇条書きを省略可)*
  - _Requirements: {{REQUIREMENT_IDS}}_

### メジャー＋サブタスク構造
- [ ] {{MAJOR_NUMBER}}. {{MAJOR_TASK_SUMMARY}}
- [ ] {{MAJOR_NUMBER}}.{{SUB_NUMBER}} {{SUB_TASK_DESCRIPTION}}{{SUB_PARALLEL_MARK}}
  - {{DETAIL_ITEM_1}}
  - {{DETAIL_ITEM_2}}
  - {{OBSERVABLE_COMPLETION_ITEM}} *(少なくとも1つの詳細項目に、このタスクの完了状態を観測可能な形で記載すること)*
  - _Requirements: {{REQUIREMENT_IDS}}_ *(IDのみ。説明や括弧は不要)*
  - _Boundary: {{COMPONENT_NAMES}}_ *((P)タスクのみ。スコープが明らかな場合は省略可)*
  - _Depends: {{TASK_IDS}}_ *(自明でないクロス境界依存関係のみ。ほとんどのタスクは省略)*

> **並列マーカー**: 並列実行可能なタスクにのみ ` (P)` を付与。`--sequential` モードではマーカーを省略。
>
> **オプションのテストカバレッジ**: サブタスクが受入基準に関連する先送り可能なテスト作業の場合、チェックボックスを `- [ ]*` とマークし、該当要件を詳細項目で説明すること。
