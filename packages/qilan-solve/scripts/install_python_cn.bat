@echo off
:: Python 环境一键安装脚本（中国网络）
:: @author draven.chen <draven.chen@rccchina.com.cn>
:: @jira [main]

echo ========================================
echo   qilan-solve Python 环境安装向导
echo   （使用清华大学镜像源）
echo ========================================
echo.

:: 检查 Python 是否已安装
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [检测] 已找到 Python:
    python --version
    echo.
    set /p CONTINUE="是否继续安装依赖包？(Y/N): "
    if /i not "%CONTINUE%"=="Y" exit /b 0
) else (
    echo [错误] 未检测到 Python！
    echo.
    echo 请先安装 Python，推荐方式：
    echo.
    echo 方案 1: 官方 Python
    echo   下载地址: https://mirrors.tuna.tsinghua.edu.cn/python/3.12.0/python-3.12.0-amd64.exe
    echo   安装时务必勾选 "Add Python to PATH"
    echo.
    echo 方案 2: Anaconda
    echo   下载地址: https://mirrors.tuna.tsinghua.edu.cn/anaconda/archive/Anaconda3-2024.10-1-Windows-x86_64.exe
    echo.
    echo 方案 3: WinPython（便携版）
    echo   下载地址: https://mirror.ghproxy.com/https://github.com/winpython/winpython/releases/download/7.1.20241103final/Winpython64-3.12.7.1.exe
    echo.
    echo 详细说明请查看 INSTALL_CN.md
    pause
    exit /b 1
)

echo [步骤 1/3] 配置清华镜像源...
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [警告] 镜像源配置失败，将使用临时镜像源
)
echo.

echo [步骤 2/3] 安装依赖包（numpy, matplotlib, pillow, pandas, tqdm）...
pip install --trusted-host pypi.tuna.tsinghua.edu.cn -i https://pypi.tuna.tsinghua.edu.cn/simple numpy matplotlib pillow pandas tqdm
if %errorlevel% neq 0 (
    echo [错误] 依赖包安装失败
    echo.
    echo 尝试使用其他镜像源：
    echo   阿里云: pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
    echo   中科大: pip config set global.index-url https://pypi.mirrors.ustc.edu.cn/simple/
    pause
    exit /b 1
)
echo.

echo [步骤 3/3] 验证安装...
python -c "import numpy, matplotlib, PIL, pandas, tqdm; print('所有依赖包安装成功！')"
if %errorlevel% neq 0 (
    echo [错误] 验证失败
    pause
    exit /b 1
)
echo.

echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 下一步：
echo   1. 记录 Python 路径（将在下方显示）
echo   2. 编辑 config/solver.json，更新 python.interpreter 路径
echo   3. 运行 python scripts/check_environment.py 检查完整环境
echo.

echo Python 路径:
python -c "import sys; print(sys.executable)"
echo.

pause
