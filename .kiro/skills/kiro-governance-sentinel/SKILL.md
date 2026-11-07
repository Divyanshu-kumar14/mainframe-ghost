---
name: kiro-governance-sentinel
description: Deep expertise in Kiro native architecture, including EARS specification syntax (.kiro/specs/), deterministic steering files (.kiro/steering/), Model Context Protocol integration (.kiro/mcp/), custom agents (.kiro/agents/), and native v2 PreToolUse execution hooks (.kiro/hooks/) that enforce POSIX Exit Code 2 deployment vetoes. Use whenever configuring, debugging, or authoring Kiro governance primitives.
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
└── agents/
    ├── cobol-porter.md      # writes services; denied write access to hooks/fixtures
    └── parity-auditor.md    # read-only; audits through the MCP tools
```

Kiro Crew is a separate local app; its docs describe no repository-level crew file, so none is kept here.

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
      "description": "Intercepts tool execution, runs the proposed code against GnuCOBOL output, and vetoes with POSIX Exit Code 2 on semantic drift.",
      "trigger": "PreToolUse",
      "matcher": "^(fs_write|fs_append|str_replace|execute_bash)$|deploy_lambda",
      "action": {
        "type": "command",
        "command": ".kiro/hooks/bin/verify_modernization_parity.sh"
      },
      "timeout": 30,
      "enabled": true
    }
  ]
}
```

### The POSIX Exit Code 2 Contract
When Kiro invokes a `PreToolUse` command hook:
- The hook receives the tool execution payload via **STDIN**.
- **Exit Code 0:** Execution approved. Kiro proceeds with the tool call.
- **Exit Code 2 (HARD VETO):** Execution rejected. Kiro aborts the tool call, displays the error message output by the script in the chat pane, and commands the agent to fix the violation.
- **Any other non-zero code:** non-blocking warning in Kiro. Never map drift to exit 1.

Notes: built-in tool IDs are snake_case (`fs_write`, `fs_append`, `str_replace`, `execute_bash`); `timeout` is a sibling of `action`; hooks load at session start.

### Hook Script

The real script is `.kiro/hooks/bin/verify_modernization_parity.sh`. Its shape:

1. Read the payload from STDIN.
2. If `engine/shadow_fuzzer.py` is missing, exit 2 (fail closed).
3. Pipe the payload to `python3 engine/shadow_fuzzer.py --verify-stdin`, which scans the proposed file, rebuilds it post-write, executes it in a sandbox and diffs it against `cobol/fixtures/`.
4. Map the fuzzer's exit code: 0 to `[PASS] ... against the GnuCOBOL oracle` (exit 0), 2 to `[VETO]` on STDERR (exit 2), anything else to `[ERROR]` (exit 1).

Never edit the hook, the fixtures or the golden vectors to make a write pass.
