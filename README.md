<div align="center">

# MainframeGhost

**A Kiro `PreToolUse` gate that runs AI-ported COBOL against the real compiler's output before the agent can save it.**

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-100%20passing-brightgreen.svg)](tests/)
[![Oracle](https://img.shields.io/badge/oracle-GnuCOBOL%203.1.2-informational.svg)](cobol/)
[![Kiroween 2026](https://img.shields.io/badge/Kiroween%202026-Resurrection-orange.svg)](https://kiroween.devpost.com/)

![Kiro blocks a Decimal port that uses ROUND_FLOOR](docs/screenshots/mg_veto.png)

</div>

---

## Contents

- [Why](#why)
- [How it works](#how-it-works)
- [Results](#results)
- [Quick start](#quick-start)
- [Kiro integration](#kiro-integration)
- [COBOL ground truth](#cobol-ground-truth)
- [Amazon Bedrock](#amazon-bedrock)
- [The cockpit](#the-cockpit)
- [Repository layout](#repository-layout)
- [Limitations](#limitations)
- [License](#license)

## Why

Banks still run COBOL batch jobs, and AI agents are now being asked to port them. The bugs that matter in those ports are rarely in the business logic. They are in how numbers are stored and rounded.

- COBOL `COMPUTE` without `ROUNDED` truncates toward zero. Python's `round()` uses banker's rounding, `ROUND_FLOOR` rounds negative values away from zero, and `ROUND_HALF_UP` adds a `ROUNDED` the program never had.
- Packed decimal (`COMP-3`), zoned sign overpunch (`"1234N"` is −12345), `SYNC` slack bytes and the EBCDIC sort order (`a < A < 0`) all follow exact byte rules.
- A linter that flags `float()` and `round()` misses a clean `decimal.Decimal` port with the wrong rounding mode. That port passes code review and positive-balance unit tests, then misposts a cent on about half the accounts.

MainframeGhost checks behaviour, not syntax. It sits in the agent's write path and compares the code's output with what the original COBOL program produced.

## How it works

```
 agent proposes fs_write / fs_append / str_replace
                     │
                     ▼
 .kiro/hooks/parity_guard.json  ──►  verify_modernization_parity.sh
                     │
                     ▼
 engine/shadow_fuzzer.py --verify-stdin
   1. static scan       float(), round(), float literals
   2. self-check        Python engines vs GnuCOBOL bytes
   3. rebuild file      apply the edit to the file on disk
   4. sandboxed run     accrue_monthly_interest on 10,000 accounts
   5. diff              against COBOL WS-INTEREST, plus a float-input probe
                     │
          ┌──────────┴──────────┐
       exit 0                exit 2
   write proceeds     write blocked, the drifting
                      records go back to the agent
```

The sandbox is a child process started with `python -I -B`. It gets an empty environment (no AWS or Kiro credentials), a throwaway working directory, CPU, memory and file-size limits, a 30-second timeout and, on Linux, no network (`unshare --net`). The candidate's own `print` output cannot reach the verdict channel.

## Results

Every number below comes from the real hook. [`scripts/export_ui_vectors.py`](scripts/export_ui_vectors.py) pipes each file through it and refuses to export if the hook and the in-process verdict disagree.

| Candidate | Static scan | Accounts that differ from COBOL | Misposted | Verdict |
| :--- | :---: | :---: | :---: | :---: |
| [`hardened_service.py`](services/hardened_service.py) · `Decimal`, `ROUND_DOWN` | clean | 0 / 10,000 | $0.00 | ✅ exit 0 |
| [`vulnerable_service.py`](services/vulnerable_service.py) · `float()`, `round()` | 7 violations | 5,383 / 10,000 | $49.37 | ⛔ exit 2 |
| [`round_floor.py`](tests/fixtures/candidates/round_floor.py) · `Decimal`, `ROUND_FLOOR` | **clean** | 4,962 / 10,000 | $49.62 | ⛔ exit 2 |
| [`round_half_up.py`](tests/fixtures/candidates/round_half_up.py) · `Decimal`, `ROUND_HALF_UP` | **clean** | 4,937 / 10,000 | $49.37 | ⛔ exit 2 |

The last two rows are the reason the project exists. A static check approves both of them; running them shows they are wrong.

*Misposted* is the sum of `|candidate − COBOL|` over the seeded 10,000-account corpus.

## Quick start

**Requirements:** Linux or macOS, Python 3.12+, Node 20+. Docker is only needed to regenerate the COBOL fixtures.

```bash
git clone https://github.com/Divyanshu-Kumar14/mainframe-ghost.git
cd mainframe-ghost
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                    # 100 tests, including Hypothesis property tests
```

Check a candidate from the command line:

```bash
python3 engine/shadow_fuzzer.py --candidate tests/fixtures/candidates/round_floor.py; echo $?   # 2
python3 engine/shadow_fuzzer.py --candidate services/hardened_service.py --3270; echo $?        # 0
```

Send a payload through the hook exactly as Kiro does:

```bash
python3 -c 'import json; print(json.dumps({"hook_event_name": "PreToolUse", "tool_name": "fs_write",
  "tool_input": {"path": "services/ported.py",
                 "text": open("tests/fixtures/candidates/round_floor.py").read()}}))' \
  | .kiro/hooks/bin/verify_modernization_parity.sh; echo $?     # 2; the drifting records are on stderr
```

Run the cockpit:

```bash
(cd ui && npm install && npm run build)
python3 -m cockpit.server                 # http://127.0.0.1:8737
```

## Kiro integration

| Feature | Location | Role |
| :--- | :--- | :--- |
| **Agent hook** | [`.kiro/hooks/parity_guard.json`](.kiro/hooks/parity_guard.json) | `PreToolUse` on `fs_write`, `fs_append`, `str_replace` and `execute_bash`. Exit 2 blocks the call and returns STDERR to the agent. The hook fails closed: if the engine is missing, every write is blocked. |
| **Steering** | [`.kiro/steering/cobol_parity.md`](.kiro/steering/cobol_parity.md) | Always included. The arithmetic rules: Decimal only, `ROUND_DOWN` unless the COBOL says `ROUNDED`, CP-037 sort keys. Steering tells the agent the rules; the hook checks that it followed them. |
| **Spec** | [`.kiro/specs/mainframe_parity/`](.kiro/specs/mainframe_parity/) | EARS requirements REQ-MF-001 to 007, the golden test vectors A–E, a design document with byte maps, and the task list the build followed. |
| **MCP server** | [`.kiro/mcp/server.py`](.kiro/mcp/server.py) | `mainframe-inspector` (FastMCP, stdio): `inspect_copybook_offsets`, `decode_comp3_hex`, and `run_shadow_parity_check`, which runs the same sandboxed diff as the hook. |
| **Custom agents** | [`.kiro/agents/`](.kiro/agents/) | `cobol-porter` writes services. It is denied write access to the hook and the fixtures, and it fixes its own code from veto output. `parity-auditor` is read-only and audits files through the MCP tools. |
| **Skills** | [`.kiro/skills/`](.kiro/skills/) | COMP-3 and EBCDIC rules, Bedrock usage, hook authoring, and the 3270 CRT design. |
| **Property-based tests** | [`tests/test_properties.py`](tests/test_properties.py) | Hypothesis tests: COMP-3 and zoned round trips for every digit count and scale, S0C7 agreement on random bytes, truncation toward zero, EBCDIC sort order, REDEFINES write-through and SYNC alignment. |

The hook also guards this repository's own development. [`docs/evidence/kiro_live_veto_2026-11-08.json`](docs/evidence/kiro_live_veto_2026-11-08.json) is the verbatim output from a Kiro session in which the hook blocked the agent's attempt to write the float negative control.

## COBOL ground truth

A Python reference written by the same author as the code it checks proves little on its own. Ground truth here comes from a COBOL compiler.

[`cobol/src/intaccr_batch.cbl`](cobol/src/intaccr_batch.cbl) `COPY`s [`copybooks/INTACCR.cpy`](copybooks/INTACCR.cpy) and computes:

```cobol
COMPUTE WS-INTEREST    = (ACCT-BALANCE * ACCT-ANNUAL-RATE) / 12
COMPUTE WS-NEW-BALANCE = ACCT-BALANCE + WS-INTEREST
```

[`cobol/src/ebcsort.cbl`](cobol/src/ebcsort.cbl) sorts the account keys with `COLLATING SEQUENCE IS EBCDIC`. Both programs run under GnuCOBOL 3.1.2 in Docker with networking disabled:

```bash
python3 -m engine.cobol_oracle generate   # build cobol/Dockerfile, compile, run, write fixtures
python3 -m engine.cobol_oracle verify     # Python engines vs COBOL bytes; exit 2 on any drift
```

The output (`ACCTOUT`: COMP-3 interest and zoned new balance per account; `KEYSOUT`: the sorted keys) is committed in [`cobol/fixtures/`](cobol/fixtures/) with SHA-256 digests. Tests, the hook and the cockpit read those bytes, so none of them need Docker, and a modified fixture counts as drift.

Both Python engines match GnuCOBOL byte for byte on all 10,000 records and on the sort.

## Amazon Bedrock

[`services/bedrock_transpiler.py`](services/bedrock_transpiler.py) sends the COBOL program to Claude Sonnet 5.5 on Bedrock (`us.anthropic.claude-sonnet-5-5`). It inlines the COPY members and attaches the byte layout from the copybook parser. Every response goes through the same sandboxed diff; if it fails, nothing is written and the command exits 2.

```bash
pip install -e ".[aws]"                   # then `aws login`, or export AWS_BEARER_TOKEN_BEDROCK
python3 -m services.bedrock_transpiler cobol/src/intaccr_batch.cbl -o services/bedrock_service.py --capture
python3 -m services.bedrock_transpiler cobol/src/intaccr_batch.cbl --naive --capture   # no parity rules in the prompt
python3 -m services.bedrock_transpiler cobol/src/intaccr_batch.cbl --dry-run           # print the request only
```

`--capture` saves the raw response and its verdict under `tests/fixtures/candidates/`, and the cockpit lists each capture as another candidate. Sonnet 5.5 always uses adaptive thinking, so its output is not deterministic. That is why every response is checked.

## The cockpit

A React 19 recreation of an IBM 3278-2 terminal (80×24, P31 green or P4 amber phosphor). It talks to the real engine through [`cockpit/server.py`](cockpit/server.py), which uses only the Python standard library.

- **Sentinel panel:** choose a candidate or edit its code, then press **RUN PreToolUse HOOK**. The code goes to `verify_stdin()`, the same function the hook script calls, and the panel shows the verdict, drift count, misposted total and hook transcript.
- **COPYBOOK tab:** paste any copybook; PF1 shows offsets, REDEFINES overlays and SYNC slack.
- **PF6 lab:** `UNPACK 40404040 S9(5)V99`, `PACK -1234567.89 S9(7)V99`, `ZONED 1234N S9(5)`, `SORT 100ACC ACC100 acc100`.
- **PF1–PF5:** copybook layout, hex dump, golden vectors, S0C7 monitor, sentinel. **PF9** switches phosphor.

Running submitted code is enabled only when the server listens on a loopback address. On a public address, or as a static build with no API, the UI shows the verdicts exported from the real hook and labels them as presets.

| Running | Parity verified (amber) | S0C7 monitor | Engine lab |
| :---: | :---: | :---: | :---: |
| ![Sentinel running](docs/screenshots/mg_running.png) | ![Parity verified](docs/screenshots/mg_pass_amber.png) | ![S0C7 monitor](docs/screenshots/mg_s0c7.png) | ![Engine lab](docs/screenshots/mg_lab.png) |

## Repository layout

```
.kiro/       hooks/, steering/, specs/, agents/, skills/, mcp/server.py, settings/mcp.json
cobol/       src/intaccr_batch.cbl, src/ebcsort.cbl, Dockerfile, fixtures/ (GnuCOBOL output + manifest)
copybooks/   INTACCR.cpy: 52-byte record with COMP-3, zoned, SYNC binary and REDEFINES
engine/      comp3_packer, ebcdic_codec, copybook_parser, shadow_fuzzer, candidate_runner, cobol_oracle
services/    hardened_service (Lambda handler), vulnerable_service (float control), bedrock_transpiler
cockpit/     server.py: JSON API and static host for ui/dist
scripts/     export_ui_vectors.py: runs the real hook on every candidate for the UI presets
tests/       test_parity_engine, test_oracle_and_gate, test_properties; fixtures/candidates/
ui/          the 3270 cockpit (React 19, Vite, Tailwind 4)
docs/        screenshots/, evidence/
```

## Limitations

- **One batch step.** The oracle covers monthly interest accrual on one record layout, plus its sort. Each new program needs its own COBOL driver and fixtures.
- **GnuCOBOL is not IBM Enterprise COBOL.** For this program (one multiply, one divide, truncation on store, COMP-3 and signed zoned output, an EBCDIC sort) the results should match, but they have not been checked on z/OS.
- **S0C7 is modelled in Python.** GnuCOBOL does not raise S0C7, so the corrupted-dump checks rely on the Python engine.
- **The sandbox is a hardened subprocess, not a VM.** It guards against accidental damage from generated code, not a determined attacker. Network isolation needs Linux with unprivileged user namespaces; without it the other limits still apply and the verdict says so.
- **Nothing is deployed.** `hardened_service.py` contains a Lambda handler, but this repository does not deploy it.

## License

[Apache-2.0](LICENSE). Built by Divyanshu Kumar ([@Divyanshu-Kumar14](https://github.com/Divyanshu-Kumar14)) for [Kiroween 2026](https://kiroween.devpost.com/), Resurrection category.
