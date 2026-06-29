@echo off
setlocal

set "RUNTIME_DIR=%LOCALAPPDATA%\BazaarHelper\runtime"
set "KEY_FILE=%RUNTIME_DIR%\deepseek_api_key.txt"

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
if not exist "%KEY_FILE%" type nul > "%KEY_FILE%"

start "" notepad.exe "%KEY_FILE%"

endlocal
