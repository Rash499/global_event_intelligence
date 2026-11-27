"""Named-entity extraction and linking.

Deterministic and conservative: only entities that can be identified by an
explicit signal are stored.

* countries come from the geolocation registry;
* organisations come from a curated registry of agencies/institutions plus
  patterns ("Ministry of …", "… Agency", "… Forces");
* armed groups and political parties come from a curated registry;
* people are extracted only as a capitalised full name adjacent to a role verb
  ("President X", "Minister Y said"), which keeps false positives low.

Entities are never merged on name similarity alone: the normalised key includes
the entity type, so "Georgia" the country and "Georgia" a person stay distinct.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from .geolocation import COUNTRY_BY_CODE, COUNTRIES

logger = logging.getLogger(__name__)

ORGANISATIONS = {
    "united nations": "United Nations",
    "un security council": "UN Security Council",
    "unhcr": "UNHCR",
    "ocha": "OCHA",
    "world food programme": "World Food Programme",
    "world health organization": "World Health Organization",
    "who": "World Health Organization",
    "international monetary fund": "International Monetary Fund",
    "imf": "International Monetary Fund",
    "world bank": "World Bank",
    "nato": "NATO",
    "european union": "European Union",
    "african union": "African Union",
    "asean": "ASEAN",
    "interpol": "Interpol",
    "red cross": "International Committee of the Red Cross",
    "icrc": "International Committee of the Red Cross",
    "medecins sans frontieres": "Médecins Sans Frontières",
    "world meteorological organization": "World Meteorological Organization",
    "usgs": "USGS",
    "noaa": "NOAA",
    "fema": "FEMA",
    "centers for disease control": "Centers for Disease Control and Prevention",
    "european commission": "European Commission",
    "international atomic energy agency": "International Atomic Energy Agency",
    "opec": "OPEC",
}

ARMED_GROUPS = {
    "hezbollah": "Hezbollah",
    "hamas": "Hamas",
    "houthi": "Houthi movement",
    "taliban": "Taliban",
    "al shabaab": "Al-Shabaab",
    "boko haram": "Boko Haram",
    "isis": "Islamic State",
    "islamic state": "Islamic State",
    "wagner": "Wagner Group",
    "rsf": "Rapid Support Forces",
    "junta": "Military junta",
}

PARTIES = {
    "labour party": "Labour Party",
    "conservative party": "Conservative Party",
    "republican": "Republican Party",
    "democrat": "Democratic Party",
    "democratic party": "Democratic Party",
    "african national congress": "African National Congress",
    "anc": "African National Congress",
    "bharatiya janata party": "Bharatiya Janata Party",
    "bjp": "Bharatiya Janata Party",
}

ROLE_PATTERN = re.compile(
    r"\b(?:President|Prime Minister|Minister|Chancellor|Premier|King|Emir|Sheikh|"
    r"General|Colonel|Admiral|Secretary-General|Spokesperson|Governor|Mayor|"
    r"Director|Chairman|Chief Executive)\s+"
    r"([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,2})\b"
)

ORG_PATTERN = re.compile(
    r"\b((?:Ministry|Department|Agency|Authority|Commission|Institute|Bureau|"
    r"Council|Organization|Organisation|Committee|Forces|Army|Navy|Police)\s+"
    r"(?:of\s+|for\s+)?(?:[A-Z][a-z]+\s*){1,4})"
)

ALL_COUNTRY_NAMES = sorted(
    ((entry["name"].lower(), entry["code"]) for entry in COUNTRIES),
    key=lambda item: -len(item[0]),
)


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", name.lower()).strip()


def extract_entities(text: str, country_code: str | None = None) -> list[dict]:
    """Return ``[{name, entity_type, role}]`` for the supplied text."""
    if not text:
        return []

    lowered = text.lower()
    found: dict[tuple[str, str], dict] = {}

    def add(name: str, entity_type: str, role: str = "mentioned") -> None:
        key = (entity_type, _normalise(name))
        if key in found:
            return
        if len(name) < 2:
            return
        found[key] = {
            "name": name.strip(),
            "entity_type": entity_type,
            "role": role,
            "country_code": country_code,
        }

    for alias, canonical in ORGANISATIONS.items():
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lowered):
            add(canonical, "organization")

    for alias, canonical in ARMED_GROUPS.items():
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lowered):
            add(canonical, "armed_group")

    for alias, canonical in PARTIES.items():
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lowered):
            add(canonical, "political_party")

    for name, code in ALL_COUNTRY_NAMES:
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", lowered):
            add(COUNTRY_BY_CODE[code]["name"], "country")

    for match in ROLE_PATTERN.finditer(text):
        add(match.group(1).strip(), "person", role=match.group(0).split()[0])

    for match in ORG_PATTERN.finditer(text):
        candidate = match.group(1).strip().strip(",")
        if len(candidate.split()) >= 2:
            add(candidate, "organization")

    return list(found.values())


def upsert_entities(conn, event_id: int, entities: list[dict], article_id: int | None = None) -> int:
    """Persist entity mentions for an event. Returns the number linked."""
    if not entities:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    linked = 0
    for entity in entities:
        normalised = _normalise(entity["name"])
        if not normalised:
            continue
        row = conn.execute(
            "SELECT id FROM entities WHERE normalized_name = ? AND entity_type = ?",
            (normalised, entity["entity_type"]),
        ).fetchone()
        if row:
            entity_id = row["id"]
            conn.execute(
                """
                UPDATE entities SET last_seen_at = ?, mention_count = mention_count + 1,
                       country_code = COALESCE(country_code, ?)
                WHERE id = ?
                """,
                (now, entity.get("country_code"), entity_id),
            )
        else:
            entity_id = conn.execute(
                """
                INSERT INTO entities (
                    name, normalized_name, entity_type, country_code,
                    first_seen_at, last_seen_at, mention_count
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    entity["name"], normalised, entity["entity_type"],
                    entity.get("country_code"), now, now,
                ),
            ).lastrowid

        conn.execute(
            """
            INSERT OR IGNORE INTO event_entity_mentions (
                event_id, entity_id, article_id, role, confidence
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, entity_id, article_id, entity.get("role"), 0.6),
        )
        linked += 1
    return linked


def extract_for_event(conn, event: dict, articles: list[dict]) -> int:
    """Extract entities from an event's own text plus its supporting articles."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='entities'").fetchone():
        return 0
    text = " ".join(
        [str(event.get("title") or ""), str(event.get("summary") or "")]
        + [str(article.get("title") or "") for article in articles[:5]]
    )
    entities = extract_entities(text, country_code=event.get("country_code"))
    return upsert_entities(conn, event["id"], entities)
