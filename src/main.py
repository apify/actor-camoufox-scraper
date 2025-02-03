from apify import Actor
from camoufox import AsyncNewBrowser
from typing_extensions import override

from crawlee._utils.context import ensure_context
from crawlee.browsers import PlaywrightBrowserPlugin, PlaywrightBrowserController, BrowserPool
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext

from src.input_handling import ActorInputData, execute_user_function


class CamoufoxPlugin(PlaywrightBrowserPlugin):
    """Example browser plugin that uses Camoufox Browser, but otherwise keeps the functionality of
    PlaywrightBrowserPlugin."""

    @ensure_context
    @override
    async def new_browser(self) -> PlaywrightBrowserController:
        if not self._playwright:
            raise RuntimeError('Playwright browser plugin is not initialized.')

        return PlaywrightBrowserController(
            browser=await AsyncNewBrowser(self._playwright, headless=True),
            max_open_pages_per_browser=1,  #  Increase, if camoufox can handle it in your usecase.
            header_generator=None,  #  This turns off the crawlee header_generation. Camoufox has its own.
        )


async def main() -> None:
    """Actor main function."""
    async with Actor:
        aid = await ActorInputData.from_input()

        crawler = PlaywrightCrawler(
            # Limit the crawl to max requests. Remove or increase it for crawling all links.
            max_crawl_depth=aid.max_depth,
            proxy_configuration=aid.proxy_configuration,
            request_handler_timeout=aid.request_timeout,
            # Custom browser pool. This gives users full control over browsers used by the crawler.
            browser_pool=BrowserPool(plugins=[CamoufoxPlugin()]),
        )

        @crawler.router.default_handler
        async def request_handler(context: PlaywrightCrawlingContext) -> None:
            # Process the request.
            Actor.log.info(f'Scraping {context.request.url} ...')
            await execute_user_function(context, aid.user_function)

            if aid.link_selector:
                await context.enqueue_links(selector=aid.link_selector, include=aid.link_patterns)

        await crawler.run(aid.start_urls)
