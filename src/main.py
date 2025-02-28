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
from src.handler_helpers import is_cloudflare, get_challenge_bounding_box
from src.input_handling import ActorInputData


@dataclasses.dataclass
class BlockedInfo:
    blocked_initially: int = 0
    blocked_after_challenge_click: int = 0
    blocked_without_challenge: int = 0
    can_get_through: int = 0
    failed_request: int = 0


async def main() -> None:
    """Actor main function."""
    async with Actor:
        aid = await ActorInputData.from_input()
        camoufox_plugin = aid.camoufox_plugin_class()

        fetcher = VersionSpecificCamoufoxFetcher()
        releases = fetcher.fetch_latest_releases(3)
        attempts_per_release = 5

        error_dataset = await Actor.open_dataset()
        error_kvs = await Actor.open_key_value_store()

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
                        max_request_retries=1,
                        proxy_configuration=aid.proxy_configuration,
                        request_handler_timeout=aid.request_timeout,
                        browser_pool=BrowserPool(plugins=[camoufox_plugin]),
                    )

                    async def failed_request_handler(
                        context: PlaywrightCrawlingContext, _: Exception
                    ):
                        context.log.info(f"Failed request: {context.request.url} ...")
                        blocked_summary[context.request.url].failed_request += 1

                    crawler._failed_request_handler = failed_request_handler
                    crawler._http_client._ignore_http_error_status_codes = {403}

                    @crawler.router.default_handler
                    async def request_handler(
                        context: PlaywrightCrawlingContext,
                    ) -> None:
                        try:
                            # Process the request.
                            context.log.info(f"Waiting for: {context.request.url} ...")
                            await asyncio.sleep(aid.sleep_time_before_challenge)

                            if await is_cloudflare(context.page):
                                blocked_summary[
                                    context.request.url
                                ].blocked_initially += 1
                                if bounding_dox := await get_challenge_bounding_box(
                                    context.page
                                ):
                                    context.log.info(
                                        f"Blocked. Try to click on challenge: {context.request.url} ..."
                                    )
                                    await context.page.mouse.click(
                                        bounding_dox["x"] + 30, bounding_dox["y"] + 30
                                    )
                                    await asyncio.sleep(10)

                                    if await is_cloudflare(context.page):
                                        blocked_summary[
                                            context.request.url
                                        ].blocked_after_challenge_click += 1
                                        context.log.info(
                                            f"Blocked after clicking on challenge: {context.request.url} ..."
                                        )
                                        return
                                else:
                                    context.log.info(
                                        f"Blocked without challenge: {context.request.url} ..."
                                    )
                                    blocked_summary[
                                        context.request.url
                                    ].blocked_without_challenge += 1
                                    return

                            context.log.info(
                                f"Not blocked for: {context.request.url} ..."
                            )
                            blocked_summary[context.request.url].can_get_through += 1
                        except Exception as e:
                            context.log.info(
                                f"Exception in handler: {context.request.url}"
                            )
                            data = {
                                "page:": context.request.url,
                                "binary": version_text,
                                "attempt": attempt,
                                "content": await context.page.content(),
                            }
                            # Errors go to unnamed default storages. No need to track them for long time.
                            await error_dataset.push_data(data)
                            context.log.info(f"Exception in handler (saved page)")
                            image = await context.page.screenshot(full_page=True)
                            await error_kvs.set_value(
                                slugify(
                                    f"{context.request.url}_{version_text}_{attempt}"
                                ),
                                image,
                                content_type="image/png",
                            )
                            context.log.info(f"Exception in handler (saved screenshot)")
                            raise

                    await crawler.run(aid.start_urls)

                finally:
                    await rq.drop()

            for page, blocked_info in blocked_summary.items():
                result_dataset = await Actor.open_dataset(
                    name=f"CamoufoxTester-{slugify(page)}"
                )
                await result_dataset.push_data(
                    {
                        "date:": datetime.now().date().isoformat(),
                        "Camoufox version:": version_text,
                        "blocked_without_click [%]": 100
                        * blocked_info.blocked_initially
                        / attempts_per_release,
                        "blocked_after_click [%]": 100
                        * blocked_info.blocked_after_challenge_click,
                        "blocked_without_challenge [%]": 100
                        * blocked_info.blocked_without_challenge
                        / attempts_per_release,
                        "can_get_through [%]": 100
                        * blocked_info.can_get_through
                        / attempts_per_release,
                        "failed_request [%]": 100
                        * blocked_info.failed_request
                        / attempts_per_release,
                    }
                )
