"""Result 类型 — success/error 包装，用于函数式错误处理。"""

from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Result(Generic[T]):
    """不可变结果包装。

    用法::

        def do_something() -> Result[int]:
            if ok:
                return Result.ok(42)
            return Result.err("something went wrong")

        r = do_something()
        if r.is_ok():
            print(r.value)
        else:
            print(r.error)
    """

    success: bool
    value: Optional[T] = None
    error: Optional[str] = None

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        """构造成功结果。"""
        return cls(success=True, value=value)

    @classmethod
    def err(cls, error: str) -> "Result[T]":
        """构造失败结果。"""
        return cls(success=False, error=error)

    def is_ok(self) -> bool:
        """是否成功。"""
        return self.success

    def is_err(self) -> bool:
        """是否失败。"""
        return not self.success
