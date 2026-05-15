"""FasterQwenTTS — CUDA Graphs 加速, RTF ~2.2x, 流式 PCM.

基于 faster-qwen3-tts (pip install faster-qwen3-tts)
0.6B-Base + 预提取 speaker embedding，启动时一次性提取。

用法:
    HF_ENDPOINT=https://hf-mirror.com python tts_server.py --host 0.0.0.0 --port 8880
"""

import argparse
import asyncio
import io
import logging
import os
import queue
import threading
import time
import wave

import numpy as np
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("tts_server")

app = FastAPI(title="FasterQwenTTS Server")

# ---- 配置 ----
_HF_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
_REF_AUDIO = os.path.join(os.path.dirname(__file__), "ref_voice_clean.wav")
_LANGUAGE = "Chinese"
_TEMPERATURE = 0.6
_TOP_P = 0.85
_INSTRUCT = "请用自然、标准的普通话朗读，语速缓慢，注意在每个逗号和句号处停顿，不要赶"
_CHUNK_SIZE = 4

# ---- 全局状态 ----
_model = None
_voice_prompt = None
_SAMPLE_RATE = 24000
_model_lock = threading.Lock()


def _to_pcm16(pcm: np.ndarray) -> bytes:
    return np.clip(pcm * 32768, -32768, 32767).astype(np.int16).tobytes()


def _to_wav(pcm: np.ndarray, sr: int) -> bytes:
    raw = _to_pcm16(pcm)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(raw)
    return buf.getvalue()


def _mp3_to_wav(mp3_path: str, wav_path: str):
    """用 ffmpeg 把 mp3 转 wav（16kHz mono）。"""
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path, "-ar", "24000", "-ac", "1", wav_path],
        check=True, capture_output=True,
    )


@app.on_event("startup")
async def startup():
    global _model, _voice_prompt, _SAMPLE_RATE
    import torch
    from faster_qwen3_tts import FasterQwen3TTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading {_HF_MODEL} on {device}...")

    # 优先从本地路径加载，没有再从 HF 下载
    local_model = "/mnt/e/models/Qwen3-TTS-12Hz-0.6B-Base"
    model_path = local_model if os.path.isdir(local_model) else _HF_MODEL
    if model_path != _HF_MODEL:
        logger.info(f"Using local model: {model_path}")

    _model = FasterQwen3TTS.from_pretrained(
        model_path, device=device, dtype=torch.bfloat16,
    )
    _SAMPLE_RATE = _model.sample_rate

    # 提取 speaker embedding（一次性，~10 秒）
    logger.info("Extracting speaker embedding...")
    _ref_text_path = os.path.join(os.path.dirname(__file__), "ref_txt.txt")
    with open(_ref_text_path, encoding="utf-8") as f:
        ref_text = f.read().strip()

    logger.info("Extracting voice clone prompt (ICL mode)...")
    _voice_prompt = _model.model.create_voice_clone_prompt(
        ref_audio=_REF_AUDIO,
        ref_text=ref_text,
        x_vector_only_mode=False,
    )
    logger.info("Speaker embedding extracted.")

    # Warmup
    logger.info("Warmup...")
    try:
        for _ in _model.generate_voice_clone_streaming(
            text="预热文本。",
            language=_LANGUAGE,
            voice_clone_prompt=_voice_prompt,
            instruct=_INSTRUCT,
            chunk_size=_CHUNK_SIZE,
        ):
            pass
    except Exception as e:
        logger.warning(f"Warmup failed: {e}")
    logger.info(f"Ready. Sample rate: {_SAMPLE_RATE} Hz, chunk_size: {_CHUNK_SIZE}")

    # GPU keepalive
    if device != "cpu":
        _ka_tensor = torch.randn(512, 512, device=device)

        async def _gpu_keepalive():
            try:
                while True:
                    await asyncio.sleep(10)
                    with torch.inference_mode():
                        torch.matmul(_ka_tensor, _ka_tensor)
            except asyncio.CancelledError:
                pass

        asyncio.create_task(_gpu_keepalive())
        logger.info("GPU keepalive enabled (every 10s)")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/audio/speech")
async def synthesize(request: Request):
    body = await request.json()
    text = body.get("input", "")
    response_format = body.get("response_format", "wav")
    stream = body.get("stream", False)

    if not text.strip():
        return Response(status_code=400, content="empty input")

    if stream and response_format == "pcm":
        return StreamingResponse(
            _stream_pcm(text),
            media_type="application/octet-stream",
        )

    # 非流式
    loop = asyncio.get_event_loop()

    def _generate():
        with _model_lock:
            return _model.generate_voice_clone(
                text=text, language=_LANGUAGE,
                voice_clone_prompt=_voice_prompt,
                temperature=_TEMPERATURE, top_p=_TOP_P,
                instruct=_INSTRUCT,
            )

    audio_list, sr = await loop.run_in_executor(None, _generate)
    audio = np.concatenate(audio_list) if isinstance(audio_list, list) else audio_list

    if response_format == "wav":
        return Response(content=_to_wav(audio, sr), media_type="audio/wav")
    return Response(content=_to_pcm16(audio), media_type="application/octet-stream")


async def _stream_pcm(text: str):
    """流式合成 — Base 模型 + 预提取 embedding。"""
    t0 = time.time()
    first_chunk = True
    chunk_count = 0
    total_audio = 0.0
    q: queue.Queue = queue.Queue()
    _DONE = object()
    _exc: list[Exception] = []

    def _producer():
        try:
            with _model_lock:
                for chunk, sr, timing in _model.generate_voice_clone_streaming(
                    text=text, language=_LANGUAGE,
                    voice_clone_prompt=_voice_prompt,
                    temperature=_TEMPERATURE, top_p=_TOP_P,
                    instruct=_INSTRUCT,
                    chunk_size=_CHUNK_SIZE,
                ):
                    q.put((chunk, sr))
        except Exception as e:
            _exc.append(e)
        finally:
            q.put(_DONE)

    thread = threading.Thread(target=_producer, daemon=True)
    thread.start()

    loop = asyncio.get_event_loop()
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is _DONE:
            break
        chunk, sr = item
        chunk_count += 1
        total_audio += len(chunk) / sr
        if first_chunk:
            logger.info(f"TTFB: {time.time() - t0:.3f}s")
            first_chunk = False
        yield _to_pcm16(chunk)

    if _exc:
        raise _exc[0]

    total_time = time.time() - t0
    rtf = total_audio / total_time if total_time > 0 else 0
    logger.info(f"Done: {total_time:.2f}s audio={total_audio:.2f}s RTF={rtf:.2f}x chunks={chunk_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8880)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
