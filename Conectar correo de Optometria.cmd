@echo off
setlocal
cd /d "%~dp0nucleo"
uv run --no-sync python -c "from azul.cli import conectar_correo_optometria; conectar_correo_optometria()"
echo.
pause
