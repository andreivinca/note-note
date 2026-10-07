"""Resolve the system's named timezone to its country using local IANA data."""
import json
import os
from pathlib import Path
from zoneinfo import TZPATH


def zone_name(value, roots):
    value = value.removeprefix(":")
    if value.startswith("/"):
        path = Path(os.path.abspath(value))
        for root in roots:
            if path.is_relative_to(root):
                value = str(path.relative_to(root))
                break
        else:
            return ""
    for prefix in ("posix/", "right/"):
        value = value.removeprefix(prefix)
    if not value or any(part in ("", ".", "..") for part in value.split("/")):
        return ""
    return value


def system_timezone(environment, roots, localtime, timezone_file):
    if "TZ" in environment:
        return zone_name(environment["TZ"], roots)
    if localtime.is_symlink():
        target = os.readlink(localtime)
        return zone_name(str(localtime.parent / target), roots)
    try:
        return zone_name(timezone_file.read_text().strip(), roots)
    except OSError:
        return ""


def country_for_timezone(timezone, roots):
    if not timezone:
        return ""
    for root in roots:
        try:
            entries = (root / "zone.tab").read_text().splitlines()
        except OSError:
            continue
        countries = {}
        for entry in entries:
            if not entry or entry.startswith("#"):
                continue
            fields = entry.split()
            if len(fields) >= 3:
                countries[fields[2]] = fields[0]
        if timezone in countries:
            return countries[timezone]
        # Preserve listed zones before resolving links: slim tzdata may share
        # files between countries that currently have identical clock rules.
        canonical = (root / timezone).resolve()
        if canonical.is_relative_to(root):
            country = countries.get(str(canonical.relative_to(root)), "")
            if country:
                return country
    return ""


def detect(environment=None, roots=None, localtime=Path("/etc/localtime"), timezone_file=Path("/etc/timezone")):
    environment = os.environ if environment is None else environment
    roots = tuple(Path(path).absolute() for path in (TZPATH if roots is None else roots))
    timezone = system_timezone(environment, roots, localtime, timezone_file)
    return {"timeZone": timezone, "countryCode": country_for_timezone(timezone, roots)}


if __name__ == "__main__":
    print(json.dumps(detect()))
