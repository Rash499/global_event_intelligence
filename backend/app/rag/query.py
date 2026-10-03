"""Deterministic query understanding for the assistant.

No LLM is used here on purpose: country, region, category, importance and time
constraints are parsed with rules, so retrieval filters are predictable,
testable and free. The LLM only writes the grounded answer.

Examples::

    "What happened in Sri Lanka this week?"
        -> country LK, time range 7d, question type "country"

    "What major natural disasters happened in Asia?"
        -> region Asia (country codes), category natural_disaster,
           minimum importance 8, question type "importance"
"""

import re
from calendar import monthrange
from datetime import datetime, timedelta, timezone

from ..config import Settings, settings as global_settings
from ..intelligence.classification import (
    CATEGORY_ALIASES,
    KEYWORD_MAP,
    normalize_category,
)
from .countries import COUNTRY_ALIASES, COUNTRY_CONTINENTS
from .embeddings import tokenize
from .models import ConversationTurn, QueryFilters, QueryOverrides, QueryPlan

REGION_ALIASES = {
    "asia": "Asia",
    "asian": "Asia",
    "south asia": "Asia",
    "southeast asia": "Asia",
    "south east asia": "Asia",
    "east asia": "Asia",
    "central asia": "Asia",
    "europe": "Europe",
    "european": "Europe",
    "africa": "Africa",
    "african": "Africa",
    "north america": "North America",
    "northern america": "North America",
    "south america": "South America",
    "latin america": "South America",
    "central america": "North America",
    "caribbean": "North America",
    "oceania": "Oceania",
    "pacific islands": "Oceania",
    "australasia": "Oceania",
}

MIDDLE_EAST_CODES = [
    "AE", "BH", "CY", "EG", "IQ", "IR", "IL", "JO", "KW", "LB", "OM", "PS",
    "QA", "SA", "SY", "TR", "YE",
]

GLOBAL_SCOPE_TERMS = ("global", "worldwide", "world wide", "the world", "everywhere")

# Phase 3 explicitly excludes predictions and recommendations.
OUT_OF_SCOPE_PATTERNS = [
    (r"\b(who|which)\b[^.?!]{0,40}\bwill\b[^.?!]{0,30}\b(win|lead|become)\b", "prediction"),
    (r"\bwill\b[^.?!]{0,40}\b(happen|win|rise|fall|increase|decrease|crash|invade|collapse)\b", "prediction"),
    (r"\bwill\b[^.?!]{0,60}\b(reach|hit|surpass|exceed|drop to)\b", "prediction"),
    (r"\b(predict|prediction|predictions|predicting)\b", "prediction"),
    (r"\bforecast\b[^.?!]{0,30}\b(outcome|result|winner)\b", "prediction"),
    (r"\belection (outcome|result|prediction)\b", "prediction"),
    (r"\b(next|future)\b[^.?!]{0,20}\belection\b[^.?!]{0,20}\b(result|winner|outcome)\b", "prediction"),
    (r"\b(investment advice|financial advice|advice on (buying|selling|investing))\b", "recommendation"),
    (r"\b(should i|should we|should one)\b[^.?!]{0,30}\b(buy|sell|invest|trade|hold)\b", "recommendation"),
    (r"\b(stock|share|crypto|bitcoin|btc|ethereum|currency)\b[^.?!]{0,40}\b(price|reach|hit|100k|worth)\b", "recommendation"),
    (r"\bwill bitcoin\b", "recommendation"),
]

GENERAL_KNOWLEDGE_PATTERNS = [
    r"\bcapital of\b",
    r"\bwho invented\b",
    r"\bpopulation of\b",
    r"\btranslate\b",
    r"\bmeaning of life\b",
    r"\bhow old is\b",
    r"\bwho was the (first|second|last|current)\b",
    r"\bwho (is|was) the president of\b",
    r"\bhow tall is\b",
    r"\bwhat is the tallest\b",
]

SOURCE_INTENT_PATTERNS = [
    r"\bwhich sources?\b",
    r"\bwhat sources?\b",
    r"\bwho reported\b",
    r"\bsources? (for|of) (this|that|the) event\b",
    r"\bwhich (news )?outlets?\b",
    r"\bwhere did you (read|get|find)\b",
    r"\b(most|highest|largest|greatest) number of (sources|reports|outlets)\b",
    r"\b(events?|stories?)\b[^.?!]{0,30}\b(most|highest)\b[^.?!]{0,20}\b(sources|reports|coverage)\b",
    r"\bwidely (reported|covered)\b",
    r"\bmost (reported|covered)\b",
]

DETAIL_INTENT_PATTERNS = [
    r"\btell me more\b",
    r"\bmore (details|information) (about|on)\b",
    r"\bdetails? (about|of|on)\b",
    r"\bexplain (the|this|that)\b",
    r"\bsummar(y|ise|ize) (the|this|that)\b",
]

TREND_INTENT_PATTERNS = [
    r"\bhow has\b[^.?!]{0,40}\bchanged\b",
    r"\btrend(s|ing)?\b",
    r"\bover the (last|past)\b",
    r"\btimeline\b",
    r"\bhistory of (event|activity|reporting)\b",
    r"\bwhat changed\b",
    r"\bincrease(d|s)? or decrease(d|s)?\b",
]

IMPORTANCE_TOP_TERMS = (
    "most important", "top events", "top event", "highest importance", "biggest",
    "most critical", "most significant",
)

IMPORTANCE_MAJOR_TERMS = (
    "major event", "major events", "major natural disaster", "major natural disasters",
    "major incident", "major incidents", "critical event", "critical events", "major",
)

IMPORTANCE_MEDIUM_TERMS = (
    "important", "significant", "notable", "serious", "high importance",
)


FOLLOW_UP_PREFIXES = (
    "and ", "what about", "which one", "which of", "the first", "the second",
    "the last", "that one", "this one", "how about", "tell me more", "more about",
)

QUESTION_WORD_STOPWORDS = {
    "events", "event", "happened", "happening", "report", "reported", "reporting",
    "week", "month", "year", "day", "days", "weeks", "months", "years", "today",
    "yesterday", "latest", "recent", "recently", "new", "news", "major", "top",
    "most", "important", "biggest", "significant", "many", "much", "few",
    "last", "past", "previous", "since", "more", "than", "changed", "change",
    "activity", "between", "sources", "source", "will", "win", "next",
    "number", "total", "count", "over", "has", "have", "had", "during",
}

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

EXTRA_CATEGORY_KEYWORDS = {
    "sports": ["sport", "sports", "tournament", "olympic", "championship"],
    "culture": ["culture", "festival", "music", "film", "movie", "celebrity", "entertainment"],
    "education": ["education", "school", "university", "student", "exam", "college"],
    "crime_security": ["crime", "arrest", "arrested", "police", "murder", "smuggling", "robbery", "court"],
    "security": ["terror", "terrorism", "militant", "extremist", "insurgency"],
    "infrastructure": ["bridge", "power grid", "airport", "rail", "pipeline"],
    "energy": ["oil", "gas", "electricity", "power plant"],
}


def _word_pattern(keyword: str) -> re.Pattern:
    escaped = re.escape(keyword.strip().lower())
    return re.compile(rf"(?<![a-z]){escaped}(?:s|es|ed|ing)?(?![a-z])")


def _build_keyword_index() -> list[tuple[re.Pattern, str]]:
    """(pattern, category) pairs for deterministic category detection."""
    entries: list[tuple[re.Pattern, str]] = []
    seen: set[str] = set()

    for category, keywords in KEYWORD_MAP.items():
        for keyword in keywords:
            if keyword in seen:
                continue
            seen.add(keyword)
            entries.append((_word_pattern(keyword), normalize_category(category)))

    for category, keywords in EXTRA_CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in seen:
                continue
            seen.add(keyword)
            entries.append((_word_pattern(keyword), normalize_category(category)))

    for alias in CATEGORY_ALIASES:
        if alias in seen:
            continue
        seen.add(alias)
        entries.append((_word_pattern(alias), normalize_category(alias)))

    entries.sort(key=lambda entry: -len(entry[0].pattern))
    return entries


CATEGORY_PATTERNS = _build_keyword_index()

COUNTRY_PATTERN = re.compile(
    "|".join(re.escape(alias) for alias in sorted(COUNTRY_ALIASES, key=len, reverse=True))
)

COUNTRY_CODES_BY_CONTINENT: dict[str, list[str]] = {}
for _code, _continent in COUNTRY_CONTINENTS.items():
    COUNTRY_CODES_BY_CONTINENT.setdefault(_continent, []).append(_code)


def normalize_question(question: str) -> str:
    return " ".join(str(question or "").lower().split())


def detect_out_of_scope(normalized: str) -> tuple[bool, str | None]:
    for pattern, reason in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, normalized):
            return True, reason

    for pattern in GENERAL_KNOWLEDGE_PATTERNS:
        if re.search(pattern, normalized):
            return True, "general_knowledge"

    return False, None


def detect_prompt_injection(normalized: str) -> bool:
    return bool(
        re.search(
            r"(ignore (all )?(previous|prior|above) (instructions|rules|prompt))"
            r"|(you are now|act as|new instructions|system prompt|disregard your rules)",
            normalized,
        )
    )


def detect_countries(normalized: str) -> list[str]:
    codes: list[str] = []

    for match in COUNTRY_PATTERN.finditer(normalized):
        code = COUNTRY_ALIASES.get(match.group(0))
        if code and code not in codes:
            codes.append(code)

    return codes


def detect_region(normalized: str) -> tuple[str | None, list[str]]:
    for alias in sorted(REGION_ALIASES, key=len, reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", normalized):
            continent = REGION_ALIASES[alias]
            codes = list(COUNTRY_CODES_BY_CONTINENT.get(continent, []))
            return continent, codes

    if re.search(r"\bmiddle east\b", normalized):
        return "Middle East", list(MIDDLE_EAST_CODES)

    return None, []


def detect_categories(normalized: str) -> list[str]:
    found: list[str] = []

    for pattern, category in CATEGORY_PATTERNS:
        if category in found:
            continue
        if pattern.search(normalized):
            found.append(category)

    return found[:3]


def detect_min_importance(normalized: str) -> int | None:
    explicit = re.search(
        r"importance\s*(?:of\s*)?(?:above|over|at least|greater than|>=|>|:)?\s*(\d{1,2})",
        normalized,
    )
    if explicit:
        value = int(explicit.group(1))
        if 1 <= value <= 10:
            return value

    slash = re.search(r"\b(\d{1,2})\s*/\s*10\b", normalized)
    if slash:
        value = int(slash.group(1))
        if 1 <= value <= 10:
            return value

    if any(
        re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", normalized)
        for term in IMPORTANCE_TOP_TERMS
    ):
        return 8

    if any(
        re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", normalized)
        for term in IMPORTANCE_MAJOR_TERMS
    ):
        return 6

    if any(
        re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", normalized)
        for term in IMPORTANCE_MEDIUM_TERMS
    ):
        return 5

    return None


def detect_time_range(normalized: str) -> tuple[str | None, str | None, str | None]:
    """Return ``(date_from, date_to, label)`` as ISO strings."""
    now = datetime.now(timezone.utc)

    def iso(moment: datetime) -> str:
        return moment.astimezone(timezone.utc).isoformat()

    between = re.search(r"\bbetween\s+(\d{4}-\d{2}-\d{2})\s+and\s+(\d{4}-\d{2}-\d{2})\b", normalized)
    if between:
        try:
            start = datetime.fromisoformat(between.group(1)).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(between.group(2)).replace(tzinfo=timezone.utc) + timedelta(days=1)
            return iso(start), iso(end), f"between {between.group(1)} and {between.group(2)}"
        except ValueError:
            pass

    if re.search(r"\blast 24 hours?\b|\bprevious 24 hours?\b", normalized):
        return iso(now - timedelta(hours=24)), None, "last 24 hours"

    since = re.search(r"\b(since|after)\s+(\d{4}-\d{2}-\d{2})", normalized)
    if since:
        try:
            start = datetime.fromisoformat(since.group(2)).replace(tzinfo=timezone.utc)
            return iso(start), None, f"since {since.group(2)}"
        except ValueError:
            pass

    explicit = re.search(
        r"\b(last|past|previous)\s+(\d{1,3})\s*(day|days|week|weeks|month|months)\b",
        normalized,
    )
    if explicit:
        amount = int(explicit.group(2))
        unit = explicit.group(3)
        if unit.startswith("week"):
            days = amount * 7
        elif unit.startswith("month"):
            days = amount * 30
        else:
            days = amount
        days = max(1, min(days, 365))
        return iso(now - timedelta(days=days)), None, f"last {days} days"

    month_match = re.search(
        r"\bin\s+(january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\b(?:\s+(\d{4}))?",
        normalized,
    )
    if month_match:
        month = MONTH_NAMES[month_match.group(1)]
        year = int(month_match.group(2)) if month_match.group(2) else now.year
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        last_day = monthrange(year, month)[1]
        end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
        return iso(start), iso(end), f"{month_match.group(1)} {year}"

    if re.search(r"\btoday\b", normalized):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return iso(start), None, "today"

    if re.search(r"\byesterday\b", normalized):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        return iso(start), iso(start + timedelta(days=1)), "yesterday"

    if re.search(
        r"\b(this week|past week|last week|previous week|last 7 days|past 7 days|"
        r"seven days|7 days)\b",
        normalized,
    ):
        return iso(now - timedelta(days=7)), None, "last 7 days"

    if re.search(
        r"\b(this month|past month|last month|previous month|last 30 days|"
        r"past 30 days|30 days)\b",
        normalized,
    ):
        return iso(now - timedelta(days=30)), None, "last 30 days"

    if re.search(
        r"\b(this year|past year|last year|last 12 months|past 12 months)\b", normalized
    ):
        return iso(now - timedelta(days=365)), None, "last 12 months"

    return None, None, None


def detect_question_type(
    normalized: str,
    countries: list[str],
    categories: list[str],
    min_importance: int | None,
) -> str:
    if any(re.search(pattern, normalized) for pattern in SOURCE_INTENT_PATTERNS):
        return "sources"

    if any(re.search(pattern, normalized) for pattern in DETAIL_INTENT_PATTERNS):
        return "event_details"

    comparison = bool(
        re.search(r"\b(compare|comparison|versus|vs\.?|compared to)\b", normalized)
        or (
            len(countries) >= 2
            and re.search(r"\b(how many|count|number of)\b", normalized)
        )
    )
    if comparison and len(countries) >= 2:
        return "comparison"

    if any(re.search(pattern, normalized) for pattern in TREND_INTENT_PATTERNS):
        return "historical"

    if re.search(r"\b(how many|count|number of|total)\b", normalized):
        return "aggregate"

    if re.search(
        r"\b(latest|most recent|recent|newest|right now|currently)\b", normalized
    ):
        return "latest"

    if re.search(r"\bwhat happened\b|\bwhat is happening\b", normalized):
        return "latest"

    if min_importance is not None and min_importance >= 5:
        return "importance"

    if countries:
        return "country"

    if categories:
        return "category"

    return "semantic"


def extract_keywords(normalized: str, filters: QueryFilters) -> list[str]:
    tokens = [
        token for token in tokenize(normalized) if token not in QUESTION_WORD_STOPWORDS
    ]

    excluded: set[str] = set()
    for code in filters.country_codes:
        for name, mapped in COUNTRY_ALIASES.items():
            if mapped == code:
                excluded.update(name.split())

    ordered: list[str] = []
    for token in tokens:
        if token in excluded or token in ordered:
            continue
        ordered.append(token)

    return ordered[:12]


def _is_follow_up(normalized: str, filters: QueryFilters) -> bool:
    if not normalized:
        return False

    if any(normalized.startswith(prefix) for prefix in FOLLOW_UP_PREFIXES):
        return True

    if filters.is_empty and len(normalized.split()) <= 6:
        return bool(
            re.search(
                r"\b(which|that|this|it|them|those|the (first|second|third|last|latest) one)\b",
                normalized,
            )
        )

    return False


def _plan_from_text(question: str) -> QueryPlan:
    normalized = normalize_question(question)
    country_codes = detect_countries(normalized)
    region, region_codes = detect_region(normalized)
    categories = detect_categories(normalized)
    min_importance = detect_min_importance(normalized)
    date_from, date_to, time_label = detect_time_range(normalized)
    out_of_scope, reason = detect_out_of_scope(normalized)

    filters = QueryFilters(
        country_codes=country_codes or (region_codes if region and not country_codes else []),
        region=region,
        categories=categories,
        min_importance=min_importance,
        date_from=date_from,
        date_to=date_to,
        time_range_label=time_label,
    )
    filters.keywords = extract_keywords(normalized, filters)

    question_type = detect_question_type(
        normalized,
        country_codes or filters.country_codes,
        categories,
        min_importance,
    )

    return QueryPlan(
        question=question,
        normalized=normalized,
        tokens=tokenize(normalized),
        question_type=question_type,
        filters=filters,
        comparison_countries=country_codes if question_type == "comparison" else [],
        wants_sources=question_type == "sources",
        follow_up=False,
        out_of_scope=out_of_scope,
        out_of_scope_reason=reason,
        prompt_injection_detected=detect_prompt_injection(normalized),
    )


def apply_overrides(plan: QueryPlan, overrides: QueryOverrides | None) -> QueryPlan:
    """Merge client-supplied filters over the parsed plan."""
    if overrides is None:
        return plan

    filters = plan.filters

    if overrides.country_code:
        filters.country_codes = [overrides.country_code]
    if overrides.category:
        filters.categories = [normalize_category(overrides.category)]
    if overrides.min_importance is not None:
        filters.min_importance = int(overrides.min_importance)
    if overrides.days:
        filters.date_from = (
            datetime.now(timezone.utc) - timedelta(days=int(overrides.days))
        ).isoformat()
        filters.time_range_label = f"last {int(overrides.days)} days"

    plan.filters = filters
    return plan


def inherit_context(plan: QueryPlan, previous: QueryPlan) -> QueryPlan:
    """Resolve follow-up questions by inheriting filters/tokens from the parent."""
    if not plan.follow_up or previous is None:
        return plan

    filters = plan.filters
    parent = previous.filters

    if not filters.country_codes:
        filters.country_codes = list(parent.country_codes)
    if not filters.categories:
        filters.categories = list(parent.categories)
    if filters.min_importance is None:
        filters.min_importance = parent.min_importance
    if not filters.date_from:
        filters.date_from = parent.date_from
    if not filters.date_to:
        filters.date_to = parent.date_to
    if not filters.region:
        filters.region = parent.region
    if not filters.time_range_label:
        filters.time_range_label = parent.time_range_label

    plan.filters = filters
    plan.tokens = list(dict.fromkeys(plan.tokens + previous.tokens))
    plan.filters.keywords = list(
        dict.fromkeys(plan.filters.keywords + [token for token in parent.keywords])
    )[:12]

    if plan.question_type in {"semantic", "country"}:
        plan.question_type = (
            "event_details" if plan.question_type == "event_details" else previous.question_type
        )

    return plan


def parse_query(
    question: str,
    conversation: list[ConversationTurn] | None = None,
    overrides: QueryOverrides | None = None,
    config: Settings | None = None,
) -> QueryPlan:
    """Parse a question into a deterministic :class:`QueryPlan`.

    ``conversation`` contains the *previous* turns only (the current question is
    passed separately), which keeps the API contract unambiguous.
    """
    config = config or global_settings
    max_turns = max(0, int(config.rag_max_conversation_turns))
    conversation = list(conversation or [])[-max_turns:] if max_turns else []

    plan = _plan_from_text(question)
    plan.follow_up = _is_follow_up(plan.normalized, plan.filters)

    if conversation:
        previous_user_turns = [
            turn.content for turn in conversation if turn.role == "user"
        ]
        if previous_user_turns:
            parent = _plan_from_text(previous_user_turns[-1])
            plan = inherit_context(plan, parent)

    return apply_overrides(plan, overrides)






