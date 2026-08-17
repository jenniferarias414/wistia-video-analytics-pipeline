# SQL / Athena

This folder contains the SQL used to register and validate the curated Wistia datasets with Amazon Athena.

## Where This Fits in the Pipeline

At this stage of the project, the data has already gone through ingestion and transformation:

```text
Wistia API
    ↓
Lambda / Python
    ↓
S3 raw JSON
    ↓
AWS Glue / PySpark
    ↓
S3 curated Parquet
    ↓
Glue Data Catalog
    ↓
Athena SQL
```

The important distinction is:

```text
S3
= stores the actual data files

Glue Data Catalog
= stores metadata describing those files as tables

Athena
= runs SQL against the S3 data using the catalog definitions
```

Athena does not copy the curated data into a separate database.

The Parquet files remain in S3.

---

## Curated Datasets

The PySpark transformation produces three datasets:

```text
s3://wistia-video-analytics-dea/curated/

├── dim_media/
├── dim_visitor/
└── fact_media_engagement/
```

These correspond to the dimensional model required by the project.

### `dim_media`

One row represents one Wistia media/video item.

Examples of fields:

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

There are two required media IDs in this project, so this table is expected to contain two media records.

---

### `dim_visitor`

One row represents one unique Wistia visitor observed in the event data.

Examples of fields:

```text
visitor_id
ip_address
country
region
city
browser
platform
mobile
```

The source `visitor_key` is hashed during the PySpark transformation before becoming `visitor_id`.

The curated table still contains IP address because visitor IP is included in the assignment requirements. Real visitor values should not be exposed in screenshots or public documentation.

---

### `fact_media_engagement`

The grain of this table is:

> One Wistia viewing event for one visitor and one media item.

Examples of fields:

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

The table connects the media and visitor dimensions through:

```text
media_id
visitor_id
```

---

## Source Metric Notes

The Wistia source does not perfectly match the simplified model in the requirement document.

### `percent_viewed`

The API was inspected before transformation.

Observed source values ranged from:

```text
0.0 → 1.0
```

For example:

```text
0.75 = 75% watched
```

The transformation therefore calculates:

```text
watched_percent = percent_viewed × 100
```

and estimates event-level watch time as:

```text
total_watch_time = duration_seconds × percent_viewed
```

Example:

```text
duration_seconds = 120
percent_viewed = 0.75

total_watch_time = 90 seconds
watched_percent = 75
```

This source-value check prevented incorrectly dividing `percent_viewed` by 100.

### `play_rate`

Wistia provides `play_rate` as a media-level aggregate metric rather than an event-level metric.

The latest media-level value is joined to engagement records because the required simplified fact-table design includes `play_rate`.

It should be interpreted as descriptive context for the media item and should not be summed across fact rows.

---

## Athena Setup

`athena_setup.sql` creates three external Athena tables:

```text
wistia_video_analytics.dim_media
wistia_video_analytics.dim_visitor
wistia_video_analytics.fact_media_engagement
```

The Glue Data Catalog database is:

```text
wistia_video_analytics
```

Each external table points to the corresponding Parquet location in S3.

Example concept:

```sql
CREATE EXTERNAL TABLE ...
STORED AS PARQUET
LOCATION 's3://.../curated/dim_media/';
```

This does not move the Parquet data.

It tells Athena:

> Files at this S3 location should be interpreted using this table schema.

---

## Athena Query Results

Athena query-result files are written to:

```text
s3://wistia-video-analytics-dea/athena-results/
```

These are Athena-generated query outputs, not pipeline source data.

---

## Validation Plan

After the three external tables are registered, basic validation includes:

```sql
SELECT COUNT(*)
FROM wistia_video_analytics.dim_media;
```

```sql
SELECT COUNT(*)
FROM wistia_video_analytics.dim_visitor;
```

```sql
SELECT COUNT(*)
FROM wistia_video_analytics.fact_media_engagement;
```

Expected high-level checks:

```text
dim_media
→ 2 required videos

dim_visitor
→ one row per distinct transformed visitor

fact_media_engagement
→ one row per unique Wistia viewing event
```

Additional queries can validate:

* event counts by media
* average watched percentage
* total estimated watch time
* visitor counts by country
* basic joins between dimensions and facts

Validation queries should avoid displaying real IP addresses or other sensitive visitor-level values in screenshots or public documentation.

---

## Files

```text
sql/
├── README.md
└── athena_setup.sql
```

Additional validation queries may be added as the project is completed.
