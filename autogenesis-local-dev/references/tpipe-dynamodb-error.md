# TPipe DynamoDB Error — Root Cause: Stray DynamoDB Local Container (2026-05-10)

## Key Finding

**TPipe is embedded in the Java game server JVM — it is NOT externally callable.** The Python controller's `tpipe_client` (port 8000) was an ALIEN broken mechanism that was NEVER connected to the actual TPipe. When Python called `tpipe_client.generate_action()`, it hit `http://127.0.0.1:8000/` — which was whatever was on port 8000 (DynamoDB Local in this session), not any TPipe service.

**The game server's TPipe** calls AWS Bedrock (Nova/Qwen) internally via the TPipe-Bedrock Kotlin library, completely inside the JVM. It does NOT use DynamoDB. The "DynamoDB 400 error" was purely from the stray DynamoDB Local container intercepting the Python controller's external requests.

## Symptom

Python controller logs show TPipe returning 400 on every turn:
```
WARNING | TPipe returned status 400: {"__type":"com.amazonaws.dynamodb.v20120810#MissingAuthenticationToken",
  "Message":"Request must contain either a valid (registered) AWS access key ID or X.509 certificate."}
WARNING | TPipe action generation failed, using fallback
```

## Root Cause

A leftover **Amazon DynamoDB Local Docker container** running on port 8000:
```
$ docker ps --format "{{.ID}} {{.Image}} {{.Ports}}"
9afd9cb57d49  amazon/dynamodb-local:latest  0.0.0.0:8000->8000/tcp  Up 44 hours
```

Started May 8 — unrelated to Autogenesis (likely another project). The container intercepts all traffic to `127.0.0.1:8000` and returns DynamoDB JSON errors.

## Diagnosis

```bash
# Confirm what's on port 8000
curl -s --max-time 3 http://127.0.0.1:8000/
# Returns DynamoDB JSON error → stray container

# Check for Docker containers on 8000
docker ps --format "{{.ID}} {{.Image}} {{.Ports}}" | grep 8000

# Check process using port 8000
fuser 8000/tcp 2>/dev/null
```

## Fix

Remove the stray DynamoDB Local container:

```bash
docker stop 9afd9cb57d49 && docker rm 9afd9cb57d49
```

After removal, the Python controller's `tpipe_client` will get "connection refused" (no service on 8000) and fall back to procedural text — same outcome, just cleaner.

## Port Pre-Flight Check

Before starting Autogenesis services, always verify no conflicting services:

```bash
ss -tlnp | grep -E "7070|7075|8000|8080|9080"
docker ps --format "{{.ID}} {{.Image}} {{.Ports}}" | grep -E "7070|7075|8000|8080|9080"
```

Common conflicts:
- **8000**: DynamoDB Local Docker (unrelated to Autogenesis)
- **8080**: Other webpack/node dev servers
- **7070/9080**: Previous Autogenesis runs not cleanly shut down