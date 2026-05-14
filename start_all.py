"""Qianxue 一键启动器 - 单窗口管理所有服务."""

import asyncio
import sys
import signal
import os

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

# 清除系统代理环境变量，防止 Clash/V2Ray 拦截服务间 localhost 通信。
# Discord 的代理通过 discord.yaml 的 proxy 字段 + discord.py 的 proxy 参数独立处理，
# 不依赖 HTTP_PROXY 环境变量，所以清除不影响 Discord。
for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(var, None)

# Discord 代理 — 只让后端的 Discord 连接走代理，其他服务直连
DISCORD_PROXY = os.environ.get("QIANXUE_DISCORD_PROXY", "")

PYTHON = os.environ.get("QIANXUE_PYTHON", "D:/Miniconda/envs/SpaceX/python.exe")

SERVICES = [
    # FasterQwenTTS — CUDA Graphs 加速, RTF ~2.2x, 流式 PCM
    {"name": "FasterQwenTTS", "tag": "TTS", "color": "35", "delay": 0,
     "wsl": True,
     "wsl_cmd": (
         "source /home/qianxue/miniconda/etc/profile.d/conda.sh && "
         "conda activate tts && "
         "cd /mnt/d/Code/Qianxue-master-git && "
         "HF_ENDPOINT=https://hf-mirror.com "
         "python tts_server.py --host 0.0.0.0 --port 8880"
     )},

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


def _handle_sigint(signum, frame):
    """Ctrl+C: 立即设置关闭标志，防止子进程退出后被自动重启。"""
    global shutting_down
    shutting_down = True
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, _handle_sigint)


def tag(svc):
    c = svc["color"]
    return f"\033[{c}m[{svc['tag']}]\033[0m"


async def wait_for_url(url: str, timeout: float = 60, interval: float = 1.0):
    """轮询等待 URL 返回 200。绕过系统代理直连 localhost。"""
    import urllib.request
    import urllib.error
    # 禁用代理，避免 Clash/V2Ray 等工具拦截 localhost 请求
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    elapsed = 0.0
    while elapsed < timeout:
        try:
            req = urllib.request.Request(url, method="GET")
            with opener.open(req, timeout=3):
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            await asyncio.sleep(interval)
            elapsed += interval
    return False


async def run_service(svc: dict):
    global shutting_down

    # Docker 容器服务：启动前清理同名旧容器
    if "docker" in svc.get("cmd", []):
        container_name = None
        for i, arg in enumerate(svc["cmd"]):
            if arg == "--name" and i + 1 < len(svc["cmd"]):
                container_name = svc["cmd"][i + 1]
                break
        if container_name:
            import subprocess
            try:
                subprocess.run(["docker", "rm", "-f", container_name],
                               capture_output=True, timeout=10)
            except Exception:
                pass

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
        # WSL 服务：通过 wsl 命令在 Ubuntu 中启动
        if svc.get("wsl"):
            for attempt in range(3):
                if shutting_down:
                    return
                env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                       "MSYS_NO_PATHCONV": "1", **svc.get("env", {})}
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "wsl", "-d", "Ubuntu", "--", "bash", "-c", svc["wsl_cmd"],
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        env=env,
                    )
                except FileNotFoundError:
                    print(f"{tag(svc)} {svc['name']} 启动失败: wsl 命令不可用，跳过此服务")
                    return
                processes[svc["tag"]] = proc
                print(f"{tag(svc)} {svc['name']} started via WSL (PID {proc.pid})")
                cancelled = False
                try:
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        text = line.decode("utf-8", errors="replace").rstrip()
                        if text:
                            print(f"{tag(svc)} {text}")
                except (asyncio.CancelledError, KeyboardInterrupt):
                    cancelled = True
                finally:
                    # 杀 wsl.exe 包装进程
                    try:
                        proc.terminate()
                    except ProcessLookupError:
                        pass
                    # 杀 WSL 内部的 Python 进程
                    try:
                        subprocess.run(
                            'wsl -d Ubuntu -- bash -c "pkill -f api.main"',
                            shell=True, timeout=10, capture_output=True
                        )
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        try:
                            proc.kill()
                        except ProcessLookupError:
                            pass
                    processes.pop(svc["tag"], None)
                if cancelled or shutting_down:
                    return
                if proc.returncode is not None and not shutting_down:
                    if attempt < 2:
                        print(f"{tag(svc)} {svc['name']} exited (code {proc.returncode}), restarting in 3s...")
                        for _ in range(30):
                            if shutting_down:
                                return
                            await asyncio.sleep(0.1)
                        if shutting_down:
                            return
                    else:
                        print(f"{tag(svc)} {svc['name']} exited (code {proc.returncode}), giving up after 3 attempts")
            break
        # limit restart attempts
        for attempt in range(3):
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                   "MSYS_NO_PATHCONV": "1", **svc.get("env", {})}
            try:
                proc = await asyncio.create_subprocess_exec(
                    *svc["cmd"],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                    cwd=svc.get("cwd"),
                )
            except FileNotFoundError:
                print(f"{tag(svc)} {svc['name']} 启动失败: 找不到命令 '{svc['cmd'][0]}'，跳过此服务")
                return
            processes[svc["tag"]] = proc
            print(f"{tag(svc)} {svc['name']} started (PID {proc.pid})")
            cancelled = False
            try:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        print(f"{tag(svc)} {text}")
            except (asyncio.CancelledError, KeyboardInterrupt):
                cancelled = True
                proc.terminate()
            finally:
                await proc.wait()
                processes.pop(svc["tag"], None)
            if cancelled or shutting_down:
                return
            if proc.returncode is not None and not shutting_down:
                if attempt < 2:
                    print(f"{tag(svc)} {svc['name']} exited (code {proc.returncode}), restarting in 3s...")
                    for _ in range(30):
                        if shutting_down:
                            return
                        await asyncio.sleep(0.1)
                    if shutting_down:
                        return
                else:
                    print(f"{tag(svc)} {svc['name']} exited (code {proc.returncode}), giving up after 3 attempts")
        break


async def shutdown():
    global shutting_down
    shutting_down = True
    import subprocess
    print("\n\033[31m[SYS] Shutting down...\033[0m")

    # 1. 先杀 WSL 里的 TTS（最难清理，放最前面）
    try:
        subprocess.run(
            'wsl -d Ubuntu -- bash -c "pkill -9 -f api.main"',
            shell=True, timeout=5, capture_output=True
        )
    except Exception:
        pass

    # 2. 通知后端优雅关闭
    import urllib.request
    import urllib.error
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request("http://localhost:8000/api/core/shutdown", method="POST")
        with opener.open(req, timeout=3):
            print("[SYS] 后端优雅关闭请求已发送")
    except Exception:
        pass

    # 3. 等后端进程退出
    api_proc = processes.get("API")
    if api_proc:
        try:
            await asyncio.wait_for(api_proc.wait(), timeout=5)
            print("[SYS] 后端已退出")
        except asyncio.TimeoutError:
            try:
                api_proc.kill()
            except ProcessLookupError:
                pass

    # 4. 终止其余所有子进程（不卡在 wait 上）
    for tag, proc in list(processes.items()):
        if tag == "API":
            continue
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    processes.clear()

    # 5. 按端口强制清理残留
    for port in (8000, 8001, 5001, 5002, 8880):
        try:
            result = subprocess.run(
                f'netstat -ano | findstr ":{port} " | findstr LISTENING',
                shell=True, capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit():
                        subprocess.run(f'taskkill /F /PID {pid}', shell=True, timeout=3)
        except Exception:
            pass

    # 6. 按进程 PID 强制清理残留子进程（兜底，不杀无关 Python）
    for pid in [p.pid for p in processes.values() if hasattr(p, 'pid')]:
        try:
            subprocess.run(f'taskkill /F /PID {pid}', shell=True, timeout=3, capture_output=True)
        except Exception:
            pass

    print("\033[31m[SYS] All services stopped.\033[0m")


async def main():
    global shutting_down
    print("\033[1m========================================")
    print("  Qianxue AI QQ Chatbot - Start All")
    print("========================================\033[0m\n")

    tasks = [asyncio.create_task(run_service(svc)) for svc in SERVICES]

    print("""\033[2m  Backend API:  http://localhost:8000
  Backend Web:  http://localhost:5002
  Memory API:   http://localhost:8001
  Memory Web:   http://localhost:5001
  Qwen3-TTS:    http://localhost:8880
  Local Chat:   http://localhost:8000/chat
  Press Ctrl+C to stop all services\033[0m
""")

    try:
        await asyncio.gather(*tasks)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        shutting_down = True
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
