#!/usr/bin/env bash
# ttt-site-backend-debugging — quick diagnostic for the live infrastructure
# Run this from anywhere; uses AWS CLI with the configured profile.
#
# What it checks (in order):
#   1. Lambda function exists and env vars are set
#   2. Most recent Lambda log streams (to see if it's being invoked)
#   3. DynamoDB has recent submissions
#   4. SES identities are verified and production access is on
#   5. SNS bounce topic has a confirmed subscription
#   6. Route 53 MX records exist (the most common reason emails don't arrive)
#
# Output is pass/fail per check with the actual values.
# Exits 0 if all critical checks pass, 1 otherwise.

set -euo pipefail

DOMAIN="${DOMAIN:-tentrilliontriangles.com}"
APEX_ZONE_ID="${APEX_ZONE_ID:-Z0266992GQSG7W4H336}"
LAMBDA_FN="${LAMBDA_FN:-ttt-site-be-v5-ContactHandlerFunction-I9n66HnFyJBB}"
DDB_TABLE="${DDB_TABLE:-Contacts}"
SNS_TOPIC="${SNS_TOPIC:-arn:aws:sns:us-east-1:521369004927:ttt-site-ses-bounces}"
LOG_GROUP="/aws/lambda/${LAMBDA_FN}"

pass=0
fail=0

check() {
    local label="$1"
    local result="$2"
    if [ "$result" = "OK" ]; then
        echo "  PASS  $label"
        pass=$((pass + 1))
    else
        echo "  FAIL  $label  ($result)"
        fail=$((fail + 1))
    fi
}

echo "=== ttt-site backend diagnostic (domain: $DOMAIN) ==="
echo

# 1. Lambda
echo "[1] Lambda function + env"
LAMBDA_JSON=$(aws lambda get-function --function-name "$LAMBDA_FN" --output json 2>/dev/null || echo "{}")
if [ "$(echo "$LAMBDA_JSON" | jq -r '.Configuration // empty' 2>/dev/null)" = "" ]; then
    check "lambda exists" "missing"
else
    check "lambda exists" "OK"
    SES_TO=$(echo "$LAMBDA_JSON" | jq -r '.Configuration.Environment.Variables.SES_TO_EMAIL // "NOT SET"')
    SES_FROM=$(echo "$LAMBDA_JSON" | jq -r '.Configuration.Environment.Variables.SES_FROM_EMAIL // "NOT SET"')
    SES_CONFIG=$(echo "$LAMBDA_JSON" | jq -r '.Configuration.Environment.Variables.SES_CONFIG_SET // "NOT SET"')
    ALLOWED=$(echo "$LAMBDA_JSON" | jq -r '.Configuration.Environment.Variables.ALLOWED_ORIGIN // "NOT SET"')
    if [ "$SES_TO" = "NOT SET" ] || [ "$SES_FROM" = "NOT SET" ]; then
        check "lambda env SES vars" "missing SES_TO_EMAIL or SES_FROM_EMAIL"
    else
        check "lambda env SES vars (TO=$SES_TO FROM=$SES_FROM)" "OK"
    fi
    if [ "$SES_CONFIG" = "ttt-site-contact" ]; then
        check "lambda env SES_CONFIG_SET" "OK"
    else
        check "lambda env SES_CONFIG_SET" "expected 'ttt-site-contact', got '$SES_CONFIG'"
    fi
fi
echo

# 2. Lambda log streams
echo "[2] Lambda log activity (last 1 hour)"
LAST_EVENT=$(aws logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --order-by LastEventTime --descending \
    --max-items 1 \
    --output json 2>/dev/null | jq -r '.logStreams[0].lastEventTimestamp // "none"')
if [ "$LAST_EVENT" = "none" ]; then
    check "lambda has log streams" "no streams in last hour"
else
    NOW=$(date +%s)000
    AGE=$(( (NOW - LAST_EVENT) / 1000 / 60 ))  # minutes
    if [ "$AGE" -lt 60 ]; then
        check "lambda has log streams" "OK"
        echo "       (last activity ${AGE}m ago)"
    else
        check "lambda has log streams" "last activity was ${AGE}m ago — Lambda may be idle or broken"
    fi
fi
echo

# 3. DDB
echo "[3] DynamoDB — recent submissions"
RECENT=$(aws dynamodb scan \
    --table-name "$DDB_TABLE" \
    --projection-expression "submittedAt,email,SK" \
    --output json 2>/dev/null | jq -r '.Items | length')
if [ -z "$RECENT" ] || [ "$RECENT" = "0" ]; then
    check "DDB has submissions" "table is empty or scan failed"
else
    LATEST=$(aws dynamodb scan \
        --table-name "$DDB_TABLE" \
        --output json 2>/dev/null | jq -r '.Items | max_by(.submittedAt.S) | .submittedAt.S')
    check "DDB has submissions ($RECENT total, latest $LATEST)" "OK"
fi
echo

# 4. SES
echo "[4] SES — identity, production access, sending enabled"
SES_JSON=$(aws sesv2 get-account --output json 2>/dev/null)
PROD=$(echo "$SES_JSON" | jq -r '.ProductionAccessEnabled')
ENFORCE=$(echo "$SES_JSON" | jq -r '.EnforcementStatus')
SENDING=$(echo "$SES_JSON" | jq -r '.SendingEnabled')
SENT_24H=$(echo "$SES_JSON" | jq -r '.SendQuota.SentLast24Hours')
if [ "$PROD" = "true" ] && [ "$ENFORCE" = "HEALTHY" ] && [ "$SENDING" = "true" ]; then
    check "SES production + sending enabled" "OK (sent in last 24h: $SENT_24H)"
else
    check "SES production + sending enabled" "prod=$PROD enforce=$ENFORCE sending=$SENDING"
fi

# Check identity
DOMAIN_STATUS=$(aws sesv2 list-email-identities --output json 2>/dev/null | jq -r --arg d "$DOMAIN" '.EmailIdentities[] | select(.IdentityName == $d) | .VerificationStatus')
if [ "$DOMAIN_STATUS" = "SUCCESS" ]; then
    check "SES domain identity verified ($DOMAIN)" "OK"
else
    check "SES domain identity verified" "status=$DOMAIN_STATUS"
fi
echo

# 5. SNS
echo "[5] SNS — bounce event topic subscriptions"
SUB_STATE=$(aws sns list-subscriptions-by-topic --topic-arn "$SNS_TOPIC" --output json 2>/dev/null | jq -r '.Subscriptions[0].SubscriptionArn // "no subscriptions"')
if [ "$SUB_STATE" = "PendingConfirmation" ]; then
    check "SNS subscription state" "PendingConfirmation — events go nowhere. Click AWS confirmation link or replace with CloudWatch Logs destination"
elif [[ "$SUB_STATE" == "arn:aws:sns:"* ]]; then
    check "SNS subscription state" "OK (confirmed)"
else
    check "SNS subscription state" "$SUB_STATE"
fi
echo

# 6. Route 53 MX
echo "[6] Route 53 — MX records (the most common reason emails don't arrive)"
MX_COUNT=$(aws route53 list-resource-record-sets --hosted-zone-id "$APEX_ZONE_ID" --output json 2>/dev/null | jq -r '[.ResourceRecordSets[] | select(.Type == "MX")] | length')
if [ "$MX_COUNT" = "0" ] || [ -z "$MX_COUNT" ]; then
    check "MX records exist" "MISSING — domain cannot receive mail. Either add MX records or change SES_TO_EMAIL to a real inbox."
else
    check "MX records exist" "OK ($MX_COUNT records)"
    aws route53 list-resource-record-sets --hosted-zone-id "$APEX_ZONE_ID" --output json 2>/dev/null | \
        jq -r '.ResourceRecordSets[] | select(.Type == "MX") | "       \(.Name) MX \(.TTL // "default") \(.ResourceRecords[] | .Value)"'
fi
echo

# Summary
echo "=== Summary: $pass passed, $fail failed ==="
if [ "$fail" -gt 0 ]; then
    echo "FIX the failed checks before claiming the contact form is working end-to-end."
    exit 1
fi
echo "All critical checks pass. If emails still don't arrive, check the inbox's spam folder and verify the recipient domain's MX records with: dig MX $DOMAIN"
exit 0
