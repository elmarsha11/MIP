@echo off
REM Abre el tablero de MIP. Doble click y listo.
cd /d "%~dp0"
python -u src\tablero\servidor.py
