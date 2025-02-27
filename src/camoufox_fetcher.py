from camoufox.pkgman import CamoufoxFetcher, Version
import requests


class VersionSpecificCamoufoxFetcher(CamoufoxFetcher):
    def set_specific_version(self, version: Version, url: str):
        self._version_obj = version
        self._url = url

    def fetch_latest_releases(self, n=3) -> list[Version]:
        latest_releases = []

        resp = requests.get(self.api_url, timeout=20)
        resp.raise_for_status()

        releases = resp.json()

        for release in releases:
            for asset in release["assets"]:
                if data := self.check_asset(asset):
                    latest_releases.append(data)
                    if len(latest_releases) >= n - 1:
                        break
        return latest_releases
