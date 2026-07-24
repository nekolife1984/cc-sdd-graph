# 要件定義書

## はじめに
{{INTRODUCTION}}

<!-- スコープの誤解を防ぐために必要に応じて記載 -->
## 境界コンテキスト（任意）
- **スコープ内**: {{IN_SCOPE_BEHAVIORS}}
- **スコープ外**: {{OUT_OF_SCOPE_BEHAVIORS}}
- **隣接する期待**: {{ADJACENT_SYSTEM_OR_SPEC_EXPECTATIONS}}

## 要件

### 要件 1: {{REQUIREMENT_AREA_1}}
<!-- 要件の見出しには数値IDのみを含めること（例: "要件 1: ..."）。アルファベッドのID（"要件 A"等）は禁止。 -->
**目的:** {{ROLE}}として、{{CAPABILITY}}したい、それにより{{BENEFIT}}

#### 受け入れ基準
1. When [イベント], the [システム] shall [応答/動作]
2. If [トリガー], then the [システム] shall [応答/動作]
3. While [前提条件], the [システム] shall [応答/動作]
4. Where [機能], the [システム] shall [応答/動作]
5. The [システム] shall [応答/動作]

### 要件 2: {{REQUIREMENT_AREA_2}}
**目的:** {{ROLE}}として、{{CAPABILITY}}したい、それにより{{BENEFIT}}

#### 受け入れ基準
1. When [イベント], the [システム] shall [応答/動作]
2. When [イベント] and [条件], the [システム] shall [応答/動作]

<!-- 以降の要件も同パターン -->
