@echo off
setlocal
cd /d "%~dp0nucleo"
echo Respaldando la memoria de Azul...
echo.
uv run --no-sync python -c "from azul.cli import respaldar; respaldar()"
echo.
pause
