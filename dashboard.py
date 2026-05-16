from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import json
import hmac
import hashlib
import time
import logging
import requests as req
from pydantic import BaseModel
from ai_orchestrator import AIOrchestrator
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="KISHAR-BINN_AI ELITE MONITOR")

# Configuración
STATE_FILE = "portfolio_state.json"
IS_CLOUD = os.getenv('RENDER', '') != '' or os.getenv('IS_CLOUD', '') == '1'
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Dashboard")

# Orquestador para el chat
IA_KEYS = {
    'gemini': os.getenv('GEMINI_API_KEY', ''),
    'deepseek': os.getenv('DEEPSEEK_API_KEY', ''),
    'groq': os.getenv('GROQ_API_KEY', ''),
    'huggingface': os.getenv('HF_API_KEY', '')
}
orchestrator = AIOrchestrator(IA_KEYS)

# ─── Helper: obtener balance de Binance directamente ───────────
def fetch_binance_state() -> dict:
    """Obtiene el estado real desde Binance API cuando corre en la nube."""
    api_key = os.getenv('BINANCE_API_KEY', '')
    secret = os.getenv('BINANCE_SECRET_KEY', '')
    testnet = os.getenv('BINANCE_TESTNET', 'True') == 'True'
    base = 'https://testnet.binance.vision' if testnet else 'https://api.binance.com'
    
    if not api_key or not secret:
        return {"error": "API keys no configuradas", "total_balance": 0,
                "usdt_balance": 0, "earn_balance": 0, "grid_balance": 0,
                "tier": "NO_KEY", "last_ai_decision": "Configura las API keys de Binance",
                "current_asset": "BTCUSDT"}
    try:
        ts = int(time.time() * 1000)
        qs = f"timestamp={ts}&recvWindow=5000"
        sig = hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
        headers = {'X-MBX-APIKEY': api_key}
        # 1. Obtener saldos de SPOT
        r = req.get(f"{base}/api/v3/account?{qs}&signature={sig}", headers=headers, timeout=8)
        data = r.json()
        
        assets = {}
        if isinstance(data, dict) and 'balances' in data:
            for b in data['balances']:
                qty = float(b['free']) + float(b['locked'])
                if qty > 0: assets[b['asset']] = qty
                
        # 1.1 Obtener saldos de FONDOS (Funding)
        try:
            r_fund = req.post(f"{base}/sapi/v1/asset/get-funding-asset?{qs}&signature={sig}", headers=headers, timeout=8)
            fund_data = r_fund.json()
            if isinstance(fund_data, list):
                for f in fund_data:
                    qty = float(f.get('free', 0)) + float(f.get('locked', 0))
                    if qty > 0: assets[f['asset']] = assets.get(f['asset'], 0.0) + qty
        except Exception: pass
        
        # 1.2 Obtener saldos de EARN
        try:
            r_earn = req.get(f"{base}/sapi/v1/simple-earn/flexible/position?{qs}&signature={sig}", headers=headers, timeout=8)
            earn_data = r_earn.json()
            if isinstance(earn_data, dict) and 'rows' in earn_data:
                for row in earn_data['rows']:
                    qty = float(row.get('totalAmount', 0))
                    if qty > 0: assets[row['asset']] = assets.get(row['asset'], 0.0) + qty
        except Exception: pass
        
        usdt_only = 0.0
        total_balance = 0.0
        
        # 2. Obtener precios para conversión
        prices_req = req.get(f"{base}/api/v3/ticker/price", timeout=8)
        prices_data = prices_req.json()
        
        price_map = {}
        if isinstance(prices_data, list):
            price_map = {item['symbol']: float(item['price']) for item in prices_data if 'symbol' in item}
        
        for asset, qty in assets.items():
            if asset == 'USDT':
                usdt_only = qty
                total_balance += qty
            else:
                symbol = f"{asset}USDT"
                if symbol in price_map:
                    total_balance += qty * price_map[symbol]
                else:
                    # Si no hay par USDT, intentamos aproximar a 0 o buscar otro par
                    pass
                    
        return {
            "total_balance": round(total_balance, 4),
            "usdt_balance": round(usdt_only, 4),
            "earn_balance": 0.0,
            "grid_balance": 0.0,
            "tier": "CLOUD",
            "last_ai_decision": "Sistema en modo nube — datos en tiempo real de Binance.",
            "current_asset": "BTCUSDT",
            "source": "binance_api"
        }
    except Exception as e:
        logger.error(f"Error Binance API: {e}")
        return {"error": str(e), "total_balance": 0, "usdt_balance": 0,
                "earn_balance": 0, "grid_balance": 0, "tier": "ERROR",
                "last_ai_decision": "Error conectando con Binance",
                "current_asset": "BTCUSDT"}

@app.get("/api/state")
async def get_state():
    if IS_CLOUD:
        return fetch_binance_state()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            return fetch_binance_state()
    return {"total_balance": 0, "usdt_balance": 0, "earn_balance": 0,
            "grid_balance": 0, "tier": "INIT",
            "last_ai_decision": "Iniciando sistema...", "current_asset": "BTCUSDT"}

# ─── Señales de Trading en Tiempo Real ────────────────────────────────────────
_sig_cache = {"data": [], "ts": 0}

def compute_signals() -> list:
    """Calcula señales técnicas desde klines de Binance (15m, 20 velas).
    Retorna lista ordenada por confianza descendente."""
    base = "https://api.binance.com"
    symbols = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]
    out = []
    for sym in symbols:
        try:
            r = req.get(f"{base}/api/v3/klines?symbol={sym}&interval=15m&limit=20", timeout=6)
            klines = r.json()
            if not isinstance(klines, list) or len(klines) < 5:
                continue
            closes  = [float(k[4]) for k in klines]
            volumes = [float(k[5]) for k in klines]
            cur = closes[-1]; prev = closes[-2]; first = closes[0]
            chg = (cur - prev) / prev * 100
            trend = (cur - first) / first * 100
            # RSI simplificado
            gains  = [max(closes[i]-closes[i-1],0) for i in range(1,len(closes))]
            losses = [max(closes[i-1]-closes[i],0) for i in range(1,len(closes))]
            ag = sum(gains)/len(gains) if gains else 0
            al = sum(losses)/len(losses) if losses else 1
            rsi = 100 - 100/(1 + ag/al) if al else 50
            avg_vol = sum(volumes[:-1])/max(len(volumes)-1,1)
            vol_r = volumes[-1]/avg_vol if avg_vol else 1
            # Señal
            sig = "NEUTRO"; conf = 45.0
            if rsi < 32 and vol_r > 1.1:
                sig = "COMPRA"; conf = min(88, 62+(32-rsi)*0.9+vol_r*4)
            elif rsi > 68 and vol_r > 1.1:
                sig = "VENTA"; conf = min(88, 62+(rsi-68)*0.9+vol_r*4)
            elif trend > 1.8 and vol_r > 1.3:
                sig = "COMPRA"; conf = min(78, 55+trend*3+vol_r*3)
            elif trend < -1.8 and vol_r > 1.3:
                sig = "VENTA"; conf = min(78, 55+abs(trend)*3+vol_r*3)
            else:
                conf = max(35, 40+vol_r*4)
            out.append({"symbol":sym,"price":round(cur,4),"change_pct":round(chg,2),
                        "trend_pct":round(trend,2),"rsi":round(rsi,1),
                        "volume_ratio":round(vol_r,2),
                        "volume_usdt":round(volumes[-1]*cur,0),
                        "signal":sig,"confidence":round(conf,1)})
        except Exception as e:
            logger.warning(f"Signal {sym}: {e}")
    out.sort(key=lambda x: x["confidence"], reverse=True)
    return out

@app.get("/api/signals")
async def get_signals():
    """Devuelve señales de trading con confianza. Caché de 30s."""
    global _sig_cache
    if time.time() - _sig_cache["ts"] > 30:
        _sig_cache = {"data": compute_signals(), "ts": time.time()}
    return {"signals": _sig_cache["data"], "updated_at": int(_sig_cache["ts"])}


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    html_content = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>KISHAR-BINN AI</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Fira+Code&display=swap" rel="stylesheet">
<script src="https://s3.tradingview.com/tv.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0E0E0F;--s1:#161618;--s2:#202024;--br:#3B82F6;--gr:#10B981;--rd:#f87171;--tx:#F3F4F6;--mu:#9CA3AF;--brd:rgba(255,255,255,0.08);--rad:12px}
body{background:var(--bg);color:var(--tx);font-family:'Inter',sans-serif;overflow-x:hidden;padding-bottom:64px}
body{background-image:linear-gradient(rgba(255,255,255,.015) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.015) 1px,transparent 1px);background-size:32px 32px}
::-webkit-scrollbar{width:4px;height:4px}::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:4px}
/* HEADER */
.hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:rgba(22,22,24,.95);border-bottom:1px solid var(--brd);position:sticky;top:0;z-index:50;backdrop-filter:blur(12px)}
.logo{display:flex;align-items:center;gap:10px}
.logo-ic{width:36px;height:36px;border-radius:9px;background:linear-gradient(135deg,#3B82F6,#1d4ed8);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;color:#fff}
.logo h1{font-size:15px;font-weight:700;color:#fff;line-height:1.2}
.logo p{font-size:9px;color:var(--mu)}
.hdr-right{display:flex;align-items:center;gap:8px}
.pill{display:flex;align-items:center;gap:6px;background:var(--s1);border:1px solid var(--brd);padding:4px 10px;border-radius:999px;font-size:10px;color:var(--mu)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--gr);box-shadow:0 0 6px var(--gr);animation:blink 2s infinite}
.sym-badge{background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.35);border-radius:8px;padding:4px 10px;font-size:11px;font-weight:700;color:#60A5FA;font-family:'Fira Code',monospace}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
/* CHART - full width, right below header */
.chart-block{width:100%;height:320px;background:var(--s1);border-bottom:1px solid var(--brd)}
@media(min-width:768px){.chart-block{height:420px}}
/* MAIN GRID */
.main{max-width:1400px;margin:0 auto;padding:12px}
@media(min-width:900px){.grid2{display:grid;grid-template-columns:1fr 360px;gap:12px;align-items:start}}
/* CARDS */
.card{background:rgba(22,22,24,.85);border:1px solid var(--brd);border-radius:var(--rad);backdrop-filter:blur(10px);margin-bottom:12px;transition:border-color .2s}
.card:hover{border-color:rgba(59,130,246,.3)}
.card-hdr{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--brd);background:rgba(0,0,0,.25)}
.card-hdr span{font-size:10px;font-weight:700;color:var(--mu);text-transform:uppercase;letter-spacing:.07em}
/* METRICS STRIP */
.metrics{display:flex;gap:10px;overflow-x:auto;margin-bottom:12px;scrollbar-width:none}
.metrics::-webkit-scrollbar{display:none}
.mc{min-width:130px;flex:1;padding:12px 14px}
.ml{font-size:9px;font-weight:600;color:var(--mu);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
.mv{font-size:20px;font-weight:700;color:#fff;line-height:1}
.ms{font-size:10px;margin-top:4px;color:var(--mu)}
/* SIGNALS */
.sig-item{padding:8px 12px;border-bottom:1px solid rgba(255,255,255,.04);cursor:pointer;transition:background .15s}
.sig-item:hover{background:rgba(59,130,246,.06)}
.sig-item:last-child{border-bottom:none}
.sig-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.sig-sym{font-size:12px;font-weight:700;color:#fff;font-family:'Fira Code',monospace}
.sig-price{font-size:11px;color:#e2e8f0;font-family:'Fira Code',monospace}
.badge{font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px}
.badge.buy{background:rgba(16,185,129,.15);color:#10B981;border:1px solid rgba(16,185,129,.3)}
.badge.sell{background:rgba(248,113,113,.15);color:#f87171;border:1px solid rgba(248,113,113,.3)}
.badge.neut{background:rgba(99,102,241,.15);color:#818CF8;border:1px solid rgba(99,102,241,.3)}
.bar-row{margin:4px 0}
.bar-lbl{display:flex;justify-content:space-between;font-size:9px;color:#6B7280;margin-bottom:3px}
.bar-lbl b{color:var(--mu)}
.bar-tr{height:4px;background:rgba(255,255,255,.06);border-radius:999px;overflow:hidden}
.bar-fi{height:100%;border-radius:999px;transition:width .6s}
.sig-stats{display:flex;gap:12px;font-size:9px;color:#6B7280;margin-top:4px}
.sig-stats b{color:var(--mu)}
/* AI BOX */
.ai-box{padding:12px 14px;border-left:3px solid var(--br)}
.ai-lbl{font-size:9px;font-weight:600;color:var(--mu);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
.ai-txt{font-size:12px;color:#e2e8f0;line-height:1.6}
/* LOG */
.log-box{height:140px;overflow-y:auto;font-size:10px;font-family:'Fira Code',monospace;color:var(--mu);padding:10px 12px;background:rgba(0,0,0,.3)}
.le{margin-bottom:4px;line-height:1.4}.lt{color:#374151}.lok{color:#34D399}.ler{color:#f87171}
/* CHAT */
.chat-wrap{display:flex;flex-direction:column;height:380px}
.chat-msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
.mb{font-size:12px;line-height:1.5;padding:8px 12px;border-radius:12px;max-width:88%;word-break:break-word}
.mb.ai{background:var(--s1);border:1px solid var(--brd);color:#e2e8f0}
.mb.usr{background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.25);color:#bfdbfe;align-self:flex-end}
.mb.err{background:rgba(248,113,113,.1);border:1px solid rgba(248,113,113,.25);color:#fca5a5}
.chat-inp{display:flex;gap:8px;padding:8px;border-top:1px solid var(--brd)}
.chat-inp input{flex:1;background:var(--bg);border:1px solid var(--brd);border-radius:8px;padding:9px 12px;font-size:12px;color:#fff;outline:none;font-family:'Inter',sans-serif}
.chat-inp input:focus{border-color:rgba(59,130,246,.5)}
.send-btn{width:36px;height:36px;border:none;border-radius:8px;background:var(--br);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.send-btn:hover{background:#60A5FA}
/* BOTTOM NAV mobile */
.bnav{position:fixed;bottom:0;left:0;right:0;display:flex;background:rgba(22,22,24,.97);border-top:1px solid var(--brd);backdrop-filter:blur(16px);height:60px;z-index:100}
.ni{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;border:none;background:transparent;color:#4B5563;font-size:10px;font-weight:600;font-family:'Inter',sans-serif;cursor:pointer}
.ni.active{color:#60A5FA}
.ni svg{width:20px;height:20px}
.sec{display:none}.sec.on{display:block}
@media(min-width:900px){body{padding-bottom:0}.bnav{display:none}.sec{display:block!important}}
</style>
</head>
<body>
<!-- HEADER: Logo, par activo, estado live -->
<header class="hdr">
  <div class="logo">
    <div class="logo-ic">KB</div>
    <div>
      <h1>KISHAR-BINN AI</h1>
      <p>Sistema Cuantitativo Institucional v2.0</p>
    </div>
  </div>
  <div class="hdr-right">
    <!-- Par activo actualizado en tiempo real -->
    <div class="sym-badge" id="active-sym">BTCUSDT</div>
    <div class="pill"><span class="dot"></span><span id="live-lbl">Live</span></div>
  </div>
</header>

<!-- CHART: Gráfico TradingView justo debajo del header -->
<div class="chart-block" id="tv_chart"></div>

<!-- MAIN CONTENT -->
<div class="main">
  <!-- Tabs solo móvil -->
  <div class="bnav">
    <button class="ni active" id="n0" onclick="st(0)">
      <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
      Resumen
    </button>
    <button class="ni" id="n1" onclick="st(1)">
      <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
      Señales
    </button>
    <button class="ni" id="n2" onclick="st(2)">
      <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
      Terminal
    </button>
  </div>

  <div class="grid2">
    <!-- COLUMNA IZQUIERDA -->
    <div>
      <!-- SECCIÓN 0: Resumen -->
      <div class="sec on" id="s0">
        <!-- Métricas de balance -->
        <div class="metrics">
          <div class="card mc">
            <div class="ml">Net Worth</div>
            <div class="mv" id="total-balance">$0.00</div>
            <div class="ms" style="color:#34D399">Capital Global</div>
          </div>
          <div class="card mc">
            <div class="ml">Libre USDT</div>
            <div class="mv" id="free-balance">$0.00</div>
            <div class="ms">Disponible</div>
          </div>
          <div class="card mc">
            <div class="ml">Tier <span id="tier-badge" style="font-size:9px;background:#202024;border:1px solid rgba(255,255,255,.08);padding:1px 6px;border-radius:4px;font-family:'Fira Code',monospace">—</span></div>
            <div class="mv" id="earn-balance" style="font-size:14px;margin-top:8px">$0.00</div>
            <div class="ms">Earn + Grid</div>
          </div>
        </div>
        <!-- Motor IA -->
        <div class="card ai-box" style="margin-bottom:12px">
          <div class="ai-lbl">🧠 Decisión Motor IA</div>
          <div class="ai-txt" id="ai-decision">Analizando mercado en tiempo real...</div>
        </div>
        <!-- Log -->
        <div class="card" style="margin-bottom:12px">
          <div class="card-hdr"><span>📋 Actividad</span><span style="width:7px;height:7px;border-radius:50%;background:#3B82F6;display:inline-block;box-shadow:0 0 6px #3B82F6"></span></div>
          <div class="log-box" id="activity-log"></div>
        </div>
      </div>

      <!-- SECCIÓN 1: Señales -->
      <div class="sec" id="s1">
        <div class="card" style="margin-bottom:12px">
          <div class="card-hdr">
            <span>📡 Señales Tiempo Real</span>
            <span id="sig-ts" style="font-size:9px;color:#4B5563"></span>
          </div>
          <div id="signals-list">
            <div style="padding:20px;text-align:center;color:#4B5563;font-size:11px">Cargando señales...</div>
          </div>
        </div>
      </div>
    </div>

    <!-- COLUMNA DERECHA: Chat + Señales desktop -->
    <div>
      <!-- Señales panel (desktop lo muestra aquí también) -->
      <div class="card" style="margin-bottom:12px;display:none" id="signals-desktop">
        <div class="card-hdr"><span>📡 Señales</span><span id="sig-ts2" style="font-size:9px;color:#4B5563"></span></div>
        <div id="signals-list2">
          <div style="padding:20px;text-align:center;color:#4B5563;font-size:11px">Cargando...</div>
        </div>
      </div>
      <!-- CHAT -->
      <div class="card chat-wrap sec on" id="s2">
        <div class="card-hdr">
          <span>💬 Terminal KISHAR AI</span>
          <span id="model-lbl" style="font-size:9px;color:#60A5FA;font-family:'Fira Code',monospace">MULTI-LLM</span>
        </div>
        <div class="chat-msgs" id="chat-msgs">
          <div><div class="mb ai">Entorno operativo inicializado. Soy KISHAR. ¿Qué analizo?</div></div>
        </div>
        <div class="chat-inp">
          <input id="chat-input" type="text" placeholder="Ej: Analiza BTC, ¿debo comprar?" autocomplete="off">
          <button class="send-btn" onclick="sendChat()">
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
/* ═══════════════════════════════════════════════════════════
   KISHAR-BINN AI Dashboard — Vanilla JS reactivo
   Endpoints: /api/state (balance), /api/signals (señales), /chat (IA)
   Refresco: state cada 5s, signals cada 30s
═══════════════════════════════════════════════════════════ */

// ── TradingView Widget ──────────────────────────────────────
let tv=null, curSym='BTCUSDT';
function initTV(sym){
  const c=document.getElementById('tv_chart');
  c.innerHTML='';
  tv=new TradingView.widget({
    autosize:true, symbol:'BINANCE:'+sym, interval:'15',
    timezone:'Etc/UTC', theme:'dark', style:'1', locale:'es',
    enable_publishing:false, backgroundColor:'rgba(14,14,15,1)',
    gridColor:'rgba(255,255,255,0.02)', container_id:'tv_chart',
    toolbar_bg:'rgba(22,22,24,1)', hide_side_toolbar:true,
    // Indicadores por defecto: RSI + Volumen
    studies:['RSI@tv-basicstudies','Volume@tv-basicstudies']
  });
}
setTimeout(()=>initTV(curSym),200);

// ── Tabs móvil ─────────────────────────────────────────────
function st(i){
  [0,1,2].forEach(j=>{
    document.getElementById('s'+j)?.classList.remove('on');
    document.getElementById('n'+j)?.classList.remove('active');
  });
  document.getElementById('s'+i)?.classList.add('on');
  document.getElementById('n'+i)?.classList.add('active');
}

// ── Desktop: mostrar panel señales en columna derecha ──────
if(window.innerWidth>=900){
  document.getElementById('signals-desktop').style.display='block';
}
window.addEventListener('resize',()=>{
  const d=document.getElementById('signals-desktop');
  if(window.innerWidth>=900) d.style.display='block'; else d.style.display='none';
});

// ── Helpers ─────────────────────────────────────────────────
const fmt=v=>{const n=parseFloat(v);return isNaN(n)?'$0.00':'$'+n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:4})};
const fmtPct=v=>{const n=parseFloat(v);return(n>=0?'+':'')+n.toFixed(2)+'%'};
const colorPct=v=>parseFloat(v)>=0?'#10B981':'#f87171';
function addLog(msg,type=''){
  const box=document.getElementById('activity-log');
  const t=new Date().toLocaleTimeString('es-ES',{hour12:false});
  const cls=type==='ok'?'lok':type==='err'?'ler':'';
  box.insertAdjacentHTML('afterbegin',`<div class="le"><span class="lt">[${t}]</span> <span class="${cls}">${msg}</span></div>`);
  // Mantener max 50 entradas en el log
  while(box.children.length>50) box.removeChild(box.lastChild);
}

// ── Fetch Balance (/api/state) ───────────────────────────────
let prevAsset='';
async function fetchState(){
  try{
    const d=await(await fetch('/api/state')).json();
    if(d.total_balance!==undefined){
      document.getElementById('total-balance').textContent=fmt(d.total_balance);
      document.getElementById('free-balance').textContent=fmt(d.usdt_balance);
      document.getElementById('earn-balance').textContent=fmt((d.earn_balance||0)+(d.grid_balance||0));
      document.getElementById('tier-badge').textContent=d.tier||'—';
      const dec=d.last_ai_decision||'Monitoreando...';
      document.getElementById('ai-decision').textContent=dec;
      // Actualizar símbolo activo y gráfico si cambia
      const asset=(d.current_asset||'BTCUSDT').replace(/[^A-Z0-9]/g,'').slice(0,10)||'BTCUSDT';
      document.getElementById('active-sym').textContent=asset;
      if(asset!==prevAsset){
        prevAsset=asset; curSym=asset; initTV(asset);
        addLog('Par activo: '+asset,'ok');
      }
    }
  }catch(e){
    document.getElementById('live-lbl').textContent='Offline';
    document.getElementById('live-lbl').style.color='#f87171';
    addLog('Error sincronizando estado','err');
  }
}
setInterval(fetchState,5000); fetchState();

// ── Fetch Señales (/api/signals) ─────────────────────────────
function buildSigColor(sig){
  return sig==='COMPRA'?'buy':sig==='VENTA'?'sell':'neut';
}
function confColor(c){
  return c>=70?'linear-gradient(90deg,#059669,#10B981)':c>=50?'linear-gradient(90deg,#D97706,#F59E0B)':'#4B5563';
}
function renderSignals(signals, containerId){
  const box=document.getElementById(containerId);
  if(!signals||signals.length===0){
    box.innerHTML='<div style="padding:20px;text-align:center;color:#4B5563;font-size:11px">Sin señales disponibles</div>';
    return;
  }
  // Construir HTML para cada señal
  box.innerHTML=signals.map(s=>`
    <div class="sig-item" onclick="switchSym('${s.symbol}')">
      <div class="sig-top">
        <div style="display:flex;align-items:center;gap:8px">
          <span class="badge ${buildSigColor(s.signal)}">${s.signal}</span>
          <span class="sig-sym">${s.symbol.replace('USDT','')}<span style="color:#374151">/USDT</span></span>
        </div>
        <span class="sig-price">${s.price?.toLocaleString('en-US',{maximumFractionDigits:4})}</span>
      </div>
      <!-- Barra de confianza: indica qué tan fuerte es la señal -->
      <div class="bar-row">
        <div class="bar-lbl"><span>Confianza</span><b style="color:${s.confidence>=70?'#10B981':s.confidence>=50?'#F59E0B':'#9CA3AF'}">${s.confidence?.toFixed(1)}%</b></div>
        <div class="bar-tr"><div class="bar-fi" style="width:${s.confidence}%;background:${confColor(s.confidence)}"></div></div>
      </div>
      <!-- Estadísticas técnicas secundarias -->
      <div class="sig-stats">
        <span>RSI <b style="color:${s.rsi<32?'#10B981':s.rsi>68?'#f87171':'#9CA3AF'}">${s.rsi}</b></span>
        <span>Cambio <b style="color:${colorPct(s.change_pct)}">${fmtPct(s.change_pct)}</b></span>
        <span>Vol <b style="color:${s.volume_ratio>1.5?'#60A5FA':'#6B7280'}">${s.volume_ratio}x</b></span>
        <span>Trend <b style="color:${colorPct(s.trend_pct)}">${fmtPct(s.trend_pct)}</b></span>
      </div>
    </div>`).join('');
}

// Clic en señal cambia el gráfico al par seleccionado
function switchSym(sym){
  curSym=sym; initTV(sym);
  document.getElementById('active-sym').textContent=sym;
  addLog('Gráfico cambiado a '+sym,'ok');
}

async function fetchSignals(){
  try{
    const d=await(await fetch('/api/signals')).json();
    if(d.signals){
      renderSignals(d.signals,'signals-list');
      renderSignals(d.signals,'signals-list2');
      const ts=new Date(d.updated_at*1000).toLocaleTimeString('es-ES',{hour12:false});
      document.getElementById('sig-ts').textContent=ts;
      document.getElementById('sig-ts2').textContent=ts;
      // Log de la mejor señal encontrada
      const top=d.signals[0];
      if(top) addLog(`Mejor oportunidad: ${top.symbol} ${top.signal} (${top.confidence}%)`, top.signal==='COMPRA'?'ok':'');
    }
  }catch(e){addLog('Error cargando señales','err');}
}
setInterval(fetchSignals,30000); fetchSignals();

// ── Chat con IA ──────────────────────────────────────────────
async function sendChat(){
  const inp=document.getElementById('chat-input');
  const box=document.getElementById('chat-msgs');
  const p=inp.value.trim(); if(!p)return; inp.value='';
  // Mostrar mensaje del usuario
  box.insertAdjacentHTML('beforeend',`<div style="display:flex;justify-content:flex-end"><div class="mb usr">${p}</div></div>`);
  // Indicador de carga animado
  const lid='l'+Date.now();
  box.insertAdjacentHTML('beforeend',`<div id="${lid}"><div class="mb ai" style="display:flex;gap:4px">
    <span style="animation:blink 1s infinite;display:inline-block">●</span>
    <span style="animation:blink 1s .3s infinite;display:inline-block">●</span>
    <span style="animation:blink 1s .6s infinite;display:inline-block">●</span>
  </div></div>`);
  box.scrollTop=box.scrollHeight;
  try{
    const r=await(await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p})})).json();
    document.getElementById(lid)?.remove();
    const reply=(r.reply||'Sin respuesta').replace(/\n/g,'<br>').replace(/\*\*(.*?)\*\*/g,'<strong style="color:#fff">$1</strong>');
    box.insertAdjacentHTML('beforeend',`<div><div class="mb ai">${reply}</div></div>`);
    if(r.model)document.getElementById('model-lbl').textContent=r.model;
    addLog('IA respondió via '+r.model,'ok');
  }catch(err){
    document.getElementById(lid)?.remove();
    box.insertAdjacentHTML('beforeend',`<div><div class="mb err">Error de conexión con el orquestador IA.</div></div>`);
    addLog('Error en chat IA','err');
  }
  box.scrollTop=box.scrollHeight;
}
document.getElementById('chat-input').addEventListener('keydown',e=>{if(e.key==='Enter')sendChat()});
</script>
</body>
</html>"""

