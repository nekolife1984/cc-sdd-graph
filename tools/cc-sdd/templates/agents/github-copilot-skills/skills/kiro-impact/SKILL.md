---
name: kiro-impact
description: Trace code changes back to affected specs, requirements, and design documents. Uses CRG MCP + .trace-mapping.yaml for bidirectional traceability.
---

# kiro-impact — Code Change Impact Analysis

<background_information>
This skill performs **code-originated impact analysis**. When a specific file or git diff changes, it identifies which specs, requirements, tasks, and design sections are affected by combining `.trace-mapping.yaml` with the CRG (code-review-graph) code graph.

- **Success Criteria**:
  - Files with `@impl` tags map to their requirements
  - Files without `@impl` tags find indirect spec relations via CRG
  - Impact is categorized into requirements, tasks, and design sections
  - `.trace-mapping.yaml` maintenance gaps are reported
</background_information>

<instructions>

## Step 1: Load Context

1. If `.trace-mapping.yaml` exists → use standard impact analysis (Steps 2-4)
2. If `.trace-mapping.yaml` does NOT exist → fall back to `--quick` mode:
   ```bash
   python3 .agents/scripts/impact.py --quick --file <path> --project-dir .
   ```
   Quick mode greps `@impl`/`@spec`/`@verifies` tags directly from the codebase
   without a mapping file (brownfield-friendly).
3. **DAG transitive mode** (CRG replacement): If CRG MCP is not available but
   `.kiro/graph/dag.json` exists, use `--dag` for transitive import analysis:
   ```bash
   python3 .agents/scripts/impact.py --spec-id 1.1 --dag
   ```
   Build DAG with: `python3 .agents/scripts/build-dag.py`
   Supports 17 languages including C/C++/C# (// @impl syntax).
4. Interpret target from `$1`:
   - File path (e.g., `src/ui/chat.py`) → single file analysis
   - `.` or `--diff` → git diff analysis
   - Empty → auto-detect files from last `/kiro-impl`

## Step 2: Code→Spec Trace

1. Run `python3 .agents/scripts/impact.py --file <path> --json` for baseline
   (or `--quick --file <path> --json` if no `.trace-mapping.yaml`)
2. If empty (unregistered in `.trace-mapping.yaml`), check code for `@impl` tags:
   - Run `python3 .agents/scripts/extract_tags.py --file <path> --format json`
   - If `@impl` found → warn that mapping entry is missing
   - If no tags → use CRG for indirect spec relations

## Step 3: CRG Indirect Trace

For files without direct mapping:

1. `query_graph_tool` — find callers of the changed code
2. Check caller files for `@impl` tags
3. `semantic_search_nodes_tool` — find related symbols
4. Reverse-lookup found symbols in `.trace-mapping.yaml`

## Step 4: Generate Impact Report

```md
## Impact Report: {file-path}
- QUERY_TYPE: file | diff | auto

### Band Summary
- 🟢 GREEN (auto-approve): N items (mapping + impl + tests)
- 🟡 AMBER (review required): N items (partial evidence)
- ⚪ GRAY (reference only): N items (weak match)

### Affected Requirements
| ID | Description | Priority |
|----|-------------|----------|
| 1.1 | Message send and response | 🔴 Direct |
| 2.1 | Streaming response | 🟡 Indirect (CRG) |
```

Band scoring:
- **GREEN** (≥50pts): .trace-mapping entry + @impl tag + tests
- **AMBER** (≥20pts): CRG transitive dep or partial grep match
- **GRAY** (<20pts): weak reference (full-text hit only)

Filter by band:
```bash
impact.py --spec-id 1.1 --band amber+    # show only amber+ items
impact.py --quick --diff --band green     # show only green items
```

## Step 5: Suggest `.trace-mapping.yaml` Updates

If `@impl` tags exist without mapping entries, or CRG shows strong relations without mapping, suggest updates.

</instructions>

## Critical Constraints

- This skill is **read-only**. Do not modify files.
- In diff mode, run impact analysis per changed file.

## Usage

```
/kiro-impact src/ui/chat.py
/kiro-impact --diff
/kiro-impact .
```
