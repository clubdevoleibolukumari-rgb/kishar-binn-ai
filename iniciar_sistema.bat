@echo off
title BAIS - Sistema Autonomo de Ingresos
color 0E

echo ============================================================
echo      BAIS: BINANCE AUTONOMOUS INCOME SYSTEM v1.0
echo             Core: ALbert-Orquestador
echo ============================================================
echo.

echo [1/3] Verificando dependencias...
pip install -r requirements.txt fastapi uvicorn Jinja2 python-dotenv

echo.
echo [2/3] Iniciando Dashboard Web (Puerto 8000)...
start /B python dashboard.py

echo.
echo [3/3] Lanzando Bot de Trading Autonomo...
echo.
echo ************************************************************
echo ATENCION: Asegurate de haber configurado tu API Key en .env
echo El bot se ejecutara en segundo plano y enviara datos al
echo dashboard cada hora.
echo ************************************************************
echo.

python bais_system.py

pause
