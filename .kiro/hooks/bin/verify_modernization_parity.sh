#!/usr/bin/env bash
# MainframeGhost zero-trust PreToolUse hook.
#   exit 0 : parity verified, tool proceeds
#   exit 2 : HARD VETO (drift, S0C7, or IEEE 754 contamination), tool blocked
#   exit 1 : sentinel runtime error
# Reads the proposed tool payload as JSON on STDIN. Runs from the workspace root.
set -uo pipefail

FUZZER="engine/shadow_fuzzer.py"
PYTHON_BIN="${MAINFRAME_GHOST_PYTHON:-python3}"

PAYLOAD="$(cat || true)"
[ -n "$PAYLOAD" ] || PAYLOAD="{}"

# Fail closed: without the sentinel engine nothing can be verified.
if [ ! -f "$FUZZER" ]; then
    echo "[VETO] Parity Sentinel: $FUZZER is missing; refusing to approve unverified tool calls." >&2
    exit 2
fi

OUTPUT="$(printf '%s' "$PAYLOAD" | "$PYTHON_BIN" "$FUZZER" --verify-stdin 2>&1)"
RC=$?

case "$RC" in
    0)
        echo "[PASS] Parity verified: 0.00000% drift against the GnuCOBOL oracle."
        printf '%s\n' "$OUTPUT" | head -1
        exit 0
        ;;
    2)
        {
            echo "$OUTPUT"
            echo "[VETO] Mainframe Parity Sentinel: semantic drift, S0C7 abend, or IEEE 754 precision violation detected."
            echo "[VETO] Halting tool execution to prevent ledger corruption. Fix with decimal.Decimal + ROUND_DOWN and exact COMP-3 nibbles, then retry."
        } >&2
        exit 2
        ;;
    *)
        {
            echo "$OUTPUT"
            echo "[ERROR] Parity Sentinel failed to run (fuzzer exit code $RC)."
        } >&2
        exit 1
        ;;
esac
