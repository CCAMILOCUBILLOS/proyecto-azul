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
uv run --quiet azul
goto :eof

:error
echo.
echo Algo fallo al preparar la app web. Revisa el mensaje de arriba.
pause
exit /b 1
