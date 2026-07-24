---
name: kiro-trace
description: Trace spec changes to codebase impact. Uses .trace-mapping.yaml + CRG (code-review-graph) to find affected files, symbols, and tasks.
---

# kiro-trace — Spec Change Impact Trace

<background_information>
This skill performs **spec-originated impact analysis**. When a specific requirement in requirements.md changes, it identifies which code files, symbols, tasks, and documents are affected by combining `.trace-mapping.yaml` with the CRG (code-review-graph) code graph.

- **Success Criteria**:
  - All code files matching the spec ID are identified
  - CRG graph covers transitive imports beyond direct matches
  - Impact is categorized into files, symbols, tasks, and docs
  - `.trace-mapping.yaml` maintenance gaps are flagged
</background_information>

<instructions>

## Step 1: Load Context

1. If `.trace-mapping.yaml` exists:
   - Read `.trace-mapping.yaml`
   - Run `python3 .agents/scripts/impact.py --spec-id $1 --json` for baseline impact
2. If `.trace-mapping.yaml` does NOT exist → fall back to `--quick` mode:
   ```bash
   python3 .agents/scripts/impact.py --quick --spec-id $1 --project-dir .
   ```
   Quick mode greps `@impl`/`@verifies`/`@spec` tags directly from the codebase.
3. **DAG transitive mode** (CRG replacement): If CRG MCP is not available but
   `.kiro/graph/dag.json` exists:
   ```bash
   python3 .agents/scripts/impact.py --spec-id $1 --dag
   ```
   This traces transitive imports (17 languages, including C/C++/C# with `// @impl`).
4. Extract spec ID from argument `$1` (e.g., `1.1`, `6.2`).

## Step 2: CRG Code Graph Investigation

For each impacted symbol, call CRG MCP tools:

1. `query_graph_tool` — get callers and callees of each symbol
2. `get_impact_radius_tool` — get blast radius of the change
3. `semantic_search_nodes_tool` — discover other symbols related to this spec

## Step 3: Generate Impact Report

Output a structured report with band analysis:

```md
## Trace Report: Spec {spec-id}
- SPEC: .kiro/specs/{feature}/requirements.md#{section}

### Band Summary
- 🟢 GREEN (auto-approve): N files (mapping + @impl + tests)
- 🟡 AMBER (review required): N files (partial evidence)
- ⚪ GRAY (reference only): N files (weak match)

### Direct Impact (.trace-mapping.yaml)
| Category | Count | List |
|----------|-------|------|
| Code files | N | file1.py, file2.py |
| Symbols | N | Class.method |
| Tasks | N | X.Y |
| Docs | N | design.md#section |

### CRG Transitive Impact (import chain)
| Symbol | Callers | Callees | Blast Radius |
|--------|---------|---------|-------------|
| SymbolA | Caller1, Caller2 | CalleeX | medium |

### Recommended Actions
- Implement/fix affected tasks: `/kiro-impl {feature} {task-id}`
- Update affected docs: .kiro/specs/{feature}/
- Check drift after changes: `python3 .agents/scripts/check_drift.py --snapshot`
- Filter by band: `python3 .agents/scripts/impact.py --spec-id {spec-id} --band amber+`
```

## Step 4: Flag Unregistered Impacts

Compare CRG impact radius against `.trace-mapping.yaml` file list. Report any files in the graph but not in the mapping as `WARNING: .trace-mapping.yaml may be out of date`.

</instructions>

## Critical Constraints

- This skill is **read-only**. Do not modify files.
- `.trace-mapping.yaml` is the source of truth, but a wider CRG impact radius indicates the mapping may need maintenance.

## Usage

```
/kiro-trace 1.1
/kiro-trace 6.1
```
