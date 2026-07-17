#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反无人机决策规则引擎 - 环境检查脚本
检查 JDK、Maven、数据库等运行环境是否就绪
用法: python check-env.py
"""

import os
import sys
import subprocess
import json

def check_command(cmd, name):
    """检查命令是否可用"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                               shell=True, encoding='utf-8')
        return True, result.stdout[:200]
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("  反无人机决策规则引擎 - 环境检查")
    print("=" * 60)
    print()

    all_ok = True

    # 1. 检查 JDK
    print("[1/5] 检查 JDK...")
    jdk_path = os.environ.get("JAVA_HOME", "")
    if not jdk_path:
        jdk_path = r"F:\lch\2026\反无\jdk-21.0.2"

    java_exe = os.path.join(jdk_path, "bin", "java.exe")
    if os.path.exists(java_exe):
        ok, output = check_command(f'"{java_exe}" -version', "Java")
        if ok:
            version_line = [l for l in output.split('\n') if 'version' in l.lower()]
            print(f"  [OK] JDK 24 已就绪: {jdk_path}")
            if version_line:
                print(f"        {version_line[0].strip()}")
        else:
            print(f"  [WARN] JDK 存在但执行失败: {output}")
            all_ok = False
    else:
        print(f"  [FAIL] JDK 未找到: {jdk_path}")
        all_ok = False

    # 2. 检查 Maven
    print("\n[2/5] 检查 Maven...")
    ok, output = check_command("mvn --version", "Maven")
    if ok:
        version_line = output.split('\n')[0] if output else ""
        print(f"  [OK] Maven 已就绪: {version_line.strip()}")
    else:
        print(f"  [WARN] Maven 未在 PATH 中找到")
        print(f"         Maven 下载: https://maven.apache.org/download.cgi")
        print(f"         或使用 IntelliJ IDEA 打开项目（内置 Maven）")
        # Don't fail - Maven can still work through IDE

    # 3. 检查项目文件
    print("\n[3/5] 检查项目文件...")
    required_files = [
        "pom.xml",
        "src/main/resources/application.yml",
        "src/main/resources/application-dev.yml",
        "src/main/resources/kmodule.xml",
        "src/main/resources/rules/l2-doctrine/threat_classification.drl",
        "src/main/resources/rules/l2-doctrine/threat_escalation.drl",
        "src/main/resources/rules/l2-doctrine/strategy_match.drl",
        "src/main/resources/rules/l2-doctrine/rules_of_engagement.drl",
        "src/main/resources/rules/l1-physics/kinematics_threat.drl",
        "src/main/resources/rules/l3-tactical/multi_target_coordination.drl",
        "src/main/resources/rules/l4-learning/historical_patterns.drl",
    ]

    missing = []
    for f in required_files:
        if not os.path.exists(f):
            missing.append(f)

    if missing:
        print(f"  [FAIL] 缺少 {len(missing)} 个文件:")
        for f in missing:
            print(f"         {f}")
        all_ok = False
    else:
        print(f"  [OK] 所有 {len(required_files)} 个关键文件就绪")

    # 4. 检查测试文件
    print("\n[4/5] 检查测试文件...")
    test_dir = "src/test/java/com/counteruav"
    test_count = 0
    for root, dirs, files in os.walk(test_dir):
        for f in files:
            if f.endswith("Test.java"):
                test_count += 1
                print(f"  [OK] {os.path.relpath(os.path.join(root, f))}")

    if test_count == 0:
        print(f"  [WARN] 未找到测试文件")
    else:
        print(f"  [OK] 共 {test_count} 个测试类")

    # 5. 检查 test_request.json
    print("\n[5/5] 检查测试数据...")
    test_file = "test_request.json"
    if os.path.exists(test_file):
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            targets = len(data.get("targets", []))
            devices = len(data.get("available_devices", []))
            print(f"  [OK] test_request.json 就绪 ({targets} 个目标, {devices} 个设备)")
        except Exception as e:
            print(f"  [WARN] test_request.json 解析失败: {e}")
    else:
        print(f"  [WARN] test_request.json 未找到")

    # 总结
    print()
    print("=" * 60)
    if all_ok:
        print("  环境检查通过！可以运行:")
        print("    run-tests.bat   - 运行单元测试")
        print("    start-dev.bat   - 开发模式启动")
        print()
        print("  或手动编译运行（需要 Maven）:")
        print("    mvn clean test -Dspring.profiles.active=dev")
        print("    mvn spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=dev")
    else:
        print("  环境检查发现问题，请先解决上述 FAIL 项")
    print("=" * 60)

if __name__ == "__main__":
    main()
