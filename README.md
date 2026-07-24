# cc-sdd-graph

A fork of [cc-sdd](https://github.com/gotalab/cc-sdd) that integrates **code-review-graph (CRG)** for bidirectional spec↔code traceability. Automatically track requirements to code via `@impl` tags, analyze impact scope, and detect spec drift.

## Quick Start

### macOS / Linux
```bash
bash <(curl -s https://raw.githubusercontent.com/nekolife1984/cc-sdd-graph/main/scripts/quickstart.sh)
```

### Windows (PowerShell)
```powershell
Invoke-WebRequest -Uri https://raw.githubusercontent.com/nekolife1984/cc-sdd-graph/main/scripts/quickstart.ps1 -OutFile quickstart.ps1
.\quickstart.ps1
```

The script automates:
1. Install cc-sdd-graph skills (choose agent & language)
2. Install and configure code-review-graph
3. Build the initial code graph
4. Initialize `.trace-mapping.yaml`
5. Set up pre-commit hook (auto snapshot on every commit)
6. Save initial snapshot

## Manual Setup

```bash
# Skills only
npx github:nekolife1984/cc-sdd-graph

# CRG only (after skills install)
bash .agents/scripts/setup-crg.sh --yes
```

## Features

### 20 kiro Skills
| Phase | Skills |
|-------|--------|
| Discovery | `kiro-discovery`, `kiro-steering` |
| Specification | `kiro-spec-init`, `kiro-spec-requirements`, `kiro-spec-design`, `kiro-spec-tasks` |
| Batch | `kiro-spec-batch`, `kiro-spec-quick` |
| Implementation | `kiro-impl` |
| Review | `kiro-review`, `kiro-validate-design`, `kiro-validate-gap`, `kiro-validate-impl` |
| Debug | `kiro-debug` |
| Completion | `kiro-verify-completion` |
| Status | `kiro-spec-status` |
| **CRG Traceability** | **`kiro-trace`**, **`kiro-impact`**, **`kiro-validate-boundary`** |

### CRG-Enhanced Skills (15 of 20)
Most skills integrate with code-review-graph for graph-aware code analysis:

| Skill | CRG Integration |
|-------|----------------|
| `kiro-discovery` | Auto-assess impact scope when extending existing specs |
| `kiro-spec-design` | Code graph analysis to inform architecture design |
| `kiro-spec-tasks` | Machine-verify `_Boundary:_` against actual code graph |
| `kiro-spec-init` | Auto-generate `.trace-mapping.yaml` skeleton |
| `kiro-spec-batch` | Auto-generate `.trace-mapping.yaml` for all specs |
| `kiro-review` | CRG-enhanced boundary respect check |
| `kiro-impl` | Auto-scan `@impl` tags and update `.trace-mapping.yaml` |
| `kiro-validate-impl` | CRG flow validation |
| `kiro-debug` | CRG graph investigation |
| `kiro-verify-completion` | CRG architecture alignment check |
| `kiro-validate-design` | Verify design components exist in code |
| `kiro-validate-gap` | Detect code without spec / spec without code |
| `kiro-trace` | Spec ID → code impact trace |
| `kiro-impact` | Code change → spec impact trace |
| `kiro-validate-boundary` | Machine-verify `_Boundary:_` vs CRG graph |

### Other
- **8 agents**: Claude Code, Codex, Cursor, Copilot, Gemini CLI, Windsurf, OpenCode, Antigravity
- **13 languages**: Templates rendered in your chosen language via `--lang`
- **Japanese templates**: `--lang ja` for requirements, design, and tasks in Japanese
- **Pre-commit hook**: Auto-updates traceability snapshot on every commit (set up by `setup-crg.sh`)
- **CI/CD gate**: `python3 .agents/scripts/check_drift.py --diff --gate` detects spec drift in CI

## Documentation

- [Package README (English)](./tools/cc-sdd/README.md)
- [Package README (日本語)](./tools/cc-sdd/README_ja.md)
- [Package README (繁體中文)](./tools/cc-sdd/README_zh-TW.md)
- [Setup Guide](./.agents/scripts/README.md)

## License

MIT
