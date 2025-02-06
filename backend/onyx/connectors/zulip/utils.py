import time
from collections.abc import Callable
from typing import Any
from typing import Dict
from typing import Optional
from urllib.parse import quote

from onyx.utils.logger import setup_logger

logger = setup_logger()


class ZulipAPIError(Exception):
    def __init__(self, code: Any = None, msg: str | None = None) -> None:
        self.code = code
        self.msg = msg

    def __str__(self) -> str:
        return (
            f"Error occurred during Zulip API call: {self.msg}" + ""
            if self.code is None
            else f" ({self.code})"
        )


class ZulipHTTPError(ZulipAPIError):
    def __init__(self, msg: str | None = None, status_code: Any = None) -> None:
        super().__init__(code=None, msg=msg)
        self.status_code = status_code

    def __str__(self) -> str:
        return f"HTTP error {self.status_code} occurred during Zulip API call"


def __call_with_retry(fun: Callable, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    result = fun(*args, **kwargs)
    if result.get("result") == "error":
        if result.get("code") == "RATE_LIMIT_HIT":
            retry_after = float(result["retry-after"]) + 1
            logger.warn(f"Rate limit hit, retrying after {retry_after} seconds")
            time.sleep(retry_after)
            return __call_with_retry(fun, *args)
    return result


def __raise_if_error(response: dict[str, Any]) -> None:
    if response.get("result") == "error":
        raise ZulipAPIError(
            code=response.get("code"),
            msg=response.get("msg"),
        )
    elif response.get("result") == "http-error":
        raise ZulipHTTPError(
            msg=response.get("msg"), status_code=response.get("status_code")
        )


def call_api(fun: Callable, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    response = __call_with_retry(fun, *args, **kwargs)
    __raise_if_error(response)
    return response


def build_search_narrow(
    limit: int = 1000,
    anchor: str = "newest",
    apply_md: bool = True,
) -> dict[str, Any]:
    return {
        "anchor": anchor,
        "num_before": limit,
        "num_after": 0,
        "narrow": [],
        "client_gravatar": True,
        "apply_markdown": apply_md,
    }


def encode_zulip_narrow_operand(value: str) -> str:
    # like https://github.com/zulip/zulip/blob/1577662a6/static/js/hash_util.js#L18-L25
    # safe characters necessary to make Python match Javascript's escaping behaviour,
    # see: https://stackoverflow.com/a/74439601
    return quote(value, safe="!~*'()").replace(".", "%2E").replace("%", ".")


def get_web_link(message: Dict[str, Any], realm_url: str) -> str:
    """Generate a web link to the message using the correct realm URL."""
    # Remove /api/v1 or other API paths if present in realm_url
    base_url = realm_url.split('/api/')[0]
    
    # Ensure base_url doesn't end with a slash
    base_url = base_url.rstrip('/')
    
    # Construct the message link
    narrow = f"narrow/stream/{message['stream_id']}-{message.get('stream_name', '')}/topic/{message.get('subject', '')}/near/{message['id']}"
    
    # Return the full URL with the correct domain
    return f"{base_url}/#{narrow}"
