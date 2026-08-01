@echo off
REM ===========================================================================
REM Build the Windows installer for Apipos.
REM
REM Produces a standalone executable (dist\Apipos.exe) and, if Inno Setup
REM (iscc) is available, a full installer (dist\Apipos-Setup.exe).
REM
REM Usage: double-click this file, or run it from a terminal:
REM   build-windows.bat            (pregunta la version a compilar)
REM   build-windows.bat 1.0.5      (usa esa version, sin preguntar)
REM
REM La version elegida se escribe en app-meta.env antes de compilar.
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- App metadata (single source of truth: app-meta.env) ------------------
for /f "tokens=1,2 delims==" %%A in ('findstr /v "^#" app-meta.env') do set "%%A=%%B"

set SPEC=apipos.spec
set VENV=.venv

REM --- 0. Version: preguntar y actualizar app-meta.env ----------------------
set "NEW_VERSION=%~1"
if not defined NEW_VERSION (
  echo.
  echo Version actual: %APP_VERSION%
  set /p "NEW_VERSION=Version a compilar [%APP_VERSION%]: "
)
if not defined NEW_VERSION set "NEW_VERSION=%APP_VERSION%"
set "NEW_VERSION=%NEW_VERSION: =%"
set "NEW_VERSION=%NEW_VERSION:"=%"

REM Solo digitos y puntos, empezando y terminando en digito, con al menos un punto.
REM (findstr no soporta grupos, por eso son dos comprobaciones.)
set "VERSION_OK=1"
echo(%NEW_VERSION%|findstr /r /c:"^[0-9][0-9.]*[0-9]$" >nul || set "VERSION_OK="
echo(%NEW_VERSION%|findstr /r /c:"[0-9]\.[0-9]" >nul || set "VERSION_OK="
if not defined VERSION_OK (
  echo ERROR: version invalida "%NEW_VERSION%". Usa el formato 1.0.5
  exit /b 1
)

if "%NEW_VERSION%"=="%APP_VERSION%" goto :version_ok

echo ==^> Actualizando app-meta.env: %APP_VERSION% -^> %NEW_VERSION%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path (Get-Location) 'app-meta.env'; $t=[IO.File]::ReadAllText($p); $t=[Text.RegularExpressions.Regex]::Replace($t,'(?m)^APP_VERSION=.*$','APP_VERSION=%NEW_VERSION%'); [IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding($false)))"

REM Releer para confirmar que el cambio quedo escrito.
for /f "tokens=1,2 delims==" %%A in ('findstr /v "^#" app-meta.env') do set "%%A=%%B"
if not "!APP_VERSION!"=="%NEW_VERSION%" (
  echo ERROR: no se pudo actualizar APP_VERSION en app-meta.env
  exit /b 1
)

:version_ok
echo ==^> %APP_NAME% v%APP_VERSION% ^(%APP_PUBLISHER%^)

REM --- 1. Virtual environment + dependencies --------------------------------
if not exist "%VENV%" (
  echo ==^> Creando entorno virtual en %VENV%
  python -m venv "%VENV%"
)
call "%VENV%\Scripts\activate.bat"

echo ==^> Instalando dependencias ^(requirements-windows.txt + pyinstaller^)
python -m pip install --upgrade pip >nul
pip install -r requirements-windows.txt >nul
pip install pyinstaller >nul

REM --- 2. Clean previous artifacts ------------------------------------------
echo ==^> Limpiando build\ y dist\
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM --- 3. Build the .exe with PyInstaller -----------------------------------
echo ==^> Empaquetando con PyInstaller
pyinstaller --noconfirm "%SPEC%"

if not exist "dist\%APP_NAME%.exe" (
  echo ERROR: no se genero dist\%APP_NAME%.exe
  exit /b 1
)

REM --- 4. Optional: build the installer with Inno Setup ---------------------
echo ==^> Buscando Inno Setup ^(iscc^) para crear el instalador
set "ISCC_CMD="

REM 4a. Primero buscar iscc en el PATH.
where iscc >nul 2>nul
if %errorlevel%==0 set "ISCC_CMD=iscc"

REM 4b. Si no esta en el PATH, probar las rutas de instalacion por defecto.
if not defined ISCC_CMD if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_CMD if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_CMD if exist "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe" set "ISCC_CMD=%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
if not defined ISCC_CMD if exist "%ProgramFiles%\Inno Setup 5\ISCC.exe" set "ISCC_CMD=%ProgramFiles%\Inno Setup 5\ISCC.exe"

if defined ISCC_CMD (
  echo ==^> Usando Inno Setup: !ISCC_CMD!
  "!ISCC_CMD!" /DAppName=%APP_NAME% /DAppVersion=%APP_VERSION% /DAppPublisher=%APP_PUBLISHER% installer-windows.iss
  echo.
  echo Instalador creado: dist\%APP_NAME%-Setup.exe
) else (
  echo.
  echo Inno Setup no encontrado ^(ni en PATH ni en rutas por defecto^).
  echo El ejecutable portable quedo en: dist\%APP_NAME%.exe
  echo Para crear un instalador instala Inno Setup: https://jrsoftware.org/isdl.php
)

echo.
echo Listo.
endlocal
