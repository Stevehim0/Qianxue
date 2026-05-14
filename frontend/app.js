const chatContainer = document.getElementById('chat-container');
const inputArea = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const voiceToggle = document.getElementById('voice-toggle');
const voiceIcon = document.getElementById('voice-icon');

let ws = null;
let currentBotMsg = null;
let voiceEnabled = false;

// --- 流式音频播放（抖动缓冲 + 逐 chunk 调度） ---
let audioCtx = null;
const SAMPLE_RATE = 24000;
const PLAY_BUFFER_MIN = 2;     // 攒够 N 个 chunk 再开始播放（chunk≈50ms, 2×50ms=100ms 抖动缓冲）
let seqBuffers = {};            // seq -> { chunks:[], done:bool, scheduled:int, started:bool }
let nextPlaySeq = 0;
let sNextTime = 0;
let activeSources = [];        // 正在播放的 AudioBufferSourceNode，用于跨回复停掉旧音频

// --- WebSocket ---

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

// --- 消息处理 ---

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
            break;
        case 'audio_chunk':
            handleAudioChunk(msg.seq, msg.idx, msg.data);
            break;
        case 'audio_end':
            handleAudioEnd(msg.seq);
            break;
        case 'audio':
            // 兼容：完整音频（EdgeTTS fallback）
            handleLegacyAudio(msg.data);
            break;
        case 'done':
            finishBotMessage();
            break;
        case 'pong':
            break;
        case 'error':
            appendSystemMessage('错误: ' + msg.message);
            break;
    }
}

// --- 消息显示 ---

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

// --- 流式音频播放（抖动缓冲 + 逐 chunk 调度） ---

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
            // 攒够缓冲再开始
            if (entry.chunks.length >= PLAY_BUFFER_MIN) {
                entry.started = true;
                scheduleUnplayed(seq);
            }
        } else {
            // 已在播放，新 chunk 直接调度
            playChunk(samples);
            entry.scheduled++;
        }
    }
}

function handleAudioEnd(seq) {
    if (seqBuffers[seq]) seqBuffers[seq].done = true;
    // 短句可能凑不够缓冲就结束了，直接播放
    if (seq === nextPlaySeq && seqBuffers[seq] && !seqBuffers[seq].started) {
        seqBuffers[seq].started = true;
        scheduleUnplayed(seq);
    }
    advancePlayback();
}

function advancePlayback() {
    while (seqBuffers[nextPlaySeq]) {
        const entry = seqBuffers[nextPlaySeq];
        // 还没开始：检查缓冲是否足够
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

// --- 发送 ---

function sendMessage() {
    const text = inputArea.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

    ws.send(JSON.stringify({ type: 'message', content: text }));
    appendUserMessage(text);
    inputArea.value = '';
    inputArea.style.height = 'auto';
}

// --- UI 工具 ---

function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// --- 事件绑定 ---

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

// --- 语音开关 ---

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

// --- 启动 ---
connect();
