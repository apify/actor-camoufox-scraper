from __future__ import annotations

import re
from datetime import timedelta
from inspect import iscoroutinefunction
from re import Pattern
from typing import Callable, Sequence, cast

from crawlee import Glob
from crawlee.crawlers import PlaywrightCrawlingContext
from pydantic import BaseModel, ConfigDict, Field
from apify import Actor, ProxyConfiguration



USER_DEFINED_FUNCTION_NAME = 'page_function'

class ActorInputData(BaseModel):
    """Processed and cleaned inputs for the actor."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    start_urls: Sequence[str]
    link_selector: str = ''
    link_patterns: list[Pattern | Glob] = []
    max_depth: int = Field(0, ge=0)
    request_timeout: timedelta = Field(timedelta(seconds=10), gt=timedelta(seconds=0))
    proxy_configuration: ProxyConfiguration
    user_function: Callable

    @classmethod
    async def from_input(cls) -> ActorInputData:
        """Instantiate the class from Actor input."""
        actor_input = await Actor.get_input() or {}

        if not (start_urls := actor_input.get('startUrls', [])):
            Actor.log.error('No start URLs specified in actor input, exiting...')
            await Actor.exit(exit_code=1)

        if not (page_function := actor_input.get('pageFunction', '')):
            Actor.log.error('No page function specified in actor input, exiting...')
            await Actor.exit(exit_code=1)

        if (
            proxy_configuration := await Actor.create_proxy_configuration(
                actor_proxy_input=actor_input.get('proxyConfiguration')
            )
        ) is not None:
            aid = cls(
                start_urls=[start_url['url'] for start_url in start_urls],
                link_selector=actor_input.get('linkSelector', ''),
                link_patterns=[
                    re.compile(pattern) for pattern in actor_input.get('linkPatterns', ['.*'])
                ],  # default matches everything
                max_depth=actor_input.get('maxCrawlingDepth', 1),
                request_timeout=timedelta(seconds=actor_input.get('requestTimeout', 10)),
                proxy_configuration=proxy_configuration,
                user_function=await extract_user_function(page_function),
            )
        else:
            Actor.log.error('Creation of proxy configuration failed, exiting...')
            await Actor.exit(exit_code=1)

        Actor.log.debug(f'actor_input = {aid}')

        return aid


async def extract_user_function(page_function: str) -> Callable:
    """Extract the user-defined function using exec and returns it as a Callable.

    This function uses `exec` internally to execute the `user_function` code in a separate scope. The `user_function`
    should be a valid Python code snippet defining a function named `USER_DEFINED_FUNCTION_NAME`.

    Args:
        page_function: The string representation of the user-defined function.

    Returns:
        The extracted user-defined function.

    Raises:
        KeyError: If the function name `USER_DEFINED_FUNCTION_NAME` cannot be found.
    """
    scope: dict = {}
    exec(page_function, scope)

    try:
        user_defined_function = scope[USER_DEFINED_FUNCTION_NAME]
    except KeyError:
        Actor.log.error(f'Function name "{USER_DEFINED_FUNCTION_NAME}" could not be found, exiting...')
        await Actor.exit(exit_code=1)

    return cast(Callable, user_defined_function)


async def execute_user_function(context: PlaywrightCrawlingContext, user_defined_function: Callable) -> None:
    """Execute the user-defined function with the provided context and pushes data to the Actor.

    This function checks if the provided user-defined function is a coroutine. If it is, the function is awaited.
    If it is not, it is executed directly.

    Args:
        context: The context object to be passed as an argument to the function.
        user_defined_function: The user-defined function to be executed.

    Returns:
        None
    """
    if iscoroutinefunction(user_defined_function):
        result = await user_defined_function(context)
    else:
        result = user_defined_function(context)

    await Actor.push_data(result)