"""Manual smoke script for the optional Ollama integration.

Not collected by pytest. Run with `python scripts/try_ollama_analysis.py`
when Ollama and the `ollama` package are available.
"""
from app.ai.ollama import analyze_article


article = analyze_article(
    title="Major earthquake strikes Japan",
    description=(
        "A powerful earthquake struck Japan, "
        "causing damage and triggering emergency responses."
    ),
    source="Test Source",
    url="https://example.com/test",
)


print("\nAI EVENT RESULT")
print("====================")

print("Important:", article.is_major_event)
print("Title:", article.event_title)
print("Category:", article.category)
print("Country:", article.country)
print("Country Code:", article.country_code)
print("Location:", article.location)
print("Latitude:", article.latitude)
print("Longitude:", article.longitude)
print("Countries:", article.countries_involved)
print("Importance:", article.importance)
print("Confidence:", article.confidence)
print("Summary:", article.summary)