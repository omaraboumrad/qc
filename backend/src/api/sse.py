import asyncio
import json
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from ..services.metrics_collector import MetricsCollector
from ..services.influxdb_writer import InfluxDBWriter

sse_router = APIRouter()

# Shared instances
metrics_collector = MetricsCollector()
influx_writer = InfluxDBWriter()


@sse_router.get("/metrics/stream")
async def stream_metrics(request: Request):
    """
    Server-Sent Events endpoint for real-time metrics streaming

    Streams metrics every second to connected clients
    """

    async def event_generator():
        """Generate SSE events with metrics data"""
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    print("Client disconnected from SSE stream")
                    break

                # Collect metrics
                try:
                    metrics = await metrics_collector.collect_all()

                    # Write to InfluxDB asynchronously (fire and forget)
                    asyncio.create_task(
                        asyncio.to_thread(influx_writer.write_metrics, metrics)
                    )

                    # Convert to dict for JSON serialization
                    metrics_dict = metrics.model_dump()

                    # Yield SSE event
                    yield {
                        "event": "metrics",
                        "data": json.dumps(metrics_dict)
                    }

                except Exception as e:
                    print(f"Error collecting metrics: {e}")
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": str(e)})
                    }

                # Wait 1 second before next update
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            print("SSE stream cancelled")
        finally:
            print("SSE stream ended")

    return EventSourceResponse(event_generator())


@sse_router.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    influx_writer.close()
