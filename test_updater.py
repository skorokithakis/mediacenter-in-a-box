"""Offline tests for the tag ranking in updater.py.

Each tag list is a small hand-written excerpt of the real registry listing for
that image, so the ranking is exercised against the shapes the registries
actually publish without touching the network.
"""
from typing import Optional

import pytest
from packaging.version import Version

from updater import filter_tags, parse_version, rank_tags


RANKING_CASES = [
    pytest.param(
        [
            "10.11.11",
            "10.11.11ubu2604-ls47",
            "10.11.10",
            "10.11.10ubu2604-ls46",
            "10.11.9",
            "10.11.9ubu2604-ls45",
            "10.10.7",
            "10.10.7ubu2404-ls44",
            "10.10.6",
            "12.0ubu2604-ls48",
        ],
        "12.0ubu2604-ls48",
        id="jellyfin",
    ),
    pytest.param(
        [
            "4.0.19",
            "4.0.19.2979-ls323",
            "4.0.19.2968-ls322",
            "4.0.18",
            "4.0.18.2948-ls321",
            "4.0.17",
            "4.0.16",
            "4.0.15.2898-ls316",
            "4.0.14",
            "4.0.10",
        ],
        "4.0.19",
        id="sonarr",
    ),
    pytest.param(
        [
            "3.27.0",
            "3.27",
            "3",
            "3.26.0",
            "3.26",
            "3.25.0",
            "3.24.0",
            "3.23.0",
            "3.22",
            "3.21.0",
        ],
        "3.27.0",
        id="maintainerr",
    ),
    pytest.param(
        [
            "1.43.4.10903-e5521bd8c",
            "1.43.3.10896-cb3ebc72d",
            "1.43.2.10808-9f8d5f4a2",
            "1.43.1.10611-1e8a7b3c9",
            "1.42.2.10156-f737b826c",
            "1.41.9.9961-46083195d",
            "1.41.8.9834-071366d65",
            "1.41.7.9823-59fe408f7",
            "1.41.6.9685-d301f511a",
            "1.41.5.9601-8b9c4c1f0",
        ],
        "1.43.4.10903-e5521bd8c",
        id="plex",
    ),
    pytest.param(
        [
            "1.43.4.9999-abcdef123",
            "1.43.4.10903-e5521bd8c",
            "1.43.3.10896-cb3ebc72d",
        ],
        "1.43.4.10903-e5521bd8c",
        id="plex-same-release-higher-build-longer-tag",
    ),
    pytest.param(
        [
            "8.7.2",
            "8.7",
            "8",
            "8.6.1",
            "8.6",
            "8.5.0",
            "8.4.0",
            "8.3.1",
            "8.2.0",
            "8.1.0",
        ],
        "8.7.2",
        id="recyclarr",
    ),
    pytest.param(
        [
            "2.18.1",
            "v2.18.1-ls244",
            "2.18.1-ls245",
            "2.18.0",
            "v2.18.0-ls243",
            "2.17.0",
            "v2.17.0-ls240",
            "2.16.1",
            "v2.16.1-ls238",
            "2.15.0",
        ],
        "2.18.1",
        id="tautulli",
    ),
]


@pytest.mark.parametrize("tags, expected", RANKING_CASES)
def test_ranking_picks_expected_release(tags: list[str], expected: str) -> None:
    assert rank_tags(tags)[0] == expected


PARSE_VERSION_CASES = [
    ("1.2.3", "1.2.3"),
    ("v2.18.1-ls244", "2.18.1"),
    ("1.43.0.10492-121068a07", "1.43.0.10492"),
    ("0.4.18-develop", "0.4.18"),
    ("12.0ubu2604-ls48", "12.0"),
    ("latest", None),
    ("sha-abc1234", None),
]


@pytest.mark.parametrize("tag, expected", PARSE_VERSION_CASES)
def test_parse_version_uses_numeric_prefix(tag: str, expected: Optional[str]) -> None:
    parsed = parse_version(tag)
    assert parsed == (Version(expected) if expected is not None else None)


def test_filter_tags_excludes_channel_names_case_insensitively() -> None:
    tags = ["13.0-NIGHTLY", "13.0-testing", "13.0-preview", "12.0ubu2604-ls48"]
    assert filter_tags(tags, "jellyfin") == ["12.0ubu2604-ls48"]


def test_filter_tags_keeps_readarr_develop_channel() -> None:
    assert filter_tags(["0.4.18-develop"], "readarr") == ["0.4.18-develop"]
