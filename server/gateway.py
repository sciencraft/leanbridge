"""
gateway.py  只导出 router 和 scoped_log_handler
"""
import json
import asyncio
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from collections import defaultdict

router = APIRouter()


log_queues: defaultdict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

async def push_log(run_id: str, level: str, msg: str):
    # dt_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dt_str = time.strftime("%Y-%m-%d %H:%M:%S")
    await log_queues[run_id].put({"type": "mcp_log", "level": level, "msg": f'{dt_str}: {msg}'})


@router.get("/events")
async def sse_endpoint(run_id: str):
    q = log_queues[run_id]
    if q is None:
        raise HTTPException(status_code=404, detail="run_id not found")
    async def gen():
        yield ":ok\n\n"
        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), 5.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ":heartbeat\n\n"
        except asyncio.CancelledError:   # 客户端断开
            # 可选：从 log_queues 里 pop(run_id) 做清理
            raise

    return StreamingResponse(gen(), media_type="text/event-stream")