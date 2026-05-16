@echo off
title KISHAR-BINN AI - Orquestador Maestro
color 0B

echo ============================================================
echo      KISHAR-BINN AI: SISTEMA CUANTITATIVO INSTITUCIONAL
echo             Core: Albert-Orquestador v2.0
echo ============================================================
echo.

echo [1/3] Verificando e Instalando Dependencias (Por favor espera)...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Hubo un problema instalando las dependencias. Revisa tu conexion a internet.
    pause
    exit /b
)
echo [OK] Dependencias al dia.
echo.

echo [2/3] Iniciando el Servidor del Dashboard Local...
:: Matar procesos anteriores en el puerto 8000 si existieran para evitar errores de Address In Use
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000" ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

:: Iniciar FastAPI usando Uvicorn en segundo plano
start "KISHAR_DASHBOARD" cmd /c "uvicorn dashboard:app --host 0.0.0.0 --port 8000"

:: Esperar 4 segundos para asegurar que el servidor web este arriba
timeout /t 4 /nobreak > nul

:: Abrir el navegador por defecto apuntando al dashboard local
start http://localhost:8000

echo.
echo [3/3] Iniciando el Bot de Trading Autonomo...
echo ============================================================
echo ATENCION: El bot comenzara a operar e interactuar con Binance.
echo Puedes minimizar esta ventana pero NO LA CIERRES.
echo Todo el estado se vera reflejado en http://localhost:8000
echo ============================================================
echo.

python bais_system.py

pause
