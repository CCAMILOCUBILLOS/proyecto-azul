@echo off
setlocal
cd /d "%~dp0"

if not exist "app\dist\index.html" (
  echo Preparando la app web por primera vez...
  pushd app
  call npm install || goto :error
  call npm run build || goto :error
  popd
)

echo Iniciando Azul...
cd nucleo
rem Cliente de voz del portatil (atajo Ctrl+Alt+A y "Oye Azul"); se apaga al cerrar esta ventana.
start "" /b uv run --no-sync python -m azul.escritorio
uv run --quiet azul
goto :eof

:error
echo.
echo Algo fallo al preparar la app web. Revisa el mensaje de arriba.
pause
exit /b 1
