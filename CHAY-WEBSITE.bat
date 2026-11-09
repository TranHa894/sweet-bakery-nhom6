@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 goto fail
set "PYTHONUTF8=1"
if not exist "main.py" goto wrongfolder
set "SWEET_RUN_PY=.venv\Scripts\python.exe"
if exist "%SWEET_RUN_PY%" goto checkpython
set "SWEET_RUN_PY=chatbot\.venv\Scripts\python.exe"
if not exist "%SWEET_RUN_PY%" goto setup
:checkpython
"%SWEET_RUN_PY%" -B -c "import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto setup
"%SWEET_RUN_PY%" -B -c "import fastapi,uvicorn,pydantic,tzdata" >nul 2>&1
if errorlevel 1 goto setup
echo Giu cua so nay mo trong khi dung website. Ctrl+C de dung.
echo Dia chi mac dinh: http://127.0.0.1:8000/
echo Quan ly don: http://127.0.0.1:8000/admin.html
"%SWEET_RUN_PY%" -B -X utf8 "main.py" --open
if errorlevel 1 goto fail
exit /b 0
:setup
echo Hay chay CAI-DAT.bat den khi bao CAI DAT THANH CONG, roi mo lai file nay.
pause
exit /b 1
:wrongfolder
echo Hay dat file nay cung thu muc voi main.py.
:fail
echo Khong chay duoc website. Chup thong bao loi phia tren de gui nguoi ho tro.
pause
exit /b 1
