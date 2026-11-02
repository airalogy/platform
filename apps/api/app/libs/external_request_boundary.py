"""Bound external input before JSON parsing; never log scientific request bodies."""

from starlette.responses import JSONResponse

MAX_EXTERNAL_BODY = 2 * 1024 * 1024


def is_external_path(path):
    return path.removeprefix("/api").startswith(("/mcp", "/external-access"))


class ExternalRequestBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not is_external_path(scope["path"]):
            return await self.app(scope, receive, send)
        # Buffer at most 2 MiB, including chunked bodies without Content-Length.
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_EXTERNAL_BODY:
                return await JSONResponse(
                    {"detail": {"code": "external_request_too_large"}}, 413
                )(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        async def private_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"no-store"),
                ]
            await send(message)

        return await self.app(scope, bounded_receive, private_send)
