"""COBOL copybook parser and byte-layout engine.

Builds an AST of data-description entries (levels 01-49, plus 77; 88 condition
names are skipped), computes byte offsets, overlays ``REDEFINES`` onto the same
storage, and injects ``SYNCHRONIZED`` slack bytes (PRD Failure Modes 4 and 5).

Supported clauses: PIC/PICTURE (X, A, 9, S, V with repeat counts), USAGE and bare
DISPLAY / COMP / COMP-3 / COMP-1 / COMP-2 / BINARY / PACKED-DECIMAL,
SYNC/SYNCHRONIZED [LEFT|RIGHT], REDEFINES, VALUE (ignored), JUSTIFIED (ignored).
Not supported (raises CopybookError): OCCURS, SIGN, RENAMES (66), edited pictures,
P scaling, national/DBCS.

``Record`` is a view over ONE shared bytearray; every field, including REDEFINES
aliases, reads and writes fixed byte offsets in that buffer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .comp3_packer import (
    coerce_decimal,
    decimal_from_scaled_int,
    decode_comp3,
    encode_comp3,
    packed_length,
    scaled_int,
)
from .ebcdic_codec import decode_zoned_bytes, encode_zoned_bytes

EBCDIC_SPACE = 0x40


class CopybookError(ValueError):
    """Raised for syntax errors or unsupported constructs in a copybook."""


@dataclass(frozen=True)
class PicInfo:
    category: str      # "numeric" or "alnum"
    digits: int        # total digit positions (numeric) or character count (alnum)
    scale: int         # digits right of V
    signed: bool
    text: str


@dataclass(eq=False)
class Field:
    level: int
    name: str
    pic: PicInfo | None = None
    usage: str | None = None          # explicit usage; None means inherit/DISPLAY
    sync: bool = False
    redefines: str | None = None
    parent: Field | None = None
    children: list[Field] = field(default_factory=list)
    # Computed by layout
    offset: int = 0
    size: int = 0
    slack_before: int = 0
    effective_usage: str = "DISPLAY"
    effective_sync: bool = False
    redef_target: Field | None = None

    @property
    def is_elementary(self) -> bool:
        """PIC items, plus COMP-1/COMP-2 items (which take no PIC)."""
        return self.pic is not None or (
            not self.children and self.effective_usage in ("COMP-1", "COMP-2"))

    @property
    def is_group(self) -> bool:
        return not self.is_elementary

    @property
    def path(self) -> str:
        names = []
        node: Field | None = self
        while node is not None:
            names.append(node.name)
            node = node.parent
        return ".".join(reversed(names))

    @property
    def is_overlay(self) -> bool:
        """True if this field or an ancestor (below the 01 root) REDEFINES other storage."""
        node: Field | None = self
        while node is not None and node.parent is not None:
            if node.redefines:
                return True
            node = node.parent
        return False

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class Copybook:
    records: list[Field]

    def record(self, name: str | None = None) -> Field:
        if name is None:
            if len(self.records) != 1:
                raise CopybookError(f"copybook has {len(self.records)} records; specify a name")
            return self.records[0]
        wanted = name.upper()
        for rec in self.records:
            if rec.name == wanted:
                return rec
        raise CopybookError(f"record {name!r} not found")

    def layout_table(self) -> list[dict]:
        """Flat, JSON-friendly layout (offsets, sizes, overlays, slack) for every field."""
        rows: list[dict] = []
        for rec in self.records:
            for fld in rec.walk():
                rows.append({
                    "record": rec.name,
                    "path": fld.path,
                    "level": fld.level,
                    "name": fld.name,
                    "pic": fld.pic.text if fld.pic else None,
                    "usage": fld.effective_usage if fld.is_elementary else None,
                    "offset": fld.offset,
                    "size": fld.size,
                    "end": fld.offset + fld.size,
                    "redefines": fld.redefines,
                    "sync": fld.effective_sync and fld.is_elementary,
                    "slack_before": fld.slack_before,
                    "slack_range": ([fld.offset - fld.slack_before, fld.offset]
                                    if fld.slack_before else None),
                })
        return rows


# --------------------------------------------------------------------------- parsing

_USAGE_ALIASES = {
    "DISPLAY": "DISPLAY",
    "COMP": "BINARY", "COMPUTATIONAL": "BINARY", "BINARY": "BINARY",
    "COMP-4": "BINARY", "COMPUTATIONAL-4": "BINARY",
    "COMP-5": "BINARY", "COMPUTATIONAL-5": "BINARY",
    "COMP-3": "COMP-3", "COMPUTATIONAL-3": "COMP-3", "PACKED-DECIMAL": "COMP-3",
    "COMP-1": "COMP-1", "COMPUTATIONAL-1": "COMP-1",
    "COMP-2": "COMP-2", "COMPUTATIONAL-2": "COMP-2",
}
_CLAUSE_WORDS = {"PIC", "PICTURE", "USAGE", "SYNC", "SYNCHRONIZED", "REDEFINES", "VALUE",
                 "OCCURS", "JUST", "JUSTIFIED", "SIGN", "BLANK", *_USAGE_ALIASES}


def _clean(text: str, fixed_format: bool) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        if fixed_format:
            if len(raw) <= 6:
                continue
            if raw[6] in "*/":
                continue
            line = raw[7:72]
        else:
            line = raw
            if line.lstrip().startswith("*"):
                continue
        line = line.split("*>", 1)[0]
        if line.strip():
            lines.append(line)
    return "\n".join(lines)


def parse_pic(pic: str) -> PicInfo:
    text = pic.upper()
    i = 0
    signed = False
    if text.startswith("S"):
        signed = True
        i = 1
    int_digits = frac_digits = char_count = 0
    seen_v = False
    kinds: set[str] = set()
    if i >= len(text):
        raise CopybookError(f"empty PIC {pic!r}")
    while i < len(text):
        char = text[i]
        i += 1
        if char == "V":
            if seen_v:
                raise CopybookError(f"multiple V in PIC {pic!r}")
            seen_v = True
            continue
        if char not in "9XA":
            raise CopybookError(f"unsupported PIC symbol {char!r} in {pic!r}")
        count = 1
        if i < len(text) and text[i] == "(":
            close = text.find(")", i)
            body = text[i + 1:close] if close != -1 else ""
            if not body.isascii() or not body.isdigit() or int(body) < 1:
                raise CopybookError(f"bad repeat count in PIC {pic!r}")
            count = int(body)
            i = close + 1
        kinds.add(char)
        if char == "9":
            if seen_v:
                frac_digits += count
            else:
                int_digits += count
        else:
            char_count += count
    if kinds <= {"9"}:
        digits = int_digits + frac_digits
        if digits == 0:
            raise CopybookError(f"numeric PIC {pic!r} has no digits")
        return PicInfo("numeric", digits, frac_digits, signed, text)
    if signed or seen_v:
        raise CopybookError(f"S/V not allowed in alphanumeric PIC {pic!r}")
    return PicInfo("alnum", char_count + int_digits, 0, False, text)


def _tokenize_statement(statement: str) -> list[str]:
    return re.findall(r"'[^']*'|\"[^\"]*\"|\S+", statement)


def _parse_entry(statement: str) -> Field | None:
    tokens = _tokenize_statement(statement)
    if not tokens:
        return None
    if not tokens[0].isascii() or not tokens[0].isdigit():
        raise CopybookError(f"entry must start with a level number: {statement!r}")
    level = int(tokens[0])
    if level == 88:
        return None
    if level == 66:
        raise CopybookError("level 66 RENAMES is not supported")
    if not (1 <= level <= 49 or level == 77):
        raise CopybookError(f"invalid level number {level}")
    pos = 1
    name = "FILLER"
    if pos < len(tokens) and tokens[pos].upper() not in _CLAUSE_WORDS:
        name = tokens[pos].upper()
        pos += 1
    entry = Field(level=level, name=name)
    while pos < len(tokens):
        word = tokens[pos].upper()
        pos += 1
        if word in ("PIC", "PICTURE"):
            if pos < len(tokens) and tokens[pos].upper() == "IS":
                pos += 1
            if pos >= len(tokens):
                raise CopybookError(f"PIC without picture string in {name}")
            entry.pic = parse_pic(tokens[pos])
            pos += 1
        elif word == "USAGE":
            if pos < len(tokens) and tokens[pos].upper() == "IS":
                pos += 1
            if pos >= len(tokens):
                raise CopybookError(f"USAGE without value in {name}")
            usage_word = tokens[pos].upper()
            pos += 1
            if usage_word not in _USAGE_ALIASES:
                raise CopybookError(f"unsupported USAGE {usage_word!r} in {name}")
            entry.usage = _USAGE_ALIASES[usage_word]
        elif word in _USAGE_ALIASES:
            entry.usage = _USAGE_ALIASES[word]
        elif word in ("SYNC", "SYNCHRONIZED"):
            entry.sync = True
            if pos < len(tokens) and tokens[pos].upper() in ("LEFT", "RIGHT"):
                pos += 1
        elif word == "REDEFINES":
            if pos >= len(tokens):
                raise CopybookError(f"REDEFINES without target in {name}")
            entry.redefines = tokens[pos].upper()
            pos += 1
        elif word == "VALUE":
            if pos < len(tokens) and tokens[pos].upper() in ("IS", "ARE"):
                pos += 1
            pos += 1  # the literal (quoted strings are single tokens)
        elif word in ("JUST", "JUSTIFIED"):
            if pos < len(tokens) and tokens[pos].upper() == "RIGHT":
                pos += 1
        elif word in ("OCCURS", "SIGN", "BLANK"):
            raise CopybookError(f"{word} clause is not supported (field {name})")
        else:
            raise CopybookError(f"unexpected token {word!r} in entry {name}")
    return entry


def _build_tree(entries: list[Field]) -> list[Field]:
    roots: list[Field] = []
    stack: list[Field] = []
    for entry in entries:
        if entry.level in (1, 77):
            stack = [entry]
            roots.append(entry)
            continue
        while stack and stack[-1].level >= entry.level:
            stack.pop()
        if not stack:
            raise CopybookError(f"{entry.name} (level {entry.level:02d}) has no parent group")
        entry.parent = stack[-1]
        stack[-1].children.append(entry)
        stack.append(entry)
    return roots


# --------------------------------------------------------------------------- layout

def _elementary_size(fld: Field) -> int:
    pic = fld.pic
    usage = fld.effective_usage
    if usage in ("COMP-1", "COMP-2"):
        if pic is not None:
            raise CopybookError(f"{fld.name}: {usage} cannot have a PIC")
        return 4 if usage == "COMP-1" else 8
    if pic is None:
        raise CopybookError(f"{fld.name}: elementary item requires a PIC")
    if pic.category == "alnum":
        if usage != "DISPLAY":
            raise CopybookError(f"{fld.name}: alphanumeric PIC cannot be {usage}")
        return pic.digits
    if usage == "DISPLAY":
        return pic.digits
    if usage == "COMP-3":
        return packed_length(pic.digits)
    if usage == "BINARY":
        if pic.digits <= 4:
            return 2
        if pic.digits <= 9:
            return 4
        if pic.digits <= 18:
            return 8
        raise CopybookError(f"{fld.name}: binary item with {pic.digits} digits exceeds 18")
    raise CopybookError(f"{fld.name}: unsupported usage {usage}")


def _alignment(fld: Field, size: int) -> int:
    """Natural boundary for a SYNCHRONIZED binary item: 2, 4 or 8 bytes."""
    if fld.effective_usage in ("BINARY", "COMP-1", "COMP-2") and size in (2, 4, 8):
        return size
    return 1


def _resolve_inheritance(fld: Field) -> None:
    parent = fld.parent
    if fld.usage is not None:
        fld.effective_usage = fld.usage
    elif parent is not None:
        fld.effective_usage = parent.effective_usage
    fld.effective_sync = fld.sync or (parent.effective_sync if parent else False)
    for child in fld.children:
        _resolve_inheritance(child)


def _layout(fld: Field, start: int) -> int:
    """Assign offsets for ``fld`` placed at ``start``. Returns the end offset."""
    fld.offset = start
    if fld.is_elementary:
        if fld.children:
            raise CopybookError(f"{fld.name}: elementary item cannot have subordinate items")
        fld.size = _elementary_size(fld)
        return start + fld.size
    if not fld.children:
        raise CopybookError(f"{fld.name}: group item has no subordinate items")
    cursor = start
    furthest = start
    placed: list[Field] = []
    for child in fld.children:
        if child.redefines:
            target = next((p for p in reversed(placed) if p.name == child.redefines), None)
            if target is None:
                raise CopybookError(f"{child.name}: REDEFINES target {child.redefines} "
                                    "not found among preceding siblings")
            base = target
            while base.redef_target is not None:
                base = base.redef_target
            child.redef_target = base
            end = _layout(child, base.offset)
            child.size = end - base.offset
            if child.size > base.size:
                raise CopybookError(f"{child.name} ({child.size} bytes) is larger than "
                                    f"redefined {base.name} ({base.size} bytes)")
            furthest = max(furthest, end)
        else:
            slack = 0
            if child.effective_sync and child.is_elementary:
                width = _elementary_size(child)
                align = _alignment(child, width)
                slack = (-(cursor - _record_root(fld).offset)) % align
            child.slack_before = slack
            end = _layout(child, cursor + slack)
            child.size = end - (cursor + slack)
            cursor = end
            furthest = max(furthest, end)
        placed.append(child)
    fld.size = max(cursor, furthest) - start
    return start + fld.size


def _record_root(fld: Field) -> Field:
    node = fld
    while node.parent is not None:
        node = node.parent
    return node


def parse_copybook(text: str, fixed_format: bool = False) -> Copybook:
    """Parse copybook text into a laid-out Copybook (AST + byte offsets)."""
    cleaned = _clean(text, fixed_format)
    statements = [s.strip() for s in re.split(r"\.(?=\s|$)", cleaned) if s.strip()]
    entries: list[Field] = []
    for statement in statements:
        entry = _parse_entry(statement)
        if entry is not None:
            entries.append(entry)
    if not entries:
        raise CopybookError("no data description entries found")
    roots = _build_tree(entries)
    for root in roots:
        _resolve_inheritance(root)
        end = _layout(root, 0)
        root.size = end
    return Copybook(roots)


# --------------------------------------------------------------------------- record

class Record:
    """Typed accessor over one shared bytearray (REDEFINES = overlapping byte slices)."""

    def __init__(self, layout: Field | Copybook, data: bytes | bytearray | None = None) -> None:
        self.root = layout.record() if isinstance(layout, Copybook) else layout
        if data is None:
            self.buffer = bytearray(self.root.size)
            self._initialize()
        else:
            if len(data) != self.root.size:
                raise ValueError(f"record is {self.root.size} bytes, got {len(data)}")
            self.buffer = bytearray(data)

    # lookup ------------------------------------------------------------
    def find(self, name: str) -> Field:
        parts = [p.upper() for p in name.split(".")]
        matches = []
        for fld in self.root.walk():
            if fld.name != parts[-1]:
                continue
            ancestors = [a.name for a in reversed(list(_ancestors(fld)))]  # outermost first
            it = iter(ancestors)
            if all(any(p == a for a in it) for p in parts[:-1]):
                matches.append(fld)
        if not matches:
            raise KeyError(name)
        if len(matches) > 1:
            raise KeyError(f"{name} is ambiguous; qualify it (matches: "
                           f"{', '.join(m.path for m in matches)})")
        return matches[0]

    def view(self, name: str) -> memoryview:
        """Writable memoryview over the field's bytes in the shared buffer."""
        fld = self.find(name)
        return memoryview(self.buffer)[fld.offset:fld.offset + fld.size]

    # typed access ------------------------------------------------------
    def get(self, name: str):
        fld = self.find(name)
        raw = bytes(self.buffer[fld.offset:fld.offset + fld.size])
        if fld.pic is None:
            return raw
        pic = fld.pic
        if pic.category == "alnum":
            return raw.decode("cp037")
        usage = fld.effective_usage
        if usage == "DISPLAY":
            return decode_zoned_bytes(raw, pic.scale, pic.signed)
        if usage == "COMP-3":
            return decode_comp3(raw, pic.digits, pic.scale)
        if usage == "BINARY":
            number = int.from_bytes(raw, "big", signed=pic.signed)
            return decimal_from_scaled_int(number, pic.scale)
        raise NotImplementedError(f"{usage} fields are floating point and not supported")

    def set(self, name: str, value) -> None:
        fld = self.find(name)
        start, end = fld.offset, fld.offset + fld.size
        if fld.pic is None:
            payload = bytes(value)
            if len(payload) != fld.size:
                raise ValueError(f"{fld.name} is {fld.size} bytes, got {len(payload)}")
            self.buffer[start:end] = payload
            return
        pic = fld.pic
        usage = fld.effective_usage
        if pic.category == "alnum":
            if not isinstance(value, str):
                raise TypeError("alphanumeric fields take str")
            encoded = value.encode("cp037")[:fld.size]  # COBOL MOVE truncates on the right
            self.buffer[start:end] = encoded.ljust(fld.size, bytes([EBCDIC_SPACE]))
        elif usage == "DISPLAY":
            self.buffer[start:end] = encode_zoned_bytes(value, pic.digits, pic.scale, pic.signed)
        elif usage == "COMP-3":
            self.buffer[start:end] = encode_comp3(value, pic.digits, pic.scale, pic.signed)
        elif usage == "BINARY":
            number = scaled_int(coerce_decimal(value), pic.scale)
            if len(str(abs(number))) > pic.digits:
                raise OverflowError(f"{fld.name}: value exceeds {pic.digits} digits")
            if number < 0 and not pic.signed:
                raise ValueError(f"{fld.name}: negative value in unsigned binary field")
            self.buffer[start:end] = number.to_bytes(fld.size, "big", signed=pic.signed)
        else:
            raise NotImplementedError(f"{usage} fields are floating point and not supported")

    __getitem__ = get
    __setitem__ = set

    def _initialize(self) -> None:
        for fld in self.root.walk():
            if fld.pic is None or fld.is_overlay:
                continue
            start, end = fld.offset, fld.offset + fld.size
            if fld.pic.category == "alnum":
                self.buffer[start:end] = bytes([EBCDIC_SPACE]) * fld.size
            elif fld.effective_usage == "DISPLAY":
                self.buffer[start:end] = encode_zoned_bytes(
                    Decimal(0), fld.pic.digits, 0, fld.pic.signed)
            elif fld.effective_usage == "COMP-3":
                self.buffer[start:end] = encode_comp3(
                    Decimal(0), fld.pic.digits, 0, fld.pic.signed)


def _ancestors(fld: Field):
    node = fld.parent
    while node is not None:
        yield node
        node = node.parent
