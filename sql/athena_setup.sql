CREATE EXTERNAL TABLE IF NOT EXISTS wistia_video_analytics.dim_media (
    media_id STRING,
    title STRING,
    url STRING,
    channel STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    duration_seconds DOUBLE,
    status STRING
)
STORED AS PARQUET
LOCATION 's3://wistia-video-analytics-dea/curated/dim_media/'
TBLPROPERTIES ('classification'='parquet');


CREATE EXTERNAL TABLE IF NOT EXISTS wistia_video_analytics.dim_visitor (
    visitor_id STRING,
    ip_address STRING,
    country STRING,
    region STRING,
    city STRING,
    browser STRING,
    platform STRING,
    mobile BOOLEAN
)
STORED AS PARQUET
LOCATION 's3://wistia-video-analytics-dea/curated/dim_visitor/'
TBLPROPERTIES ('classification'='parquet');


CREATE EXTERNAL TABLE IF NOT EXISTS wistia_video_analytics.fact_media_engagement (
    engagement_id STRING,
    media_id STRING,
    visitor_id STRING,
    received_at TIMESTAMP,
    date DATE,
    play_count BIGINT,
    play_rate DOUBLE,
    total_watch_time DOUBLE,
    watched_percent DOUBLE
)
STORED AS PARQUET
LOCATION 's3://wistia-video-analytics-dea/curated/fact_media_engagement/'
TBLPROPERTIES ('classification'='parquet');
