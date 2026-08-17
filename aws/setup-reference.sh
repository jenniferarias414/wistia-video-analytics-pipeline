#!/usr/bin/env bash

set -euo pipefail

PROFILE="retail-poc"
REGION="us-east-2"
ACCOUNT_ID="272987324508"

BUCKET="wistia-video-analytics-dea"

LAMBDA_FUNCTION="wistia-video-analytics-ingestion"
LAMBDA_ROLE="wistia-video-analytics-lambda-role"

GLUE_JOB="wistia-video-analytics-transform"
GLUE_ROLE="AWSGlueServiceRole-wistia-video-analytics"

EVENT_RULE="wistia-video-analytics-schedule"

GLUE_DATABASE="wistia_video_analytics"

LAMBDA_ZIP="/tmp/wistia-lambda.zip"

if [[ -z "${WISTIA_API_TOKEN:-}" ]]; then
  echo "WISTIA_API_TOKEN must be supplied as an environment variable."
  echo "Do not store the token in this script."
  exit 1
fi

echo "Verifying AWS identity..."

aws sts get-caller-identity \
  --profile "$PROFILE" \
  --region "$REGION"

echo "Creating S3 bucket..."

aws s3api create-bucket \
  --bucket "$BUCKET" \
  --create-bucket-configuration LocationConstraint="$REGION" \
  --profile "$PROFILE" \
  --region "$REGION"

echo "Creating Lambda execution role..."

aws iam create-role \
  --role-name "$LAMBDA_ROLE" \
  --assume-role-policy-document file://aws/iam/lambda-trust-policy.json \
  --profile "$PROFILE"

aws iam attach-role-policy \
  --role-name "$LAMBDA_ROLE" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
  --profile "$PROFILE"

aws iam put-role-policy \
  --role-name "$LAMBDA_ROLE" \
  --policy-name WistiaVideoAnalyticsS3Access \
  --policy-document file://aws/iam/lambda-s3-access.json \
  --profile "$PROFILE"

aws iam put-role-policy \
  --role-name "$LAMBDA_ROLE" \
  --policy-name WistiaVideoAnalyticsGlueStartJob \
  --policy-document file://aws/iam/lambda-glue-start-job.json \
  --profile "$PROFILE"

echo "Creating Glue execution role..."

aws iam create-role \
  --role-name "$GLUE_ROLE" \
  --assume-role-policy-document file://aws/iam/glue-trust-policy.json \
  --profile "$PROFILE"

aws iam attach-role-policy \
  --role-name "$GLUE_ROLE" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole \
  --profile "$PROFILE"

aws iam put-role-policy \
  --role-name "$GLUE_ROLE" \
  --policy-name WistiaVideoAnalyticsS3Access \
  --policy-document file://aws/iam/glue-s3-access.json \
  --profile "$PROFILE"

echo "Upload the current PySpark transformation script..."

aws s3 cp \
  src/transformation/transform_wistia.py \
  "s3://$BUCKET/scripts/transform_wistia.py" \
  --profile "$PROFILE" \
  --region "$REGION"

echo "Creating Glue transformation job..."

aws glue create-job \
  --name "$GLUE_JOB" \
  --description "Transform raw Wistia analytics into curated dimensional Parquet datasets" \
  --role "arn:aws:iam::$ACCOUNT_ID:role/$GLUE_ROLE" \
  --command "{\"Name\":\"glueetl\",\"ScriptLocation\":\"s3://$BUCKET/scripts/transform_wistia.py\",\"PythonVersion\":\"3\"}" \
  --default-arguments "{\"--S3_BUCKET\":\"$BUCKET\",\"--job-language\":\"python\"}" \
  --glue-version "5.1" \
  --worker-type "G.1X" \
  --number-of-workers 2 \
  --timeout 10 \
  --max-retries 0 \
  --execution-class STANDARD \
  --profile "$PROFILE" \
  --region "$REGION"

echo "Waiting briefly for IAM role propagation..."

sleep 10

if [[ ! -f "$LAMBDA_ZIP" ]]; then
  echo "Lambda deployment ZIP not found at:"
  echo "$LAMBDA_ZIP"
  echo "Build the deployment package before creating Lambda."
  exit 1
fi

echo "Creating Lambda function..."

# aws lambda create-function \
#   --function-name "$LAMBDA_FUNCTION" \
#   --runtime python3.13 \
#   --architectures x86_64 \
#   --handler wistia_ingest.lambda_handler \
#   --role "arn:aws:iam::$ACCOUNT_ID:role/$LAMBDA_ROLE" \
#   --zip-file "fileb://$LAMBDA_ZIP" \
#   --timeout 120 \
#   --memory-size 256 \
#   --environment "Variables={WISTIA_API_TOKEN=$WISTIA_API_TOKEN,S3_BUCKET=$BUCKET,GLUE_JOB_NAME=$GLUE_JOB}" \
#   --profile "$PROFILE" \
#   --region "$REGION"

LAMBDA_ENV_FILE=$(mktemp /tmp/wistia-lambda-env.XXXXXX.json)

trap 'rm -f "$LAMBDA_ENV_FILE"' EXIT

python - "$LAMBDA_ENV_FILE" "$WISTIA_API_TOKEN" "$BUCKET" "$GLUE_JOB" <<'PY'
import json
import sys

output_path, token, bucket, glue_job = sys.argv[1:]

with open(output_path, "w") as f:
    json.dump(
        {
            "Variables": {
                "WISTIA_API_TOKEN": token,
                "S3_BUCKET": bucket,
                "GLUE_JOB_NAME": glue_job,
            }
        },
        f,
    )
PY

aws lambda create-function \
  --function-name "$LAMBDA_FUNCTION" \
  --runtime python3.13 \
  --architectures x86_64 \
  --handler wistia_ingest.lambda_handler \
  --role "arn:aws:iam::$ACCOUNT_ID:role/$LAMBDA_ROLE" \
  --zip-file "fileb://$LAMBDA_ZIP" \
  --timeout 120 \
  --memory-size 256 \
  --environment "file://$LAMBDA_ENV_FILE" \
  --profile "$PROFILE" \
  --region "$REGION"

echo "Creating EventBridge scheduled rule..."

aws events put-rule \
  --name "$EVENT_RULE" \
  --schedule-expression "rate(1 day)" \
  --state ENABLED \
  --profile "$PROFILE" \
  --region "$REGION"

EVENT_RULE_ARN=$(aws events describe-rule \
  --name "$EVENT_RULE" \
  --query 'Arn' \
  --output text \
  --profile "$PROFILE" \
  --region "$REGION")

LAMBDA_ARN=$(aws lambda get-function \
  --function-name "$LAMBDA_FUNCTION" \
  --query 'Configuration.FunctionArn' \
  --output text \
  --profile "$PROFILE" \
  --region "$REGION")

aws lambda add-permission \
  --function-name "$LAMBDA_FUNCTION" \
  --statement-id AllowEventBridgeScheduledIngestion \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "$EVENT_RULE_ARN" \
  --profile "$PROFILE" \
  --region "$REGION"

aws events put-targets \
  --rule "$EVENT_RULE" \
  --targets "Id"="1","Arn"="$LAMBDA_ARN" \
  --profile "$PROFILE" \
  --region "$REGION"

echo "Creating Glue Data Catalog database..."

aws glue create-database \
  --database-input "{\"Name\":\"$GLUE_DATABASE\",\"Description\":\"Curated Wistia video analytics datasets\"}" \
  --profile "$PROFILE" \
  --region "$REGION"

echo
echo "AWS resource setup complete."
echo
echo "Next steps:"
echo "1. Run the Athena DDL in sql/athena_setup.sql."
echo "2. Validate the tables using sql/validation_queries.sql."
echo "3. Confirm the EventBridge rule is enabled."
echo "4. Confirm Lambda can start the Glue job."
echo
echo "This script is a rebuild reference and is not intended to be"
echo "rerun blindly against an environment where these resources already exist."
