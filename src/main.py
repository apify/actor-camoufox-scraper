import asyncio
import dataclasses
from collections import defaultdict
from datetime import datetime

from apify import Actor
from camoufox.addons import maybe_download_addons, DefaultAddons
from slugify import slugify

from crawlee.browsers import BrowserPool
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.storages import RequestQueue

from src.camoufox_fetcher import VersionSpecificCamoufoxFetcher
from src.input_handling import ActorInputData


@dataclasses.dataclass
class BlockedInfo:
    blocked_without_click_count: int = 0
    blocked_after_click_count: int = 0
    can_get_through: int = 0


async def main() -> None:
    """Actor main function."""
    async with Actor:
        aid = await ActorInputData.from_input()
        camoufox_plugin = aid.camoufox_plugin_class()

        fetcher = VersionSpecificCamoufoxFetcher()
        releases = fetcher.fetch_latest_releases(3)
        attempts_per_release = 5

        dataset = await Actor.open_dataset(name="CamoufoxTester")

        # Start one crawler for each release
        for release in releases:
            fetcher.set_specific_version(*release)

            fetcher.install()
            maybe_download_addons(list(DefaultAddons))

            blocked_summary = defaultdict(BlockedInfo)

            for attempt in range(1, attempts_per_release + 1):
                version_text = release[0].full_string

                rq = await RequestQueue.open(name=slugify(version_text))
                try:
                    crawler = PlaywrightCrawler(
                        request_manager=rq,
                        max_requests_per_crawl=aid.max_requests_per_crawl,
                        max_crawl_depth=aid.max_depth,
                        max_request_retries=1,
                        proxy_configuration=aid.proxy_configuration,
                        request_handler_timeout=aid.request_timeout,
                        browser_pool=BrowserPool(plugins=[camoufox_plugin]),
                    )

                    crawler._http_client._ignore_http_error_status_codes = {403}

                    @crawler.router.default_handler
                    async def request_handler(
                        context: PlaywrightCrawlingContext,
                    ) -> None:
                        # Process the request.
                        context.log.info(f"Waiting for: {context.request.url} ...")
                        await asyncio.sleep(aid.sleep_time_before_screenshot)
                        context.log.info(f"Screenshot of: {context.request.url} ...")
                        bounding_dox = await context.page.locator(
                            "css=.main-content div"
                        ).first.bounding_box()

                        if await context.page.get_by_text(
                            "Cloudflare"
                        ).first.all_inner_texts():
                            blocked_summary[
                                context.request.url
                            ].blocked_without_click_count += 1

                        await context.page.mouse.click(
                            bounding_dox["x"] + 30, bounding_dox["y"] + 30
                        )

                        await asyncio.sleep(10)

                        if await context.page.get_by_text(
                            "Cloudflare"
                        ).first.all_inner_texts():
                            blocked_summary[
                                context.request.url
                            ].blocked_after_click_count += 1
                            return

                        blocked_summary[context.request.url].can_get_through += 1

                    await crawler.run(aid.start_urls)

                finally:
                    await rq.drop()

            for page, blocked_info in blocked_summary.items():
                await dataset.push_data(
                    {
                        "date:": datetime.now().date().isoformat(),
                        "Camoufox binary": version_text,
                        "page:": page,
                        "blocked_without_click_count [%]": blocked_info.blocked_without_click_count
                        / attempts_per_release,
                        "blocked_after_click_count [%]": blocked_info.blocked_after_click_count
                        / attempts_per_release,
                        "can_get_through [%]": blocked_info.can_get_through
                        / attempts_per_release,
                    }
                )
