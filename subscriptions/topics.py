"""FCM topic-naming contract for Android result-release broadcasts.

This is the single source of truth for how degree/regulation preferences map
to FCM topic names. Both the broadcaster (subscriptions/firebase_notification.py)
and the preference API (service/subscriptionService.py) import from here so the
client-facing and server-derived topic names can never drift apart.
"""

import re
from itertools import product

from config.settings import FCM_RESULTS_TOPIC

# Mirrors scrapers.resultNotificationScraper.categorize_degree(). Not derived
# from it directly to avoid importing the scraper module from a leaf package.
DEGREES: frozenset[str] = frozenset(
    {"btech", "bpharmacy", "mtech", "mpharmacy", "mba", "mca"}
)

_REGULATION_PATTERN = re.compile(r"^R\d{2}$")
_REGULATION_SPLIT_PATTERN = re.compile(r"[,/&]")

_MAX_CONDITION_TOPICS = 5
_MAX_PREFERENCE_TOPICS = 30


def normalize_degree(raw: str | None) -> str | None:
    """Return the canonical degree slug, or None if unrecognized."""
    if not raw:
        return None
    candidate = raw.strip().lower()
    return candidate if candidate in DEGREES else None


def normalize_regulations(raw: str | None) -> list[str]:
    """Extract every valid R\\d\\d regulation token from a free-text string.

    Never raises; unparseable input yields an empty list. This is the
    topic-explosion guard against garbage scraped values like "Set-1" or "RCRV".
    """
    if not raw:
        return []
    tokens = {
        token.strip().upper()
        for token in _REGULATION_SPLIT_PATTERN.split(raw)
        if _REGULATION_PATTERN.match(token.strip().upper())
    }
    return sorted(token.lower() for token in tokens)


def result_topics_for_exam(
    degree: str | None, regulation_raw: str | None
) -> tuple[list[str], int]:
    """Full topic set a newly-detected exam release should be broadcast to.

    Always includes the global topic. Adds the degree-only topic when the
    degree normalizes, and a (regulation-only, degree+regulation) pair for
    every regulation found in `regulation_raw`.

    Returns `(topics, pinned_count)`. `pinned_count` is how many leading
    entries are the global topic plus (if present) the degree-only topic —
    the entries `partition_into_conditions` must keep out of the spillable
    per-regulation remainder.
    """
    topics = [FCM_RESULTS_TOPIC]

    degree_slug = normalize_degree(degree)
    if degree_slug:
        topics.append(f"{FCM_RESULTS_TOPIC}-{degree_slug}")
    pinned_count = len(topics)

    for regulation_slug in normalize_regulations(regulation_raw):
        topics.append(f"{FCM_RESULTS_TOPIC}-{regulation_slug}")
        if degree_slug:
            topics.append(f"{FCM_RESULTS_TOPIC}-{degree_slug}-{regulation_slug}")

    return topics, pinned_count


def partition_into_conditions(
    topics: list[str], pinned_count: int = 1
) -> list[list[str]]:
    """Pack topics into chunks of at most 5 (FCM's per-condition topic cap).

    `topics[:pinned_count]` (the global topic, plus the degree-only topic
    when present — see `result_topics_for_exam`) is kept in the first chunk
    only and never repeated in later chunks, so a default "subscribed to
    all" device never receives more than one notification per release. Only
    per-regulation topics spill into additional chunks, which happens only
    for releases naming more regulations than fit alongside the pinned
    topics.
    """
    if not topics:
        return []

    pinned = topics[:pinned_count]
    remainder = topics[pinned_count:]

    chunks: list[list[str]] = []
    first_chunk = pinned + remainder[: _MAX_CONDITION_TOPICS - len(pinned)]
    chunks.append(first_chunk)
    rest = remainder[_MAX_CONDITION_TOPICS - len(pinned) :]

    for start in range(0, len(rest), _MAX_CONDITION_TOPICS):
        chunks.append(rest[start : start + _MAX_CONDITION_TOPICS])

    return chunks


def result_topic_condition(topics: list[str]) -> str:
    """Build an FCM `condition` expression OR-ing every topic together."""
    if len(topics) > _MAX_CONDITION_TOPICS:
        raise ValueError(
            f"FCM conditions support at most {_MAX_CONDITION_TOPICS} topics, got {len(topics)}"
        )
    return " || ".join(f"'{topic}' in topics" for topic in topics)


def topics_for_preference(degrees: list[str], regulations: list[str]) -> list[str]:
    """Client-facing subscription set for a saved degree/regulation preference.

    An empty list on either axis means "all" on that axis:
      - both empty            -> the global topic (default: everything)
      - only regulations set  -> one regulation-only topic per regulation
      - only degrees set      -> one degree-only topic per degree
      - both set              -> the degree x regulation cross product
    """
    if not degrees and not regulations:
        return [FCM_RESULTS_TOPIC]

    if not degrees:
        topics = {f"{FCM_RESULTS_TOPIC}-{r}" for r in regulations}
    elif not regulations:
        topics = {f"{FCM_RESULTS_TOPIC}-{d}" for d in degrees}
    else:
        if len(degrees) * len(regulations) > _MAX_PREFERENCE_TOPICS:
            raise ValueError(
                "Degree/regulation combination exceeds the maximum of "
                f"{_MAX_PREFERENCE_TOPICS} topics"
            )
        topics = {
            f"{FCM_RESULTS_TOPIC}-{d}-{r}" for d, r in product(degrees, regulations)
        }

    return sorted(topics)
