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
        
        # 1. Obtener saldos
        r = req.get(f"{base}/api/v3/account?{qs}&signature={sig}", headers=headers, timeout=8)
        data = r.json()
        balances = [b for b in data.get('balances', []) if float(b['free']) > 0 or float(b['locked']) > 0]
        
        usdt_only = 0.0
        total_balance = 0.0
        
        # 2. Obtener precios para conversión
        prices_req = req.get(f"{base}/api/v3/ticker/price", timeout=8)
        prices_data = prices_req.json()
        
        price_map = {}
        if isinstance(prices_data, list):
            price_map = {item['symbol']: float(item['price']) for item in prices_data if 'symbol' in item}
        
        for b in balances:
            asset = b['asset']
            qty = float(b['free']) + float(b['locked'])
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
    # En la nube: consultar Binance directamente
    if IS_CLOUD:
        return fetch_binance_state()
    # Local: leer el archivo generado por el bot
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            return fetch_binance_state()  # fallback
    return {"total_balance": 0, "usdt_balance": 0, "earn_balance": 0,
            "grid_balance": 0, "tier": "INIT",
            "last_ai_decision": "Iniciando sistema...", "current_asset": "BTCUSDT"}

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    html_content = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>KISHAR-BINN_AI</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
<script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0E0E0F;--surface:#161618;--surface2:#202024;
  --brand:#3B82F6;--brand-light:#60A5FA;
  --money:#10B981;--money-light:#34D399;
  --text:#F3F4F6;--text-muted:#9CA3AF;--text-dim:#4B5563;
  --border:rgba(255,255,255,0.08);
  --radius:12px;
}
html,body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;min-height:100vh;overflow-x:hidden}
body{
  background-image:linear-gradient(rgba(255,255,255,0.015) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(255,255,255,0.015) 1px,transparent 1px);
  background-size:32px 32px;
  padding-bottom:64px; /* espacio para bottom nav en móvil */
}
/* ─ Scrollbar ─ */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:4px}
/* ─ Glassmorphism ─ */
.card{
  background:rgba(22,22,24,0.85);
  border:1px solid var(--border);
  border-radius:var(--radius);
  backdrop-filter:blur(12px);
  transition:border-color .2s;
}
.card:hover{border-color:rgba(59,130,246,0.3)}
/* ─ Layout wrapper ─ */
.wrapper{max-width:1400px;margin:0 auto;padding:12px 12px 0}
/* ─ Header ─ */
header{
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 14px;margin-bottom:12px;
}
.logo{display:flex;align-items:center;gap:10px}
.logo-icon{
  width:38px;height:38px;border-radius:10px;
  background:linear-gradient(135deg,var(--brand),#1d4ed8);
  display:flex;align-items:center;justify-content:center;
  font-weight:700;font-size:15px;color:#fff;flex-shrink:0;
}
.logo-text h1{font-size:16px;font-weight:700;color:#fff;line-height:1.2}
.logo-text p{font-size:10px;color:var(--text-muted)}
.status-pill{
  display:flex;align-items:center;gap:6px;
  background:var(--surface);border:1px solid var(--border);
  padding:5px 10px;border-radius:999px;font-size:11px;color:var(--text-muted);
  white-space:nowrap;
}
.dot{
  width:7px;height:7px;border-radius:50%;background:var(--money);
  box-shadow:0 0 6px var(--money);animation:pulse 2s infinite;
}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
/* ─ Tab bar (desktop) ─ */
.tab-bar{
  display:flex;gap:4px;margin-bottom:12px;
  background:var(--surface);border:1px solid var(--border);
  border-radius:10px;padding:4px;
}
.tab-btn{
  flex:1;padding:7px 10px;border:none;border-radius:7px;
  background:transparent;color:var(--text-muted);
  font-size:11px;font-weight:600;cursor:pointer;
  transition:all .2s;font-family:'Inter',sans-serif;
}
.tab-btn.active{background:var(--brand);color:#fff}
/* ─ Sections ─ */
.section{display:none}
.section.active{display:block}
/* ─ Metrics row (scroll horizontal en móvil) ─ */
.metrics-row{
  display:flex;gap:10px;overflow-x:auto;padding-bottom:4px;margin-bottom:12px;
  scrollbar-width:none;
}
.metrics-row::-webkit-scrollbar{display:none}
.metric-card{
  min-width:140px;flex:1;padding:12px 14px;
}
.metric-label{font-size:9px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
.metric-value{font-size:22px;font-weight:700;color:#fff;line-height:1}
.metric-sub{font-size:10px;margin-top:4px}
.badge{
  display:inline-block;font-size:9px;font-family:'Fira Code',monospace;
  padding:2px 6px;border-radius:4px;
  background:var(--surface2);border:1px solid var(--border);color:var(--text-muted);
}
/* ─ Bars ─ */
.bar-row{margin-bottom:6px}
.bar-header{display:flex;justify-content:space-between;font-size:10px;font-weight:500;margin-bottom:4px;color:var(--text-muted)}
.bar-header span:last-child{font-family:'Fira Code',monospace;color:#fff}
.bar-track{height:5px;background:var(--surface2);border-radius:999px;overflow:hidden}
.bar-fill{height:100%;border-radius:999px;transition:width .5s}
/* ─ Desktop 2-col grid ─ */
@media(min-width:768px){
  body{padding-bottom:0}
  .wrapper{padding:16px 16px 16px}
  .bottom-nav{display:none!important}
  .tab-bar{display:none}
  .section{display:block!important}
  .desktop-grid{display:grid;grid-template-columns:1fr 380px;gap:12px;align-items:start}
  .metrics-row{overflow-x:visible}
  .metric-card{min-width:0}
}
/* ─ AI Decision ─ */
.ai-box{padding:12px 14px;position:relative;overflow:hidden;margin-bottom:12px}
.ai-box::before{
  content:'';position:absolute;left:0;top:0;bottom:0;width:3px;
  background:linear-gradient(to bottom,var(--brand-light),var(--brand));
}
.ai-label{font-size:9px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;display:flex;align-items:center;gap:5px}
.ai-text{font-size:12px;color:#e2e8f0;line-height:1.6;font-weight:500}
/* ─ Log terminal ─ */
.log-box{height:160px;overflow-y:auto;font-size:10px;font-family:'Fira Code',monospace;color:var(--text-muted);padding:10px 12px;background:rgba(0,0,0,0.3);border-radius:0 0 var(--radius) var(--radius)}
.log-header{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border);font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted)}
.log-entry{margin-bottom:4px;line-height:1.4}
.log-time{color:var(--text-dim)}
.log-ok{color:var(--money-light)}
.log-err{color:#f87171}
/* ─ Chart ─ */
.chart-wrap{border-radius:var(--radius);overflow:hidden;height:280px;position:relative;margin-bottom:12px}
@media(min-width:768px){.chart-wrap{height:380px}}
/* ─ Chat ─ */
.chat-wrap{display:flex;flex-direction:column;height:360px;@media(min-width:768px){height:420px}}
.chat-header{padding:10px 14px;border-bottom:1px solid var(--border);background:rgba(22,22,24,0.9)}
.chat-header h3{font-size:13px;font-weight:700;color:#fff}
.chat-model{font-size:9px;color:var(--brand-light);font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-top:2px}
.chat-messages{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
.msg-wrap{display:flex;flex-direction:column;gap:3px}
.msg-wrap.user{align-items:flex-end}
.msg-sender{font-size:9px;font-weight:600;color:var(--text-dim);padding:0 4px;letter-spacing:.06em}
.msg-bubble{
  font-size:12px;line-height:1.5;padding:8px 12px;
  border-radius:12px;max-width:88%;word-break:break-word;
}
.msg-bubble.ai{background:var(--surface);border:1px solid var(--border);color:#e2e8f0;border-top-left-radius:3px}
.msg-bubble.user-b{background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.25);color:#bfdbfe;border-top-right-radius:3px}
.msg-bubble.error{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.25);color:#fca5a5}
.chat-input-row{padding:8px 10px;border-top:1px solid var(--border);background:rgba(22,22,24,0.8);display:flex;gap:8px;align-items:center}
.chat-input-row input{
  flex:1;background:var(--bg);border:1px solid var(--border);
  border-radius:8px;padding:9px 12px;font-size:12px;color:#fff;
  font-family:'Inter',sans-serif;outline:none;min-width:0;
}
.chat-input-row input:focus{border-color:rgba(59,130,246,0.5)}
.chat-input-row input::placeholder{color:var(--text-dim)}
.send-btn{
  width:34px;height:34px;border-radius:8px;border:none;flex-shrink:0;
  background:var(--brand);color:#fff;cursor:pointer;
  display:flex;align-items:center;justify-content:center;transition:background .2s;
}
.send-btn:hover{background:var(--brand-light)}
.bounce-dot{width:6px;height:6px;border-radius:50%;background:var(--brand-light);animation:bounce .8s ease-in-out infinite}
.bounce-dot:nth-child(2){animation-delay:.15s}
.bounce-dot:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
/* ─ Bottom nav (solo móvil) ─ */
.bottom-nav{
  position:fixed;bottom:0;left:0;right:0;z-index:100;
  display:flex;
  background:rgba(22,22,24,0.97);
  border-top:1px solid var(--border);
  backdrop-filter:blur(16px);
  height:60px;
}
.nav-item{
  flex:1;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:3px;border:none;background:transparent;
  color:var(--text-dim);cursor:pointer;font-size:10px;font-weight:600;
  font-family:'Inter',sans-serif;transition:color .2s;
}
.nav-item.active{color:var(--brand-light)}
.nav-item svg{width:20px;height:20px}
</style>
</head>
<body>
<div class="wrapper">
  <!-- Header -->
  <header class="card">
    <div class="logo">
      <div class="logo-icon">KB</div>
      <div class="logo-text">
        <h1>KISHAR-BINN_AI</h1>
        <p>Institutional Quant · Core v2.0</p>
      </div>
    </div>
    <div class="status-pill">
      <span class="dot"></span>
      <span id="sync-status">Live</span>
    </div>
  </header>

  <!-- Tab bar (desktop only via CSS) -->
  <div class="tab-bar">
    <button class="tab-btn active" onclick="showTab('overview')">Resumen</button>
    <button class="tab-btn" onclick="showTab('chart')">Gráfico</button>
    <button class="tab-btn" onclick="showTab('chat')">Terminal IA</button>
  </div>

  <!-- Desktop grid wrapper -->
  <div class="desktop-grid">

    <!-- LEFT COLUMN -->
    <div>
      <!-- Section: Overview -->
      <div class="section active" id="sec-overview">
        <!-- Metrics row (scrollable on mobile) -->
        <div class="metrics-row">
          <div class="card metric-card">
            <div class="metric-label">Net Worth</div>
            <div class="metric-value" id="total-balance">$0.00</div>
            <div class="metric-sub" style="color:var(--money-light)">▲ Capital Global</div>
          </div>
          <div class="card metric-card">
            <div class="metric-label">Libre (USDT)</div>
            <div class="metric-value" id="free-balance">$0.00</div>
            <div class="metric-sub" style="color:var(--text-muted)">Disponible</div>
          </div>
          <div class="card metric-card">
            <div class="metric-label">Tier <span class="badge" id="tier-badge">—</span></div>
            <div class="bar-row" style="margin-top:10px">
              <div class="bar-header"><span>Earn</span><span id="earn-balance">$0.00</span></div>
              <div class="bar-track"><div class="bar-fill" style="background:#6366f1;width:70%"></div></div>
            </div>
            <div class="bar-row" style="margin-top:8px">
              <div class="bar-header"><span>Grid</span><span id="grid-balance">$0.00</span></div>
              <div class="bar-track"><div class="bar-fill" style="background:var(--brand);width:50%"></div></div>
            </div>
          </div>
        </div>

        <!-- AI Decision -->
        <div class="card ai-box">
          <div class="ai-label">
            <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="color:var(--brand-light)"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
            Motor de Decisión IA
          </div>
          <div class="ai-text" id="ai-decision">Esperando análisis del mercado...</div>
        </div>

        <!-- Log terminal -->
        <div class="card" style="margin-bottom:12px">
          <div class="log-header">
            <span>Log Operaciones</span>
            <span style="width:7px;height:7px;border-radius:50%;background:var(--brand);display:inline-block;box-shadow:0 0 6px var(--brand)"></span>
          </div>
          <div class="log-box" id="activity-log"></div>
        </div>
      </div>

      <!-- Section: Chart -->
      <div class="section" id="sec-chart">
        <div class="card chart-wrap" id="tv_chart_container"></div>
      </div>
    </div>

    <!-- RIGHT COLUMN: Chat -->
    <div class="section active" id="sec-chat">
      <div class="card chat-wrap">
        <div class="chat-header">
          <h3>Terminal Kishar</h3>
          <div class="chat-model" id="chat-model-badge">LLM CONECTANDO...</div>
        </div>
        <div class="chat-messages" id="chat-messages">
          <div class="msg-wrap">
            <span class="msg-sender">KISHAR-BINN</span>
            <div class="msg-bubble ai">Entorno operativo inicializado. Monitoreando riesgo y capital. Ingresa comandos.</div>
          </div>
        </div>
        <div class="chat-input-row">
          <input id="chat-input" type="text" placeholder="Ej: Analiza SOL..." autocomplete="off">
          <button class="send-btn" onclick="sendChat(event)">
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
          </button>
        </div>
      </div>
    </div>

  </div><!-- end desktop-grid -->
</div><!-- end wrapper -->

<!-- Bottom Nav (mobile only) -->
<nav class="bottom-nav">
  <button class="nav-item active" id="nav-overview" onclick="mobileTab('overview')">
    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
    Resumen
  </button>
  <button class="nav-item" id="nav-chart" onclick="mobileTab('chart')">
    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"/></svg>
    Gráfico
  </button>
  <button class="nav-item" id="nav-chat" onclick="mobileTab('chat')">
    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
    Terminal
  </button>
</nav>

<script>
// ─ TradingView ─
let tvWidget=null, currentSymbol="BTCUSDT";
function initTV(sym){
  if(tvWidget)tvWidget.remove();
  tvWidget=new TradingView.widget({autosize:true,symbol:"BINANCE:"+sym,interval:"15",timezone:"Etc/UTC",theme:"dark",style:"1",locale:"es",enable_publishing:false,backgroundColor:"transparent",gridColor:"rgba(255,255,255,0.02)",container_id:"tv_chart_container",toolbar_bg:"transparent",hide_side_toolbar:true});
}
// Init chart after small delay so container is visible
setTimeout(()=>initTV(currentSymbol),100);

// ─ Tabs (desktop) ─
function showTab(t){
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  event.target.classList.add('active');
  if(t==='overview'){document.getElementById('sec-overview').classList.add('active');document.getElementById('sec-chart').classList.remove('active');}
  else if(t==='chart'){document.getElementById('sec-chart').classList.add('active');document.getElementById('sec-overview').classList.remove('active');}
}

// ─ Mobile bottom nav ─
function mobileTab(t){
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  document.getElementById('nav-'+t).classList.add('active');
  document.querySelectorAll('.section').forEach(s=>s.style.display='none');
  if(t==='overview'){document.getElementById('sec-overview').style.display='block';}
  else if(t==='chart'){document.getElementById('sec-chart').style.display='block';if(!tvWidget)initTV(currentSymbol);}
  else if(t==='chat'){document.getElementById('sec-chat').style.display='block';}
}

// ─ State polling ─
let isFirstLoad=true;
function fmt(v){const n=parseFloat(v);return isNaN(n)?'$0.00':'$'+n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:4});}
function addLog(msg,type='info'){
  const box=document.getElementById('activity-log');
  const t=new Date().toLocaleTimeString('es-ES',{hour12:false});
  const cls=type==='success'?'log-ok':type==='error'?'log-err':'';
  box.insertAdjacentHTML('afterbegin',`<div class="log-entry"><span class="log-time">[${t}]</span> <span class="${cls}">${msg}</span></div>`);
}
async function fetchState(){
  try{
    const d=await(await fetch('/api/state')).json();
    if(d.total_balance!==undefined){
      document.getElementById('total-balance').innerText=fmt(d.total_balance);
      document.getElementById('free-balance').innerText=fmt(d.usdt_balance);
      document.getElementById('earn-balance').innerText=fmt(d.earn_balance);
      document.getElementById('grid-balance').innerText=fmt(d.grid_balance);
      document.getElementById('tier-badge').innerText=d.tier||'—';
      const dec=document.getElementById('ai-decision');
      const nd=d.last_ai_decision||'Analizando...';
      if(dec.innerText!==nd){dec.innerText=nd;addLog('Motor IA actualizó directrices','success');}
      const asset=d.current_asset?.match(/^[A-Z0-9]{5,10}/)?.[0]||'BTCUSDT';
      if(asset!==currentSymbol){currentSymbol=asset;if(tvWidget)initTV(currentSymbol);addLog('Par actualizado: '+currentSymbol);}
      if(isFirstLoad){addLog('Sincronización completada','success');isFirstLoad=false;}
    }
  }catch(e){
    document.getElementById('sync-status').innerText='Offline';
    document.getElementById('sync-status').style.color='#f87171';
  }
}
setInterval(fetchState,3000);fetchState();

// ─ Chat ─
async function sendChat(e){
  if(e)e.preventDefault();
  const inp=document.getElementById('chat-input');
  const box=document.getElementById('chat-messages');
  const p=inp.value.trim();if(!p)return;
  inp.value='';
  box.innerHTML+=`<div class="msg-wrap user"><span class="msg-sender">TÚ</span><div class="msg-bubble user-b">${p}</div></div>`;
  const lid='l'+Date.now();
  box.innerHTML+=`<div id="${lid}" class="msg-wrap"><div class="msg-bubble ai" style="display:flex;gap:4px;align-items:center"><div class="bounce-dot"></div><div class="bounce-dot"></div><div class="bounce-dot"></div></div></div>`;
  box.scrollTop=box.scrollHeight;
  try{
    const r=await(await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p})})).json();
    document.getElementById(lid)?.remove();
    const reply=r.reply.replace(/\\n/g,'<br>').replace(/\\*\\*(.*?)\\*\\*/g,'<strong style="color:#fff">$1</strong>');
    box.innerHTML+=`<div class="msg-wrap"><span class="msg-sender">KISHAR-BINN</span><div class="msg-bubble ai">${reply}</div></div>`;
    if(r.model)document.getElementById('chat-model-badge').innerText=r.model;
  }catch(err){
    document.getElementById(lid)?.remove();
    box.innerHTML+=`<div class="msg-wrap"><div class="msg-bubble error">Error de conexión con el orquestador.</div></div>`;
  }
  box.scrollTop=box.scrollHeight;
}
document.getElementById('chat-input').addEventListener('keydown',e=>{if(e.key==='Enter')sendChat(e);});
</script>
</body>
</html>"""
    return HTMLResponse(content=html_content)

class ChatRequest(BaseModel):
    prompt: str

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    prompt = request.prompt
    
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            
    context = f"Eres KISHAR-BINN_AI, el orquestador cuantitativo institucional. Estado actual: {json.dumps(state)}. Responde de forma técnica, analítica pero motivadora en un máximo de 2 párrafos cortos."
    
    try:
        response, active_provider = orchestrator.ask_ai(prompt, system_context=context)
        usage = orchestrator.get_usage_report().get(active_provider, {})
        model_label = f"{active_provider.upper()} [{usage.get('used',0)}/{usage.get('limit','?')} calls]"
        return {"reply": response, "model": model_label}
    except Exception as e:
        return {"reply": f"Error del sistema IA: {str(e)}", "model": "ERROR"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
