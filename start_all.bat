@echo off
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d %~dp0

if defined QIANXUE_PYTHON (
    set "PY=%QIANXUE_PYTHON%"
    goto :found
)

REM 1. SpaceX env (preferred - has all project deps)
if exist "D:\Miniconda\envs\SpaceX\python.exe" (
    set "PY=D:\Miniconda\envs\SpaceX\python.exe"
    goto :found
)

REM 2. other conda envs
for /d %%e in (
    "%USERPROFILE%\miniconda3\envs\*"
    "%USERPROFILE%\Miniconda3\envs\*"
    "D:\Miniconda\envs\*"
    "D:\Miniconda3\envs\*"
    "C:\Miniconda3\envs\*"
) do (
    if exist "%%e\python.exe" (
        set "PY=%%e\python.exe"
        goto :found
    )
)

REM 2. venv
if exist "venv\Scripts\python.exe" (
    set "PY=venv\Scripts\python.exe"
    goto :found
)
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    goto :found
)

REM 3. conda base (fallback)
for %%d in (
    "%USERPROFILE%\miniconda3\python.exe"
    "%USERPROFILE%\Miniconda3\python.exe"
    "D:\Miniconda\python.exe"
    "D:\Miniconda3\python.exe"
    "C:\Miniconda3\python.exe"
) do (
    if exist %%d (
        set "PY=%%~d"
        goto :found
    )
)

REM 4. system PATH
where python >nul 2>&1
if %errorlevel%==0 (
    set "PY=python"
    goto :found
)

echo.
echo [ERROR] Python not found. Try one of:
echo   1. set QIANXUE_PYTHON=path\to\python.exe
echo   2. python -m venv venv
echo.
pause
exit /b 1

:found
echo Using Python: %PY%
"%PY%" start_all.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Exit code: %errorlevel%
)
pause
