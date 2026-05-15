const chatContainer = document.getElementById('chat-container');
const inputArea = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const voiceToggle = document.getElementById('voice-toggle');
const voiceIcon = document.getElementById('voice-icon');
const micToggle = document.getElementById('mic-toggle');
const micIcon = document.getElementById('mic-icon');

let ws = null;
let currentBotMsg = null;
let voiceEnabled = false;

// --- 流式音频播放（抖动缓冲 + 逐 chunk 调度） ---
let audioCtx = null;
const SAMPLE_RATE = 24000;
const PLAY_BUFFER_MIN = 2;
let seqBuffers = {};
let nextPlaySeq = 0;
let sNextTime = 0;
let activeSources = [];

// --- 全双工语音 ---
let micMode = false;           // 语音对话模式
let micStream = null;          // MediaStream
let micAudioCtx = null;        // 用于采集的 AudioContext
let micProcessor = null;       // ScriptProcessorNode
let vadState = 'silence';      // 'silence' | 'speech'
let silenceFrames = 0;
const SILENCE_FRAME_THRESHOLD = 20;  // ~400ms at ~20ms/frame
const SPEECH_FRAME_THRESHOLD = 8;    // ~160ms to confirm speech start
let speechFrameCount = 0;
let voiceState = 'IDLE';       // IDLE | LISTENING | USER_SPEAKING | AI_THINKING | AI_SPEAKING
let audioChunks = [];          // 缓冲当前语音段的 PCM chunks
let sttPartialDiv = null;      // 显示中间转写结果的 div

// ================================================================
// WebSocket
// ================================================================

function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws/computer`);

    ws.onopen = () => {
        statusDot.classList.add('connected');
        statusText.textContent = '已连接';
        startPing();
    };

    ws.onclose = () => {
        statusDot.classList.remove('connected');
        statusText.textContent = '已断开';
        currentBotMsg = null;
        stopMicMode();
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {
        ws.close();
    };

    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        handleServerMessage(msg);
    };
}

let pingTimer = null;
function startPing() {
    clearInterval(pingTimer);
    pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
        }
    }, 30000);
}

// ================================================================
// 消息处理
// ================================================================

function handleServerMessage(msg) {
    switch (msg.type) {
        case 'token':
            appendBotToken(msg.text);
            break;
        case 'audio_begin':
            if (msg.seq === 0) {
                stopAllAudio();
                seqBuffers = {};
                nextPlaySeq = 0;
                sNextTime = 0;
            }
            seqBuffers[msg.seq] = { chunks: [], done: false, scheduled: 0, started: false };
            // AI 开始说话了
            if (micMode) {
                voiceState = 'AI_SPEAKING';
            }
            break;
        case 'audio_chunk':
            handleAudioChunk(msg.seq, msg.idx, msg.data);
            break;
        case 'audio_end':
            handleAudioEnd(msg.seq);
            break;
        case 'audio':
            handleLegacyAudio(msg.data);
            break;
        case 'done':
            finishBotMessage();
            if (micMode && voiceState === 'AI_SPEAKING') {
                voiceState = 'LISTENING';
            }
            break;
        case 'stt_final':
            handleSTTFinal(msg.text);
            break;
        case 'voice_ready':
            voiceState = 'LISTENING';
            break;
        case 'interrupt_ack':
            break;
        case 'pong':
            break;
        case 'error':
            appendSystemMessage('错误: ' + msg.message);
            break;
    }
}

// ================================================================
// 消息显示
// ================================================================

function appendUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'message user';
    div.textContent = text;
    chatContainer.appendChild(div);
    scrollToBottom();
}

function appendBotToken(token) {
    if (!currentBotMsg) {
        currentBotMsg = document.createElement('div');
        currentBotMsg.className = 'message bot';
        currentBotMsg.dataset.content = '';
        chatContainer.appendChild(currentBotMsg);
    }

    currentBotMsg.dataset.content += token;
    currentBotMsg.innerHTML = escapeHtml(currentBotMsg.dataset.content) + '<span class="typing-cursor"></span>';
    scrollToBottom();
}

function finishBotMessage() {
    if (currentBotMsg) {
        currentBotMsg.innerHTML = escapeHtml(currentBotMsg.dataset.content);
        currentBotMsg = null;
    }
    scrollToBottom();
}

function appendSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'message bot';
    div.style.color = 'var(--text-muted)';
    div.style.fontStyle = 'italic';
    div.textContent = text;
    chatContainer.appendChild(div);
    scrollToBottom();
}

// ================================================================
// 流式音频播放（抖动缓冲 + 逐 chunk 调度）
// ================================================================

function ensureAudioCtx() {
    if (!audioCtx || audioCtx.state === 'closed') {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: SAMPLE_RATE });
        seqBuffers = {};
        nextPlaySeq = 0;
        sNextTime = 0;
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
}

function pcmBase64ToFloat32(base64Data) {
    const binary = atob(base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const numSamples = bytes.length / 2;
    if (numSamples === 0) return null;
    const samples = new Float32Array(numSamples);
    const view = new DataView(bytes.buffer);
    for (let i = 0; i < numSamples; i++) {
        samples[i] = view.getInt16(i * 2, true) / 32768.0;
    }
    return samples;
}

function playChunk(samples) {
    const buf = audioCtx.createBuffer(1, samples.length, SAMPLE_RATE);
    buf.getChannelData(0).set(samples);
    const src = audioCtx.createBufferSource();
    src.buffer = buf;
    src.connect(audioCtx.destination);
    const t = Math.max(audioCtx.currentTime, sNextTime);
    src.start(t);
    sNextTime = t + buf.duration;
    activeSources.push(src);
    src.onended = () => {
        const i = activeSources.indexOf(src);
        if (i >= 0) activeSources.splice(i, 1);
    };
}

function stopAllAudio() {
    for (const src of activeSources) {
        try { src.stop(); } catch (_) {}
    }
    activeSources = [];
    sNextTime = 0;
}

function scheduleUnplayed(seq) {
    const entry = seqBuffers[seq];
    if (!entry) return;
    while (entry.scheduled < entry.chunks.length) {
        playChunk(entry.chunks[entry.scheduled]);
        entry.scheduled++;
    }
}

function handleAudioChunk(seq, idx, base64Data) {
    if (!voiceEnabled) return;
    ensureAudioCtx();
    const samples = pcmBase64ToFloat32(base64Data);
    if (!samples) return;
    if (!seqBuffers[seq]) seqBuffers[seq] = { chunks: [], done: false, scheduled: 0, started: false };
    seqBuffers[seq].chunks.push(samples);

    if (seq === nextPlaySeq) {
        const entry = seqBuffers[seq];
        if (!entry.started) {
            if (entry.chunks.length >= PLAY_BUFFER_MIN) {
                entry.started = true;
                scheduleUnplayed(seq);
            }
        } else {
            playChunk(samples);
            entry.scheduled++;
        }
    }
}

function handleAudioEnd(seq) {
    if (seqBuffers[seq]) seqBuffers[seq].done = true;
    if (seq === nextPlaySeq && seqBuffers[seq] && !seqBuffers[seq].started) {
        seqBuffers[seq].started = true;
        scheduleUnplayed(seq);
    }
    advancePlayback();
}

function advancePlayback() {
    while (seqBuffers[nextPlaySeq]) {
        const entry = seqBuffers[nextPlaySeq];
        if (!entry.started) {
            if (entry.chunks.length >= PLAY_BUFFER_MIN || entry.done) {
                entry.started = true;
            } else {
                break;
            }
        }
        scheduleUnplayed(nextPlaySeq);
        if (entry.done) {
            delete seqBuffers[nextPlaySeq];
            nextPlaySeq++;
        } else {
            break;
        }
    }
}

function handleLegacyAudio(base64Data) {
    if (!voiceEnabled) return;
    const bytes = atob(base64Data);
    const buf = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) buf[i] = bytes.charCodeAt(i);
    const blob = new Blob([buf], { type: 'audio/wav' });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    audio.onerror = () => URL.revokeObjectURL(url);
    audio.play().catch(() => {});
}

// ================================================================
// 发送
// ================================================================

function sendMessage() {
    const text = inputArea.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

    ws.send(JSON.stringify({ type: 'message', content: text }));
    appendUserMessage(text);
    inputArea.value = '';
    inputArea.style.height = 'auto';
}

// ================================================================
// 全双工语音 — 麦克风采集 + VAD
// ================================================================

async function startMicMode() {
    micMode = true;
    voiceState = 'IDLE';
    micIcon.textContent = '🎙️';
    document.body.classList.add('mic-active');

    try {
        micStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            }
        });
    } catch (e) {
        appendSystemMessage('无法访问麦克风: ' + e.message);
        stopMicMode();
        micToggle.checked = false;
        return;
    }

    // 采样率让浏览器决定（通常 48kHz），我们后面下采样到 16kHz
    micAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = micAudioCtx.createMediaStreamSource(micStream);
    const bufferSize = 2048;
    micProcessor = micAudioCtx.createScriptProcessor(bufferSize, 1, 1);

    micProcessor.onaudioprocess = (e) => {
        if (!micMode) return;
        const input = e.inputBuffer.getChannelData(0);
        const sampleRate = micAudioCtx.sampleRate;

        // 下采样到 16kHz
        const pcm16k = downsample(input, sampleRate, 16000);
        // Float32 → Int16
        const pcmInt16 = float32ToInt16(pcm16k);

        // 能量检测 VAD
        const rms = computeRMS(pcm16k);
        const isSpeech = rms > 0.025; // 阈值可调，0.025 过滤大多数环境噪音

        processVAD(isSpeech, pcmInt16);
    };

    source.connect(micProcessor);
    micProcessor.connect(micAudioCtx.destination);
    appendSystemMessage('语音对话已开启，可以说话了');
}

function stopMicMode() {
    micMode = false;
    voiceState = 'IDLE';
    vadState = 'silence';
    silenceFrames = 0;
    speechFrameCount = 0;
    audioChunks = [];
    micIcon.textContent = '🎤';
    document.body.classList.remove('mic-active');

    if (micProcessor) {
        micProcessor.disconnect();
        micProcessor = null;
    }
    if (micAudioCtx) {
        micAudioCtx.close();
        micAudioCtx = null;
    }
    if (micStream) {
        micStream.getTracks().forEach(t => t.stop());
        micStream = null;
    }
    removeSTTPartial();
}

function processVAD(isSpeech, pcmInt16) {
    if (vadState === 'silence' && isSpeech) {
        speechFrameCount++;
        if (speechFrameCount >= SPEECH_FRAME_THRESHOLD) {
            // 确认语音开始
            vadState = 'speech';
            silenceFrames = 0;
            speechFrameCount = 0;
            audioChunks = [];

            // 如果 AI 正在说话，打断
            if (voiceState === 'AI_SPEAKING') {
                stopAllAudio();
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'voice_start' }));
                }
                finishBotMessage();
            } else if (voiceState === 'AI_THINKING') {
                // AI 还没开始说话，取消当前处理
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'voice_start' }));
                }
                finishBotMessage();
            } else if (voiceState === 'LISTENING' || voiceState === 'IDLE') {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'voice_start' }));
                }
            }

            voiceState = 'USER_SPEAKING';
            showSTTPartial('正在听...');
        }
    } else if (vadState === 'speech') {
        if (isSpeech) {
            silenceFrames = 0;
            audioChunks.push(pcmInt16);

            // 发送音频 chunk
            if (ws && ws.readyState === WebSocket.OPEN) {
                const base64 = arrayBufferToBase64(pcmInt16.buffer);
                ws.send(JSON.stringify({ type: 'audio_input', data: base64 }));
            }
        } else {
            silenceFrames++;
            if (silenceFrames >= SILENCE_FRAME_THRESHOLD) {
                // 语音结束
                vadState = 'silence';
                silenceFrames = 0;

                // 发送结束信号（附带完整音频）
                if (ws && ws.readyState === WebSocket.OPEN) {
                    const completePCM = mergeAudioChunks();
                    const base64 = arrayBufferToBase64(completePCM.buffer);
                    ws.send(JSON.stringify({ type: 'voice_end', data: base64 }));
                }

                voiceState = 'AI_THINKING';
                showSTTPartial('正在识别...');
            }
        }
    } else {
        speechFrameCount = isSpeech ? 1 : 0;
    }
}

// ================================================================
// STT 结果显示
// ================================================================

function handleSTTFinal(text) {
    removeSTTPartial();
    appendUserMessage(text);
}

function showSTTPartial(text) {
    removeSTTPartial();
    sttPartialDiv = document.createElement('div');
    sttPartialDiv.className = 'message user stt-partial';
    sttPartialDiv.textContent = text;
    chatContainer.appendChild(sttPartialDiv);
    scrollToBottom();
}

function removeSTTPartial() {
    if (sttPartialDiv && sttPartialDiv.parentNode) {
        sttPartialDiv.parentNode.removeChild(sttPartialDiv);
    }
    sttPartialDiv = null;
}

// ================================================================
// 音频工具函数
// ================================================================

function downsample(float32Array, fromRate, toRate) {
    if (fromRate === toRate) return float32Array;
    const ratio = fromRate / toRate;
    const newLength = Math.round(float32Array.length / ratio);
    const result = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {
        const srcIdx = Math.round(i * ratio);
        result[i] = float32Array[Math.min(srcIdx, float32Array.length - 1)];
    }
    return result;
}

function float32ToInt16(float32Array) {
    const int16 = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
        const s = Math.max(-1, Math.min(1, float32Array[i]));
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16;
}

function computeRMS(float32Array) {
    let sum = 0;
    for (let i = 0; i < float32Array.length; i++) {
        sum += float32Array[i] * float32Array[i];
    }
    return Math.sqrt(sum / float32Array.length);
}

function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

function mergeAudioChunks() {
    let totalLength = 0;
    for (const chunk of audioChunks) {
        totalLength += chunk.length;
    }
    const merged = new Int16Array(totalLength);
    let offset = 0;
    for (const chunk of audioChunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
    }
    audioChunks = [];
    return merged;
}

// ================================================================
// UI 工具
// ================================================================

function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// ================================================================
// 事件绑定
// ================================================================

sendBtn.addEventListener('click', sendMessage);

inputArea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

inputArea.addEventListener('input', () => {
    inputArea.style.height = 'auto';
    inputArea.style.height = Math.min(inputArea.scrollHeight, 120) + 'px';
});

// 语音播放开关
voiceToggle.addEventListener('change', () => {
    voiceEnabled = voiceToggle.checked;
    voiceIcon.textContent = voiceEnabled ? '🔊' : '🔇';
    if (!voiceEnabled && audioCtx) {
        audioCtx.close();
        audioCtx = null;
        seqBuffers = {};
        nextPlaySeq = 0;
        sNextTime = 0;
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_voice', enabled: voiceEnabled }));
    }
});

// 语音对话开关
micToggle.addEventListener('change', () => {
    if (micToggle.checked) {
        startMicMode();
    } else {
        stopMicMode();
    }
});

// ================================================================
// 启动
// ================================================================

connect();
