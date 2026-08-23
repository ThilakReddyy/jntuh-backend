import re

import pytest

from subscriptions.topics import (
    DEGREES,
    normalize_degree,
    normalize_regulations,
    partition_into_conditions,
    result_topic_condition,
    result_topics_for_exam,
    topics_for_preference,
)

_FCM_TOPIC_CHARSET = re.compile(r"^[a-zA-Z0-9\-_.~%]+$")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("R18", ["r18"]),
        ("r18", ["r18"]),
        (" R18 ", ["r18"]),
        ("R18, R16", ["r16", "r18"]),
        ("R18/R16", ["r16", "r18"]),
        ("R18 & R16", ["r16", "r18"]),
        (None, []),
        ("", []),
        ("RCRV", []),
        ("Set-1", []),
        ("R1", []),
        ("R180", []),
    ],
)
def test_normalize_regulations(raw, expected):
    assert normalize_regulations(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("btech", "btech"),
        ("BTECH", "btech"),
        (" btech ", "btech"),
        ("b.tech", None),
        ("cse", None),
        (None, None),
        ("", None),
    ],
)
def test_normalize_degree(raw, expected):
    assert normalize_degree(raw) == expected


def test_degrees_are_the_six_known_values():
    assert DEGREES == {"btech", "bpharmacy", "mtech", "mpharmacy", "mba", "mca"}


def test_result_topics_for_exam_single_regulation():
    topics, pinned_count = result_topics_for_exam("btech", "R18")

    assert topics == [
        "result-updates",
        "result-updates-btech",
        "result-updates-r18",
        "result-updates-btech-r18",
    ]
    assert pinned_count == 2


def test_result_topics_for_exam_no_degree_or_regulation():
    topics, pinned_count = result_topics_for_exam(None, None)

    assert topics == ["result-updates"]
    assert pinned_count == 1


def test_result_topics_for_exam_regulation_only():
    topics, pinned_count = result_topics_for_exam(None, "R18")

    assert topics == ["result-updates", "result-updates-r18"]
    assert pinned_count == 1


def test_result_topics_for_exam_multi_regulation():
    topics, pinned_count = result_topics_for_exam("btech", "R18, R16")

    assert topics == [
        "result-updates",
        "result-updates-btech",
        "result-updates-r16",
        "result-updates-btech-r16",
        "result-updates-r18",
        "result-updates-btech-r18",
    ]
    assert pinned_count == 2


@pytest.mark.parametrize("degree,regulation", [(None, None), ("btech", None), (None, "R18"), ("btech", "R18")])
def test_every_generated_topic_matches_fcm_charset(degree, regulation):
    topics, _ = result_topics_for_exam(degree, regulation)
    for topic in topics:
        assert _FCM_TOPIC_CHARSET.match(topic)


def test_partition_into_conditions_never_exceeds_five_per_chunk():
    topics, pinned_count = result_topics_for_exam("btech", "R18, R16, R15, R13")
    chunks = partition_into_conditions(topics, pinned_count)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 5


def test_partition_into_conditions_pins_global_and_degree_to_first_chunk_only():
    topics, pinned_count = result_topics_for_exam("btech", "R18, R16, R15, R13")
    chunks = partition_into_conditions(topics, pinned_count)

    assert chunks[0][:2] == ["result-updates", "result-updates-btech"]
    for chunk in chunks[1:]:
        assert "result-updates" not in chunk
        assert "result-updates-btech" not in chunk


def test_partition_into_conditions_single_chunk_when_under_cap():
    topics, pinned_count = result_topics_for_exam("btech", "R18")
    chunks = partition_into_conditions(topics, pinned_count)

    assert chunks == [topics]


def test_partition_into_conditions_empty_input():
    assert partition_into_conditions([]) == []


def test_result_topic_condition_builds_or_expression():
    condition = result_topic_condition(["result-updates", "result-updates-btech"])

    assert condition == "'result-updates' in topics || 'result-updates-btech' in topics"


def test_result_topic_condition_rejects_over_cap():
    with pytest.raises(ValueError):
        result_topic_condition(["a", "b", "c", "d", "e", "f"])


def test_topics_for_preference_default_is_global():
    assert topics_for_preference([], []) == ["result-updates"]


def test_topics_for_preference_regulations_only():
    assert topics_for_preference([], ["r18", "r16"]) == [
        "result-updates-r16",
        "result-updates-r18",
    ]


def test_topics_for_preference_degrees_only():
    assert topics_for_preference(["btech", "mtech"], []) == [
        "result-updates-btech",
        "result-updates-mtech",
    ]


def test_topics_for_preference_cross_product():
    assert topics_for_preference(["btech", "mtech"], ["r18", "r22"]) == [
        "result-updates-btech-r18",
        "result-updates-btech-r22",
        "result-updates-mtech-r18",
        "result-updates-mtech-r22",
    ]


def test_topics_for_preference_deduplicates():
    assert topics_for_preference(["btech", "btech"], ["r18"]) == [
        "result-updates-btech-r18",
    ]


def test_topics_for_preference_rejects_over_cap():
    degrees = ["btech", "bpharmacy", "mtech", "mpharmacy", "mba", "mca"]
    regulations = ["r18", "r19", "r22", "r25", "r17"]
    # 6 x 5 = 30 is the cap, exactly at the limit, should not raise.
    topics_for_preference(degrees, regulations)

    with pytest.raises(ValueError):
        topics_for_preference(degrees, regulations + ["r13"])
