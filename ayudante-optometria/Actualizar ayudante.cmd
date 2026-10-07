@echo off
setlocal
rem Baja la version nueva de Azul desde GitHub y la copia encima de esta carpeta (ADR 0040).
rem Conserva la clave del ayudante (.clave) y su registro; no borra nada.
cd /d "%~dp0.."
echo Bajando la version nueva de Azul desde GitHub...
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $zip=Join-Path $env:TEMP 'azul-main.zip'; $dir=Join-Path $env:TEMP 'azul-main'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest 'https://github.com/CCAMILOCUBILLOS/proyecto-azul/archive/refs/heads/main.zip' -OutFile $zip -UseBasicParsing; if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }; Expand-Archive $zip $dir; robocopy (Join-Path $dir 'proyecto-azul-main') (Get-Location).Path /E /XF .clave ayudante.log /NFL /NDL /NJH /NJS | Out-Null; Remove-Item $zip -Force; Remove-Item $dir -Recurse -Force"
if errorlevel 1 (
  echo.
  echo No se pudo actualizar. Revisa el mensaje de arriba.
) else (
  echo.
  echo Listo. Cierra la ventana del ayudante y abre otra vez "Iniciar ayudante de Azul".
)
pause
