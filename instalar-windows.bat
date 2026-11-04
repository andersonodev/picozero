@echo off
rem instalar-windows.bat - instala tudo que o PicoZero precisa no Windows 10/11.
rem Baixa o uv (que traz o Python 3.12), o Node.js LTS se faltar, e as dependencias do backend e do frontend.
setlocal
title PicoZero - instalacao
cd /d "%~dp0"

rem A janela atual nao enxerga o PATH novo depois de instalar; estes sao os lugares padrao do uv e do Node.
set "PATH=%USERPROFILE%\.local\bin;%ProgramFiles%\nodejs;%PATH%"

echo.
echo ===== PicoZero: instalacao =====
echo.

rem ---------- 1/4 uv: gerencia o Python 3.12 e as dependencias do backend
where uv >nul 2>nul
if not errorlevel 1 goto uv_pronto
echo [1/4] Baixando o uv...
powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
where uv >nul 2>nul
if not errorlevel 1 goto uv_pronto
echo.
echo Nao consegui instalar o uv. Instale por https://docs.astral.sh/uv/ e rode este arquivo de novo.
goto erro
:uv_pronto
rem Um uv antigo nao le o uv.lock deste projeto; atualiza quando foi instalado pelo instalador oficial.
uv self update >nul 2>nul
echo [1/4] uv pronto.

rem ---------- 2/4 Node.js 20.19+ ou 22.12+: roda o frontend
call :node_serve
if not errorlevel 1 goto node_pronto
echo [2/4] Baixando o Node.js LTS pelo winget...
where winget >nul 2>nul
if errorlevel 1 goto node_manual
winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
call :node_serve
if not errorlevel 1 goto node_pronto
:node_manual
echo.
echo Preciso do Node.js 22 LTS. Baixe em https://nodejs.org, instale e rode este arquivo de novo.
goto erro
:node_pronto
echo [2/4] Node.js pronto.

rem ---------- 3/4 backend
echo [3/4] Instalando o backend: Python 3.12 e dependencias...
cd /d "%~dp0backend"
rem Um .venv que veio de outro computador (Mac/Linux) nao serve no Windows: apaga e recria.
if exist ".venv" if not exist ".venv\Scripts\python.exe" rmdir /s /q ".venv"
uv sync
if errorlevel 1 goto erro
if exist ".env" goto env_pronto
echo.
echo Chave do Vertex AI: opcional. Sem ela a IA responde por regras.
echo Crie em https://console.cloud.google.com/apis/credentials
set "CHAVE="
set /p "CHAVE=Cole a VERTEX_API_KEY e aperte Enter, ou so Enter para pular: "
if not defined CHAVE goto env_sem_chave
> ".env" echo VERTEX_API_KEY=%CHAVE%
findstr /v /b "VERTEX_API_KEY=" ".env.example" >> ".env"
goto env_pronto
:env_sem_chave
copy /y ".env.example" ".env" >nul
:env_pronto
echo [3/4] Backend pronto. Configuracao em backend\.env

rem ---------- 4/4 frontend (npm e um .cmd: sem "call" este script terminaria aqui)
echo [4/4] Instalando o frontend...
cd /d "%~dp0frontend"
call npm ci
if errorlevel 1 goto erro
rem Marca que o node_modules foi instalado neste Windows (o rodar-windows.bat confere).
type nul > "node_modules\.instalado-windows"
echo [4/4] Frontend pronto.

echo.
echo ===== Tudo instalado. Para abrir o PicoZero, de dois cliques em rodar-windows.bat =====
echo.
if /i not "%~1"=="/sem-pausa" pause
exit /b 0

:erro
echo.
echo ===== A instalacao parou com erro. Veja a mensagem acima. =====
echo.
pause
exit /b 1

rem Sai com 0 se houver um Node que o Vite 8 aceita.
:node_serve
where node >nul 2>nul || exit /b 1
node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a>22||(a===22&&b>=12)||(a===20&&b>=19)?0:1)"
exit /b %errorlevel%
