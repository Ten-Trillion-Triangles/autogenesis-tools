# SES Delivery Investigation Checklist

When the user reports "the contact form sends, but no email arrives at contact@tentrilliontriangles.com," run this checklist in order. The most common culprits are checked first.

## Background: the ttt-site SES setup

- **Sender:** `contact@tentrilliontriangles.com` (verified email identity)
- **Recipient:** `contact@tentrilliontriangles.com` (same — admin notification loops to itself)
- **Config set:** `ttt-site-contact` (enables event publishing)
- **Event destination:** `arn:aws:sns:us-east-1:521369004927:ttt-site-ses-bounces`
- **Configured from the Lambda env vars:** `SES_FROM_EMAIL`, `SES_TO_EMAIL`, `SES_CONFIG_SET`
- **Domain SPF:** `v=spf1 include:amazonses.com -all` (allows SES to send)
- **Domain DKIM:** 3 CNAMEs in Route 53 pointing to `dkim.amazonses.com`

## Step 0 (the cheap shortcut that often solves it): ask the user for a screenshot

Before any AWS investigation, send the user this question:

> "Can you take a screenshot of your inbox / spam folder / any quarantine or
> security digest emails (GoDaddy / Microsoft / Google) and tell me if you
> see any contact form emails? If you see a digest with a list of
> quarantined emails, click on 'Release' or 'Release & Approve' and tell me
> what happens."

The signature pattern that the problem is recipient-side filtering (not
MX records, not Lambda, not SES): the user shows you the contact form
emails landing in a **GoDaddy Advanced Email Security** quarantine digest
with `Preview | Release | Release & Approve | Block` actions. CloudWatch
shows `Send > 0, Delivery = 0, Bounce = 0`. The fix is to release and
allowlist. See `references/recipient-side-quarantine.md` for the full
recipient-side diagnostic.

## The checklist (in order)

### 1. Does the recipient domain have MX records?

```bash
dig MX tentrilliontriangles.com +short
```

If empty: **STOP. Mail cannot be delivered to anything@tentrilliontriangles.com.** This is the most common cause of "emails don't arrive" and it has no workaround via SES. The fix is to either:

- Add MX records pointing to a real mail server (Google Workspace, AWS WorkMail, Microsoft 365, etc.)
- Change `SES_TO_EMAIL` to a real inbox on a working domain (Gmail, Outlook, ProtonMail, etc.) and redeploy the Lambda

Do NOT assume "MX records never existed" — CloudTrail may not capture zone file imports, registrar changes, or pre-lookback-window additions. Always verify with `dig` before declaring it.

Also: if the email is hosted at a third party (GoDaddy, M365, Google Workspace), the MX records for the email flow live wherever the mailbox provider's DNS is configured — that's typically NOT in Route 53. Check the registrar's panel and the email provider's DNS configuration.

**If the user shows you their inbox has the contact form emails but in a "Quarantine" digest, the problem is NOT the MX record. Jump to `references/recipient-side-quarantine.md` for the real fix path.**

### 2. Is SES itself sending?

```python
# Direct CLI test — bypasses Lambda entirely
direct = call_boto3(
    service_name='sesv2',
    operation_name='SendEmail',
    params={
        'FromEmailAddress': 'contact@tentrilliontriangles.com',
        'Destination': {'ToAddresses': ['contact@tentrilliontriangles.com']},
        'Content': {
            'Simple': {
                'Subject': {'Data': 'CLI DIRECT SES TEST', 'Charset': 'UTF-8'},
                'Body': {'Text': {'Data': 'If you receive this, SES itself is working.', 'Charset': 'UTF-8'}}
            }
        },
        'ConfigurationSetName': 'ttt-site-contact'
    }
)
# If direct['MessageId'] is set, SES accepted the send
```

If SES is sending from CLI but the form emails still don't arrive, the problem is downstream (deliverability, not delivery).

### 3. Is the CloudWatch `SentLast24Hours` quota metric increasing?

```python
quota = call_boto3(service_name='sesv2', operation_name='GetAccount')
sent_24h = quota['SendQuota']['SentLast24Hours']
```

**This metric lags the actual SES activity by 10-15 minutes.** A value of `0.0` right after a direct invoke does NOT mean SES wasn't called. Wait 15 minutes and re-check.

**Better signal: per-day `Send` metric from CloudWatch with 1-day period.** This shows daily send counts, not the lagging rolling-24h. Compare against the DDB row count for the same day to spot divergence.

### 4. Are bounce/complaint events reaching a confirmed subscriber?

```python
subs = call_boto3(
    service_name='sns',
    operation_name='ListSubscriptionsByTopic',
    params={'TopicArn': 'arn:aws:sns:us-east-1:521369004927:ttt-site-ses-bounces'}
)
# If SubscriptionArn == 'PendingConfirmation', events go nowhere
```

A `PendingConfirmation` subscription means:
1. SNS events ARE being published by SES (good — config set works)
2. But they reach no consumer (bad — no observability)
3. Bounce notifications from SES to the original recipient are also lost in transit (since the destination is broken — see step 1)

To fix: confirm the email subscription (click the AWS confirmation link in the original SNS email) or replace it with a CloudWatch Logs destination for real-time observability. **For ttt-site specifically, the CloudWatch destination approach is broken in SESv2** — see `references/ses-cloudwatch-destination-gotcha.md`. Use an SNS + Lambda subscriber instead.

### 5. Is the SES identity verified and production access enabled?

```python
identities = call_boto3(
    service_name='sesv2',
    operation_name='ListEmailIdentities'
)
# Look for tentrilliontriangles.com (DOMAIN) and contact@tentrilliontriangles.com (EMAIL_ADDRESS)
# Both should have VerificationStatus: 'SUCCESS' and SendingEnabled: true

account = call_boto3(service_name='sesv2', operation_name='GetAccount')
# ProductionAccessEnabled should be true
# EnforcementStatus should be 'HEALTHY'
```

If the identity is in `Pending` verification status, SES will accept the request but bounce it. If `ProductionAccessEnabled` is false, you're in SES sandbox and can only send to verified recipient addresses.

### 6. Is the Lambda actually calling SES?

The contact handler has this pattern:

```javascript
// index.js lines 67-80
try {
  await sendAdminNotification({...});
} catch (emailError) {
  console.warn('Email notification failed (non-fatal):', emailError.message);
}
```

The try/catch swallows SES errors silently. If `sendAdminNotification` throws (e.g., access denied, identity issue), the Lambda returns 200 with no DDB write lost but no email sent. To detect this:

```python
# Get the most recent log stream and look for console.warn
events = call_boto3(
    service_name='logs',
    operation_name='GetLogEvents',
    params={
        'logGroupName': '/aws/lambda/ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB',
        'logStreamName': '<latest-stream>',
        'limit': 30
    }
)
# If you see 'Email notification failed (non-fatal):' anywhere, the SES call threw
```

A clean log (no `Email notification failed`) means either SES succeeded or the SES call wasn't reached. Verify with a direct invoke that includes `LogType: Tail`.

**Heuristic for "SES was called but succeeded silently":** ~~Lambda duration is 200-900ms. DDB write alone is ~50-100ms. The remaining time is the SES round-trip.~~ **RETRACTED 2026-06-25.** The duration heuristic gives false positives. A Lambda with no SES call at all can complete in 150ms with a 200 response if `sendAdminNotification` short-circuits via `USE_SMTP=1` or a stale-build no-op path. Use the `SentLast24Hours` counter instead: if the counter does not increment after a successful Lambda invocation, SES was not contacted — regardless of duration or log silence.

### 7. Are SPF and DKIM aligned?

```bash
dig +short TXT tentrilliontriangles.com | grep spf
# Expected: "v=spf1 include:amazonses.com -all"

dig +short CNAME 5m6gqncrk7nqgfopoaqndzyot4upp2vv._domainkey.tentrilliontriangles.com
# Expected: 5m6gqncrk7nqgfopoaqndzyot4upp2vv.dkim.amazonses.com.
# (and 2 more for the other DKIM CNAMEs)
```

Missing SPF or DKIM means recipient mail servers are more likely to mark the email as spam or reject it.

### 8. Is there a DMARC record?

```bash
dig +short TXT _dmarc.tentrilliontriangles.com
# If empty, no DMARC policy — recipient servers fall back to SPF/DKIM only
```

Without DMARC, some providers (notably Microsoft/Outlook) are more aggressive about quarantine/spam decisions. Adding a DMARC record is cheap:

```bash
# In Route 53
_dmarc.tentrilliontriangles.com.  IN  TXT  "v=DMARC1; p=none; rua=mailto:contact@tentrilliontriangles.com"
```

Start with `p=none` (monitor only, no enforcement). Once you have good signal from `rua` reports, move to `p=quarantine` or `p=reject`.

## When you've found the problem

| Symptom | Fix |
|---|---|
| No MX records | Add MX records OR change `SES_TO_EMAIL` env var to a real inbox, then `sam deploy` |
| Emails in GoDaddy Advanced Email Security quarantine | Release + add SES sender to allowlist (see `references/recipient-side-quarantine.md`) |
| CLI direct send works, form emails don't | The Lambda is the problem — check `USE_SMTP` env, Lambda code, IAM role SES permissions |
| CLI direct send fails | SES identity/production access issue — see step 5 |
| Bounce event topic has `PendingConfirmation` sub | Click the AWS confirmation link OR replace with SNS + Lambda subscriber (CloudWatch destination won't work in v2 — see gotcha reference) |
| `SentLast24Hours` not increasing | Wait 15 minutes (lag) — if still 0, SES isn't being called. Better: check daily CloudWatch `Send` metric |
| Email arrives at spam | Fix SPF/DKIM/DMARC alignment |

## Edge cases worth checking

- **Self-send suppression:** if `From == To` and recipient provider is Gmail, the email may be silently dropped or quarantined. Test by sending `contact@tentrilliontriangles.com → some-real-gmail-address`.
- **SMTP fallback active:** if `USE_SMTP=1` is in the Lambda env vars, the handler routes to nodemailer instead of SES. Should not happen in production but worth checking.
- **Sandbox mode:** if `ProductionAccessEnabled` is false, you can only send to verified recipient addresses (the same address as `From`). Production access request was historically denied (CaseId: 178069955500104). Check current state.
- **Recipient-side quarantine:** CloudWatch shows `Send > 0, Delivery = 0, Bounce = 0`. The receiving mail server is filtering before SMTP completes. See `references/recipient-side-quarantine.md`.
- **DKIM or SPF records modified mid-flight:** CloudTrail DNS history can show who changed what and when. If the user is certain emails arrived before, find the regression point via `cloudtrail:LookupEvents` filtered to `EventSource=route53.amazonaws.com`.
- **Rate limit false positive:** the contact form's rate limiter (`rate-limit.js`) allows 5 requests/hour per IP. A test from `127.0.0.1` will be blocked after 5 invocations. The 429 is silent — `sendContact` returns 429 before reaching DDB. The Lambda log will show a much shorter duration (~30-50ms).
