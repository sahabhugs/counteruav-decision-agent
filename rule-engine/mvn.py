#!/usr/bin/env python3
"""
反无人机决策规则引擎 - 跨平台启动脚本
支持中文路径，从 Git Bash / PowerShell / cmd 均可运行

用法:
    python mvn.py test           # 运行测试
    python mvn.py run            # 启动服务（开发模式 H2 数据库）
    python mvn.py compile        # 仅编译
"""

import subprocess
import os
import sys

# 路径配置
JDK_HOME = r"F:\lch\2026\反无\jdk-17.0.19+10"
MAVEN_HOME = r"F:\lch\2026\反无\apache-maven-3.9.6"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# 也可以用 junction 路径（无中文，兼容性更好）
# PROJECT_DIR = r"F:\lch\2026\temp\rule-engine-link"

def run_mvn(args, timeout=600):
    """运行 Maven 命令"""
    env = os.environ.copy()
    env["JAVA_HOME"] = JDK_HOME
    env["PATH"] = JDK_HOME + r"\bin;" + MAVEN_HOME + r"\bin;" + env.get("PATH", "")

    mvn_cmd = os.path.join(MAVEN_HOME, "bin", "mvn.cmd")
    cmd = [mvn_cmd] + args

    print(f"[Maven] {' '.join(args)}")
    print(f"[JDK]   {JDK_HOME}")
    print(f"[Dir]   {PROJECT_DIR}")
    print()

    return subprocess.run(cmd, cwd=PROJECT_DIR, env=env, timeout=timeout).returncode


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    action = sys.argv[1].lower()

    if action == "test":
        return run_mvn(["test", "-Dspring.profiles.active=dev"])

    elif action == "run" or action == "start":
        return run_mvn([
            "spring-boot:run",
            "-Dspring-boot.run.arguments=--spring.profiles.active=dev",
            "-Dspring-boot.run.jvmArguments=-Xmx512m -Dfile.encoding=UTF-8",
        ])

    elif action == "compile":
        return run_mvn(["compile", "-Dspring.profiles.active=dev"])

    elif action == "clean":
        return run_mvn(["clean", "compile", "-Dspring.profiles.active=dev"])

    else:
        # 透传原始 Maven 参数
        return run_mvn(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
