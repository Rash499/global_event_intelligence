"""CSV and PDF export for generated reports.

CSV carries structured rows (not presentation text). PDF is produced with the
standard-library ``reportlab``-free approach: a minimal PDF writer is avoided in
favour of returning a text/HTML document the browser prints, because pulling in a
heavy PDF dependency is not justified. The HTML export is print-ready and keeps
source references.
"""

from __future__ import annotations

import csv
import io
from html import escape

EVENT_FIELDS = [
    ("id", "event_id"),
    ("title", "title"),
    ("category", "category"),
    ("subcategory", "subcategory"),
    ("country", "country"),
    ("country_code", "country_code"),
    ("location_precision", "location_precision"),
    ("latitude", "latitude"),
    ("longitude", "longitude"),
    ("severity", "severity"),
    ("severity_label", "severity_label"),
    ("confidence", "confidence"),
    ("priority_label", "priority_label"),
    ("event_state", "event_state"),
    ("corroboration_level", "corroboration_level"),
    ("independent_source_count", "independent_publishers"),
    ("occurred_at", "occurred_at"),
]


def report_to_csv(report: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["report_title", report.get("title")])
    writer.writerow(["generated_at", report.get("generated_at")])
    writer.writerow(["reporting_period_start", report.get("reporting_period", {}).get("start")])
    writer.writerow(["reporting_period_end", report.get("reporting_period", {}).get("end")])
    writer.writerow([])

    writer.writerow([header for _, header in EVENT_FIELDS])
    for event in report.get("all_events", []):
        writer.writerow([event.get(key) for key, _ in EVENT_FIELDS])

    writer.writerow([])
    writer.writerow(["sources"])
    writer.writerow(["publisher", "publisher_domain", "title", "url", "published_at", "reporting_type", "event_id"])
    for source in report.get("sources", []):
        writer.writerow([
            source.get("publisher"), source.get("publisher_domain"),
            source.get("title"), source.get("url"), source.get("published_at"),
            source.get("reporting_type"), source.get("event_id"),
        ])

    writer.writerow([])
    writer.writerow(["methodology", report.get("methodology")])
    for note in report.get("contradictions_and_uncertainty", []):
        writer.writerow(["limitation", note])
    return buffer.getvalue()


def report_to_html(report: dict) -> str:
    """Print-ready HTML report with source references and methodology."""
    rows = "".join(
        f"<tr><td>{escape(str(event.get('title') or ''))}</td>"
        f"<td>{escape(str(event.get('category') or ''))}</td>"
        f"<td>{escape(str(event.get('country') or '—'))}</td>"
        f"<td>{event.get('severity') if event.get('severity') is not None else '—'}</td>"
        f"<td>{round((event.get('confidence') or 0) * 100)}%</td>"
        f"<td>{escape(str(event.get('event_state') or ''))}</td>"
        f"<td>{escape(str(event.get('occurred_at') or ''))}</td></tr>"
        for event in report.get("all_events", [])
    )
    source_rows = "".join(
        f"<li>{escape(str(source.get('publisher') or source.get('publisher_domain') or 'unknown'))}"
        f" — <a href=\"{escape(str(source.get('url') or ''))}\">{escape(str(source.get('title') or ''))}</a>"
        f" <span class=\"muted\">{escape(str(source.get('published_at') or ''))}</span></li>"
        for source in report.get("sources", [])
    )
    limitations = "".join(
        f"<li>{escape(note)}</li>" for note in report.get("contradictions_and_uncertainty", [])
    )
    key_developments = "".join(
        f"<li><strong>{escape(str(item.get('title') or ''))}</strong> "
        f"<span class=\"muted\">({escape(str(item.get('category_label') or ''))}, "
        f"severity {item.get('severity')}, confidence {round((item.get('confidence') or 0) * 100)}%, "
        f"{escape(str(item.get('corroboration') or ''))})</span></li>"
        for item in report.get("key_developments", [])
    )
    coverage = report.get("coverage", {})

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(str(report.get('title') or 'Intelligence report'))}</title>
<style>
 body {{ font-family: Georgia, 'Times New Roman', serif; margin: 40px auto; max-width: 900px; color: #1a1a1a; }}
 h1 {{ font-size: 26px; margin-bottom: 4px; }}
 h2 {{ font-size: 18px; margin-top: 28px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }}
 .muted {{ color: #666; font-size: 12px; }}
 table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }}
 th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; }}
 th {{ background: #f2f2f2; }}
 .ai {{ background: #fff8e1; border-left: 3px solid #c9a227; padding: 8px 12px; }}
 footer {{ margin-top: 32px; font-size: 11px; color: #666; }}
</style></head>
<body>
<h1>{escape(str(report.get('title') or 'Intelligence report'))}</h1>
<p class="muted">Reporting period {escape(str(report.get('reporting_period', {}).get('start') or ''))} →
 {escape(str(report.get('reporting_period', {}).get('end') or ''))} · generated {escape(str(report.get('generated_at') or ''))}</p>

<h2>Executive summary</h2>
<p>{escape(str(report.get('executive_summary') or '')).replace(chr(10), '<br>')}</p>

<h2>Key developments</h2>
<ol>{key_developments or '<li>No events met the report scope.</li>'}</ol>

<h2>Events</h2>
<table><thead><tr><th>Title</th><th>Category</th><th>Country</th><th>Severity</th><th>Confidence</th><th>State</th><th>Occurred</th></tr></thead>
<tbody>{rows or '<tr><td colspan="7">No events in scope.</td></tr>'}</tbody></table>

<h2>Coverage</h2>
<p>{coverage.get('distinct_publishers', 0)} publishers · {coverage.get('events_with_coordinates', 0)} events with coordinates ·
 {coverage.get('events_country_level_only', 0)} events known only at country level.</p>

<h2>Sources</h2>
<ul>{source_rows or '<li>No supporting sources recorded.</li>'}</ul>

<h2>Methodology and limitations</h2>
<p>{escape(str(report.get('methodology') or ''))}</p>
<ul>{limitations}</ul>

<footer>Generated by the Global Event Intelligence Platform. AI-generated sections are labelled and are assessments, not verified facts.</footer>
</body></html>"""
