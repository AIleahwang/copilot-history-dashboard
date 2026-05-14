@echo off
chcp 65001 >nul
echo.
echo ============================================
echo  Copilot History Dashboard 看板 卸载
echo ============================================
echo.
echo 即将删除看板代码（不会动你的 Copilot CLI 对话数据）
echo 路径：%~dp0
echo.
set /p CONFIRM=确认卸载？输入 yes 继续：
if /I not "%CONFIRM%"=="yes" (
  echo 已取消。
  pause
  exit /b 0
)

REM 先尝试关掉占用 8765 端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8765 ^| findstr LISTENING') do (
  echo 关闭占用端口的进程 PID=%%a
  taskkill /F /PID %%a >nul 2>&1
)

echo.
echo 删除目录中...
cd /d "%~dp0\.."
rmdir /S /Q "%~dp0"
echo.
echo ✓ 卸载完成。你的 Copilot CLI 历史对话依然完整保留在：
echo   %USERPROFILE%\.copilot\
echo.
pause
