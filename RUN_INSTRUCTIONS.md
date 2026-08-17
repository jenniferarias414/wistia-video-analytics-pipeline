# Wistia Video Analytics Pipeline - Run Instructions

This document explains how to set up, validate, run, and troubleshoot the Wistia Video Analytics pipeline.

For architecture and design decisions, see:

```text
architecture/architecture-overview.md
```

For AWS resource details and rebuild references, see:

```text
aws/README.md
aws/setup-reference.sh
```

---

# Pipeline Overview

The production data flow is:

```text
Amazon EventBridge
        ↓
AWS Lambda
Python Wistia ingestion
        ↓
Wistia Stats API
        ↓
Amazon S3 raw JSON + checkpoint
        ↓
Lambda starts AWS Glue
        ↓
Glue PySpark transformation
        ↓
Amazon S3 curated Parquet
        ↓
AWS Glue Data Catalog
        ↓
Amazon Athena
```

Development validation runs separately:

```text
GitHub push / pull request
        ↓
GitHub Actions
        ↓
syntax checks
pytest
tracked .env check
```

---

# Prerequisites

Local development requires:

```text
Python 3.13
AWS CLI
Git
AWS credentials/profile
Wistia API token
```

AWS region used by this project:

```text
us-east-2
```

AWS CLI profile used during development:

```text
retail-poc
```

Project S3 bucket:

```text
wistia-video-analytics-dea
```

---

# 1. Clone and Enter the Repository

Example:

```bash
git clone <repository-url>
cd wistia-video-analytics-pipeline
```

---

# 2. Create a Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

The active shell should show:

```text
(.venv)
```

---

# 3. Install Dependencies

Runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

Development and unit-test dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

The two requirements files are intentionally separate.

```text
requirements.txt
→ packages required by the pipeline

requirements-dev.txt
→ packages required only for development/testing
```

---

# 4. Configure Local Environment Variables

The Wistia API token must never be committed to Git.

Set it only in the local shell or another approved secret-management mechanism.

Example:

```bash
export WISTIA_API_TOKEN='<token>'
export S3_BUCKET='wistia-video-analytics-dea'
export AWS_REGION='us-east-2'
export AWS_PROFILE='retail-poc'
```

Do not place the real token in:

```text
README files
source code
screenshots
Git commits
example configuration files
```

---

# 5. Verify AWS Identity

Before creating, changing, or deleting AWS resources:

```bash
aws sts get-caller-identity \
  --profile retail-poc \
  --region us-east-2
```

Expected development account:

```text
272987324508
```

Verify the account before continuing with AWS changes.

---

# 6. Run Unit Tests

```bash
python -m pytest -q
```

Current tests validate:

```text
Wistia timestamp parsing
incremental event filtering
```

Expected result:

```text
2 passed
```

The tests do not call the real Wistia API or AWS.

They use controlled test data so code behavior can be validated safely and repeatedly.

---

# 7. Run Python Syntax Checks

```bash
python -m py_compile \
  src/ingestion/wistia_ingest.py \
  src/transformation/transform_wistia.py
```

No output means Python successfully parsed both files.

---

# 8. Local Ingestion Execution

Production ingestion code:

```text
src/ingestion/wistia_ingest.py
```

A local run can be started with:

```bash
python src/ingestion/wistia_ingest.py
```

Local execution performs ingestion only.

It does not intentionally start the Glue transformation job.

This distinction exists because the Glue start logic is called from the AWS Lambda handler rather than the local Python entry point.

Local ingestion requires:

```text
WISTIA_API_TOKEN
S3_BUCKET
AWS_REGION
AWS_PROFILE
```

to be configured correctly.

---

# 9. Expected Raw S3 Output

Successful ingestion writes under:

```text
s3://wistia-video-analytics-dea/raw/
```

Run-specific layout:

```text
raw/
└── run_date=YYYY-MM-DD/
    └── run_id=<UTC-run-id>/
        ├── media_metadata.json
        ├── media_stats/
        ├── events/
        └── run_manifest.json
```

The incremental checkpoint is stored separately:

```text
s3://wistia-video-analytics-dea/state/checkpoint.json
```

---

# 10. Check Raw S3 Data

List recent raw objects:

```bash
aws s3 ls \
  s3://wistia-video-analytics-dea/raw/ \
  --recursive \
  --profile retail-poc \
  --region us-east-2
```

Check the state prefix:

```bash
aws s3 ls \
  s3://wistia-video-analytics-dea/state/ \
  --profile retail-poc \
  --region us-east-2
```

Do not publish visitor-level raw data in screenshots or repository documentation.

---

# 11. AWS Lambda

Production Lambda:

```text
wistia-video-analytics-ingestion
```

Handler:

```text
wistia_ingest.lambda_handler
```

Runtime:

```text
Python 3.13
```

Main responsibilities:

```text
call Wistia API
paginate event data
retry temporary HTTP errors
apply incremental checkpoint logic
write raw JSON
write run manifest
update checkpoint
start Glue after successful ingestion
```

---

# 12. Manually Invoke Lambda

A manual AWS test can be performed with:

```bash
aws lambda invoke \
  --function-name wistia-video-analytics-ingestion \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  --profile retail-poc \
  --region us-east-2 \
  /tmp/wistia-lambda-response.json \
  --no-cli-pager
```

Inspect the response:

```bash
cat /tmp/wistia-lambda-response.json
```

A successful response should indicate that:

```text
Wistia ingestion completed successfully
Glue transformation started
```

and return a:

```text
glue_job_run_id
```

---

# 13. Lambda Environment Variables

The deployed Lambda uses:

```text
WISTIA_API_TOKEN
S3_BUCKET
GLUE_JOB_NAME
```

Current non-secret values include:

```text
S3_BUCKET=wistia-video-analytics-dea
GLUE_JOB_NAME=wistia-video-analytics-transform
```

Never print or commit the full Lambda environment configuration because it contains the Wistia API token.

To verify only the Glue job variable:

```bash
aws lambda get-function-configuration \
  --function-name wistia-video-analytics-ingestion \
  --query 'Environment.Variables.GLUE_JOB_NAME' \
  --output text \
  --profile retail-poc \
  --region us-east-2
```

---

# 14. EventBridge Schedule

Scheduled rule:

```text
wistia-video-analytics-schedule
```

Current cadence:

```text
rate(1 day)
```

During implementation, the schedule was temporarily changed to:

```text
rate(5 minutes)
```

to prove automatic invocation.

After successful scheduled execution was observed, it was changed to the daily cadence.

Verify the current rule:

```bash
aws events describe-rule \
  --name wistia-video-analytics-schedule \
  --query '{State:State,Schedule:ScheduleExpression}' \
  --profile retail-poc \
  --region us-east-2 \
  --no-cli-pager
```

---

# 15. AWS Glue Transformation

Glue job:

```text
wistia-video-analytics-transform
```

Transformation script:

```text
src/transformation/transform_wistia.py
```

Deployed script location:

```text
s3://wistia-video-analytics-dea/scripts/transform_wistia.py
```

The Glue job:

```text
reads accumulated raw JSON
deduplicates event_key
selects latest media metadata
selects latest media statistics
hashes visitor_key
derives engagement metrics
builds dimensional datasets
writes curated Parquet
```

---

# 16. Manually Start Glue

A Glue transformation can also be started manually for testing or recovery:

```bash
aws glue start-job-run \
  --job-name wistia-video-analytics-transform \
  --profile retail-poc \
  --region us-east-2 \
  --query 'JobRunId' \
  --output text
```

The normal automated data path starts this job from Lambda after successful ingestion.

---

# 17. Check Glue Run Status

List recent runs:

```bash
aws glue get-job-runs \
  --job-name wistia-video-analytics-transform \
  --max-results 5 \
  --query 'JobRuns[*].[Id,JobRunState,ExecutionTime]' \
  --output table \
  --profile retail-poc \
  --region us-east-2 \
  --no-cli-pager
```

Successful transformation state:

```text
SUCCEEDED
```

---

# 18. Expected Curated Output

Glue writes:

```text
s3://wistia-video-analytics-dea/curated/
```

with:

```text
dim_media/
dim_visitor/
fact_media_engagement/
```

Check the output:

```bash
aws s3 ls \
  s3://wistia-video-analytics-dea/curated/ \
  --profile retail-poc \
  --region us-east-2
```

Expected logical datasets:

```text
dim_media
dim_visitor
fact_media_engagement
```

---

# 19. Validated Data Counts

The validated project transformation produced:

```text
dim_media = 2
dim_visitor = 1,122
fact_media_engagement = 1,197
```

The initial API ingestion retrieved:

```text
1,199 raw event rows
```

Source validation found:

```text
1,197 distinct event_key values
2 duplicated event IDs
```

The transformation intentionally deduplicates on:

```text
event_key
```

so the curated engagement count of 1,197 is expected.

---

# 20. Glue Data Catalog

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

Verify:

```bash
aws glue get-tables \
  --database-name wistia_video_analytics \
  --query 'TableList[*].[Name,StorageDescriptor.Location]' \
  --output table \
  --profile retail-poc \
  --region us-east-2 \
  --no-cli-pager
```

The catalog stores table metadata.

The actual records remain in S3 Parquet files.

---

# 21. Athena Table Definitions

Table-creation SQL:

```text
sql/athena_setup.sql
```

Validation SQL:

```text
sql/validation_queries.sql
```

Athena query results are written under:

```text
s3://wistia-video-analytics-dea/athena-results/
```

---

# 22. Athena Validation

Example row-count query:

```sql
SELECT
    (SELECT COUNT(*)
     FROM wistia_video_analytics.dim_media) AS media_count,

    (SELECT COUNT(*)
     FROM wistia_video_analytics.dim_visitor) AS visitor_count,

    (SELECT COUNT(*)
     FROM wistia_video_analytics.fact_media_engagement) AS engagement_count;
```

Validated result:

```text
media_count = 2
visitor_count = 1122
engagement_count = 1197
```

---

# 23. Example Analytics Query

```sql
SELECT
    m.title,
    COUNT(*) AS engagement_events,
    ROUND(AVG(f.watched_percent), 2) AS avg_watched_percent,
    ROUND(SUM(f.total_watch_time) / 60.0, 2) AS estimated_watch_minutes
FROM wistia_video_analytics.fact_media_engagement f
JOIN wistia_video_analytics.dim_media m
    ON f.media_id = m.media_id
GROUP BY m.title
ORDER BY engagement_events DESC;
```

This demonstrates that the curated fact and dimension tables can be joined and queried through Athena.

---

# 24. GitHub Actions CI

Workflow:

```text
.github/workflows/ci.yml
```

Triggers:

```text
push to main
pull request
```

The workflow:

```text
checks out repository
sets up Python 3.13
installs runtime dependencies
installs development dependencies
checks Python syntax
runs pytest
checks for tracked .env files
```

GitHub Actions does not run the Wistia ingestion pipeline.

It validates repository code separately from the AWS data-processing schedule.

---

# 25. Future Daily Run Behavior

A normal automated run is expected to follow:

```text
EventBridge invokes Lambda
        ↓
Lambda requests current Wistia data
        ↓
pagination processes available pages
        ↓
checkpoint logic identifies new events
        ↓
new raw records are written to S3
        ↓
checkpoint advances after successful ingestion
        ↓
Lambda starts Glue
        ↓
Glue rebuilds curated Parquet
        ↓
existing Glue Catalog tables continue pointing
to the curated S3 locations
        ↓
Athena queries return refreshed data
```

A pipeline that is working today still requires ongoing monitoring.

Future execution could expose conditions such as:

```text
checkpoint bugs
duplicate ingestion
incorrect pagination state
schedule configuration problems
expired or invalid credentials
source/API changes
transient API errors
incremental logic accidentally reprocessing historical data
```

These are expected operational risks to monitor, not failures observed during the validated project runs.

---

# 26. Troubleshooting Lambda

CloudWatch log group:

```text
/aws/lambda/wistia-video-analytics-ingestion
```

Check recent streams:

```bash
aws logs describe-log-streams \
  --log-group-name /aws/lambda/wistia-video-analytics-ingestion \
  --order-by LastEventTime \
  --descending \
  --max-items 5 \
  --profile retail-poc \
  --region us-east-2 \
  --no-cli-pager
```

Useful Lambda log information includes:

```text
full vs incremental mode
events fetched
events saved
pages fetched
S3 output location
checkpoint update
Glue JobRunId
exceptions
```

---

# 27. Troubleshooting Glue

If Lambda successfully starts Glue but the transformation later fails, inspect:

```text
AWS Glue job run status
Glue error message
CloudWatch / Glue logs
raw S3 input
```

Lambda starting Glue and Glue completing successfully are separate events.

A successful Lambda invocation does not by itself prove the later Glue transformation succeeded.

---

# 28. Checkpoint Troubleshooting

Checkpoint:

```text
state/checkpoint.json
```

The checkpoint represents the latest successfully processed event timestamp for each media ID.

When investigating unexpected incremental behavior, compare:

```text
checkpoint timestamp
raw event received_at values
run manifest
Lambda logs
events fetched
events saved
```

Do not manually modify the production checkpoint unless intentionally testing or performing a controlled recovery.

---

# 29. Security Notes

Never commit:

```text
Wistia API token
AWS credentials
.env files
raw visitor data
visitor names or emails
```

The curated model hashes the raw visitor key before storing:

```text
visitor_id
```

Real IP addresses should not be displayed in public screenshots or repository examples.

---

# 30. AWS Rebuild Reference

AWS infrastructure reference files:

```text
aws/
├── README.md
├── setup-reference.sh
└── iam/
```

`aws/setup-reference.sh` documents how the project resources can be recreated.

It is a rebuild reference and should not be run blindly against an environment where those resources already exist.

The script requires the Wistia token to be supplied externally.

---

# 31. Architecture Documentation

Architecture files:

```text
architecture/
├── architecture-overview.md
├── wistia-video-analytics-architecture.png
└── wistia-video-analytics-architecture.svg
```

The PNG provides a presentation-friendly architecture overview.

The SVG provides an editable version.

The Markdown file contains the detailed architecture rationale and operational behavior.

---

# 32. Project Validation Checklist

Before considering the environment healthy, verify:

```text
pytest passes
Python syntax checks pass
GitHub Actions is green
EventBridge rule is enabled
Lambda executes successfully
raw S3 run is created
checkpoint exists
Lambda returns a Glue JobRunId
Glue run succeeds
curated Parquet exists
Glue Catalog contains all three tables
Athena row counts are reasonable
analytics query succeeds
```

---

# 33. Cleanup

AWS resources should eventually be removed when the live project environment is no longer needed.

Before deleting resources:

```text
confirm required screenshots are saved
confirm GitHub documentation is complete
confirm walkthrough/demo evidence is complete
inventory existing AWS resources
```

Use the documented AWS resource names in:

```text
aws/README.md
```

when preparing teardown commands.

Always verify AWS identity before destructive commands.
