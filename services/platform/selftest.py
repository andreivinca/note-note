"""Timezone detection uses local region data, independently of UI locale."""
from pathlib import Path
import tempfile
import unittest

import region


class SystemRegion(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.zones = base / "usr/share/zoneinfo"
        self.zones.mkdir(parents=True)
        (self.zones / "zone.tab").write_text(
            "# IANA timezone countries\n"
            "RO\t+4426+02606\tEurope/Bucharest\n"
            "FR\t+4852+00220\tEurope/Paris\n"
            "DE\t+5230+01322\tEurope/Berlin\n"
            "SE\t+5920+01803\tEurope/Stockholm\n"
            "US\t+404251-0740023\tAmerica/New_York\n")
        (self.zones / "Europe").mkdir()
        for city in ("Bucharest", "Paris", "Berlin"):
            (self.zones / "Europe" / city).touch()
        (self.zones / "Europe/Stockholm").symlink_to("Berlin")
        (self.zones / "Romania").symlink_to("Europe/Bucharest")
        etc = base / "etc"
        etc.mkdir()
        self.localtime = etc / "localtime"
        self.timezone = etc / "timezone"

    def detect(self, environment=None):
        return region.detect(environment or {}, [self.zones], self.localtime, self.timezone)

    def test_flatpak_relative_localtime_link_ignores_english_locale(self):
        self.localtime.symlink_to("../usr/share/zoneinfo/Europe/Bucharest")
        self.assertEqual(self.detect({"LANG": "en_US.UTF-8", "LC_ALL": "C.UTF-8"}),
                         {"timeZone": "Europe/Bucharest", "countryCode": "RO"})

    def test_timezone_override_takes_precedence(self):
        self.localtime.symlink_to(self.zones / "Europe/Bucharest")
        for zone in ("Europe/Paris", ":Europe/Paris", ":" + str(self.zones / "Europe/Paris")):
            with self.subTest(zone=zone):
                self.assertEqual(self.detect({"TZ": zone})["countryCode"], "FR")

    def test_copied_localtime_uses_timezone_file(self):
        self.localtime.touch()
        self.timezone.write_text("Europe/Bucharest\n")
        self.assertEqual(self.detect()["countryCode"], "RO")

    def test_aliases_resolve_without_changing_listed_countries(self):
        self.assertEqual(self.detect({"TZ": "Romania"})["countryCode"], "RO")
        self.assertEqual(self.detect({"TZ": "Europe/Stockholm"})["countryCode"], "SE")

    def test_unknown_utc_and_invalid_timezones_do_not_invent_a_country(self):
        for zone in ("UTC", "Etc/UTC", "EEST", "", "Unknown/City", "../Europe/Bucharest", "/etc/passwd"):
            with self.subTest(zone=zone):
                self.assertEqual(self.detect({"TZ": zone})["countryCode"], "")
        self.assertEqual(self.detect(), {"timeZone": "", "countryCode": ""})

    def test_missing_timezone_database_does_not_invent_a_country(self):
        (self.zones / "zone.tab").unlink()
        self.assertEqual(self.detect({"TZ": "Europe/Bucharest"})["countryCode"], "")


if __name__ == "__main__":
    unittest.main()
