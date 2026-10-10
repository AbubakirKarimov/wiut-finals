"""Validation of user-submitted URLs for POST /check: public https sites only.

Every address the host resolves to must be a public (global) IP, so the server cannot be
used to reach internal services. The same guard runs on every redirect hop of the crawl.
CHECK_ALLOW_PRIVATE_URLS=1 (local tests only) also allows http and private addresses.
"""

import ipaddress
import os
import socket
from urllib.parse import urlsplit


def allow_private() -> bool:
    return os.getenv("CHECK_ALLOW_PRIVATE_URLS", "").strip() == "1"


def validate_public_url(url: str) -> str:
    url = (url or "").strip()
    p = urlsplit(url)
    private_ok = allow_private()
    if p.scheme != "https" and not (private_ok and p.scheme == "http"):
        raise ValueError("Only https:// URLs can be checked.")
    if not p.hostname:
        raise ValueError("The URL has no host name.")
    if p.username or p.password:
        raise ValueError("URLs with a user name or password are not accepted.")
    if private_ok:
        return url
    if p.port not in (None, 443):
        raise ValueError("Only the standard https port (443) is allowed.")
    try:
        infos = socket.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"The host name {p.hostname!r} could not be resolved.") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError(f"{p.hostname!r} resolves to a non-public address; "
                             "only public websites can be checked.")
    return url
