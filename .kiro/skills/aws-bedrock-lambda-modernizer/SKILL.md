---
name: aws-bedrock-lambda-modernizer
description: Expert patterns for architecting mainframe modernizations on AWS using AWS Bedrock (Claude 3.5 Sonnet) for neural copybook transpilation and AWS Lambda (Python 3.12) for serverless execution. Enforces strict arbitrary-precision Decimal arithmetic, zero-float guarantees, and Aurora Serverless v2 ledger integration. Use whenever designing AWS serverless microservices or invoking Bedrock for COBOL migration.
---

# AWS Bedrock & Lambda Modernization Skill

This skill provides architectural guidance for migrating legacy IBM z/OS COBOL workloads to serverless AWS cloud infrastructure using AWS Bedrock and AWS Lambda.

---

## 1. AWS Bedrock Neural Transpiler Architecture

### Model Selection & Configuration
- **Model ID:** `anthropic.claude-3-5-sonnet-20241022-v2:0` (or `us.anthropic.claude-3-5-sonnet-20241022-v2:0` cross-region profile)
- **Temperature:** `0.0` (Mandatory for deterministic, reproducible code transpilation)
- **Top-P:** `1.0`

### Bedrock Boto3 Invocation Pattern
```python
import json
import boto3

bedrock = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1"
)

def transpile_cobol_copybook(copybook_source: str) -> str:
    prompt = f"""You are a mission-critical mainframe modernization compiler.
Translate the following COBOL copybook into a Python 3.12 data class.
CRITICAL RULES:
1. NEVER use float or double.
2. ALWAYS use decimal.Decimal with ROUND_DOWN context.
3. Map REDEFINES to bytearray slice properties.
4. Support EBCDIC CP-037 collating order.

COBOL SOURCE:
{copybook_source}
"""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.0,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    })
    
    response = bedrock.invoke_model(
        modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
        contentType="application/json",
        accept="application/json",
        body=body
    )
    
    result = json.loads(response["body"].read())
    return result["content"][0]["text"]
```

---

## 2. Serverless AWS Lambda Execution Standards

### Mandatory Decimal Arithmetic Context
Every Lambda handler executing financial logic must establish a strict `decimal.Context`:

```python
import json
from decimal import Decimal, Context, ROUND_DOWN

# Establish 28-digit precision matching IBM mainframe high-precision decimal math
FINANCIAL_CTX = Context(prec=28, rounding=ROUND_DOWN)

def lambda_handler(event, context):
    """
    AWS Lambda entrypoint for mainframe batch transaction processing.
    """
    # Reject float numbers at API gateway / SQS ingestion boundary
    body = json.loads(event.get("body", "{}"), parse_float=Decimal)
    
    principal = Decimal(str(body["principal"]))
    annual_rate = Decimal(str(body["annual_rate"]))
    months = Decimal(str(body["months"]))
    
    # Compute monthly interest with strict truncation (matching COBOL default)
    monthly_rate = FINANCIAL_CTX.divide(annual_rate, Decimal("12"))
    interest = FINANCIAL_CTX.multiply(principal, monthly_rate)
    
    # Quantize to 2 decimal places with ROUND_DOWN
    final_interest = interest.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "SUCCESS",
            "accrued_interest": str(final_interest)
        })
    }
```

---

## 3. Storage & Database Modernization Patterns

| Legacy Mainframe Primitive | AWS Cloud Target | Configuration Notes |
| :--- | :--- | :--- |
| **VSAM KSDS (Keyed Dataset)** | **Amazon Aurora PostgreSQL Serverless v2** | Create table with indexed primary keys using custom EBCDIC collation table. |
| **VSAM ESDS (Sequential)** | **Amazon DynamoDB or S3 Parquet** | High-throughput sequential ingestion with deterministic sorting keys. |
| **CICS Transaction Monitor** | **AWS Step Functions + API Gateway** | Provides distributed ACID transactions, sagas, and idempotency keys. |
| **IBM RACF Security** | **AWS IAM + AWS Secrets Manager** | Role-based least-privilege access and automatic credential rotation. |
| **SMF System Management Logs**| **Amazon CloudWatch Logs & OpenSearch** | Real-time structured telemetry, metric filters, and audit alarms. |

---

## 4. Preventing IEEE 754 Floating-Point Contamination

### Linting & Static Analysis Rule
When writing or auditing Python code destined for AWS Lambda financial services:
- Reject `float(...)` constructors.
- Reject `math.sqrt()` or `math.pow()` (use `Decimal.sqrt()`).
- In `json.loads`, always pass `parse_float=Decimal`.
- In database queries, always bind numeric parameters as strings or `Decimal` objects.
