"""
ReAct（推理-行动）推理引擎
实现思考→行动→观察→思考的迭代推理循环，是 LLM Agent 的核心。
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from .config import config
    from .output_validator import OutputValidator
    from .tools.registry import ToolRegistry
except (ImportError, ValueError):
    from config import config  # type: ignore[no-redef]
    from output_validator import OutputValidator  # type: ignore[no-redef]
    from tools.registry import ToolRegistry  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# 停止标记
STOP_TOKENS = ["</decision>", "\n\n\n"]

# 超时决策模板
_TIMEOUT_DECISION_TEMPLATE = {
    "threat_assessment": {
        "threat_score": 0.85,
        "threat_level": 5,
        "confidence": 0.30,
        "key_factors": ["推理超时", "未完成分析"],
        "uncertainty_flags": ["数据不完整", "推理超时"],
    },
    "recommended_action": {
        "action_type": "全频段压制",
        "priority": 1,
        "devices": [],
        "parameters": {"reason": "推理超时，默认保守策略"},
        "expected_effect": "推理超时时的默认保守处置，全频段压制以确保安全",
        "alternative_actions": [],
    },
    "reasoning_chain": ["推理超时，系统自动生成保守决策"],
    "data_sources": ["系统超时保护机制"],
    "rule_proposal": None,
    "remarks": "警告：此决策由系统超时保护机制自动生成，置信度极低。请指挥员务必人工复核并确认。",
}


class ReActEngine:
    """ReAct 推理循环引擎。

    负责：
    1. 构建系统提示词（注入态势、工具、任务）
    2. 执行思考→行动→观察循环
    3. 从 LLM 输出中解析 Action 指令或 Final 答案
    4. 调用工具并整合结果
    5. 对最终输出进行校验
    6. 处理超时、最大轮次等边界情况
    """

    def __init__(
        self,
        cfg: Any,
        tools_registry: ToolRegistry,
        llm_instance: Any,
    ) -> None:
        """初始化 ReAct 引擎。

        Args:
            cfg: LLMAgentConfig 配置实例。
            tools_registry: 工具注册中心。
            llm_instance: llama.cpp 模型实例（提供 create_chat_completion 方法）。
        """
        self.cfg = cfg
        self.tools_registry = tools_registry
        self.llm = llm_instance
        self.validator = OutputValidator()

        # 加载提示词模板
        self._system_prompt_template = self._load_system_prompt()
        self._few_shot_examples = self._load_few_shot_examples()
        self._terminology = self._load_terminology()

        logger.info("ReAct 引擎初始化完成")

    # ==================== 主入口 ====================

    def run(self, task: str, situation: dict) -> dict:
        """运行 ReAct 推理循环。

        Args:
            task: 任务描述文本。
            situation: 当前态势信息字典（包含目标、环境、设备等完整上下文）。

        Returns:
            结构化决策字典。
        """
        start_time = time.monotonic()
        task_id = situation.get("task_id", situation.get("id", "unknown"))
        target_id = situation.get("target_id", situation.get("id", "unknown"))

        logger.info(f"ReAct 引擎启动: task_id={task_id}, task={task[:80]}...")

        # 构建系统提示词
        system_prompt = self._build_system_prompt(situation, task)

        # 初始化消息历史
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请分析以下任务并给出决策建议：\n\n任务：{task}"},
        ]

        # 将态势信息注入 context（供工具调用）
        tool_context = {"_situation": situation}

        round_num = 0
        final_decision: Optional[dict] = None

        while round_num < self.cfg.MAX_ROUNDS:
            elapsed = time.monotonic() - start_time
            if elapsed >= self.cfg.TIMEOUT_SECONDS:
                logger.warning(f"推理超时 ({elapsed:.2f}s > {self.cfg.TIMEOUT_SECONDS}s)")
                # 尝试从已有消息提取决策
                partial = self._extract_partial_decision(messages, task_id, target_id)
                if partial:
                    return partial
                return self._generate_timeout_decision(task_id, target_id)

            round_num += 1
            logger.info(f"--- ReAct 第 {round_num}/{self.cfg.MAX_ROUNDS} 轮 ---")

            # 调用 LLM
            response_text = self._call_llm(messages)
            if not response_text:
                logger.error("LLM 返回空响应")
                # 发送重试提示
                messages.append({
                    "role": "user",
                    "content": "上一条响应为空，请重新输出你的分析和行动。如果需要最终结论，请以 Final: 开头输出完整 JSON。",
                })
                continue

            # 添加到消息历史
            messages.append({"role": "assistant", "content": response_text})

            # 解析 LLM 输出
            if round_num < self.cfg.MAX_ROUNDS:
                # 尝试解析 Action
                action = self._parse_action(response_text)
                if action:
                    tool_name = action["tool"]
                    tool_args = action.get("args", {})
                    # 合并 tool context
                    tool_args.update(tool_context)

                    # 执行工具并获取结果
                    exec_result = self.tools_registry.execute(tool_name, tool_args)

                    # 格式化观察结果
                    observation = self._format_observation(tool_name, exec_result)
                    messages.append({"role": "user", "content": observation})
                    logger.info(f"工具 {tool_name} 执行完成，继续推理")
                    continue

            # 尝试解析 Final 答案
            final = self._parse_final(response_text)
            if final:
                # 在校验前补充缺失字段
                final = self._ensure_fields(final, task_id, target_id)
                valid, errors = self.validator.validate(final)
                if valid:
                    final_decision = final
                    logger.info(f"ReAct 引擎获得有效最终决策 (第{round_num}轮)")
                    break
                else:
                    logger.warning(f"最终决策校验失败 ({len(errors)} 个错误): {errors}")
                    # 将校验错误反馈给 LLM
                    error_feedback = (
                        f"上一轮输出的决策 JSON 校验失败，请修正以下问题并重新输出：\n"
                        + "\n".join(f"- {e}" for e in errors)
                        + "\n\n请以 Final: 开头输出修正后的完整 JSON。"
                    )
                    messages.append({"role": "user", "content": error_feedback})
                    continue

            # 未解析到 Action 或 Final，LLM 输出的是中间推理
            # 提示 LLM 继续
            if round_num < self.cfg.MAX_ROUNDS:
                messages.append({
                    "role": "user",
                    "content": (
                        "请继续你的推理。如果已准备好给出最终决策，请以 Final: 开头输出完整 JSON。"
                        "如需调用工具获取更多信息，请以 Action: 工具名(参数) 格式指定。"
                    ),
                })

        # 循环结束
        elapsed = time.monotonic() - start_time

        if final_decision:
            final_decision["reasoning_chain"].append(
                f"推理完成：共 {round_num} 轮，耗时 {elapsed:.2f}s"
            )
            logger.info(f"ReAct 引擎完成: {round_num} 轮, {elapsed:.2f}s")
            return final_decision

        # 达到最大轮次但无有效决策，强制生成
        logger.warning("达到最大轮次，强制要求 LLM 给出最终决策")
        return self._generate_max_rounds_decision(messages, task_id, target_id)

    # ==================== 系统提示词 ====================

    def _build_system_prompt(self, situation: dict, task: str) -> str:
        """构建完整的系统提示词（注入态势和工具信息）。

        Args:
            situation: 当前态势信息。
            task: 任务描述。

        Returns:
            格式化的系统提示词。
        """
        # 基础模板
        prompt = self._system_prompt_template

        # 注入可用工具描述
        tool_descriptions = self.tools_registry.get_descriptions()
        prompt = prompt.replace("{available_tools}", tool_descriptions)

        # 注入当前态势摘要
        situation_text = self._format_situation(situation)
        prompt += f"\n\n# 当前态势摘要\n{situation_text}"

        # 注入 Few-shot 示例
        if self._few_shot_examples:
            prompt += "\n\n# Few-shot 参考示例\n以下是典型场景的推理示例，供参考：\n"
            for i, example in enumerate(self._few_shot_examples, 1):
                prompt += f"\n## 示例 {i}: {example.get('scenario', '未命名场景')}\n"
                prompt += f"态势: {example.get('situation', '')}\n"
                prompt += f"推理: {example.get('reasoning', '')}\n"
                prompt += f"决策: {example.get('decision', '')}\n"

        # 注入军事术语表
        if self._terminology:
            prompt += "\n\n# 军事/反无人机术语表\n"
            for term, definition in self._terminology.items():
                prompt += f"- **{term}**: {definition}\n"

        return prompt

    def _format_situation(self, situation: dict) -> str:
        """格式化态势信息为可读文本。

        Args:
            situation: 原始态势字典。

        Returns:
            格式化的态势描述文本。
        """
        lines: list[str] = []

        # 目标信息
        targets = situation.get("targets", [situation] if "target_id" in situation else [])
        if not targets:
            targets = [situation]

        for i, t in enumerate(targets, 1):
            lines.append(f"## 目标 {i}")
            lines.append(f"- ID: {t.get('target_id', t.get('id', '未知'))}")
            lines.append(f"- 类型: {t.get('type', t.get('target_type', '未知'))}")
            lines.append(f"- 型号: {t.get('model', t.get('drone_model', '未知'))}")
            lines.append(f"- 位置: lat={t.get('lat', '?')}, lon={t.get('lon', '?')}, alt={t.get('alt', '?')}m")
            lines.append(f"- 速度: {t.get('speed_ms', t.get('speed', '?'))} m/s")
            lines.append(f"- 航向: {t.get('heading', t.get('course', '?'))} deg")
            lines.append(f"- 距离: {t.get('distance_m', t.get('distance', '?'))} m")
            lines.append(f"- CPA: {t.get('cpa_m', t.get('cpa', '?'))} m")
            lines.append(f"- 信号特征: {t.get('signal_features', t.get('rf_signature', '未知'))}")
            lines.append(f"- SNRs: {t.get('snr_db', t.get('snr', '?'))} dB")
            lines.append(f"- 行为: {t.get('behavior', t.get('flight_pattern', '未知'))}")
            threat_hint = t.get("threat_hint", t.get("preliminary_threat", ""))
            if threat_hint:
                lines.append(f"- 初步威胁判断: {threat_hint}")
            lines.append("")

        # 环境信息
        env = situation.get("environment", {})
        if env:
            lines.append("## 环境信息")
            lines.append(f"- 地形: {env.get('terrain', '未知')}")
            lines.append(f"- 天气: {env.get('weather', '未知')}")
            lines.append(f"- 空域等级: {env.get('airspace_class', env.get('zone_type', '未知'))}")
            lines.append(f"- 人口密度: {env.get('population_density', '未知')}")
            lines.append(f"- 电磁环境: {env.get('em_environment', '未知')}")
            lines.append("")

        # 约束条件
        constraints = situation.get("constraints", {})
        if constraints:
            lines.append("## 约束条件")
            for k, v in constraints.items():
                lines.append(f"- {k}: {v}")
            lines.append("")

        return "\n".join(lines)

    # ==================== LLM 调用 ====================

    def _call_llm(self, messages: list[dict]) -> str:
        """调用本地 llama.cpp 模型。

        Args:
            messages: 完整的对话历史消息列表。

        Returns:
            LLM 生成的文本（失败时返回空字符串）。
        """
        try:
            # 确保上下文不超出 N_CTX
            # 简单估算：所有消息字符数 * 2（中文大概2 token/char）
            total_chars = sum(len(m.get("content", "")) for m in messages)
            estimated_tokens = total_chars * 2

            if estimated_tokens > self.cfg.N_CTX:
                logger.warning(
                    f"消息历史估算 token 数 ({estimated_tokens}) 接近 N_CTX ({self.cfg.N_CTX})，"
                    f"可能被截断"
                )

            response = self.llm.create_chat_completion(
                messages=messages,
                max_tokens=self.cfg.MAX_TOKENS,
                temperature=self.cfg.TEMPERATURE,
                stop=STOP_TOKENS,
                top_p=0.9,
            )

            if response and "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"]
                logger.debug(f"LLM 响应 ({len(content)} 字符): {content[:200]}...")
                return content.strip()
            else:
                logger.error("LLM 响应格式异常")
                return ""

        except Exception as e:
            logger.error(f"LLM 调用异常: {e}", exc_info=True)
            return ""

    # ==================== 输出解析 ====================

    def _parse_action(self, text: str) -> Optional[dict]:
        """从 LLM 输出中解析 Action 指令。

        支持格式：
        1. Action: tool_name(args)                  # Python 风格
        2. Action: tool_name arg1=val1 arg2=val2    # Shell 风格
        3. {"action": "tool_name", "args": {...}}   # JSON 格式

        Args:
            text: LLM 输出文本。

        Returns:
            解析后的 Action 字典 {"tool": str, "args": dict}，失败返回 None。
        """
        # 模式 1: Action: tool_name(key=value, ...)
        pattern1 = r"(?:Action|行动|调用)[：:]\s*(\w+)\s*\(\s*(.*?)\s*\)"
        match = re.search(pattern1, text, re.IGNORECASE)
        if match:
            tool_name = match.group(1)
            args_str = match.group(2)
            args = self._parse_kwargs(args_str)
            logger.debug(f"解析到 Action (模式1): {tool_name}({args})")
            return {"tool": tool_name, "args": args}

        # 模式 2: Action: tool_name param=value param2=value2
        pattern2 = r"(?:Action|行动|调用)[：:]\s*(\w+)\s+(.+)"
        match = re.search(pattern2, text, re.IGNORECASE)
        if match:
            tool_name = match.group(1)
            args_str = match.group(2)
            args = self._parse_kwargs(args_str)
            logger.debug(f"解析到 Action (模式2): {tool_name}({args})")
            return {"tool": tool_name, "args": args}

        # 模式 3: JSON 格式 {"action": "...", "args": {...}}
        pattern3 = r'\{"action"\s*:\s*"(\w+)"\s*,\s*"args"\s*:\s*(\{[^}]+\})\s*\}'
        match = re.search(pattern3, text, re.IGNORECASE)
        if match:
            tool_name = match.group(1)
            try:
                args = json.loads(match.group(2))
            except json.JSONDecodeError:
                args = {}
            logger.debug(f"解析到 Action (模式3): {tool_name}({args})")
            return {"tool": tool_name, "args": args}

        return None

    def _parse_final(self, text: str) -> Optional[dict]:
        """从 LLM 输出中解析 Final 答案。

        识别标记：
        - 以 "Final:" 或 "最终决策:" 开头
        - 包含决策 JSON（```json 块或裸 JSON）

        Args:
            text: LLM 输出文本。

        Returns:
            解析后的决策字典，失败返回 None。
        """
        # 检查是否有 Final 标记
        final_markers = ["Final:", "最终决策:", "最终答案:", "决策输出:"]
        has_final_marker = any(marker in text for marker in final_markers)

        # 提取 JSON
        extracted = self._extract_json(text)
        if extracted is None:
            return None

        # 如果没有 Final 标记但有完整决策 JSON，也行
        if not has_final_marker:
            # 检查是否包含决策核心字段
            if "threat_assessment" not in extracted and "decision_id" not in extracted:
                return None
            logger.info("未找到 Final 标记，但提取到完整决策 JSON")

        return extracted

    def _parse_kwargs(self, args_str: str) -> dict:
        """解析 key=value 格式的参数字符串。

        Args:
            args_str: 参数字符串。

        Returns:
            解析后的参数字典。
        """
        kwargs: dict = {}
        if not args_str.strip():
            return kwargs

        # 匹配 key=value 对
        pattern = r"""(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)'|(\[[^\]]*\])|(\{[^}]*\})|([^\s,]+))"""
        for m in re.finditer(pattern, args_str):
            key = m.group(1)
            # 优先级：双引号 > 单引号 > 列表 > 字典 > 原子值
            value: Any = (
                m.group(2) or m.group(3) or m.group(4) or m.group(5) or m.group(6)
            )
            # 尝试解析列表
            if isinstance(value, str):
                if value.startswith("[") and value.endswith("]"):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                elif value.startswith("{") and value.endswith("}"):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                elif value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                else:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
            kwargs[key] = value

        return kwargs

    def _extract_json(self, text: str) -> Optional[dict]:
        """从文本中提取 JSON 对象。

        尝试多种方式：
        1. ```json ... ``` 代码块
        2. 直接全文 JSON 解析
        3. 匹配最外层花括号

        Args:
            text: 可能包含 JSON 的文本。

        Returns:
            解析后的字典，失败返回 None。
        """
        candidates: list[str] = []

        # 方式 1: JSON 代码块
        json_blocks = re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        candidates.extend(json_blocks)

        # 方式 2: 通用代码块
        code_blocks = re.findall(r"```\s*(\{.*?\})\s*```", text, re.DOTALL)
        candidates.extend(code_blocks)

        # 方式 3: 匹配最外层花括号（多层嵌套）
        brace_idx = text.find("{")
        while brace_idx != -1:
            depth = 0
            start = brace_idx
            for i in range(brace_idx, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:i + 1]
                        if len(candidate) > 20:  # 过滤太短的片段
                            candidates.append(candidate)
                        break
            brace_idx = text.find("{", brace_idx + 1)

        # 方式 4: 整段文本
        candidates.append(text)

        for candidate in candidates:
            candidate = candidate.strip()
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue

        return None

    # ==================== 边界处理 ====================

    def _generate_timeout_decision(self, task_id: str, target_id: str) -> dict:
        """生成超时时的保守决策。

        Args:
            task_id: 任务 ID。
            target_id: 目标 ID。

        Returns:
            保守决策字典（威胁等级 5，全频段压制）。
        """
        logger.warning("生成超时保护决策（威胁等级 5，全频段压制）")
        decision = json.loads(json.dumps(_TIMEOUT_DECISION_TEMPLATE))
        decision["decision_id"] = task_id
        decision["target_id"] = target_id
        decision["remarks"] = (
            f"【警告】推理超时（超过 {self.cfg.TIMEOUT_SECONDS} 秒），系统自动生成保守决策。"
            "置信度极低（0.30），强烈建议指挥员人工复核并确认后方可执行。"
        )
        return decision

    def _generate_max_rounds_decision(self, messages: list[dict], task_id: str, target_id: str) -> dict:
        """达到最大轮次时强制 LLM 生成最终决策。

        Args:
            messages: 当前消息历史。
            task_id: 任务 ID。
            target_id: 目标 ID。

        Returns:
            决策字典。
        """
        # 发送强制结束消息
        force_msg = (
            f"已达到最大推理轮次 ({self.cfg.MAX_ROUNDS})。"
            "请立即输出最终决策 JSON，不要调用工具，不要继续推理。"
            "直接以 Final: 开头输出完整的决策 JSON。"
        )
        messages.append({"role": "user", "content": force_msg})

        response_text = self._call_llm(messages)
        if response_text:
            extracted = self._extract_json(response_text)
            if extracted:
                extracted = self._ensure_fields(extracted, task_id, target_id)
                valid, errors = self.validator.validate(extracted)
                if valid:
                    extracted["reasoning_chain"].append("达到最大推理轮次，强制生成最终决策")
                    extracted["remarks"] = (
                        extracted.get("remarks", "")
                        + f"（注：本决策在第{self.cfg.MAX_ROUNDS}轮强制生成）"
                    )
                    return extracted
                else:
                    logger.warning(f"强制生成决策校验失败: {errors}")

        # 所有尝试失败，返回超时决策
        return self._generate_timeout_decision(task_id, target_id)

    def _extract_partial_decision(
        self, messages: list[dict], task_id: str, target_id: str
    ) -> Optional[dict]:
        """从已有消息中尝试提取部分决策（超时时使用）。

        Args:
            messages: 消息历史。
            task_id: 任务 ID。
            target_id: 目标 ID。

        Returns:
            提取的决策字典或 None。
        """
        # 从后往前搜索 assistant 消息中的 JSON
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            extracted = self._extract_json(content)
            if extracted and "threat_assessment" in extracted:
                extracted = self._ensure_fields(extracted, task_id, target_id)
                extracted["reasoning_chain"].append("超时时从部分推理中提取")
                extracted["data_sources"].append("部分推理（超时）")
                extracted["remarks"] = (
                    extracted.get("remarks", "")
                    + "（注：决策在推理超时时从部分结果中提取，请人工复核）"
                )
                logger.info("从部分推理中提取决策成功")
                return extracted
        return None

    # ==================== 工具观察 ====================

    def _format_observation(self, tool_name: str, result: dict) -> str:
        """格式化工具执行结果为观察文本。

        Args:
            tool_name: 工具名称。
            result: 工具执行结果。

        Returns:
            格式化的观察文本。
        """
        if result.get("success"):
            data = result.get("data", {})
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
            # 限制输出长度
            if len(data_str) > 2000:
                data_str = data_str[:2000] + f"\n...（输出截断，共 {len(data_str)} 字符）"
            return (
                f"【工具调用结果】{tool_name}\n"
                f"状态: 成功\n"
                f"数据:\n{data_str}"
            )
        else:
            error = result.get("error", "未知错误")
            return (
                f"【工具调用结果】{tool_name}\n"
                f"状态: 失败\n"
                f"错误: {error}\n"
                f"请考虑使用其他方式获取所需信息，或基于已有信息进行推理。"
            )

    # ==================== 字段保障 ====================

    def _ensure_fields(self, decision: dict, task_id: str, target_id: str) -> dict:
        """确保决策包含所有必要字段。

        Args:
            decision: 原始决策字典。
            task_id: 任务 ID。
            target_id: 目标 ID。

        Returns:
            补全后的决策字典。
        """
        if "decision_id" not in decision:
            decision["decision_id"] = task_id

        if "target_id" not in decision:
            decision["target_id"] = target_id

        if "threat_assessment" not in decision:
            decision["threat_assessment"] = {}
        ta = decision["threat_assessment"]
        if "threat_score" not in ta:
            ta["threat_score"] = 0.5
        if "threat_level" not in ta:
            # 从 threat_score 推算
            score = float(ta.get("threat_score", 0.5))
            ta["threat_level"] = max(1, min(5, int(score * 5 + 0.5)))
        if "confidence" not in ta:
            ta["confidence"] = 0.5
        if "key_factors" not in ta:
            ta["key_factors"] = ["未指定"]
        if "uncertainty_flags" not in ta:
            ta["uncertainty_flags"] = []

        if "recommended_action" not in decision:
            decision["recommended_action"] = {}
        ra = decision["recommended_action"]
        if "action_type" not in ra:
            ra["action_type"] = "监测"
        if "priority" not in ra:
            ra["priority"] = 5
        if "devices" not in ra:
            ra["devices"] = []
        if "parameters" not in ra:
            ra["parameters"] = {}
        if "expected_effect" not in ra:
            ra["expected_effect"] = ""
        if "alternative_actions" not in ra:
            ra["alternative_actions"] = []

        if "reasoning_chain" not in decision:
            decision["reasoning_chain"] = []
        if "data_sources" not in decision:
            decision["data_sources"] = []
        if "rule_proposal" not in decision:
            decision["rule_proposal"] = None
        if "remarks" not in decision:
            decision["remarks"] = ""

        return decision

    # ==================== 模板加载 ====================

    def _load_system_prompt(self) -> str:
        """加载系统提示词模板。"""
        template_paths = [
            Path(__file__).resolve().parent.parent / "prompt_templates" / "system_prompt.txt",
            Path(__file__).resolve().parent / "prompt_templates" / "system_prompt.txt",
        ]
        for path in template_paths:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                logger.info(f"加载系统提示词模板: {path}")
                return content

        logger.warning("未找到系统提示词模板文件，使用内置默认模板")
        return self._default_system_prompt()

    def _load_few_shot_examples(self) -> list[dict]:
        """加载 Few-shot 示例。"""
        example_paths = [
            Path(__file__).resolve().parent.parent / "prompt_templates" / "few_shot_examples.json",
            Path(__file__).resolve().parent / "prompt_templates" / "few_shot_examples.json",
        ]
        for path in example_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        examples = json.load(f)
                    logger.info(f"加载 Few-shot 示例 ({len(examples)} 条): {path}")
                    return examples
                except Exception as e:
                    logger.warning(f"Few-shot 示例加载失败: {e}")

        logger.warning("未找到 Few-shot 示例文件，将不使用示例")
        return []

    def _load_terminology(self) -> dict:
        """加载术语词典。"""
        term_paths = [
            Path(__file__).resolve().parent.parent / "prompt_templates" / "terminology.json",
            Path(__file__).resolve().parent / "prompt_templates" / "terminology.json",
        ]
        for path in term_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        terms = json.load(f)
                    logger.info(f"加载术语词典 ({len(terms)} 条): {path}")
                    return terms
                except Exception as e:
                    logger.warning(f"术语词典加载失败: {e}")

        logger.warning("未找到术语词典文件")
        return {}

    @staticmethod
    def _default_system_prompt() -> str:
        """内置默认系统提示词（文件加载失败时的回退）。"""
        return """你是反无人机辅助决策AI，代号"决策参谋"。
你的职责是分析战场态势，提供辅助决策建议。

{available_tools}

推理完成后，请以 Final: 开头输出完整的决策 JSON。

重要原则：
- 你是建议者，非执行者，最终决定权在人类指挥员
- 优先采用监测→警告→软杀伤→硬杀伤的渐进升级策略
- 每个结论必须有据可查
- 在信息不足时，倾向于保守估计（假定威胁更高）
"""
