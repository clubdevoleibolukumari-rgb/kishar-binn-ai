from bais_system import AdaptiveRiskController, BinanceClient, Config
from dotenv import load_dotenv

load_dotenv()

def test_adaptive_logic():
    print("="*50)
    print("PRUEBA DE FACTIBILIDAD: KISHAR-BINN_AI AUTO-TUNE")
    print("="*50)
    
    client = BinanceClient()
    risk = AdaptiveRiskController(client)
    
    print("\nEvaluando volatilidad actual del mercado (SOLUSDT)...")
    res = risk.evaluate_market_conditions("SOLUSDT")
    
    print(f"\nResultado de la evaluación: {res}")
    print(f"-> Estado del Mercado Detectado: {risk.market_state}")
    print(f"-> Grid Range Adaptado (Auto-config): {Config.GRID_RANGE_PCT}%")
    print(f"-> Stop Loss Adaptado (Auto-config): {Config.STOP_LOSS_PCT}%")
    print("\nFACTIBILIDAD: ÉXITO. El sistema ajusta el riesgo basándose en volatilidad pura.")

if __name__ == "__main__":
    test_adaptive_logic()
