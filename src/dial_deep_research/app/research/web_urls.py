"""Whether a URL is one a citation pill may open in a browser.

A module of its own because both the citation conversion and the data-query capture judge URLs by
this rule, and the capture module is imported by the conversion module.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# The schemes a citation pill may open. A web citation's URL is followed by the client in a new
# browser tab, so it has to be one the browser can resolve on its own.
_WEB_URL_SCHEMES = ("http", "https")


def is_web_url(url: str) -> bool:
    """Whether the URL is one a browser can open: absolute, `http` or `https`, with a host.

    Public because a caller resolving URLs has to refuse one this would reject, rather than hand
    over a URL whose citations then quietly keep their marker text.

    The metadata surfaces return a string and nothing else, so the URL's own form is what the app
    has to go on. A storage-relative `files/…` path, a scheme the client would not follow and a
    value that is not a URL at all are each treated as not openable — the conservative direction,
    since a pill that opens nothing is worse than a marker that at least names its source. A
    relative path in particular would make the client offer a file download rather than open a
    page.
    """
    parts = urlsplit(url)
    return parts.scheme.lower() in _WEB_URL_SCHEMES and bool(parts.netloc)
