"""相对时间格式化工具。

为 AI 上下文提供人类可读的相对时间标注，
帮助 LLM 准确感知事件发生的时间距离。
"""

from datetime import datetime, timedelta
from typing import Optional


def format_relative_time_for_display(iso_str: str, now: Optional[datetime] = None) -> str:
    """将 ISO 时间戳格式化为带相对时间标注的显示字符串。

    规则:
    - 同一天且 < 10分钟 → "14:30" (仅时间)
    - 同一天且 >= 10分钟 → "14:30 (23分钟前)"
    - 昨天 → "昨天 14:30"
    - 2-6天前 → "3天前 14:30"
    - >= 7天 → "03-01 14:30"

    Args:
        iso_str: ISO 格式的时间戳字符串
        now: 参考时间（默认为当前时间）

    Returns:
        格式化后的时间字符串
    """
    try:
        event_time = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        # 尝试截取前19个字符（去掉毫秒/时区等）
        try:
            event_time = datetime.fromisoformat(iso_str[:19])
        except (ValueError, TypeError):
            return "??"

    ref_time = now or datetime.now()
    delta = ref_time - event_time
    total_seconds = delta.total_seconds()

    # 未来时间（时钟偏移容差 60s）
    if total_seconds < -60:
        return event_time.strftime("%H:%M")

    # 同一天内
    if total_seconds < 0:
        total_seconds = 0

    days_diff = (ref_time.date() - event_time.date()).days

    if days_diff == 0:
        # 同一天
        minutes = int(total_seconds / 60)
        hhmm = event_time.strftime("%H:%M")
        if minutes < 10:
            return hhmm
        elif minutes < 60:
            return f"{hhmm} ({minutes}分钟前)"
        else:
            hours = minutes // 60
            return f"{hhmm} ({hours}小时前)"
    elif days_diff == 1:
        return f"昨天 {event_time.strftime('%H:%M')}"
    elif days_diff < 7:
        return f"{days_diff}天前 {event_time.strftime('%H:%M')}"
    else:
        return event_time.strftime("%m-%d %H:%M")


def format_gap(seconds: float) -> str:
    """将秒数格式化为人类可读的时间间隔。

    Args:
        seconds: 秒数

    Returns:
        如 "3分钟"、"2小时"、"1.5天"
    """
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        return f"{int(seconds / 60)}分钟"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}小时"
    else:
        return f"{seconds / 86400:.1f}天"
