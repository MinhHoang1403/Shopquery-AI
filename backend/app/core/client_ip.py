"""Accept a single normalized client IP only from explicitly trusted proxy peers."""

import ipaddress
import socket

from starlette.requests import Request

from app.core.config import Settings


def client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    trusted: set[str] = set()
    for host in settings.trusted_proxy_hosts:
        try:
            trusted.update(address[4][0] for address in socket.getaddrinfo(host, None))
        except OSError:
            continue
    if peer not in trusted:
        return peer
    try:
        return str(ipaddress.ip_address(request.headers.get("x-forwarded-for", "")))
    except ValueError:
        return peer
