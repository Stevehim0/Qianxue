"""MemoryAPI自定义异常类。

提供清晰的错误分类和错误信息。
"""


class MemoryAPIError(Exception):
    """MemoryAPI 基础异常类。

    所有 API 层异常的基类，提供统一的错误处理接口。
    """

    def __init__(self, message: str):
        """初始化异常。

        Args:
            message: 错误消息
        """
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class InputError(MemoryAPIError):
    """输入参数错误。

    当用户提供的输入参数无效时抛出。
    """

    pass


class RecallError(MemoryAPIError):
    """召回操作错误。

    当召回层操作失败时抛出。
    """

    pass


class ConsolidationError(MemoryAPIError):
    """巩固操作错误。

    当巩固层操作失败时抛出。
    """

    pass


class StateError(MemoryAPIError):
    """状态操作错误。

    当状态层操作失败时抛出。
    """

    pass


class CoreError(MemoryAPIError):
    """核心层操作错误。

    当核心层操作失败时抛出。
    """

    pass
