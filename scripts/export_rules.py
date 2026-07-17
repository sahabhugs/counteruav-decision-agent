#!/usr/bin/env python3
"""
规则导出工具

支持将 rules/ 目录下的规则导出为 markdown、CSV 或 JSON 格式。
可筛选特定层（L1-L4）或全部导出。
生成完整的规则目录文档、数据表或标准化 JSON 数组。

各层说明：
- L1: 物理层 - 物理公式参考表（Java PhysicsLibrary）
- L2: 条令层 - .drl Drools 规则文件
- L3: 战术层 - JSON 战术规则文件
- L4: 学习层 - LLM 元规则 JSON 文件
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("export_rules")


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
        return files
    for ext in extensions:
        files.extend(sorted(directory.rglob(f"*{ext}")))
    return files


# ---------------------------------------------------------------------------
# 规则解析
# ---------------------------------------------------------------------------

def _parse_drl_file(filepath: Path) -> List[Dict]:
    """解析单个 .drl 文件，提取所有规则为字典列表。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error("读取 DRL 文件失败 (%s): %s", filepath, e)
        return []

    rules: List[Dict] = []
    pattern = re.compile(
        r'rule\s+"([^"]+)"(.*?)end\b',
        re.DOTALL | re.IGNORECASE,
    )

    for match in pattern.finditer(content):
        rule_name = match.group(1)
        body = match.group(2)
        line_number = content[: match.start()].count("\n") + 1

        # 提取属性
        salience = None
        sal_match = re.search(r'@?salience\s*[=:(]\s*(\d+)\s*[)]?', body, re.IGNORECASE)
        if sal_match:
            try:
                salience = int(sal_match.group(1))
            except ValueError:
                pass

        agenda_group = None
        ag_match = re.search(r'@?agenda-group\s*[=:(]\s*"([^"]+)"\s*[)]?', body, re.IGNORECASE)
        if ag_match:
            agenda_group = ag_match.group(1)

        no_loop = bool(re.search(r'@?no-loop\s*', body, re.IGNORECASE))

        # 提取 description
        desc_match = re.search(r'@?description\s*[=:(]\s*"([^"]+)"\s*[)]?', body, re.IGNORECASE)
        description = desc_match.group(1) if desc_match else ""

        # 提取 when/then 内容摘要
        when_match = re.search(r'\bwhen\b(.*?)\bthen\b', body, re.DOTALL | re.IGNORECASE)
        conditions_summary = ""
        actions_summary = ""
        if when_match:
            conditions_text = when_match.group(1).strip()
            # 截取前几行作为摘要
            cond_lines = [l.strip() for l in conditions_text.split("\n") if l.strip()]
            conditions_summary = "; ".join(cond_lines[:5])
            if len(cond_lines) > 5:
                conditions_summary += " ..."

            # then 块在 when 之后
            then_start = when_match.end()
            then_text = body[then_start - len("then"):].strip()
            # 去掉开头的 "then"
            if then_text.lower().startswith("then"):
                then_text = then_text[4:].strip()
            act_lines = [l.strip() for l in then_text.split("\n") if l.strip()]
            actions_summary = "; ".join(act_lines[:5])
            if len(act_lines) > 5:
                actions_summary += " ..."

        rules.append({
            "layer": "L2",
            "rule_id": rule_name,
            "name": rule_name,
            "type": "drl",
            "description": description,
            "conditions": conditions_summary,
            "actions": actions_summary,
            "salience": salience,
            "agenda_group": agenda_group,
            "no_loop": no_loop,
            "file": filepath.name,
            "file_path": str(filepath),
            "line": line_number,
        })

    return rules


def _parse_json_rule_file(filepath: Path, layer: str = "L3") -> List[Dict]:
    """解析单个 JSON 规则文件。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("解析 JSON 规则文件失败 (%s): %s", filepath, e)
        return []

    rule_list: List[Dict] = []
    if isinstance(data, list):
        rule_list = data
    elif isinstance(data, dict):
        for key in ("rules", "items", "data", "rule_list"):
            if key in data and isinstance(data[key], list):
                rule_list = data[key]
                break
        else:
            for val in data.values():
                if isinstance(val, list):
                    rule_list = val
                    break
            else:
                if "rule_id" in data:
                    rule_list = [data]

    # 标准化
    normalized: List[Dict] = []
    for item in rule_list:
        if not isinstance(item, dict):
            continue

        # 提取 conditions 摘要
        conditions = item.get("conditions", [])
        if isinstance(conditions, list):
            cond_summary = "; ".join(
                str(c) if not isinstance(c, dict)
                else ", ".join(f"{k}={v}" for k, v in c.items())
                for c in conditions[:5]
            )
        elif isinstance(conditions, dict):
            cond_summary = ", ".join(f"{k}={v}" for k, v in conditions.items())
        else:
            cond_summary = str(conditions)

        # 提取 actions 摘要
        actions = item.get("actions", [])
        if isinstance(actions, list):
            act_summary = "; ".join(
                str(a) if not isinstance(a, dict)
                else a.get("action_type", a.get("type", str(a)))
                for a in actions[:5]
            )
        else:
            act_summary = str(actions)

        normalized.append({
            "layer": layer,
            "rule_id": item.get("rule_id", item.get("id", "")),
            "name": item.get("name", item.get("rule_name", "")),
            "type": "json",
            "description": item.get("description", ""),
            "conditions": cond_summary,
            "actions": act_summary,
            "salience": item.get("salience"),
            "agenda_group": item.get("agenda_group", item.get("agendaGroup")),
            "no_loop": item.get("no_loop", item.get("noLoop", False)),
            "file": filepath.name,
            "file_path": str(filepath),
            "line": 0,
            "enabled": item.get("enabled", True),
            "priority": item.get("priority"),
            "tags": item.get("tags", []),
            "raw": item,
        })

    return normalized


# ---------------------------------------------------------------------------
# L1 物理层参考表
# ---------------------------------------------------------------------------

L1_PHYSICS_REFERENCE = [
    {
        "formula_id": "L1-F-001",
        "name": "Haversine 距离计算",
        "formula": "d = 2 * R * atan2(sqrt(a), sqrt(1-a)), a = sin^2(dLat/2)+cos(lat1)*cos(lat2)*sin^2(dLon/2)",
        "description": "计算两个经纬度坐标之间的地球表面距离，适用于 WGS84 坐标系",
        "unit": "米 (m)",
        "reference_radius": 6371000.0,
        "module": "PhysicsLibrary.distanceTo()",
    },
    {
        "formula_id": "L1-F-002",
        "name": "方位角计算",
        "formula": "theta = atan2(sin(dLon)*cos(lat2), cos(lat1)*sin(lat2)-sin(lat1)*cos(lat2)*cos(dLon))",
        "description": "计算从 A 点到 B 点的初始方位角，0 度为正北方向",
        "unit": "度 (°)",
        "module": "PhysicsLibrary.bearingTo()",
    },
    {
        "formula_id": "L1-F-003",
        "name": "径向速度计算",
        "formula": "vr = v * cos(theta - heading)",
        "description": "计算目标相对于防御中心径向的速度分量（负值表示接近）",
        "unit": "米/秒 (m/s)",
        "module": "PhysicsLibrary.radialSpeed()",
    },
    {
        "formula_id": "L1-F-004",
        "name": "到达时间预估 (TTA)",
        "formula": "TTA = distance / |vr|  (只有径向速度为接近时有效)",
        "description": "预估目标到达防御区域的最短时间",
        "unit": "秒 (s)",
        "module": "PhysicsLibrary.estimateTTA()",
    },
    {
        "formula_id": "L1-F-005",
        "name": "检测概率与距离关系",
        "formula": "Pd = Pd0 * exp(-k * d^2)  (简化的雷达方程近似)",
        "description": "根据目标距离估算系统对该目标的检测概率",
        "unit": "无（概率 0-1）",
        "module": "PhysicsLibrary.detectionProbability()",
    },
    {
        "formula_id": "L1-F-006",
        "name": "TOPSIS 相对贴近度",
        "formula": "C_i = D_i^- / (D_i^+ + D_i^-), D^+=欧氏距离到正理想解, D^-=欧氏距离到负理想解",
        "description": "多属性决策归一化评分，用于将多维度威胁指标映射为单一评分 0-1",
        "unit": "无（评分 0-1）",
        "module": "PhysicsLibrary.calculateTOPSIS()",
    },
    {
        "formula_id": "L1-F-007",
        "name": "TOPSIS -> 威胁等级映射",
        "formula": "cc>=0.8->5, cc>=0.6->4, cc>=0.4->3, cc>=0.2->2, cc<0.2->1",
        "description": "将 TOPSIS 贴近度映射为 5 级威胁等级",
        "unit": "等级 (1-5)",
        "module": "ThreatLevel.fromClosenessCoefficient()",
    },
    {
        "formula_id": "L1-F-008",
        "name": "视距判定 (Line of Sight)",
        "formula": "R_los = sqrt(2 * Re) * (sqrt(h1) + sqrt(h2)), Re = 4/3 * R_earth",
        "description": "雷达/设备视距判定（考虑大气折射的等效地球半径）",
        "unit": "米 (m)",
        "module": "PhysicsLibrary.lineOfSight()",
    },
]


# ---------------------------------------------------------------------------
# 导出格式
# ---------------------------------------------------------------------------

def _export_markdown(
    rules: List[Dict],
    title: str = "反无人机决策规则目录",
) -> str:
    """生成 markdown 格式的规则目录文档。"""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"> 生成时间: {now_str}")
    lines.append(f"> 规则总数: {len(rules)}")
    lines.append("")

    # 按层分组
    l1_rules = [r for r in rules if r.get("layer") == "L1"]
    l2_rules = [r for r in rules if r.get("layer") == "L2"]
    l3_rules = [r for r in rules if r.get("layer") == "L3"]
    l4_rules = [r for r in rules if r.get("layer") == "L4"]

    # ---- 目录 ----
    lines.append("## 目录")
    lines.append("")
    lines.append(f"1. [L1 物理层公式参考](#l1-物理层公式参考) ({len(l1_rules)} 项)")
    lines.append(f"2. [L2 条令层规则 (DRL)](#l2-条令层规则-drl) ({len(l2_rules)} 项)")
    lines.append(f"3. [L3 战术层规则 (JSON)](#l3-战术层规则-json) ({len(l3_rules)} 项)")
    lines.append(f"4. [L4 学习层元规则](#l4-学习层元规则) ({len(l4_rules)} 项)")
    lines.append(f"5. [覆盖统计](#覆盖统计)")
    lines.append("")

    # ---- L1 ----
    lines.append("## L1 物理层公式参考")
    lines.append("")
    lines.append("| 编号 | 名称 | 公式 | 单位 | 模块 |")
    lines.append("|------|------|------|------|------|")
    for r in l1_rules:
        fid = r.get("formula_id", r.get("rule_id", ""))
        name = r.get("name", "")
        formula = r.get("formula", "")
        unit = r.get("unit", "")
        module = r.get("module", "")
        # 转义 markdown 特殊字符
        formula_esc = formula.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {fid} | {name} | `{formula_esc}` | {unit} | `{module}` |")
    lines.append("")

    # 添加公式说明
    lines.append("### L1 公式详细说明")
    lines.append("")
    for r in l1_rules:
        fid = r.get("formula_id", r.get("rule_id", ""))
        name = r.get("name", "")
        desc = r.get("description", "")
        ref_radius = r.get("reference_radius")
        lines.append(f"**{fid}: {name}**")
        lines.append("")
        lines.append(f"> {desc}")
        if ref_radius:
            lines.append(f"- 地球参考半径: {ref_radius} m")
        lines.append("")

    # ---- L2 ----
    lines.append("## L2 条令层规则 (DRL)")
    lines.append("")
    if l2_rules:
        lines.append("| 规则ID | 名称 | Salience | Agenda Group | 条件摘要 | 动作摘要 | 文件 |")
        lines.append("|--------|------|----------|-------------|----------|----------|------|")
        for r in l2_rules:
            rid = r.get("rule_id", "")
            name = r.get("name", "")
            sal = r.get("salience", "")
            ag = r.get("agenda_group", "") or ""
            cond = (r.get("conditions", "") or "")[:80]
            act = (r.get("actions", "") or "")[:80]
            fname = r.get("file", "")
            # 转义
            cond = cond.replace("|", "\\|").replace("\n", " ")
            act = act.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {rid} | {name} | {sal} | {ag} | {cond} | {act} | {fname} |")
        lines.append("")

        # 详细展开
        lines.append("### L2 规则详情")
        lines.append("")
        for r in l2_rules:
            rid = r.get("rule_id", "")
            name = r.get("name", "")
            desc = r.get("description", "") or "（无描述）"
            sal = r.get("salience")
            ag = r.get("agenda_group", "")
            nl = r.get("no_loop", False)
            cond = r.get("conditions", "")
            act = r.get("actions", "")
            fname = r.get("file", "")
            line_no = r.get("line", 0)

            lines.append(f"#### {rid}: {name}")
            lines.append("")
            lines.append(f"- **文件**: `{fname}:{line_no}`")
            lines.append(f"- **描述**: {desc}")
            if sal is not None:
                lines.append(f"- **Salience**: {sal}")
            if ag:
                lines.append(f"- **Agenda Group**: `{ag}`")
            if nl:
                lines.append(f"- **No-loop**: 是")
            lines.append("")
            lines.append("**条件 (When):**")
            lines.append("```")
            lines.append(cond or "（无）")
            lines.append("```")
            lines.append("")
            lines.append("**动作 (Then):**")
            lines.append("```")
            lines.append(act or "（无）")
            lines.append("```")
            lines.append("")
    else:
        lines.append("*暂无 L2 规则*")
        lines.append("")

    # ---- L3 ----
    lines.append("## L3 战术层规则 (JSON)")
    lines.append("")
    if l3_rules:
        lines.append("| 规则ID | 名称 | 优先级 | 条件摘要 | 动作摘要 | 文件 |")
        lines.append("|--------|------|--------|----------|----------|------|")
        for r in l3_rules:
            rid = r.get("rule_id", "")
            name = r.get("name", "")
            pri = r.get("priority", r.get("salience", ""))
            cond = (r.get("conditions", "") or "")[:80]
            act = (r.get("actions", "") or "")[:80]
            fname = r.get("file", "")
            cond = cond.replace("|", "\\|").replace("\n", " ")
            act = act.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {rid} | {name} | {pri} | {cond} | {act} | {fname} |")
        lines.append("")

        # 详情
        lines.append("### L3 规则详情")
        lines.append("")
        for r in l3_rules:
            rid = r.get("rule_id", "")
            name = r.get("name", "")
            desc = r.get("description", "") or "（无描述）"
            enabled = r.get("enabled", True)
            tags = r.get("tags", [])
            cond = r.get("conditions", "")
            act = r.get("actions", "")
            fname = r.get("file", "")

            lines.append(f"#### {rid}: {name}")
            lines.append("")
            lines.append(f"- **文件**: `{fname}`")
            lines.append(f"- **描述**: {desc}")
            lines.append(f"- **启用**: {'是' if enabled else '否'}")
            if tags:
                lines.append(f"- **标签**: {', '.join(tags) if isinstance(tags, list) else str(tags)}")
            lines.append("")
            lines.append("**条件:**")
            lines.append("```json")
            lines.append(json.dumps(cond, ensure_ascii=False, indent=2) if isinstance(cond, (dict, list)) else str(cond))
            lines.append("```")
            lines.append("")
            lines.append("**动作:**")
            lines.append("```json")
            lines.append(json.dumps(act, ensure_ascii=False, indent=2) if isinstance(act, (dict, list)) else str(act))
            lines.append("```")
            lines.append("")
    else:
        lines.append("*暂无 L3 规则*")
        lines.append("")

    # ---- L4 ----
    lines.append("## L4 学习层元规则")
    lines.append("")
    if l4_rules:
        lines.append("| 规则ID | 名称 | 置信度阈值 | 触发条件 | 建议动作 |")
        lines.append("|--------|------|-----------|----------|----------|")
        for r in l4_rules:
            rid = r.get("rule_id", "")
            name = r.get("name", "")
            conf = r.get("confidence_threshold", r.get("salience", ""))
            cond = (r.get("conditions", "") or "")[:80]
            act = (r.get("actions", "") or "")[:80]
            cond = cond.replace("|", "\\|").replace("\n", " ")
            act = act.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {rid} | {name} | {conf} | {cond} | {act} |")
        lines.append("")

        lines.append("### L4 规则详情")
        lines.append("")
        for r in l4_rules:
            rid = r.get("rule_id", "")
            name = r.get("name", "")
            desc = r.get("description", "") or "（无描述）"
            lines.append(f"- **{rid}**: {name} - {desc}")
        lines.append("")
    else:
        lines.append("*暂无 L4 规则*")
        lines.append("")

    # ---- 覆盖统计 ----
    lines.append("## 覆盖统计")
    lines.append("")
    lines.append("| 层 | 规则数量 | 类型 |")
    lines.append("|----|---------|------|")
    lines.append(f"| L1 物理层 | {len(l1_rules)} | 公式参考 |")
    lines.append(f"| L2 条令层 | {len(l2_rules)} | DRL |")
    lines.append(f"| L3 战术层 | {len(l3_rules)} | JSON |")
    lines.append(f"| L4 学习层 | {len(l4_rules)} | JSON 元规则 |")
    lines.append(f"| **合计** | **{len(rules)}** | |")
    lines.append("")

    # 威胁等级统计
    threat_levels = defaultdict(int)
    for r in rules:
        raw = r.get("raw", {})
        if isinstance(raw, dict):
            tl = raw.get("threatLevel", raw.get("threat_level"))
            if tl is not None:
                threat_levels[int(tl)] = threat_levels.get(int(tl), 0) + 1

    if threat_levels:
        lines.append("### 威胁等级分布")
        lines.append("")
        lines.append("| 等级 | 标签 | 规则数 |")
        lines.append("|------|------|--------|")
        labels = {1: "低危", 2: "中危", 3: "高危", 4: "极高", 5: "极危"}
        for level in range(1, 6):
            lines.append(f"| {level} | {labels.get(level, '未知')} | {threat_levels.get(level, 0)} |")
        lines.append("")

    return "\n".join(lines)


def _export_csv(rules: List[Dict]) -> str:
    """导出为 CSV 格式。"""
    output = StringIO()
    fieldnames = [
        "layer", "rule_id", "name", "type", "conditions",
        "actions", "salience", "agenda_group", "file",
    ]
    # 对于 L1，使用不同字段名
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for r in rules:
        row = {
            "layer": r.get("layer", ""),
            "rule_id": r.get("rule_id", r.get("formula_id", "")),
            "name": r.get("name", ""),
            "type": r.get("type", ""),
            "conditions": r.get("conditions", r.get("formula", ""))[:200],
            "actions": r.get("actions", r.get("description", ""))[:200],
            "salience": r.get("salience", ""),
            "agenda_group": r.get("agenda_group", ""),
            "file": r.get("file", ""),
        }
        writer.writerow(row)

    return output.getvalue()


def _export_json_structured(rules: List[Dict]) -> str:
    """导出为标准化 JSON 数组。"""
    normalized: List[Dict] = []
    for r in rules:
        entry: Dict[str, Any] = {
            "layer": r.get("layer", ""),
            "rule_id": r.get("rule_id", r.get("formula_id", "")),
            "name": r.get("name", ""),
            "type": r.get("type", ""),
            "description": r.get("description", ""),
            "salience": r.get("salience"),
            "agenda_group": r.get("agenda_group"),
            "no_loop": r.get("no_loop", False),
            "file": r.get("file", ""),
            "file_path": r.get("file_path", ""),
            "line": r.get("line", 0),
        }

        # L1 专有字段
        if r.get("layer") == "L1":
            entry["formula"] = r.get("formula", "")
            entry["unit"] = r.get("unit", "")
            entry["module"] = r.get("module", "")

        # L2/L3/L4 专有字段
        if r.get("layer") in ("L2", "L3", "L4"):
            entry["conditions"] = r.get("conditions", "")
            entry["actions"] = r.get("actions", "")

            if r.get("type") == "json":
                entry["enabled"] = r.get("enabled", True)
                entry["tags"] = r.get("tags", [])
                entry["raw_definition"] = r.get("raw", {})

        normalized.append(entry)

    return json.dumps(normalized, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _get_default_rules_dir() -> Path:
    """获取默认的 rules 目录路径。"""
    script_dir = _get_script_dir()
    candidate1 = script_dir.parent / "rule-engine" / "src" / "main" / "resources" / "rules"
    if candidate1.exists():
        return candidate1
    candidate2 = script_dir.parent / "rules"
    if candidate2.exists():
        return candidate2
    return candidate2


def _get_layer_dirs(rules_dir: Path, layers: List[str]) -> Dict[str, Path]:
    """根据层获取对应的子目录映射。"""
    mapping = {
        "L1": rules_dir / "l1-physics",
        "L2": rules_dir / "l2-doctrine",
        "L3": rules_dir / "l3-tactical",
        "L4": rules_dir / "l4-learning",
    }
    # 如果子目录不存在，有些规则可能直接在 rules/ 下
    return {k: v for k, v in mapping.items() if k in layers}


def main() -> None:
    """主函数：解析参数并执行规则导出。"""
    parser = argparse.ArgumentParser(
        description="规则导出工具：将规则导出为 markdown、CSV 或 JSON 格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python export_rules.py
  python export_rules.py --format markdown --output rules_catalog.md
  python export_rules.py --format csv --layer L2,L3
  python export_rules.py --format json --output rules.json --layer all
        """,
    )

    default_rules = str(_get_default_rules_dir())

    parser.add_argument(
        "--format",
        type=str,
        default="markdown",
        choices=["markdown", "csv", "json"],
        help="输出格式 (默认: markdown)",
    )
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
        "--layer",
        type=str,
        default="all",
        help="要导出的层: L1|L2|L3|L4|all，多个用逗号分隔 (默认: all)",
    )

    args = parser.parse_args()

    # 解析层
    if args.layer == "all":
        layers = ["L1", "L2", "L3", "L4"]
    else:
        layers = [l.strip().upper() for l in args.layer.split(",") if l.strip()]
        valid = {"L1", "L2", "L3", "L4"}
        for l in layers:
            if l not in valid:
                logger.error("无效的层参数: %s (有效值: L1, L2, L3, L4)", l)
                sys.exit(1)

    # 解析规则目录
    rules_dir = Path(args.rules_dir)
    if not rules_dir.is_absolute():
        rules_dir = _get_script_dir().parent / rules_dir

    logger.info("规则目录: %s", rules_dir)
    logger.info("目标层: %s", layers)
    logger.info("输出格式: %s", args.format)

    if not rules_dir.exists():
        logger.error("规则目录不存在: %s", rules_dir)
        sys.exit(1)

    all_rules: List[Dict] = []

    # L1: 物理公式参考表
    if "L1" in layers:
        logger.info("加载 L1 物理层公式参考 (%d 项)", len(L1_PHYSICS_REFERENCE))
        all_rules.extend(L1_PHYSICS_REFERENCE)

    # L2: .drl 文件
    if "L2" in layers:
        drl_files = _collect_files(rules_dir, [".drl"])
        logger.info("找到 %d 个 DRL 文件", len(drl_files))
        for fp in drl_files:
            rules = _parse_drl_file(fp)
            logger.info("  %s: %d 条规则", fp.name, len(rules))
            all_rules.extend(rules)

    # L3: JSON 规则文件
    if "L3" in layers:
        # L3 优先从 l3-tactical 子目录读取
        l3_dir = rules_dir / "l3-tactical"
        if l3_dir.exists():
            json_files = _collect_files(l3_dir, [".json"])
        else:
            json_files = _collect_files(rules_dir, [".json"])
        logger.info("找到 %d 个 JSON 规则文件 (L3)", len(json_files))
        for fp in json_files:
            rules = _parse_json_rule_file(fp, layer="L3")
            logger.info("  %s: %d 条规则", fp.name, len(rules))
            all_rules.extend(rules)

    # L4: LLM 元规则
    if "L4" in layers:
        l4_dir = rules_dir / "l4-learning"
        if l4_dir.exists():
            l4_json_files = _collect_files(l4_dir, [".json"])
        else:
            l4_json_files = []
        logger.info("找到 %d 个 JSON 规则文件 (L4)", len(l4_json_files))
        for fp in l4_json_files:
            rules = _parse_json_rule_file(fp, layer="L4")
            logger.info("  %s: %d 条规则", fp.name, len(rules))
            all_rules.extend(rules)

    logger.info("共收集到 %d 条规则", len(all_rules))

    # ---- 生成输出 ----
    if args.format == "markdown":
        output = _export_markdown(all_rules)
    elif args.format == "csv":
        output = _export_csv(all_rules)
    elif args.format == "json":
        output = _export_json_structured(all_rules)
    else:
        output = ""

    # ---- 写入 ----
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output)
        logger.info("规则导出完成，已保存到: %s", output_path)
    else:
        print(output)

    sys.exit(0)


if __name__ == "__main__":
    main()
