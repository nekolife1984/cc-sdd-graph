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

1. Verify `.trace-mapping.yaml` exists.
2. Interpret target from `$1`:
   - File path (e.g., `src/ui/chat.py`) → single file analysis
   - `.` or `--diff` → git diff analysis
   - Empty → auto-detect files from last `/kiro-impl`

## Step 2: Code→Spec Trace

1. Run `python3 .agents/scripts/impact.py --file <path> --json` for baseline
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

### Affected Requirements
| ID | Description | Priority |
|----|-------------|----------|
| 1.1 | Message send and response | 🔴 Direct |
| 2.1 | Streaming response | 🟡 Indirect (CRG) |

### Affected Tasks
- X.Y — task description

### Affected Design Sections
- design.md#section-name
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
