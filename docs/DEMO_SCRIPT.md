<!-- SPDX-License-Identifier: Apache-2.0 -->

# MainframeGhost Demo Video: 120-Second High-Impact Storyboard & Script

**Project:** MainframeGhost  
**Target Hackathon:** Kiroween 2026 (Category: *Resurrection*)  
**Target Duration:** 120 Seconds (Strict maximum: < 180s)  
**Output:** YouTube (Public)

---

## Technical Setup & Recording Layout

- **Screen Resolution:** 1920x1080 @ 60 FPS
- **Display Setup:** Side-by-side:
  - **Left 50%:** Kiro IDE / CLI with terminal showing live agent execution.
  - **Right 50%:** IBM 3278-2 Cockpit (`http://127.0.0.1:8737`) in full retro phosphor green (P31).

---

## Scene-by-Scene Breakdown

### Scene 1: The Banking Micro-Crisis (0:00 - 0:15)
- **Visual:** Terminal screen showing:
  > **Bank Modernization Failure:**
  > Python `Decimal` port with `ROUND_FLOOR` misposts $49.37 on 10,000 accounts.
- **Voiceover:**
  > *"Every day, global banks process trillions of dollars on COBOL mainframe batch jobs. As engineering teams use AI agents to modernize these systems to Python, a hidden catastrophe lurks in the bytes: COBOL truncation rules, COMP-3 packed decimals, and EBCDIC collation.*
  > *A port using binary floats or standard rounding passes code review, passes unit tests, and then misposts cents across millions of customer accounts.*
  > *Meet MainframeGhost: an autonomous Kiro PreToolUse governance gate that halts AI code generation before financial drift can ever be saved."*

---

### Scene 2: The Kiro Pipeline & The Live Veto (0:15 - 0:45)
- **Visual:** In Kiro IDE, the `cobol-porter` agent attempts to write a modernized interest accrual script (`services/vulnerable_service.py`) that uses `float()` and `round()`.
- **Action:** The moment Kiro initiates the `fs_write` tool call, the `.kiro/hooks/parity_guard.json` hook triggers:
  ```text
  [VETO] Mainframe Parity Sentinel: semantic drift or IEEE 754 precision violation detected.
  [FAIL] 5,383 / 10,000 accounts drifted from GnuCOBOL ground truth.
  Total misposted: $49.37.
  Tool call blocked with exit code 2. File write halted.
  ```
- **Voiceover:**
  > *"Here, our Kiro custom agent `cobol-porter` attempts to save a Python port using standard binary floats. Instantly, Kiro's `PreToolUse` hook intercepts the tool call.*
  > *In under two seconds, the sandboxed shadow fuzzer runs the code against real GnuCOBOL compiler output across 10,000 accounts. It detects 5,383 drifted balances, calculates the $49 mispost, and hard-aborts the write with exit code 2."*

---

### Scene 3: Autonomous Self-Correction via Kiro Steering (0:45 - 1:10)
- **Visual:** Kiro agent reads the hook's STDERR feedback and consults `.kiro/steering/cobol_parity.md`.
- **Action:** The agent refactors the code to use `decimal.Decimal` with `ROUND_DOWN` (exact COBOL truncation). The agent re-runs `fs_write`:
  ```text
  [PASS] 0 / 10,000 accounts differ from COBOL.
  [PASS] COMP-3 nibbles verified.
  [PASS] EBCDIC sort order verified.
  Verdict: APPROVED (exit 0). Write proceeds.
  ```
- **Voiceover:**
  > *"Because Kiro feeds the hook's stderr directly back into the agent's context, the agent sees the exact drifting records. Guided by our Kiro steering document, it refactors the math to `decimal.Decimal` with `ROUND_DOWN`.*
  > *The hook re-evaluates the edit: zero drift across 10,000 accounts, exact COMP-3 packed nibble parity, zero misposts. The write is approved."*

---

### Scene 4: The IBM 3270 CRT Cockpit & MCP Tools (1:10 - 1:40)
- **Visual:** Switch focus to the IBM 3278-2 retro cockpit running in browser (`http://127.0.0.1:8737`).
- **Action:**
  - Press **F9** to toggle from P31 green phosphor to P4 amber.
  - Navigate to **PF1 (Copybook Offsets)** and show the parsed 52-byte `INTACCR.cpy` layout with REDEFINES overlays.
  - Navigate to **PF6 (Engine Lab)** and live-unpack COMP-3 hex: `UNPACK 40404040 S9(5)V99`.
- **Voiceover:**
  > *"To give enterprise mainframe teams complete visibility, MainframeGhost features a pixel-accurate IBM 3270 CRT terminal cockpit built in React 19.*
  > *Through our FastMCP server, teams can inspect copybook byte offsets, decode COMP-3 hex dumps, monitor S0C7 abends, and audit candidate code in real time."*

---

### Scene 5: Mathematical Rigor & Architecture (1:40 - 1:55)
- **Visual:** Terminal running pytest:
  ```bash
  pytest -q
  # 100 passed in 28.51s
  ```
- **Voiceover:**
  > *"MainframeGhost is backed by 100 passing tests, including Hypothesis property-based testing over random packed decimals and zoned signs. Built on Kiro hooks, specs, steering, custom agents, and MCP, it turns days of manual ledger triage into a 60-second automated veto."*

---

### Scene 6: Outro (1:55 - 2:00)
- **Visual:** End card displaying:
  > **MainframeGhost: Bringing Mainframes Back to Life Safely**  
  > Hackathon: Kiroween 2026 (Category: *Resurrection*)  
  > GitHub: `github.com/Divyanshu-Kumar14/mainframe-ghost`
- **Voiceover:**
  > *"Zero ledger drift. Zero financial corruption. Mainframe modernization you can trust."*
