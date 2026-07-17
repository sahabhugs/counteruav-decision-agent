"""
工具注册中心
管理所有可用工具的注册、查找和执行。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心，管理 ReAct 引擎可用的所有工具。

    每个工具为一个可调用对象，接受参数字典，返回结果字典。
    结果字典格式：{"success": bool, "data": ..., "error": str (if failed)}
    """

    def __init__(self):
        # tool_name -> {"function": callable, "description": str}
        self._tools: Dict[str, dict] = {}

    def register(self, tool_name: str, tool_function: Callable, description: str) -> None:
        """注册一个工具。

        Args:
            tool_name: 工具名称（唯一标识，在 Action 解析时使用）。
            tool_function: 工具函数，签名为 func(args: dict) -> dict。
            description: 工具描述（将出现在系统提示词中）。
        """
        if tool_name in self._tools:
            logger.warning(f"工具 '{tool_name}' 已注册，将覆盖旧定义")
        self._tools[tool_name] = {
            "function": tool_function,
            "description": description,
        }
        logger.info(f"工具已注册: {tool_name}")

    def unregister(self, tool_name: str) -> bool:
        """注销一个工具。

        Args:
            tool_name: 工具名称。

        Returns:
            是否成功注销。
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.info(f"工具已注销: {tool_name}")
            return True
        return False

    def execute(self, tool_name: str, args: dict) -> dict:
        """执行指定工具。

        Args:
            tool_name: 工具名称。
            args: 工具参数字典。

        Returns:
            工具执行结果字典，包含 success、data、error 字段。
        """
        if tool_name not in self._tools:
            error_msg = f"工具 '{tool_name}' 未注册"
            logger.error(error_msg)
            return {"success": False, "data": None, "error": error_msg}

        tool_info = self._tools[tool_name]
        func = tool_info["function"]

        try:
            logger.info(f"执行工具: {tool_name}, 参数: {args}")
            result = func(args)
            if not isinstance(result, dict):
                result = {"success": True, "data": result, "error": ""}
            if "success" not in result:
                result["success"] = True
            if "error" not in result:
                result["error"] = ""
            logger.info(f"工具 {tool_name} 执行成功")
            return result
        except Exception as e:
            error_msg = f"工具 {tool_name} 执行异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "data": None, "error": error_msg}

    def get_descriptions(self) -> str:
        """获取所有已注册工具的格式化描述文本（用于系统提示词）。

        Returns:
            格式化的工具描述字符串。
        """
        if not self._tools:
            return "（暂无可用工具）"

        lines = ["【可用工具列表】", ""]
        for idx, (name, info) in enumerate(self._tools.items(), 1):
            lines.append(f"{idx}. {name}")
            lines.append(f"   描述: {info['description']}")
            lines.append("")

        return "\n".join(lines)

    def list_tools(self) -> list[str]:
        """列出所有已注册的工具名称。"""
        return list(self._tools.keys())

    def has_tool(self, tool_name: str) -> bool:
        """检查工具是否已注册。"""
        return tool_name in self._tools

    def get_tool_count(self) -> int:
        """返回已注册工具数量。"""
        return len(self._tools)
