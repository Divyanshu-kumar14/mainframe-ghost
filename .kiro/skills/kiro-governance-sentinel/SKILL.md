---
name: kiro-governance-sentinel
description: Deep expertise in Kiro native architecture, including EARS specification syntax (.kiro/specs/), deterministic steering files (.kiro/steering/), Model Context Protocol integration (.kiro/mcp/), multi-agent crew definitions (.kiro/crew/), and native v2 PreToolUse execution hooks (.kiro/hooks/) that enforce POSIX Exit Code 2 deployment vetoes. Use whenever configuring, debugging, or authoring Kiro governance primitives.
---

# Kiro Governance & Parity Sentinel Skill

This skill provides expert patterns for building zero-trust governance architectures inside Kiro IDE.

---

## 1. Kiro Directory Topology

A production-grade Kiro workspace enforces safety through the `.kiro/` directory structure:

```
.kiro/
├── specs/                   # Formal EARS requirements & design
│   └── mainframe_parity/
│       ├── requirements.md  # EARS format (When/While/Where/If/The system shall)
│       ├── design.md        # Architecture, byte maps, and mathematical formulas
│       └── tasks.md         # Deterministic sprint tasks for Kiro Spec Runner
├── steering/                # Agent behavioral governance
│   └── cobol_parity.md      # Frontmatter: "inclusion: always" or "inclusion: auto"
├── hooks/                   # Runtime event hooks
│   ├── parity_guard.json    # Kiro v2 hook configuration (PreToolUse trigger)
│   └── bin/
│       └── verify_modernization_parity.sh  # Executable hook (Exit Code 2 veto)
├── mcp/                     # Model Context Protocol servers
│   └── server.py            # FastMCP copybook and memory inspection server
├── settings/
│   └── mcp.json             # MCP server registrations
└── crew/
    └── crew.yaml            # Multi-agent crew topology & roles
```

---

## 2. Formal EARS Specification Syntax

Requirements in `.kiro/specs/` must strictly follow the **Easy Approach to Requirements Syntax (EARS)**:

- **Ubiquitous:** "The system shall [action]"
- **Event-Driven:** "*When* [trigger occurs], the system *shall* [action]"
- **State-Driven:** "*While* [in state], the system *shall* [action]"
- **Optional Feature:** "*Where* [feature is included], the system *shall* [action]"
- **Unwanted Behavior:** "*If* [error/condition], *then* the system *shall* [action]"

### Example EARS Requirement
```markdown
### REQ-MF-001: Arbitrary Precision Decimal Scale
*When* executing monetary or balance sheet computations, the transpiled system *shall* compute results using fixed-point arbitrary precision decimal arithmetic matching the scale and precision of the original COBOL `PIC` declaration.

### REQ-MF-004: Zero-Trust Deployment Veto
*Where* transpiled cloud code exhibits arithmetic drift, floating-point contamination, or S0C7 invalid nibbles, the Kiro PreToolUse hook *shall* abort deployment and terminate with POSIX Exit Code 2.
```

---

## 3. Kiro Native v2 Hooks (`.kiro/hooks/`)

Kiro v2 hooks execute directly before or after IDE events.

### Hook Triggers
- `PreToolUse`: Fires before an agent executes a tool call (ideal for security gates and deployment vetoes).
- `PostToolUse`: Fires after a tool completes.
- `PostFileSave`: Fires whenever a file is saved.
- `SessionStart`: Fires when a new agent session begins.

### Hook JSON Schema (`.kiro/hooks/parity_guard.json`)
```json
{
  "version": "v1",
  "hooks": [
    {
      "name": "Mainframe Parity Sentinel Guard",
      "description": "Intercepts tool execution, runs dual-engine parity fuzzer, and halts with Exit Code 2 on semantic drift.",
      "trigger": "PreToolUse",
      "matcher": ".*(deploy_lambda|write_to_file|edit_file|bash).*",
      "action": {
        "type": "command",
        "command": ".kiro/hooks/bin/verify_modernization_parity.sh",
        "timeout": 30
      }
    }
  ]
}
```

### The POSIX Exit Code 2 Contract
When Kiro invokes a `PreToolUse` command hook:
- The hook receives the tool execution payload via **STDIN**.
- **Exit Code 0:** Execution approved. Kiro proceeds with the tool call.
- **Exit Code 2 (HARD VETO):** Execution rejected. Kiro aborts the tool call, displays the error message output by the script in the chat pane, and commands the agent to fix the violation.
- **Exit Code 1:** Script runtime error / crash.

### Bash Hook Script (`.kiro/hooks/bin/verify_modernization_parity.sh`)
```bash
#!/usr/bin/env bash
set -euo pipefail

# Ingest proposed tool payload from STDIN
INPUT_PAYLOAD=$(cat || echo "{}")

# Run shadow fuzzer test
if ! python3 engine/shadow_fuzzer.py --verify-stdin <<< "$INPUT_PAYLOAD" 2>&1; then
    echo "[VETO] Mainframe Parity Sentinel: Detected semantic drift or IEEE 754 precision violation!" >&2
    echo "[VETO] Halting deployment pipeline to prevent ledger corruption." >&2
    exit 2
fi

echo "[PASS] Parity verified: 0.00000% drift against IBM z/OS golden records."
exit 0
```
