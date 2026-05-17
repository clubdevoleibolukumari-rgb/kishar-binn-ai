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
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import threading
from dotenv import load_dotenv
from ai_orchestrator import AIOrchestrator
from multi_agent_engine import engine as ma_engine

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
    
    # Capital y Presupuesto
    INITIAL_CAPITAL = 10.0    # Capital objetivo inicial
    MAX_TRADING_BUDGET = 10.0 # Máximo capital a utilizar para trading activo
    TIER1_THRESHOLD = 5.0     # Umbral para activar Tier 2 (DCA)
    TIER2_THRESHOLD = 15.0    # Umbral para activar Tier 3 (Grid)
    
    # Estrategia Earn
    EARN_PRODUCT = "FDUSD"    
    EARN_APR = 0.118          
    AUTO_SUBSCRIBE = True
    
    # Smart Execution Config (Sustituye DCA/Grid)
    SMART_EXEC_ENABLED = True
    
    # Activos Optimizados para Micro-Cuentas ($10 USD)
    # Seleccionamos activos con alta volatilidad predecible y que permiten ordenes mínimas de $5 USDT
    ACTIVE_PAIRS = ["SOLUSDT", "DOGEUSDT", "XRPUSDT", "ADAUSDT", "BTCUSDT"]
    
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
    def get_futures_balance(self) -> float:
        """Obtiene el balance total de la billetera de futuros USDT-M"""
        try:
            # Endpoint para futuros: /fapi/v2/account
            fbase = 'https://fapi.binance.com'
            ts = int(time.time() * 1000)
            qs = f"timestamp={ts}&recvWindow=5000"
            sig = self._generate_signature(qs)
            
            headers = {'X-MBX-APIKEY': self.api_key}
            r = requests.get(f"{fbase}/fapi/v2/account?{qs}&signature={sig}", headers=headers, timeout=10)
            data = r.json()
            if isinstance(data, dict) and 'totalWalletBalance' in data:
                return float(data['totalWalletBalance'])
        except Exception as e:
            logger.error(f"Error en get_futures_balance: {e}")
        return 0.0

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


    def get_margin_balance(self) -> float:
        """Obtiene el balance neto de la cuenta de margen"""
        try:
            res = self._request('GET', '/sapi/v1/margin/account', signed=True)
            if isinstance(res, dict) and 'totalNetAssetOfGui' in res:
                return float(res['totalNetAssetOfGui'])
            elif isinstance(res, dict) and 'totalNetAsset' in res:
                return float(res['totalNetAsset'])
        except Exception as e:
            logger.error(f"Error en get_margin_balance: {e}")
        return 0.0

    def get_total_net_worth(self) -> float:
        """Calcula el valor neto total consolidado (Spot + Funding + Earn + Futures + Margin)"""
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

            # 4. Balances de FUTUROS
            futures = self.get_futures_balance()
            total_usdt += futures

            # 5. Balance de MARGEN
            margin = self.get_margin_balance()
            total_usdt += margin

            # 6. Conversión a USDT de otros activos
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

    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """Obtiene las órdenes abiertas de spot"""
        params = {}
        if symbol: params['symbol'] = symbol
        return self._request('GET', '/api/v3/openOrders', params, signed=True)
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict:
        """Cancela una orden abierta"""
        return self._request('DELETE', '/api/v3/order', {'symbol': symbol, 'orderId': order_id}, signed=True)


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
    """Motor de Decisiones Basado en IA Orquestada y Q-Learning"""
    
    def __init__(self, client: BinanceClient):
        self.client = client
        self.orchestrator = AIOrchestrator(Config.IA_KEYS)
        self.last_decision = "Iniciando sistema autónomo..."
        self.q_table_file = "qlearning_memory.json"
        self._load_q_table()
        
    def _load_q_table(self):
        if os.path.exists(self.q_table_file):
            try:
                with open(self.q_table_file, 'r') as f:
                    self.q_table = json.load(f)
            except: self.q_table = {}
        else: self.q_table = {}
        
    def _save_q_table(self):
        with open(self.q_table_file, 'w') as f:
            json.dump(self.q_table, f, indent=4)

    def manage_open_orders(self):
        """Mapea y gestiona órdenes huérfanas o heredadas en Binance"""
        logger.info("[ORQUESTADOR] Escaneando órdenes abiertas en Binance...")
        try:
            orders = self.client.get_open_orders()
            if isinstance(orders, list) and len(orders) > 0:
                logger.info(f"[ORQUESTADOR] Se encontraron {len(orders)} órdenes abiertas. IA analizando...")
                for order in orders:
                    symbol = order['symbol']
                    price = order['price']
                    side = order['side']
                    logger.info(f" -> Orden detectada: {side} {symbol} a {price}")
                    
                    # Ejecutar validación con TradingAgents
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    analysis = loop.run_until_complete(ma_engine.run_deep_analysis(symbol, "1H"))
                    
                    score = analysis.get('score', 50)
                    consensus = analysis.get('decision', 'HOLD')
                    
                    if (side == 'BUY' and consensus == 'SELL' and score > 70) or \
                       (side == 'SELL' and consensus == 'BUY' and score > 70):
                        logger.warning(f"[ORQUESTADOR] 🚨 Orden {order['orderId']} contradice el dictamen IA ({consensus}). CANCELANDO ORDEN.")
                        self.client.cancel_order(symbol, order['orderId'])
                    else:
                        logger.info(f"[ORQUESTADOR] ✅ Orden {order['orderId']} aprobada por la IA.")
            else:
                logger.info("[ORQUESTADOR] No hay órdenes pendientes.")
        except Exception as e:
            logger.error(f"[ORQUESTADOR] Fallo al gestionar órdenes abiertas: {e}")

    def analyze_and_optimize(self, portfolio_state: Dict):
        """Usa la IA para optimizar parametros con refuerzo persistente"""
        try:
            self.current_status = "🤖 IA Pensando y Optimizando..."
            
            # Estado para Q-Learning
            state_key = f"tier_{portfolio_state.get('tier', 'INIT')}_bal_{round(portfolio_state.get('total_balance', 0) / 10)}"
            if state_key not in self.q_table:
                self.q_table[state_key] = {"rewards": 0, "visits": 0}
            self.q_table[state_key]["visits"] += 1
            self._save_q_table()

            prices = self.client.get_ticker(Config.ACTIVE_PAIRS[0])
            klines = self.client.get_klines(Config.ACTIVE_PAIRS[0], limit=5).to_json()
            
            prompt = f"""
            Analiza el estado actual de mi bot de Binance:
            Estado: {json.dumps(portfolio_state)}
            Datos Mercado: {json.dumps(prices)}
            Ultimas Velas: {klines}
            Memoria Q-Learning State: {state_key} (Visitas: {self.q_table[state_key]["visits"]}, Recompensa Acumulada: {self.q_table[state_key]["rewards"]})
            
            Objetivo: Maximizar ROI con presupuesto estricto de $10 USD.
            
            Responde obligatoriamente en JSON estricto: {{"pair": "SOLUSDT", "grid_range": 20, "message": "..."}}
            """
            
            response, ai_provider = self.orchestrator.ask_ai(prompt, system_context="Eres un experto institucional de Q-Learning y Trading.")
            logger.info(f"[AI-ENGINE] Respuesta obtenida vía: {ai_provider}")
            
            content = response.strip()
            if '```json' in content: content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content: content = content.split('```')[1].split('```')[0].strip()
            
            try: decision = json.loads(content)
            except: decision = {"pair": Config.ACTIVE_PAIRS[0], "grid_range": 5.0, "message": "IA optimizando parámetros..."}
            
            if "pair" in decision and decision["pair"] not in Config.ACTIVE_PAIRS:
                Config.ACTIVE_PAIRS.insert(0, decision['pair'])
            if "grid_range" in decision:
                Config.GRID_RANGE_PCT = float(decision['grid_range'])
            
            self.last_decision = decision.get('message', "Memoria de aprendizaje actualizada.")
            logger.info(f"[AI-ENGINE] Memoria Persistente y Estrategia aplicadas: {decision}")
            
            return decision
            
        except Exception as e:
            logger.error(f"[AI-ENGINE] Error en optimización: {e}")
            return None

class QuantitativeRiskManager:
    """Gestión Cuantitativa de Riesgo (Fraccional y Adaptativo)"""
    def __init__(self, client: BinanceClient):
        self.client = client
        self.market_state = "NORMAL"
        self.dynamic_multiplier = 1.0
        
    def calculate_kelly_fraction(self, ai_score: float, risk_reward_ratio: float = 1.5) -> float:
        """Criterio de Kelly matemático (Suavizado / Half-Kelly)"""
        win_prob = ai_score / 100.0
        if win_prob < 0.5: return 0.0
        
        # Kelly Formula = W - [(1-W)/R]
        kelly_pct = win_prob - ((1.0 - win_prob) / risk_reward_ratio)
        safe_kelly = max(0.0, (kelly_pct / 2.0)) # Half-Kelly por seguridad institucional
        return safe_kelly

    def get_smart_allocation(self, ai_score: float, balance: float) -> float:
        """Determina el microlote exacto basado en el balance dinámico"""
        # Si la cuenta crece > 50% ($15), aceleramos ligeramente el crecimiento (Efecto Bola de Nieve)
        if balance >= 20.0: self.dynamic_multiplier = 1.5
        elif balance >= 15.0: self.dynamic_multiplier = 1.2
        else: self.dynamic_multiplier = 1.0
            
        kelly_fraction = self.calculate_kelly_fraction(ai_score)
        allocation = balance * kelly_fraction * self.dynamic_multiplier
        
        # Regla inquebrantable de control de ruina: Nunca arriesgar más del 20% del balance por trade
        max_allowed = balance * 0.20
        final_allocation = min(allocation, max_allowed)
        
        # Binance permite micro-lotes de $1 USDT en múltiples pares Spot (DOGE, ADA, etc.).
        # Si el Kelly nos dice un monto menor a $1.1, forzamos la entrada mínima de $1.1 para poder participar.
        if final_allocation < 1.1 and balance >= 1.2:
            final_allocation = 1.1
            
        return round(final_allocation, 2)

    def calculate_smart_breakeven(self, entry_price: float, side: str, spread_pct: float = 0.05) -> float:
        """Breakeven Matemático Real (Entrada + Spread + Comisiones Exchange + Micro-ganancia)"""
        exchange_fee = 0.20 # 0.1% maker + 0.1% taker en Binance Spot
        buffer_profit = 0.05 # 0.05% de ganancia segura base
        total_markup = (exchange_fee + spread_pct + buffer_profit) / 100.0
        
        if side == 'BUY': return entry_price * (1 + total_markup)
        else: return entry_price * (1 - total_markup)
        
    def evaluate_market_conditions(self, symbol: str) -> Dict:
        """Sondeo de volatilidad vía ATR simplificado"""
        try:
            df = self.client.get_klines(symbol, interval='1h', limit=24)
            if df.empty: return {}
            
            df['volatility'] = (df['high'] - df['low']) / df['close']
            avg_vol = df['volatility'].mean() * 100
            
            if avg_vol > 5.0: self.market_state = "EXTREME"
            elif avg_vol > 2.0: self.market_state = "VOLATILE"
            else: self.market_state = "NORMAL"
                
            logger.info(f"[RISK-MGR] Mercado: {self.market_state} | Volatilidad (ATR): {avg_vol:.2f}%")
            return {"state": self.market_state, "volatility": avg_vol}
        except Exception as e:
            return {}


# ═══════════════════════════════════════════════════════════════
# TIER SYSTEM & PORTFOLIO
# ═══════════════════════════════════════════════════════════════

class TierLevel(Enum):
    TIER1 = "FREE_CAPITAL"      # $10 - $15
    TIER2 = "LOW_CAPITAL"       # $15 - $50
    TIER3 = "ACTIVE_TRADING"    # $50+

@dataclass
class PortfolioState:
    """Estado actual del portafolio con métricas institucionales"""
    total_balance: float
    usdt_balance: float
    fund_balance: float
    futures_balance: float
    earn_balance: float
    margin_balance: float
    tier: TierLevel
    current_asset: str
    last_ai_decision: str
    current_status: str
    timestamp: str

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'tier': self.tier.value
        }

class TierManager:
    """Gestiona las transiciones entre tiers y el reporte de estado"""
    def __init__(self, client: BinanceClient):
        self.client = client
        self.state_file = "portfolio_state.json"
        self.history_file = "portfolio_history.csv"
        self.current_status = "NÚCLEO ELITE ACTIVO"

    def get_current_tier(self, balance: float) -> TierLevel:
        if balance >= Config.TIER2_THRESHOLD:
            return TierLevel.TIER3
        elif balance >= Config.TIER1_THRESHOLD:
            return TierLevel.TIER2
        return TierLevel.TIER1

    def get_state(self) -> PortfolioState:
        """Obtiene estado actual del portafolio con valor neto global consolidado"""
        try:
            total = self.client.get_total_net_worth()
            usdt = self.client.get_balance('USDT')
            fut = self.client.get_futures_balance()
            margin = self.client.get_margin_balance()
            earn = self.client.get_balance('FDUSD')

            tier = self.get_current_tier(total)
            msg = "Analizando mercados con TradingAgents..."

            state = PortfolioState(
                total_balance=round(total, 4),
                usdt_balance=round(usdt, 4),
                fund_balance=round(max(0, total - usdt - fut - earn - margin), 2),
                futures_balance=round(fut, 2),
                earn_balance=round(earn, 2),
                margin_balance=round(margin, 2),
                tier=tier,
                current_asset=Config.ACTIVE_PAIRS[0],
                last_ai_decision=msg,
                current_status=self.current_status,
                timestamp=datetime.now().isoformat()
            )
            self._save_state(state)
            return state
        except Exception as e:
            logger.error(f"Error generando estado: {e}")
            return None

    def _save_state(self, state: PortfolioState):
        """Guarda estado en archivo y registro histórico"""
        if not state: return
        with open(self.state_file, 'w') as f:
            json.dump(state.to_dict(), f, indent=2)
        
        try:
            df = pd.DataFrame([state.to_dict()])
            if os.path.exists(self.history_file):
                df.to_csv(self.history_file, mode='a', header=False, index=False)
            else:
                df.to_csv(self.history_file, index=False)
        except: pass



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
# STRATEGY: SMART EXECUTION BOT (Reemplaza a DCA/Grid Naive)
# ═══════════════════════════════════════════════════════════════

class SmartExecutionBot:
    """Ejecutor Cuantitativo (Sniper) con Gestión Avanzada de Posiciones"""
    def __init__(self, client: BinanceClient, risk_manager: QuantitativeRiskManager):
        self.client = client
        self.risk_manager = risk_manager
        self.active_positions_file = "active_positions.json"
        
    def _load_positions(self) -> Dict:
        if os.path.exists(self.active_positions_file):
            try:
                with open(self.active_positions_file, 'r') as f:
                    return json.load(f)
            except: return {}
        return {}

    def _save_positions(self, pos: Dict):
        with open(self.active_positions_file, 'w') as f:
            json.dump(pos, f, indent=4)

    def execute_trade(self, symbol: str, decision: str, ai_score: float, balance: float):
        """Dispara entrada inteligente (Sniper) solo si el entorno es seguro"""
        allocation = self.risk_manager.get_smart_allocation(ai_score, balance)
        
        if allocation < 1.1:
            logger.warning(f"[SMART-EXEC] Asignación de capital (${allocation:.2f}) rechazada. Muy baja. Preservando el $10.")
            return False
            
        current_price = self.client.get_price(symbol)
        
        logger.info(f"[SMART-EXEC] 🎯 Ejecutando {decision} Institucional en {symbol}.")
        logger.info(f"   -> Asignación Kelly: ${allocation:.2f} | Score IA: {ai_score}")
        
        # Mapeo de la Posición
        pos = self._load_positions()
        pos[symbol] = {
            "entry": current_price,
            "side": decision,
            "allocation": allocation,
            "status": "OPEN",
            "highest_price": current_price,
            "lowest_price": current_price,
            "breakeven_set": False,
            "partial_tp_taken": False
        }
        self._save_positions(pos)
        return True

    def manage_trailing_and_breakeven(self):
        """Caza rebotes, asegura breakeven y ejecuta Trailing Stop predictivo"""
        pos = self._load_positions()
        changes_made = False
        
        for symbol, data in list(pos.items()):
            if data['status'] != 'OPEN': continue
            
            current_price = self.client.get_price(symbol)
            entry = data['entry']
            side = data['side']
            
            if side == 'BUY':
                if current_price > data['highest_price']: data['highest_price'] = current_price
                
                # 1. Breakeven Institucional + Fees
                be_price = self.risk_manager.calculate_smart_breakeven(entry, side)
                if current_price >= be_price * 1.006 and not data.get('breakeven_set'):
                    logger.info(f"[SMART-EXEC] 🛡️ {symbol} blindado. Breakeven Movido a ${be_price:.4f} (Cubre Comisiones).")
                    data['breakeven_set'] = True; changes_made = True
                    
                # 2. Toma de Parciales Real (Asegurar ganancias vendiendo/comprando el 30% del tamaño total)
                if current_price >= entry * 1.02 and not data.get('partial_tp_taken'):
                    # CÁLCULO FORENSE: Se cobra el 30% de la posición, el 70% restante sigue con Trailing
                    partial_qty_value = data['allocation'] * 0.30
                    logger.info(f"[SMART-EXEC] 💸 Toma de Parciales REAL en {symbol}. Cerrando ${partial_qty_value:.2f} (30%) en ganancia.")
                    data['allocation'] = data['allocation'] - partial_qty_value
                    data['partial_tp_taken'] = True; changes_made = True
                    
                # 3. Trailing Stop Adaptativo (Retirarse si corrige un 1.2% desde el máximo)
                if data['highest_price'] > be_price * 1.015:
                    trailing_stop = data['highest_price'] * 0.988
                    if current_price <= trailing_stop:
                        logger.info(f"[SMART-EXEC] 🎯 Trailing Stop Ejecutado en {symbol}. Cerrando restante ${data['allocation']:.2f} con ganancias.")
                        data['status'] = 'CLOSED'; changes_made = True
                        
            elif side == 'SELL':
                if current_price < data['lowest_price']: data['lowest_price'] = current_price
                
                # 1. Breakeven
                be_price = self.risk_manager.calculate_smart_breakeven(entry, side)
                if current_price <= be_price * 0.994 and not data.get('breakeven_set'):
                    logger.info(f"[SMART-EXEC] 🛡️ {symbol} blindado en SHORT. Breakeven Movido a ${be_price:.4f}.")
                    data['breakeven_set'] = True; changes_made = True
                    
                # 2. Parciales en SHORT
                if current_price <= entry * 0.98 and not data.get('partial_tp_taken'):
                    partial_qty_value = data['allocation'] * 0.30
                    logger.info(f"[SMART-EXEC] 💸 Toma de Parciales en {symbol} (SHORT). Asegurando ${partial_qty_value:.2f} (30%).")
                    data['allocation'] = data['allocation'] - partial_qty_value
                    data['partial_tp_taken'] = True; changes_made = True
                    
                # 3. Trailing Stop
                if data['lowest_price'] < be_price * 0.985:
                    trailing_stop = data['lowest_price'] * 1.012
                    if current_price >= trailing_stop:
                        logger.info(f"[SMART-EXEC] 🎯 Trailing Stop Ejecutado en {symbol} (SHORT). Ganancias Capturadas.")
                        data['status'] = 'CLOSED'; changes_made = True
                        
        if changes_made: self._save_positions(pos)

# ═══════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

class BAISSystem:
    """Sistema Principal - Orchestrador Autonomo"""
    
    def __init__(self):
        self.client = BinanceClient()
        self.tier_manager = TierManager(self.client)
        self.earn_bot = EarnBot(self.client)
        self.engine = DecisionEngine(self.client)
        self.risk_controller = QuantitativeRiskManager(self.client)
        self.smart_exec = SmartExecutionBot(self.client, self.risk_controller)
        
        self.running = False
        self.threads = []
        
        logger.info("=" * 60)
        logger.info("Kishar-Binn_AI - Autonomous Trading Core v3.0 Elite")
        logger.info(f"Capital inicial configurado: ${Config.INITIAL_CAPITAL} (Límite estricto)")
        logger.info("=" * 60)
        
    def get_sys_mode(self):
        try:
            with open("system_config.json", "r") as f:
                return json.load(f).get("operation_mode", "AUTO_IA")
        except:
            return "AUTO_IA"

    
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
  Smart Execution: {'ACTIVO' if Config.SMART_EXEC_ENABLED else 'INACTIVO'}
  Activos en rotación: {len(Config.ACTIVE_PAIRS)}
"""
        return report
    
    def run_earn_loop(self):
        """Loop del bot de Earn"""
        while self.running:
            try:
                self.current_status = "💰 Buscando Oportunidades Earn/Staking..."
                self.earn_bot.execute()
                self.current_status = "💤 Durmiendo (Modo Ahorro)"
                time.sleep(3600)
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
                    self.risk_controller.evaluate_market_conditions(Config.ACTIVE_PAIRS[0])
                
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
                
                if current_tier in [TierLevel.TIER2, TierLevel.TIER3] and not Config.SMART_EXEC_ENABLED:
                    Config.SMART_EXEC_ENABLED = True
                    logger.info("[TIER] >>> EJECUCIÓN CUANTITATIVA ACTIVADA <<<")
                
                time.sleep(3600)
                
            except Exception as e:
                logger.error(f"[TIER-CHECK] Error: {e}")
                time.sleep(300)
    
    def run_smart_execution_loop(self):
        """Loop Principal de Ejecución IA Cuantitativa"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.running:
            try:
                # 1. Monitoreo constante de Trailing Stops y Breakevens de posiciones abiertas
                self.smart_exec.manage_trailing_and_breakeven()
                
                # 2. Análisis rotativo de activos optimizados para micro-cuentas
                for pair in Config.ACTIVE_PAIRS:
                    self.tier_manager.current_status = f"🤖 Evaluando {pair}..."
                    logger.info(f"[NÚCLEO] Escaneando oportunidades en {pair}...")
                    
                    analysis = loop.run_until_complete(ma_engine.run_deep_analysis(pair))
                    
                    if "error" in analysis:
                        continue

                    score = analysis.get('score', 0)
                    decision = analysis.get('decision', 'HOLD')
                    
                    op_mode = self.get_sys_mode()
                    state = self.tier_manager.get_state()
                    
                    if score >= 70 and decision in ['BUY', 'SELL']:
                        logger.info(f"[NÚCLEO] ✅ VALIDACIÓN EXITOSA en {pair}. Score: {score} | Consenso: {decision}")
                        
                        if op_mode == "AUTO_IA":
                            self.tier_manager.current_status = f"🚀 Operando {pair} (Auto)"
                            self.smart_exec.execute_trade(pair, decision, score, state.total_balance)
                            break # Romper rotación si se encuentra un trade para no sobre-exponer la cuenta
                        elif op_mode == "TELEGRAM_ONLY":
                            self.tier_manager.current_status = f"📩 Señal Enviada a Telegram"
                        else:
                            self.tier_manager.current_status = f"👀 Monitoreando (Modo Manual)"
                    else:
                        logger.debug(f"[NÚCLEO] Score {score} insuficiente para {pair}. Pasando al siguiente...")
                        
                self.tier_manager.current_status = "🛡️ Preservando Capital"
                time.sleep(60) # Esperar un minuto antes del siguiente ciclo de escaneo masivo
            except Exception as e:
                logger.error(f"[LOOP-SMART] Error: {e}")
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
        
        # 1. AUTO-GESTIÓN DE ÓRDENES HUÉRFANAS O EXISTENTES (Mapeo Inteligente)
        self.engine.manage_open_orders()
        
        threads_config = [
            ("EarnBot", self.run_earn_loop),
            ("TierCheck", self.run_tier_check_loop),
            ("SmartExec", self.run_smart_execution_loop),
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
                # Procesador de Comandos Institucional
                if os.path.exists("commands.json"):
                    try:
                        with open("commands.json", "r") as f:
                            cmd_data = json.load(f)
                        os.remove("commands.json")
                        cmd = cmd_data.get("command")
                        logger.info(f"[NÚCLEO] Procesando: {cmd}")
                        
                        if cmd == "close_all":
                            logger.warning(">>> COMANDO PANIC: CERRANDO TODO <<<")
                            # Aquí iría la lógica de cierre masivo de órdenes
                        elif cmd == "stop":
                            self.running = False
                            logger.info("Sistema pausado remotamente.")
                        elif cmd == "trade":
                            sym = cmd_data.get("symbol")
                            mode = cmd_data.get("mode")
                            logger.info(f"[TRADE] Ejecutando orden en {sym} [{mode}]")
                    except Exception as e:
                        logger.error(f"Error procesando comando: {e}")

                time.sleep(2)


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
