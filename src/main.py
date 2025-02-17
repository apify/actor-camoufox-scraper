import asyncio

from apify import Actor

from crawlee.browsers import BrowserPool
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext

from src.input_handling import ActorInputData

async def main() -> None:
    """Actor main function."""
    async with Actor:
        aid = await ActorInputData.from_input()

        camoufox_plugin = aid.camoufox_plugin_class()
        crawler = PlaywrightCrawler(
            max_requests_per_crawl=aid.max_requests_per_crawl,
            max_crawl_depth=aid.max_depth,
            proxy_configuration=aid.proxy_configuration,
            request_handler_timeout=aid.request_timeout,
            # Custom browser pool. This gives users full control over browsers used by the crawler.
            browser_pool=BrowserPool(plugins=[camoufox_plugin]),
        )

        crawler._http_client.ignore_http_error_status_codes = {403}

        @crawler.router.default_handler
        async def request_handler(context: PlaywrightCrawlingContext) -> None:
            # Process the request.
            context.log.info(f'Processing {context.request.url} ...')
            for i in range(15):
                image = await context.page.screenshot(full_page = True )
                kvs= await context.get_key_value_store()
                await kvs.set_value(f"{context.request.url}",image, content_type='image/png')
                await asyncio.sleep(aid.sleep_time_before_screenshot)

        await crawler.run(aid.start_urls)
