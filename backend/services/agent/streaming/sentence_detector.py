"""句子边界检测器 — 流式 token 累加，检测完整句子后输出."""


class SentenceDetector:
    """有状态累加器：接收 streaming token，检测到完整句子时输出。

    边界字符与 send_message.py / send_voice.py 的 _SPLIT_PUNCTS 保持一致:
    。！？\n.!?
    """

    SENTENCE_ENDINGS = set('。！？\n.!?')

    def __init__(self):
        self._buffer: list[str] = []

    def feed(self, token: str) -> list[str]:
        """输入 token，返回检测到的完整句子列表。"""
        if not token:
            return []

        self._buffer.append(token)
        return self._flush_sentences()

    def flush(self) -> list[str]:
        """输出缓冲区剩余内容（无论是否以标点结尾）。"""
        text = ''.join(self._buffer).strip()
        self._buffer.clear()
        if text:
            return [text]
        return []

    def reset(self):
        """重置缓冲区。"""
        self._buffer.clear()

    def _flush_sentences(self) -> list[str]:
        """从缓冲区中提取完整句子。"""
        text = ''.join(self._buffer)

        sentences = []
        last_cut = 0
        for i, ch in enumerate(text):
            if ch in self.SENTENCE_ENDINGS:
                # 包含连续的边界字符
                end = i + 1
                while end < len(text) and text[end] in self.SENTENCE_ENDINGS:
                    end += 1
                sentence = text[last_cut:end].strip()
                if sentence:
                    sentences.append(sentence)
                last_cut = end

        if sentences:
            remaining = text[last_cut:]
            self._buffer = [remaining] if remaining else []

        return sentences
