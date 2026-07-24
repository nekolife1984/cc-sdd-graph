# Agentic SDLC and Spec-Driven Development

Kiro-style Spec-Driven Development on an agentic SDLC

## CRG MCP Tools (code-review-graph)

This project integrates **code-review-graph (CRG)** MCP tools for code-graph-aware impact analysis across all phases:

- **kiro-spec-design**: Uses `get_architecture_overview_tool`, `semantic_search_nodes_tool`, `query_graph_tool` during codebase analysis
- **kiro-spec-tasks**: Validates `_Boundary:_` annotations against `get_impact_radius_tool`
- **kiro-review**: Enhanced Boundary Respect check with CRG impact radius verification
- **kiro-validate-impl**: Uses `get_affected_flows_tool` for cross-task integration validation
- **kiro-debug**: Uses `query_graph_tool` and `get_impact_radius_tool` for root cause investigation
- **kiro-trace**: Traces spec changes to code impact
- **kiro-impact**: Traces code changes back to affected specs
- **kiro-validate-boundary**: Mechanically verifies `_Boundary:_` against CRG graph

## Traceability

Projects can maintain a `.trace-mapping.yaml` file linking spec IDs to code files, symbols, tasks, and docs.
Scripts in `.agents/scripts/` provide automated impact analysis:

| Script | Purpose |
|--------|---------|
| `extract_tags.py` | Extract `@impl`/`@module`/`@feature`/`@verifies` from code, `@spec`/`@design`/`@satisfies` from spec docs |
| `impact.py` | Bidirectional spec\u2194code impact analysis (`--quick` for grep-based mode without .trace-mapping.yaml) |
| `check_drift.py` | Snapshot-based drift detection between code and specs |
| `check-trace-completeness.py` | **Gate**: Verify @impl, code.files, code.symbols, @module, _Requirements:_, _Depends:_, @spec, @design, @satisfies, and @verifies traceability |

## Project Context

### Paths
- Steering: `.kiro/steering/`
- Specs: `.kiro/specs/`

### Steering vs Specification

**Steering** (`.kiro/steering/`) - Guide AI with project-wide rules and context
**Specs** (`.kiro/specs/`) - Formalize development process for individual features

### Active Specifications
- Check `.kiro/specs/` for active specifications
- Use `/kiro-spec-status [feature-name]` to check progress

## Development Guidelines
- Think in English, generate responses in English. All Markdown content written to project files (e.g., requirements.md, design.md, tasks.md, research.md, validation reports) MUST be written in the target language configured for this specification (see spec.json.language).

## Minimal Workflow
- Phase 0 (optional): `/kiro-steering`, `/kiro-steering-custom`
- Discovery: `/kiro-discovery "idea"` — determines action path, writes brief.md + roadmap.md for multi-spec projects
- Phase 1 (Specification):
  - Single spec: `/kiro-spec-quick {feature} [--auto]` or step by step:
    - `/kiro-spec-init "description"`
    - `/kiro-spec-requirements {feature}`
    - `/kiro-validate-gap {feature}` (optional: for existing codebase)
    - `/kiro-spec-design {feature} [-y]`
    - `/kiro-validate-design {feature}` (optional: design review)
    - `/kiro-spec-tasks {feature} [-y]`
  - Multi-spec: `/kiro-spec-batch` — creates all specs from roadmap.md in parallel by dependency wave
- Phase 2 (Implementation): `/kiro-impl {feature} [tasks]`
  - Without task numbers: autonomous mode (subagent per task + independent review + final validation)
  - With task numbers: manual mode (selected tasks only in main context)
  - `/kiro-validate-impl {feature}` (standalone re-validation)
- Progress check: `/kiro-spec-status {feature}` (use anytime)

## Skills Structure
Skills are located in `.claude/skills/kiro-*/SKILL.md`
- Each skill is a directory with a `SKILL.md` file
- Skills run inline with access to conversation context
- Skills may delegate parallel research to subagents for efficiency
- Additional files (templates, examples) can be added to skill directories
- `kiro-review` — task-local adversarial review protocol used by reviewer subagents
- `kiro-debug` — root-cause-first debug protocol used by debugger subagents
- `kiro-verify-completion` — fresh-evidence gate before success or completion claims
- **If there is even a 1% chance a skill applies to the current task, invoke it.** Do not skip skills because the task seems simple.

## Development Rules
- 3-phase approval workflow: Requirements → Design → Tasks → Implementation
- Human review required each phase; use `-y` only for intentional fast-track
- Keep steering current and verify alignment with `/kiro-spec-status`
- Follow the user's instructions precisely, and within that scope act autonomously: gather the necessary context and complete the requested work end-to-end in this run, asking questions only when essential information is missing or the instructions are critically ambiguous.

## Steering Configuration
- Load entire `.kiro/steering/` as project memory
- Default files: `product.md`, `tech.md`, `structure.md`
- Custom files are supported (managed via `/kiro-steering-custom`)
