#!/usr/bin/env python3
"""Sandbox-side harness that executes one untrusted candidate service.

Started only by ``engine.shadow_fuzzer.execute_candidate`` in a child process with
``python -I -B``, an empty environment (no AWS credentials), CPU / memory / file
size limits and, where the kernel allows it, a private network namespace.

Protocol
    argv[1]  path of the candidate .py file (a temp copy of the proposed source)
    stdin    {"function": "accrue_monthly_interest", "cases": [["123.45", "0.0525"], ...]}
    stdout   {"loaded": bool, "error": str | null, "missing": bool,
              "results": [[type_name, text], ...], "float_probe": str}

Exceptions raised by the candidate are reported as ``["!ExcName", message]``.
The candidate's own prints go to stderr so they cannot forge the verdict JSON.
"""

from __future__ import annotations

import importlib.util
import json
import operator
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # candidates may import the engine package


def _describe(exc: BaseException) -> list[str]:
    return [f"!{type(exc).__name__}", str(exc)[:200]]


def main() -> int:
    verdict_fd = os.dup(1)
    os.dup2(2, 1)  # candidate output -> stderr
    sys.stdout = sys.stderr
    out: dict = {"loaded": False, "error": None, "missing": False, "results": [],
                 "float_probe": "not run"}
    try:
        request = json.loads(sys.stdin.read())
        name = str(request["function"])
        cases = request["cases"]
        spec = importlib.util.spec_from_file_location("candidate_service", sys.argv[1])
        if spec is None or spec.loader is None:
            raise ImportError("cannot load candidate")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out["loaded"] = True
        func = getattr(module, name, None)
        if not callable(func):
            out["missing"] = True
        else:
            results = []
            for balance, rate in cases:
                try:
                    got = func(Decimal(balance), Decimal(rate))
                    results.append([type(got).__name__, str(got)])
                except Exception as exc:  # untrusted code: report, never crash
                    results.append(_describe(exc))
            out["results"] = results
            # Steering rule: reject IEEE 754 input with TypeError, never coerce.
            # The probe is built with operator.truediv on purpose: it is the one
            # binary float the sentinel creates, and only to feed it to the candidate.
            probe = operator.truediv(3, 2)
            try:
                func(probe, Decimal("0.0525"))
                out["float_probe"] = "accepted"
            except TypeError:
                out["float_probe"] = "TypeError"
            except Exception as exc:
                out["float_probe"] = f"{type(exc).__name__} (expected TypeError)"
    except BaseException as exc:  # includes SystemExit from candidate code
        out["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    with os.fdopen(verdict_fd, "w", encoding="utf-8") as verdict:
        verdict.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
