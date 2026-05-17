import os
import time
import hashlib
import requests
import logging
from datetime import date
from typing import Dict, Optional

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE LÍMITES DE TOKENS Y TOPES DE USO DIARIO
# ═══════════════════════════════════════════════════════════════
PROVIDER_CONFIG = {
    "groq": {
        "max_tokens": 512,        # Ampliado para análisis más ricos
        "daily_limit": 120,       # Groq tiene límite alto (~14k tokens/día), siendo conservadores
        "cooldown_sec": 3,
        "model": "llama-3.1-8b-instant"
    },
    "gemini": {
        "max_tokens": 512,
        "daily_limit": 15,        # gemini-2.5-flash: cuota gratuita limitada, usar con cuidado
        "cooldown_sec": 20,       # Cooldown alto para no saturar cuota
        "model": "gemini-2.5-flash"  # VERIFICADO: modelo disponible y funcional
    },
    "gemini_lite": {
        "max_tokens": 256,
        "daily_limit": 30,        # gemini-2.5-flash-lite: cuota más amplia
        "cooldown_sec": 12,
        "model": "gemini-2.5-flash-lite"
    },
    "deepseek": {
        "max_tokens": 256,
        "daily_limit": 0,         # DESACTIVADO: saldo insuficiente en cuenta
        "cooldown_sec": 10,
        "model": "deepseek-chat"
    },
    "huggingface": {
        "max_tokens": 256,
        "daily_limit": 40,
        "cooldown_sec": 12,
        "model": "mistralai/Mistral-7B-Instruct-v0.3"
    },
    "ollama": {
        "max_tokens": 512,
        "daily_limit": 999,       # Local, sin límites externos
        "cooldown_sec": 2,
        "model": "llama3.2"
    }
}

# Prompt de sistema ultra-comprimido para trading (reduce tokens de entrada)
SYSTEM_TRADING_PROMPT = (
    "Eres un analista de trading cuantitativo. "
    "Responde en máximo 3 oraciones. "
    "Formato: [SEÑAL: BUY/SELL/HOLD] [RAZÓN] [RIESGO: ALTO/MEDIO/BAJO]."
)


class AIOrchestrator:
    """
    Orquestador de APIs de IA con:
    - Fallback automático entre proveedores
    - Optimización de tokens (max_tokens por proveedor)
    - Topes de uso diario por proveedor
    - Rate limiting (cooldown entre llamadas)
    - Cache de respuestas para prompts similares (evita llamadas duplicadas)
    - Compresión de prompts largos
    """
    
    def __init__(self, api_keys: Dict[str, str]):
        self.api_keys = api_keys
        self.logger = logging.getLogger("AI_Orchestrator")
        # Orden de fallback: Groq (más rápido/generoso) → Gemini Lite → Gemini → HuggingFace → Ollama local
        # DeepSeek eliminado del ciclo activo por saldo insuficiente
        self.fallback_order = ['groq', 'gemini_lite', 'gemini', 'huggingface', 'ollama']
        self.current_index = 0
        self.ollama_base_url = "http://localhost:11434"
        
        # Estado de uso: contadores diarios y timestamps de último uso
        self._usage: Dict[str, Dict] = {
            p: {"count": 0, "last_call": 0.0, "date": str(date.today())}
            for p in ['groq', 'gemini', 'gemini_lite', 'deepseek', 'huggingface', 'ollama']
        }
        
        # Cache simple: hash_del_prompt -> (respuesta, timestamp)
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl_sec = 300  # Respuestas válidas por 5 minutos

    # ─── Utilidades internas ────────────────────────────────────

    def _reset_daily_counters(self):
        """Reinicia contadores si cambia el día."""
        today = str(date.today())
        for p in self._usage:
            if self._usage[p]["date"] != today:
                self._usage[p] = {"count": 0, "last_call": 0.0, "date": today}

    def _can_use(self, provider: str) -> tuple[bool, str]:
        """Verifica si el proveedor puede ser usado (límites y cooldown)."""
        self._reset_daily_counters()
        cfg = PROVIDER_CONFIG.get(provider, {})
        usage = self._usage[provider]
        
        if usage["count"] >= cfg.get("daily_limit", 999):
            return False, f"Límite diario alcanzado ({usage['count']}/{cfg['daily_limit']})"
        
        elapsed = time.time() - usage["last_call"]
        cooldown = cfg.get("cooldown_sec", 5)
        if elapsed < cooldown:
            return False, f"Cooldown activo ({cooldown - elapsed:.1f}s restantes)"
        
        return True, "OK"

    def _register_call(self, provider: str):
        """Registra una llamada exitosa al proveedor."""
        self._usage[provider]["count"] += 1
        self._usage[provider]["last_call"] = time.time()

    def _compress_prompt(self, prompt: str, max_chars: int = 800) -> str:
        """Trunca prompts muy largos para reducir tokens de entrada."""
        if len(prompt) > max_chars:
            self.logger.warning(f"Prompt truncado de {len(prompt)} a {max_chars} chars.")
            return prompt[:max_chars] + "... [truncado]"
        return prompt

    def _get_cache_key(self, prompt: str) -> str:
        return hashlib.md5(prompt.encode()).hexdigest()

    def _check_cache(self, prompt: str) -> Optional[str]:
        key = self._get_cache_key(prompt)
        if key in self._cache:
            resp, ts = self._cache[key]
            if time.time() - ts < self._cache_ttl_sec:
                self.logger.info("Cache hit: reutilizando respuesta previa.")
                return resp
        return None

    def _store_cache(self, prompt: str, response: str):
        key = self._get_cache_key(prompt)
        self._cache[key] = (response, time.time())
        # Limpiar cache si crece demasiado (máx 50 entradas)
        if len(self._cache) > 50:
            oldest = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest]

    # ─── Backends por proveedor ─────────────────────────────────

    def _query_groq(self, prompt: str) -> str:
        key = self.api_keys.get('groq')
        if not key: raise ValueError("No Groq key")
        cfg = PROVIDER_CONFIG["groq"]
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": SYSTEM_TRADING_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": cfg["max_tokens"],
                "temperature": 0.3   # Menos creatividad = más determinista en trading
            },
            timeout=8
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']

    def _query_gemini(self, prompt: str) -> str:
        key = self.api_keys.get('gemini')
        if not key: raise ValueError("No Gemini key")
        cfg = PROVIDER_CONFIG["gemini"]
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['model']}:generateContent?key={key}"
        response = requests.post(
            url,
            json={
                "contents": [{"parts": [{"text": f"{SYSTEM_TRADING_PROMPT}\n\n{prompt}"}]}],
                "generationConfig": {"maxOutputTokens": cfg["max_tokens"], "temperature": 0.3}
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text']

    def _query_gemini_lite(self, prompt: str) -> str:
        """Consulta a gemini-2.5-flash-lite (más rápido, cuota más amplia)"""
        key = self.api_keys.get('gemini')
        if not key: raise ValueError("No Gemini key")
        cfg = PROVIDER_CONFIG["gemini_lite"]
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['model']}:generateContent?key={key}"
        response = requests.post(
            url,
            json={
                "contents": [{"parts": [{"text": f"{SYSTEM_TRADING_PROMPT}\n\n{prompt}"}]}],
                "generationConfig": {"maxOutputTokens": cfg["max_tokens"], "temperature": 0.3}
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text']

    def _query_deepseek(self, prompt: str) -> str:
        key = self.api_keys.get('deepseek')
        if not key: raise ValueError("No Deepseek key")
        cfg = PROVIDER_CONFIG["deepseek"]
        
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": SYSTEM_TRADING_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": cfg["max_tokens"],
                "temperature": 0.3
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']

    def _query_huggingface(self, prompt: str) -> str:
        key = self.api_keys.get('huggingface')
        if not key: raise ValueError("No HF key")
        cfg = PROVIDER_CONFIG["huggingface"]
        
        full_prompt = f"{SYSTEM_TRADING_PROMPT}\n\n{prompt}"
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{cfg['model']}",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "inputs": full_prompt,
                "parameters": {"max_new_tokens": cfg["max_tokens"], "temperature": 0.3}
            },
            timeout=15
        )
        response.raise_for_status()
        res = response.json()
        raw = res[0]['generated_text'] if isinstance(res, list) else res.get('generated_text', '')
        # HuggingFace devuelve el prompt + respuesta. Extraer solo la respuesta.
        return raw.replace(full_prompt, "").strip()

    def _query_ollama(self, prompt: str) -> str:
        cfg = PROVIDER_CONFIG["ollama"]
        response = requests.post(
            f"{self.ollama_base_url}/api/generate",
            json={
                "model": cfg["model"],
                "prompt": f"{SYSTEM_TRADING_PROMPT}\n\n{prompt}",
                "stream": False,
                "options": {"num_predict": cfg["max_tokens"]}
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()['response']

    # ─── Interfaz principal ─────────────────────────────────────

    def ask_ai(self, prompt: str, system_context: str = "") -> tuple[str, str]:
        """
        Consulta la IA con fallback automático, cache y control de límites.
        Retorna: (respuesta, nombre_del_proveedor_usado)
        """
        # Comprimir prompt para reducir consumo de tokens
        compressed = self._compress_prompt(prompt)
        full_prompt = f"{system_context}\n\n{compressed}" if system_context else compressed
        
        # Verificar cache primero
        cached = self._check_cache(full_prompt)
        if cached:
            return cached, "cache"

        # Rotar proveedores con control de límites
        attempts = 0
        start_index = self.current_index
        
        while attempts < len(self.fallback_order):
            provider = self.fallback_order[self.current_index]
            can_use, reason = self._can_use(provider)
            
            if not can_use:
                self.logger.warning(f"[{provider}] Saltando: {reason}")
                self.current_index = (self.current_index + 1) % len(self.fallback_order)
                attempts += 1
                continue
            
            self.logger.info(f"[{provider}] Enviando consulta ({len(full_prompt)} chars)...")
            
            try:
                query_fn = {
                    'groq': self._query_groq,
                    'gemini': self._query_gemini,
                    'gemini_lite': self._query_gemini_lite,
                    'deepseek': self._query_deepseek,
                    'huggingface': self._query_huggingface,
                    'ollama': self._query_ollama
                }.get(provider)
                
                if query_fn is None:
                    self.logger.warning(f"[{provider}] Proveedor desconocido. Saltando.")
                    self.current_index = (self.current_index + 1) % len(self.fallback_order)
                    attempts += 1
                    continue
                
                result = query_fn(full_prompt)
                self._register_call(provider)
                self._store_cache(full_prompt, result)
                
                self.logger.info(
                    f"[{provider}] Éxito. Uso hoy: {self._usage[provider]['count']}"
                    f"/{PROVIDER_CONFIG.get(provider, {}).get('daily_limit', '?')}"
                )
                return result, provider
                
            except Exception as e:
                self.logger.warning(f"[{provider}] Fallo: {str(e)[:120]}. Cambiando...")
                self.current_index = (self.current_index + 1) % len(self.fallback_order)
                attempts += 1
                time.sleep(1)
        
        # En lugar de lanzar excepción, retornar respuesta de contingencia para no bloquear el sistema
        self.logger.error("Todos los proveedores de IA fallaron. Activando respuesta de contingencia local.")
        return "[CONTINGENCIA LOCAL] Mercado en análisis. Sin señales claras. Mantener posición actual.", "fallback_local"

    def get_usage_report(self) -> Dict:
        """Retorna el uso actual de cada proveedor para mostrar en el dashboard."""
        self._reset_daily_counters()
        report = {}
        for p in self.fallback_order:
            cfg = PROVIDER_CONFIG.get(p, {})
            usage = self._usage[p]
            report[p] = {
                "used": usage["count"],
                "limit": cfg.get("daily_limit", "∞"),
                "pct": round(usage["count"] / max(cfg.get("daily_limit", 1), 1) * 100, 1)
            }
        return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Carga segura desde variables de entorno (sin hardcodear)
    from dotenv import load_dotenv
    load_dotenv()
    keys = {
        'gemini': os.getenv('GEMINI_API_KEY', ''),
        'deepseek': os.getenv('DEEPSEEK_API_KEY', ''),
        'groq': os.getenv('GROQ_API_KEY', ''),
        'huggingface': os.getenv('HF_API_KEY', '')
    }
    orchestrator = AIOrchestrator(keys)
    try:
        ans, provider = orchestrator.ask_ai("Analiza el par SOLUSDT. ¿Es buen momento para comprar?")
        print(f"[{provider.upper()}] {ans}")
        print("\nReporte de uso:", orchestrator.get_usage_report())
    except Exception as e:
        print(f"Error fatal: {e}")
