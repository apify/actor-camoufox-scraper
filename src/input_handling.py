from __future__ import annotations

from datetime import timedelta
from typing import Sequence, cast

from camoufox import AsyncNewBrowser
from crawlee.browsers import PlaywrightBrowserPlugin, PlaywrightBrowserController
from pydantic import BaseModel, ConfigDict, Field
from apify import Actor, ProxyConfiguration


USER_DEFINED_FUNCTION_NAME = "page_function"


class ActorInputData(BaseModel):
    """Processed and cleaned inputs for the actor."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    camoufox_plugin_class: type[PlaywrightBrowserPlugin]
    start_urls: Sequence[str]
    sleep_time_before_challenge: int = Field(0, ge=0)
    request_timeout: timedelta = Field(timedelta(seconds=30), gt=timedelta(seconds=0))
    proxy_configuration: ProxyConfiguration

    @classmethod
    async def from_input(cls) -> ActorInputData:
        """Instantiate the class from Actor input."""
        actor_input = await Actor.get_input() or {}

        if not (start_urls := actor_input.get("startUrls", [])):
            Actor.log.error("No start URLs specified in actor input, exiting...")
            await Actor.exit(exit_code=1)

        if not (camoufox_plugin := actor_input.get("camoufoxPlugin", "")):
            Actor.log.error("No page function specified in actor input, exiting...")
            await Actor.exit(exit_code=1)

        if (
            proxy_configuration := await Actor.create_proxy_configuration(
                actor_proxy_input=actor_input.get("proxyConfiguration")
            )
        ) is not None:
            aid = cls(
                start_urls=[start_url["url"] for start_url in start_urls],
                sleep_time_before_challenge=actor_input.get(
                    "sleepTimeBeforeChallenge", 10
                ),
                max_requests_per_crawl=actor_input.get("maxRequestsPerCrawl", 5),
                request_timeout=timedelta(
                    seconds=actor_input.get("requestTimeout", 30)
                ),
                proxy_configuration=proxy_configuration,
                camoufox_plugin_class=extract_plugin_class(camoufox_plugin),
            )
        else:
            Actor.log.error("Creation of proxy configuration failed, exiting...")
            await Actor.exit(exit_code=1)

        Actor.log.debug(f"actor_input = {aid}")

        return aid


def extract_plugin_class(camoufox_plugin) -> PlaywrightBrowserPlugin:
    scope: dict = {
        "PlaywrightBrowserPlugin": PlaywrightBrowserPlugin,
        "PlaywrightBrowserController": PlaywrightBrowserController,
        "AsyncNewBrowser": AsyncNewBrowser,
    }
    exec(camoufox_plugin, scope)

    plugin = scope["CamoufoxPlugin"]
    return cast(PlaywrightBrowserPlugin, plugin)
