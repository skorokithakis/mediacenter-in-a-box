#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests",
#     "pudb",
# ]
# ///
"""
Update all LinuxServer containers to their latest versions.
"""
import re
from typing import Optional

import requests


def get_latest_version(repo: str) -> Optional[str]:
    """Get the latest version tag for a LinuxServer repository."""
    url = f"https://hub.docker.com/v2/namespaces/linuxserver/repositories/{repo}/tags"
    version_tags = []

    while url:
        response = requests.get(url)
        if not response.ok:
            print(f"Failed to fetch tags for {repo}: {response.status_code}")
            return None

        data = response.json()
        if not data.get("results"):
            return None

        # Collect version tags from this page
        page_tags = [
            (result["name"], result["tag_last_pushed"])
            for result in data["results"]
            if result["name"] != "latest"
            and not any(
                x in result["name"]
                for x in ["dev", "alpha", "beta", "rc", "nightly", "unstable"]
            )
        ]
        version_tags.extend(page_tags)

        # If we found any valid versions, no need to check more pages
        if version_tags:
            break

        # Move to next page if available
        url = data.get("next")

    if not version_tags:
        return None

    # Sort by tag_last_pushed timestamp (newest first) and take the first tag name
    version_tags.sort(key=lambda x: x[1], reverse=True)
    return version_tags[0][0]  # Return just the tag name


with open("docker-compose.yml") as infile:
    compose = infile.read()

# Find all LinuxServer programs in the compose file
programs = re.findall("lscr.io/linuxserver/(.*?):.*$", compose, re.MULTILINE)

# Update each program's version
for program in programs:
    version = get_latest_version(program)
    if version:
        print(f"Updating {program} to version {version}")
        compose = re.sub(
            f"lscr.io/linuxserver/{program}:.*$",
            f"lscr.io/linuxserver/{program}:{version}",
            compose,
            flags=re.MULTILINE,
        )
    else:
        print(f"Failed to find version for {program}")

with open("docker-compose.yml", "w") as outfile:
    outfile.write(compose)
