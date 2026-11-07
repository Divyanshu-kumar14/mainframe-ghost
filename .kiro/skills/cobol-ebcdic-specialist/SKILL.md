---
name: cobol-ebcdic-specialist
description: Deep expertise in IBM System/360, System/370, System/390, and z/Architecture COBOL binary data representations, EBCDIC CP-037 collating sequences, Packed Decimal (COMP-3), Zoned Decimal sign overpunching, REDEFINES memory overlays, SYNCHRONIZED alignment slack bytes, and S0C7 Data Exception Abends. Use whenever parsing COBOL copybooks, converting mainframe binary data, or verifying semantic byte parity.
---

# IBM z/OS COBOL & EBCDIC Specialist Skill

This skill provides comprehensive, first-principles domain knowledge for IBM mainframe systems programming, COBOL copybook structure parsing, and binary/packed decimal arithmetic.

---

## 1. EBCDIC CP-037 vs. ASCII Collating Sequence Inversion

### The Problem
IBM z/OS uses EBCDIC Code Page 037, whereas modern cloud databases (PostgreSQL, MySQL, DynamoDB) and programming languages (Python, JavaScript, Go) use ASCII/UTF-8.

- **Mainframe EBCDIC Order:** Lowercase letters < Uppercase letters < Numeric Digits
  $$\text{Collating Sequence: } [a \dots z] < [A \dots Z] < [0 \dots 9]$$
  - Digits `0–9` map to hex `0xF0`–`0xF9`.
  - Uppercase `A–Z` map to hex `0xC1–0xC9`, `0xD1–0xD9`, `0xE2–0xE9`.
  - Lowercase `a–z` map to hex `0x81–0x89`, `0x91–0x99`, `0xA2–0xA9`.

- **Cloud ASCII Order:** Numeric Digits < Uppercase letters < Lowercase letters
  $$\text{Collating Sequence: } [0 \dots 9] < [A \dots Z] < [a \dots z]$$
  - Digits `0–9` map to hex `0x30`–`0x39`.
  - Uppercase `A–Z` map to hex `0x41`–`0x5A`.
  - Lowercase `a–z` map to hex `0x61`–`0x7A`.

### Implementation Rule
When sorting alphanumeric transaction batches, merge files, or building search indexes, **never sort using native ASCII string comparisons**. Apply an explicit EBCDIC CP-037 key transform:

```python
EBCDIC_COLLATE_TABLE = bytes.maketrans(
    bytes(range(256)),
    # Maps ASCII byte value to its relative rank in IBM EBCDIC CP-037
    bytes(ord(c.encode('cp037')) if c else b for b in range(256) for c in [chr(b)])
)

def ebcdic_sort_key(s: str) -> bytes:
    """Sort key that preserves mainframe batch ledger ordering in ASCII environments."""
    return s.encode('cp037')
```

---

## 2. IBM Packed Decimal (`COMP-3`) Encoding & Decoding

### Byte Length Formula
For a field with $D$ declared decimal digits (`PIC S9(D) COMP-3`):
$$L = \left\lfloor \frac{D}{2} \right\rfloor + 1 = \left\lceil \frac{D + 1}{2} \right\rceil$$

### Sign Nibbles (Lowest 4 bits of the final byte)
- `0xC`: Preferred positive (standard signed `+`)
- `0xD`: Preferred negative (standard signed `-`)
- `0xF`: Default positive (unsigned values `PIC 9(D)`)

### The Even-Digit Alignment Trap
When $D$ is even (e.g., $D=6$ in `PIC S9(6) COMP-3`):
- Byte length is $\lfloor 6/2 \rfloor + 1 = 4$ bytes (8 nibbles).
- Since $D=6$ plus 1 sign nibble equals 7 nibbles, the IBM compiler prepends an **implicit zero nibble (`0x0`)** into the highest position of Byte 0.
- `+123456` $\longrightarrow$ `0x01 0x23 0x45 0x6C`
- `-123456` $\longrightarrow$ `0x01 0x23 0x45 0x6D`

### Decoding Algorithm
```python
from decimal import Decimal

def decode_comp3(data: bytes, scale: int = 0) -> Decimal:
    """Decodes IBM System/390 COMP-3 packed decimal bytes into Decimal."""
    hex_str = data.hex()
    sign_nibble = hex_str[-1].upper()
    digits_str = hex_str[:-1]

    # Validate digit nibbles (0-9)
    for ch in digits_str:
        if ch not in "0123456789":
            raise ValueError(f"S0C7 Abend: Invalid decimal digit nibble 0x{ch}")

    # Validate sign nibble
    if sign_nibble in ("C", "F"):
        sign = 1
    elif sign_nibble == "D":
        sign = -1
    else:
        raise ValueError(f"S0C7 Abend: Invalid packed decimal sign nibble 0x{sign_nibble}")

    value = Decimal(digits_str) * sign
    if scale > 0:
        value = value / (Decimal(10) ** scale)
    return value
```

---

## 3. Zoned Decimal (`USAGE DISPLAY`) Sign Overpunching

Mainframe punchcards and sequential tape datasets encode signed integers without allocating an extra character for `+` or `-`. The algebraic sign is overpunched into the high zone nibble of the trailing byte.

### Zone Overpunch Matrix
| Digit | Positive (`0xC` Zone) | Negative (`0xD` Zone) |
| :---: | :---: | :---: |
| **0** | `{` (`0xC0`) | `}` (`0xD0`) |
| **1** | `A` (`0xC1`) | `J` (`0xD1`) |
| **2** | `B` (`0xC2`) | `K` (`0xD2`) |
| **3** | `C` (`0xC3`) | `L` (`0xD3`) |
| **4** | `D` (`0xC4`) | `M` (`0xD4`) |
| **5** | `E` (`0xC5`) | `N` (`0xD5`) |
| **6** | `F` (`0xC6`) | `O` (`0xD6`) |
| **7** | `G` (`0xC7`) | `P` (`0xD7`) |
| **8** | `H` (`0xC8`) | `Q` (`0xD8`) |
| **9** | `I` (`0xC9`) | `R` (`0xD9`) |

### Example Ingestion
- Ingesting `+12345` yields ASCII `"1234E"`.
- Ingesting `-12345` yields ASCII `"1234N"`.
- Calling `int("1234E")` will crash with `ValueError`. Always pass zoned strings through the overpunch translator.

---

## 4. `REDEFINES` Memory Overlay Aliasing

COBOL structures use `REDEFINES` to alias physical memory without copying bytes.

```cobol
01  TRANSACTION-RECORD.
    05  TX-DATE             PIC 9(8).
    05  TX-DATE-PARTS REDEFINES TX-DATE.
        10  TX-YEAR         PIC 9(4).
        10  TX-MONTH        PIC 9(2).
        10  TX-DAY          PIC 9(2).
```

### Rule for Modern Transpilers
Never transpile `REDEFINES` into independent class properties with separate heap allocations. Implement a backing `bytearray` with `memoryview` slice pointers:

```python
class TransactionRecord:
    def __init__(self, raw: bytearray = None):
        self._buf = raw if raw is not None else bytearray(8)

    @property
    def tx_date(self) -> str:
        return self._buf[0:8].decode('ascii')

    @tx_date.setter
    def tx_date(self, val: str):
        self._buf[0:8] = val.encode('ascii')[:8].ljust(8, b' ')

    @property
    def tx_year(self) -> str:
        return self._buf[0:4].decode('ascii')

    @tx_year.setter
    def tx_year(self, val: str):
        self._buf[0:4] = val.encode('ascii')[:4].ljust(4, b' ')
```

---

## 5. `SYNCHRONIZED` Alignment Slack Bytes

IBM compilers align binary numbers (`COMP` / binary integers) to natural hardware boundaries:
- Halfword (`PIC S9(4) COMP` = 2 bytes): Must start on an address divisible by 2.
- Fullword (`PIC S9(9) COMP` = 4 bytes): Must start on an address divisible by 4.
- Doubleword (`PIC S9(18) COMP` = 8 bytes): Must start on an address divisible by 8.

If previous fields leave the buffer unaligned, the compiler injects **1 to 3 invisible slack bytes** (padding).
Always calculate cumulative byte offsets modulo 2, 4, or 8 and add alignment slack bytes.

---

## 6. S0C7 Data Exception Abend Emulation

When non-numeric data is loaded into numeric fields or packed decimal math encounters an invalid sign nibble, IBM System/390 generates a hardware data exception:
$$\mathbf{S0C7 \text{ Abend: Decimal Data Exception}}$$
Modern parity sentinels must detect invalid nibbles and simulate the S0C7 exception rather than silently corrupting data or ignoring the error.
