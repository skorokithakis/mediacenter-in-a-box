#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "requests",
# ]
# ///
"""
Update all LinuxServer containers to their latest versions.
"""
import re

import requests

url = "https://fleet.linuxserver.io/api/v1/images"
response = requests.get(url)
data = response.json()
versions = {
    program["name"]: program["version"]
    for program in data["data"]["repositories"]["linuxserver"]
}

with open("docker-compose.yml") as infile:
    compose = infile.read()
programs = re.findall("lscr.io/linuxserver/(.*?):.*$", compose, re.MULTILINE)
for program in programs:
    version = versions[program]
    print(program, version)
    compose = re.sub(
        f"lscr.io/linuxserver/{program}:.*$",
        f"lscr.io/linuxserver/{program}:{version}",
        compose,
        flags=re.MULTILINE,
    )

with open("docker-compose.yml", "w") as outfile:
    outfile.write(compose)
