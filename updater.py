#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "requests",
#     "packaging",
# ]
# ///
"""
Update all containers in docker-compose.yml to their latest versions.
"""
import re
import sys
from typing import Optional

import requests
from packaging.version import Version


# Tags containing these strings are always excluded. The `dev` exclusion is
# conditional on the repo name — readarr's stable channel is named "develop".
EXCLUDED_SUBSTRINGS = [
    "alpha",
    "beta",
    "rc",
    "nightly",
    "unstable",
    "edge",
    "preview",
    "testing",
    "snapshot",
    "prerelease",
]
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
    """Parse a tag into a Version, returning None if it has no numeric prefix.

    We match the leading `v?` plus the dotted numeric prefix and parse only
    that. This covers every tag shape the three former attempts handled: the
    plain `1.2.3`, the Plex build suffix in `1.43.0.10492-121068a07`, the
    readarr `0.4.18-develop` channel suffix, and linuxserver tags such as
    `12.0ubu2604-ls48` whose release lives entirely in the numeric prefix.
    """
    match = re.match(r"^v?(\d+(?:\.\d+)*)", tag)
    if match is None:
        return None
    return Version(match.group(1))


def filter_tags(tags: list[str], repo: str) -> list[str]:
    """Return only the tags that are valid version candidates.

    Applies the exclusion list and the version-like heuristic. Exclusions are
    matched against the lowercased tag so `13.0-NIGHTLY` is caught even though
    the exclusion list is lowercase. The `dev` substring is only excluded for
    repos other than readarr, because readarr's stable release channel is named
    `*-develop`.

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
        if tag.lower() not in EXCLUDED_EXACT
        and not any(exclusion in tag.lower() for exclusion in exclusions)
        and not re.search(r"-(?:amd64|arm64|armhf)$", tag)
        and is_version_like(tag)
    ]


def rank_tags(tags: list[str]) -> list[str]:
    """Rank valid version tags from best to worst, dropping unparseable ones.

    The four keys, in order of significance, all descending:

    1. The release version truncated to three components. The truncation
       treats the fourth component of a linuxserver tag as the upstream build
       number rather than a release, so `4.0.19` ties with `4.0.19.2979-ls323`
       and `12.0ubu2604-ls48` beats `10.11.11`. A longer release tuple sorts
       above its own prefix, so `3.27.0` beats the rolling tag `3.27`.
    2. The negative component count. Preferring fewer components breaks the
       release tie toward the plain tag (e.g. `4.0.19` over
       `4.0.19.2979-ls323`) so the compose file does not churn on every
       linuxserver rebuild.
    3. The parsed release version itself. Among tags with the same component
       count this picks the higher build, so `1.43.4.10903-e5521bd8c` beats
       `1.43.4.9999-abcdef123` instead of depending on the registry's response
       order.
    4. The negative tag length. The shorter tag wins the last tie, so `2.18.1`
       beats `v2.18.1-ls244`.
    """
    candidates: list[tuple[Version, str]] = []
    for tag in tags:
        version = parse_version(tag)
        if version is not None:
            candidates.append((version, tag))

    candidates.sort(
        key=lambda pair: (
            pair[0].release[:3],
            -len(pair[0].release),
            pair[0].release,
            -len(pair[1]),
        ),
        reverse=True,
    )
    return [tag for _, tag in candidates]


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
        # A registry failure must abort the run rather than look like a repo
        # with no tags, which would silently leave the compose file untouched.
        response.raise_for_status()

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
    token_response.raise_for_status()

    token = token_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    url: Optional[str] = f"https://ghcr.io/v2/{owner}/{repo}/tags/list"
    all_tags: list[str] = []

    while url:
        tags_response = requests.get(url, headers=headers)
        tags_response.raise_for_status()

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

    ranked_tags = rank_tags(candidate_tags)
    print(f"  Top candidates: {', '.join(ranked_tags[:3]) or 'none'}")
    return ranked_tags[0] if ranked_tags else None


def main() -> None:
    with open("docker-compose.yml") as infile:
        compose = infile.read()

    # Extract every unique image reference from the compose file.
    image_references = re.findall(r"^\s+image:\s+(\S+)", compose, re.MULTILINE)

    failed_images: list[str] = []

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
            failed_images.append(base)

    # Write what was resolved before failing, so a single unparseable image
    # does not discard the updates that did succeed.
    with open("docker-compose.yml", "w") as outfile:
        outfile.write(compose)

    if failed_images:
        print(
            f"Failed to find a valid version tag for: {', '.join(failed_images)}",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
