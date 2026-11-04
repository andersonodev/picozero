@echo off
rem rodar-windows.bat - sobe o backend (porta 8000) e o painel (porta 5173) e abre o navegador.
rem Se ainda nao instalou neste Windows (ou a pasta veio de outro computador), chama o instalar-windows.bat.
setlocal
title PicoZero
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%ProgramFiles%\nodejs;%PATH%"
set "SAUDE=http://127.0.0.1:8000/api/saude"

rem .venv\Scripts e o marcador do npm so existem quando a instalacao foi feita neste Windows.
if not exist "backend\.venv\Scripts\python.exe" goto instalar
if not exist "frontend\node_modules\.instalado-windows" goto instalar
goto backend

:instalar
call "%~dp0instalar-windows.bat" /sem-pausa
if errorlevel 1 exit /b 1

rem ---------- backend
:backend
curl -s -f -o nul "%SAUDE%" 2>nul
if not errorlevel 1 (
  echo O backend ja estava rodando na porta 8000.
  goto painel
)
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto porta_ocupada

echo Conferindo o backend...
cd /d "%~dp0backend"
uv run python -c "import picozero.api"
if errorlevel 1 goto backend_quebrado
cd /d "%~dp0"

echo Subindo o backend em http://127.0.0.1:8000 ...
start "PicoZero backend - feche para parar" /D "%~dp0backend" cmd /k uv run uvicorn picozero.api:app --host 127.0.0.1 --port 8000

rem ---------- painel
:painel
echo Subindo o painel em http://localhost:5173 ...
start "PicoZero painel - feche para parar" /D "%~dp0frontend" cmd /k npm run dev

rem Na primeira vez o backend monta o banco antes de responder; espera ate 2 minutos.
echo Esperando o backend responder...
set /a ESPERA=0
:esperar
curl -s -f -o nul "%SAUDE%" 2>nul
if not errorlevel 1 goto pronto
set /a ESPERA+=1
if %ESPERA% geq 120 goto sem_resposta
timeout /t 1 /nobreak >nul
goto esperar

:pronto
start "" http://localhost:5173
echo.
echo ===== PicoZero rodando =====
echo   Painel:        http://localhost:5173
echo   API e docs:    http://127.0.0.1:8000/docs
echo.
echo Para parar, feche as janelas "PicoZero backend" e "PicoZero painel".
echo.
pause
exit /b 0

:sem_resposta
echo.
echo ===== O backend nao respondeu em 2 minutos =====
echo Olhe a janela "PicoZero backend": a mensagem de erro aparece la.
echo O painel vai abrir mesmo assim, com os dados de previa.
start "" http://localhost:5173
echo.
pause
exit /b 1

:porta_ocupada
echo.
echo ===== A porta 8000 esta ocupada por outro programa =====
echo O backend do PicoZero precisa dela. Feche o programa que usa a porta 8000
echo ou reinicie o computador, e rode este arquivo de novo.
echo.
pause
exit /b 1

:backend_quebrado
echo.
echo ===== O backend nao carregou =====
echo A mensagem de erro esta logo acima. Tente rodar instalar-windows.bat de novo;
echo se continuar, mande um print desta janela.
echo.
pause
exit /b 1
