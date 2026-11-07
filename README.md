# MainframeGhost
### 1959 IBM z/OS COBOL to AWS Bedrock & Lambda Parity Sentinel

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Tests Passing](https://img.shields.io/badge/pytest-64%2F64%20passed-brightgreen.svg)](tests/)
[![Kiro Native Hook](https://img.shields.io/badge/kiro-PreToolUse%20v2%20hook-orange.svg)](.kiro/hooks/)
[![Exit Code](https://img.shields.io/badge/governance-POSIX%20Exit%202%20VETO-red.svg)](.kiro/hooks/bin/verify_modernization_parity.sh)
[![Parity](https://img.shields.io/badge/shadow%20drift-0.00000%25-success.svg)](engine/shadow_fuzzer.py)
[![React 19](https://img.shields.io/badge/ui-React%2019%20%2B%20Vite-61dafb.svg)](ui/)
[![IBM 3270](https://img.shields.io/badge/terminal-IBM%203278--2%20CRT-33ff33.svg)](ui/src/components/GhostTerminal.tsx)

> **Built for Kiroween 2026 (Devpost / AWS & Kiro — $100,000 Cash Pool)**  
> **Primary Tracks:** Track 1 (Resurrection) / Track 2 (Frankenstein) / Track 4 (Costume Contest)  
> **Bonus Track:** Best Startup Project ($10,000) & 1st Place Grand Prize ($30,000)  
> **Author:** Divyanshu Kumar ([@Divyanshu-Kumar14](https://github.com/Divyanshu-Kumar14))

---

## 1. Executive Summary & Problem Statement

### The $3 Trillion Mainframe Reality
- **43% of all US banking systems**, **95% of ATM transactions**, and **80% of in-person point-of-sale swipes** run on legacy IBM z/OS mainframes executing COBOL programs written between 1959 and 1985.
- Over **220 billion lines of active COBOL** operate in production globally, processing over **$3 trillion in daily commerce**.
- The senior systems engineers who authored these critical ledgers have retired. The contemporary cloud generation does not understand EBCDIC memory architectures, packed decimal math, or mainframe abend semantics.

### The Modernization Graveyard
According to Standish Group and Gartner data, **74% of enterprise core banking modernization initiatives fail or run catastrophically over budget**, with an average write-down exceeding **$35 million per failed attempt**.

The failure mode is almost never high-level business logic. It is **silent semantic drift** at the binary execution boundary:
1. Generative AI and transpilers translate COBOL copybooks into Python/TypeScript classes using IEEE 754 floating-point primitives (`float`), triggering silent rounding errors.
2. Standard library sorting routines swap ledger transaction ordering due to ASCII vs. EBCDIC CP-037 collating sequence inversions.
3. Batch ledgers diverge by fractions of a cent over 10,000 accounts, violating Sarbanes-Oxley (SOX) compliance and causing regulatory freezes.
4. Legacy space-filled buffers (`0x40`) passed to modern math runtimes trigger unhandled catastrophic data exception crashes (**S0C7 Abends**).

### The Solution: MainframeGhost
`MainframeGhost` is a zero-trust, dual-engine semantic parity sentinel. It pairs **AWS Bedrock** (running Claude 3.5 Sonnet) as the modernization engine with **Kiro** as the deterministic runtime safety governor.

Before any AI-modernized cloud service (AWS Lambda) can be promoted or written to production, `MainframeGhost` intercepts the tool call at the Kiro IDE **`PreToolUse` hook boundary**, executing a byte-level shadow fuzzer comparing IBM System/390 execution state against the modernized cloud candidate. If a single-bit semantic drift, float contamination, or S0C7 risk is detected, Kiro halts the pipeline with **POSIX Exit Code 2 (VETO)**, physically preventing ledger corruption from reaching AWS CloudWatch or production databases.

---

## 2. Visual Gallery: IBM 3270 Ghost Terminal Cockpit

The `MainframeGhost` operations cockpit recreates the physical experience of an authentic **IBM 3278 Model 2 Display Station** (80 columns × 24 rows) with real-time CRT beam-spring switch acoustics, P31 green / P4 amber phosphor persistence shaders, barrel distortion, and scanline rendering.

| Idle Terminal Cockpit (PF1 AST Layout) | Live Fuzzing Sentinel Execution |
| :---: | :---: |
| ![IBM 3278-2 Idle Screen](docs/screenshots/mg_idle.png) | ![Fuzzing in Progress](docs/screenshots/mg_running.png) |
| *Authentic 80×24 monospace grid with copybook AST and SYNC slack detection.* | *Real-time dual-engine differential execution across 10,000 synthetic records.* |

| POSIX Exit Code 2 Hook VETO | P4 Amber Night Mode (0.00000% Parity) |
| :---: | :---: |
| ![Hook VETO Banner](docs/screenshots/mg_veto.png) | ![P4 Amber Passed](docs/screenshots/mg_pass_amber.png) |
| *Kiro PreToolUse hook intercepts IEEE 754 float contamination and vetoes deployment.* | *Hardened AWS Lambda service passes 10,000 records with 0.00000% drift.* |

| System Abend S0C7 Data Exception Monitor | 52-Byte EBCDIC CP-037 Hex Memory Dump |
| :---: | :---: |
| ![S0C7 Abend Alert](docs/screenshots/mg_s0c7.png) | ![Hex Memory Dump](docs/screenshots/mg_hex.png) |
| *CEE3207S diagnostic dump on invalid packed nibbles and space-filled buffers.* | *Byte-accurate CP-037 memory dump with color-coded COMP-3 packed fields.* |

---

## 3. High-Level System Architecture

```
                                  MAINFRAMEGHOST SYSTEM TOPOLOGY
                                  
  +---------------------------------------------------------------------------------------------------+
  |                                        INPUT ARTIFACTS                                            |
  |   +---------------------------------------+       +-------------------------------------------+   |
  |   | 1959 IBM z/OS COBOL Copybooks (.cpy) |       | EBCDIC Binary Flat Records / VSAM Dumps   |   |
  |   +---------------------------------------+       +-------------------------------------------+   |
  +---------------------------------------------------------------------------------------------------+
                                                    |
                                                    v
  +---------------------------------------------------------------------------------------------------+
  |                               KIRO GOVERNED AGENTIC WORKSPACE                                     |
  |                                                                                                   |
  |   +-----------------------------------+             +-----------------------------------------+   |
  |   | .kiro/specs/ (EARS Syntax)        |             | .kiro/steering/ (Deterministic Rules)   |   |
  |   | - Mathematical Scale Preserv.     |             | - Always enforce decimal.Decimal        |   |
  |   | - EBCDIC Collating Inversion      |             | - Reject IEEE 754 float types           |   |
  |   +-----------------------------------+             +-----------------------------------------+   |
  |                     |                                             |                               |
  |                     v                                             v                               |
  |   +-------------------------------------------------------------------------------------------+   |
  |   | Kiro IDE Agent / AWS Bedrock Transpiler (Claude 3.5 Sonnet)                               |   |
  |   | Generates modernized Python 3.12 AWS Lambda banking microservice                          |   |
  |   +-------------------------------------------------------------------------------------------+   |
  |                                                    |                                              |
  |                                                    v                                              |
  |   +-------------------------------------------------------------------------------------------+   |
  |   | Zero-Trust PreToolUse Hook (.kiro/hooks/bin/verify_modernization_parity.sh)               |   |
  |   | Intercepts fs_write / str_replace / execute_bash tool payload from STDIN                  |   |
  |   |   1. Static AST Scanner: Forbids float(), round(), and floating-point literals            |   |
  |   |   2. Dual-Engine Shadow Fuzzer: Compares System/390 byte engine against Python candidate |   |
  |   |   3. S0C7 Abend Battery: Injects corrupted buffers and uninitialized space dumps          |   |
  |   |                                                                                           |   |
  |   |   -> If Parity Drift == 0: Return POSIX Exit Code 0 (DEPLOY PROCEEDS)                     |   |
  |   |   -> If Parity Drift != 0: Return POSIX Exit Code 2 (DEPLOYMENT VETOED & ABORTED)          |   |
  |   +-------------------------------------------------------------------------------------------+   |
  +---------------------------------------------------------------------------------------------------+
             |                                                                       |
             | (Veto: Exit Code 2)                                                   | (Pass: Exit Code 0)
             v                                                                       v
  +-------------------------------------+                 +-------------------------------------------+
  | IBM 3270 Ghost Terminal Cockpit     |                 | AWS Serverless Production Cloud           |
  | - Retro Green-Phosphor CRT Display   |                 | - AWS Lambda (Python 3.12 Decimal)        |
  | - Hex Dump Memory Visualizer        |                 | - AWS Bedrock Modernization Pipeline      |
  | - S0C7 Abend Alert & Diff Inspector |                 | - Amazon Aurora PostgreSQL Financial DWH   |
  +-------------------------------------+                 +-------------------------------------------+
```

---

## 4. The 6 Fatal Modernization Failure Modes Solved

### Failure Mode 1: IEEE 754 Float Precision Loss & Round-Half-Even Drift
- **Mainframe Rule:** IBM Enterprise COBOL packed arithmetic executes exact base-10 decimal math with hardware truncation toward zero (`ROUNDED` modes must be explicitly requested).
- **Modern Failure:** Standard Python/JS floats use IEEE 754 binary representation ($0.1_{10} = 0.000110011..._2$) and Banker's Rounding (`round-half-even`).
- **Real Drift:** On a 10,000-account test run, naive float modernization caused **50.00% of accounts to drift by $0.01**, creating an aggregate error of **$41.82**.
- **MainframeGhost Enforcement:** AST inspection and runtime shadow fuzzer mandate `decimal.Decimal` with explicit `ROUND_DOWN`.

### Failure Mode 2: EBCDIC CP-037 Collating Sequence Inversion
- **Mainframe Rule:** In EBCDIC CP-037, lowercase letters precede uppercase letters, which precede digits:
  $$\text{EBCDIC: } [a-z] < [A-Z] < [0-9] \quad (\text{e.g., } 'a' = 0x81, 'A' = 0xC1, '0' = 0xF0)$$
- **Modern Failure:** In ASCII / UTF-8, numbers precede uppercase letters, which precede lowercase letters:
  $$\text{ASCII: } [0-9] < [A-Z] < [a-z] \quad (\text{e.g., } '0' = 0x30, 'A' = 0x41, 'a' = 0x61)$$
- **Consequence:** Batch reconciliation sorts transaction IDs and account numbers in reverse order, breaking ledger sequence dependencies.
- **MainframeGhost Enforcement:** Implements the full 256-byte System/390 collating sequence sort key in Python.

### Failure Mode 3: Even-Digit COMP-3 High-Nibble Padding
- **Mainframe Rule:** A packed decimal field of $D$ digits occupies $L = \lfloor D/2 \rfloor + 1$ bytes. When $D$ is even, the value must be zero-padded in the high nibble of the first byte:
  $$\text{Value } +123456 \text{ on } \text{PIC S9(6) COMP-3} \implies \text{Hex: } \mathbf{01}\;23\;45\;6\mathbf{C}$$
- **Modern Failure:** Naive encoders omit the leading nibble, producing invalid length allocations and corrupting adjacent memory offsets.
- **MainframeGhost Enforcement:** `comp3_packer.py` strictly validates and generates leading `0x0` nibbles for even-digit clauses.

### Failure Mode 4: Zoned Decimal Sign Overpunch
- **Mainframe Rule:** `PIC S9(n) USAGE DISPLAY` stores the arithmetic sign as an overpunch in the high nibble of the final byte:
  - Positive signs (`0xC`) overpunch digits `0-9` into `{`, `A-I` (`+12345` -> `"1234E"`).
  - Negative signs (`0xD`) overpunch digits `0-9` into `}`, `J-R` (`-12345` -> `"1234N"`).
- **Modern Failure:** Cloud microservices parsing string data with `int()` or `float()` crash immediately with `ValueError: invalid literal`.
- **MainframeGhost Enforcement:** Built-in bidirectional zoned overpunch codec handles positive, negative, and zero overpunch braces (`{` / `}`).

### Failure Mode 5: `SYNCHRONIZED` Boundary Slack Byte Padding
- **Mainframe Rule:** When `SYNCHRONIZED` (`SYNC`) is specified on binary fields, IBM Enterprise COBOL aligns halfwords (`PIC S9(4) BINARY`) to 2-byte boundaries and fullwords (`PIC S9(9) BINARY`) to 4-byte boundaries, silently inserting slack bytes.
- **Modern Failure:** Naive copybook parsers sum field byte lengths without alignment math, placing every downstream field at the wrong byte offset.
- **MainframeGhost Enforcement:** `copybook_parser.py` calculates modulo boundary alignments and tracks `slack_before` offsets (e.g. `RECORD-STATUS` at offset 8, slack at offset 9, `TRANS-COUNT` aligned at offset 10).

### Failure Mode 6: Uninitialized Buffer S0C7 Data Exception Abend
- **Mainframe Rule:** Packed arithmetic instructions (`AP`, `MP`, `CP`) fault with hardware System Abend **S0C7** if any digit nibble is non-decimal (`0xA–0xF`) or if the sign nibble is invalid.
- **Modern Failure:** When legacy buffers filled with EBCDIC spaces (`0x40`) are passed into calculation pipelines, naive cloud services silently interpret them as zeros instead of rejecting bad records.
- **MainframeGhost Enforcement:** Injects a 500-sample corruption battery testing non-digit nibbles, space fills, and invalid signs, ensuring the candidate service surfaces an explicit data exception.

---

## 5. Differential Fuzzing Benchmark Results

We benchmarked the original IBM z/OS System/390 execution engine against two modernized AWS Lambda services across 10,000 synthetic banking accounts:

| Metric | Modernized Float Lambda (Unsafe) | Modernized Hardened Lambda (MainframeGhost) |
| :--- | :--- | :--- |
| **Numeric Type** | IEEE 754 `float` | `decimal.Decimal(prec=28)` |
| **Rounding Mode** | `round(val, 2)` (Round-Half-Even) | `quantize(Decimal('0.01'), ROUND_DOWN)` |
| **Records Evaluated** | 10,000 accounts | 10,000 accounts |
| **Diverged Records** | **5,000 accounts (50.00%)** | **0 accounts (0.00000%)** |
| **Max Account Drift** | **+$0.01000** | **$0.00000** |
| **Cumulative Ledger Error** | **+$41.82** | **$0.00000** |
| **Kiro PreToolUse Hook** | **EXIT CODE 2 (VETO)** | **EXIT CODE 0 (APPROVED)** |
| **Production Promotion** | **BLOCKED BEFORE CLOUD** | **PROMOTED TO AWS LAMBDA** |

---

## 6. Repository Layout

```
.
├── .kiro/                               # Kiro Agentic Governance Configuration
│   ├── hooks/
│   │   ├── parity_guard.json            # PreToolUse hook configuration
│   │   └── bin/
│   │       └── verify_modernization_parity.sh # Executable POSIX Exit Code 2 sentinel
│   ├── specs/mainframe_parity/         # Formal EARS requirements and design docs
│   └── steering/
│       └── cobol_parity.md              # Global invariant: ban floats, enforce Decimal
├── copybooks/
│   └── INTACCR.cpy                      # Core banking interest accrual COBOL copybook
├── docs/
│   └── screenshots/                     # High-resolution 3270 cockpit screenshots
├── engine/
│   ├── __init__.py
│   ├── comp3_packer.py                  # System/390 COMP-3 packed decimal codec
│   ├── copybook_parser.py               # COBOL parser with REDEFINES & SYNC slack math
│   ├── ebcdic_codec.py                  # EBCDIC CP-037 & Zoned Overpunch codec
│   └── shadow_fuzzer.py                 # Dual-engine differential comparator & 3270 CRT
├── scripts/
│   └── export_ui_vectors.py             # Parity data pipeline exporting to React UI
├── services/
│   ├── bedrock_transpiler.py            # AWS Bedrock Claude 3.5 Sonnet transpiler
│   └── hardened_service.py              # Modernized AWS Lambda service (0.00000% drift)
├── tests/
│   └── test_parity_engine.py            # 64-test comprehensive pytest test suite
└── ui/                                  # IBM 3278 Model 2 CRT Operations Cockpit
    ├── src/
    │   ├── components/
    │   │   ├── GhostTerminal.tsx        # CRT tube screen component
    │   │   └── Sentinel.tsx             # AWS CloudWatch / Kiro Sentinel control plane
    │   ├── lib/
    │   │   ├── audio.ts                 # Web Audio API beam-spring sound generator
    │   │   ├── pages.ts                 # PF1-PF5 80x24 monospace terminal panels
    │   │   └── screen.ts                # 3270 screen buffer and text styling
    │   └── App.tsx                      # Cockpit state machine and keyboard router
    └── vite.config.ts
```

---

## 7. Quickstart & Verification

### Prerequisites
- Linux / macOS
- Python 3.12+
- Node.js 20+
- (Optional) AWS Credentials configured with Bedrock access (`anthropic.claude-3-5-sonnet`)

### 1. Run the Pytest Test Suite (64/64 Passing)
```bash
git clone https://github.com/Divyanshu-Kumar14/mainframe-ghost.git
cd mainframe-ghost
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

### 2. Run the Dual-Engine Shadow Fuzzer in 80×24 CRT Mode
```bash
# Run 10,000 differential banking records in authentic 3270 terminal format
python engine/shadow_fuzzer.py --records 10000 --seed 42 --3270
```

### 3. Test the Kiro PreToolUse Governance Hook
```bash
# Pipe a clean payload (passes with Exit Code 0)
echo '{"hook_event_name":"PreToolUse","tool_name":"fs_write","tool_input":{"path":"services/clean.py","text":"from decimal import Decimal\nval = Decimal(\"100.00\")"}}' | .kiro/hooks/bin/verify_modernization_parity.sh
echo $? # Output: 0

# Pipe a float-contaminated payload (blocked with POSIX Exit Code 2)
echo '{"hook_event_name":"PreToolUse","tool_name":"fs_write","tool_input":{"path":"services/bad.py","text":"val = round(float(100.0) * 0.05, 2)"}}' | .kiro/hooks/bin/verify_modernization_parity.sh
echo $? # Output: 2
```

### 4. Launch the IBM 3270 CRT Operations Cockpit
```bash
cd ui
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.
- **PF1**: Copybook AST & Byte Layout (shows `SYNC` slack byte injection).
- **PF2**: 52-Byte CP-037 Hex Memory Dump with color-coded field overlays.
- **PF3**: Golden Vectors (COMP-3, Zoned Overpunch, EBCDIC sort keys).
- **PF4**: S0C7 System Abend Exception Monitor.
- **PF5**: Live Fuzzer & Exit Code 2 VETO Sentinel.
- **PF9**: Toggle between P31 Green and P4 Amber phosphor modes.

---

## 8. Kiroween 2026 Competitive Alignment

| Criterion | MainframeGhost Implementation |
| :--- | :--- |
| **Track 1: Resurrection ($5k)** | Resurrects 67-year-old COBOL (1959) copybooks, EBCDIC CP-037 collating sequences, and System/390 packed decimal arithmetic into modern cloud environments. |
| **Track 2: Frankenstein ($5k)** | Stitches legacy IBM mainframe binary memory layouts and IBM 3270 terminal protocols directly into AWS Bedrock and Kiro agentic IDE hooks. |
| **Track 4: Costume Contest ($5k)** | Recreates the physical IBM 3278-2 display station with P31 green/P4 amber phosphor decay, scanline bloom, and procedural Web Audio beam-spring acoustics. |
| **Best Startup Project ($10k)** | Solves the primary cause behind the 74% enterprise banking modernization failure rate, targeting a multi-billion dollar enterprise TAM. |
| **Grand Prize ($30k)** | End-to-end integration: AWS Bedrock Claude 3.5 Sonnet transpiler, Kiro v2 hooks returning POSIX Exit Code 2, 64/64 pytest tests, and a fully interactive operations cockpit. |

---

## 9. License

Apache-2.0 License. See [LICENSE](LICENSE) for details.
