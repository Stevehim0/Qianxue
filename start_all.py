"""Qianxue 一键启动器 - 单窗口管理所有服务."""

import asyncio
import sys
import signal
import os

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

PYTHON = os.environ.get("QIANXUE_PYTHON", sys.executable)

SERVICES = [
    # FunASR 语音识别 Server (D-03: SERVICES 第一项)
    # 阿里云镜像（中国大陆推荐）:
    #   registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13
    # Docker Hub 镜像（海外环境）:
    #   funasr/funasr:funasr-runtime-sdk-online-cpu-0.1.13
    # 注意: 首次运行需要下载模型（可能数分钟），不使用 wait_for (D-04)
    {"name": "FunASR Server", "tag": "ASR", "color": "35", "delay": 0,
     "cmd": ["docker", "run", "--rm", "--name", "funasr-server",
             "-p", "10095:10095",
             "registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13"]},
    {"name": "Memory API",  "tag": "MEM",  "color": "36", "delay": 0,
     "cmd": [PYTHON, "-m", "Memory.server"]},
    {"name": "Backend API", "tag": "API",  "color": "32", "delay": 0,
     "wait_for": "http://localhost:8001/health",
     "cmd": [PYTHON, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]},
    {"name": "Memory Web",  "tag": "MWEB", "color": "34", "delay": 0,
     "cmd": [PYTHON, "Memory/web/app.py"]},
    {"name": "Backend Web", "tag": "BWEB", "color": "33", "delay": 0,
     "cmd": [PYTHON, "backend/web/app.py"]},
]

MEM_READY_FLAG = asyncio.Event()

processes: dict[str, asyncio.subprocess.Process] = {}
shutting_down = False


def tag(svc):
    c = svc["color"]
    return f"\033[{c}m[{svc['tag']}]\033[0m"


async def wait_for_url(url: str, timeout: float = 60, interval: float = 1.0):
    """轮询等待 URL 可访问。"""
    import urllib.request
    import urllib.error
    elapsed = 0.0
    while elapsed < timeout:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            await asyncio.sleep(interval)
            elapsed += interval
    return False


async def run_service(svc: dict):
    global shutting_down

    # 等待依赖服务就绪
    wait_url = svc.get("wait_for")
    if wait_url:
        svc_tag = tag(svc)
        print(f"{svc_tag} 等待依赖服务就绪: {wait_url}")
        ok = await wait_for_url(wait_url)
        if not ok:
            print(f"{svc_tag} 依赖服务未就绪，超时跳过")
            return
        print(f"{svc_tag} 依赖服务已就绪，启动中...")

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
  FunASR ASR:   ws://localhost:10095
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
