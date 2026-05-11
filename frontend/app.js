const chatContainer = document.getElementById('chat-container');
const inputArea = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const voiceToggle = document.getElementById('voice-toggle');
const voiceIcon = document.getElementById('voice-icon');

let ws = null;
let currentBotMsg = null;
let audioQueue = [];
let isPlayingAudio = false;
let voiceEnabled = false;

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
        case 'sentence':
            appendBotSentence(msg.text);
            break;
        case 'audio':
            queueAudio(msg.data);
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

function appendUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'message user';
    div.textContent = text;
    chatContainer.appendChild(div);
    scrollToBottom();
}

function appendBotSentence(text) {
    if (!currentBotMsg) {
        currentBotMsg = document.createElement('div');
        currentBotMsg.className = 'message bot';
        currentBotMsg.dataset.content = '';
        chatContainer.appendChild(currentBotMsg);
    }

    currentBotMsg.dataset.content += text;
    // 渲染：文本 + 闪烁光标
    currentBotMsg.innerHTML = escapeHtml(currentBotMsg.dataset.content) + '<span class="typing-cursor"></span>';
    scrollToBottom();
}

function finishBotMessage() {
    if (currentBotMsg) {
        // 移除光标，显示最终文本
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

// --- 音频播放 ---

function queueAudio(base64Mp3) {
    if (!voiceEnabled) return;
    audioQueue.push(base64Mp3);
    if (!isPlayingAudio) {
        playNextAudio();
    }
}

function playNextAudio() {
    if (audioQueue.length === 0) {
        isPlayingAudio = false;
        return;
    }
    isPlayingAudio = true;
    const b64 = audioQueue.shift();
    const bytes = atob(b64);
    const buf = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) buf[i] = bytes.charCodeAt(i);
    const blob = new Blob([buf], { type: 'audio/mp3' });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => {
        URL.revokeObjectURL(url);
        playNextAudio();
    };
    audio.onerror = () => {
        URL.revokeObjectURL(url);
        playNextAudio();
    };
    audio.play().catch(() => playNextAudio());
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
    if (!voiceEnabled) {
        // 关闭时清空队列，停止播放
        audioQueue = [];
        isPlayingAudio = false;
    }
});

// --- 启动 ---
connect();
