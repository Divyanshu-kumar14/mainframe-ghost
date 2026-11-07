---
name: aws-bedrock-lambda-modernizer
description: Patterns for porting COBOL to Python 3.12 services with Amazon Bedrock (Claude Sonnet 5.5) and AWS Lambda handlers, gated by the GnuCOBOL parity sentinel. Enforces Decimal-only arithmetic and zero-float guarantees. Use whenever invoking Bedrock for COBOL migration or writing a Lambda-style service in this repo.
---

# Amazon Bedrock & Lambda Modernization Skill

Guidance for turning the COBOL in `cobol/src/` into Python services under `services/`. The implementation lives in `services/bedrock_transpiler.py`; follow it rather than re-implementing the call.

---

## 1. Bedrock Transpiler

### Model
- **Model ID:** `us.anthropic.claude-sonnet-5-5` (US geo inference profile; `global.anthropic.claude-sonnet-5-5` also works). Override with `BEDROCK_MODEL_ID`.
- **Sampling:** send no `temperature`. Sonnet 5.5 always runs adaptive thinking, so output is not deterministic. That is why every response is verified.
- **max_tokens:** 16000 (thinking tokens count against it). A `stop_reason` of `max_tokens` is a rejection.

### Request shape (as built by `build_request`)
```python
body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 16000,
    "system": PROGRAM_PROMPT,          # parity rules + required function names
    "messages": [{"role": "user", "content": [{"type": "text", "text":
        "LAYOUT of COPY INTACCR (authoritative, computed by the parity engine):\n...\n\n"
        "<cobol>\n...program with COPY members inlined...\n</cobol>"}]}],
}
client.invoke_model(modelId="us.anthropic.claude-sonnet-5-5", body=json.dumps(body),
                    contentType="application/json", accept="application/json")
```

### Gate, never trust
1. Extract the fenced `python` block; ignore thinking blocks.
2. Static IEEE 754 scan (`engine.shadow_fuzzer.scan_source`).
3. `check_candidate(code, report, ...)`: run `accrue_monthly_interest` in the sandbox on 10,000 records and diff against GnuCOBOL output.
4. Any violation or drift: exit 2, write nothing. `--capture` keeps the raw output and verdict under `tests/fixtures/candidates/` either way.

Run it: `python3 -m services.bedrock_transpiler cobol/src/intaccr_batch.cbl -o services/bedrock_service.py --capture` (add `--naive` to drop the parity rules from the prompt).

---

## 2. Lambda Handler Standards

Reference: `services/hardened_service.py` (`lambda_handler`). It is a handler module; this repo does not deploy it.

```python
FIN_CTX = Context(prec=28, rounding=ROUND_DOWN)
CENT = Decimal("0.01")

def accrue_monthly_interest(balance: Decimal, annual_rate: Decimal) -> Decimal:
    if not isinstance(balance, Decimal) or not isinstance(annual_rate, Decimal):
        raise TypeError("balance and annual_rate must be decimal.Decimal")
    # Same order of operations as the COBOL: (BALANCE * RATE) / 12, then truncate.
    monthly = FIN_CTX.divide(FIN_CTX.multiply(balance, annual_rate), Decimal(12))
    return monthly.quantize(CENT, rounding=ROUND_DOWN, context=FIN_CTX)
```

- Parse bodies with `json.loads(body, parse_float=Decimal)`; money travels as JSON strings.
- Validate every input against its PIC (digits, scale, sign); reject `float` with `TypeError`, never `Decimal(str(x))` it.
- Keep the COBOL order of operations. Dividing the rate by 12 first changes intermediate precision.
- Return all numbers as strings; sort keys with `key=lambda s: s.encode("cp037")`.

---

## 3. Mapping Notes (not implemented here)

If the service grows beyond one batch step, typical targets are: VSAM KSDS to a relational table keyed on the CP-037 bytes of the key, CICS to API Gateway + Step Functions, RACF to IAM. None of these are part of this repository.

---

## 4. Preventing IEEE 754 Floating-Point Contamination

### Linting & Static Analysis Rule
When writing or auditing Python code destined for AWS Lambda financial services:
- Reject `float(...)` constructors.
- Reject `math.sqrt()` or `math.pow()` (use `Decimal.sqrt()`).
- In `json.loads`, always pass `parse_float=Decimal`.
- In database queries, always bind numeric parameters as strings or `Decimal` objects.
