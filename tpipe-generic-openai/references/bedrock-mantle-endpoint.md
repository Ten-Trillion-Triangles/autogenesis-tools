# Bedrock Mantle endpoint — integration reference

**Status:** research-stage facts verified against AWS docs as of 2026-07-28.
No code in `TPipe-GenericOpenAI/` has been modified yet to target this endpoint.
Treat this file as the source of truth for the integration plan, not a
contract — AWS may add models, change auth, or rename the endpoint surface.

## What Mantle is

A **separate regional endpoint service** in Amazon Bedrock that exposes
selected new models over an **OpenAI-compatible HTTP surface**, instead of
the Converse/Invoke API. Models on Mantle are NOT reachable from
`TPipe-Bedrock` — they don't support Converse.

Endpoint pattern:

```
https://bedrock-mantle.{region}.api.aws/openai/v1
```

Example: `https://bedrock-mantle.us-east-1.api.aws/openai/v1`.

AWS recommends Mantle over `bedrock-runtime` whenever possible for these
specific models.

## Authentication — two modes, same endpoint

| Mode | Use case | Wire shape |
|---|---|---|
| **Bedrock API key (bearer)** | OpenAI SDK, scripts | `Authorization: Bearer <key>` header. Short-term keys (≤12h) inherit IAM role permissions and can be minted from AWS creds via the `aws-bedrock-token-generator` package. |
| **AWS SigV4** | Production HTTP, no API key | Standard `Authorization: AWS4-HMAC-SHA256 …` headers. |

Minimum IAM policy for SigV4:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockMantleInference",
      "Effect": "Allow",
      "Action": [
        "bedrock-mantle:CreateInference",
        "bedrock-mantle:Get*",
        "bedrock-mantle:List*"
      ],
      "Resource": "arn:aws:bedrock-mantle:us-east-1:111122223333:project/*"
    },
    {
      "Sid": "BedrockMantleApiKeyAccess",
      "Effect": "Allow",
      "Action": "bedrock-mantle:CallWithBearerToken",
      "Resource": "*"
    }
  ]
}
```

Managed policies exist (added 2025-12-03):
`AmazonBedrockMantleFullAccess`, `AmazonBedrockMantleReadOnly`,
`AmazonBedrockMantleInferenceAccess`. SigV4 statement is sufficient on its
own; the bearer statement is only needed if using API keys.

## Models currently on Mantle (verified 2026-07-28, re-verified 2026-07-29 by direct Mantle probe)

| Provider | Model ID | Notes |
|---|---|---|
| OpenAI | `openai.gpt-5.6-sol` | flagship reasoning |
| OpenAI | `openai.gpt-5.6-terra` | |
| OpenAI | `openai.gpt-5.6-luna` | fast / cost-effective |
| Google | `google.gemma-4-31b` | 31B Gemma 4 (30.7B dense) |
| Google | `google.gemma-4-e2b` | efficient Gemma 4 (smallest: 5.1B total / 2.3B effective via Per-Layer Embeddings) |
| Google | `google.gemma-4-26b-a4b` | MoE, 25.2B total / 3.8B active per token (verified via direct Mantle probe 2026-07-29 — NOT in AWS docs catalog list) |

**Models NOT on Mantle** (commonly mistaken for Mantle models):

| ID | Actual status |
|---|---|
| `google.gemma-4-e4b` | **404 `not_found_error`** on Mantle. AWS calls the small Gemma 4 "E2B" not "E4B" despite user memory and HF model family conventions. Verified 2026-07-29. |
| Gemma 3 family (`gemma-3-4b-it`, `gemma-3-12b-it`, `gemma-3-27b-it`) | reachable on BOTH `bedrock-runtime` (Converse) AND `bedrock-mantle` (OpenAI-compatible). AWS recommends Mantle over runtime for these. |

All Mantle models support **Chat Completions** and **Responses**. Do NOT
attempt InvokeModel or Converse against Mantle — those fail because
Mantle doesn't speak that protocol.

Model IDs are dot-namespaced (`openai.gpt-5.6-sol`), unlike bare OpenAI
names. The pipe must pass through whatever model string the caller
supplies with no transformation.

## Verifying a candidate Mantle model ID (don't trust the AWS docs catalog)

**Don't trust `aws bedrock list-foundation-models` as the source of truth for Mantle availability.** The standard control-plane catalog lists models with regional availability flags and is populated for `bedrock-runtime`; Mantle-only models (`gemma-4-*`, `gpt-5.6-*`) do NOT appear there. `aws bedrock list-foundation-models --by-provider GOOGLE` returned only `gemma-3-*` across every probed region as of 2026-07-29.

**Mantle itself is the source of truth.** Probe the `/openai/v1/chat/completions` endpoint directly with a SigV4-signed POST. Working recipe (Python, no SDK dep — uses `urllib` + AWS SigV4 hand-roll). Reads creds from a specific INI profile in `~/.aws/credentials`:

```python
import urllib.request, urllib.error, json, hmac, hashlib, datetime
from urllib.parse import urlparse

# Read creds + pick a profile from ~/.aws/credentials:
ak, sk = <resolve from profile>

def sign_request(method, url, body_bytes, region, service, ak, sk):
    host = urlparse(url).netloc
    path = urlparse(url).path
    t = datetime.datetime.utcnow()
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = t.strftime('%Y%m%d')
    payload_hash = hashlib.sha256(body_bytes).hexdigest()
    canonical_headers = (f"content-type:application/json\nhost:{host}\n"
                        f"x-amz-content-sha256:{payload_hash}\n"
                        f"x-amz-date:{amz_date}\n")
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = (f"{method}\n{path}\n\n{canonical_headers}\n"
                         f"{signed_headers}\n{payload_hash}")
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
                      f"{hashlib.sha256(canonical_request.encode()).hexdigest()}")
    k_date = hmac.new(('AWS4' + sk).encode(), date_stamp.encode(), hashlib.sha256).digest()
    k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode(), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b'aws4_request', hashlib.sha256).digest()
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Authorization": f"AWS4-HMAC-SHA256 Credential={ak}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}",
        "Content-Type": "application/json", "Host": host,
        "X-Amz-Date": amz_date, "X-Amz-Content-Sha256": payload_hash,
    }

def probe_model(model_id, region="us-east-1"):
    url = f"https://bedrock-mantle.{region}.api.aws/openai/v1/chat/completions"
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with the single word 'pong'."}],
        "max_tokens": 16, "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers=sign_request("POST", url, body, region, "bedrock-mantle", ak, sk),
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        return ("OK", json.loads(resp.read().decode()))
    except urllib.error.HTTPError as e:
        return ("FAIL", f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
```

Output signals:
- `OK` + body has `choices[0].message.content` containing `"pong"` → model is reachable on Mantle in `region`.
- `HTTP 404` + `not_found_error` body claiming `model '<id>' does not exist` → model is NOT on Mantle. **Fix the ID, don't keep probing other regions** — Mantle model availability is global within a region family.
- `HTTP 403 AccessDenied` → IAM policy issue, not a model-availability problem.
- `HTTP 400` + `bedrock-mantle:InvokeModel` style error → wrong service identifier / wrong path; double-check URL and SigV4 service (`bedrock-mantle`, not `bedrock`).

Verified pattern (2026-07-29, `us-east-1`):
- `google.gemma-4-e2b` → 200 with `"pong"` (~0.3s)
- `google.gemma-4-26b-a4b` → 200 with `"pong"` (~0.3s)
- `google.gemma-4-31b` → 200 with `"pong"` (~1.7s)
- `google.gemma-4-e4b` → 404 not_found_error

**AWS MCP note**: in the Hermes AWS MCP sandbox, only `bedrock-runtime` is registered as a callable service — `bedrock` (control-plane) is not. `call_boto3(service_name="bedrock", operation_name="list_foundation_models")` returns `OperationNotFoundError`. Direct SigV4 probe (above) is the working alternative.

## Mapping to `TPipe-GenericOpenAI`

The module already has the right shape — Ktor HTTP client, OpenAI
Chat Completions serialization, no AWS-SDK dependency. Three integration
gaps, ordered smallest → largest:

### Gap 1 — Base URL override (likely already present)

`OPENAI_BASE_URL` is the documented knob for choosing the endpoint. Verify
that `GenericOpenAIEnv.kt` and the pipe config read this env var OR
expose a programmatic `setBaseUrl(...)` setter. If only env var is
read, add a programmatic setter for tests.

### Gap 2 — Bearer-token auth (likely already works)

OpenAI wire auth is `Authorization: Bearer <api_key>`. Mantle API keys
slot in unchanged. No code change needed if the existing pipe already
sets the bearer header from `OPENAI_API_KEY` (or its programmatic
equivalent). Just pass the Bedrock API key where you'd pass an OpenAI
key.

### Gap 3 — SigV4 signing (real work)

When no API key is configured and the user wants production SigV4 auth,
the pipe needs to sign each request. Two options:

1. **Mint short-lived bearer tokens via `aws-bedrock-token-generator`**
   and feed them into the existing bearer header. Keeps the wire
   protocol pure OpenAI. Requires the generator package as a
   dependency.
2. **Native SigV4 in a Ktor `Auth` plugin** using AWS credentials
   directly. No new package; more code; signs every request including
   streaming chunks.

Option 1 is the smaller change. Option 2 is the more production-grade
answer for high-throughput / long-running sessions.

## Recommended first cut

Bearer-token path only (Gaps 1 + 2). Land the test seam, write tests
that target the Mantle endpoint with a recorded response, then expand to
SigV4 only if requested.

## Anti-patterns

- **Don't** try to dispatch Mantle models through `TPipe-Bedrock`'s
  Converse code path. Mantle doesn't speak Converse.
- **Don't** rewrite model IDs. `openai.gpt-5.6-sol` must reach the wire
  unchanged — Bedrock uses these IDs to route, not just to display.
- **Don't** hard-code a single Mantle region. Mantle is regional; users
  in `us-west-2` need `https://bedrock-mantle.us-west-2.api.aws/openai/v1`.
- **Don't** assume Mantle model availability is stable. AWS adds new
  models to Mantle regularly (Claude Opus 4.8, Claude Sonnet 5, Claude
  Mythos Preview all sit on the standard Bedrock-runtime surface;
  Mantle is for the OpenAI + Gemma family right now, but the roster
  moves).

## Sources

- `https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html`
- `https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions-mantle.html`
- `https://aws.amazon.com/blogs/machine-learning/run-minimax-models-on-amazon-bedrock/`
- `https://aws.amazon.com/blogs/machine-learning/introducing-gemma-4-models-on-amazon-bedrock/`
- `https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html` (What's new section)
- `https://docs.aws.amazon.com/bedrock/latest/userguide/security-iam-awsmanpol.html` (managed policies)