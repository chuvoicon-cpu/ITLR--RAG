"""Close suspended ASGI generators even when disconnect occurs during send()."""

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send


class ClosingStreamingResponse(StreamingResponse):
    def __init__(self, *args, release=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.release = release

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                with anyio.CancelScope(shield=True):
                    await self.body_iterator.aclose()
            finally:
                if self.release is not None:
                    with anyio.CancelScope(shield=True):
                        await anyio.to_thread.run_sync(self.release)
