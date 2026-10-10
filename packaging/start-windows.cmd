@echo off
chcp 65001 >nul
setlocal
if /i not "%PROCESSOR_ARCHITECTURE%"=="AMD64" if /i not "%PROCESSOR_ARCHITEW6432%"=="AMD64" (
  echo 此安装包适用于 Windows 11 x64，请确认系统架构。
  pause
  exit /b 1
)
"%~dp0bin\smartsketch-launcher.exe"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
