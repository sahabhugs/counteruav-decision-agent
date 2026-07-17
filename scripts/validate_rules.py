#!/usr/bin/env python3
"""
规则校验脚本

功能：
1. 扫描 rules/ 目录下的 .drl 文件，校验 Drools 语法
2. 扫描 rules/ 目录下的 .json 规则文件，校验 JSON Schema
3. 跨文件检查：重复 rule_id、规则冲突、威胁等级覆盖、salience 一致性
4. 输出 JSON 或文本格式的校验报告

适用规则层：
- L1: 物理参数计算（Java 代码，由 PhysicsLibrary 处理）
- L2: .drl 条令层规则（Drools 语法）
- L3: .json 战术层规则
- L4: LLM 学习层元规则（JSON 格式）
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,  # 默认只输出警告和错误
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("validate_rules")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _get_script_dir() -> Path:
    """获取当前脚本所在目录的绝对路径。"""
    return Path(__file__).resolve().parent


def _collect_files(directory: Path, extensions: List[str]) -> List[Path]:
    """递归收集指定扩展名的文件。"""
    files: List[Path] = []
    if not directory.exists():
        logger.warning("目录不存在: %s", directory)
        return files
    for ext in extensions:
        files.extend(sorted(directory.rglob(f"*{ext}")))
    return files


# ---------------------------------------------------------------------------
# DRL 规则解析
# ---------------------------------------------------------------------------

class DRLRule:
    """表示一个 .drl 文件中解析出的单条规则。"""

    def __init__(self):
        self.file_path: str = ""
        self.line_number: int = 0
        self.rule_name: str = ""
        self.salience: Optional[int] = None
        self.agenda_group: Optional[str] = None
        self.no_loop: bool = False
        self.duration: Optional[int] = None
        self.raw_text: str = ""
        self.has_when: bool = False
        self.has_then: bool = False
        self.errors: List[str] = []

    def is_valid(self) -> bool:
        """检查规则是否有解析错误。"""
        return len(self.errors) == 0

    def to_dict(self) -> Dict:
        """转换为字典。"""
        return {
            "file": self.file_path,
            "line": self.line_number,
            "rule_name": self.rule_name,
            "salience": self.salience,
            "agenda_group": self.agenda_group,
            "no_loop": self.no_loop,
            "duration": self.duration,
            "errors": self.errors,
        }


def _parse_drl_file(filepath: Path) -> List[DRLRule]:
    """解析单个 .drl 文件，提取所有规则。"""
    if not filepath.exists():
        logger.error("DRL 文件不存在: %s", filepath)
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error("读取 DRL 文件失败 (%s): %s", filepath, e)
        return []

    rules: List[DRLRule] = []

    # 使用正则提取 rule 块（支持多行，处理嵌套结构）
    # 匹配 rule "name" ... end
    pattern = re.compile(
        r'rule\s+"([^"]+)"(.*?)end\b',
        re.DOTALL | re.IGNORECASE,
    )

    for match in pattern.finditer(content):
        rule = DRLRule()
        rule.file_path = str(filepath)
        rule.rule_name = match.group(1)
        rule.raw_text = match.group(0)

        # 计算行号
        rule.line_number = content[: match.start()].count("\n") + 1

        body = match.group(2)

        # 检查 when/then 块
        rule.has_when = bool(re.search(r'\bwhen\b', body, re.IGNORECASE))
        rule.has_then = bool(re.search(r'\bthen\b', body, re.IGNORECASE))

        if not rule.has_when:
            rule.errors.append(f"缺少 'when' 块")
        if not rule.has_then:
            rule.errors.append(f"缺少 'then' 块")

        # 提取属性
        # salience
        sal_match = re.search(r'@?salience\s*[=:(]\s*(\d+)\s*[)]?', body, re.IGNORECASE)
        if sal_match:
            try:
                rule.salience = int(sal_match.group(1))
            except ValueError:
                rule.errors.append(f"salience 值无法解析: {sal_match.group(1)}")

        # agenda-group
        ag_match = re.search(
            r'@?agenda-group\s*[=:(]\s*"([^"]+)"\s*[)]?',
            body,
            re.IGNORECASE,
        )
        if ag_match:
            rule.agenda_group = ag_match.group(1)

        # no-loop
        rule.no_loop = bool(re.search(r'@?no-loop\s*', body, re.IGNORECASE))

        # duration
        dur_match = re.search(r'@?duration\s*[=:(]\s*(\d+)\s*[)]?', body, re.IGNORECASE)
        if dur_match:
            try:
                rule.duration = int(dur_match.group(1))
            except ValueError:
                pass

        # 检查规则名是否合法（非空）
        if not rule.rule_name.strip():
            rule.errors.append("规则名为空")

        # 检查是否有匹配的 end 关键字已由正则保证
        rules.append(rule)

    # 检查是否有未匹配到的 rule 关键字（语法错误）
    open_rules = re.findall(r'\brule\s+', content, re.IGNORECASE)
    close_ends = re.findall(r'\bend\b', content, re.IGNORECASE)
    if len(open_rules) != len(close_ends):
        logger.warning(
            "%s: rule/end 数量不匹配: rule=%d, end=%d",
            filepath.name,
            len(open_rules),
            len(close_ends),
        )

    return rules


# ---------------------------------------------------------------------------
# JSON 规则校验
# ---------------------------------------------------------------------------

# JSON 规则的必需字段
_JSON_RULE_REQUIRED_FIELDS = {"rule_id", "name", "conditions", "actions"}
_JSON_RULE_OPTIONAL_FIELDS = {
    "description", "layer", "salience", "agenda_group",
    "no_loop", "priority", "category", "enabled", "version",
    "tags", "author", "created", "modified", "notes",
}


def _validate_json_rule_file(filepath: Path) -> Tuple[List[Dict], List[Dict]]:
    """校验单个 JSON 规则文件。

    Returns:
        (rules, errors): 解析出的规则列表和错误列表
    """
    rules: List[Dict] = []
    errors: List[Dict] = []

    if not filepath.exists():
        errors.append({
            "file": str(filepath),
            "line": 0,
            "severity": "error",
            "message": f"文件不存在",
        })
        return rules, errors

    # 解析 JSON
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        errors.append({
            "file": str(filepath),
            "line": e.lineno,
            "severity": "error",
            "message": f"JSON 解析失败: {e.msg}",
        })
        return rules, errors
    except Exception as e:
        errors.append({
            "file": str(filepath),
            "line": 0,
            "severity": "error",
            "message": f"读取文件失败: {str(e)}",
        })
        return rules, errors

    # 规范化数据为规则列表
    rule_list: List[Dict] = []
    if isinstance(data, list):
        rule_list = data
    elif isinstance(data, dict):
        # 可能的封装键
        for key in ("rules", "items", "data", "rule_list", "entries"):
            if key in data and isinstance(data[key], list):
                rule_list = data[key]
                break
        else:
            # 查找字典中第一个列表值
            for val in data.values():
                if isinstance(val, list):
                    rule_list = val
                    break
            else:
                # 可能单条规则直接是顶层 dict，且包含 rule_id
                if "rule_id" in data:
                    rule_list = [data]
                else:
                    errors.append({
                        "file": str(filepath),
                        "line": 0,
                        "severity": "error",
                        "message": "无法识别规则列表格式（期望 list 或含 rules/items 等键的 dict）",
                    })
                    return rules, errors

    # 逐条校验规则
    known_ids: Set[str] = set()
    for i, item in enumerate(rule_list):
        if not isinstance(item, dict):
            errors.append({
                "file": str(filepath),
                "line": 0,
                "severity": "error",
                "message": f"规则 [{i}] 不是有效的 JSON 对象",
            })
            continue

        rule_entry = dict(item)

        # 检查必需字段
        missing = _JSON_RULE_REQUIRED_FIELDS - set(rule_entry.keys())
        if missing:
            errors.append({
                "file": str(filepath),
                "line": 0,
                "severity": "error",
                "message": f"规则 '{rule_entry.get('rule_id', f'[索引 {i}]')}' 缺少必需字段: {', '.join(sorted(missing))}",
            })

        # 检查条件/动作不为空
        conditions = rule_entry.get("conditions", [])
        if isinstance(conditions, list) and len(conditions) == 0:
            errors.append({
                "file": str(filepath),
                "line": 0,
                "severity": "warning",
                "message": f"规则 '{rule_entry.get('rule_id', f'[索引 {i}]')}' 的 conditions 为空列表",
            })

        actions = rule_entry.get("actions", [])
        if isinstance(actions, list) and len(actions) == 0:
            errors.append({
                "file": str(filepath),
                "line": 0,
                "severity": "warning",
                "message": f"规则 '{rule_entry.get('rule_id', f'[索引 {i}]')}' 的 actions 为空列表",
            })

        # 检查同文件内重复 rule_id
        rid = rule_entry.get("rule_id", "")
        if rid:
            if rid in known_ids:
                errors.append({
                    "file": str(filepath),
                    "line": 0,
                    "severity": "error",
                    "message": f"规则 ID '{rid}' 在同一文件中重复",
                })
            known_ids.add(rid)

        # 增加文件来源信息
        rule_entry["_source_file"] = str(filepath)
        rules.append(rule_entry)

    return rules, errors


# ---------------------------------------------------------------------------
# 跨文件检查
# ---------------------------------------------------------------------------

def _check_duplicate_ids(all_rules: List[Dict]) -> List[Dict]:
    """检查所有规则中是否存在重复的 rule_id。"""
    id_map: Dict[str, List[str]] = defaultdict(list)
    for r in all_rules:
        rid = r.get("rule_id", r.get("rule_name", ""))
        if rid:
            id_map[rid].append(r.get("_source_file", "unknown"))

    duplicates = []
    for rid, files in id_map.items():
        if len(files) > 1:
            duplicates.append({
                "rule_id": rid,
                "files": files,
                "message": f"规则 ID '{rid}' 在 {len(files)} 个文件中重复定义",
            })

    if duplicates:
        logger.warning("发现 %d 个重复的 rule_id", len(duplicates))
    return duplicates


def _check_rule_conflicts(all_rules: List[Dict]) -> List[Dict]:
    """检查规则冲突：相同条件触发但不同动作的规则。"""
    # 提取规则的 (conditions_signature, rule_ids)
    condition_map: Dict[str, List[Dict]] = defaultdict(list)

    for r in all_rules:
        conditions = r.get("conditions", [])
        if isinstance(conditions, list):
            # 生成条件签名：排序后的条件字符串
            cond_strs = sorted(
                json.dumps(c, sort_keys=True, ensure_ascii=False)
                if isinstance(c, dict)
                else str(c)
                for c in conditions
            )
            sig = "||".join(cond_strs)
        elif isinstance(conditions, dict):
            sig = json.dumps(conditions, sort_keys=True, ensure_ascii=False)
        else:
            sig = str(conditions)

        if sig:
            condition_map[sig].append({
                "rule_id": r.get("rule_id", r.get("rule_name", "")),
                "actions": r.get("actions", []),
                "file": r.get("_source_file", ""),
            })

    conflicts = []
    for sig, entries in condition_map.items():
        if len(entries) > 1:
            # 检查动作是否不同
            action_sigs = set()
            for e in entries:
                act_sig = json.dumps(e["actions"], sort_keys=True, ensure_ascii=False)
                action_sigs.add(act_sig)
            if len(action_sigs) > 1:
                conflicts.append({
                    "condition_signature": sig[:200] + ("..." if len(sig) > 200 else ""),
                    "rules": entries,
                    "message": f"{len(entries)} 条规则条件相同但动作不同",
                })

    if conflicts:
        logger.warning("发现 %d 个潜在的规则冲突", len(conflicts))
    return conflicts


def _check_threat_coverage(all_rules: List[Dict]) -> Dict:
    """检查是否覆盖了所有威胁等级 1-5。"""
    threat_level_refs = set()
    pattern = re.compile(r'threatLevel\s*[><=!]+\s*(\d)', re.IGNORECASE)

    for r in all_rules:
        # 检查 conditions 中的威胁等级引用
        conditions = r.get("conditions", [])
        cond_text = json.dumps(conditions, ensure_ascii=False) if conditions else ""

        # 同时检查 raw_text / description
        raw = r.get("raw_text", "")
        desc = r.get("description", "")
        search_text = f"{cond_text} {raw} {desc}"

        matches = pattern.findall(search_text)
        for m in matches:
            try:
                threat_level_refs.add(int(m))
            except ValueError:
                pass

        # 也检查 action 中对 threatLevel 的设置
        actions = r.get("actions", [])
        act_text = json.dumps(actions, ensure_ascii=False) if actions else ""
        act_matches = pattern.findall(act_text)
        for m in act_matches:
            try:
                threat_level_refs.add(int(m))
            except ValueError:
                pass

    all_levels = set(range(1, 6))
    covered = sorted(threat_level_refs & all_levels)
    missing = sorted(all_levels - threat_level_refs)

    return {
        "expected_levels": list(all_levels),
        "covered_levels": covered,
        "missing_levels": missing,
        "coverage_percentage": len(covered) / len(all_levels) * 100 if all_levels else 0,
    }


def _check_salience_conflicts(all_rules: List[Dict]) -> List[Dict]:
    """检查同一 agenda-group 内是否有相同 salience 的规则。"""
    group_map: Dict[str, List[Dict]] = defaultdict(list)

    for r in all_rules:
        ag = r.get("agenda_group", r.get("agendaGroup", ""))
        sal = r.get("salience")
        rid = r.get("rule_id", r.get("rule_name", ""))

        if ag and sal is not None:
            group_map[ag].append({
                "rule_id": rid,
                "salience": sal,
                "file": r.get("_source_file", ""),
            })

    conflicts = []
    for group, entries in group_map.items():
        sal_map: Dict[int, List[str]] = defaultdict(list)
        for e in entries:
            sal_map[e["salience"]].append(e["rule_id"])

        for sal, rids in sal_map.items():
            if len(rids) > 1:
                conflicts.append({
                    "agenda_group": group,
                    "salience": sal,
                    "conflicting_rule_ids": rids,
                    "message": (
                        f"agenda-group '{group}' 中存在 salience={sal} 冲突: "
                        f"{', '.join(rids)}"
                    ),
                })

    if conflicts:
        logger.warning("发现 %d 个 salience 冲突", len(conflicts))
    return conflicts


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def _generate_report(
    drl_rules: List[DRLRule],
    json_rules: List[Dict],
    validation_results: Dict,
    output_format: str,
) -> str:
    """生成校验报告。"""
    total_drl = len(drl_rules)
    total_json = len(json_rules)
    total = total_drl + total_json

    errors: List[Dict] = validation_results.get("errors", [])
    warnings: List[Dict] = validation_results.get("warnings", [])
    coverage = validation_results.get("coverage_report", {})
    duplicates = validation_results.get("duplicate_ids", [])
    salience_conflicts = validation_results.get("salience_conflicts", [])

    # 计算汇总状态
    has_errors = len(errors) > 0
    has_warnings = len(warnings) > 0
    has_critical = any(e.get("severity") == "error" for e in errors)

    if has_critical:
        summary = "FAIL"
    elif has_errors or has_warnings:
        summary = "WARN"
    else:
        summary = "PASS"

    if output_format == "json":
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_rules": total,
            "drl_rules": total_drl,
            "json_rules": total_json,
            "errors": errors,
            "warnings": warnings,
            "coverage_report": coverage,
            "duplicate_ids": duplicates,
            "salience_conflicts": salience_conflicts,
            "summary": summary,
        }
        return json.dumps(report, ensure_ascii=False, indent=2)

    # 文本格式
    lines = []
    lines.append("=" * 70)
    lines.append("  规则校验报告")
    lines.append("=" * 70)
    lines.append(f"  生成时间:     {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"  规则总数:     {total} (DRL: {total_drl}, JSON: {total_json})")
    lines.append(f"  错误数:       {len(errors)}")
    lines.append(f"  警告数:       {len(warnings)}")
    lines.append(f"  汇总状态:     {summary}")
    lines.append("")

    # 错误详情
    if errors:
        lines.append("-" * 70)
        lines.append("  错误详情:")
        lines.append("-" * 70)
        for i, err in enumerate(errors, 1):
            lines.append(f"  [{i}] [{err.get('severity', 'error').upper()}] {err.get('file', '')}:{err.get('line', 0)}")
            lines.append(f"      {err.get('message', '')}")
        lines.append("")

    # 警告详情
    if warnings:
        lines.append("-" * 70)
        lines.append("  警告详情:")
        lines.append("-" * 70)
        for i, warn in enumerate(warnings, 1):
            lines.append(f"  [{i}] [{warn.get('severity', 'warning').upper()}] {warn.get('file', '')}:{warn.get('line', 0)}")
            lines.append(f"      {warn.get('message', '')}")
        lines.append("")

    # 威胁覆盖报告
    if coverage:
        lines.append("-" * 70)
        lines.append("  威胁等级覆盖报告:")
        lines.append("-" * 70)
        lines.append(f"  覆盖等级:     {coverage.get('covered_levels', [])}")
        lines.append(f"  缺失等级:     {coverage.get('missing_levels', [])}")
        lines.append(f"  覆盖率:       {coverage.get('coverage_percentage', 0):.0f}%")
        lines.append("")

    # 重复 ID
    if duplicates:
        lines.append("-" * 70)
        lines.append("  重复规则 ID:")
        lines.append("-" * 70)
        for dup in duplicates:
            lines.append(f"  - {dup['rule_id']}: 出现在 {len(dup.get('files', []))} 个文件中")
            for f in dup.get("files", []):
                lines.append(f"      {f}")
        lines.append("")

    # Salience 冲突
    if salience_conflicts:
        lines.append("-" * 70)
        lines.append("  Salience 冲突:")
        lines.append("-" * 70)
        for sc in salience_conflicts:
            lines.append(f"  - agenda-group: {sc['agenda_group']}, salience: {sc['salience']}")
            lines.append(f"    冲突规则: {', '.join(sc.get('conflicting_rule_ids', []))}")
        lines.append("")

    # DRL 规则摘要
    if drl_rules:
        lines.append("-" * 70)
        lines.append("  DRL 规则摘要:")
        lines.append("-" * 70)
        for rule in drl_rules:
            status = "OK" if rule.is_valid() else f"ERROR ({len(rule.errors)} 个错误)"
            lines.append(
                f"  [{status}] {rule.rule_name} "
                f"(salience={rule.salience}, agenda={rule.agenda_group}) "
                f"- {Path(rule.file_path).name}:{rule.line_number}"
            )
        lines.append("")

    lines.append("=" * 70)
    lines.append(f"  校验结果: {summary}")
    lines.append("=" * 70)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _get_default_rules_dir() -> Path:
    """获取默认的 rules 目录路径。"""
    # 优先查找 rule-engine/src/main/resources/rules
    script_dir = _get_script_dir()
    candidate1 = script_dir.parent / "rule-engine" / "src" / "main" / "resources" / "rules"
    if candidate1.exists():
        return candidate1
    # 回退到项目根下的 rules/
    candidate2 = script_dir.parent / "rules"
    if candidate2.exists():
        return candidate2
    return candidate2  # 返回预期路径（可能不存在，由后续代码处理）


def main() -> None:
    """主函数：解析参数并执行规则校验。"""
    parser = argparse.ArgumentParser(
        description="规则校验工具：扫描并校验 DRL 和 JSON 规则文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python validate_rules.py
  python validate_rules.py --rules-dir ../rule-engine/src/main/resources/rules --format json --output report.json
  python validate_rules.py --format text
        """,
    )

    default_rules = str(_get_default_rules_dir())

    parser.add_argument(
        "--rules-dir",
        type=str,
        default=default_rules,
        help="规则文件目录路径 (默认: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出文件路径（默认: stdout）",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="text",
        choices=["json", "text"],
        help="输出格式 (默认: text)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="输出详细日志",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    rules_dir = Path(args.rules_dir)
    if not rules_dir.is_absolute():
        rules_dir = _get_script_dir().parent / rules_dir

    logger.info("规则目录: %s", rules_dir)

    if not rules_dir.exists():
        logger.error("规则目录不存在: %s", rules_dir)
        sys.exit(1)

    all_errors: List[Dict] = []
    all_warnings: List[Dict] = []
    all_drl_rules: List[DRLRule] = []
    all_json_rules: List[Dict] = []

    # ---- 阶段 1: 扫描 .drl 文件 ----
    drl_files = _collect_files(rules_dir, [".drl"])
    logger.info("找到 %d 个 DRL 文件", len(drl_files))

    for fp in drl_files:
        file_rules = _parse_drl_file(fp)
        all_drl_rules.extend(file_rules)
        for rule in file_rules:
            for err in rule.errors:
                all_errors.append({
                    "file": str(fp),
                    "line": rule.line_number,
                    "severity": "error",
                    "message": f"规则 '{rule.rule_name}': {err}",
                })

    logger.info("解析到 %d 条 DRL 规则", len(all_drl_rules))

    # ---- 阶段 2: 扫描 .json 规则文件 ----
    json_files = _collect_files(rules_dir, [".json"])
    logger.info("找到 %d 个 JSON 文件", len(json_files))

    for fp in json_files:
        rules, errs = _validate_json_rule_file(fp)
        all_json_rules.extend(rules)
        for e in errs:
            if e.get("severity") == "warning":
                all_warnings.append(e)
            else:
                all_errors.append(e)

    logger.info("解析到 %d 条 JSON 规则", len(all_json_rules))

    # ---- 阶段 3: 跨文件检查 ----
    # 合并所有规则用于跨文件分析
    combined_rules: List[Dict] = []
    for drl_rule in all_drl_rules:
        combined_rules.append(drl_rule.to_dict())
        combined_rules[-1]["rule_id"] = drl_rule.rule_name
        combined_rules[-1]["_source_file"] = drl_rule.file_path
        combined_rules[-1]["conditions"] = []
        combined_rules[-1]["actions"] = []
        combined_rules[-1]["raw_text"] = drl_rule.raw_text
    combined_rules.extend(all_json_rules)

    duplicates = _check_duplicate_ids(combined_rules)
    conflicts = _check_rule_conflicts(combined_rules)
    coverage = _check_threat_coverage(combined_rules)
    salience_conflicts = _check_salience_conflicts(combined_rules)

    # 将跨文件检查结果加入警告
    for dup in duplicates:
        all_warnings.append({
            "file": ", ".join(dup.get("files", [])),
            "line": 0,
            "severity": "warning",
            "message": dup.get("message", ""),
        })

    # 规则冲突可能是错误或警告
    for cf in conflicts:
        all_warnings.append({
            "file": ", ".join(e.get("file", "") for e in cf.get("rules", [])),
            "line": 0,
            "severity": "warning",
            "message": cf.get("message", ""),
        })

    # 缺失威胁等级覆盖为警告
    missing_levels = coverage.get("missing_levels", [])
    if missing_levels:
        all_warnings.append({
            "file": "N/A",
            "line": 0,
            "severity": "warning",
            "message": f"威胁等级覆盖缺失: {missing_levels} (覆盖率: {coverage.get('coverage_percentage', 0):.0f}%)",
        })

    # ---- 阶段 4: 生成报告 ----
    validation_results = {
        "errors": all_errors,
        "warnings": all_warnings,
        "coverage_report": coverage,
        "duplicate_ids": duplicates,
        "salience_conflicts": salience_conflicts,
    }

    report = _generate_report(all_drl_rules, all_json_rules, validation_results, args.format)

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info("校验报告已保存到: %s", output_path)
    else:
        print(report)

    # 退出码
    has_critical = any(e.get("severity") == "error" for e in all_errors)
    num_issues = len(all_errors) + len(all_warnings)
    if has_critical:
        sys.exit(1)
    elif num_issues > 0:
        sys.exit(0)  # 有警告但不阻塞
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
