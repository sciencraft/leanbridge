from __future__ import annotations
import env_setup
from mcp.types import LoggingLevel
from mcp.types import LoggingMessageNotificationParams
from mcp.client.session import ClientSession
from datetime import timedelta

from agents.mcp.server import MCPServerSse
import gateway

def make_log_handler(run_id: str):
    async def _official_callback(params: LoggingMessageNotificationParams) -> None:
        await gateway.push_log(run_id, params.level.upper(), params.data.get("msg", ""))
    return _official_callback

class PatchedMCPServerSse(MCPServerSse):
    """
    继承官方 MCPServerSse
    """
    def __init__(self, *args, run_id: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_id = run_id

    async def connect(self) -> None:
        """Connect to the server."""
        self._log_cb = make_log_handler(self.run_id)
        try:
            transport = await self.exit_stack.enter_async_context(self.create_streams())
            # streamablehttp_client returns (read, write, get_session_id)
            # sse_client returns (read, write)

            read, write, *_ = transport

            session = await self.exit_stack.enter_async_context(
                ClientSession(
                    read,
                    write,
                    timedelta(seconds=self.client_session_timeout_seconds)
                    if self.client_session_timeout_seconds
                    else None,
                    logging_callback=self._log_cb,
                )
            )
            server_result = await session.initialize()
            self.server_initialize_result = server_result
            self.session = session
        except Exception as e:
            print(f"Error initializing MCP server: {e}")
            await self._log_cb(
                LoggingMessageNotificationParams(
                    level=LoggingLevel.ERROR,
                    data={"msg": f"Error initializing MCP server: {e}"}
                )
            )
            await self.cleanup()
            raise