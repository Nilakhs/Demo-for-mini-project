# -*- coding: utf-8 -*-
"""
dashboard.py
============
FastAPI web dashboard for the Dependency-Aware Parallel Build Demonstration.

Architecture:
    C build subprocesses
          |
          v
    DependencyAwareScheduler  (runs in a background thread)
          |
          | event_callback  (non-blocking queue.put)
          v
    _event_queue  (thread-safe stdlib queue)
          |
          | asyncio drain task  (polls every 50 ms)
          v
    FastAPI  (async event loop)
          |
          | WebSocket broadcast
          v
    Browser Dashboard

The scheduler is the ONLY source of truth.
This file only routes events -- it makes no scheduling decisions.

Usage:
    python dashboard.py
    # then open http://127.0.0.1:8000
"""

import asyncio
import json
import os
import queue as stdlib_queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEMO_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(DEMO_DIR))

from demo_scheduler import DependencyAwareScheduler, build_tasks  # noqa: E402

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Dependency-Aware Build Dashboard")

# ---------------------------------------------------------------------------
# Shared state  (all mutations guarded by _state_lock)
# ---------------------------------------------------------------------------
_event_queue: stdlib_queue.Queue = stdlib_queue.Queue()
_task_states: dict = {}          # task_name -> last event dict
_build_running: bool = False
_state_lock = threading.Lock()


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self._connections: list = []
        self._asyncio_lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._asyncio_lock:
            self._connections.append(ws)
        # Send current snapshot so late-joining clients see the current state
        with _state_lock:
            snapshot = {
                "type":          "snapshot",
                "tasks":         dict(_task_states),
                "build_running": _build_running,
                "timestamp":     datetime.now().isoformat(),
            }
        try:
            await ws.send_text(json.dumps(snapshot))
        except Exception:
            pass

    async def disconnect(self, ws: WebSocket):
        async with self._asyncio_lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def broadcast(self, data: dict):
        text = json.dumps(data)
        async with self._asyncio_lock:
            dead = []
            for ws in self._connections:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in self._connections:
                    self._connections.remove(ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Background asyncio task: drain the stdlib queue and broadcast to WebSocket
# ---------------------------------------------------------------------------
async def _drain():
    """Continuously drain _event_queue and broadcast to all WebSocket clients."""
    while True:
        batch = []
        try:
            while True:
                batch.append(_event_queue.get_nowait())
        except stdlib_queue.Empty:
            pass

        for event in batch:
            # Keep snapshot up-to-date (for new WebSocket connections)
            if event.get("type") == "task_state":
                with _state_lock:
                    _task_states[event["task"]] = event
            await manager.broadcast(event)

        await asyncio.sleep(0.05)


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_drain())


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(DEMO_DIR / "static" / "index.html")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()   # keep-alive; client may send pings
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# API: run dependency-aware scheduler
# ---------------------------------------------------------------------------

@app.post("/api/run-scheduler")
def run_scheduler():
    global _build_running, _task_states
    with _state_lock:
        if _build_running:
            return JSONResponse({"error": "A build is already running."}, status_code=409)
        _build_running = True
        _task_states   = {}

    def _worker():
        global _build_running
        try:
            # Clean artifacts from any previous run
            subprocess.run(
                [sys.executable, str(DEMO_DIR / "clean_demo.py")],
                cwd=str(DEMO_DIR), capture_output=True,
            )

            _event_queue.put({
                "type":      "build_start",
                "mode":      "scheduler",
                "timestamp": datetime.now().isoformat(),
            })

            def _callback(event):
                """Put scheduler event into queue; non-blocking."""
                with _state_lock:
                    _task_states[event["task"]] = event
                _event_queue.put(event)

            tasks     = build_tasks()
            scheduler = DependencyAwareScheduler(
                tasks,
                work_dir=str(DEMO_DIR),
                event_callback=_callback,
            )
            success = scheduler.run()

            _event_queue.put({
                "type":      "build_complete",
                "success":   success,
                "timestamp": datetime.now().isoformat(),
            })
        finally:
            with _state_lock:
                _build_running = False

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}


# ---------------------------------------------------------------------------
# API: wrong-order demo
# ---------------------------------------------------------------------------

@app.post("/api/run-wrong-order")
def run_wrong_order():
    global _build_running, _task_states
    with _state_lock:
        if _build_running:
            return JSONResponse({"error": "A build is already running."}, status_code=409)
        _build_running = True
        _task_states   = {}

    def _worker():
        global _build_running
        exe_suffix = ".exe" if sys.platform == "win32" else ""
        try:
            subprocess.run(
                [sys.executable, str(DEMO_DIR / "clean_demo.py")],
                cwd=str(DEMO_DIR), capture_output=True,
            )

            _event_queue.put({
                "type":      "build_start",
                "mode":      "wrong_order",
                "timestamp": datetime.now().isoformat(),
            })

            # Signal the UI that we are *attempting* consumer_compile
            _event_queue.put({
                "type":         "task_state",
                "task":         "consumer_compile",
                "state":        "RUNNING",
                "timestamp":    datetime.now().isoformat(),
                "display_time": datetime.now().strftime("%H:%M:%S"),
                "duration":     None,
                "output":       "",
                "reason":       "Attempting compile before dependency is satisfied",
            })

            # Real GCC call -- will fail because generated_config.h does not exist
            result = subprocess.run(
                ["gcc", "consumer.c", "-o", "consumer" + exe_suffix],
                cwd=str(DEMO_DIR),
                capture_output=True,
                text=True,
            )
            err_text = (result.stdout + result.stderr).strip()

            _event_queue.put({
                "type":         "task_state",
                "task":         "consumer_compile",
                "state":        "FAILED",
                "timestamp":    datetime.now().isoformat(),
                "display_time": datetime.now().strftime("%H:%M:%S"),
                "duration":     None,
                "output":       err_text,
                "reason":       "generated_config.h does not exist",
            })

            _event_queue.put({
                "type":      "wrong_order_failure",
                "error":     err_text,
                "message":   (
                    "EXPECTED FAILURE: consumer.c depends on generated_config.h, "
                    "but the artifact has not been produced yet.\n\n"
                    "The GCC preprocessor cannot resolve the #include directive. "
                    "This is a real compiler error, not a simulation."
                ),
                "timestamp": datetime.now().isoformat(),
            })

            _event_queue.put({
                "type":      "build_complete",
                "success":   False,
                "timestamp": datetime.now().isoformat(),
            })

        finally:
            with _state_lock:
                _build_running = False

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}


# ---------------------------------------------------------------------------
# API: clean
# ---------------------------------------------------------------------------

@app.post("/api/clean")
def clean():
    global _task_states
    subprocess.run(
        [sys.executable, str(DEMO_DIR / "clean_demo.py")],
        cwd=str(DEMO_DIR), capture_output=True, text=True,
    )
    with _state_lock:
        _task_states = {}
    _event_queue.put({
        "type":      "clean_done",
        "timestamp": datetime.now().isoformat(),
    })
    return {"status": "cleaned"}


@app.get("/api/status")
def status():
    with _state_lock:
        return {
            "build_running": _build_running,
            "tasks":         dict(_task_states),
        }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    EQ = "=" * 60
    print()
    print(EQ)
    print("  Dependency-Aware Build Dashboard")
    print(EQ)
    print()
    print("  Open your browser:")
    print("  http://127.0.0.1:8000")
    print()
    print("  Press Ctrl+C to stop the server.")
    print()
    uvicorn.run("dashboard:app", host="127.0.0.1", port=8000, reload=False)
