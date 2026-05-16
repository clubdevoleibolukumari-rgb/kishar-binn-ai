import threading
import uvicorn
import os
from bais_system import BAISSystem
from dashboard import app
import logging

# Configurar logging para la nube
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainCloud")

def run_trading_bot():
    """Inicia el motor de trading en un hilo separado"""
    logger.info("Iniciando motor de trading BAIS...")
    try:
        system = BAISSystem()
        system.start()
    except Exception as e:
        logger.error(f"Error mortal en el motor de trading: {e}")

if __name__ == "__main__":
    # 1. Iniciar el bot en segundo plano
    bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
    bot_thread.start()
    
    # 2. Iniciar el servidor web del Dashboard
    # Usamos el puerto que asigne la plataforma cloud (PORT) o 8000 por defecto
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Dashboard iniciando en el puerto {port}...")
    
    # Ejecutar uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
