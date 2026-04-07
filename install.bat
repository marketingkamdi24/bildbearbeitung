@echo off
setlocal EnableDelayedExpansion
echo ========================================
echo  Image-Project Environment Setup
echo ========================================
echo.

set REQUIRED_VER=3.13
set VENV_DIR=%~dp0.venv
set PYTHON_EXE=

REM ══════════════════════════════════════════════════════════════
REM  Step 1: Find Python 3.13 — try multiple methods
REM ══════════════════════════════════════════════════════════════
echo [1/6] Searching for Python %REQUIRED_VER%...

REM Method A: Windows py launcher (most reliable)
py -%REQUIRED_VER% --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('py -%REQUIRED_VER% -c "import sys; print(sys.executable)"') do set PYTHON_EXE=%%i
    echo   Found via py launcher: !PYTHON_EXE!
    goto :found_python
)

REM Method B: python3.13 on PATH
python3.13 --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('python3.13 -c "import sys; print(sys.executable)"') do set PYTHON_EXE=%%i
    echo   Found on PATH: !PYTHON_EXE!
    goto :found_python
)

REM Method C: plain 'python' — check if it's 3.13
python --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('python -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')"') do set PY_VER=%%i
    if "!PY_VER!"=="%REQUIRED_VER%" (
        for /f "tokens=*" %%i in ('python -c "import sys; print(sys.executable)"') do set PYTHON_EXE=%%i
        echo   Found as 'python': !PYTHON_EXE!
        goto :found_python
    )
    echo   'python' is version !PY_VER!, not %REQUIRED_VER%.
)

REM Method D: Scan common install directories
echo   Scanning common install directories...
for %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313-64\python.exe"
    "C:\Python313\python.exe"
    "C:\Python\Python313\python.exe"
    "%PROGRAMFILES%\Python313\python.exe"
    "%PROGRAMFILES(x86)%\Python313\python.exe"
) do (
    if exist %%D (
        set PYTHON_EXE=%%~D
        echo   Found at: !PYTHON_EXE!
        goto :found_python
    )
)

echo.
echo   ERROR: Python %REQUIRED_VER% was NOT found on this system.
echo   Please install Python %REQUIRED_VER% from:
echo     https://www.python.org/downloads/
echo   Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found_python
echo.

REM ══════════════════════════════════════════════════════════════
REM  Step 2: Create or verify virtual environment
REM ══════════════════════════════════════════════════════════════
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo [2/6] Virtual environment already exists.
    REM Verify it uses the correct Python version
    for /f "tokens=*" %%i in ('"%VENV_DIR%\Scripts\python.exe" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')"') do set VENV_VER=%%i
    if not "!VENV_VER!"=="%REQUIRED_VER%" (
        echo   WARNING: .venv uses Python !VENV_VER!, recreating with %REQUIRED_VER%...
        rmdir /s /q "%VENV_DIR%" 2>nul
        "!PYTHON_EXE!" -m venv "%VENV_DIR%"
        echo   Recreated.
    ) else (
        echo   Confirmed: .venv uses Python %REQUIRED_VER%.
    )
) else (
    echo [2/6] Creating virtual environment with Python %REQUIRED_VER%...
    "!PYTHON_EXE!" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo   Created.
)
echo.

REM ══════════════════════════════════════════════════════════════
REM  Step 3: Activate and upgrade pip
REM ══════════════════════════════════════════════════════════════
call "%VENV_DIR%\Scripts\activate.bat"
echo [3/6] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo.

REM ══════════════════════════════════════════════════════════════
REM  Step 4: Install pinned packages
REM ══════════════════════════════════════════════════════════════
echo [4/6] Installing pinned dependencies...
python -m pip install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 (
    echo   WARNING: Some packages had issues. Check output above.
) else (
    echo   All packages installed.
)
echo.

REM ══════════════════════════════════════════════════════════════
REM  Step 5: Register Jupyter kernel
REM ══════════════════════════════════════════════════════════════
echo [5/6] Registering Jupyter kernel...
python -m pip install ipykernel --quiet
python -m ipykernel install --user --name image-project --display-name "Python (image-project)"
echo.

REM ══════════════════════════════════════════════════════════════
REM  Step 6: Verify
REM ══════════════════════════════════════════════════════════════
echo [6/6] Verifying installations...
echo.
python -c "import sys; print('  Python', sys.version.split()[0])"
python -c "import PIL; print('  OK Pillow:', PIL.__version__)" 2>nul || echo   FAIL Pillow
python -c "import numpy; print('  OK NumPy:', numpy.__version__)" 2>nul || echo   FAIL NumPy
python -c "import cv2; print('  OK OpenCV:', cv2.__version__)" 2>nul || echo   FAIL OpenCV
python -c "import gradio; print('  OK Gradio:', gradio.__version__)" 2>nul || echo   FAIL Gradio
python -c "import rembg; print('  OK rembg: Installed')" 2>nul || echo   FAIL rembg
python -c "import fitz; print('  OK PyMuPDF:', fitz.__version__)" 2>nul || echo   FAIL PyMuPDF
python -c "import pandas; print('  OK pandas:', pandas.__version__)" 2>nul || echo   FAIL pandas
python -c "import openpyxl; print('  OK openpyxl:', openpyxl.__version__)" 2>nul || echo   FAIL openpyxl

echo.
echo ========================================
echo  Setup Complete!
echo ========================================
echo.
echo To use the environment:
echo   1. Open VS Code in this folder
echo   2. The kernel 'Python (image-project)' is auto-registered
echo   3. Run bild-bearbeitung.ipynb — Cell 0 will auto-select it
echo.
echo Or activate manually:  .venv\Scripts\activate
echo.
pause