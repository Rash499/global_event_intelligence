# Geographic convergence

Two related routes serve different questions:

- `/api/convergence` groups stored events by country and taxonomy group, then compares event counts with the preceding equal time window or detects a critical-severity record. It is temporal reporting-volume convergence at country scale.
- `/api/spatial-convergence` bins geolocated records into fixed 1° latitude/longitude cells over the most recent 24 hours. It reports cells with at least three distinct event categories. Score is `25 × unique category count + min(25, 2 × event count)`; four categories or score ≥90 is critical, otherwise high. The nearest-country label uses the local country-coordinate anchors and is approximate, not a border-level reverse geocode.

Spatial convergence may create a system alert linked to its newest sample event, but it still passes the same recency, severity, importance and cooldown checks as other alerts. This describes co-location in collected data and makes no forecast.
