#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "requests",
#     "pudb",
#     "packaging",
# ]
# ///
"""
Update all containers in docker-compose.yml to their latest versions.
"""
import re
from typing import Optional

import requests
from packaging.version import Version, InvalidVersion


# Tags containing these strings are always excluded. The `dev` exclusion is
# conditional on the repo name — readarr's stable channel is named "develop".
EXCLUDED_SUBSTRINGS = ["alpha", "beta", "rc", "nightly", "unstable", "edge"]
EXCLUDED_EXACT = {"latest"}


def is_version_like(tag: str) -> bool:
    """Return True if the tag looks like a version number.

    Tags such as `sha-abc1234`, `main`, `master`, or `develop` on their own
    are not version-like. We require that the tag, after stripping an optional
    leading `v`, starts with a digit.
    """
    stripped = tag.lstrip("v")
    return bool(stripped) and stripped[0].isdigit()


def parse_version(tag: str) -> Optional[Version]:
    """Parse a tag into a Version, returning None if all attempts fail.

    We strip a leading `v` because packaging.version.Version does not accept
    it, but it is a common convention in image tags.

    We try three forms in order, stopping at the first that parses:
    1. As-is (after `v` strip) — handles standard semver and PEP 440 tags.
    2. With a trailing `-[0-9a-f]+` hex suffix stripped — handles Plex-style
       build tags like `1.43.0.10492-121068a07` without mangling genuine
       pre-release labels like `1.2.3a1` (which parse fine in attempt 1).
    3. With a trailing `-develop` stripped — handles readarr's stable channel
       tag format `0.4.18-develop`, which is not valid PEP 440.
    """
    normalized = tag.lstrip("v")
    candidates = [
        normalized,
        re.sub(r"-[0-9a-f]+$", "", normalized),
        re.sub(r"-develop$", "", normalized),
    ]
    for candidate in candidates:
        try:
            return Version(candidate)
        except InvalidVersion:
            pass
    return None


def filter_tags(tags: list[str], repo: str) -> list[str]:
    """Return only the tags that are valid version candidates.

    Applies the exclusion list and the version-like heuristic. The `dev`
    substring is only excluded for repos other than readarr, because readarr's
    stable release channel is named `*-develop`.

    Architecture-specific tags (e.g. `1.43.0.10492-121068a07-amd64`) are
    excluded because they are duplicates of the multi-arch manifest tag and
    would otherwise compete with it during version sorting.
    """
    exclusions = list(EXCLUDED_SUBSTRINGS)
    if repo != "readarr":
        exclusions.append("dev")

    return [
        tag
        for tag in tags
        if tag not in EXCLUDED_EXACT
        and not any(exclusion in tag for exclusion in exclusions)
        and not re.search(r"-(?:amd64|arm64|armhf)$", tag)
        and is_version_like(tag)
    ]


def best_tag(tags: list[str]) -> Optional[str]:
    """Return the tag with the highest parsed version, or None if none parse."""
    candidates: list[tuple[Version, str]] = []
    for tag in tags:
        version = parse_version(tag)
        if version is not None:
            candidates.append((version, tag))

    if not candidates:
        return None

    # Sort descending by version; the tag string is used exactly as fetched.
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def fetch_dockerhub_tags(namespace: str, repo: str) -> list[str]:
    """Fetch tag names for a Docker Hub image via the Hub v2 API.

    lscr.io/linuxserver/* images are mirrored on Docker Hub under the
    `linuxserver` namespace, so we always query hub.docker.com regardless of
    whether the original reference used lscr.io or docker.io.

    Docker Hub returns tags in reverse chronological order and some repos have
    12,000+ tags. We cap at 3 pages (300 tags) because the latest version will
    always appear on the first page in practice; the extra pages are a margin
    for repos that publish many tags in a short burst.
    """
    url: Optional[str] = (
        f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repo}/tags"
        "?page_size=100"
    )
    all_tags: list[str] = []
    pages_fetched = 0

    while url and pages_fetched < 3:
        response = requests.get(url)
        if not response.ok:
            print(f"Failed to fetch tags for {namespace}/{repo}: {response.status_code}")
            return []

        data = response.json()
        results = data.get("results") or []
        all_tags.extend(result["name"] for result in results)
        url = data.get("next")
        pages_fetched += 1

    return all_tags


def fetch_ghcr_tags(owner: str, repo: str) -> list[str]:
    """Fetch all tag names for a GHCR image using anonymous token auth.

    GHCR requires a short-lived anonymous bearer token even for public images.
    The token endpoint returns a JSON object with a `token` field.

    GHCR paginates via OCI distribution-spec `Link` headers. `requests` parses
    these automatically into `response.links`, so we follow `rel="next"` until
    it is absent.
    """
    token_response = requests.get(
        f"https://ghcr.io/token?scope=repository:{owner}/{repo}:pull"
    )
    if not token_response.ok:
        print(f"Failed to get GHCR token for {owner}/{repo}: {token_response.status_code}")
        return []

    token = token_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    url: Optional[str] = f"https://ghcr.io/v2/{owner}/{repo}/tags/list"
    all_tags: list[str] = []

    while url:
        tags_response = requests.get(url, headers=headers)
        if not tags_response.ok:
            print(f"Failed to fetch GHCR tags for {owner}/{repo}: {tags_response.status_code}")
            return []

        all_tags.extend(tags_response.json().get("tags") or [])
        next_link = tags_response.links.get("next")
        url = f"https://ghcr.io{next_link['url']}" if next_link else None

    return all_tags


def get_latest_tag(image_reference: str) -> Optional[str]:
    """Return the latest version tag for the given image reference.

    Parses the registry, namespace/owner, and repo from the reference, fetches
    all tags from the appropriate registry, filters them, and returns the
    highest-versioned tag.
    """
    # Strip the existing tag to get the base reference.
    base, _, _ = image_reference.partition(":")

    if base.startswith("ghcr.io/"):
        # ghcr.io/{owner}/{repo}
        path = base[len("ghcr.io/"):]
        owner, _, repo = path.partition("/")
        raw_tags = fetch_ghcr_tags(owner, repo)
        candidate_tags = filter_tags(raw_tags, repo)
    elif base.startswith("lscr.io/linuxserver/"):
        # lscr.io is a mirror; the canonical tag list lives on Docker Hub.
        repo = base[len("lscr.io/linuxserver/"):]
        raw_tags = fetch_dockerhub_tags("linuxserver", repo)
        candidate_tags = filter_tags(raw_tags, repo)
    else:
        # Bare Docker Hub reference: {namespace}/{repo}
        namespace, _, repo = base.partition("/")
        raw_tags = fetch_dockerhub_tags(namespace, repo)
        candidate_tags = filter_tags(raw_tags, repo)

    return best_tag(candidate_tags)


with open("docker-compose.yml") as infile:
    compose = infile.read()

# Extract every unique image reference from the compose file.
image_references = re.findall(r"^\s+image:\s+(\S+)", compose, re.MULTILINE)

for image_reference in image_references:
    base, _, current_tag = image_reference.partition(":")
    print(f"Fetching latest tag for {base}...")
    latest_tag = get_latest_tag(image_reference)

    if latest_tag:
        if latest_tag != current_tag:
            print(f"  Updating {base}: {current_tag} → {latest_tag}")
        else:
            print(f"  {base} is already up to date ({current_tag}).")
        # Replace the full image reference so the tag is written exactly as
        # fetched, preserving any `v` prefix or other formatting the registry uses.
        compose = compose.replace(
            f"image: {image_reference}",
            f"image: {base}:{latest_tag}",
        )
    else:
        print(f"  Failed to find a valid version tag for {base}.")

with open("docker-compose.yml", "w") as outfile:
    outfile.write(compose)
