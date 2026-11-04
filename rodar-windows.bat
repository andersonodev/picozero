@echo off
rem rodar-windows.bat - sobe o backend (porta 8000) e o painel (porta 5173) e abre o navegador.
rem Na primeira vez chama o instalar-windows.bat sozinho.
setlocal
title PicoZero
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%ProgramFiles%\nodejs;%PATH%"

if not exist "backend\.venv" goto instalar
if not exist "frontend\node_modules" goto instalar
goto rodar

:instalar
call "%~dp0instalar-windows.bat" /sem-pausa
if errorlevel 1 exit /b 1

:rodar
echo Subindo o backend em http://127.0.0.1:8000 ...
start "PicoZero backend - feche para parar" /D "%~dp0backend" cmd /k uv run fastapi dev
echo Subindo o painel em http://localhost:5173 ...
start "PicoZero painel - feche para parar" /D "%~dp0frontend" cmd /k npm run dev

rem Na primeira vez o backend monta o banco; espera ele responder antes de abrir o painel (ate 90 s).
echo Esperando o backend ficar pronto...
set /a ESPERA=0
:esperar
curl -s -f -o nul http://127.0.0.1:8000/api/saude 2>nul
if not errorlevel 1 goto pronto
set /a ESPERA+=1
if %ESPERA% geq 90 goto pronto
timeout /t 1 /nobreak >nul
goto esperar

:pronto
start "" http://localhost:5173
echo.
echo ===== PicoZero rodando =====
echo   Painel:        http://localhost:5173
echo   API e docs:    http://127.0.0.1:8000/docs
echo.
echo Para parar, feche as duas janelas "PicoZero backend" e "PicoZero painel".
echo.
pause
