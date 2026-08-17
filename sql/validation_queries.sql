-- Basic row-count validation

SELECT COUNT(*) AS media_count
FROM wistia_video_analytics.dim_media;

SELECT COUNT(*) AS visitor_count
FROM wistia_video_analytics.dim_visitor;

SELECT COUNT(*) AS engagement_count
FROM wistia_video_analytics.fact_media_engagement;


-- Engagement totals by media

SELECT
    media_id,
    COUNT(*) AS engagement_events,
    ROUND(AVG(watched_percent), 2) AS avg_watched_percent,
    ROUND(SUM(total_watch_time), 2) AS estimated_watch_seconds
FROM wistia_video_analytics.fact_media_engagement
GROUP BY media_id
ORDER BY engagement_events DESC;


-- Join fact data to readable media titles

SELECT
    m.title,
    COUNT(*) AS engagement_events,
    ROUND(AVG(f.watched_percent), 2) AS avg_watched_percent
FROM wistia_video_analytics.fact_media_engagement f
JOIN wistia_video_analytics.dim_media m
    ON f.media_id = m.media_id
GROUP BY m.title
ORDER BY engagement_events DESC;


-- Curated fact-table uniqueness check
-- The source full load contained 1,199 event rows but 1,197 distinct event_key
-- values. The PySpark transformation deduplicates by event_key.

SELECT
    COUNT(*) AS fact_rows,
    COUNT(DISTINCT engagement_id) AS distinct_engagement_ids
FROM wistia_video_analytics.fact_media_engagement;
