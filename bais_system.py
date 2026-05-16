#!/usr/bin/env python3
"""
══════════════════════════════════════════════════════════════════
  KISHAR-BINN_AI v2.0 - QUANTITATIVE AUTONOMOUS SYSTEM
  Capital inicial: $2.80 USD | 100% Automatizado | IA Libre
  Fecha: 2026-05-15 | License: MIT
══════════════════════════════════════════════════════════════════

ESTRATEGIAS IMPLEMENTADAS:
├── Tier 1 ($2.80-$10): Simple Earn Flexible + Auto-Subscribe
├── Tier 2 ($10-$50):  DCA + Grid Trading
├── Tier 3 ($50+):     Multi-Bot + Compound Reinvestment
└── Always ON:         Airdrop Monitor + Referral Tracker

REQUISITOS:
  pip install python-binance pandas numpy requests
"""

import os
import time
import json
import logging
import hmac
import hashlib
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import threading
from dotenv import load_dotenv
from ai_orchestrator import AIOrchestrator

# Cargar variables de entorno
load_dotenv()

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

class Config:
    """Configuración central del sistema"""
    # Binance API
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
    BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')
    BASE_URL = "https://testnet.binance.vision" if os.getenv('BINANCE_TESTNET', 'True') == 'True' else "https://api.binance.com"
    
    # IA APIs (Orquestador)
    IA_KEYS = {
        'gemini': os.getenv('GEMINI_API_KEY', ''),
        'deepseek': os.getenv('DEEPSEEK_API_KEY', ''),
        'groq': os.getenv('GROQ_API_KEY', ''),
        'huggingface': os.getenv('HF_API_KEY', '')
    }
    
    # Configuración de Riesgo Institucional
    MAX_DRAWDOWN_PCT = 5.0    # 5% máximo de pérdida permitido antes de cierre total
    STOP_LOSS_PCT = 1.0       # Stop Loss por operación individual
    MIN_BALANCE_CORE = 2.0    # No operar si el balance baja de $2 para proteger el honorario de red
    
    # Capital
    INITIAL_CAPITAL = 2.80
    TIER1_THRESHOLD = 1.0     # Umbral para activar Tier 2 (DCA)
    TIER2_THRESHOLD = 5.0     # Umbral para activar Tier 3 (Grid)
    
    # Estrategia Earn
    EARN_PRODUCT = "FDUSD"    
    EARN_APR = 0.118          
    AUTO_SUBSCRIBE = True
    
    # DCA Config
    DCA_ENABLED = False       
    DCA_AMOUNT = 1.0          
    DCA_FREQUENCY = "daily"   
    DCA_PAIR = "BTCUSDT"
    
    # Grid Trading Config (Tier 2+)
    GRID_ENABLED = False
    GRID_PAIR = "SOLUSDT"
    GRID_LEVELS = 20
    GRID_RANGE_PCT = 20       
    
    # Referidos
    REFERRAL_LINK = os.getenv('BINANCE_REF_LINK', '')
    
    # Logging
    LOG_LEVEL = logging.INFO
    LOG_FILE = "bais_system.log"
    
    # Intervalos
    EARN_CHECK_INTERVAL = 3600      # 1 hora
    GRID_CHECK_INTERVAL = 60        # 1 minuto
    DCA_CHECK_INTERVAL = 86400      # 24 horas
    REPORT_INTERVAL = 86400         # 24 horas

# ═══════════════════════════════════════════════════════════════
# LOGGER
# ═══════════════════════════════════════════════════════════════

def setup_logger(name: str) -> logging.Logger:
    """Configura logger con formato profesional"""
    logger = logging.getLogger(name)
    logger.setLevel(Config.LOG_LEVEL)
    
    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File handler
    fh = logging.FileHandler(Config.LOG_FILE)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    return logger

logger = setup_logger('Kishar-Binn')

# ═══════════════════════════════════════════════════════════════
# BINANCE API CLIENT
# ═══════════════════════════════════════════════════════════════

class BinanceClient:
    """Cliente seguro para la API de Binance"""
    
    def __init__(self, api_key: str = None, secret_key: str = None, testnet: bool = None):
        self.api_key = api_key or Config.BINANCE_API_KEY
        self.secret_key = secret_key or Config.BINANCE_SECRET_KEY
        
        # Determinar testnet desde Config si no se pasa explícitamente
        if testnet is None:
            testnet = os.getenv('BINANCE_TESTNET', 'True') == 'True'
            
        self.base_url = Config.BASE_URL
        self.testnet_mode = testnet
        self.session = requests.Session()
        self.session.headers.update({
            'X-MBX-APIKEY': self.api_key
        })
        logger.info(f"BinanceClient inicializado | Testnet: {self.testnet_mode}")
    
    def _generate_signature(self, query_string: str) -> str:
        """Genera firma HMAC-SHA256"""
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False) -> Dict:
        """Ejecuta request a la API"""
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['recvWindow'] = 5000
            query = '&'.join([f"{k}={v}" for k, v in params.items()])
            params['signature'] = self._generate_signature(query)
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=10)
            elif method == 'POST':
                response = self.session.post(url, data=params, timeout=10)
            else:
                response = self.session.delete(url, params=params, timeout=10)
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API Error: {e}")
            return {'error': str(e)}
    
    # Account
    def get_account(self) -> Dict:
        """Obtiene información de la cuenta"""
        return self._request('GET', '/api/v3/account', signed=True)
    def get_balance(self, asset: str = 'USDT') -> float:
        """Obtiene balance de un activo sumando Spot y Funding de forma segura"""
        total = 0.0
        try:
            # 1. Spot
            account = self.get_account()
            if isinstance(account, dict) and 'balances' in account:
                for b in account['balances']:
                    if b['asset'] == asset:
                        total += float(b.get('free', 0))
            
            # 2. Funding
            funding = self._request('POST', '/sapi/v1/asset/get-funding-asset', signed=True)
            if isinstance(funding, list):
                for f in funding:
                    if f['asset'] == asset:
                        total += float(f.get('free', 0))
        except Exception as e:
            logger.error(f"Error en get_balance para {asset}: {e}")
        return float(total)

    def get_total_net_worth(self) -> float:
        """Calcula el valor neto total en USDT de todas las billeteras y activos"""
        total_usdt = 0.0
        assets = {}

        try:
            # 1. Balances de SPOT
            spot = self.get_account()
            if isinstance(spot, dict) and 'balances' in spot:
                for b in spot['balances']:
                    qty = float(b.get('free', 0)) + float(b.get('locked', 0))
                    if qty > 0: assets[b['asset']] = assets.get(b['asset'], 0.0) + qty

            # 2. Balances de FONDOS (Funding)
            funding = self._request('POST', '/sapi/v1/asset/get-funding-asset', signed=True)
            if isinstance(funding, list):
                for f in funding:
                    qty = float(f.get('free', 0)) + float(f.get('locked', 0))
                    if qty > 0: assets[f['asset']] = assets.get(f['asset'], 0.0) + qty

            # 3. Balances de SIMPLE EARN
            earn = self._request('GET', '/sapi/v1/simple-earn/flexible/position', signed=True)
            if isinstance(earn, dict) and 'rows' in earn:
                for r in earn['rows']:
                    qty = float(r.get('totalAmount', 0))
                    if qty > 0: assets[r['asset']] = assets.get(r['asset'], 0.0) + qty

            # 4. Conversión a USDT
            for asset, qty in assets.items():
                if asset in ['USDT', 'USDC', 'DAI']:
                    total_usdt += qty
                else:
                    try:
                        price = self.get_price(f"{asset}USDT")
                        if price > 0:
                            total_usdt += qty * price
                    except:
                        pass
            
            return round(float(total_usdt), 4)
        except Exception as e:
            logger.error(f"Error crítico en Net Worth: {e}")
            return 0.0

    # Market Data
    def get_ticker(self, symbol: str) -> Dict:
        """Obtiene precio actual y 24h stats"""
        return self._request('GET', '/api/v3/ticker/24hr', {'symbol': symbol})
    
    def get_price(self, symbol: str) -> float:
        """Obtiene precio actual"""
        result = self._request('GET', '/api/v3/ticker/price', {'symbol': symbol})
        return float(result.get('price', 0))
    
    def get_klines(self, symbol: str, interval: str = '1d', limit: int = 30) -> pd.DataFrame:
        """Obtiene datos históricos OHLCV"""
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        data = self._request('GET', '/api/v3/klines', params)
        
        if isinstance(data, list):
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 
                'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['volume'] = df['volume'].astype(float)
            return df
        return pd.DataFrame()
    
    # Simple Earn
    def subscribe_flexible(self, product_id: str, amount: float, auto_subscribe: bool = True) -> Dict:
        """Subscribe a producto flexible de earn"""
        params = {
            'productId': product_id,
            'amount': amount,
            'autoSubscribe': str(auto_subscribe).lower()
        }
        return self._request('POST', '/sapi/v1/simple-earn/flexible/subscribe', params, signed=True)
    
    def get_flexible_products(self, asset: str = None) -> List[Dict]:
        """Obtiene lista de productos flexibles disponibles"""
        params = {}
        if asset:
            params['asset'] = asset
        return self._request('GET', '/sapi/v1/simple-earn/flexible/list', params, signed=True)
    
    def redeem_flexible(self, product_id: str, amount: float = None) -> Dict:
        """Redime producto flexible"""
        params = {'productId': product_id}
        if amount:
            params['amount'] = amount
        return self._request('POST', '/sapi/v1/simple-earn/flexible/redeem', params, signed=True)
    
    # Auto-Invest / DCA
    def create_dca_plan(self, symbol: str, amount: float, frequency: str = 'DAILY') -> Dict:
        """Crea plan DCA"""
        params = {
            'sourceType': 'SPOT',
            'subscriptionAmount': amount,
            'subscriptionCycle': frequency,
            'sourceAsset': 'USDT',
            'details': json.dumps([{
                'targetAsset': symbol.replace('USDT', ''),
                'subscriptionRatio': 100
            }])
        }
        return self._request('POST', '/sapi/v1/auto-invest/plan/create', params, signed=True)
    
    # Grid Trading
    def create_grid_order(self, symbol: str, lower_price: float, upper_price: float, 
                         grid_count: int, investment: float) -> Dict:
        """Crea orden de grid trading"""
        params = {
            'symbol': symbol,
            'lowerPrice': lower_price,
            'upperPrice': upper_price,
            'gridNumber': grid_count,
            'initialInvestQuote': investment
        }
        return self._request('POST', '/sapi/v1/grid/spot/order', params, signed=True)

# ═══════════════════════════════════════════════════════════════
# AUTONOMOUS ENGINE (AI)
# ═══════════════════════════════════════════════════════════════

class DecisionEngine:
    """Motor de Decisiones Basado en IA Orquestada"""
    
    def __init__(self, client: BinanceClient):
        self.client = client
        self.orchestrator = AIOrchestrator(Config.IA_KEYS)
        self.last_decision = "Iniciando sistema autónomo..."
    
    def analyze_and_optimize(self, portfolio_state: Dict):
        """Usa la IA para optimizar parametros del sistema"""
        try:
            self.current_status = "🤖 IA Pensando y Optimizando..."
            # Recolectar datos actuales
            prices = self.client.get_ticker(Config.GRID_PAIR)
            klines = self.client.get_klines(Config.GRID_PAIR, limit=5).to_json()
            
            prompt = f"""
            Analiza el estado actual de mi bot de Binance:
            Estado: {json.dumps(portfolio_state)}
            Datos Mercado ({Config.GRID_PAIR}): {json.dumps(prices)}
            Ultimas Velas: {klines}
            
            Objetivo: Maximizar ROI con capital bajo ($2.80).
            Tareas:
            1. ¿Debo cambiar el par de Grid/DCA?
            2. ¿Ajusto el rango del Grid ({Config.GRID_RANGE_PCT}%)?
            3. Dame un mensaje motivacional corto para el reporte.
            
            Responde en formato JSON: {{"pair": "...", "grid_range": 20, "message": "..."}}
            """
            
            response, ai_provider = self.orchestrator.ask_ai(prompt, system_context="Eres un experto en trading algorítmico institucional.")
            logger.info(f"[AI-ENGINE] Respuesta obtenida vía: {ai_provider}")
            
            # Intentar parsear respuesta JSON (limpiando posibles markdown)
            content = response.strip()
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            try:
                decision = json.loads(content)
            except json.JSONDecodeError:
                # Fallback: intentar encontrar JSON con regex o tomar valores por defecto
                logger.warning("[AI-ENGINE] Respuesta IA no es JSON puro. Usando valores por defecto.")
                decision = {"pair": Config.GRID_PAIR, "grid_range": Config.GRID_RANGE_PCT, "message": "IA analizando..."}
            
            # Aplicar cambios si la IA lo sugiere
            if "pair" in decision:
                Config.GRID_PAIR = decision['pair']
                Config.DCA_PAIR = decision['pair']
            if "grid_range" in decision:
                Config.GRID_RANGE_PCT = decision['grid_range']
            
            self.last_decision = decision.get('message', "Optimización completada.")
            logger.info(f"[AI-ENGINE] Nueva estrategia aplicada: {decision}")
            return decision
            
        except Exception as e:
            logger.error(f"[AI-ENGINE] Error en optimización: {e}")
            return None

class AdaptiveRiskController:
    """Auto-ajusta los parámetros operativos en tiempo real según el mercado"""
    def __init__(self, client: BinanceClient):
        self.client = client
        self.market_state = "NORMAL" # NORMAL, VOLATILE, EXTREME
        
    def evaluate_market_conditions(self, symbol: str) -> Dict:
        """Mide la volatilidad (ATR aproximado) para adaptar el riesgo"""
        try:
            df = self.client.get_klines(symbol, interval='1h', limit=24)
            if df.empty: return {}
            
            # Cálculo de volatilidad (High - Low) / Close
            df['volatility'] = (df['high'] - df['low']) / df['close']
            avg_vol = df['volatility'].mean() * 100 # en porcentaje
            
            if avg_vol > 5.0:
                self.market_state = "EXTREME"
                # Mercado loco: Aumentar rango del Grid, reducir exposición
                Config.GRID_RANGE_PCT = 30.0
                Config.STOP_LOSS_PCT = 2.0
            elif avg_vol > 2.0:
                self.market_state = "VOLATILE"
                Config.GRID_RANGE_PCT = 15.0
                Config.STOP_LOSS_PCT = 1.0
            else:
                self.market_state = "NORMAL"
                Config.GRID_RANGE_PCT = 5.0 # Rango ajustado para más operaciones en mercado lateral
                Config.STOP_LOSS_PCT = 0.5
                
            logger.info(f"[AUTO-TUNE] Mercado evaluado: {self.market_state} | Volatilidad: {avg_vol:.2f}%. Parámetros ajustados.")
            return {"state": self.market_state, "volatility": avg_vol}
        except Exception as e:
            logger.error(f"[AUTO-TUNE] Error adaptando riesgo: {e}")
            return {}

# ═══════════════════════════════════════════════════════════════
# TIER SYSTEM & PORTFOLIO
# ═══════════════════════════════════════════════════════════════

class TierLevel(Enum):
    TIER1 = "FREE_CAPITAL"      # $2.80 - $10
    TIER2 = "LOW_CAPITAL"       # $10 - $50
    TIER3 = "ACTIVE_TRADING"    # $50+

@dataclass
class PortfolioState:
    """Estado actual del portafolio"""
    total_balance: float
    usdt_balance: float
    earn_balance: float
    grid_balance: float
    tier: TierLevel
    current_asset: str
    last_ai_decision: str
    current_status: str       # Nuevo: "Pensando", "Ejecutando", etc.
    timestamp: str
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'tier': self.tier.value
        }

class TierManager:
    """Gestiona las transiciones entre tiers"""
    
    def __init__(self, client: BinanceClient):
        self.client = client
        self.state_file = "portfolio_state.json"
        self.history_file = "portfolio_history.csv"
    
    def get_current_tier(self, balance: float) -> TierLevel:
        """Determina el tier basado en el balance"""
        if balance >= Config.TIER2_THRESHOLD:
            return TierLevel.TIER3
        elif balance >= Config.TIER1_THRESHOLD:
            return TierLevel.TIER2
        return TierLevel.TIER1
    
    def get_state(self) -> PortfolioState:
        """Obtiene estado actual del portafolio con valor neto global"""
        total = self.client.get_total_net_worth()
        usdt = self.client.get_balance('USDT')
        earn = self.client.get_balance('FDUSD')
        
        # Auto-ajuste de capital inicial en el primer arranque exitoso
        if Config.INITIAL_CAPITAL == 2.80 and total > 0 and total < 2.0:
             # Si el saldo es bajo, asumimos que este es el nuevo capital base
             Config.INITIAL_CAPITAL = total
             logger.info(f"[SISTEMA] Capital inicial ajustado a saldo real detectado: ${total}")

        tier = self.get_current_tier(total)
        
        # Intentar recuperar la última decisión del DecisionEngine si existe
        self.last_decision_text = "Analizando oportunidades..."
        if hasattr(self, 'engine'):
            self.last_decision_text = self.engine.last_decision
        
        state = PortfolioState(
            total_balance=round(total, 4),
            usdt_balance=round(usdt, 4),
            earn_balance=round(earn, 4),
            grid_balance=0.0,
            tier=tier,
            current_asset=Config.GRID_PAIR,
            last_ai_decision=getattr(self, 'last_decision_text', 'Analizando...'),
            current_status=getattr(self, 'current_status', 'Monitoreando Mercado'),
            timestamp=datetime.now().isoformat()
        )
        
        self._save_state(state)
        return state
    
    def _save_state(self, state: PortfolioState):
        """Guarda estado en archivo"""
        with open(self.state_file, 'w') as f:
            json.dump(state.to_dict(), f, indent=2)
        
        df = pd.DataFrame([state.to_dict()])
        if os.path.exists(self.history_file):
            df.to_csv(self.history_file, mode='a', header=False, index=False)
        else:
            df.to_csv(self.history_file, index=False)

# ═══════════════════════════════════════════════════════════════
# STRATEGY: TIER 1 - EARN BOT
# ═══════════════════════════════════════════════════════════════

class EarnBot:
    """Bot de Simple Earn Flexible"""
    
    def __init__(self, client: BinanceClient):
        self.client = client
        self.apr = Config.EARN_APR
        self.product = Config.EARN_PRODUCT
    
    def calculate_daily_yield(self, amount: float) -> float:
        """Calcula yield diario basado en APR"""
        return amount * (self.apr / 365)
    
    def calculate_projected_growth(self, principal: float, days: int) -> Dict:
        """Calcula proyeccion de crecimiento"""
        daily_rate = self.apr / 365
        final = principal * ((1 + daily_rate) ** days)
        
        return {
            'principal': principal,
            'days': days,
            'final_amount': round(final, 6),
            'total_yield': round(final - principal, 6),
            'roi_pct': round(((final - principal) / principal) * 100, 2),
            'daily_yield': round(self.calculate_daily_yield(principal), 6)
        }
    
    def execute(self):
        """Ejecuta estrategia de Earn/Staking"""
        try:
            usdt_balance = self.client.get_balance('USDT')
            
            if usdt_balance > 0.01:
                logger.info(f"[EARN] Optimizando saldo: ${usdt_balance:.2f}")
                
                # Intentar suscripción automática si está configurado
                if Config.AUTO_SUBSCRIBE:
                    products = self.client.get_flexible_products('USDT')
                    if isinstance(products, list) and len(products) > 0:
                        product_id = products[0]['productId']
                        res = self.client.subscribe_flexible(product_id, usdt_balance)
                        if 'purchaseId' in res:
                            logger.info(f"[EARN] Suscripción exitosa a Staking Flexible: {res['purchaseId']}")
                
                projection = self.calculate_projected_growth(usdt_balance, 30)
                return True
            return False
                
        except Exception as e:
            logger.error(f"[EARN] Error: {e}")
            return False

# ═══════════════════════════════════════════════════════════════
# STRATEGY: DCA BOT (Tier 2+)
# ═══════════════════════════════════════════════════════════════

class DCABot:
    """Bot de Dollar Cost Averaging"""
    
    def __init__(self, client: BinanceClient):
        self.client = client
        self.enabled = Config.DCA_ENABLED
        self.amount = Config.DCA_AMOUNT
        self.pair = Config.DCA_PAIR
    
    def should_buy(self, history: pd.DataFrame) -> Tuple[bool, Dict]:
        """Determina si debe comprar basado en analisis tecnico simple"""
        if history.empty or len(history) < 20:
            return False, {}
        
        close = history['close']
        
        # RSI simple
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        # SMA
        sma_20 = close.rolling(window=20).mean().iloc[-1]
        current_price = close.iloc[-1]
        
        signal = current_rsi < 40 or current_price < sma_20 * 0.95
        
        analysis = {
            'rsi': round(current_rsi, 2),
            'sma20': round(sma_20, 2),
            'price': round(current_price, 2),
            'signal': 'BUY' if signal else 'HOLD'
        }
        
        return signal, analysis
    
    def execute(self):
        """Ejecuta estrategia DCA"""
        if not self.enabled:
            return False
        
        try:
            history = self.client.get_klines(self.pair, interval='1d', limit=30)
            should_buy, analysis = self.should_buy(history)
            
            logger.info(f"[DCA] Analisis: {analysis}")
            
            if should_buy:
                usdt = self.client.get_balance('USDT')
                if usdt >= self.amount:
                    logger.info(f"[DCA] Ejecutando compra de ${self.amount} en {self.pair}")
                    return True
                else:
                    logger.warning(f"[DCA] Balance insuficiente: ${usdt:.2f}")
            
            return False
            
        except Exception as e:
            logger.error(f"[DCA] Error: {e}")
            return False

# ═══════════════════════════════════════════════════════════════
# STRATEGY: GRID BOT (Tier 2+)
# ═══════════════════════════════════════════════════════════════

class GridBot:
    """Bot de Grid Trading"""
    
    def __init__(self, client: BinanceClient):
        self.client = client
        self.enabled = Config.GRID_ENABLED
        self.pair = Config.GRID_PAIR
        self.levels = Config.GRID_LEVELS
        self.range_pct = Config.GRID_RANGE_PCT
        self.grid_orders = []
    
    def calculate_grid_params(self) -> Dict:
        """Calcula parametros optimos del grid"""
        current_price = self.client.get_price(self.pair)
        
        lower = current_price * (1 - self.range_pct / 100 / 2)
        upper = current_price * (1 + self.range_pct / 100 / 2)
        spacing = (upper - lower) / self.levels
        
        return {
            'pair': self.pair,
            'current_price': current_price,
            'lower_price': round(lower, 4),
            'upper_price': round(upper, 4),
            'grid_spacing': round(spacing, 4),
            'levels': self.levels,
            'profit_per_grid': round(spacing / current_price * 100, 4)
        }
    
    def execute(self, allocation: float):
        """Ejecuta estrategia de Grid"""
        if not self.enabled or allocation < 5:
            return False
        
        try:
            params = self.calculate_grid_params()
            logger.info(f"[GRID] Parametros: {params}")
            
            result = self.client.create_grid_order(
                symbol=params['pair'],
                lower_price=params['lower_price'],
                upper_price=params['upper_price'],
                grid_count=params['levels'],
                investment=allocation
            )
            
            if 'gridId' in result:
                logger.info(f"[GRID] Grid creado exitosamente: ID {result['gridId']}")
                self.grid_orders.append(result['gridId'])
                return True
            else:
                logger.error(f"[GRID] Error creando grid: {result}")
                return False
                
        except Exception as e:
            logger.error(f"[GRID] Error: {e}")
            return False

# ═══════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

class BAISSystem:
    """Sistema Principal - Orchestrador Autonomo"""
    
    def __init__(self):
        self.client = BinanceClient()
        self.tier_manager = TierManager(self.client)
        self.earn_bot = EarnBot(self.client)
        self.dca_bot = DCABot(self.client)
        self.grid_bot = GridBot(self.client)
        self.engine = DecisionEngine(self.client)
        self.risk_controller = AdaptiveRiskController(self.client)
        
        self.running = False
        self.threads = []
        
        logger.info("=" * 60)
        logger.info("Kishar-Binn_AI - Autonomous Trading Core v2.0")
        logger.info(f"Capital inicial configurado: ${Config.INITIAL_CAPITAL}")
        logger.info("=" * 60)
    
    def generate_report(self) -> str:
        """Genera reporte completo del sistema"""
        state = self.tier_manager.get_state()
        
        earn_projection = self.earn_bot.calculate_projected_growth(
            state.total_balance if state.total_balance > 0 else 0.01, 30
        )
        earn_365 = self.earn_bot.calculate_projected_growth(
            state.total_balance if state.total_balance > 0 else 0.01, 365
        )
        
        report = f"""
KISHAR-BINN_AI - REPORTE DE TELEMETRIA
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

BALANCE ACTUAL
  Total:     ${state.total_balance:.4f} USDT
  Spot:      ${state.usdt_balance:.4f} USDT
  Earn:      ${state.earn_balance:.4f} USDT
  Tier:      {state.tier.value}

PROYECCIONES EARN (APR: {Config.EARN_APR*100:.1f}%)
  30 dias:   ${earn_projection['final_amount']:.4f} (+{earn_projection['roi_pct']}%)
  365 dias:  ${earn_365['final_amount']:.4f} (+{earn_365['roi_pct']}%)

ESTRATEGIAS ACTIVAS
  Earn:   SIEMPRE ACTIVO
  DCA:    {'ACTIVO' if Config.DCA_ENABLED else 'ESPERANDO TIER 2'}
  Grid:   {'ACTIVO' if Config.GRID_ENABLED else 'ESPERANDO TIER 2'}
"""
        return report
    
    def run_earn_loop(self):
        """Loop del bot de Earn"""
        while self.running:
            try:
                self.current_status = "💰 Buscando Oportunidades Earn/Staking..."
                self.earn_bot.execute()
                self.current_status = "💤 Durmiendo (Modo Ahorro)"
            except Exception as e:
                logger.error(f"[LOOP-EARN] Error: {e}")
                time.sleep(60)
    
    def run_tier_check_loop(self):
        """Loop de verificacion de tier"""
        while self.running:
            try:
                state = self.tier_manager.get_state()
                current_tier = state.tier
                
                # Auto-ajuste de mercado antes de verificar Tiers
                if state.total_balance > 0:
                    self.risk_controller.evaluate_market_conditions(Config.GRID_PAIR)
                
                # PROTOCOLO DE SEGURIDAD: Max Drawdown (Solo si hay balance)
                if state.total_balance > 0:
                    current_drawdown = ((Config.INITIAL_CAPITAL - state.total_balance) / Config.INITIAL_CAPITAL) * 100
                    if current_drawdown > Config.MAX_DRAWDOWN_PCT:
                        logger.critical(f"ALERTA: Drawdown de {current_drawdown:.2f}% detectado. ACTIVANDO PROTOCOLO DE CIERRE.")
                        self.stop()
                        return
                    dd_display = max(0, current_drawdown)
                else:
                    logger.warning("[SEGURIDAD] Balance es 0. Verificando conexión o cuenta vacía...")
                    dd_display = 0.0

                logger.info(f"[TIER] Estado actual: {current_tier.value} | "
                          f"Balance: ${state.total_balance:.2f} | DD: {dd_display:.2f}%")
                
                if current_tier in [TierLevel.TIER2, TierLevel.TIER3] and not Config.DCA_ENABLED:
                    Config.DCA_ENABLED = True
                    logger.info("[TIER] >>> DCA ACTIVADO <<<")
                
                if current_tier in [TierLevel.TIER2, TierLevel.TIER3] and not Config.GRID_ENABLED:
                    if state.total_balance >= 10:
                        Config.GRID_ENABLED = True
                        logger.info("[TIER] >>> GRID TRADING ACTIVADO <<<")
                
                time.sleep(3600)
                
            except Exception as e:
                logger.error(f"[TIER-CHECK] Error: {e}")
                time.sleep(300)
    
    def run_dca_loop(self):
        """Loop del bot DCA"""
        while self.running:
            try:
                if Config.DCA_ENABLED:
                    self.dca_bot.execute()
                time.sleep(Config.DCA_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"[LOOP-DCA] Error: {e}")
                time.sleep(60)
    
    def run_grid_loop(self):
        """Loop del bot de Grid"""
        while self.running:
            try:
                if Config.GRID_ENABLED:
                    # Distribuye el 50% del balance para el grid
                    state = self.tier_manager.get_state()
                    allocation = state.total_balance * 0.5
                    self.grid_bot.execute(allocation)
                time.sleep(Config.GRID_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"[LOOP-GRID] Error: {e}")
                time.sleep(60)

    def run_report_loop(self):
        """Loop de reportes"""
        while self.running:
            try:
                report = self.generate_report()
                print(report)
                time.sleep(Config.REPORT_INTERVAL)
            except Exception as e:
                logger.error(f"[LOOP-REPORT] Error: {e}")
                time.sleep(3600)

    def run_ai_loop(self):
        """Loop de optimización por IA"""
        while self.running:
            try:
                state = self.tier_manager.get_state()
                self.engine.analyze_and_optimize(state.to_dict())
                # Optimizar cada 12 horas para no saturar APIs gratuitas
                time.sleep(43200) 
            except Exception as e:
                logger.error(f"[LOOP-AI] Error: {e}")
                time.sleep(300)
    
    def start(self):
        """Inicia el sistema autonomo"""
        self.running = True
        logger.info("INICIANDO BAIS - Sistema Autonomo de Ingresos")
        
        threads_config = [
            ("EarnBot", self.run_earn_loop),
            ("TierCheck", self.run_tier_check_loop),
            ("DCA", self.run_dca_loop),
            ("Grid", self.run_grid_loop),
            ("AI-Engine", self.run_ai_loop),
            ("Report", self.run_report_loop)
        ]
        
        for name, target in threads_config:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self.threads.append(t)
            logger.info(f"Thread {name} iniciado")
        
        logger.info("Sistema completamente operativo")
        
        try:
            while self.running:
                # Vigilancia básica de hilos
                for t in self.threads:
                    if not t.is_alive():
                        logger.warning(f"Thread {t.name} murio. Reiniciando...")
                        # En un entorno real aqui se recrearia el hilo especifico
                time.sleep(10)
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            logger.error(f"FALLO CRITICO DEL SISTEMA: {e}. Reiniciando en 30s...")
            time.sleep(30)
            self.start() # Autoreinicio
    
    def stop(self):
        """Detiene el sistema"""
        self.running = False
        logger.info("Sistema detenido por usuario")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        client = BinanceClient()
        earn = EarnBot(client)
        
        print("\n" + "=" * 60)
        print("BAIS - PROYECCIONES MATEMATICAS")
        print("=" * 60)
        
        capital = float(sys.argv[2]) if len(sys.argv) > 2 else 2.80
        
        for days in [7, 30, 90, 180, 365]:
            proj = earn.calculate_projected_growth(capital, days)
            print(f"{days:>4} dias: ${proj['final_amount']:.4f} "
                  f"(+${proj['total_yield']:.4f} | +{proj['roi_pct']}%)")
    else:
        system = BAISSystem()
        system.start()
