---
name: kiro-validate-boundary
description: Verify _Boundary:_ annotations against CRG code graph. Detect narrow, wide, or missing boundary definitions across all tasks.
---

# kiro-validate-boundary — Boundary Validation

<background_information>
This skill performs **task boundary vs. actual code graph verification**. It uses CRG (code-review-graph) to mechanically check whether `_Boundary:_` annotations in tasks.md match actual code dependencies.

- **Success Criteria**:
  - All `_Boundary:_` annotations are validated against CRG impact radius
  - Narrow boundaries (actual impact wider than declared) are detected
  - Wide boundaries (declared scope broader than actual) are detected
  - Undeclared dependencies missing from `_Depends:_` are detected
  - `.trace-mapping.yaml` consistency with `@impl` tags is verified
</background_information>

<instructions>

## Step 1: Load Context

1. Verify `.kiro/specs/$1/tasks.md` exists
2. If `$1` is empty, scan all features in `.kiro/specs/`
3. Extract all `_Boundary:_` annotations from tasks.md
4. Read `.trace-mapping.yaml`

## Step 2: CRG Code Graph Verification

For each `_Boundary:_` annotation:

1. Extract component/symbol name from the boundary value
2. `semantic_search_nodes_tool` — locate the symbol in code
3. `get_impact_radius_tool` — get actual graph impact scope
4. Compare CRG impact radius files against boundary-declared files

## Step 3: Aggregate Results

Rate each `_Boundary:_`:

| Rating | Meaning | Action |
|--------|---------|--------|
| ✅ CONSISTENT | CRG graph matches boundary | None |
| ⚠️ NARROW | Boundary is narrower than actual | Update tasks.md |
| ⚠️ WIDE | Boundary is wider than needed | Simplify annotation |
| ❌ UNDEFINED | Symbol not found in CRG graph | Fix spec |

## Step 4: Generate Report

```md
## Boundary Validation Report: {feature}

### Summary
- Total _Boundary:_ annotations: N
- ✅ CONSISTENT: N
- ⚠️ NARROW: N
- ⚠️ WIDE: N
- ❌ UNDEFINED: N

### Detail
#### Task X.Y — _Boundary: ComponentA_
- Status: ⚠️ NARROW
- CRG impact radius: file_a.py, file_b.py, file_c.py
- _Boundary:_ declared: file_a.py
- Missing: file_b.py (implicit dep), file_c.py (import chain)
```

## Step 5: Auto-Fix (Optional)

If user explicitly requests auto-fix (`--fix`):
1. Expand narrow `_Boundary:_` to match CRG impact
2. Add discovered deps to `_Depends:_`
3. Update `.trace-mapping.yaml`

</instructions>

## Critical Constraints

- Default is **read-only** mode. Auto-fix only on explicit request.
- If CRG is unavailable, report and run basic `.trace-mapping.yaml` validation only.

## Usage

```
/kiro-validate-boundary photo-albums
/kiro-validate-boundary                     # scan all features
/kiro-validate-boundary photo-albums --fix  # auto-fix mode
```
