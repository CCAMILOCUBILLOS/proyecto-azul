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

echo Iniciando Azul en http://127.0.0.1:8710
echo Para detenerlo, cierra esta ventana o presiona Ctrl+C.
cd nucleo
uv run azul
goto :eof

:error
echo.
echo Algo fallo al preparar la app web. Revisa el mensaje de arriba.
pause
exit /b 1
