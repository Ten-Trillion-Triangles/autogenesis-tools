# MX Resurrection + 22-Day Outage Recovery (Incident 2026-06-28)

The complete playbook for the scenario where the user reports: "**our email has been down since [date]**" — meaning `tentrilliontriangles.com` lost its MX records for weeks, then you fix it, then you have to prove that mail actually flows again at every layer.

This reference is **additive** to the rest of the skill — it adds three things that the other files only touch in passing:

1. **The `~/.aws/config` default-region trap** — querying via the terminal without `--region` returns sandbox/prod-state answers from a *different* region than your resources actually live in.
2. **The "sendmail from this box as a fallback" anti-pattern** — same-domain-from-serverless-self-send always gets SPF-fail → recipient quarantine, even when MX is fine.
3. **The atomic Route 53 change-batch** for adding an entire M365/GoDaddy email setup (MX + autodiscover CNAME + email CNAME + verification TXT + merged SPF) in 4 separate UPSERT/CREATE change batches because Route 53 forbids two TXT record-sets on the same name+type.

## When to load this

The user says one of:
- "Our email has been down since [date]"
- "We're not receiving mail" + "the inbox hasn't received anything since June"
- "Add these records to our hosted zone" + image of a GoDaddy/MS365 DNS setup page
- "Check if mail is flowing" after a records-set change

## The 4-layer mental model

When email "doesn't work," always decompose into these four layers. A fix that doesn't identify the broken layer doesn't stick.

| Layer | What it does | How to test it |
|---|---|---|
| **DNS** (Route 53 hosted zone) | Tells the world where to send mail TO the domain | `dig MX tentrilliontriangles.com`, `dig TXT tentrilliontriangles.com`, `dig CNAME autodiscover.tentrilliontriangles.com` |
| **Auth** (SPF / DKIM / DMARC) | Tells recipient servers the message is legit | `dig TXT` for SPF, `dig CNAME _domainkey.*`, `dig TXT _dmarc` |
| **SES** (sending identity + production access + per-region quotas) | Lets you SEND mail from the domain | `aws sesv2 list-email-identities`, `aws sesv2 get-account` |
| **Lambda / handler** (ContactHandler for the form path) | Actually invokes SES + writes DDB | Direct `aws lambda invoke` with API GW proxy wrapper |

A failure in any ONE layer blocks mail. The common mistake is fixing layer 1 and assuming layers 2-4 are fine. They aren't.

## Step 0 — Region default trap

**Before any AWS CLI call against ttt-site resources, set `--region us-east-1` explicitly.** The local `~/.aws/config` may default to a different region (e.g. `us-east-2`). Querying the wrong region returns garbage answers that look right:

```bash
# This is wrong if ~/.aws/config defaults to us-east-2:
aws sesv2 get-account
# Returns sandbox numbers (Max24HourSend: 200) because the us-east-2 account is sandbox.
# ttt-site prod SES lives in us-east-1.

# Always pass --region:
aws sesv2 get-account --region us-east-1
# Returns Max24HourSend: 50000, ProductionAccessEnabled: true, healthy.
```

**Heuristic:** if the AWS CLI returns a sandbox readout (`Max24HourSend: 200`, `MaxSendRate: 1`, `ProductionAccessEnabled: false`) but you know production access was approved, **you are querying the wrong region.** Always pin `--region us-east-1` for ttt-site ops.

The same trap exists for the AWS MCP server. Verify with `mcp_aws_aws___list_regions` and use a region parameter on every subsequent call. The MCP server's `run_script` sandbox accepts `region_name=...` on each `call_boto3`.

## Step 1 — Read the screenshot the user gave you (don't guess at it)

When the user attaches a GoDaddy/MS365 DNS setup page screenshot, the visible content is **a complete inventory of the records they want on the zone**. Read it like a contract:

| Section | What to extract |
|---|---|
| TXT Record | `Name` (usually `@`) + `TXT Value` (verification token + SPF) |
| CNAME Record | `Host` (usually `autodiscover` + `email`) + `Points to` |
| MX Record | `Host` + `Priority` + `Target` (usually 10 → primary, 20 → secondary) |
| Bottom notes | "If you have existing MX records, you must remove them" + "select I'm Done" |

Don't paraphrase, don't reorder. Extract the exact strings; they're literal DNS values that go verbatim into `ResourceRecordSet.ResourceRecords[].Value`.

## Step 2 — Read the existing zone (find the conflict)

**Before writing anything, list what's already there.** Run:

```bash
aws route53 list-resource-record-sets \
  --hosted-zone-id Z0266992GQSG7W4H336 \
  --query "ResourceRecordSets[].{Name:Name,Type:Type,TTL:TTL,Records:ResourceRecords[].Value}" \
  --output table
```

The three conflict patterns you'll see, in order of likelihood:

1. **Existing TXT `@` for SPF.** The zone probably already has something like `"v=spf1 include:amazonses.com -all"` from when SES was wired up. The M365 wizard wants a new SPF. **You cannot have two TXT record-sets at the same name.** Pick one:
   - **MERGED:** keep both `include:amazonses.com` and add `a:dispatch-us.ppe-hosted.com include:secureserver.net`. Safer — preserves SES outbound if it's still in use.
   - **REPLACE:** literal wizard value. Faster but breaks SES outbound if it's still wired.
2. **Existing MX records** on `@` from a prior mail provider (Google Workspace, M365, etc.). The wizard's note 4 says "remove them." `DELETE` action in a change batch removes the entire record-set including all priority targets.
3. **Orphaned DKIM CNAMEs.** Look for `_domainkey.tentrilliontriangles.com` CNAMEs pointing at `dkim.amazonses.com` (legitimate SES DKIM) versus SendGrid or other vendors. Note: a duplicated name like `s1._domainkey.tentrilliontriangles.com.tentrilliontriangles.com` (the parent domain name repeated) is a malformed record — investigate before deleting.

## Step 3 — Atomic change batch (4 separate batches, not 1)

Route 53 **refuses a single change batch with two TXT records at the same name**. Split into separate batches, applied in this order:

**Batch 1: SPF (UPSERT or CREATE)**
```json
{
  "Comment": "MERGED SPF preserving include:amazonses.com alongside M365 wizard's requires",
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "tentrilliontriangles.com.",
      "Type": "TXT",
      "TTL": 600,
      "ResourceRecords": [
        { "Value": "\"v=spf1 a:dispatch-us.ppe-hosted.com include:secureserver.net include:amazonses.com -all\"" }
      ]
    }
  }]
}
```

**Batch 2: MX (CREATE)**
**Batch 3: CNAMEs `autodiscover` + `email` (CREATE)**
**Batch 4: M365 verification TXT — folded into the SAME `@` TXT record-set as a second value**

Critical: do NOT try `CREATE` for the M365 verification token as its own TXT `@` record-set. Route 53 will reject it with `InvalidChangeBatch: Tried to create resource record set [name='...', type='TXT'] but it already exists`. The fix is to UPSERT the apex TXT record-set with TWO `ResourceRecords` — one is the SPF, the other is the M365 verification string. DNS allows multiple values in one record-set:

```json
{
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "tentrilliontriangles.com.",
      "Type": "TXT",
      "TTL": 600,
      "ResourceRecords": [
        { "Value": "\"v=spf1 a:dispatch-us.ppe-hosted.com include:secureserver.net include:amazonses.com -all\"" },
        { "Value": "\"NETORGFT9192171.onmicrosoft.com\"" }
      ]
    }
  }]
}
```

MS's verification portal reads all `TXT @` records and looks for the verification token in any of them. The dual-value approach works.

**Apply each batch, then `aws route53 wait resource-record-sets-changed --id <change-id>` to block until INSYNC before the next.** Don't apply them in parallel — order matters (SPF before MX before CNAME).

## Step 4 — Verify with `dig` from the resolver

```bash
dig +short tentrilliontriangles.com MX
dig +short tentrilliontriangles.com TXT
dig +short autodiscover.tentrilliontriangles.com CNAME
dig +short email.tentrilliontriangles.com CNAME
```

DNS TTL is 600s (10 min), so wait a full propagation window before declaring victory on the resolver side. (Route 53 ITSYNC state happens in seconds — that's just the API accepting the change. Authoritative nameserver propagation is independent and slower.)

## Step 5 — Test send: do NOT use sendmail from this box

When proving "mail flows now," **never use `sendmail` from the terminal as the test sender.** Here's what happens:

- Your `From:` is e.g. `probe@tentrilliontriangles.com`
- The merged SPF is `v=spf1 a:dispatch-us.ppe-hosted.com include:secureserver.net include:amazonses.com -all`
- This terminal's IP is **none of those includes** — specifically not authorized by `a:`, not by `include:secureserver.net`, not by `include:amazonses.com`
- SPF validation returns **fail** (not softfail — `-all` means hard-fail)
- Recipient's `mx1-us1.ppe-hosted.com` (Proofpoint/FortiGate front) **quarantines** the message — not bounces, not delivers — because SPF-fail on a same-domain sender is a known spoofer signal
- No bounce comes back to you (Proofpoint swallows it)
- The message sits in `contact@`'s Junk/Quarantine folder, invisible to you

**The right test, in order of preference:**

1. **From a real GoDaddy webmail client** (`webmail.godaddy.com`) logged in as `contact@tentrilliontriangles.com` or any team mailbox, send to `contact@` itself. Webmail DKIM-signs and uses `secureserver.net` outbound (covered by SPF). Lands in inbox.
2. **From a real Gmail/Outlook web client** logged in as a team mailbox, send to `contact@`. Recipient is different domain, doesn't trip the same-domain flag.
3. **Direct SES via the production Lambda invocation** — invoke `ContactHandlerFunction` with the API GW proxy wrapper payload. This is the production path. See step 6.
4. **Last resort: direct CLI `aws sesv2 send-email`** with a unique marker in the subject. Uses SES directly, bypasses the Lambda entirely. Returns a `MessageId` if SES accepts.

The sendmail failure mode also teaches a recipient-side lesson: **CloudWatch shows `Send > 0, Delivery = 0, Bounce = 0`** — same fingerprint as Proofpoint quarantine. Don't get confused thinking MX is broken when it's actually SPF/DMARC alignment at the recipient.

## Step 6 — Direct Lambda invoke (the production path test)

Invoking the ContactHandler from the terminal to test "does the form path work":

```bash
INNER_JSON='{"name":"Bob Probe","email":"contact@tentrilliontriangles.com","company":"TenTrillionTriangles","role":"Founder","useCase":"Evaluating TPipe","budget":"$10k+/mo","message":"Marker: MXRESURRECT-20260628T230419Z\n\nSES-direct path test."}'

OUTER_JSON=$(printf '{"httpMethod":"POST","headers":{"Content-Type":"application/json","Origin":"https://www.tentrilliontriangles.com"},"body":%s}' \
  "$(printf '%s' "$INNER_JSON" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')")

printf '%s' "$OUTER_JSON" | base64 -w0 > /tmp/lambda-payload.b64

aws lambda invoke \
  --function-name ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB \
  --invocation-type RequestResponse \
  --log-type Tail \
  --payload file:///tmp/lambda-payload.b64 \
  --region us-east-1 \
  /tmp/lambda-resp.json
```

**Why the API GW proxy wrapper?** The handler does `JSON.parse(event.body || '{}')`. If you pass the form payload directly as the event object, `event.body` is `undefined`, parses to `{}`, validation fails for every required field. The wrapper makes the handler think it's a real API Gateway proxy request.

**Why base64 the payload?** The `aws lambda invoke` CLI's `--payload` parameter accepts a file path with `file://` scheme, OR a base64-encoded inline string. The file-with-`file://` approach is cleaner for complex payloads. If you do inline, `--cli-binary-format raw-in-base64-out` is the alternative.

### Validator whitelist gotcha

The handler's `validate.js` whitelists exact strings for `useCase` and `budget`:

- **useCase:** `Evaluating TPipe`, `Production Use`, `Research`, `Partner Integration`, `Open Source`, `Enterprise`, `Other`
- **budget:** `Under $1k/mo`, `$1k-5k/mo`, `$5k-10k/mo`, `$10k+/mo`, `Enterprise (need custom quote)`

There is **no `$50k+/mo` option** — selecting it in the contact form will be silently rejected. The dropdown in `src/components/pricing/ContactForm.astro` must stay in sync with these lists. (The validator's comment explicitly says "MUST stay in sync with src/components/pricing/ContactForm.astro options.")

If you get a 400 with `"Use case is required"` or `"Budget is required"`, your value isn't in the whitelist. Pick a valid value, or read the deployed `validate.js` from the bundle.

### Required fields

The handler requires `name`, `email`, `company`, `role`, `useCase`, `budget`, `message`. The 400 response lists all missing fields — read it like a checklist.

## Step 7 — Verify DDB write (independent of SES)

Even if the email doesn't arrive, the form path writes to DDB on success. Verify by scanning for the marker:

```bash
aws dynamodb scan \
  --table-name Contacts \
  --region us-east-1 \
  --filter-expression 'contains(#m, :m)' \
  --expression-attribute-names '{"#m":"message"}' \
  --expression-attribute-values '{":m":{"S":"MXRESURRECT"}}' \
  --query "Items[].{PK:PK.S,SK:SK.S,name:name.S,email:email.S,submittedAt:submittedAt.S,status:status.S}"
```

**Auto-pagination:** the MCP `run_script` sandbox paginates `Scan` automatically. Direct CLI `aws dynamodb scan` does NOT — it returns 1 MB at a time. Use `mcp_aws_aws___run_script` for full scans; for direct CLI, loop on `ExclusiveStartKey` or use `--max-items` to bound.

`Scan` with `Select=COUNT` includes the rate-limiter rows (`PK="RATE#<ip>"`) — message counts will be ~100 higher than reality. Partition-sum via `Query` on `StatusIndex` for accurate per-status counts.

## Step 8 — Check SES CloudWatch event destination log group

The configuration set `ttt-site-contact` has both an SNS event destination (`ttt-site-ses-bounces`) and a CloudWatch destination. The CloudWatch log group is:

```
/aws/ses/ttt-site-contact-events
```

NOT `/aws/ses/ConfigurationSetEvents/<set-name>`. The latter is a guess that doesn't work — the actual log group name is `/aws/ses/<configuration-set>-events` without the `ConfigurationSetEvents/` prefix.

**Log group events lag by 5–15 minutes.** If you check right after a Lambda invoke, expect empty results. Wait and re-poll.

## Step 9 — Tell the user to check the inbox

After all of the above, the only authoritative check is **the recipient's inbox**. The user (or whoever has the `contact@tentrilliontriangles.com` mailbox credentials) opens the inbox and looks for the unique marker. The probe's evidence sources stop at "SES accepted the send" — everything after that is the receiving infrastructure's responsibility and you cannot verify it from here.

**Possible verdicts and what they mean:**

| Verdict | What it means | Fix |
|---|---|---|
| Email in inbox | All four layers working. 22-day outage over. | Done. |
| Email in Junk | SPF/DKIM/DMARC alignment issue, not MX | Add DMARC record; verify all 3 DKIM CNAMEs present; release from quarantine |
| Email in Quarantine digest (GoDaddy AES / M365 Defender) | Recipient-side filter, not AWS-side | Release + add sender to allowlist — see `references/recipient-side-quarantine.md` |
| No email, no bounce | Either still in transit (wait 15 min) or recipient dropped silently | Try a different sender (Gmail), check CloudWatch logs 15 min later |
| Bounce back | Recipient server actively rejected | Read the SMTP status code: `5.1.2` = no such user, `5.7.x` = policy/SPF/auth, `4.x.x` = transient |

## Step 10 — Tell the user about the lost mail

Whatever you fix today, **the 22-day window of inbound mail is still mostly lost**. Most MTAs bounce within 24–72 hours with a DSN containing the original message. Recovery path:

1. Send a "sorry, our MX was misconfigured for 3 weeks, please resend" to the VIP contact list
2. Anything that came in via SES (the contact form) kept flowing — those are in the `Contacts` DDB table (verify count with `Scan Select=COUNT`)
3. Anything from `noreply@` senders is in a void (their bounce mailbox auto-purged)
4. Anything from MTAs that retried past 4–7 days is in a void

## Cross-references

- `references/ses-delivery-investigation.md` — full SES-side checklist (Step 2 onwards is identical, this file is just the SES-side piece)
- `references/recipient-side-quarantine.md` — when CloudWatch shows `Send > 0, Delivery = 0, Bounce = 0`, the problem is recipient-side filtering
- `references/contact-form-trace.md` — the per-layer evidence commands; this file's step 6 is the same Lambda-invoke recipe
- `references/cloudtrail-dns-regression.md` — if MX records were deleted and you want to know when/by whom

## One-line summary of the lesson

When "email has been down for weeks," the right diagnostic order is: **(1) confirm region, (2) read the screenshot literally, (3) check existing zone for conflicts, (4) atomic batch split because Route 53 forbids two TXT @ record-sets, (5) verify with `dig`, (6) test send via real webmail not sendmail, (7) check DDB write, (8) check CloudWatch event logs after 15 min, (9) ask the user to check inbox, (10) acknowledge the lost-mail window.**