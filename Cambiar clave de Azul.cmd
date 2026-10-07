@echo off
setlocal
cd /d "%~dp0nucleo"
echo Cambiando la clave de acceso de Azul...
echo.
uv run --no-sync python -c "from azul.cli import cambiar_clave_y_mostrar; cambiar_clave_y_mostrar()"
echo.
pause
