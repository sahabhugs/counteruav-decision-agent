@echo off
chcp 65001 >nul
REM ============================================================
REM  反无人机决策规则引擎 - 环境配置脚本
REM  用法: 双击运行或在命令行执行 setup-env.bat
REM ============================================================

echo.
echo ========================================
echo   配置 Java 和 Maven 环境变量
echo ========================================
echo.

REM --- 设置 JDK 路径（IntelliJ IDEA 自带的 Eclipse Temurin JDK 24）---
set "JDK_PATH=F:\lch\2026\反无\jdk-21.0.2"
if exist "%JDK_PATH%\bin\java.exe" (
    setx JAVA_HOME "%JDK_PATH%" >nul
    set JAVA_HOME=%JDK_PATH%
    echo [OK] JAVA_HOME = %JDK_PATH%
    "%JDK_PATH%\bin\java" -version 2>&1 | findstr /C:"OpenJDK"
) else (
    echo [ERROR] JDK 未找到: %JDK_PATH%
    echo 请手动设置 JAVA_HOME 环境变量
)

echo.
echo ========================================
echo   环境配置完成！
echo   关闭此窗口后，重新打开命令行即可生效
echo ========================================
echo.
echo   运行方式:
echo     run-tests.bat   - 运行单元测试
echo     start-dev.bat   - 开发模式启动（H2嵌入式数据库）
echo     start-prod.bat  - 生产模式启动（需要MySQL）
echo.
pause
