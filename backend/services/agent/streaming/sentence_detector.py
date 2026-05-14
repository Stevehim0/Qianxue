"""句子边界检测器 — 流式 token 累加，检测完整句子后输出."""


class SentenceDetector:
    """有状态累加器：接收 streaming token，检测到完整句子时输出。

    边界字符: ，。！？\n ,.!?
    拆分后 ，。 会被去掉，！？ 保留。

    首句优化（faster_first_response）：
    第一句在逗号处切断，不等句号，降低 TTS 首包延迟。
    """

    SENTENCE_ENDINGS = set('，。！？\n ,.!?')
    STRIP_ENDINGS = set('，。 ,.')
    COMMA_CHARS = set('，,')

    def __init__(self):
        self._buffer: list[str] = []
        self._first_sent: bool = False

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
        self._first_sent = False

    def _flush_sentences(self) -> list[str]:
        """从缓冲区中提取完整句子。"""
        text = ''.join(self._buffer)

        sentences = []
        last_cut = 0
        for i, ch in enumerate(text):
            if ch in self.SENTENCE_ENDINGS:
                end = i + 1
                while end < len(text) and text[end] in self.SENTENCE_ENDINGS:
                    end += 1
                sentence = text[last_cut:end].strip()
                if sentence:
                    # 去掉尾部的 ，。
                    while sentence and sentence[-1] in self.STRIP_ENDINGS:
                        sentence = sentence[:-1]
                    if sentence:
                        sentences.append(sentence)
                last_cut = end
                self._first_sent = True

        # 首句优化：还没发出过句子时，在逗号处切分
        if not self._first_sent and not sentences:
            for i, ch in enumerate(text):
                if ch in self.COMMA_CHARS:
                    end = i + 1
                    sentence = text[last_cut:end].strip()
                    if len(sentence) >= 2:
                        # 去掉尾部的 ，。
                        while sentence and sentence[-1] in self.STRIP_ENDINGS:
                            sentence = sentence[:-1]
                        if sentence:
                            sentences.append(sentence)
                        last_cut = end
                        self._first_sent = True
                        break

        if sentences:
            remaining = text[last_cut:]
            self._buffer = [remaining] if remaining else []

        return sentences
