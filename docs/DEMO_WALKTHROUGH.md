<!-- SPDX-License-Identifier: Apache-2.0 -->

# MainframeGhost: Interactive Demo & Evaluator Walkthrough

**Project:** MainframeGhost  
**Target Hackathon:** Kiroween 2026 (Category: *Resurrection*)  
**Audience:** Hackathon judges, banking modernization architects, security evaluators  

---

## Overview

This guide provides a self-contained, 60-second interactive evaluation walkthrough for **MainframeGhost**. You can test the Kiro `PreToolUse` parity gate, trigger real exit code 2 vetos against floating-point drift, and interact with the IBM 3270 CRT terminal cockpit directly on your local workstation.

---

## 1. Quick Setup (15 Seconds)

From the repository root:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                       # 100 tests pass, including Hypothesis PBT
```

---

## 2. Step 1: The Golden Path Demo (30 Seconds)

Evaluate how MainframeGhost detects arithmetic drift between AI-ported Python code and GnuCOBOL 3.1.2 ground truth on 10,000 banking ledger accounts.

### Run the Hardened Service (Approved Path)
```bash
python3 engine/shadow_fuzzer.py --candidate services/hardened_service.py
echo "Exit code: $?"
```
**Expected Output:**
```text
[PASS] drift=0.00000% records=10000 drifted=0 sort_mismatches=0
Verdict: APPROVED (exit 0)
Exit code: 0
```

### Run the Floating-Point Port (Veto Path)
Now run the candidate that uses standard Python `Decimal` with `ROUND_FLOOR` (which passes standard unit tests but rounds negative balances away from zero):
```bash
python3 engine/shadow_fuzzer.py --candidate tests/fixtures/candidates/round_floor.py
echo "Exit code: $?"
```
**Expected Output:**
```text
[FAIL] drift=49.62000% records=10000 drifted=4962 misposted=$49.62
[VETO] Mainframe Parity Sentinel: arithmetic drift from COBOL ground truth detected.
Exit code: 2
```

---

## 3. Step 2: Testing the Live Kiro `PreToolUse` Hook

MainframeGhost hooks directly into Kiro's tool execution pipeline (`.kiro/hooks/parity_guard.json`). When an agent attempts an `fs_write` or `str_replace` with code that causes ledger drift, the hook intercepts the call before it touches disk.

Simulate a Kiro `PreToolUse` event via stdin:

```bash
python3 -c 'import json; print(json.dumps({
  "hook_event_name": "PreToolUse",
  "tool_name": "fs_write",
  "tool_input": {
    "path": "services/ported.py",
    "text": open("tests/fixtures/candidates/round_floor.py").read()
  }
}))' | .kiro/hooks/bin/verify_modernization_parity.sh
echo "Hook Exit code: $?"
```

### Expected Behavior
- **Exit code 2**: The tool call is hard-aborted.
- **STDERR Feedback**: Detailed drift report and account discrepancy diffs are emitted directly back to the Kiro agent context so it can self-correct.

---

## 4. Step 3: Launching the IBM 3270 CRT Cockpit

Experience the retro banking terminal cockpit built in React 19:

```bash
python3 -m cockpit.server       # Listens on http://127.0.0.1:8737
```

1. Open `http://127.0.0.1:8737` in your browser.
2. Click **INITIALIZE 3270 COCKPIT** or click **Trigger Float Drift VETO** to watch the hook block the float port live.
3. Press **F9** to switch between P31 green phosphor and P4 amber phosphor.
4. Press **PF1** to inspect the 52-byte `INTACCR.cpy` copybook byte offsets and REDEFINES overlays.
5. Press **PF6** for the Engine Lab to test live COMP-3 hex packing and unpacking (`UNPACK 40404040 S9(5)V99`).
