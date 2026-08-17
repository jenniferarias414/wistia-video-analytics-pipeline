# Wistia Video Analytics Pipeline Architecture

## Objective

Build a scheduled AWS data pipeline that retrieves Wistia video analytics, preserves the raw API responses, incrementally processes new engagement activity, transforms the source data with PySpark, and exposes a structured dimensional model for SQL analytics.

The implemented solution is intentionally small and serverless. The data volume and processing frequency do not require a continuously running database, cluster, or complex orchestration platform.

---

## Architecture Diagram

![Wistia Video Analytics Architecture](wistia-video-analytics-architecture.png)

The editable SVG version is also stored in this folder:

```text
architecture/wistia-video-analytics-architecture.svg
```


---

## End-to-End Data Flow

### 1. Scheduled Start

Amazon EventBridge invokes the ingestion Lambda on the final schedule:

```text
rate(1 day)
```

During implementation, the rule was temporarily configured as:

```text
rate(5 minutes)
```

to verify that EventBridge could invoke Lambda automatically.

After the scheduled invocation was successfully observed, the rule was changed to the daily cadence.

---

## 2. Wistia API Ingestion

Production ingestion code:

```text
src/ingestion/wistia_ingest.py
```

AWS Lambda runs the Python ingestion process.

The ingestion retrieves:

- media metadata
- media-level statistics
- visitor-level engagement events

The two project media IDs are processed independently.

The ingestion also implements:

- pagination
- HTTP retry handling
- incremental filtering
- run manifests
- persistent checkpoint state
- CloudWatch logging

---

## Wistia Authentication

The project requirement summary refers to token-based Basic Authentication.

The implemented integration uses:

```text
Authorization: Bearer <token>
```

because Wistia's current API documentation states that Bearer Token is the supported authentication method.

The implementation therefore follows the currently documented and successfully validated Wistia API interface rather than forcing an authentication method that does not match the live API behavior.

Official Wistia documentation:

https://docs.wistia.com/docs/making-api-requests

The API token is supplied to Lambda at runtime and is never committed to Git.

---

## 3. Pagination

Wistia event results can span multiple API pages.

The ingestion repeatedly requests pages until all available records for the media item have been processed.

Pagination was validated during source exploration by retrieving multiple pages and confirming that separate pages returned different event IDs.

The initial full ingestion retrieved:

```text
Media 8hunphufxp
873 events

Media 9k4tbcdfg0
326 events

Total raw event rows
1,199
```

---

## 4. Incremental Ingestion

Incremental state is persisted in:

```text
s3://wistia-video-analytics-dea/state/checkpoint.json
```

The checkpoint records the latest successfully processed event timestamp for each media item.

Conceptually:

```text
previous checkpoint
        ↓
request current Wistia events
        ↓
compare received_at timestamps
        ↓
save only events newer than checkpoint
        ↓
complete ingestion successfully
        ↓
advance checkpoint
```

The checkpoint is not intentionally advanced before successful ingestion completes.

This reduces the risk of incorrectly marking failed or incomplete data as processed.

---

## 5. Raw S3 Layer

Raw API responses are preserved under run-specific paths.

Conceptual layout:

```text
s3://wistia-video-analytics-dea/raw/

run_date=YYYY-MM-DD/
    run_id=<UTC-run-id>/
        media_metadata.json
        media_stats/
        events/
        run_manifest.json
```

The raw layer provides:

- source preservation
- run-level traceability
- input for reprocessing
- separation between ingestion and transformation

JSON is retained here because it closely reflects the Wistia API responses.

---

## 6. Run Manifest

Each ingestion run writes:

```text
run_manifest.json
```

The manifest records run-level information including media processing results and completion status.

It provides a record of what happened during a specific ingestion run independently of the mutable checkpoint.

---

## 7. Lambda Starts Glue

After ingestion finishes successfully, the Lambda handler calls:

```text
glue:StartJobRun
```

for:

```text
wistia-video-analytics-transform
```

AWS returns a Glue:

```text
JobRunId
```

after accepting the job request.

Lambda does not wait for the PySpark transformation to finish.

The integration was tested end to end:

```text
Lambda ingestion
        ↓
Glue StartJobRun
        ↓
automatically initiated Glue run
        ↓
SUCCEEDED
```

The validated automatically initiated Glue run completed in:

```text
81 seconds
```

---

## 8. PySpark Transformation

Transformation code:

```text
src/transformation/transform_wistia.py
```

AWS Glue reads accumulated raw Wistia data from S3.

The transformation:

- reads raw event JSON
- removes duplicate event IDs
- selects the latest media metadata
- selects the latest media statistics
- hashes the source visitor key
- derives engagement measures
- creates the dimensional datasets
- writes curated data as Parquet

---

## Duplicate Event Handling

The original full ingestion contained:

```text
1,199 raw event rows
```

Source validation found:

```text
1,197 distinct event_key values
2 duplicate event IDs
0 missing event_key values
```

The PySpark transformation deduplicates on:

```text
event_key
```

Therefore:

```text
1,199 raw rows
        ↓
deduplicate event_key
        ↓
1,197 unique engagement facts
```

The difference between raw and curated counts is intentional data-quality handling rather than unexplained record loss.

---

## percent_viewed Handling

Source inspection showed that Wistia represents:

```text
percent_viewed
```

as a decimal between:

```text
0.0 and 1.0
```

rather than 0 through 100.

Therefore:

```text
watched_percent =
percent_viewed × 100
```

and estimated event watch time is:

```text
total_watch_time =
duration_seconds × percent_viewed
```

This logic was corrected after inspecting actual source values and before the production Glue transformation was finalized.

---

# Curated Dimensional Model

The curated data is stored as Snappy-compressed Parquet in:

```text
s3://wistia-video-analytics-dea/curated/
```

with three datasets:

```text
dim_media/
dim_visitor/
fact_media_engagement/
```

This is the project's structured analytical data model.

---

## dim_media

Grain:

> One row per Wistia media item.

Validated row count:

```text
2
```

Main fields include:

```text
media_id
title
url
channel
created_at
updated_at
duration_seconds
status
```

---

## dim_visitor

Grain:

> One row per unique Wistia visitor observed in the engagement data.

Validated row count:

```text
1,122
```

The raw Wistia:

```text
visitor_key
```

is converted to a SHA-256 hash before becoming:

```text
visitor_id
```

Unnecessary identity attributes such as visitor name and email are not retained in the curated model.

IP address remains because it is part of the requested visitor structure, but real visitor-level values are not shown in public screenshots or documentation.

---

## fact_media_engagement

Grain:

> One row per unique Wistia engagement event.

Validated row count:

```text
1,197
```

Main fields include:

```text
engagement_id
media_id
visitor_id
received_at
date
play_count
play_rate
total_watch_time
watched_percent
```

Relationships:

```text
fact_media_engagement.media_id
        ↓
dim_media.media_id
```

and:

```text
fact_media_engagement.visitor_id
        ↓
dim_visitor.visitor_id
```

---

# Why Parquet for Curated Data

Raw responses remain JSON for source preservation.

Curated analytical data is written as Parquet.

Parquet is a columnar format suited to analytical queries and works efficiently with Athena.

This separates:

```text
Raw JSON
source-oriented storage

        ↓

Curated Parquet
analytics-oriented storage
```

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

The Glue Data Catalog stores metadata such as:

- table names
- column names
- data types
- S3 locations

The actual records remain in S3.

Athena uses this metadata to understand how to query the curated Parquet files.

---

# Why No Glue Crawler

The curated model has only three known tables with known schemas.

Their definitions are version-controlled in:

```text
sql/athena_setup.sql
```

The tables were registered explicitly instead of introducing automatic schema discovery.

This provides deterministic schemas and keeps the architecture small.

---

# Amazon Athena

Athena provides serverless SQL access to the curated model.

Conceptually:

```text
Athena SQL
    ↓
Glue Data Catalog
    ↓
S3 Parquet
```

Athena does not store a separate copy of the dimensional data.

Validated counts:

```text
dim_media = 2
dim_visitor = 1,122
fact_media_engagement = 1,197
```

A validated business query joins media to engagement data to calculate:

- engagement-event count
- average watched percentage
- estimated watch minutes

---

# Why Athena Instead of a Dedicated Warehouse

The project data volume is small and the analytical datasets already live naturally in S3.

Using:

```text
S3 + Glue Data Catalog + Athena
```

provides a structured dimensional analytics layer without requiring a continuously running warehouse cluster.

This reduces infrastructure, operational overhead, and cost while still supporting SQL analysis.

---

# Why One Glue Job

All three curated tables derive from the same small collection of Wistia source data.

A single PySpark job can:

```text
read source
    ↓
deduplicate
    ↓
transform
    ↓
build dimensions and fact
```

without introducing multiple dependent transformation jobs.

This keeps the processing flow understandable and appropriate for the size of the project.

---

# Why S3 for Incremental State

The pipeline requires only a small persisted watermark per media item.

The checkpoint fits naturally in:

```text
state/checkpoint.json
```

inside the existing project bucket.

A separate state database would add infrastructure and permissions for a very small amount of control data.

---

# Why EventBridge for Scheduling

The production ingestion requires one recurring schedule.

The implemented flow is:

```text
daily schedule
    ↓
Lambda
    ↓
Glue
```

There are no complex branches or large dependency graphs requiring a separate orchestration platform.

---

# CloudWatch Monitoring

CloudWatch captures Lambda execution logs including:

- ingestion start and completion
- event counts
- incremental/full mode
- S3 output locations
- checkpoint updates
- Glue JobRunId
- exceptions

Glue also exposes its own job-run status and logs.

This separates ingestion execution status from transformation execution status.

---

# Future Daily Run Expectations

The pipeline has been validated through:

```text
local ingestion execution
        ↓
manual AWS Lambda execution
        ↓
short-interval EventBridge scheduled execution
        ↓
daily EventBridge configuration
        ↓
Lambda-triggered Glue transformation
```

A normal future daily run is expected to:

```text
EventBridge invokes Lambda
        ↓
Lambda requests current Wistia data
        ↓
pagination retrieves available event pages
        ↓
checkpoint logic identifies new events
        ↓
new raw records are stored
        ↓
checkpoint advances after successful ingestion
        ↓
Lambda starts Glue
        ↓
Glue rebuilds curated Parquet
        ↓
existing Data Catalog definitions continue pointing
to the refreshed curated locations
        ↓
Athena queries return the updated data
```

Successful automation at one point in time does not guarantee that the pipeline will operate indefinitely without intervention.

Longer-running operation may expose issues such as:

- checkpoint bugs
- duplicate ingestion
- incorrect pagination state
- schedule configuration problems
- expired or invalid credentials
- changes in Wistia source data or API behavior
- transient API failures
- incremental logic accidentally reprocessing historical records

These are operational risks to monitor rather than failures observed during the validated project runs.

CloudWatch logs, Glue run status, S3 run manifests, checkpoint state, and row-count validation provide the main evidence for diagnosing those conditions.

---

# Failure Behavior

## Wistia / Lambda Failure

If ingestion encounters a handled API or AWS client failure:

```text
run marked failed
        ↓
failed run manifest attempted
        ↓
exception logged
        ↓
Lambda invocation fails
```

Glue is not intentionally started after unsuccessful ingestion.

---

## Glue Failure

Starting Glue and completing Glue are separate events.

Lambda can successfully submit:

```text
StartJobRun
```

while the later Glue transformation could still fail.

The transformation result must therefore be checked through:

```text
Glue job-run status
CloudWatch / Glue logs
```

A later transformation can rebuild the curated datasets from the accumulated raw S3 layer.

---

# IAM and Least Privilege

## Lambda Role

```text
wistia-video-analytics-lambda-role
```

Permissions include:

```text
CloudWatch logging
S3 GetObject / PutObject
glue:StartJobRun
```

The Glue permission is restricted to:

```text
wistia-video-analytics-transform
```

rather than broad:

```text
glue:*
```

---

## Glue Role

```text
AWSGlueServiceRole-wistia-video-analytics
```

The role can read the project's raw objects and write/overwrite the project's curated S3 output.

---

# GitHub Actions CI

GitHub Actions is separate from the daily data pipeline.

Flow:

```text
GitHub push / pull request
        ↓
temporary GitHub runner
        ↓
install dependencies
        ↓
Python syntax checks
        ↓
pytest
        ↓
tracked .env safety check
```

The workflow validates code changes.

It does not receive AWS or Wistia credentials and does not run the daily data ingestion.

This separates:

```text
development automation
GitHub Actions
```

from:

```text
data pipeline automation
EventBridge + Lambda + Glue
```

---

# Future Analytics Integration

Athena is the current SQL consumption layer.

Because the curated model is already exposed through Athena, future analytics consumers could connect to this layer without changing ingestion or transformation logic.

Examples include:

```text
Tableau
Streamlit
other BI or analytical applications
```

Conceptually:

```text
S3 curated
    ↓
Glue Data Catalog
    ↓
Athena
    ↓
BI / analytics consumer
```

---

# Key Design Decisions

| Decision | Reason |
|---|---|
| Python + Lambda for Wistia ingestion | Lightweight API workload with pagination, retries, and checkpoint logic |
| S3 raw layer | Preserves source responses and supports reprocessing |
| S3 checkpoint | Small amount of state does not require another database |
| Glue PySpark | Performs the required transformation and creates dimensional outputs |
| Single Glue job | Source volume and transformation dependencies are small |
| Parquet curated layer | Columnar analytical storage for Athena |
| Explicit table DDL | Only three known schemas; deterministic and version-controlled |
| Glue Data Catalog | Central metadata definition for Athena tables |
| Athena | Serverless SQL without a dedicated warehouse cluster |
| EventBridge | Simple recurring schedule without heavier orchestration |
| CloudWatch | Native execution logs and operational diagnostics |
| GitHub Actions | Automated code validation independent of daily data processing |

---

# Architecture Summary

The implemented architecture is:

```text
Wistia Stats API
        ↓
AWS Lambda / Python
        ↓
incremental raw JSON in S3
        ↓
persistent S3 checkpoint
        ↓
AWS Glue / PySpark
        ↓
curated dimensional Parquet
        ↓
AWS Glue Data Catalog
        ↓
Amazon Athena
```

Scheduling:

```text
Amazon EventBridge
        ↓
daily Lambda invocation
```

Code validation:

```text
GitHub
    ↓
GitHub Actions CI
```

Monitoring:

```text
Lambda + Glue
    ↓
CloudWatch
```

The result is a small serverless analytics architecture with separate ingestion, raw storage, state management, transformation, curated dimensional storage, metadata, and SQL-query layers.

---

# References

## Wistia

Wistia - Making API Requests / Authentication:

https://docs.wistia.com/docs/making-api-requests

## AWS

AWS Glue - StartJobRun:

https://docs.aws.amazon.com/boto3/latest/reference/services/glue/client/start_job_run.html

Amazon Athena - AWS Glue Data Catalog:

https://docs.aws.amazon.com/athena/latest/ug/data-sources-glue.html

Amazon Athena - Parquet:

https://docs.aws.amazon.com/athena/latest/ug/parquet-serde.html

Amazon EventBridge - Scheduled Rules:

https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-rule-schedule.html
