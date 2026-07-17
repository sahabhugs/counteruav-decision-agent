#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反无人机决策规则引擎 - 离线编译与测试脚本
使用本地 .m2/repository 缓存中的 Maven JAR 运行 Maven（无需互联网）
要求: JDK 已配置 + .m2/repository 已缓存依赖

用法:
    python build-with-cache.py compile   # 编译
    python build-with-cache.py test      # 运行测试
    python build-with-cache.py run       # 启动应用
"""

import os
import sys
import subprocess
import glob
import shutil

# ============================================================
# 配置
# ============================================================
JDK_PATH = r"C:\Users\asus\.jdks\temurin-24"
M2_REPO = os.path.expanduser(r"~/.m2/repository")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Maven 主类 JAR（从本地缓存查找）
MAVEN_EMBEDDER = os.path.join(M2_REPO, "org/apache/maven/maven-embedder")

def find_jar(base_path, artifact_id, version_prefix=""):
    """在 Maven 本地缓存中查找 JAR 文件"""
    if not os.path.exists(base_path):
        return None
    pattern = os.path.join(base_path, "*", f"{artifact_id}-*.jar")
    jars = glob.glob(pattern)
    # 排除 sources 和 javadoc
    jars = [j for j in jars if "-sources" not in j and "-javadoc" not in j]
    return jars[0] if jars else None

def build_classpath(jars):
    """构建 Java classpath"""
    separator = ";" if sys.platform == "win32" else ":"
    return separator.join(jars)

def run_maven_goal(goal, offline=True, dev_profile=True):
    """使用缓存的 Maven JAR 运行 Maven 目标"""
    java_exe = os.path.join(JDK_PATH, "bin", "java.exe")
    if not os.path.exists(java_exe):
        print(f"[ERROR] JDK 未找到: {java_exe}")
        return 1

    # 查找 Maven 核心 JAR
    maven_core_jars = glob.glob(os.path.join(M2_REPO, "org/apache/maven/**/*.jar"), recursive=True)
    # 过滤出需要的 JAR
    maven_jars = []
    needed_artifacts = [
        "maven-embedder", "maven-core", "maven-model", "maven-model-builder",
        "maven-artifact", "maven-settings", "maven-settings-builder",
        "maven-plugin-api", "maven-repository-metadata",
    ]
    for artifact in needed_artifacts:
        jar = find_jar(os.path.join(M2_REPO, "org/apache/maven"), artifact)
        if jar:
            maven_jars.append(jar)

    # 添加其他必要依赖
    more_deps = [
        ("org/apache/maven/resolver", ["maven-resolver-api", "maven-resolver-impl",
                                        "maven-resolver-connector-basic", "maven-resolver-transport-wagon"]),
        ("org/apache/maven/wagon", ["wagon-provider-api", "wagon-http"]),
        ("org/codehaus/plexus", ["plexus-utils", "plexus-component-annotations"]),
        ("org/slf4j", ["slf4j-api"]),
        ("org/apache/commons", ["commons-lang3"]),
        ("com/google/guava", ["guava"]),
        ("org/sonatype/plexus", ["plexus-sec-dispatcher", "plexus-cipher"]),
    ]
    for base, artifacts in more_deps:
        for artifact in artifacts:
            jar = find_jar(os.path.join(M2_REPO, base), artifact)
            if jar:
                maven_jars.append(jar)

    if not maven_jars:
        print("[ERROR] 未在 .m2/repository 中找到 Maven JAR")
        print("请安装 Maven 并运行一次 mvn 命令以缓存依赖")
        print("下载: https://maven.apache.org/download.cgi")
        return 1

    cp = build_classpath(maven_jars)
    props = {
        "maven.home": os.path.join(M2_REPO, "..", ".."),  # parent of .m2
        "classworlds.conf": "",
        "maven.multiModuleProjectDirectory": PROJECT_DIR,
    }

    sys_props = " ".join([f"-D{k}={v}" for k, v in props.items()])

    # 构建 Maven 命令参数
    maven_args = goal
    if offline:
        maven_args += " -o"  # offline mode
    if dev_profile:
        maven_args += " -Dspring.profiles.active=dev"

    cmd = f'"{java_exe}" -cp "{cp}" {sys_props} org.apache.maven.cli.MavenCli {maven_args}'

    print(f"[INFO] 运行: mvn {maven_args}")
    print(f"[INFO] 工作目录: {PROJECT_DIR}")
    print()

    result = subprocess.run(cmd, shell=True, cwd=PROJECT_DIR)
    return result.returncode


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n可用命令: compile, test, run")
        return 1

    command = sys.argv[1].lower()

    # 验证 JDK
    java_exe = os.path.join(JDK_PATH, "bin", "java.exe")
    if not os.path.exists(java_exe):
        print(f"[ERROR] JDK 未找到: {java_exe}")
        print("请修改本脚本中的 JDK_PATH 变量")
        return 1

    print("=" * 60)
    print("  反无人机决策规则引擎 - 离线构建")
    print(f"  JDK: {JDK_PATH}")
    print(f"  M2 缓存: {M2_REPO}")
    print("=" * 60)
    print()

    if command == "compile":
        print("[1/2] 编译项目...")
        ret = run_maven_goal("compile")
        if ret != 0:
            print("\n[FAIL] 编译失败")
            print("如果因为缺少 Maven 启动器 JAR 而失败，请:")
            print("  1. 下载 Maven: https://maven.apache.org/download.cgi")
            print("  2. 解压并添加 bin 目录到 PATH")
            print("  3. 或在 IntelliJ IDEA 中打开本项目")
            return ret
        print("[OK] 编译成功")

    elif command == "test":
        print("[1/2] 编译测试代码...")
        ret = run_maven_goal("test-compile")
        if ret != 0:
            return ret
        print("\n[2/2] 运行测试...")
        ret = run_maven_goal("test")
        if ret == 0:
            print("\n[PASS] 所有测试通过!")
        else:
            print("\n[FAIL] 测试失败")

    elif command == "run":
        print("启动规则引擎服务...")
        ret = run_maven_goal("spring-boot:run -Dspring-boot.run.jvmArguments=\"-Xmx512m\"")
        return ret

    else:
        print(f"未知命令: {command}")
        print("可用命令: compile, test, run")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
