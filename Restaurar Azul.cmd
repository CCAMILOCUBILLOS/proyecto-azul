@echo off
setlocal
cd /d "%~dp0nucleo"
echo Restaurar la memoria de Azul desde el respaldo mas reciente.
echo Para usar un respaldo especifico, arrastra su archivo .zip sobre este icono.
echo.
uv run --no-sync python -c "from azul.cli import restaurar; restaurar()" %1
echo.
pause
