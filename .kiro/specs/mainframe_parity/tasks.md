# Implementation Plan: MainframeGhost Parity Sentinel

Requirements: `requirements.md`. Design: `design.md`. Test vectors: `specs/PRD.md` Section 8.

- [ ] 1. Governance scaffolding
  - [ ] 1.1 Create `.kiro/steering/cobol_parity.md` with `inclusion: always`
    - _Requirements: REQ-MF-001_
  - [ ] 1.2 Create `.kiro/hooks/parity_guard.json` and `.kiro/hooks/bin/verify_modernization_parity.sh` (`chmod +x`)
    - _Requirements: REQ-MF-004_
  - [ ] 1.3 Register FastMCP inspector in `.kiro/settings/mcp.json`
    - _Requirements: REQ-MF-004_

- [ ] 2. Project structure
  - [ ] 2.1 Create `engine/__init__.py`, `tests/`, `pyproject.toml` (Python >= 3.12, pytest, fastmcp pinned)
  - [ ] 2.2 Add `.gitignore` for `__pycache__`, `.venv`, `.pytest_cache`

- [ ] 3. `engine/comp3_packer.py`
  - [ ] 3.1 `packed_length(digits)` returns `digits // 2 + 1`
    - _Requirements: AC-003.1_
  - [ ] 3.2 `encode_comp3(value, digits, scale, signed=True)` with even-digit leading `0x0` nibble and signs `C`/`D`/`F`
    - _Requirements: AC-003.2, AC-003.3, AC-003.6_
  - [ ] 3.3 `decode_comp3(data, digits, scale)` returns `Decimal`; raises `S0C7Abend` for invalid digit or sign nibble
    - _Requirements: AC-003.4, AC-003.5_
  - [ ] 3.4 Reject `float` input with `TypeError`; reject overflow
    - _Requirements: AC-001.4_

- [ ] 4. `engine/ebcdic_codec.py`
  - [ ] 4.1 `ebcdic_sort_key(s)` using `cp037`; `ebcdic_sorted(keys)`
    - _Requirements: AC-002.1, AC-002.2, AC-002.3_
  - [ ] 4.2 Zoned Decimal codec: `encode_zoned(value, digits)` and `decode_zoned(text_or_bytes)` with overpunch matrix
    - _Requirements: AC-001.5_
  - [ ] 4.3 S0C7 on invalid zone or digit nibble

- [ ] 5. `engine/copybook_parser.py`
  - [ ] 5.1 Tokenizer: strip fixed-format columns and comments, split on sentence periods
  - [ ] 5.2 Parse levels 01-49, PIC (`X`, `9`, `S`, `V`, repeats like `9(7)`), USAGE (`DISPLAY`, `COMP`, `COMP-3`), `SYNC`, `REDEFINES`; build tree by level
  - [ ] 5.3 Layout pass: sizes, cumulative offsets, REDEFINES overlay at target offset, SYNC slack insertion
    - _Requirements: REQ-MF-005_
  - [ ] 5.4 Record accessor backed by one `bytearray` with offset-based views
    - _Requirements: REQ-MF-005.3_
  - [ ] 5.5 Validate PRD examples: TRANSACTION-RECORD (8 bytes, aliases) and ACCOUNT-RECORD (8 bytes, 3 slack)

- [ ] 6. `engine/shadow_fuzzer.py`
  - [ ] 6.1 Golden (integer) engine and modern (`Decimal`, `ROUND_DOWN`) engine
    - _Requirements: REQ-MF-001_
  - [ ] 6.2 Seeded 10,000-record generator without floats
  - [ ] 6.3 Comparator and report: `drift_pct` to 5 decimals, S0C7 counter
  - [ ] 6.4 Static contamination scan (AST): `float`, `round`, float literals
    - _Requirements: AC-004.4_
  - [ ] 6.5 CLI: `--verify-stdin`, `--records N`, `--seed`; exit 0/2/1
    - _Requirements: AC-004.1 to AC-004.7_

- [ ] 7. `tests/test_parity_engine.py` (PRD Section 8)
  - [ ] 7.1 Vector A: COMP-3 roundtrip `-1234567.89` -> `12 34 56 78 9D`
  - [ ] 7.2 Vector B: zoned `+12345` -> `F1F2F3F4C5` / `"1234E"`, `-12345` -> `D5` / `"1234N"`
  - [ ] 7.3 Vector C: EBCDIC collating inversion
  - [ ] 7.4 Vector D: even-digit COMP-3 `01 23 45 6C` / `6D`
  - [ ] 7.5 Vector E: `40 40 40 40` raises S0C7; fuzzer/hook exit code 2
  - [ ] 7.6 Negative control: float engine produces drift > 0
  - [ ] 7.7 Parser tests: REDEFINES alias write-through, SYNC slack

- [ ] 8. Hook and MCP verification
  - [ ] 8.1 Run the hook with a clean payload (expect 0) and a float-contaminated payload (expect 2)
  - [ ] 8.2 Implement `.kiro/mcp/server.py` with `inspect_copybook_offsets`, `decode_comp3_hex`, `run_shadow_parity_check`
  - [ ] 8.3 Smoke-test MCP tools

- [ ] 9. Checkpoint
  - [ ] 9.1 `pytest` green, fuzzer reports `0.00000%`, hook exit codes verified
