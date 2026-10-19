"""Bound JSON requests before parsing; raw file streams are bounded in their route."""

import asyncio

from starlette.responses import JSONResponse

from app.core.config import get_settings


class GuestBodyLimit:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/guest/"):
            await self.app(scope, receive, send)
            return
        if scope["path"].startswith("/api/guest/files") or scope["method"] == "GET":
            await self.app(scope, receive, send)
            return
        chunks, size = [], 0
        try:
            async with asyncio.timeout(get_settings().guest_parse_timeout_seconds):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > 8192:
                        await JSONResponse({"detail": "Guest request body too large"}, 413)(
                            scope, receive, send
                        )
                        return
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await JSONResponse({"detail": "Guest request timed out"}, 408)(scope, receive, send)
            return
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
