# Recipient-Side Filtering: The Hidden Email Black Hole

When the user reports "emails aren't arriving," the most common scenario the user has
actually been experiencing is **the email is arriving but getting filtered at the
recipient side** — and the AWS-side metrics look fine because the email was never
bounced at SMTP. This reference covers how to detect, confirm, and resolve it.

## Symptom signature

- Lambda: returns 200, no `console.warn`, durations consistent with DDB + SES
- DynamoDB: row present
- SES: returns `MessageId`, CloudWatch `Send` count goes up
- CloudWatch `Bounce`: 0 (or near 0)
- CloudWatch `Delivery`: 0
- User: "I'm not seeing the email"

This pattern — `Send > 0`, `Delivery = 0`, `Bounce = 0` — is the fingerprint of
**recipient-side filter interception**. The receiving mail server (or a
pre-SMTP-accept security layer) is dropping or quarantining the email before
SMTP completes, so SES never sees a "delivered" or "bounced" final-state event.

## The GoDaddy Advanced Email Security pattern (real-world example)

This is what shows up when the recipient domain's email is routed through
**GoDaddy + Microsoft 365** with GoDaddy's email security subscription enabled.

### What the user sees

In their Microsoft 365 Outlook web client (e.g. `outlook.cloud.microsoft`):

1. **Inbox has 800+ unread messages**, mostly AWS / Google / spam digests
2. A periodic email from **GoDaddy Advanced Email Security** with subject
   "Quarantine List - GoDaddy Em..." and the pattern `Quarantined (by Score)` table
3. The table has columns: `Address`, `Subject`, `Delivery Date/Time`, `Action`
4. Action links per row: **Preview | Release | Release & Approve | Block**
5. The quarantined emails are FROM `contact@tentrilliontriangles.com` (the SES
   sender) and have subjects like `[TPipe Contact] Test User from TestCo`

### Why the bounces never show up in SES

GoDaddy intercepts after SMTP RCPT TO but before final delivery, marks the
email as quarantined, and **does not return an SMTP bounce to SES**. SES sees
the email as still "in flight" and eventually moves on without recording a
bounce event. The `Bounce` count stays at 0 even though the user never sees
the email.

### The fix path

**Short-term (immediate unblock):**
1. User opens the GoDaddy Advanced Email Security digest email
2. Clicks `Release` (or `Release & Approve`) on the quarantined contact form emails
3. The emails land in their inbox and they're visible

**Medium-term (prevent future quarantines):**
1. User logs into GoDaddy Advanced Email Security admin console
2. Adds the SES sending identity (the verified sender, e.g.
   `contact@tentrilliontriangles.com`) to the **Sender Allowlist** (also called
   "Approved Senders" depending on console version)
3. Future SES-originated emails skip the quarantine scan and go straight to inbox

**Long-term (lower spam score so they pass through without allowlisting):**
1. Verify SPF (`v=spf1 include:amazonses.com -all` for ttt-site's domain) is in place
2. Verify the 3 DKIM CNAMEs are in Route 53 pointing to `*.dkim.amazonses.com`
3. Add a **DMARC** record: `_dmarc.tentrilliontriangles.com. IN TXT "v=DMARC1; p=none; rua=mailto:contact@tentrilliontriangles.com"`
4. Avoid spam-triggering content: "test" in subject lines, all-caps, multiple
   exclamation points, generic body text. The original GoDaddy quarantine on
   2026-06-06 was triggered by test subjects like `[TPipe Contact] Test from X`.

## Diagnostic confirmation: how to be sure it's recipient-side

**Tell-tale signs the problem is recipient-side, not AWS-side:**

1. The user can show you a screenshot of their **spam folder, quarantine digest,
   or junk folder** containing the missing emails
2. A direct CLI `aws sesv2 send-email` test with a unique marker (e.g. "DIRECT SES
   RECIPIENT TEST") does NOT appear in the user's inbox even 5+ minutes later
3. CloudWatch `Bounce` count is 0 (if the receiving server was bouncing, we'd
   see it)
4. The user can describe their email setup (GoDaddy / M365 / Gmail for business
   / etc.) and it's plausible they have a security filter in front of it

**Tell-tale signs the problem is AWS-side, not recipient-side:**

1. CloudWatch `Send` is also 0 (Lambda is silently failing before reaching SES)
2. CloudWatch `Bounce` count is high (recipient server IS returning bounces)
3. The Lambda log shows `Email notification failed (non-fatal):` lines
4. A direct CLI send-email from your machine (different IP / different auth
   context) fails the same way

## Related: the `SentLast24Hours` is NOT a real-time metric

`GetAccount.SendQuota.SentLast24Hours` lags the actual SES activity by 10-15
minutes. A value of `0.0` right after a direct send does **not** mean SES
wasn't called. Use a direct CLI `aws sesv2 send-email` and check that you
get a real `MessageId` response — that's the authoritative proof SES itself
accepted the send, regardless of what the quota metric says.

## Where to look for the recipient-side filter

For ttt-site specifically:

- **Email hosted at GoDaddy** → GoDaddy webmail, then GoDaddy Advanced Email
  Security (admin login at `https://email.secureserver.net`)
- **Email hosted at Microsoft 365** → `outlook.cloud.microsoft`, then
  Microsoft 365 Defender (admin login at `https://security.microsoft.com`)
- **Email hosted at Google Workspace** → `mail.google.com`, then Google Admin
  Console > Apps > Google Workspace > Gmail > Safety
- **Email hosted at AWS WorkMail** → WorkMail web app, no external filter
  typically
- **Email forwarded from the domain to a personal Gmail/Outlook** → check the
  forwarding rules at the registrar/email provider, AND check the destination's
  spam folder

## Quick ask-the-user prompt

When the user says "I don't see the email," this is the question that
short-circuits the most debugging time:

> "Can you check (1) your regular inbox, (2) your spam folder, and (3) any
> quarantine or security digest emails (from GoDaddy / Microsoft / Google)?
> If you see a digest with a list of quarantined emails, click on
> 'Release' or 'Release & Approve' and tell me what happens."

That single question often surfaces the real problem in one round trip
instead of an hour of AWS console digging.
