"""Forwarded identity must come from an explicitly trusted socket peer."""

import socket

import pytest
from starlette.requests import Request

from app.core.client_ip import client_ip
from app.core.config import Settings


@pytest.mark.parametrize(
    ("peer", "forwarded", "expected"),
    [
        ("172.20.0.4", "198.51.100.7", "198.51.100.7"),
        ("172.20.0.1", "198.51.100.7", "172.20.0.1"),
        ("127.0.0.1", "198.51.100.7", "127.0.0.1"),
        ("172.20.0.4", "198.51.100.7, 203.0.113.1", "172.20.0.4"),
        ("172.20.0.4", "invalid", "172.20.0.4"),
    ],
)
def test_trusts_only_the_configured_proxy_peer(monkeypatch, peer, forwarded, expected):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: [(2, 1, 6, "", ("172.20.0.4", 0))])
    request = Request(
        {
            "type": "http",
            "client": (peer, 1234),
            "headers": [(b"x-forwarded-for", forwarded.encode())],
        }
    )
    assert client_ip(request, Settings(_env_file=None, trusted_proxy_hosts=["web"])) == expected


def test_dns_failure_and_default_configuration_fail_closed(monkeypatch):
    def unavailable(*args):
        raise OSError("DNS unavailable")

    monkeypatch.setattr(socket, "getaddrinfo", unavailable)
    request = Request(
        {
            "type": "http",
            "client": ("172.20.0.4", 1234),
            "headers": [(b"x-forwarded-for", b"198.51.100.7")],
        }
    )
    for hosts in ([], ["web"]):
        assert (
            client_ip(request, Settings(_env_file=None, trusted_proxy_hosts=hosts)) == "172.20.0.4"
        )
