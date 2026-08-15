# Decoding Lambda `LogType: Tail` output

When you `lambda:Invoke` with `LogType: Tail`, the response includes a base64-encoded string in the `LogResult` field. The string is the captured log output (START/END/REPORT plus any console.log/warn/error) from the single invocation.

## Why this matters

If the Lambda is silent (no console output), the tail still contains the START/END/REPORT lines that confirm:
- The function ran (START RequestId)
- It returned cleanly (END RequestId)  
- The duration was X ms (REPORT line)

These three lines alone are often enough to rule out a 5xx error or a hang. You don't need a second CloudWatch round-trip — the tail comes back in the Invoke response.

## Decoding

The decoded payload is usually 300-500 bytes and base64-encoded.

### Via `execute_code` (sandbox blocks `import base64` and `import binascii`)

The MCP `execute_code` sandbox blocks both `base64` and `binascii` imports with: "This module is blocked for security reasons."

So you cannot decode in the sandbox. Two workarounds:

### Workaround 1: Print the b64 verbatim, decode in `terminal`

```python
# Inside execute_code
invoke_resp = await call_boto3(service_name='lambda', operation_name='Invoke', params={...})
print(invoke_resp.get('LogResult'))   # prints the base64 string to stdout
```

Then in a `terminal` call:

```bash
printf '<paste-b64-here>' | base64 -d
```

This works because `terminal` runs in a separate shell with full stdlib.

### Workaround 2: Print structured output and decode in agent context

The Hermes runtime's tool output goes through to the agent's context. If your agent model can decode base64 in-context (most can), the string in the tool result is sufficient — no terminal round-trip needed.

### Workaround 3: Use `terminal` for the whole Invoke

```bash
aws lambda invoke \
  --function-name ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB \
  --payload file:///tmp/payload.json \
  --log-type Tail \
  --query 'LogResult' \
  --output text \
  /tmp/invoke-out.json | base64 -d
```

## Pitfalls

- **Don't re-edit the base64 by hand.** It looks like random ASCII. The session where this technique was discovered lost a decode pass because the agent manually typed the b64 back into a terminal echo and it was the wrong string. Always copy-paste from the actual tool output.
- **The sandbox will reject `import base64` AND `import binascii`.** Use the terminal workaround.
- **`LogResult` is a STRING, not bytes.** When passing to a decoder, treat it as a UTF-8 string.
- **`LogType: None` returns no log output.** Always pass `Tail` explicitly.

## When the Lambda's deployed bundle itself is the suspect

If you suspect the deployed code is the problem (e.g., silent SES calls, no console output, quota counter doesn't tick), and you've exhausted log analysis, the next step is reading the deployed bundle directly:

```bash
# 1. Get the presigned code URL
aws lambda get-function --function-name <name> --query 'Code.Location' --output text

# 2. Download + unzip
curl -sSL '<presigned-url>' -o /tmp/func.zip
unzip -l /tmp/func.zip
unzip -p /tmp/func.zip index.js | less
```

**The shell consent gate often blocks step 2** (long presigned S3 URLs are flagged as potential exfiltration). In that case, indirect evidence is usually sufficient:
- Quota counter doesn't tick + log is silent = deployed code has a no-op path. The fix is `sam build && sam deploy`.
- Skip the bundle inspection and go straight to the redeploy.

If you do need the bundle and the consent gate blocks, the user can pull it from the AWS Console (Lambda → Code tab) in 30 seconds.