#!/usr/bin/env bash

set -euo pipefail

PROFILE="retail-poc"
REGION="us-east-2"
EXPECTED_ACCOUNT="272987324508"

BUCKET="wistia-video-analytics-dea"

EVENT_RULE="wistia-video-analytics-schedule"

LAMBDA_FUNCTION="wistia-video-analytics-ingestion"
LAMBDA_ROLE="wistia-video-analytics-lambda-role"
LAMBDA_LOG_GROUP="/aws/lambda/wistia-video-analytics-ingestion"

GLUE_JOB="wistia-video-analytics-transform"
GLUE_ROLE="AWSGlueServiceRole-wistia-video-analytics"
GLUE_DATABASE="wistia_video_analytics"

echo
echo "========================================"
echo " Wistia Video Analytics AWS Teardown"
echo "========================================"
echo

ACCOUNT_ID=$(aws sts get-caller-identity \
  --profile "$PROFILE" \
  --region "$REGION" \
  --query 'Account' \
  --output text)

echo "AWS account: $ACCOUNT_ID"
echo "AWS region:  $REGION"
echo "AWS profile: $PROFILE"
echo

if [[ "$ACCOUNT_ID" != "$EXPECTED_ACCOUNT" ]]; then
  echo "ERROR: Expected AWS account $EXPECTED_ACCOUNT."
  echo "No resources were deleted."
  exit 1
fi

echo "Checking S3 bucket versioning..."

if aws s3api head-bucket \
  --bucket "$BUCKET" \
  --profile "$PROFILE" \
  --region "$REGION" \
  2>/dev/null
then
  VERSIONING=$(aws s3api get-bucket-versioning \
    --bucket "$BUCKET" \
    --query 'Status' \
    --output text \
    --profile "$PROFILE" \
    --region "$REGION")

  if [[ "$VERSIONING" == "Enabled" || "$VERSIONING" == "Suspended" ]]; then
    echo
    echo "ERROR: Bucket versioning is $VERSIONING."
    echo "This script does not automatically delete object versions."
    echo "No resources were deleted."
    exit 1
  fi
fi

echo
echo "Resources targeted for deletion:"
echo
echo "EventBridge:"
echo "  $EVENT_RULE"
echo
echo "Lambda:"
echo "  $LAMBDA_FUNCTION"
echo "  $LAMBDA_LOG_GROUP"
echo
echo "Glue:"
echo "  $GLUE_JOB"
echo "  $GLUE_DATABASE"
echo
echo "IAM:"
echo "  $LAMBDA_ROLE"
echo "  $GLUE_ROLE"
echo
echo "S3:"
echo "  s3://$BUCKET"
echo

read -r -p "Type DELETE-WISTIA to continue: " CONFIRM

if [[ "$CONFIRM" != "DELETE-WISTIA" ]]; then
  echo "Teardown cancelled."
  exit 0
fi

echo
echo "1. Removing EventBridge schedule..."

if aws events describe-rule \
  --name "$EVENT_RULE" \
  --profile "$PROFILE" \
  --region "$REGION" \
  >/dev/null 2>&1
then
  TARGET_IDS=$(aws events list-targets-by-rule \
    --rule "$EVENT_RULE" \
    --query 'Targets[*].Id' \
    --output text \
    --profile "$PROFILE" \
    --region "$REGION")

  if [[ -n "$TARGET_IDS" ]]; then
    aws events remove-targets \
      --rule "$EVENT_RULE" \
      --ids $TARGET_IDS \
      --profile "$PROFILE" \
      --region "$REGION"
  fi

  aws events delete-rule \
    --name "$EVENT_RULE" \
    --profile "$PROFILE" \
    --region "$REGION"

  echo "EventBridge rule deleted."
else
  echo "EventBridge rule not found."
fi

echo
echo "2. Deleting Lambda function..."

if aws lambda get-function \
  --function-name "$LAMBDA_FUNCTION" \
  --profile "$PROFILE" \
  --region "$REGION" \
  >/dev/null 2>&1
then
  aws lambda delete-function \
    --function-name "$LAMBDA_FUNCTION" \
    --profile "$PROFILE" \
    --region "$REGION"

  echo "Lambda function deleted."
else
  echo "Lambda function not found."
fi

echo
echo "3. Deleting Lambda CloudWatch log group..."

if aws logs describe-log-groups \
  --log-group-name-prefix "$LAMBDA_LOG_GROUP" \
  --query "logGroups[?logGroupName=='$LAMBDA_LOG_GROUP'].logGroupName" \
  --output text \
  --profile "$PROFILE" \
  --region "$REGION" \
  | grep -q .
then
  aws logs delete-log-group \
    --log-group-name "$LAMBDA_LOG_GROUP" \
    --profile "$PROFILE" \
    --region "$REGION"

  echo "Lambda log group deleted."
else
  echo "Lambda log group not found."
fi

echo
echo "4. Deleting Glue job..."

if aws glue get-job \
  --job-name "$GLUE_JOB" \
  --profile "$PROFILE" \
  --region "$REGION" \
  >/dev/null 2>&1
then
  aws glue delete-job \
    --job-name "$GLUE_JOB" \
    --profile "$PROFILE" \
    --region "$REGION"

  echo "Glue job deleted."
else
  echo "Glue job not found."
fi

echo
echo "5. Deleting Glue Data Catalog tables and database..."

if aws glue get-database \
  --name "$GLUE_DATABASE" \
  --profile "$PROFILE" \
  --region "$REGION" \
  >/dev/null 2>&1
then
  TABLES=$(aws glue get-tables \
    --database-name "$GLUE_DATABASE" \
    --query 'TableList[*].Name' \
    --output text \
    --profile "$PROFILE" \
    --region "$REGION")

  for TABLE in $TABLES; do
    echo "Deleting table: $TABLE"

    aws glue delete-table \
      --database-name "$GLUE_DATABASE" \
      --name "$TABLE" \
      --profile "$PROFILE" \
      --region "$REGION"
  done

  aws glue delete-database \
    --name "$GLUE_DATABASE" \
    --profile "$PROFILE" \
    --region "$REGION"

  echo "Glue Data Catalog database deleted."
else
  echo "Glue database not found."
fi

echo
echo "6. Emptying and deleting S3 bucket..."

if aws s3api head-bucket \
  --bucket "$BUCKET" \
  --profile "$PROFILE" \
  --region "$REGION" \
  2>/dev/null
then
  aws s3 rm \
    "s3://$BUCKET" \
    --recursive \
    --profile "$PROFILE" \
    --region "$REGION"

  aws s3api delete-bucket \
    --bucket "$BUCKET" \
    --profile "$PROFILE" \
    --region "$REGION"

  echo "S3 bucket deleted."
else
  echo "S3 bucket not found."
fi

echo
echo "7. Removing Lambda IAM policies and role..."

if aws iam get-role \
  --role-name "$LAMBDA_ROLE" \
  --profile "$PROFILE" \
  >/dev/null 2>&1
then
  aws iam delete-role-policy \
    --role-name "$LAMBDA_ROLE" \
    --policy-name WistiaVideoAnalyticsS3Access \
    --profile "$PROFILE" \
    2>/dev/null || true

  aws iam delete-role-policy \
    --role-name "$LAMBDA_ROLE" \
    --policy-name WistiaVideoAnalyticsGlueStartJob \
    --profile "$PROFILE" \
    2>/dev/null || true

  aws iam detach-role-policy \
    --role-name "$LAMBDA_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    --profile "$PROFILE" \
    2>/dev/null || true

  aws iam delete-role \
    --role-name "$LAMBDA_ROLE" \
    --profile "$PROFILE"

  echo "Lambda IAM role deleted."
else
  echo "Lambda IAM role not found."
fi

echo
echo "8. Removing Glue IAM policies and role..."

if aws iam get-role \
  --role-name "$GLUE_ROLE" \
  --profile "$PROFILE" \
  >/dev/null 2>&1
then
  aws iam delete-role-policy \
    --role-name "$GLUE_ROLE" \
    --policy-name WistiaVideoAnalyticsS3Access \
    --profile "$PROFILE" \
    2>/dev/null || true

  aws iam detach-role-policy \
    --role-name "$GLUE_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole \
    --profile "$PROFILE" \
    2>/dev/null || true

  aws iam delete-role \
    --role-name "$GLUE_ROLE" \
    --profile "$PROFILE"

  echo "Glue IAM role deleted."
else
  echo "Glue IAM role not found."
fi

echo
echo "========================================"
echo " Wistia AWS teardown complete"
echo "========================================"
