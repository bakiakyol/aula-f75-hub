@echo off
rem Run from anywhere: aula info   (install.ps1 puts this folder on PATH)
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
if not defined AULA_PYTHON goto launcher
"%AULA_PYTHON%" -m aula %*
exit /b
:launcher
where py >nul 2>nul || goto plain
py -3 -m aula %*
exit /b
:plain
python -m aula %*
exit /b
