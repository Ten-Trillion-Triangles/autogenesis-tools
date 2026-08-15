# CloudTrail DNS Regression Investigation

When the user reports a regression of the form "X used to work, now it doesn't" and X involves DNS (MX records, DKIM, SPF, A records, redirects), use CloudTrail `LookupEvents` to find what changed.

## The pattern

```python
import asyncio

ct = call_boto3(
    service_name='cloudtrail',
    operation_name='LookupEvents',
    params={
        'LookupAttributes': [
            {'AttributeKey': 'EventSource', 'AttributeValue': 'route53.amazonaws.com'}
        ],
        'MaxResults': 50
    }
)

events = [
    {
        'time': e.get('EventTime'),
        'name': e.get('EventName'),
        'user': e.get('Username'),
        'event_id': e.get('EventId'),
        'cloud_trail_event': e.get('CloudTrailEvent')  # contains the full requestParameters
    }
    for e in ct.get('Events', [])
]
```

The `CloudTrailEvent` field contains the full event JSON including `requestParameters` with the exact record set that was created, deleted, or upserted. Parse it to see what the change was:

```python
import json
for e in events:
    if e['name'] != 'ChangeResourceRecordSets':
        continue
    cte = json.loads(e['cloud_trail_event'])
    request = cte.get('requestParameters', {})
    zone_id = request.get('hostedZoneId')
    changes = request.get('changeBatch', {}).get('changes', [])
    for change in changes:
        print(f"{change['action']}: {change['resourceRecordSet']}")
```

## What to look for

- **`DELETE` actions** — records that were removed. Compare against current state to find what was lost.
- **Apex zone ID `Z0266992GQSG7W4H336`** — the contact form's `tentrilliontriangles.com` zone
- **www zone ID `Z00864641AXKDQ2VDEHG3`** — the `www.tentrilliontriangles.com` zone
- **`action: 'CREATE'` without trailing dot** — sometimes DNS changes fail silently when the FQDN doesn't have a trailing dot
- **`mfaAuthenticated: 'true'` in sessionContext** — these are interactive console changes (user logged in)
- **`mfaAuthenticated: 'false'` or missing** — these are programmatic (hermes user, amplify.amazonaws.com, aws-mcp)

## Common DNS change actors on ttt-site

- **`root` from `73.123.181.194` (Firefox/Ubuntu)** — the user manually editing via AWS console
- **`hermes` from `aws-mcp.amazonaws.com`** — programmatic changes via the AWS MCP
- **`root` from `amplify.amazonaws.com`** — AWS Amplify's own DNS changes (e.g., when you re-deploy, Amplify updates the A/CNAME records)

## Caveats — what CloudTrail does NOT show

1. **Zone file imports.** Records added via Route 53's "Import Zone File" feature appear as a single `ChangeResourceRecordSets` with all records, not as individual adds. Easy to miss if you grep for specific record types.
2. **Registrar-level changes.** If the domain's nameservers were ever pointed to a different DNS provider, records at that provider won't appear in Route 53 CloudTrail.
3. **Pre-lookback-window changes.** CloudTrail LookupEvents defaults to a 90-day lookback. Anything older is gone (unless you have a long-term S3 archive configured on the trail).
4. **Non-API changes.** Anything done via the console is captured, but if someone used the Route 53 API directly with a different IAM role or the old `route53` (v1) endpoint, it might appear with a different event name.

## Worked example — finding the MX record deletion (this session)

```python
# Get route53 events from the last 90 days
ct = call_boto3(
    service_name='cloudtrail',
    operation_name='LookupEvents',
    params={
        'LookupAttributes': [{'AttributeKey': 'EventName', 'AttributeValue': 'ChangeResourceRecordSets'}],
        'MaxResults': 50
    }
)

# Filter to events on the apex zone and parse each change
import json
for e in ct.get('Events', []):
    cte = json.loads(e.get('CloudTrailEvent', '{}'))
    if cte.get('requestParameters', {}).get('hostedZoneId') != 'Z0266992GQSG7W4H336':
        continue
    for change in cte['requestParameters']['changeBatch']['changes']:
        rs = change['resourceRecordSet']
        print(f"{e['EventTime']} {change['action']} {rs['type']} {rs['name']}")
```

In the actual session, the user's recent changes (2026-06-14) were:
- `CREATE CNAME hr3evj2esczh... → gv-z2m2r6id7ghvlq.dv.googlehosted.com` (Google Search Console verification)
- `DELETE` + `CREATE CNAME ekq3oyaaxyu5c2iuichqqdeu2ttore7s._domainkey...` (DKIM, trailing dot fix)

Neither touched MX. The MX records were never in the CloudTrail data — but that doesn't prove they never existed (zone file import, registrar panel, or pre-lookback changes are all possible). **Always verify with `dig` before drawing conclusions.**

## Historical context for ttt-site DNS

Looking at the full CloudTrail data (this session), the DNS history of the apex zone:

- **2026-06-05 23:16:** Amplify initial A + CNAME (CloudFront d3pgno5aueji96)
- **2026-06-06 01:46:** Amplify deletes the above (cleanup)
- **2026-06-06 02:01:** Amplify recreates A + CNAME (CloudFront d44a8ny3lbtxu)
- **2026-06-06 02:50:** Amplify recreates the same again (likely the A record was somehow wrong between)
- **2026-06-13 18:43:** hermes user: 3 DKIM CNAMEs + 1 SPF TXT (comment: "Enable DKIM for tentrilliontriangles.com + SPF for SES")
- **2026-06-14 12:53:** root (73.123.181.194): CREATE `hr3evj2esczh` Google DV CNAME
- **2026-06-14 12:54:** root (73.123.181.194): DELETE + CREATE one DKIM record (trailing dot fix)

That's the full picture. No MX changes are visible.

## Verification: cross-check with `dig`

CloudTrail is suggestive but not definitive. Always cross-check with external DNS:

```bash
dig tentrilliontriangles.com MX +short
dig tentrilliontriangles.com A +short
dig tentrilliontriangles.com TXT +short
dig www.tentrilliontriangles.com CNAME +short

# DKIM
for selector in 5m6gqncrk7nqgfopoaqndzyot4upp2vv ekq3oyaaxyu5c2iuichqqdeu2ttore7s knza6qbterncuudw4zidxtk4hqzl7e4g; do
    dig +short CNAME ${selector}._domainkey.tentrilliontriangles.com
done
```

If `dig MX` returns empty, MX is missing regardless of what CloudTrail shows.
