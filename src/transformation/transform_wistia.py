import sys

from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import Window
from pyspark.sql.functions import (
    col,
    input_file_name,
    lit,
    lower,
    regexp_extract,
    row_number,
    sha2,
    to_date,
    to_timestamp,
    when,
)


args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "S3_BUCKET"],
)

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session

job = Job(glue_context)
job.init(args["JOB_NAME"], args)

spark.sparkContext.setLogLevel("WARN")

bucket = args["S3_BUCKET"]

raw_base = f"s3://{bucket}/raw"
curated_base = f"s3://{bucket}/curated"


def read_json(path):
    return (
        spark.read
        .option("multiline", "true")
        .json(path)
    )


print("Reading raw Wistia event data")

events = read_json(
    f"{raw_base}/run_date=*/run_id=*/events/media_id=*/*.json"
)

print(f"Raw event rows read: {events.count()}")


print("Deduplicating events by event_key")

events = events.dropDuplicates(["event_key"])

print(f"Unique event rows: {events.count()}")


print("Reading media metadata")

metadata = read_json(
    f"{raw_base}/run_date=*/run_id=*/media_metadata.json"
)

metadata = metadata.withColumn(
    "media_id",
    col("hashed_id"),
)

metadata_window = Window.partitionBy(
    "media_id"
).orderBy(
    col("updated").desc()
)

latest_metadata = (
    metadata
    .withColumn(
        "_row_number",
        row_number().over(metadata_window),
    )
    .filter(col("_row_number") == 1)
    .drop("_row_number")
)


print("Reading media statistics")

media_stats = (
    read_json(
        f"{raw_base}/run_date=*/run_id=*/media_stats/*.json"
    )
    .withColumn(
        "_source_file",
        input_file_name(),
    )
    .withColumn(
        "media_id",
        regexp_extract(
            col("_source_file"),
            r"/media_stats/([^/]+)\.json$",
            1,
        ),
    )
    .withColumn(
        "_run_id",
        regexp_extract(
            col("_source_file"),
            r"run_id=([^/]+)",
            1,
        ),
    )
)

stats_window = Window.partitionBy(
    "media_id"
).orderBy(
    col("_run_id").desc()
)

latest_stats = (
    media_stats
    .withColumn(
        "_row_number",
        row_number().over(stats_window),
    )
    .filter(col("_row_number") == 1)
    .drop(
        "_row_number",
        "_source_file",
        "_run_id",
    )
)


print("Building dim_media")

event_media_window = Window.partitionBy(
    "media_id"
).orderBy(
    col("received_at").desc()
)

latest_event_media = (
    events
    .filter(col("media_id").isNotNull())
    .withColumn(
        "_row_number",
        row_number().over(event_media_window),
    )
    .filter(col("_row_number") == 1)
    .select(
        "media_id",
        "media_url",
    )
)

dim_media = (
    latest_metadata
    .join(
        latest_event_media,
        on="media_id",
        how="left",
    )
    .select(
        col("media_id"),
        col("name").alias("title"),
        col("media_url").alias("url"),
        when(
            lower(col("media_url")).contains("youtube"),
            lit("YouTube"),
        )
        .when(
            lower(col("media_url")).contains("facebook"),
            lit("Facebook"),
        )
        .otherwise(
            lit(None).cast("string")
        )
        .alias("channel"),
        to_timestamp(col("created")).alias("created_at"),
        to_timestamp(col("updated")).alias("updated_at"),
        col("duration").cast("double").alias(
            "duration_seconds"
        ),
        col("status"),
    )
)


print("Building dim_visitor")

visitor_window = Window.partitionBy(
    "visitor_key"
).orderBy(
    col("received_at").desc()
)

latest_visitors = (
    events
    .filter(col("visitor_key").isNotNull())
    .withColumn(
        "_row_number",
        row_number().over(visitor_window),
    )
    .filter(col("_row_number") == 1)
)

dim_visitor = (
    latest_visitors
    .select(
        sha2(
            col("visitor_key"),
            256,
        ).alias("visitor_id"),
        col("ip").alias("ip_address"),
        col("country"),
        col("region"),
        col("city"),
        col("user_agent_details.browser").alias(
            "browser"
        ),
        col("user_agent_details.platform").alias(
            "platform"
        ),
        col("user_agent_details.mobile").alias(
            "mobile"
        ),
    )
)


print("Building fact_media_engagement")

fact_base = (
    events
    .join(
        dim_media.select(
            "media_id",
            "duration_seconds",
        ),
        on="media_id",
        how="left",
    )
    .join(
        latest_stats.select(
            "media_id",
            col("play_rate").cast("double").alias(
                "media_play_rate"
            ),
        ),
        on="media_id",
        how="left",
    )
)

fact_media_engagement = (
    fact_base
    .select(
        col("event_key").alias("engagement_id"),
        col("media_id"),
        sha2(
            col("visitor_key"),
            256,
        ).alias("visitor_id"),
        to_timestamp(col("received_at")).alias(
            "received_at"
        ),
        to_date(
            to_timestamp(col("received_at"))
        ).alias("date"),
        lit(1).cast("long").alias("play_count"),
        col("media_play_rate").alias("play_rate"),
        (
            col("duration_seconds")
            * col("percent_viewed")
            / lit(100.0)
        ).alias("total_watch_time"),
        col("percent_viewed").cast("double").alias(
            "watched_percent"
        ),
    )
)


print("Writing dim_media")

(
    dim_media
    .coalesce(1)
    .write
    .mode("overwrite")
    .parquet(
        f"{curated_base}/dim_media/"
    )
)


print("Writing dim_visitor")

(
    dim_visitor
    .coalesce(1)
    .write
    .mode("overwrite")
    .parquet(
        f"{curated_base}/dim_visitor/"
    )
)


print("Writing fact_media_engagement")

(
    fact_media_engagement
    .coalesce(1)
    .write
    .mode("overwrite")
    .parquet(
        f"{curated_base}/fact_media_engagement/"
    )
)


print("Transformation completed successfully")

print(
    f"dim_media rows: {dim_media.count()}"
)

print(
    f"dim_visitor rows: {dim_visitor.count()}"
)

print(
    "fact_media_engagement rows: "
    f"{fact_media_engagement.count()}"
)

job.commit()
