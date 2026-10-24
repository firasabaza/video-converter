@echo off
rem Double-cliquez pour lancer le convertisseur video.
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
uv run --no-dev video-converter %*
if errorlevel 1 pause
