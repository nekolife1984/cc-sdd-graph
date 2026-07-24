# 4-Fixture テスト基盤
#
# 各 false-green ベクターに対して4種類の fixture を用意する。
# これらの fixture を全パスすることで verifier が正しく動作していることを確認する。
#
# Fixture types:
#   green_control:        正常系 ― 必ず PASS すべき
#   false_green_candidate:偽成功 ― 検出して RED にすべき
#   false_red_guard:      偽失敗 ― 決して RED にしてはいけない
#   legacy_backcompat:    後方互換 ― 既存の正しいコードが壊れていないか

## P0-1: impl_tag_orphan

### green_control
```python
# @impl 1.1
def login():
    return "login ok"
```
→ coverage run でこのファイルがヒットされる → PASS

### false_green_candidate
```python
# @impl 1.2
def unused_function():
    return "never called"
```
→ このコードはどのテストからも呼ばれない → coverage 未ヒット → RED

### false_red_guard
```python
# @impl 1.3
def helper():
    return "called"
```
→ テストから呼ばれる → coverage ヒット → GREEN（通報してはいけない）

### legacy_backcompat
```python
# @impl 1.4
def old_api():
    return "legacy"
```
→ 既存のカバレッジレポートでこのファイルが緑である → 変更後も緑

---

## P0-2: verifies_empty_assert

### green_control
```python
# @verifies 1.1
def test_login():
    result = login()
    assert result == "login ok"
```
→ 実アサーションあり → PASS

### false_green_candidate
```python
# @verifies 1.2
def test_login():
    result = login()
    # assert result == "login ok"  ← コメントアウト
    pass
```
→ 実アサーションなし → RED

### false_red_guard
```python
# @verifies 1.3
def test_complex():
    # pytest.approx を使った高度なアサーション
    import pytest
    assert {"a": 1} == pytest.approx({"a": 1.0001})
```
→ アサーション存在（見逃してはいけない） → GREEN

### legacy_backcompat
```python
# @verifies 1.4
from pytest import approx

def test_legacy():
    assert 1 + 1 == 2
```
→ 既存プロジェクトで動いているテスト → 変更後も GREEN

---

## P0-3: mapping_stale

### green_control
```yaml
# .trace-mapping.yaml (一部)
mappings:
  - id: "1.1"
    code:
      files: ["src/recently_updated.py"]
```
→ recently_updated.py が直近90日以内に変更 → PASS

### false_green_candidate
```yaml
mappings:
  - id: "2.1"
    code:
      files: ["src/unmodified.py"]
```
→ unmodified.py が90日以上未変更 → RED

### false_red_guard
```yaml
mappings:
  - id: "3.1"
    tags: ["@frozen"]
    code:
      files: ["src/stable.py"]
```
→ @frozen タグで明示的に除外 → GREEN（通報してはいけない）

### legacy_backcompat
```yaml
mappings:
  - id: "4.1"
    description: "Long-standing feature"
    code:
      files: ["src/established.py"]
```
→ 既存の安定したマッピング → 変更後も GREEN
