"""SenseVoice STT HTTP 服务 — 最低延迟离线转写.

用法：
    pip install funasr torch torchaudio fastapi uvicorn
    python sensevoice_server.py

POST http://localhost:10096/stt
Body: 16kHz mono 16-bit PCM (raw bytes)
Response: {"text": "你好"}

比 WebSocket 少一次握手，延迟降低 ~2s。
"""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("sensevoice-server")

app = FastAPI(title="SenseVoice STT")

# ---------------------------------------------------------------------------
# 模型加载
# ---------------------------------------------------------------------------

_model = None


def get_model():
    global _model
    if _model is not None:
        return _model

    from funasr import AutoModel
    import torch

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    logger.info(f"加载 SenseVoiceSmall 模型 (device={device})...")
    _model = AutoModel(
        model="iic/SenseVoiceSmall",
        device=device,
        disable_update=True,
    )
    logger.info("SenseVoiceSmall 模型加载完成")
    return _model


# ---------------------------------------------------------------------------
# 推理端点
# ---------------------------------------------------------------------------

@app.post("/stt")
async def transcribe(request: Request):
    """转写 16kHz mono 16-bit PCM，返回文本。"""
    import re
    import numpy as np

    body = await request.body()
    if len(body) < 3200:
        return JSONResponse({"text": ""})

    t0 = time.monotonic()

    # PCM bytes → numpy float32
    audio = np.frombuffer(body, dtype=np.int16).astype(np.float32) / 32768.0

    # 在线程池中跑推理，不阻塞事件循环
    import asyncio
    loop = asyncio.get_event_loop()

    def _infer():
        model = get_model()
        result = model.generate(input=audio, language="auto", use_itn=True)
        if result and len(result) > 0:
            text = result[0].get("text", "")
            return re.sub(r'<\|[^|]*\|>', '', text).strip()
        return ""

    text = await loop.run_in_executor(None, _infer)
    dt = int((time.monotonic() - t0) * 1000)

    audio_ms = len(body) // 32
    logger.info(f"转写完成: {dt}ms, audio={audio_ms}ms → {text[:60]}")

    return JSONResponse({"text": text})


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.on_event("startup")
async def startup():
    """预加载模型。"""
    get_model()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sensevoice_server:app", host="0.0.0.0", port=10096, log_level="info")
