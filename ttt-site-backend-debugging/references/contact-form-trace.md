# Contact Form Trace — Exact Commands

End-to-end trace of a single contact form submission from browser to inbox. Use this when the user says "I submitted but the email never arrived" or "did the form actually send?"

## What the trace proves at each step

| # | What it proves | Evidence in the data |
|---|---|---|
| 1 | The form's fetch was issued | Network tab / browser console |
| 2 | API Gateway received the request | Lambda log stream has a new `START` line |
| 3 | Lambda was invoked | Log `START RequestId: <uuid>` |
| 4 | Rate limit allowed it | No early `429` in the log (we'd see 429 before any DDB or SES) |
| 5 | Validation passed | No 400 in the log; DynamoDB row exists |
| 6 | DDB write succeeded | `Scan` with marker filter returns the row |
| 7 | SES was called | Lambda duration is 200-900ms (DDB alone is ~50-100ms; rest is SES) |
| 8 | SES accepted the send | CLI direct `sesv2 send-email` returns a `MessageId` |
| 9 | Email was attempted to deliver | CloudWatch `SentLast24Hours` updates within 15 min |
| 10 | Email was actually delivered | Requires MX records on recipient domain + working inbox |

If evidence at any step is missing, that's where the bug is. Stop and fix that step before continuing.

## The exact trace commands

### Step 1-2: Confirm the API route

```python
# AWS MCP — list resources on the contact API
resources = call_boto3(
    service_name='apigateway',
    operation_name='GetResources',
    params={'restApiId': 'mgf9b7ggkd'}
)
# Look for path == '/contact' with methods including 'POST'
```

Expected: `{'path': '/contact', 'methods': ['OPTIONS', 'POST']}`

### Step 3-4: Confirm Lambda invocation

```python
# Get the most recent log stream
streams = call_boto3(
    service_name='logs',
    operation_name='DescribeLogStreams',
    params={
        'logGroupName': '/aws/lambda/ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB',
        'orderBy': 'LastEventTime',
        'descending': True,
        'limit': 1
    }
)
stream_name = streams['logStreams'][0]['logStreamName']

# Read the events
events = call_boto3(
    service_name='logs',
    operation_name='GetLogEvents',
    params={
        'logGroupName': '/aws/lambda/ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB',
        'logStreamName': stream_name,
        'limit': 30
    }
)
```

Look for: `START RequestId: <uuid>` lines, one per invocation. Compare `lastEventTimestamp` to your test submission time to confirm your test ran.

### Step 5: Direct Lambda invoke (for the "I need to know what the deployed code does" test)

```python
# Use a unique marker in the message so you can find it in DDB
import json
payload = json.dumps({
    'httpMethod': 'POST',
    'headers': {'Content-Type': 'application/json'},
    'body': json.dumps({
        'name': 'TRACE TEST',
        'email': 'bigwang@tentrilliontriangles.com',
        'company': 'TenTrillionTriangles',
        'role': 'CEO',
        'useCase': 'Evaluating TPipe',
        'budget': '$10k+/mo',
        'message': 'UNIQUE_MARKER_GOES_HERE'  # change per test
    }),
    'requestContext': {'identity': {'sourceIp': '192.0.2.99'}}
})

invoke = call_boto3(
    service_name='lambda',
    operation_name='Invoke',
    params={
        'FunctionName': 'ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB',
        'LogType': 'Tail',
        'Payload': payload
    }
)
# invoke['Payload'] = API Gateway proxy response (statusCode, body, headers)
# invoke.get('FunctionError') = None if successful
```

The `LogType: Tail` returns the log output in the response, so you can see START/END/REPORT without a second `GetLogEvents` call.

### Step 6: Verify DDB write

```python
# Scan with a marker to confirm your specific submission
scan = call_boto3(
    service_name='dynamodb',
    operation_name='Scan',
    params={
        'TableName': 'Contacts',
        'FilterExpression': 'contains (message, :m)',
        'ExpressionAttributeValues': {':m': {'S': 'UNIQUE_MARKER_GOES_HERE'}}
    }
)
# scan['Count'] should be >= 1
# scan['Items'][0] is your submission
```

If `Count == 0` after a successful Lambda invocation, the rate limit returned 429 before reaching `saveContact`, OR the validation failed. The Lambda log will show the duration is much shorter (~30-50ms) if it returned early.

### Step 7-8: Verify SES was actually called and accepted

```python
# Direct CLI send — proves SES itself works for your identity/payload
direct = call_boto3(
    service_name='sesv2',
    operation_name='SendEmail',
    params={
        'FromEmailAddress': 'contact@tentrilliontriangles.com',
        'Destination': {'ToAddresses': ['contact@tentrilliontriangles.com']},
        'Content': {
            'Simple': {
                'Subject': {'Data': 'CLI DIRECT SES TEST', 'Charset': 'UTF-8'},
                'Body': {'Text': {'Data': 'Direct SES send from CLI to verify SES itself can deliver. If you see this, SES is working.', 'Charset': 'UTF-8'}}
            }
        },
        'ConfigurationSetName': 'ttt-site-contact'
    }
)
# direct['MessageId'] = something like '0100019ec6bef2b2-fa5904f6-...'
# If MessageId is present, SES accepted the send
```

### 9. Check the CloudWatch quota — but don't trust the lag claim

```python
quota = call_boto3(service_name='sesv2', operation_name='GetAccount')
sent_24h = quota['SendQuota']['SentLast24Hours']
# UPDATE 2026-06-25: counter increments immediately on SendEmail accept.
# Use as oracle: if Lambda returns 200 and counter doesn't tick, SES wasn't called.
```

### Step 10: Check actual delivery (the hard one)

Requires:
- MX records on recipient domain (run `dig MX <domain>`)
- OR a working inbox if `SES_TO_EMAIL` is not the same domain

If MX is empty, email is bouncing silently. The bounce notification is sent to the same broken destination and is also lost. The `ttt-site-ses-bounces` SNS topic should be receiving the bounce events — but its subscription is typically `PendingConfirmation`, so the events go nowhere.

## Cross-reference: the full submission via browser

When the user reports "the form doesn't work" but API tests succeed, the problem is in the browser. Use the browser MCP:

```
browser_navigate → https://www.tentrilliontriangles.com/pricing/
browser_console → (function(){...fill form, dispatch submit, observe...})()
```

The ContactForm component (`src/components/pricing/ContactForm.astro` line 366) does:
```javascript
const response = await fetch('https://mgf9b7ggkd.execute-api.us-east-1.amazonaws.com/Prod/contact', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data)
});
```

The form `action="https://www.tentrilliontriangles.com/pricing/"` and `method="get"` are placeholders — the JS submit handler intercepts `e.preventDefault()`. If JS is disabled or the handler fails, the form would do a GET to the same page and lose the data.

## Verifying the deployed code matches source

```bash
# Build artifact lives at:
ls -la infrastructure/.aws-sam/build/ContactHandlerFunction/

# If these match the source, deployed code is current
diff src/lambda/contact-handler/ses.js infrastructure/.aws-sam/build/ContactHandlerFunction/ses.js
diff src/lambda/contact-handler/index.js infrastructure/.aws-sam/build/ContactHandlerFunction/index.js
```

If they differ, the deployed code is older. Rebuild with `sam build && sam deploy`.
