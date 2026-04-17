import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import structlog
import orjson

from src.config import get_settings
from src.redis_client import get_redis

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Evals Real-Time Streaming"])


@router.websocket("/runs/{run_id}/stream")
async def stream_run_progress(websocket: WebSocket, run_id: UUID):
    """
    Establish a WebSocket connection to stream real-time worker progress
    updates directly from the Redis Pub/Sub cluster.
    """
    settings = get_settings()
    
    await websocket.accept()
    log = logger.bind(run_id=str(run_id), client="websocket")
    log.info("websocket.connected")
    
    # Initialize the main Async Redis Client for PubSub
    redis = await get_redis()
    pubsub = redis.pubsub()
    channel = f"channel:run:{run_id}"

    try:
        # Subscribe to this specific run's channel
        await pubsub.subscribe(channel)
        log.info("websocket.subscribed", channel=channel)
        
        # Continuously listen to messages while the websocket is open
        async for message in pubsub.listen():
            # Check if websocket unexpectedly died
            if websocket.client_state == WebSocketState.DISCONNECTED:
                break
                
            if message["type"] == "message":
                try:
                    payload = orjson.loads(message["data"])
                    await websocket.send_json(payload)
                    
                    # If the task tells us it's entirely done natively via some payload flag
                    if payload.get("progress") == 100 and payload.get("worker_type") == "final_aggregator":
                        # We could optionally break here if we want automatic closure
                        pass
                        
                except Exception as e:
                    log.error("websocket.send_error", error=str(e))
                    
    except WebSocketDisconnect:
        log.info("websocket.disconnected_by_client")
    except Exception as exc:
        log.error("websocket.unexpected_error", error=str(exc))
    finally:
        # Cleanup
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass
            
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
