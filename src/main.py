import asyncio

from apify import Actor
from slugify import slugify

from crawlee.browsers import BrowserPool
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.storages import RequestQueue

from src.camoufox_fetcher import VersionSpecificCamoufoxFetcher
from src.input_handling import ActorInputData

async def main() -> None:
    """Actor main function."""
    async with Actor:
        aid = await ActorInputData.from_input()
        camoufox_plugin = aid.camoufox_plugin_class()

        fetcher = VersionSpecificCamoufoxFetcher()
        releases = fetcher.fetch_latest_releases(3)

        # Start one crawler for each release
        for release in releases:
            version_text = release[0].full_string
            rq=await RequestQueue.open(name=slugify(version_text))
            fetcher.set_specific_version(*release)
            fetcher.install()
            crawler = PlaywrightCrawler(
                request_manager=rq,
                max_requests_per_crawl=aid.max_requests_per_crawl,
                max_crawl_depth=aid.max_depth,
                proxy_configuration=aid.proxy_configuration,
                request_handler_timeout=aid.request_timeout,
                # Custom browser pool. This gives users full control over browsers used by the crawler.
                browser_pool=BrowserPool(plugins=[camoufox_plugin]),
            )

            crawler._http_client._ignore_http_error_status_codes = {403}

            @crawler.router.default_handler
            async def request_handler(context: PlaywrightCrawlingContext) -> None:
                # Process the request.
                context.log.info(f'Waiting for: {context.request.url} ...')
                await asyncio.sleep(aid.sleep_time_before_screenshot)
                context.log.info(f'Screenshot of: {context.request.url} ...')
                image = await context.page.screenshot(full_page=True)
                kvs= await context.get_key_value_store()
                await kvs.set_value(slugify(f"{context.request.url}_{version_text}"),image, content_type='image/png')


            await crawler.run(aid.start_urls)

            await rq.drop()
