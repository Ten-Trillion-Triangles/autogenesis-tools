# SES Event Destination: CloudWatch Logs Setup and Pitfalls

How to set up a CloudWatch Logs destination for SES configuration set event
publishing, the gotchas that bite you on the way, and the more reliable
alternative when CloudWatch doesn't work.

## The setup (what you want to achieve)

You want every bounce / complaint / delivery / send event for the
`ttt-site-contact` configuration set to land in a CloudWatch Logs log group
where you can query it with Logs Insights. The use case: when a contact form
submission isn't arriving at the inbox, you need the bounce reason in real
time, not after waiting for the (broken) SNS topic to forward it to a
`PendingConfirmation` email subscriber.

## The naive setup (what I did, what didn't work)

### What I did

1. Created IAM role `ttt-site-ses-cloudwatch-logs-role` with:
   - Trust policy: `{"Effect": "Allow", "Principal": {"Service": "ses.amazonaws.com"}, "Action": "sts:AssumeRole", "Condition": {"StringEquals": {"AWS:SourceAccount": "521369004927"}}}`
   - Inline policy: `logs:CreateLogStream`, `logs:PutLogEvents`, `logs:DescribeLogStreams` on the log group ARN
2. Created log group `/aws/ses/ttt-site-contact-events`
3. Added a resource-based policy to the log group allowing `ses.amazonaws.com` to write
4. Called `sesv2:CreateConfigurationSetEventDestination` with:
   ```json
   {
     "ConfigurationSetName": "ttt-site-contact",
     "EventDestinationName": "cloudwatch-bounce-logs",
     "EventDestination": {
       "Enabled": true,
       "MatchingEventTypes": ["BOUNCE", "COMPLAINT", "DELIVERY", "DELIVERY_DELAY", "REJECT", "SEND"],
       "CloudWatchDestination": {
         "DimensionConfigurations": [
           {"DimensionName": "ses:configuration-set", "DimensionValueSource": "MESSAGE_TAG", "DefaultDimensionValue": "ttt-site-contact"}
         ]
       }
     }
   }
   ```

### What happened

The destination was created and verified as enabled. Test sends were
accepted by SES (got `MessageId` back). But **no log streams ever appeared in
the log group** — even after 90+ seconds of wait. The destination was
silently broken.

## The root cause

**The `sesv2:CreateConfigurationSetEventDestination` API for `CloudWatchDestination`
does NOT expose an `IamRoleArn` field.** Compare:

- **v1 SES API** (`ses:CreateConfigurationSetEventDestination`):
  `CloudWatchDestination` had `IamRoleArn` as an explicit field
- **v2 SES API** (`sesv2:CreateConfigurationSetEventDestination`):
  `CloudWatchDestination` only has `DimensionConfigurations` — no `IamRoleArn`

The v2 API removed the role-specification field but does not auto-discover
the role from any other source. The result: SES has no way to know which
role to assume to publish to CloudWatch Logs, so the destination never
publishes anything. The destination is "configured" but functionally dead.

You can confirm this is the issue by:
- Verifying the destination is enabled (`GetConfigurationSetEventDestinations`)
- Confirming the IAM role's trust policy is correct
- Confirming the log group's resource policy allows `ses.amazonaws.com`
- Sending test emails
- Still seeing zero log streams

## The reliable alternative: SNS topic + Lambda subscriber

The existing setup already has an SNS topic (`ttt-site-ses-bounces`) with
the right event destination wired up from SES. The events ARE being
published to SNS — they just have no confirmed subscriber. The fix is to
add a Lambda function as a subscriber to that SNS topic, and have the
Lambda write the event payload to CloudWatch Logs.

### Why this works

- SNS events are durably persisted in the topic (24h-14d retention)
- Lambda subscribes via SNS event source mapping (push or pull, both work)
- Lambda writes the event to CloudWatch Logs with whatever structured format you want
- SNS retries failed Lambda invocations, so you don't lose events
- No role-association footgun because Lambda has its own execution role
- Works the same in v1 and v2 API

### Implementation sketch

```javascript
// Lambda handler
export const handler = async (event) => {
  for (const record of event.Records) {
    const snsMessage = JSON.parse(record.Sns.Message);
    // snsMessage contains the full SES event including:
    // - eventType (Bounce/Complaint/Delivery/etc.)
    // - mail.messageId
    // - bounce.bounceType, bounce.bounceSubType, bounce.bouncedRecipients[].diagnosticCode
    // - complaint.complainedRecipients[].diagnosticCode
    console.log(JSON.stringify({
      timestamp: new Date().toISOString(),
      eventType: snsMessage.eventType,
      messageId: snsMessage.mail?.messageId,
      bounceType: snsMessage.bounce?.bounceType,
      bounceSubType: snsMessage.bounce?.bounceSubType,
      diagnosticCode: snsMessage.bounce?.bouncedRecipients?.[0]?.diagnosticCode,
      recipient: snsMessage.bounce?.bouncedRecipients?.[0]?.emailAddress,
      smtpResponse: snsMessage.delivery?.smtpResponse,
      // ...etc, structured for easy Logs Insights queries
    }));
  }
};
```

Add a CloudWatch Logs Insights saved query for fast lookup:

```
fields @timestamp, eventType, messageId, bounceType, bounceSubType, diagnosticCode, recipient
| filter eventType = "Bounce"
| sort @timestamp desc
| limit 20
```

### SNS subscription confirmation gotcha

If you instead add an **email** subscriber to the SNS topic, the user has to
click the confirmation link in the AWS confirmation email. If that email
gets filtered (e.g., by the same GoDaddy / M365 setup that's filtering the
contact form emails), the subscription stays `PendingConfirmation` and
events go nowhere. This is the most common failure mode for the
email-subscriber approach.

## When the CloudWatch approach IS fine

- You're in a non-production environment where you can iterate on the role
  configuration freely
- You're using the v1 SES API (which has `IamRoleArn`) — but ttt-site is on
  v2 via `sesv2:*` calls in SAM
- You have a separate, well-known working CloudWatch destination set up
  that you can model after (and confirm the v2 API behavior you're seeing
  isn't unique to your config)

For ttt-site production: **skip the CloudWatch destination, go straight to
SNS + Lambda.** It's the path that's already wired up and works.

## Cleanup: removing the broken CloudWatch destination

If you created a CloudWatch destination that isn't publishing, remove it so
it doesn't add to the destination count when you debug later:

```python
call_boto3(
    service_name='sesv2',
    operation_name='DeleteConfigurationSetEventDestination',
    params={
        'ConfigurationSetName': 'ttt-site-contact',
        'EventDestinationName': 'cloudwatch-bounce-logs'
    }
)
```

The IAM role and log group can be left in place — they're cheap (zero cost
when unused) and might be useful if you revisit this approach.
