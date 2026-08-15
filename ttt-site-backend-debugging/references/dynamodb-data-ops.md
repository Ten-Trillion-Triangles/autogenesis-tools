# DynamoDB `Contacts` table — data-plane ops

The `Contacts` DynamoDB table is shared between two entity types (single-table design). This reference covers reading, archiving, and spam-triage operations against it without nuking data.

## Table layout

```
Table: Contacts  (region us-east-1, account 521369004927)
KeySchema:        PK (HASH, S) + SK (RANGE, S)
GSI:              StatusIndex — status (HASH, S) + submittedAt (RANGE, S), Projection=ALL
BillingMode:      (legacy) PROVISIONED — pay attention before bumping WCU/RCU
ItemCount:        ~100–110 typical (includes rate-limit windows)
```

## Entity types in the table

### Entity 1: Contact submission (`PK="CONTACT"`)

```
PK         = "CONTACT"
SK         = "<ISO8601 submittedAt>#<email>"   e.g. "2026-06-22T11:36:20.375Z#z.o@example.com"
status     = "new" | "spam" | "archived" | "contacted" | "qualified" | "closed"
submittedAt = ISO8601 string (also encoded in SK)
name, email, subject, message, company, role, budget, useCase, ipAddress, userAgent  (some optional)
```

### Entity 2: Rate-limiter sliding window (`PK="RATE#<ip>"`)

```
PK = "RATE#<ip>"     e.g. "RATE#73.123.181.194"
SK = "WINDOW#<epoch>"  e.g. "WINDOW#494806"
  + window start/end timestamps, request count, etc.
NO status, NO submittedAt, NO name, NO email.
```

These are written by the Lambda's rate-limit middleware. They are NOT user-visible submissions and must not be modified or interpreted as such.

## Reading the table

### List recent submissions (filter out rate-limit rows)

```python
r = await call_boto3(service_name='dynamodb', operation_name='Scan',
    params={'TableName': 'Contacts', 'Limit': 200})
items = r.get('Items', [])
messages = [it for it in items if it.get('PK', {}).get('S') == 'CONTACT']
messages.sort(key=lambda x: x.get('submittedAt', {}).get('S', ''), reverse=True)
```

`Scan` returns ALL items (rate-limit + messages) up to `Limit`. Always filter by `PK == "CONTACT"` after the scan, then sort by `submittedAt` desc.

### Count by status (use StatusIndex)

```python
async def status_count(s):
    r = await call_boto3(service_name='dynamodb', operation_name='Query',
        params={'TableName': 'Contacts', 'IndexName': 'StatusIndex',
                'KeyConditionExpression': '#st = :s',
                'ExpressionAttributeNames': {'#st': 'status'},
                'ExpressionAttributeValues': {':s': {'S': s}},
                'Select': 'COUNT'})
    return r.get('Count')
```

Parallelize with `asyncio.gather(status_count('new'), status_count('spam'), status_count('archived'), ...)` for a fast dashboard view.

### Total item count vs message count

`DescribeTable.ItemCount` and `Scan(Count)` return the TOTAL across all entity types. Don't report "table has 102 messages" when 23 of those are `RATE#` windows. Always reconcile: `total = sum(status_counts) + rate_limit_window_count`.

## Writing safely — the three traps

### Trap 1: `BatchWriteItem` with `PutRequest` nukes attributes

`PutRequest` REPLACES the item with only the attributes you list. Every other attribute (`name`, `email`, `message`, `submittedAt`, `useCase`, `role`, `company`, `budget`, `ipAddress`, `userAgent`) is silently dropped.

**Right tool for "set status" is `UpdateItem`** with `UpdateExpression: "SET #s = :s"` and `ExpressionAttributeNames: {"#s": "status"}`. UpdateItem only touches the attributes you specify.

If you must use BatchWriteItem for many status updates, use `PutRequest` with EVERY attribute you want to preserve (you'll have to read first, modify, then write). Easier path: loop `UpdateItem` calls — slower but correct.

**Recovery if you've already nuked a row:**
- `submittedAt` is recoverable from the SK prefix (`sk.split("#")[0]`).
- `email` is recoverable from the SK suffix.
- `name`, `message`, `subject`, and other user-provided fields are GONE for those rows unless you have a backup.

### Trap 2: `submittedAt` missing → invisible in StatusIndex

StatusIndex requires BOTH `status` and `submittedAt` to be set on the item. If a prior operation removed `submittedAt`, the row will:
- Still exist in the base table (visible via Scan/GetItem)
- NOT appear in any StatusIndex Query for any status partition
- NOT show up in admin UI status-filtered views

**Symptom**: `Scan` total > `sum(Query StatusIndex for each status)`. The delta is orphan rows.

**Fix**: `UpdateItem` to re-set `submittedAt` from the SK prefix. Single batch works.

### Trap 3: SK typo creates a phantom row

SK is `<ISO8601>#<email>` — high precision timestamps with millis. Typo ONE digit (e.g. `851` → `134`) and `BatchWriteItem` happily creates a NEW row at the typo'd SK. Your "update" landed on empty space; the original row is untouched at the correct SK.

**Detection**: Compare `DescribeTable.ItemCount` before and after a batch op. If `ItemCount` increased by more than 0, you wrote a phantom row.

**Fix**: `DeleteItem` the phantom (read it back first to confirm it's a husk — only PK/SK/status), then re-do the operation against the correct SK.

**Prevention**: NEVER type SKs by hand when constructing batch ops. Pull them from a prior Scan result and re-display them in the script source. Or use `UpdateItem` per row with keys read directly from a Scan.

## Standard operations

### Mark a single message as spam

```python
await call_boto3(service_name='dynamodb', operation_name='UpdateItem',
    params={
        'TableName': 'Contacts',
        'Key': {'PK': {'S': 'CONTACT'}, 'SK': {'S': sk_from_scan}},
        'UpdateExpression': 'SET #s = :spam',
        'ExpressionAttributeNames': {'#s': 'status'},
        'ExpressionAttributeValues': {':spam': {'S': 'spam'}},
    })
```

Returns nothing useful — verify by re-reading or by querying `StatusIndex` with `status="spam"`.

### Mark several messages as archived

Loop `UpdateItem` per row. Or use `BatchWriteItem` with `PutRequest` ONLY if you've read all the source rows and are re-emitting every attribute (safer to just loop).

### Verify after any batch op

1. Re-read the targeted rows. Confirm `name`, `email`, `message`, `submittedAt` are still present.
2. Re-query StatusIndex per status. Counts should match your intent.
3. `DescribeTable.ItemCount` should match `pre_count + 0` (no phantoms created) and `pre_count - deletions`.
4. If `ItemCount` drifted, scan for `PK="CONTACT"` items with no `status` attribute — those are orphans.

## Verification script

```bash
#!/usr/bin/env bash
# Verify Contacts table consistency — no orphan rows, partition counts match.
# Safe to run anytime. Read-only.
set -euo pipefail

DDB_TABLE="${DDB_TABLE:-Contacts}"

echo "=== Contacts table consistency check ==="

# Total item count
TOTAL=$(aws dynamodb describe-table --table-name "$DDB_TABLE" \
    --query 'Table.ItemCount' --output text)
echo "Total items (includes rate-limit windows): $TOTAL"

# Partition counts via GSI
for s in new spam archived contacted qualified closed; do
    N=$(aws dynamodb query --table-name "$DDB_TABLE" \
        --index-name StatusIndex \
        --key-condition-expression "#st = :s" \
        --expression-attribute-names '{"#st":"status"}' \
        --expression-attribute-values "{\":s\":{\"S\":\"$s\"}}" \
        --select COUNT --query 'Count' --output text)
    echo "  status=$s : $N"
done

# Count rate-limit windows
RL=$(aws dynamodb scan --table-name "$DDB_TABLE" \
    --filter-expression "begins_with(PK, :p)" \
    --expression-attribute-values '{":p":{"S":"RATE#"}}' \
    --select COUNT --query 'Count' --output text)
echo "Rate-limit windows (RATE#*): $RL"

# Count CONTACT rows missing status (orphans)
ORPHANS=$(aws dynamodb scan --table-name "$DDB_TABLE" \
    --filter-expression "PK = :pk AND attribute_not_exists(#st)" \
    --expression-attribute-names '{"#st":"status"}' \
    --expression-attribute-values '{":pk":{"S":"CONTACT"}}' \
    --select COUNT --query 'Count' --output text)
echo "CONTACT rows missing status (orphans): $ORPHANS"
```

If `total > sum(status_counts) + rate_limit_count + orphan_count`, you have a row type the script doesn't recognize — scan and inspect.

## When NOT to use this reference

- Building a new feature that writes to `Contacts` → use `ttt-site-pricing` for the form schema, or read `src/lambda/contact-handler/index.js` directly. This reference is for the admin/triage workflow, not the write path.
- Diagnosing why the contact form is broken → use `references/contact-form-trace.md` instead.

## Recognized bot-spam patterns (as of 2026-06-25)

When triaging the `new` queue, these signatures are observed-junk and safe to mark `status="spam"` in bulk. Spot-check a sample before bulk-updating.

| Pattern | Examples | Action |
|---|---|---|
| **Dotted-gmail gibberish** — `first.last.x.y.z.k@gmail.com` style with random initials between dots. Name + company + message are random base62 strings of similar length. Three submissions within ~30 seconds, then silence. Hits both contact form and waitlist signup. | `o.yun.a.r.ebe.1.7.8@gmail.com`, `ye.p.o.w.i.b.i.g.o.ki.59@gmail.com` | Mark all submissions from this email as `spam`. Pattern: same `email` field, names like `ggyDzmNNSyLmlrZc`, companies like `BkhBwxPUpXCdvSXFDzwseuzo`, messages like `MBIdQgBHClQFDTahZuvv`. |
| **Single-character name + single-character role/company** from a real-looking but disposable email, message is "test"-flavored | `name="A"`, `role="R"`, `company="C"`, message="This is a contact form test from apex, please ignore" — these are apex's automated CORS-fix verification traffic, NOT spam, but the inbox view should be deprioritized | These are apex's own QA. Either keep them in `new` for audit, or mark `archived`. DO NOT mark `spam` — they have legitimate internal provenance. |
| **Honest single-character placeholder messages** from your own email patterns | `name="bob"`, `company="bob"`, `message="bob"` from `bob@bob.com` | Personal scratch test from you. Mark `archived`, not `spam`. |

The first pattern is the only one that's safe to mark `spam` without reviewing the actual content. For everything else, read the message body.

**Safe bulk-spam recipe for the dotted-gmail pattern:**

```python
import asyncio

# Step 1: Scan all `new` items
scan = await call_boto3(service_name='dynamodb', operation_name='Scan',
    params={'TableName': 'Contacts',
            'FilterExpression': '#st = :new',
            'ExpressionAttributeNames': {'#st': 'status'},
            'ExpressionAttributeValues': {':new': {'S': 'new'}}})
items = scan.get('Items', [])

# Step 2: Identify dotted-gmail gibberish (4+ dots in local part, all lowercase alpha)
def is_bot_email(s):
    if not s or '@' not in s:
        return False
    local = s.split('@', 1)[0].lower()
    return local.count('.') >= 4 and local.replace('.', '').isalpha()

# Step 3: UpdateItem per match
async def mark_spam(item):
    await call_boto3(service_name='dynamodb', operation_name='UpdateItem',
        params={'TableName': 'Contacts',
                'Key': {'PK': item['PK'], 'SK': item['SK']},
                'UpdateExpression': 'SET #s = :spam',
                'ExpressionAttributeNames': {'#s': 'status'},
                'ExpressionAttributeValues': {':spam': {'S': 'spam'}}})

bot_items = [i for i in items if is_bot_email(i.get('email', {}).get('S', ''))]
await asyncio.gather(*[mark_spam(i) for i in bot_items])
```

Always re-scan after to confirm.