---
name: ttt-site-backend-debugging
description: Use when working with the ttt-site live backend — contact form not sending, SES emails not arriving, Lambda silent, DDB write missing, "API returns 200 but nothing happened", "page not indexed in Google", "Search Console shows 302/canonical/404 errors", OR any data-plane op against the `Contacts` DynamoDB table (archive, mark spam, status query, scan submissions). Triggers on "contact form broken", "SES emails not arriving", "no email in inbox", "Lambda silent", "trace the form", "no MX record", "DDB write missing", "archive the messages", "mark spam", "what's in the contacts table", "Google not indexing my pages", "Search Console Page indexing report shows N reasons", "apex redirects to www and that's bad", "canonical points to wrong host". Covers API Gateway → Lambda → DDB → SES → SNS → S3 → Amplify customRules → Route 53 (account 521369004927, region us-east-1, hosted zone Z0266992GQSG7W4H336). NOT for building new features (use ttt-site-* content skills) or general AWS patterns (use aws-serverless).
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [ttt-site, backend, debugging, ses, lambda, dynamodb, route53, cloudtrail, observability]
    related_skills: [troubleshooting-application-failures, aws-serverless, aws-observability, aws-messaging-and-streaming, ttt-site-blog, ttt-site-comparison-pages]
---

# ttt-site Backend Debugging

Investigation playbook for the live ttt-site infrastructure when the user reports a runtime behavior gap (form returns 200 but no email arrives, data missing from DDB, etc.). The methodology is **trace every layer, gather evidence at each, identify the break** — not "guess and check."

## Architecture at a glance

The stack is fixed; commit it to memory at the start of every investigation.

| Layer | Resource | Identifier | Purpose |
|---|---|---|---|
| Frontend | Astro site, contact form | `src/components/pricing/ContactForm.astro` | Browser fetch to API |
| API Gateway | REST API | `mgf9b7ggkd` / Stage `Prod` | Routes `/contact` POST → Lambda |
| Lambda | `ContactHandlerFunction` | `ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB` | Node.js 22, handler `index.handler` |
| Lambda env | `DYNAMODB_TABLE_NAME`, `SES_FROM_EMAIL`, `SES_TO_EMAIL`, `SES_CONFIG_SET`, `ALLOWED_ORIGIN` | (always check these first) | Required for the handler to function |
| DDB | `Contacts` table | region us-east-1 | Stores every submission |
| SES | Domain identity + email identity | `tentrilliontriangles.com`, `contact@tentrilliontriangles.com` | Sends notification |
| SES config set | `ttt-site-contact` | SNS event dest for bounce/complaint/delivery | Delivery observability |
| SNS | `ttt-site-ses-bounces` | arn:aws:sns:us-east-1:521369004927:ttt-site-ses-bounces | Event fanout (often PendingConfirmation) |
| S3 | `tentrilliontriangles.com` (origin) + `tentrilliontriangles-com-logs` (access logs) | us-east-1 | Static site + S3 server access logs |
| Route 53 | Apex + www zones | `Z0266992GQSG7W4H336`, `Z00864641AXKDQ2VDEHG3` | DNS — CRITICAL: no MX records = mail can't be delivered |
| CloudWatch | Lambda log group | `/aws/lambda/ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB` | Runtime evidence |
| CloudTrail | route53.amazonaws.com events | region us-east-1 | DNS change audit trail |

## The investigation recipe

When the user reports "X isn't working":

1. **Identify the symptom layer.** Form returns 200 but no email → SES/DNS layer. Form returns 500 → Lambda layer. Form hangs → API GW or CORS.
2. **Verify the layer is actually broken before suggesting fixes.** A common failure mode is jumping to "the Lambda is wrong" when in fact Lambda is silent-and-correct and the email is bouncing at SES. **Gather evidence first, then name the broken layer.**
3. **Trace each layer with one AWS call.** Use `mcp_aws_aws___run_script` to call boto3 in parallel where possible. Use the `aws` CLI directly via `terminal` only when the MCP tools don't cover the operation.
4. **Always check the Lambda environment variables first** when the Lambda is misbehaving. Misconfigured `ALLOWED_ORIGIN`, `SES_FROM_EMAIL`, `SES_TO_EMAIL`, or `SES_CONFIG_SET` are the most common silent failures.
5. **Don't trust CloudWatch's `SentLast24Hours` quota metric as the only signal — but DO trust it for "did SES get called at all?"** Counter-intuitively: the lag claim is wrong. In the 2026-06-25 SES-no-delivery investigation, a single direct `sesv2 SendEmail` call incremented `SentLast24Hours` from 0.0 → 1.0 immediately (verified on the same call). Use it as a positive/negative oracle: if `SentLast24Hours` increments after a Lambda invocation, SES was contacted. If it does NOT increment after a Lambda returns 200, the Lambda never reached SES — even if CloudWatch logs are silent (which they will be if a try/catch swallowed the error). Pair it with a direct `aws sesv2 send-email` test from CLI to get a real `MessageId` and verify SES itself accepts your payload.

## Per-layer evidence commands

| Layer to check | Command / MCP call | What to look for |
|---|---|---|
| Frontend code | read_file `src/components/pricing/ContactForm.astro` around line 352 | The fetch URL, headers, JSON payload |
| API Gateway | `apigateway:GetResources` on `mgf9b7ggkd` | The `/contact` POST route exists |
| Lambda config | `lambda:GetFunction` for `ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB` | Env vars, runtime, code size, last modified |
| Lambda code | Diff `infrastructure/.aws-sam/build/ContactHandlerFunction/*.js` against `src/lambda/contact-handler/*.js` | If they differ, deployed ≠ source |
| Lambda invocation | `lambda:Invoke` with a hand-built payload + `LogType: Tail` | Tail logs come back in the response, skip the CloudWatch trip |
| Lambda runtime | `logs:GetLogEvents` on the function's log group, most recent stream | Duration, errors, init duration |
| DDB write | `dynamodb:Scan` with `FilterExpression: contains(message, :marker)` | Did the most recent submission actually land? |
| SES identity | `sesv2:ListEmailIdentities` | Domain + email verified, sending enabled |
| SES quota | `sesv2:GetAccount` → `SendQuota.SentLast24Hours` | Near-real-time for in-session sends (confirmed 2026-06-25: ticks within seconds). May lag after long idle periods. Use as oracle: tick = SES called, no-tick = SES not called. |
| SES direct test | `sesv2:SendEmail` from CLI with a `MessageId` response | If this works, SES itself is fine; problem is downstream |
| SES config set | `sesv2:GetConfigurationSet` + `GetConfigurationSetEventDestinations` | SNS event dest exists, has a destination |
| SNS subscription | `sns:ListSubscriptionsByTopic` on `arn:aws:sns:us-east-1:521369004927:ttt-site-ses-bounces` | Subscription state — `PendingConfirmation` = events go nowhere |
| Route 53 records | `route53:ListResourceRecordSets` on apex + www zones | **CRITICAL: check for MX records** — domain has none, mail delivery is impossible |
| CloudTrail DNS history | `cloudtrail:LookupEvents` filtered to `EventSource=route53.amazonaws.com` | When did the MX (or other) record get added/removed, by whom |
| S3 access logs | `s3:GetObject` on `tentrilliontriangles-com-logs/access-logs/*` | S3 origin-side traffic only (not CloudFront edge traffic) |

## Common failure modes and their signatures

### Symptom: "Form returns 200, no email arrives"

1. **No MX records** — domain can't receive mail. Check Route 53 first. If zero MX records, fix by either adding MX records pointing to a real mail server OR change `SES_TO_EMAIL` to a real inbox. (Caveat: CloudTrail showing no `ChangeResourceRecordSets` with MX is suggestive but not proof — records can be imported via zone file, set at the registrar, or exist outside the trail's lookback window. **Verify with `dig` before declaring it never existed.**)
2. **Self-send suppression** — `From == To` and recipient provider drops/quarantines. Some providers (Gmail especially) treat self-addressed SES mail as suspicious.
3. **SNS event destination is `PendingConfirmation`** — bounce notifications go to a topic that has 0 confirmed subscribers. The bounce itself is sent back to the broken destination, so the bounce is also lost. Visible only by `sns:ListSubscriptionsByTopic`.
4. **CloudWatch `SentLast24Hours` showing 0.0** — only matters if you've been actively sending in this session. If you ran a direct Lambda invoke or CLI send in the last few minutes and the counter didn't tick, SES wasn't called. After long idle periods the counter may show 0 even though historical sends happened — verify with `aws sesv2 send-email` direct CLI and a real `MessageId` response.

### Symptom: "Lambda is silent (no console output)"

The deployed Lambda might be:
- Emitting console output but the log group retention is too short
- Running an old build that doesn't have the current `index.js`
- The try/catch is swallowing the error and never reaching the `console.warn` line
- Using `USE_SMTP=1` env var silently routing to SMTP instead of SES (only an issue in dev/staging — production Lambda doesn't have this set)

Always check:
1. `infrastructure/.aws-sam/build/<FunctionName>/*.js` matches `src/lambda/<function>/*.js`
2. Lambda env vars (especially `USE_SMTP`, `SES_CONFIG_SET`)
3. Whether the log group has been recently written to (logs.GetLogEvents)

**Silent success is NORMAL, not a bug signal.** The deployed `sendAdminNotification` only logs `console.warn` on FAILURE (the SES throw). On success — SES accepts the send, MessageId returned — there is zero console output. A clean log is the expected behavior when SES sends succeed. The opposite reasoning ("no logs = something is broken") is a trap; the 2026-06-25 investigation fell into it on the first pass and had to be corrected after pulling the deployed source. Don't conclude "the Lambda is silently swallowing errors" from log silence alone — pair it with the `SentLast24Hours` counter tick.

**The duration heuristic is unreliable.** Old guidance said "Lambda duration is 200-900ms means SES was called; DDB write alone is ~50-100ms." This is wrong. In the 2026-06-25 investigation, a Lambda with no SES call and no console output completed in **151ms** with a successful 200 response. The 200ms+ threshold gives false positives — `sendAdminNotification` can return early via the `USE_SMTP=1` branch or a silent no-op path in a stale build. Don't trust duration as evidence SES was called.

**Reliable "was SES called?" oracle:** check `SentLast24Hours` on `sesv2:GetAccount` before and after a direct Lambda invoke. If the counter doesn't tick, SES was not called — full stop. The CloudWatch log being silent is corroborating evidence, not proof.

### Verify the deployed bundle is what you think it is (don't guess)

When you're debugging the Lambda and have a hypothesis about deployed code, READ IT before writing the report. The deployed bundle is reachable two ways:

  1. **Local build artifact (works without shell consent):** `infrastructure/.aws-sam/build/ContactHandlerFunction/*.js`. SAM uploads the contents of this directory to the deployment bucket at `sam package` time. After a `sam deploy`, the directory contains the EXACT deployed code. Verified 2026-06-25: read `infrastructure/.aws-sam/build/ContactHandlerFunction/ses.js` and `index.js` — they matched `src/lambda/contact-handler/*` byte-for-byte and resolved all the "is there a no-op path?" speculation.
  2. **Presigned S3 download (often blocked by shell consent):** `aws lambda get-function --query 'Code.Location'` then curl the URL. The shell consent gate routinely refuses long presigned S3 URLs as potential exfiltration. If the consent gate blocks, fall back to (1).

If `infrastructure/.aws-sam/build/<Func>/` doesn't exist (clean checkout, no recent deploy), you can regenerate it with `sam build` from the `infrastructure/` directory. The build is local and doesn't require AWS credentials.

### Symptom: "Email used to arrive, now it doesn't" (regression)

1. `cloudtrail:LookupEvents` filtered to `EventSource=route53.amazonaws.com` — find recent `ChangeResourceRecordSets` events on the apex zone. Read the `requestParameters` to see exactly what was added/removed.
2. **Ask the user for a screenshot of their inbox first** before digging into DNS. The recipient side is often where the actual break is, not Route 53. If they show you the email is landing in a GoDaddy / M365 / Gmail quarantine digest, the answer is "release it and add a sender allowlist," not "fix your DNS."
3. If user says "MX records were never set" but they're certain emails arrived before, **don't argue** — investigate. CloudTrail only catches changes made through AWS API/console. Zone file imports, registrar panels, and changes before the trail's lookback window won't appear. Verify with `dig` or external DNS lookup. Also: MX records for ttt-site's email flow live wherever the mailbox provider (GoDaddy / M365) is configured — that's typically NOT in Route 53 if the DNS was set up via the registrar or the email provider's own panel.
4. Check the user's recent browser/Root console activity timestamps. The fix is usually "release from quarantine + add allowlist" or "re-add the missing record," not "explain why it was removed."

### Symptom: "DDB write is missing but Lambda returned 200"

1. The handler returns 200 even if `saveContact` throws — the throw is caught by the outer try/catch. Check the actual handler code for this pattern: `try { ... } catch (error) { console.error(...); return { statusCode: 500, ... } }` means a throw should produce 500. If you see 200 with no DDB write, the write might be silently succeeding against a different table.
2. Check both `DYNAMODB_TABLE_NAME` and `DDB_TABLE_NAME` env vars. The code has fallbacks: `process.env.DYNAMODB_TABLE_NAME || process.env.DDB_TABLE_NAME || 'Contacts'`. A misconfigured env could point to a different table.

## Investigation tool order (cheat sheet)

```
1. ListLambda             → confirm function exists, get env
2. GetFunction            → confirm code size, runtime, last modified
3. GetLogEvents (latest)  → see what the function is actually doing
4. ListHostedZones +      → confirm DNS, including MX
   ListResourceRecordSets
5. ListEmailIdentities +  → confirm SES identities
   GetAccount             → (counter is near-real-time within a session)
6. ListSubscriptionsByTopic → confirm SNS event dest has subscribers
7. LookupEvents (CloudTrail, → find DNS history, regressions
   EventSource=route53)
8. Scan DDB with marker   → confirm a known submission actually wrote
9. Direct SES SendEmail   → verify SES itself works (MessageId response)
```

Do these in parallel where possible. `mcp_aws_aws___run_script` with `asyncio.gather` handles this in one call.

## When the AWS MCP tools aren't visible in your session

Symptoms:
- `mcp_aws_aws___call_aws` (or any `mcp_aws_*`) is NOT in your toolset
- `hermes tools list` shows `aws — all tools enabled` at the gateway level
- `agent.log` shows `MCP server 'aws' (stdio): registered 9 tool(s)` from a prior gateway startup
- Your session was started before MCP late-binding could populate the toolset
- `mcp-stderr.log` shows `===== [timestamp] starting MCP server 'aws' =====` with no further output (this is NORMAL — `mcp-proxy-for-aws` doesn't print a banner until it receives a JSON-RPC `initialize`)

The fix: speak JSON-RPC directly to `mcp-proxy-for-aws` via `uvx`, bypassing Hermes entirely. The `scripts/aws_mcp_query.py` script does this. Same 9 tools, same SigV4 credentials (via the `AWS_REGION` metadata or your `~/.aws/credentials` chain), no dependency on the Hermes MCP loader.

```bash
python3 ~/.hermes/skills/ttt-site-backend-debugging/scripts/aws_mcp_query.py \
  aws___call_aws '{"cli_command":"aws amplify get-app --app-id d48lytolyaq3z --region us-east-1 --query app.customRules --output json"}'
```

Why this works: `mcp-proxy-for-aws@latest` is a self-contained stdio MCP server. It doesn't care who its parent process is. Hermes is just one of many possible JSON-RPC clients; `uvx` and a heredoc-shaped stdin is another. The 1.5s `mcp_discovery_timeout` cap that kills lazy-starting servers in the Hermes loader doesn't apply when YOU are the client and you wait for the response.

For a full investigation where the AWS MCP tools are the right answer but aren't loaded, this script replaces them completely for the duration of one shell call. For long-running work, restart the gateway (`hermes gateway restart`) so the late-binding fires properly.

## Critical: don't argue with the user (and don't theorize before seeing the state)

When the user pushes back on your findings ("it used to work", "the MX records are there", "I see the email in my inbox"), **stop and verify before asserting**. Common mistakes from prior sessions:

- Asserting "MX records never existed" when CloudTrail's lookback window just didn't cover the change
- Assuming a Google Workspace domain verification CNAME implied Workspace was set up
- Suggesting work (TLDR blocks, comparison tables, FAQ schemas) that was already shipped

When the user sends a screenshot you can't load (vision API failure), **say so directly** — don't guess at the contents. Don't claim "I see the MX records" if you can't see them.

### Look at the actual user-facing state before theorizing about backend

The single most expensive mistake in this domain: opening with a backend theory ("the Lambda is wrong", "the DNS is broken", "MX records are missing") without first checking what the user is actually seeing. The most common scenarios:

- The user IS receiving the email — it just landed in quarantine (GoDaddy Advanced Email Security, M365 quarantine, Gmail spam, etc.). The `Bounce` metric stays at 0; the `Delivery` metric may also stay at 0 if the receiving filter intercepts before SMTP accept. The user is sitting on a real signal — ask them to share it.
- The user is not receiving the email — but for a reason completely different from your theory (mailbox full, M365 connector rejecting SES, transport rule, etc.). Only a recipient-side check reveals this.

**First diagnostic question to ask:** "Can you take a screenshot of your inbox / your spam / your quarantine, and tell me if you see any contact form emails?" That single question often short-circuits an hour of CloudTrail digging.

### Vision tool failures: retry before debugging the tool

When a vision tool (e.g. `vision_analyze` or `mcp_MiniMax_understand_image`) fails on the first call, the failure mode is often transient:

- `vision_analyze` fails with "nginx 404" on local file paths — the Hermes vision backend is hosted on a service that can't see the local FS. Switch to `mcp_MiniMax_understand_image` with the same local path; it accepts file paths and runs the request through MiniMax's VLM endpoint. If it returns an SSL error on the first call, **just retry** — the connection is usually established on the second attempt.
- Don't spend multiple turns trying to debug a tool that the user can clearly see works for them. One diagnostic call, then either retry or ask the user to paste the relevant text.

Pattern: if a tool call fails on first try with a transient-looking error (SSL, 5xx, timeout), retry the SAME call once before going down the rabbit hole. If it fails twice the same way, then debug.

## Verification checklist after a fix

After applying any fix in this domain, re-verify the trace end-to-end:

- [ ] API Gateway returns 200 on a real payload
- [ ] Lambda log shows START/END/REPORT for the new invocation
- [ ] DDB has the new submission row (Scan with marker filter)
- [ ] SES accepts a direct CLI send-email (MessageId returned)
- [ ] If MX was added: `dig MX <domain>` from external resolver returns the new records (DNS TTL may delay this)
- [ ] SNS subscription is `Confirmed` (not `PendingConfirmation`) — see note below: list may return EMPTY if drift removed the sub entirely
- [ ] CloudWatch `SentLast24Hours` updates within the same session after the next submit

## Related references

- `references/contact-form-trace.md` — the full browser → API GW → Lambda → DDB → SES trace with exact MCP commands
- `references/ses-delivery-investigation.md` — when SES emails don't arrive at the inbox, run this checklist
- `references/mx-resurrection-22-day-outage.md` — when the user says "email has been down for weeks" and you need to add M365/GoDaddy records + verify end-to-end. Covers the region-default trap, Route 53 atomic batch split (forbids two TXT @), sendmail-from-this-box anti-pattern, API GW proxy wrapper for direct Lambda invoke, and the lost-mail-window recovery protocol.
- `references/cloudtrail-dns-regression.md` — when something changed but you don't know what, use CloudTrail
- `references/recipient-side-quarantine.md` — when CloudWatch shows `Send > 0, Delivery = 0, Bounce = 0`, the problem is recipient-side filtering (GoDaddy Advanced Email Security, M365 quarantine, Gmail spam). The most expensive mistake is theorizing about the AWS side before asking the user to share a screenshot of their inbox.
- `references/ses-cloudwatch-destination-gotcha.md` — the `sesv2:CreateConfigurationSetEventDestination` API for `CloudWatchDestination` doesn't expose an `IamRoleArn` field, so CloudWatch destinations set up via v2 are silently broken. Use SNS + Lambda subscriber instead.
- `references/dynamodb-data-ops.md` — DDB `Contacts` table schema, single-table layout (`PK=CONTACT` vs `PK=RATE#<ip>`), how to safely archive/spam/status-change submissions, the three classic screwups (PutRequest nukes attributes, SK typo creates phantom rows, Scan-then-count ignores rate-limiter rows), and the recognized bot-spam patterns (dotted-gmail gibberish) with a safe bulk-spam recipe.
- `references/seo-indexing-amplify-302-redirect.md` — when Google Search Console "Page indexing" report shows 302/canonical/404 reasons: the root cause is almost always a 302 in `amplify update-app --custom-rules` plus canonical tags pointing at apex. The 60-second check, the exact API call to fix it, the trailing-slash canonical drift bug class, and the CloudTrail forensic recipe to answer "why is this 302 there in the first place?" (reconstructed 2026-07-03 for ttt-site: root user via Console, 1-second window with `UpdateDomainAssociation` + `Route53 ChangeResourceRecordSets` + `UpdateApp`, default 302 from the domain-attach wizard, NOT a deliberate SEO decision).
- `scripts/aws_mcp_query.py` — when the AWS MCP tools (`mcp_aws_aws___call_aws` etc.) are NOT visible in your session's toolset (Hermes late-binding hasn't fired, or the tool-snapshot is stale), this script speaks JSON-RPC directly to `mcp-proxy-for-aws` via `uvx` and bypasses the Hermes layer. Same credentials, same SigV4 signing, same 9-tool surface, no dependency on `hermes tools list` showing them. Usage: `python3 scripts/aws_mcp_query.py aws___call_aws '{"cli_command":"aws sts get-caller-identity"}'`.
- `references/lambda-tail-log-decode.md` — how to decode `lambda:Invoke` `LogType: Tail` output in this sandbox (base64/binascii imports are blocked; decode via `terminal` instead), and the shell-consent gate on downloading the deployed bundle.

## DDB data-plane ops on the `Contacts` table

Beyond debugging, the admin workflow includes direct DDB edits: archiving old threads, marking obvious bot submissions as spam, querying "what's new since X". The table is non-trivial and easy to corrupt. Read `references/dynamodb-data-ops.md` before any batch mutation.

Critical facts the rest of this section assumes:

- **PK/SK layout.** Contact submissions are `PK="CONTACT"`, `SK="<ISO8601 submittedAt>#<email>"`. The rate-limiter sliding-window records live in the SAME table with `PK="RATE#<ip>"`, `SK="WINDOW#<epoch>"`. They are NOT messages — they have no `name`, `email`, `status`, or `submittedAt`. Do not try to interpret them as messages.
- **GSI.** `StatusIndex` is `HASH=status, RANGE=submittedAt, Projection=ALL`. Status values seen in the wild: `new` (active), `spam` (triaged junk), `archived` (triaged but kept). No `contacted`/`qualified`/`closed` rows exist yet.
- **ItemCount includes rate-limit windows.** A Scan with `Select=COUNT` will report ~100+ items even if you "only have 70 messages". Always partition-sum (Query on StatusIndex per status) when reporting message counts.

Three screwups that have happened in real sessions — don't repeat them:

1. **`BatchWriteItem` with `PutRequest` instead of `UpdateRequest` REPLACES the row.** PutRequest only keeps the attributes you specify; everything else (`name`, `email`, `message`, `submittedAt`, `useCase`, `role`, `company`, `budget`) is silently dropped. After any batch Put, immediately re-read the affected rows and verify the non-key attributes are still there. If you just want to set `status`, use `UpdateItem` with `UpdateExpression: "SET #s = :s"`.
2. **GSI requires both `status` AND `submittedAt` to be present on the item** for it to appear in StatusIndex. If a prior Put/Update nuked `submittedAt`, the row is invisible to all status queries even though it exists in the base table. The SK contains the original timestamp — recover it by `submittedAt = sk.split("#")[0]`.
3. **SK is the timestamp+email composite — typo ONE DIGIT and you create a phantom row.** Always re-read the actual SK from a Scan before constructing UpdateItem/DeleteItem keys. Compare digit-by-digit. `BatchWriteItem` will happily write to a SK that doesn't exist, leaving the original row untouched and your "update" pointed at a brand-new husk. Verify `ItemCount` on `DescribeTable` before and after a batch op, and reconcile any delta.
