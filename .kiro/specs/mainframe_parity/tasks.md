# Implementation Plan: MainframeGhost Parity Sentinel

Requirements: `requirements.md`. Design: `design.md`. Test vectors: `requirements.md` (Golden Test Vectors).

- [x] 1. Governance scaffolding
  - [x] 1.1 Create `.kiro/steering/cobol_parity.md` with `inclusion: always`
    - _Requirements: REQ-MF-001_
  - [x] 1.2 Create `.kiro/hooks/parity_guard.json` and `.kiro/hooks/bin/verify_modernization_parity.sh` (`chmod +x`)
    - _Requirements: REQ-MF-004_
  - [x] 1.3 Register FastMCP inspector in `.kiro/settings/mcp.json`
    - _Requirements: REQ-MF-004_

- [x] 2. Project structure
  - [x] 2.1 Create `engine/__init__.py`, `tests/`, `pyproject.toml` (Python >= 3.12, pytest, fastmcp pinned)
  - [x] 2.2 Add `.gitignore` for `__pycache__`, `.venv`, `.pytest_cache`

- [x] 3. `engine/comp3_packer.py`
  - [x] 3.1 `packed_length(digits)` returns `digits // 2 + 1`
    - _Requirements: AC-003.1_
  - [x] 3.2 `encode_comp3(value, digits, scale, signed=True)` with even-digit leading `0x0` nibble and signs `C`/`D`/`F`
    - _Requirements: AC-003.2, AC-003.3, AC-003.6_
  - [x] 3.3 `decode_comp3(data, digits, scale)` returns `Decimal`; raises `S0C7Abend` for invalid digit or sign nibble
    - _Requirements: AC-003.4, AC-003.5_
  - [x] 3.4 Reject `float` input with `TypeError`; reject overflow
    - _Requirements: AC-001.4_

- [x] 4. `engine/ebcdic_codec.py`
  - [x] 4.1 `ebcdic_sort_key(s)` using `cp037`; `ebcdic_sorted(keys)`
    - _Requirements: AC-002.1, AC-002.2, AC-002.3_
  - [x] 4.2 Zoned Decimal codec with overpunch matrix
    - _Requirements: AC-001.5_
  - [x] 4.3 S0C7 on invalid zone or digit nibble

- [x] 5. `engine/copybook_parser.py`
  - [x] 5.1 Tokenizer: strip fixed-format columns and comments, split on sentence periods
  - [x] 5.2 Parse levels 01-49, PIC, USAGE, `SYNC`, `REDEFINES`; build tree by level
  - [x] 5.3 Layout pass: sizes, offsets, REDEFINES overlay, SYNC slack
    - _Requirements: REQ-MF-005_
  - [x] 5.4 Record accessor backed by one `bytearray`
    - _Requirements: REQ-MF-005.3_
  - [x] 5.5 Validate layout examples (TRANSACTION-RECORD, ACCOUNT-RECORD)

- [x] 6. `engine/shadow_fuzzer.py`
  - [x] 6.1 Golden (integer) engine and modern (`Decimal`, `ROUND_DOWN`) engine
  - [x] 6.2 Seeded 10,000-record generator without floats
  - [x] 6.3 Comparator and report: `drift_pct` to 5 decimals, S0C7 counter
  - [x] 6.4 Static contamination scan: `float`, `round`, float literals
    - _Requirements: AC-004.4_
  - [x] 6.5 CLI: `--verify-stdin`, `--records N`, `--seed`; exit 0/2/1

- [x] 7. `tests/test_parity_engine.py` (golden vectors A-E, parser, negative control)

- [x] 8. Hook and MCP verification
  - [x] 8.1 Hook exit 0 on a clean payload, 2 on float contamination
  - [x] 8.2 `.kiro/mcp/server.py` with three tools
  - [x] 8.3 Smoke-test MCP tools

- [x] 9. GnuCOBOL oracle
  - [x] 9.1 `cobol/src/intaccr_batch.cbl` (COPY INTACCR, no ROUNDED) and `cobol/src/ebcsort.cbl` (SORT with EBCDIC alphabet)
    - _Requirements: AC-006.1_
  - [x] 9.2 `cobol/Dockerfile` (Debian bookworm, gnucobol3 3.1.2) and `engine/cobol_oracle.py generate|verify`
  - [x] 9.3 Commit `cobol/fixtures/` with a SHA-256 manifest; tamper check
    - _Requirements: AC-006.2, AC-006.3_
  - [x] 9.4 Golden and modern engines match COBOL byte for byte on 10,000 records and the SORT
    - _Requirements: AC-006.4_

- [x] 10. Execute proposed code in the hook
  - [x] 10.1 `proposed_source()` rebuilds post-write text for fs_write / fs_append / str_replace
    - _Requirements: AC-007.1_
  - [x] 10.2 `engine/candidate_runner.py` + `execute_candidate()` sandbox
    - _Requirements: AC-007.2, AC-007.5_
  - [x] 10.3 Diff candidate vs COBOL, float-input probe, veto on any mismatch
    - _Requirements: AC-007.3, AC-007.4_
  - [x] 10.4 Hook fails closed when the engine is missing

- [x] 11. Bedrock program mode
  - [x] 11.1 Inline COPY members, attach parser layout, Claude Sonnet 5.5 (`us.anthropic.claude-sonnet-5-5`)
  - [x] 11.2 Gate every response through `check_candidate`; `--capture` keeps raw output + verdict; `--naive` control prompt
  - [ ] 11.3 Live capture against a real AWS account (needs credentials)

- [x] 12. Cockpit
  - [x] 12.1 `cockpit/server.py` API (comp3, pack, zoned, sort, layout, verify on loopback only)
  - [x] 12.2 UI: editable candidate, live verdicts, pasted copybook layout, PF6 lab, preset fallback when offline

- [x] 13. Property-based tests (`tests/test_properties.py`, Hypothesis)

- [x] 14. Custom agents: `.kiro/agents/cobol-porter.md`, `.kiro/agents/parity-auditor.md`
