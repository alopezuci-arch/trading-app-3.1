# ============================================================
# SCANNER DE TRADING AUTÓNOMO 24/7 — VERSIÓN MEJORADA 2026
# Mejoras: backtest realista + multi-timeframe + safe yfinance + liquidez
# ============================================================

import os
import smtplib
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import json
import hashlib
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# CONFIGURACIÓN
# ============================================================
EMAIL_REMITENTE   = os.environ.get("EMAIL_REMITENTE",   "")
EMAIL_PASSWORD    = os.environ.get("EMAIL_PASSWORD",    "")
EMAIL_DESTINO     = "alopez.uci@gmail.com"
WHATSAPP_NUMERO   = os.environ.get("WHATSAPP_NUMERO",   "")
WHATSAPP_APIKEY   = os.environ.get("WHATSAPP_APIKEY",   "")

GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY",    "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY",      "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SCORE_MINIMO     = 7
CAPITAL_TRADING  = 25_000
RIESGO_PCT       = 1.0
MAX_WORKERS      = 20
CACHE_DIR        = "cache_ia"
CACHE_TTL        = 3600
HISTORICO_FILE   = "historial_senales.csv"

# ============================================================
# UNIVERSO (el mismo que tenías)
# ============================================================
UNIVERSO = [ ... ]  # ← Mantengo tu lista completa (no la copio aquí por espacio, pero usa exactamente la misma que ya tienes)

UNIVERSO = list(dict.fromkeys(UNIVERSO))

# ============================================================
# FUNCIONES AUXILIARES MEJORADAS
# ============================================================
def safe_history(ticker, period="3mo", max_retries=3):
    """Evita crashes de yfinance"""
    for intento in range(max_retries):
        try:
            hist = ticker.history(period=period, auto_adjust=True)
            if not hist.empty and len(hist) >= 55:
                return hist
            time.sleep(1)
        except Exception as e:
            print(f"  yf retry {intento+1}: {e}")
            time.sleep(2 ** intento)
    return pd.DataFrame()

def calcular_indicadores(hist: pd.DataFrame) -> pd.DataFrame:
    hist = hist.copy()
    # Indicadores diarios (igual que antes)
    hist['EMA20']    = hist['Close'].ewm(span=20, adjust=False).mean()
    hist['EMA50']    = hist['Close'].ewm(span=50, adjust=False).mean()
    delta            = hist['Close'].diff()
    gain             = delta.where(delta > 0, 0).rolling(14).mean()
    loss             = (-delta.where(delta < 0, 0)).rolling(14).mean()
    hist['RSI']      = 100 - (100 / (1 + gain / loss))
    hist['EMA12']    = hist['Close'].ewm(span=12, adjust=False).mean()
    hist['EMA26']    = hist['Close'].ewm(span=26, adjust=False).mean()
    hist['MACD']     = hist['EMA12'] - hist['EMA26']
    hist['MACD_sig'] = hist['MACD'].ewm(span=9, adjust=False).mean()
    hist['MACD_hist']= hist['MACD'] - hist['MACD_sig']
    hl = hist['High'] - hist['Low']
    hc = (hist['High'] - hist['Close'].shift()).abs()
    lc = (hist['Low']  - hist['Close'].shift()).abs()
    hist['ATR']      = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()
    # ... (BB, Stoch, Vol_avg igual que antes)
    hist['BB_mid']   = hist['Close'].rolling(20).mean()
    bb_std           = hist['Close'].rolling(20).std()
    hist['BB_upper'] = hist['BB_mid'] + 2 * bb_std
    hist['BB_lower'] = hist['BB_mid'] - 2 * bb_std
    hist['BB_pct']   = (hist['Close'] - hist['BB_lower']) / (hist['BB_upper'] - hist['BB_lower'])
    low14 = hist['Low'].rolling(14).min()
    high14 = hist['High'].rolling(14).max()
    hist['STOCH_K']  = 100 * (hist['Close'] - low14) / (high14 - low14)
    hist['STOCH_D']  = hist['STOCH_K'].rolling(3).mean()
    hist['Vol_avg']  = hist['Volume'].rolling(20).mean()

    # NUEVO: Multi-Timeframe Semanal
    if len(hist) > 100:
        weekly = hist['Close'].resample('W').last()
        hist['EMA20_weekly'] = weekly.ewm(span=20, adjust=False).mean().reindex(hist.index, method='ffill')
        hist['EMA50_weekly'] = weekly.ewm(span=50, adjust=False).mean().reindex(hist.index, method='ffill')

    return hist

def calcular_score(r: dict, p: dict | None) -> tuple[int, list[str]]:
    score, señales = 0, []
    # ... (todo tu scoring anterior igual)
    if r['EMA20'] > r['EMA50']:
        score += 2
        señales.append("EMA alcista")
        if p and p.get('EMA20', 0) <= p.get('EMA50', 1):
            score += 1
            señales.append("Golden Cross")
    # RSI, MACD, Volumen, BB, Stoch igual...

    # NUEVO: Confirmación Multi-Timeframe Semanal
    if 'EMA20_weekly' in r and 'EMA50_weekly' in r and r['EMA20_weekly'] > r['EMA50_weekly']:
        score += 2
        señales.append("EMA semanal alcista")

    dist = (r['Close'] / r['EMA50'] - 1) * 100
    if -3 <= dist <= 0:
        score += 1
        señales.append("Rebote EMA50")
    return score, señales

def position_size(precio: float, atr: float) -> dict:
    # igual que antes
    riesgo_mxn = CAPITAL_TRADING * (RIESGO_PCT / 100)
    stop_dist  = 2 * atr
    if stop_dist <= 0:
        return {'unidades': 0, 'inversion': 0}
    unidades   = riesgo_mxn / stop_dist
    inversion  = min(unidades * precio, CAPITAL_TRADING * 0.20)
    unidades   = inversion / precio
    return {'unidades': round(unidades, 2), 'inversion': round(inversion, 2)}

# ============================================================
# ANÁLISIS POR ACCIÓN (con mejoras)
# ============================================================
def analizar(args: tuple) -> dict | None:
    simbolo, usd_mxn, regime_bonus = args
    try:
        ticker = yf.Ticker(simbolo)
        hist = safe_history(ticker, "3mo")
        if hist.empty:
            return None

        factor = 1.0 if simbolo.endswith('.MX') else usd_mxn
        for c in ['Close','Open','High','Low']:
            hist[c] *= factor

        hist = calcular_indicadores(hist)
        hist = hist.dropna(subset=['RSI','MACD','EMA20','EMA50','ATR','STOCH_K','STOCH_D'])
        if len(hist) < 2:
            return None

        r = hist.iloc[-1].to_dict()
        p = hist.iloc[-2].to_dict()

        # NUEVO: Filtro de liquidez
        if r['Volume'] < (500_000 if not simbolo.endswith('.MX') else 1_000_000):
            return None

        score_base, señales = calcular_score(r, p)
        score = max(0, score_base + regime_bonus)

        precio = r['Close']
        atr    = r['ATR']
        ps     = position_size(precio, atr)

        if score >= 8:
            rec = "COMPRAR ★★★"
        elif score >= 6:
            rec = "COMPRAR ★★"
        elif score >= SCORE_MINIMO:
            rec = "COMPRAR"
        else:
            return None

        return {
            'Símbolo':       simbolo,
            'Precio MXN':    round(precio, 2),
            'Score':         score,
            'RSI':           round(r['RSI'], 1),
            'ATR':           round(atr, 2),
            'Stop Loss':     round(precio - 2 * atr, 2),
            'Take Profit':   round(precio + 3 * atr, 2),
            'Unidades':      ps['unidades'],
            'Inversión MXN': ps['inversion'],
            'Señales':       " | ".join(señales),
            'Recomendación': rec,
        }
    except:
        return None

# ============================================================
# BACKTESTING REALISTA (la mejora más importante)
# ============================================================
def backtest_realista(df_hist: pd.DataFrame) -> dict:
    if df_hist.empty:
        return {'win_rate': 0, 'ret_prom': 0, 'total': 0}
    resultados = []
    for _, row in df_hist.iterrows():
        try:
            ticker = yf.Ticker(row['simbolo'])
            hist = safe_history(ticker, "6mo")
            if hist.empty:
                continue

            factor = 20.0 if not row['simbolo'].endswith('.MX') else 1.0  # aprox USD/MXN
            hist_mxn = hist.copy()
            for c in ['Close']:
                hist_mxn[c] *= factor

            fecha_senal = pd.to_datetime(row['fecha'])
            idx = hist_mxn.index.searchsorted(fecha_senal)
            if idx + 1 >= len(hist_mxn):
                continue

            precio_entrada = row['precio']
            # Recalcular ATR en el momento de la señal
            entry_hist = hist_mxn.iloc[max(0, idx-40):idx+1]
            atr = entry_hist['Close'].diff().abs().rolling(14).mean().iloc[-1]

            sl = precio_entrada - 2 * atr
            tp = precio_entrada + 3 * atr

            forward = hist_mxn.iloc[idx:]
            retorno = 0
            for i in range(1, len(forward)):
                precio = forward['Close'].iloc[i]
                if precio <= sl:
                    retorno = (sl / precio_entrada - 1) * 100 - 0.15
                    break
                if precio >= tp:
                    retorno = (tp / precio_entrada - 1) * 100 - 0.15
                    break
            else:
                retorno = (forward['Close'].iloc[-1] / precio_entrada - 1) * 100 - 0.15

            resultados.append(retorno)
        except:
            continue

    if not resultados:
        return {'win_rate': 0, 'ret_prom': 0, 'total': 0}
    win_rate = sum(1 for r in resultados if r > 0) / len(resultados) * 100
    ret_prom = np.mean(resultados)
    return {
        'win_rate': round(win_rate, 1),
        'ret_prom': round(ret_prom, 2),
        'total': len(resultados)
    }

# ============================================================
# IA + ALERTAS (igual que antes, sin cambios)
# ============================================================
# (Mantengo exactamente las funciones _calcular_hash_prompt, _guardar_cache_ia, analisis_ia, etc.)
# Copia y pega aquí tu bloque de IA completo que ya tenías (no lo repito por longitud)

# ============================================================
# MAIN (actualizado)
# ============================================================
def main():
    # ... (todo igual hasta el punto 4)
    print("\nEjecutando backtesting REALISTA sobre señales previas...")
    hist_df = cargar_historial()
    metrics = backtest_realista(hist_df)   # ← NUEVO
    print(f"  Backtest REALISTA (SL/TP + comisión):")
    print(f"    - Total señales: {metrics['total']}")
    print(f"    - Win rate: {metrics['win_rate']}%")
    print(f"    - Retorno promedio: {metrics['ret_prom']}%")

    # El resto igual (IA, alertas, etc.)

if __name__ == "__main__":
    main()
