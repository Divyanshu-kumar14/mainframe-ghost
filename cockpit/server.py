#!/usr/bin/env python3
"""Cockpit API: the real engine behind the 3270 UI. Standard library only.

    python3 -m cockpit.server                 # http://127.0.0.1:8737, exec enabled
    python3 -m cockpit.server --host 0.0.0.0  # public: candidate execution disabled

Endpoints (JSON in, JSON out; numbers travel as strings, bodies are parsed with
parse_float=Decimal):

    GET  /api/health                      engine, oracle and sandbox status
    POST /api/comp3   {hex, pic}          unpack COMP-3, nibble breakdown, S0C7
    POST /api/pack    {value, pic}        pack a decimal string as COMP-3
    POST /api/zoned   {text, pic}         decode zoned overpunch ("1234N")
    POST /api/sort    {keys: [...]}       ASCII vs EBCDIC CP-037 order
    POST /api/layout  {copybook}          byte layout, REDEFINES, SYNC slack
    POST /api/verify  {code, target?}     the PreToolUse verdict for a proposed write:
                                          static scan + sandboxed run vs GnuCOBOL

``/api/verify`` executes submitted code (in the sentinel sandbox). It is enabled
only when the server listens on a loopback address. On any other address it
returns 403, and the UI falls back to the precomputed verdicts.

Everything else is served from ui/dist (single-page app fallback to index.html).
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import mimetypes
import os
import sys
import threading
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.cobol_oracle import OracleError, fixtures_present, load_oracle  # noqa: E402
from engine.comp3_packer import S0C7Abend, describe_comp3, encode_comp3  # noqa: E402
from engine.copybook_parser import CopybookError, parse_copybook, parse_pic  # noqa: E402
from engine.ebcdic_codec import decode_zoned, ebcdic_sorted  # noqa: E402
from engine.shadow_fuzzer import (  # noqa: E402
    DEFAULT_RECORDS,
    DEFAULT_SEED,
    netns_available,
    render_3270,
    verify_stdin,
)

DIST = ROOT / "ui" / "dist"
MAX_BODY = 256 * 1024
MAX_CODE = 100 * 1024
MAX_COPYBOOK = 64 * 1024
MAX_KEYS = 2000
VERIFY_SLOTS = threading.BoundedSemaphore(2)


class ApiError(ValueError):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


def _text(body: dict, key: str, limit: int) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(f"{key}: required non-empty string")
    if len(value.encode("utf-8")) > limit:
        raise ApiError(f"{key}: longer than {limit} bytes")
    return value


def _numeric_pic(body: dict) -> tuple[int, int, str]:
    raw = _text(body, "pic", 40).upper().replace(" ", "")
    for suffix in ("COMP-3", "PACKED-DECIMAL", "COMP3"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
    try:
        info = parse_pic(raw)
    except CopybookError as exc:
        raise ApiError(str(exc)) from None
    if info.category != "numeric" or info.digits > 31:
        raise ApiError("pic: numeric PIC with at most 31 digits required, e.g. S9(7)V99")
    return info.digits, info.scale, info.text


def comp3(body: dict) -> dict:
    digits, scale, pic = _numeric_pic(body)
    return {"pic": pic, **describe_comp3(_text(body, "hex", 200), digits, scale)}


def pack(body: dict) -> dict:
    digits, scale, pic = _numeric_pic(body)
    text = _text(body, "value", 64).strip()
    try:
        value = Decimal(text)
        if not value.is_finite():
            raise ValueError
        data = encode_comp3(value, digits, scale)
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ApiError(f"value: cannot pack {text!r} into PIC {pic}: {exc}") from None
    return {"pic": pic, "input": text, **describe_comp3(data.hex(), digits, scale)}


def zoned(body: dict) -> dict:
    _, scale, pic = _numeric_pic(body)
    text = _text(body, "text", 64).strip()
    try:
        value = decode_zoned(text, scale)
    except S0C7Abend as exc:
        return {"pic": pic, "text": text, "valid": False, "s0c7": True, "error": str(exc)}
    except ValueError as exc:
        raise ApiError(str(exc)) from None
    try:
        ebcdic = text.encode("cp037").hex(" ").upper()
    except UnicodeEncodeError:
        ebcdic = None
    return {"pic": pic, "text": text, "valid": True, "s0c7": False, "value": str(value),
            "ebcdic_hex": ebcdic}


def sort_keys(body: dict) -> dict:
    keys = body.get("keys")
    if not isinstance(keys, list) or not keys or len(keys) > MAX_KEYS:
        raise ApiError(f"keys: list of 1..{MAX_KEYS} strings required")
    if not all(isinstance(k, str) and 0 < len(k) <= 64 for k in keys):
        raise ApiError("keys: every key must be a string of 1..64 characters")
    try:
        ebcdic = ebcdic_sorted(keys)
    except UnicodeEncodeError:
        raise ApiError("keys: characters outside EBCDIC CP-037") from None
    return {"ascii": sorted(keys), "ebcdic": ebcdic,
            "first_bytes": {k: {"ascii": f"{ord(k[0]):02X}",
                                "ebcdic": f"{k.encode('cp037')[0]:02X}"} for k in keys}}


def layout(body: dict) -> dict:
    text = _text(body, "copybook", MAX_COPYBOOK)
    errors = []
    for fixed in (False, True):
        try:
            book = parse_copybook(text, fixed_format=fixed)
            return {"fixed_format": fixed, "layout": book.layout_table(),
                    "records": [{"name": r.name, "size": r.size} for r in book.records]}
        except CopybookError as exc:
            errors.append(str(exc))
    raise ApiError(f"copybook: {errors[-1]}")


def verify(body: dict, exec_enabled: bool) -> dict:
    if not exec_enabled:
        raise ApiError("candidate execution is disabled on this public server; run the "
                       "cockpit locally (python3 -m cockpit.server) to verify your own code",
                       HTTPStatus.FORBIDDEN)
    code = _text(body, "code", MAX_CODE)
    target = body.get("target") or "services/candidate_service.py"
    if (not isinstance(target, str) or not target.endswith(".py") or ".." in target
            or target.startswith(("/", "tests/", ".kiro/"))):
        raise ApiError("target: relative .py path outside tests/ and .kiro/ required")
    payload = {"hook_event_name": "PreToolUse", "tool_name": "fs_write",
               "tool_input": {"path": target, "text": code}}
    if not VERIFY_SLOTS.acquire(timeout=60):
        raise ApiError("sentinel busy, retry", HTTPStatus.SERVICE_UNAVAILABLE)
    try:
        exit_code, report = verify_stdin(json.dumps(payload), DEFAULT_RECORDS, DEFAULT_SEED)
    finally:
        VERIFY_SLOTS.release()
    return {"exit_code": exit_code, "target": target, "report": report.as_dict(),
            "screen": render_3270(report).splitlines(), "summary": report.summary()}


def health(exec_enabled: bool) -> dict:
    oracle = None
    if fixtures_present():
        try:
            manifest = load_oracle().manifest
            oracle = {"compiler": manifest["compiler"], "records": manifest["records"]}
        except OracleError as exc:
            oracle = {"error": str(exc)}
    return {"ok": True, "exec_enabled": exec_enabled, "oracle": oracle,
            "sandbox": ("netns+rlimits" if netns_available() else "rlimits") if exec_enabled
            else None}


ROUTES = {"/api/comp3": comp3, "/api/pack": pack, "/api/zoned": zoned,
          "/api/sort": sort_keys, "/api/layout": layout}


class Handler(BaseHTTPRequestHandler):
    server_version = "MainframeGhost/1.0"
    exec_enabled = False

    def log_message(self, fmt: str, *args) -> None:  # one line per request on stderr
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    def _send(self, status: int, payload: bytes, ctype: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            return self._json(200, health(self.exec_enabled))
        if path.startswith("/api/"):
            return self._json(404, {"error": "not found"})
        return self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                raise ApiError(f"body must be 1..{MAX_BODY} bytes",
                               HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                raise ApiError("Content-Type must be application/json",
                               HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            body = json.loads(self.rfile.read(length), parse_float=Decimal)
            if not isinstance(body, dict):
                raise ApiError("body must be a JSON object")
            if path == "/api/verify":
                return self._json(200, verify(body, self.exec_enabled))
            route = ROUTES.get(path)
            if route is None:
                return self._json(404, {"error": "not found"})
            return self._json(200, route(body))
        except ApiError as exc:
            return self._json(exc.status, {"error": str(exc)})
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._json(400, {"error": "malformed JSON"})

    def _static(self, path: str) -> None:
        if not DIST.is_dir():
            return self._json(404, {"error": "ui/dist not built: cd ui && npm run build"})
        target = (DIST / path.lstrip("/")).resolve()
        if not target.is_relative_to(DIST.resolve()) or not target.is_file():
            target = DIST / "index.html"  # SPA fallback
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        cache = "public, max-age=31536000, immutable" if "/assets/" in str(target) else "no-cache"
        self._send(200, target.read_bytes(), ctype, cache)


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MainframeGhost cockpit API")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8737")))
    parser.add_argument("--no-exec", action="store_true",
                        help="disable /api/verify even on loopback")
    args = parser.parse_args(argv)
    Handler.exec_enabled = _is_loopback(args.host) and not args.no_exec
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    mode = "candidate execution ENABLED (loopback)" if Handler.exec_enabled else \
        "candidate execution disabled"
    print(f"MainframeGhost cockpit on http://{args.host}:{args.port}  [{mode}]", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
