@echo off
chcp 65001 >nul
REM ============================================================
REM  反无人机决策规则引擎 - 一键编译+测试+启动
REM  用法: build-and-run.bat [test|run|all]
REM    test - 仅运行测试
REM    run  - 编译并启动服务
REM    all  - 完整流程（默认）
REM ============================================================

setlocal enabledelayedexpansion

REM --- 设置 JDK ---
set "JDK_PATH=F:\lch\2026\反无\jdk-21.0.2"
if not exist "%JDK_PATH%\bin\java.exe" (
    echo [ERROR] JDK 未找到: %JDK_PATH%
    echo 请修改本脚本中的 JDK_PATH 变量指向正确的 JDK 路径
    pause
    exit /b 1
)
set JAVA_HOME=%JDK_PATH%
set PATH=%JAVA_HOME%\bin;%PATH%

echo.
echo ========================================
echo   反无人机决策规则引擎 v1.0.0
echo   JDK: %JAVA_HOME%
echo ========================================

REM --- 解析参数 ---
set MODE=%1
if "%MODE%"=="" set MODE=all

REM --- 查找 Maven ---
set MVN_CMD=
where mvn >nul 2>&1
if %errorlevel%==0 (
    set MVN_CMD=mvn
    echo   Maven: 已就绪
) else (
    echo   Maven: 未安装（请先安装 Maven 或使用 IntelliJ IDEA）
    echo.
    echo   Maven 下载: https://maven.apache.org/download.cgi
    echo   下载后解压并添加 bin 目录到系统 PATH
    pause
    exit /b 1
)
echo.

REM ============================================================
REM  1. 编译项目
REM ============================================================
echo [1/3] 编译项目...
call mvn clean compile -Dspring.profiles.active=dev -q
if %errorlevel% neq 0 (
    echo [FAIL] 编译失败
    pause
    exit /b 1
)
echo [OK] 编译成功
echo.

REM ============================================================
REM  2. 运行测试
REM ============================================================
if "%MODE%"=="test" goto :RUN_TESTS
if "%MODE%"=="all" goto :RUN_TESTS
goto :RUN_APP

:RUN_TESTS
echo [2/3] 运行单元测试...
call mvn test -Dspring.profiles.active=dev
if %errorlevel% neq 0 (
    echo [WARN] 部分测试失败，查看 target/surefire-reports/
) else (
    echo [OK] 所有测试通过
)
echo.

if "%MODE%"=="test" goto :DONE

REM ============================================================
REM  3. 启动应用（开发模式 H2 数据库）
REM ============================================================
:RUN_APP
echo [3/3] 启动规则引擎服务（开发模式）...
echo.
echo   数据库: H2 嵌入式
echo   端口:   8080
echo   H2 Console: http://localhost:8080/h2-console
echo   API 测试:
echo     curl -X POST http://localhost:8080/api/decision/assess ^
echo       -H "Content-Type: application/json" ^
echo       -d @test_request.json
echo.
echo ========================================
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

call mvn spring-boot:run ^
    -Dspring-boot.run.arguments="--spring.profiles.active=dev" ^
    -Dspring-boot.run.jvmArguments="-Xmx512m"

:DONE
endlocal
