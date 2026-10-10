@echo off
rem Opens the GUI with MSYS2's Python, which has GTK 3 (see docs/windows.md).
rem Set AULA_MSYS2 if MSYS2 isn't installed in C:\msys64.
setlocal
if not defined AULA_MSYS2 set AULA_MSYS2=C:\msys64
set BIN=%AULA_MSYS2%\ucrt64\bin
if not exist "%BIN%\python.exe" (
    echo MSYS2 Python with GTK 3 was not found in %BIN%.
    echo See docs\windows.md, "Graphical interface".
    pause
    exit /b 1
)
set PATH=%BIN%;%PATH%
set PYTHONUTF8=1
cd /d "%~dp0"
if exist "%BIN%\pythonw.exe" (
    start "" "%BIN%\pythonw.exe" -m aula gui
) else (
    "%BIN%\python.exe" -m aula gui
)
