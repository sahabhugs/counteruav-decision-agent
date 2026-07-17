@echo off
chcp 65001 >nul
REM ============================================================
REM  反无人机决策规则引擎 - 测试运行脚本
REM  运行所有单元测试（ThreatEvaluator, StrategyMatcher,
REM  ConfidenceGate, PhysicsLibrary）
REM ============================================================

REM --- 设置 JDK ---
set "JDK_PATH=F:\lch\2026\反无\jdk-21.0.2"
if not exist "%JDK_PATH%\bin\java.exe" (
    echo [ERROR] JDK 未找到，请先运行 setup-env.bat
    pause
    exit /b 1
)
set JAVA_HOME=%JDK_PATH%
set PATH=%JAVA_HOME%\bin;%PATH%

echo.
echo ========================================
echo   反无人机决策规则引擎 - 单元测试
echo ========================================
echo.
echo JDK: %JAVA_HOME%
echo.

REM --- 查找 Maven ---
set MVN_CMD=
for %%d in (mvn.cmd mvn.bat mvn) do (
    where %%d >nul 2>&1
    if !errorlevel!==0 set MVN_CMD=%%d
)
if "%MVN_CMD%"=="" (
    echo [ERROR] Maven (mvn) 未找到
    echo 请安装 Maven 或使用 IntelliJ IDEA 打开项目运行测试
    echo.
    echo Maven 下载地址: https://maven.apache.org/download.cgi
    echo 将 Maven 的 bin 目录添加到系统 PATH 即可
    pause
    exit /b 1
)

echo [INFO] 使用: %MVN_CMD%
echo.

REM --- 运行测试 ---
echo ========================================
echo   编译并运行所有测试...
echo ========================================
echo.

call %MVN_CMD% clean test -Dspring.profiles.active=dev 2>&1

if %errorlevel%==0 (
    echo.
    echo ========================================
    echo   [PASS] 所有测试通过！
    echo ========================================
) else (
    echo.
    echo ========================================
    echo   [FAIL] 测试失败，请检查上方日志
    echo ========================================
)

echo.
echo 测试报告位置: target\surefire-reports\
pause
