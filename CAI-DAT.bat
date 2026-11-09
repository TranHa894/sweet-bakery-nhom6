@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 goto fail
set "PYTHONUTF8=1"
echo === CAI DAT SWEET BAKERY - PYTHON 3.12 ===
echo Can ket noi Internet trong lan cai dat nay.
echo Hay dong cua so CHAY-WEBSITE truoc khi cai dat.
echo.
if not exist "requirements.txt" goto wrongfolder
if not exist "create_db.py" goto wrongfolder
if not exist "main.py" goto wrongfolder
if exist ".venv\Scripts\python.exe" goto checkvenv
goto findpython
:checkvenv
".venv\Scripts\python.exe" -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto install
:findpython
set "SWEET_PY=py -3.12"
%SWEET_PY% -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto prepare
set "SWEET_PY=python"
%SWEET_PY% -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto prepare
set SWEET_PY="%LocalAppData%\Programs\Python\Python312\python.exe"
%SWEET_PY% -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 goto nopython
:prepare
if not exist ".venv" goto createvenv
set "SWEET_BACKUP=.venv-backup-%RANDOM%-%RANDOM%"
if exist "%SWEET_BACKUP%" goto prepare
echo Dang giu lai moi truong cu trong %SWEET_BACKUP% ...
ren ".venv" "%SWEET_BACKUP%"
if errorlevel 1 goto busy
:createvenv
echo [1/4] Tao moi truong Python 3.12...
%SWEET_PY% -m venv ".venv"
if errorlevel 1 goto fail
:install
echo [2/4] Cap nhat pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto fail
echo [3/4] Cai thu vien tu requirements.txt...
".venv\Scripts\python.exe" -m pip install --only-binary=:all: -r "requirements.txt"
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto fail
echo [4/4] Khoi tao du lieu con thieu...
".venv\Scripts\python.exe" "create_db.py"
if errorlevel 1 goto fail
echo.
echo CAI DAT THANH CONG!
echo Tu lan sau, chi can mo CHAY-WEBSITE.bat.
pause
exit /b 0
:wrongfolder
echo LOI: Dat hai file BAT vao thu muc Sweet-Bakery chua main.py va requirements.txt.
goto fail
:nopython
echo LOI: Chua tim thay Python 3.12 64-bit.
echo Cai Python 3.12 64-bit, tick Add python.exe to PATH, roi mo lai file nay.
echo File nay khong su dung Python 3.15.
goto fail
:busy
echo LOI: Khong doi ten duoc .venv. Dong website va cac chuong trinh dang dung no.
goto fail
:fail
echo.
echo CAI DAT CHUA THANH CONG. Chup loi phia tren de gui nguoi ho tro.
pause
exit /b 1
