@echo off
setlocal
cd /d "%~dp0"
rem Ayudante de Outlook de Azul (ADR 0040). Dejar esta ventana abierta.
python ayudante_outlook.py
echo.
echo El ayudante se detuvo. Revisa el mensaje de arriba.
pause
