# False-Green Detection Matrix

cc-sdd-graph の検証器（verifier）強靭化状況を示すマトリクス。

最終測定: 2026-07-25

## マトリクス

| Vector | Pri | Owner Gate | Status | Detection | Check CLI |
|--------|:---:|:----------:|:------:|:---------:|-----------|
| impl_tag_orphan | P0 | No | shipped | caught_amber | `--check coverage` |
| verifies_empty_assert | P0 | No | shipped | caught_amber | `--check assertions` |
| mapping_stale | P0 | No | shipped | caught_amber | `--check stale` |
| ci_gate_bypassed | P0 | Yes | **shipped** | **caught_amber** | `check-ci-bypass.py` |
| spec_no_test_coverage | P1 | No | planned | missed_green | `--coverage` |
| snapshot_missing_update | P1 | No | planned | missed_green | pre-commit skip 検知 |
| cross_language_tag_mismatch | P1 | No | planned | missed_green | `--cross-ref` |
| mapping_no_description | P2 | Yes | planned | missed_green | `--check-descriptions` |
| spec_in_design_not_mapped | P2 | No | planned | missed_green | チェック8（部分的） |

## 充足条件（Saturation）

全 P0 ベクターが出荷済み。P1 以降の saturation を目指す:

| 条件 | 状態 |
|------|:----:|
| 4-fixture 完備 | 🟡 ガイド作成済み（`quality/4-fixtures-guide.md`） |
| **P0 kill rate 100%** | 🟢 **4/4 shipped**（coverage, assertions, stale, ci_bypass） |
| P1 kill rate ≥95% | 🔴 未着手 |
| control/legacy false-red = 0 | 🟡 未検証 |
| 連続2回の discovery で新規 missed_green なし | 🟡 初回 discovery 未実施 |

## 測定コマンド

```bash
# P0-1: @impl orphan 検出率
python3 -m pytest tests/quality/test_vector_impl_tag_orphan.py -q

# P0-2: verifies empty assert 検出率
python3 -m pytest tests/quality/test_vector_verifies_empty_assert.py -q

# P0-3: stale mapping 検出率
python3 -m pytest tests/quality/test_vector_mapping_stale.py -q
```
