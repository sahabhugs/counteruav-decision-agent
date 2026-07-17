@echo off
chcp 65001 >nul
REM ============================================================
REM  反无人机决策规则引擎 - 开发模式启动
REM  使用 H2 嵌入式数据库，无需安装 MySQL
REM  使用方式: start-dev.bat
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
echo   反无人机决策规则引擎 - 开发模式
echo   数据库: H2 嵌入式 (无MySQL)
echo   端口: 8080
echo   H2 Console: http://localhost:8080/h2-console
echo ========================================
echo.

REM --- 确保数据目录存在 ---
if not exist "data" mkdir data

REM --- 查找 Maven ---
set MVN_CMD=
where mvn >nul 2>&1
if %errorlevel%==0 (
    set MVN_CMD=mvn
) else (
    echo [WARN] Maven (mvn) 未找到
)

if not "%MVN_CMD%"=="" (
    echo [INFO] 使用 Maven 启动...
    echo.
    call mvn spring-boot:run ^
        -Dspring-boot.run.arguments="--spring.profiles.active=dev" ^
        -Dspring-boot.run.jvmArguments="-Xmx512m"
) else (
    echo [INFO] 尝试直接使用 java -jar 启动...
    echo [INFO] 请先编译: mvn clean package -DskipTests
    echo.
    set JAR_FILE=target\rule-engine-1.0.0-SNAPSHOT.jar
    if exist "%JAR_FILE%" (
        java -Xmx512m -jar "%JAR_FILE%" --spring.profiles.active=dev
    ) else (
        echo [ERROR] 未找到 JAR 文件: %JAR_FILE%
        echo 请先使用 Maven 编译: mvn clean package -DskipTests
    )
)

echo.
pause
