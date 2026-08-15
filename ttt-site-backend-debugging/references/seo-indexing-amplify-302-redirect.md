# SEO Indexing Failures: Apex→WWW 302 Redirect in Amplify customRules

Captured 2026-07-03 from a Search Console "Page indexing" report showing 4 distinct failure categories — all traced to a single root cause.

## The symptom (Search Console "Page indexing" report)

When the user reports indexing failures, you may see all four of these buckets at once and assume multiple independent problems. **They are usually one root cause:**

| Bucket in GSC | Real cause |
|---|---|
| "Page with redirect" | Apex URL 3xx's to www — Google records this for every URL on the site |
| "Alternate page with proper canonical tag" | Canonical points to apex, apex 3xx's to www, Google sees a canonical loop |
| "Crawled - currently not indexed" | Google dedup'd both versions, de-prioritized after the redirect↔canonical dance |
| "Not found (404)" | Inbound links to old/renamed URLs (NOT in the sitemap — sitemap URLs all return 200) |

## The 60-second check

```bash
curl -sI https://<apex-domain>/ | head -5
```

If the response is `HTTP/2 302` with `location: https://www.<domain>/`, you've found it. If it's `301`, the redirect is fine — the bug is elsewhere (canonical mismatch, sitemap drift, real 404s from inbound links).

## Where the 302 actually lives (ttt-site: Amplify customRules)

The redirect is **not** in Route 53, **not** in S3 bucket website config, and **not** in a CloudFront function you can edit. It is in the Amplify Console's "Rewrites and redirects" panel, which surfaces in the AWS API as the `customRules` field on the Amplify app.

```bash
# Find the Amplify app for a site
aws amplify list-apps --query "apps[?name=='<app-name>'].appId" --output text --region us-east-1
# d48lytolyaq3z for ttt-site as of 2026-07-03

# Read the customRules (this is the smoking gun)
aws amplify get-app --app-id d48lytolyaq3z --region us-east-1 \
  --query "app.customRules" --output json
```

For ttt-site as of 2026-07-03 the rules were:

```json
[
  {
    "source": "https://tentrilliontriangles.com",
    "target": "https://www.tentrilliontriangles.com",
    "status": "302"
  },
  {
    "source": "/<*>",
    "target": "/index.html",
    "status": "404-200"
  }
]
```

That single `"status": "302"` is the entire problem. The second rule (`/<*> → /index.html, 404-200`) is the Astro SPA fallback — it's correct and not part of the bug.

## Why 302 is wrong, why 301 is right

| Status | What Google does | When to use |
|---|---|---|
| **302 Found** | "Temporarily moved. Keep both URLs in the index, dedupe with canonical." | A/B test, temporary maintenance, page under construction |
| **301 Moved Permanently** | "Permanently moved. Move apex out of the index, consolidate signal to www, transfer PageRank." | Permanent canonicalization (apex → www, http → https, old domain → new domain) |

The interaction with the canonical tag is the trap. The ttt-site layout emits:

```html
<link rel="canonical" href="https://tentrilliontriangles.com/">
```

So with 302 + canonical-pointing-to-apex, Google sees:
1. Crawl `tentrilliontriangles.com/blog/foo/`
2. See canonical self-reference
3. Get 302 → `www.tentrilliontriangles.com/blog/foo/`
4. Crawl www
5. See canonical → apex (self-reference)
6. Decide to keep both. De-prioritize indexing.

**301 alone fixes ~80% of the issue.** The remaining "Alternate page with proper canonical tag" bucket clears naturally within 2-4 weeks as Google re-crawls.

## The fix (single API call)

```bash
aws amplify update-app \
  --app-id d48lytolyaq3z \
  --region us-east-1 \
  --custom-rules '[
    {
      "source": "https://tentrilliontriangles.com",
      "target": "https://www.tentrilliontriangles.com",
      "status": "301"
    },
    {
      "source": "/<*>",
      "target": "/index.html",
      "status": "404-200"
    }
  ]'
```

**Do not run this without operator approval.** It changes production site behavior. Reversible (change 301 back to 302), but Google will re-converge over 24-48 hours.

## The 20% followup: canonical host

After the 301 lands, canonical tags still point to apex. The 301 will eventually win, but cleaner is to also fix the canonical to point to `www.`. That's a layout change (`BaseLayout.astro` or wherever the canonical is constructed) + rebuild + deploy.

Also check for **inconsistent trailing-slash canonicals** — some pages canonicalize to `/foo/` and some to `/foo`. Astro defaults to no trailing slash; the layout should match. Mixed trailing-slash is a real bug class. As of 2026-07-03, ttt-site had:

```
<link rel="canonical" href="https://tentrilliontriangles.com/">                          ← trailing /
<link rel="canonical" href="https://tentrilliontriangles.com/blog/.../native-runtime">  ← NO trailing /
<link rel="canonical" href="https://tentrilliontriangles.com/comparison/tpipe-vs-langchain"> ← NO trailing /
<link rel="canonical" href="https://tentrilliontriangles.com/docs/core-concepts/pipe-class/"> ← trailing /
```

Pick one (Astro default = no trailing slash) and enforce.

## Why the redirect is at Amplify, not CloudFront/S3

`aws cloudfront list-distributions` for account 521369004927 returns **zero distributions**. The CloudFront domain `d44a8ny3lbtxu.cloudfront.net` (the one in the Route 53 A record) is **provisioned by Amplify** under an AWS-managed account, not yours. That's why:
- You can't see it in `aws cloudfront list-distributions`
- You can't put a Lambda@Edge or CloudFront Function on it
- The only place the 302 is configurable is the Amplify `customRules` field

If you ever migrate the site off Amplify (CloudFront+S3 standalone, Vercel, etc.), the 302/301 rule needs to be re-implemented in the new platform's redirect primitive.

## Don't conflate this with the contact-form / SES / DNS debugging workflow

This skill is `ttt-site-backend-debugging`. **The "page indexing" failure is a marketing/SEO problem, not a backend problem.** Different layer, different evidence, different fix. The same skill covers both because the surface is "the live site is misbehaving" and the resources overlap (same AWS account, same hosted zones, same Amplify app). But the investigation recipe is different:

- **Backend debugging:** trace the request path (browser → API GW → Lambda → DDB/SES) using the playbook in the main SKILL.md
- **SEO indexing:** start with `curl -sI <apex>`, then read `amplify get-app --custom-rules`, then `route53 list-resource-record-sets`

The Sitemap and SEO work belongs at the **content layer** (sitemap.xml.ts in `src/pages/`, canonicals in the layouts, `public/robots.txt`). The redirect/amplify-rule work is the **platform layer** (Amplify Console customRules). Two different fixes, two different files, two different owners.

## The forensic question: "WHO/WHEN/WHY was this redirect added?"

When the operator asks "why is this 302 there in the first place" (real question, asked 2026-07-03), the answer is reconstructible from CloudTrail even though Amplify Console UI clicks don't always produce a single obvious audit event. The recipe:

1. **Get the Amplify app's `updateTime`** from `aws amplify get-app`. This is the smoking gun — it updates whenever any field of the app changes (rules, domain, build spec, env vars). The 302's `updateTime` for ttt-site was `2026-06-06T02:50:11Z`.

2. **Pull CloudTrail events for `amplify.amazonaws.com` in the 5-minute window** around that timestamp. Use:
   ```bash
   aws cloudtrail lookup-events \
     --lookup-attributes AttributeKey=EventSource,AttributeValue=amplify.amazonaws.com \
     --region us-east-1 \
     --start-time <updateTime-2min> --end-time <updateTime+2min> \
     --max-items 50 --output json
   ```

3. **Look for the `UpdateApp` mutation.** The `requestParameters` will include the full `customRules` list. If you see one, the 302 was added by an API call. If you don't (just reads, no mutations), the 302 was added by an Amplify Console UI click that bundled multiple field changes into one internal action. For ttt-site, the `UpdateApp` event at `2026-06-06T02:50:11Z` was found and it was the moment the 302 was added.

4. **Look at the parallel `UpdateDomainAssociation` event** at the same second. If a domain-attach happened in the same 1-second window as the `UpdateApp`, the 302 was almost certainly added by the Amplify Console's domain-management wizard as a default-suggested redirect, not as a deliberate SEO decision. The wizard flow is:
   ```
   UpdateDomainAssociation  →  Route53 ChangeResourceRecordSets  →  UpdateApp
   (attach domain)            (create A/CNAME records)             (apply default redirect)
   ```
   All three happen within ~1 second, all by the same `userIdentity` (typically `root` or a console user with `sessionCredentialFromConsole: true`).

5. **Decode the `userIdentity`**: `type: "Root"` = AWS account root user; `type: "IAMUser"` = an IAM user; `invokedBy: "aws-mcp.amazonaws.com"` = via the AWS MCP server (e.g. `mcp_aws_aws___call_aws`); `sessionCredentialFromConsole: "true"` = Amplify Console UI click. For ttt-site, the `UpdateApp` event was by `root` from `73.123.181.194` (the operator's home IP) via Firefox 151 in the Console.

6. **The "why 302 not 301" answer**: the Amplify Console's redirect dropdown defaults to 302. The wizard does not warn that 302 causes indexing issues. The operator almost certainly didn't deliberate on the 302/301 choice — it was a one-click default during domain setup.

### Real example: ttt-site's 302 origin (reconstructed 2026-07-03)

| Time (UTC) | Event | Actor | What happened |
|---|---|---|---|
| 2026-05-26T21:07:35 | `CreateApp` | `root` via Console | App created with only `customRules: [/<*> → /index.html, 404-200]`. **No 302 at this point.** |
| (10 days of normal deploys, 65 total) | | | |
| 2026-06-06T02:50:10 | `UpdateDomainAssociation` | `root` via Console | Attached `tentrilliontriangles.com` to the app, with subDomainSettings `[www, ""]` |
| 2026-06-06T02:50:11 | `ChangeResourceRecordSets` | Amplify service (on root's behalf) | Created apex A alias + www CNAME, both → `d44a8ny3lbtxu.cloudfront.net` |
| **2026-06-06T02:50:11** | **`UpdateApp`** | **`root` via Console** | **Added the `https://tentrilliontriangles.com → https://www.tentrilliontriangles.com, 302` rule** |
| 2026-06-06T02:50:11+ | `app.updateTime` changes to this timestamp | | This is the field to grep against later |

The git log does NOT mention the 302 because Amplify Console settings are not in source control. There will be no commit with "302" in its message. The 302 is "invisible" to anyone who only looks at the repo.

### Why CloudTrail sometimes shows no `UpdateApp` event but the rules still changed

If you find the `updateTime` change but no `UpdateApp` event in the trail, the change was made by:
- An **Amplify Console UI click** that bundled multiple field updates into a single internal Amplify API (some Console panels fire `TagResource` or `UpdateApp` with only partial diff fields, and the actual full `customRules` payload is reconstructed server-side).
- A **CloudFormation stack update** if the Amplify app is managed by CFN (not the case for ttt-site — it's console-managed).
- A **direct AWS API call from an old session** that has been aged out of the 90-day default CloudTrail retention.

**This account has no S3-backed CloudTrail trail** (verified 2026-07-03: `aws cloudtrail describe-trails` returns empty `trailList: []`). All audit history is in the 90-day event history, and management events older than 90 days are gone forever. **This is a real risk** — set up a CloudTrail trail with S3 archival if you need audit history past 90 days. The skill's earlier "no CloudTrail trail" finding applies to this AWS account globally; if you need to investigate anything older than 90 days, the answer is "not retrievable from CloudTrail" and you need alternative evidence (git, S3 logs, internal docs).

### The "two Amplify apps" pattern

ttt-site has had two Amplify apps in its history:
- `d2vx7pek5h0ard` (created ~2026-05-24, broken with `x-cache: Error from cloudfront` on every URL — the "x-cache 404 bug" documented in `md/00-amplify-404-investigation.md`)
- `d48lytolyaq3z` (created 2026-05-26, the current working one)

**The lesson:** when an Amplify app is irrecoverably broken (Amplify Console's internal CloudFront→S3 chain is in a state AWS support has to fix manually), the practical fix is to **delete the broken app and create a new one**, not to try to repair the broken one via repeated `update-app` calls. The audit trail in `md/00-amplify-404-investigation.md` documents 8 consecutive failed deploys on `d2vx7pek5h0ard` before the pivot.

**Implication for forensics:** the Amplify app ID in the operator's current config (`d48lytolyaq3z`) is the second one. Old artifacts (job logs, build artifacts) from `d2vx7pek5h0ard` are still in S3 and may surface in searches. Don't be confused when the old app ID appears in `md/` notes — it's the previous generation, not the current one.

## Pitfalls when working in this AWS account (MCP-side)

- **AWS MCP server visible in gateway but not in this session.** `hermes tools list` shows `aws — all tools enabled` and `agent.log` shows `MCP server 'aws' (stdio): registered 9 tool(s)` at gateway startup, but the current session's toolset does NOT include `mcp_aws_*`. Cause: per-session tool-snapshot caching, late-binding doesn't fire mid-conversation, the 1.5s `mcp_discovery_timeout` cap kills lazy-starting servers. **Workaround used 2026-07-03:** the `scripts/aws_mcp_query.py` script speaks JSON-RPC directly to `mcp-proxy-for-aws` via `uvx`, bypassing Hermes entirely. Same 9 tools, same SigV4 credentials, no dependency on Hermes MCP loader. See the "When the AWS MCP tools aren't visible in your session" section in the main SKILL.md.
- **CloudTrail default 90-day retention with no S3 trail.** Don't promise the operator you can reconstruct an audit chain older than 90 days — that data is gone forever for this account. The fix is to set up a CloudTrail trail (multi-region, with S3 + optional CloudWatch Logs integration) the first time it's needed. For one-off investigations in older windows, the only recovery is from git history, S3 access logs, application logs, or operator memory.
- **CloudFront distributions for Amplify-managed apps are invisible.** `aws cloudfront list-distributions` returns empty for this account. The CloudFront domain in the Route 53 A record (`d44a8ny3lbtxu.cloudfront.net`) is provisioned by Amplify under an AWS-managed account, not yours. Don't try to set up a CloudFront Function or Lambda@Edge on it — you don't own the distribution.

## Related

- `routing-traffic-with-route53-and-cloudfront` skill — general Route 53 + CloudFront setup; also covers the 301-vs-302 SEO canonicalization table at depth (this reference covers the Amplify-specific case)
- `ttt-site-blog` and `ttt-site-comparison-pages` skills — content layer where canonicals are emitted
- `aws-amplify` skill — Amplify Console workflows (rewrites/redirects panel = `customRules` API field)
- `scripts/aws_mcp_query.py` — the direct-AWS-MCP-via-uvx client used during the 2026-07-03 investigation to bypass the Hermes MCP loader's late-binding. Use when `mcp_aws_*` tools aren't in the session's toolset but you need to run AWS calls without restarting the gateway.