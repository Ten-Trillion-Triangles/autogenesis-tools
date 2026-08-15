# Mantle reference

Mantle is the OpenAI-compatible regional Bedrock data plane at
`bedrock-mantle.{region}.api.aws`. Same model surface as
`bedrock-runtime` Converse but a different wire format. Mantle-only
models (Gemma 4 family) cannot be reached through Converse.

## Endpoint

```
https://bedrock-mantle.{region}.api.aws/openai/v1/chat/completions
https://bedrock-mantle.{region}.api.aws/openai/v1/responses
```

Verified regions (live 2026-07-29): `us-east-1`, `us-east-2`,
`us-west-2`, `eu-central-1`. The `/openai/v1/models` endpoint returns
404 — Mantle does not expose a model-listing endpoint, only
`chat/completions` and `responses`.

## Auth (SigV4)

| Path | Mechanism |
|---|---|
| Bearer `BEDROCK_MANTLE_API_KEY` | Bedrock API key (NOT IAM access key) |
| AWS SigV4 with IAM keys | `service = "bedrock-mantle"` (NOT `bedrock`) |

TPipe's `GenericOpenAIPipe.setBedrockMantle(...)` auto-detects:
1. `BEDROCK_MANTLE_API_KEY` env var → Bearer fallback
2. `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` env vars → SigV4
   with `service = "bedrock-mantle"`
3. (no further fallback)

Set the AWS env vars at runtime, never hardcode keys in source. For
programmatic / CI use, parse an INI-format credentials file and push
keys onto `BedrockMantleEnv.setAccessKeyId(...)` /
`setSecretAccessKey(...)` before invoking the pipe.

## Verified Mantle-only model IDs (Gemma 4 family)

Live-probed 2026-07-29 against
`https://bedrock-mantle.us-east-1.api.aws/openai/v1/chat/completions`
(SigV4-signed POST with prompt "Reply with the single word 'pong'."):

| Model ID | Params | Context | Reasoning | Mantle response |
|---|---|---|---|---|
| `google.gemma-4-e2b` | 5.1B total / 2.3B effective (PLE) | 128K | yes | 200 "pong" |
| `google.gemma-4-26b-a4b` | 25.2B MoE / 3.8B active | 256K | yes | 200 "pong" |
| `google.gemma-4-31b` | 30.7B dense | 256K | yes | 200 "pong" |

**Confused IDs that DO NOT EXIST (404 from Mantle, confirmed live):**

- `google.gemma-4-e4b` — Mantle returns
  `{"code":"not_found_error","message":"The model 'google.gemma-4-e4b' does not exist"}`.
  The small Gemma 4 variant is named **E2B** (PLE), not E4B.
- `google.gemma-4-4b` — no matching foundation-model entry.

Standard Bedrock `aws bedrock list-foundation-models --by-provider GOOGLE`
does NOT list the Mantle-only subset. The catalog only shows Gemma 3
(12B/4B/27B, all with `-it` suffix). Gemma 4 is Mantle-only — don't
trust `list_foundation_models` to detect them.

## Mantle short-form reasoning event names

When parsing SSE streams from Mantle Responses API, accept BOTH:

- `response.reasoning_text.delta` (OpenAI format)
- `response.reasoning.delta` (Mantle short form)

Either name may be emitted; the parser must accept both. (OpenAI's own
Responses API uses the long form; Mantle uses the short form.)

## Responses API minimum

Mantle's Responses API requires `max_output_tokens >= 16` to avoid a
hard error. Use `MAX_TOKENS = 32` as a safe default for both Chat
Completions and Responses API surfaces.

## Mantle-vs-Converse detection

Before invoking any Bedrock model, check whether the model ID is in
the Mantle-only subset (Gemma 4 today). If it is:

- DO NOT use `bedrock-runtime` Converse API
- DO NOT use `aws bedrock-runtime converse --model-id <id>`
- USE `bedrock-mantle` OpenAI-compatible endpoint via
  `GenericOpenAIPipe` or direct HTTP to `/openai/v1/chat/completions`

Detection signals:
- `aws bedrock list-foundation-models` returns the model with NO
  `outputModalities: TEXT` (Mantle-only models are absent from the
  catalog entirely)
- model ID starts with a Mantle-family prefix that's absent from the
  catalog

## Verifying a model ID is reachable (quick probe)

```python
import boto3, requests, json
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

def probe(model_id, region="us-east-1"):
    creds = boto3.Session().get_credentials()
    req = AWSRequest(
        method="POST",
        url=f"https://bedrock-mantle.{region}.api.aws/openai/v1/chat/completions",
        data=json.dumps({"model": model_id, "messages": [{"role": "user", "content": "Reply with the single word 'pong'."}]}),
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(creds, "bedrock-mantle", region).add_auth(req)
    return requests.request(
        method=req.method, url=req.url, headers=dict(req.headers), data=req.body,
        timeout=30,
    )
```

A 200 with `pong` in the response confirms reachability. A 404 with
`not_found_error` means the model ID does not exist on Mantle.

## Live-test gating pattern (JUnit 5)

```kotlin
@EnabledIfEnvironmentVariable(named = "BEDROCK_MANTLE_LIVE_TEST", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class BedrockMantleLiveTest
{
    private fun installCredentials() {
        assumeTrue(
            credentialsFile.exists(),
            "Skipping: ${credentialsFile.absolutePath} missing"
        )
        // parse INI file, push keys to BedrockMantleEnv
    }

    @Test
    fun testMantleGemmaE2B() = runBlocking<Unit> {
        installCredentials()
        try {
            val pipe = GenericOpenAIPipe()
                .setBedrockMantle("us-east-1", "google.gemma-4-e2b")
                .setMaxTokens(32)
                .setTemperature(0.0)
                .init()
            val response = pipe.execute("Reply with the single word 'pong'.")
            assertTrue(response.contains("pong", ignoreCase = true))
        } finally {
            BedrockMantleEnv.clearAccessKeyId()
            BedrockMantleEnv.clearSecretAccessKey()
        }
    }
}
```

The two-stage gate (class-level `@EnabledIfEnvironmentVariable` plus
per-method `assumeTrue`) produces `tests=N skipped=N failures=0` on
JUnit XML when the gate is off — the correct "skip, not fail" behavior
for optional live integration tests.

## Quick way to know a Mantle model ID exists

1. Look it up in this reference's "Verified Mantle-only model IDs" table
2. If not in the table, run the verification probe above
3. If still 404, the ID doesn't exist — pick a different one from the
   table or check AWS docs at the Gemma 4 family page