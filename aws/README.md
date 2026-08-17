# AWS Resource Setup Reference

This folder documents the AWS resources and IAM relationships used by the Wistia Video Analytics pipeline.

The files are intended to:

- document the deployed AWS architecture
- preserve the IAM policies used by the project
- provide reference commands for rebuilding resources after teardown
- explain how the AWS services interact

Secrets are never stored in this folder.

---

## Resource Flow

The completed AWS data path is:

```text
Amazon EventBridge
Daily scheduled rule
        ↓
AWS Lambda
Python Wistia ingestion
        ↓
Wistia Stats API
        ↓
Pagination + retries
        ↓
Incremental filtering
        ↓
Amazon S3
raw JSON + run manifest + checkpoint
        ↓
Lambda calls glue:StartJobRun
        ↓
AWS Glue
PySpark transformation
        ↓
Amazon S3
curated Parquet
        ↓
AWS Glue Data Catalog
        ↓
Amazon Athena
SQL analytics
```

A separate development-validation path runs in GitHub:

```text
GitHub push / pull request
        ↓
GitHub Actions
        ↓
Python syntax checks
        ↓
pytest unit tests
        ↓
tracked .env safety check
```

GitHub Actions validates repository code. It is not part of the daily Wistia data-processing path.

---

# AWS Region

```text
us-east-2
```

The project uses the personal AWS CLI profile:

```text
retail-poc
```

---

# Amazon S3

Bucket:

```text
wistia-video-analytics-dea
```

Main logical prefixes:

```text
raw/
state/
scripts/
curated/
athena-results/
```

These are S3 prefixes displayed as folders, not separate buckets.

## raw/

Stores Wistia API responses by ingestion run.

Example structure:

```text
raw/
└── run_date=YYYY-MM-DD/
    └── run_id=<UTC-run-id>/
        ├── media_metadata.json
        ├── media_stats/
        ├── events/
        └── run_manifest.json
```

Raw data is preserved before transformation.

## state/

Contains the incremental-ingestion checkpoint:

```text
state/checkpoint.json
```

The checkpoint tracks the latest successfully processed Wistia event timestamp for each media ID.

The ingestion process compares incoming event timestamps with this persisted state so previously processed records are not blindly saved again.

The checkpoint is updated only after a successful ingestion run.

## scripts/

Stores the PySpark transformation used by AWS Glue:

```text
scripts/transform_wistia.py
```

## curated/

Contains the dimensional analytics model written by AWS Glue as Snappy-compressed Parquet:

```text
curated/
├── dim_media/
├── dim_visitor/
└── fact_media_engagement/
```

## athena-results/

Stores Athena-generated query-result files.

These files are query outputs and are separate from the curated dimensional datasets.

---

# AWS Lambda

Function:

```text
wistia-video-analytics-ingestion
```

Runtime:

```text
Python 3.13
```

Handler:

```text
wistia_ingest.lambda_handler
```

Main responsibilities:

1. Authenticate to the Wistia API.
2. Retrieve media metadata.
3. Retrieve current media statistics.
4. Retrieve paginated engagement events.
5. Retry temporary HTTP failures.
6. Compare event timestamps with the persisted checkpoint.
7. Save new raw data to S3.
8. Write a run manifest.
9. Update the checkpoint after successful ingestion.
10. Start the AWS Glue transformation job.

The local Python entry point runs ingestion only.

The Lambda-specific handler runs ingestion and, after successful ingestion, starts Glue.

This avoids unexpectedly launching a Glue job during local development.

---

# Lambda Environment Variables

The deployed Lambda uses runtime environment variables including:

```text
WISTIA_API_TOKEN
S3_BUCKET
GLUE_JOB_NAME
```

Current non-secret values:

```text
S3_BUCKET=wistia-video-analytics-dea
GLUE_JOB_NAME=wistia-video-analytics-transform
```

The Wistia token is intentionally not stored in Git.

---

# Lambda IAM Role

Role:

```text
wistia-video-analytics-lambda-role
```

Trust principal:

```text
lambda.amazonaws.com
```

## AWS-Managed Policy

```text
AWSLambdaBasicExecutionRole
```

Purpose:

```text
CloudWatch logging
```

## Project S3 Policy

```text
WistiaVideoAnalyticsS3Access
```

Purpose:

```text
s3:GetObject
s3:PutObject
```

against the project bucket objects.

Policy file:

```text
aws/iam/lambda-s3-access.json
```

## Glue Start Policy

```text
WistiaVideoAnalyticsGlueStartJob
```

Purpose:

```text
glue:StartJobRun
```

Resource is limited to:

```text
arn:aws:glue:us-east-2:272987324508:job/wistia-video-analytics-transform
```

Policy file:

```text
aws/iam/lambda-glue-start-job.json
```

The Lambda role does not receive broad `glue:*` access.

It can start only the transformation job used by this project.

---

# Amazon EventBridge

Scheduled rule:

```text
wistia-video-analytics-schedule
```

Target:

```text
wistia-video-analytics-ingestion
```

The schedule was initially tested using:

```text
rate(5 minutes)
```

After scheduled invocation was verified, the rule was changed to:

```text
rate(1 day)
```

EventBridge does not use a separate execution role in this implementation.

Instead:

1. Lambda grants `events.amazonaws.com` permission to invoke the function.
2. The Lambda function is registered as the EventBridge rule target.

---

# AWS Glue

Glue job:

```text
wistia-video-analytics-transform
```

Script:

```text
s3://wistia-video-analytics-dea/scripts/transform_wistia.py
```

Configuration:

```text
Glue version: 5.1
Worker type: G.1X
Workers: 2
Execution class: STANDARD
Timeout: 10 minutes
Retries: 0
```

The Glue job reads accumulated raw Wistia JSON from S3 and rebuilds the small curated dimensional datasets.

Data flow:

```text
S3 raw JSON
    ↓
PySpark
    ↓
deduplicate + transform + join
    ↓
S3 curated Parquet
```

The transformation intentionally deduplicates engagement records using:

```text
event_key
```

The validated source load contained:

```text
1,199 raw event rows
1,197 distinct event_key values
```

Therefore the final engagement fact table contains:

```text
1,197 unique events
```

---

# Glue IAM Role

Role:

```text
AWSGlueServiceRole-wistia-video-analytics
```

Trust principal:

```text
glue.amazonaws.com
```

## AWS-Managed Policy

```text
AWSGlueServiceRole
```

## Project S3 Policy

```text
WistiaVideoAnalyticsS3Access
```

Permissions:

```text
s3:ListBucket
s3:GetObject
s3:PutObject
s3:DeleteObject
```

Policy file:

```text
aws/iam/glue-s3-access.json
```

`DeleteObject` is required because the curated Parquet output is rebuilt using overwrite mode.

---

# Lambda to Glue Automation

The Lambda function starts Glue only after ingestion completes successfully.

Conceptually:

```text
main()
    ↓
Wistia ingestion
    ↓
raw data saved
    ↓
run manifest saved
    ↓
checkpoint saved
    ↓
main() returns successfully
    ↓
lambda_handler()
    ↓
glue:StartJobRun
```

The Glue request is asynchronous.

Lambda receives a Glue:

```text
JobRunId
```

after AWS accepts the job request.

Lambda does not wait for the Glue transformation to finish.

This means:

```text
Lambda succeeded
```

proves that ingestion completed and the Glue job was successfully submitted.

The final transformation result is validated separately through the Glue job run status.

An end-to-end AWS test confirmed:

```text
Lambda ingestion
        ↓
Glue StartJobRun
        ↓
Glue job SUCCEEDED
```

The automatically initiated Glue run completed successfully in 81 seconds.

---

# Glue Data Catalog

Database:

```text
wistia_video_analytics
```

Tables:

```text
dim_media
dim_visitor
fact_media_engagement
```

The tables point to:

```text
s3://wistia-video-analytics-dea/curated/dim_media
s3://wistia-video-analytics-dea/curated/dim_visitor
s3://wistia-video-analytics-dea/curated/fact_media_engagement
```

The Glue Data Catalog stores:

```text
table names
column definitions
data types
S3 locations
```

It does not store another copy of the data.

The actual records remain in S3 Parquet files.

---

# Amazon Athena

Athena queries the curated S3 data using the Glue Data Catalog definitions.

Conceptually:

```text
Athena SQL
    ↓
Glue Data Catalog
    ↓
S3 Parquet
```

Athena does not require the data to be loaded into a traditional database first.

Table definitions are version-controlled in:

```text
sql/athena_setup.sql
```

Validation and analytics SQL is stored in:

```text
sql/validation_queries.sql
```

Validated row counts:

```text
dim_media = 2
dim_visitor = 1,122
fact_media_engagement = 1,197
```

---

# CloudWatch

Lambda logs are written under:

```text
/aws/lambda/wistia-video-analytics-ingestion
```

The logs provide evidence for:

```text
ingestion start/completion
media-level event counts
incremental behavior
S3 locations
checkpoint updates
Glue job submission
Glue JobRunId
errors and exceptions
```

AWS Glue also provides job-run status and execution logs for the transformation layer.

---

# IAM Pattern Used in This Project

For AWS services that need access to another AWS resource:

```text
1. Define who can assume the role
2. Create the IAM role
3. Attach the AWS-managed service policy
4. Add project-specific permissions
5. Limit resources when practical
6. Assign the role to the service
7. Verify the deployed permissions
```

## Trust Policy

Answers:

> Who can assume this role?

Examples:

```text
lambda.amazonaws.com
glue.amazonaws.com
```

## AWS-Managed Service Policy

Provides standard permissions needed by the AWS service.

Used here:

```text
AWSLambdaBasicExecutionRole
AWSGlueServiceRole
```

## Project-Specific Policies

Grant only the project access needed beyond the standard service role.

Examples:

```text
Lambda
→ project S3 objects
→ start one specific Glue job

Glue
→ project S3 bucket and objects
```

---

# Security

The Wistia API token must never be stored in this folder or committed to Git.

The committed AWS reference files contain only:

```text
resource names
IAM policy definitions
non-secret AWS CLI examples
architecture documentation
```

Visitor-level source data may contain personally identifiable information.

The curated model does not retain unnecessary identity fields such as visitor name or email.

The source visitor key is hashed before becoming the curated `visitor_id`.

Real visitor IP addresses should not be displayed in public screenshots or documentation.

---

# Why These Files Are Kept

The live AWS resources can eventually be removed to prevent ongoing project costs.

Keeping the policy JSON and setup references in Git preserves:

- AWS resource names
- IAM trust relationships
- least-privilege permissions
- service connections
- deployment configuration
- the intended scheduling model
- the transformation configuration
- the structure needed to understand or recreate the project later

This provides an architecture record even after the live AWS environment has been torn down.
