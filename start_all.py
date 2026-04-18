"""Qianxue 一键启动器 - 单窗口管理所有服务."""

import asyncio
import sys
import signal
import os

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

PYTHON = os.environ.get("QIANXUE_PYTHON", sys.executable)

SERVICES = [
    {"name": "Memory API",  "tag": "MEM",  "color": "36", "delay": 0,
     "cmd": [PYTHON, "-m", "Memory.server"]},
    {"name": "Backend API", "tag": "API",  "color": "32", "delay": 3,
     "cmd": [PYTHON, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]},
    {"name": "Memory Web",  "tag": "MWEB", "color": "34", "delay": 0,
     "cmd": [PYTHON, "Memory/web/app.py"]},
    {"name": "Backend Web", "tag": "BWEB", "color": "33", "delay": 0,
     "cmd": [PYTHON, "backend/web/app.py"]},
    {"name": "Heartbeat",   "tag": "HB",   "color": "35", "delay": 0,
     "cmd": [PYTHON, "-m", "heartbeat"]},
]

processes: dict[str, asyncio.subprocess.Process] = {}
shutting_down = False


def tag(svc):
    c = svc["color"]
    return f"\033[{c}m[{svc['tag']}]\033[0m"


async def run_service(svc: dict):
    global shutting_down
    if svc["delay"]:
        await asyncio.sleep(svc["delay"])
    while not shutting_down:
        # limit restart attempts
        for attempt in range(3):
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
            proc = await asyncio.create_subprocess_exec(
                *svc["cmd"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            processes[svc["tag"]] = proc
            print(f"{tag(svc)} {svc['name']} started (PID {proc.pid})")
            try:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        print(f"{tag(svc)} {text}")
            except asyncio.CancelledError:
                pass
            finally:
                await proc.wait()
                processes.pop(svc["tag"], None)
            if proc.returncode is not None and not shutting_down:
                if attempt < 2:
                    print(f"{tag(svc)} {svc['name']} exited (code {proc.returncode}), restarting in 3s...")
                    await asyncio.sleep(3)
                else:
                    print(f"{tag(svc)} {svc['name']} exited (code {proc.returncode}), giving up after 3 attempts")
        break


async def shutdown():
    global shutting_down
    shutting_down = True
    print("\n\033[31m[SYS] Shutting down all services...\033[0m")
    for proc in processes.values():
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
    for proc in processes.values():
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
    print("\033[31m[SYS] All services stopped.\033[0m")


async def main():
    print("\033[1m========================================")
    print("  Qianxue AI QQ Chatbot - Start All")
    print("========================================\033[0m\n")

    tasks = [asyncio.create_task(run_service(svc)) for svc in SERVICES]

    print("""\033[2m  Backend API:  http://localhost:8000
  Backend Web:  http://localhost:5002
  Memory API:   http://localhost:8001
  Memory Web:   http://localhost:5001
  Press Ctrl+C to stop all services\033[0m
""")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
