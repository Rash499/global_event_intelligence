# Descriptive anomaly baselines

The existing anomaly engine keeps its collection-coverage adequacy suppression and independent-source checks. Migration 009 adds 90-day rolling daily country/region samples and compact Welford mean/variance aggregates in weekday and calendar-month buckets. At least ten matched samples are required. Region anomalies carry observed activity, baseline mean, z-score in the `deviation` field, severity (`medium` ≥1.5, `high` ≥2, `critical` ≥3), and sample event IDs. A zero-variance baseline uses a conservative 3.0 score only when observed activity is above the mean.

A separate title/entity-term counter flags terms with a positive seven-day observed baseline whose 24-hour count exceeds three times that average. Stopwords are excluded. These are deviations in stored reporting volume only, not forecasts or claims about future events. Missing collection coverage continues to suppress baseline alerts.
