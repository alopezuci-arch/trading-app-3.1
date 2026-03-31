# ============================================================
# SCANNER DE TRADING AUTÓNOMO 24/7 — VERSIÓN MEJORADA 2026
# Mejoras: safe yfinance + multi-timeframe + backtest realista + liquidez
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
# UNIVERSO COMPLETO (exacto al que tenías)
# ============================================================
UNIVERSO = [
    'AAPL', 'MSFT', 'AMZN', 'NVDA', 'META', 'GOOGL', 'GOOG', 'BRK-B', 'JPM', 'V',
    'JNJ', 'WMT', 'PG', 'UNH', 'HD', 'DIS', 'MA', 'BAC', 'XOM', 'CVX',
    'KO', 'PEP', 'ADBE', 'CRM', 'NFLX', 'TMO', 'ABT', 'ACN', 'AMD', 'INTC',
    'CMCSA', 'TXN', 'QCOM', 'COST', 'NKE', 'MRK', 'ABBV', 'LLY', 'PFE', 'BMY',
    'CVS', 'HON', 'UPS', 'BA', 'CAT', 'GE', 'IBM', 'GS', 'SPGI', 'MS',
    'PLD', 'LMT', 'MDT', 'ISRG', 'BLK', 'AMGN', 'GILD', 'FISV', 'SYK', 'ZTS',
    'T', 'VZ', 'NEE', 'DUK', 'SO', 'MO', 'PM', 'MDLZ', 'SBUX', 'MCD',
    'LOW', 'TGT', 'TJX', 'ORCL', 'NOW', 'INTU', 'BKNG', 'UBER', 'TSLA', 'AVGO',
    'ADBE', 'AMD', 'AMGN', 'AMZN', 'ASML', 'AVGO', 'BIIB', 'BKNG', 'CDNS', 'CHTR',
    'CMCSA', 'COST', 'CSCO', 'CSX', 'CTAS', 'DXCM', 'EA', 'EBAY', 'EXC', 'FANG',
    'FAST', 'FTNT', 'GILD', 'GOOGL', 'GOOG', 'HON', 'IDXX', 'ILMN', 'INTC', 'INTU',
    'ISRG', 'KDP', 'KLAC', 'LRCX', 'LULU', 'MAR', 'MELI', 'META', 'MNST', 'MSFT',
    'MU', 'NFLX', 'NVDA', 'NXPI', 'ODFL', 'ORLY', 'PANW', 'PAYX', 'PCAR', 'PDD',
    'PEP', 'QCOM', 'REGN', 'ROST', 'SBUX', 'SGEN', 'SIRI', 'SNPS', 'SPLK', 'SWKS',
    'TCOM', 'TEAM', 'TMUS', 'TSLA', 'TTD', 'TXN', 'VRTX', 'WBA', 'WDAY', 'XEL',
    'ZM', 'ZS', 'SAN.MC', 'BBVA.MC', 'TEF.MC', 'ITX.MC', 'IBE.MC', 'FER.MC',
    'ENG.MC', 'ACS.MC', 'REP.MC', 'AENA.MC', 'CLNX.MC', 'GRF.MC', 'MTS.MC',
    'MAP.MC', 'MEL.MC', 'CABK.MC', 'ELE.MC', 'IAG.MC', 'ANA.MC', 'VIS.MC',
    'CIE.MC', 'LOG.MC', 'ACX.MC', 'WALMEX.MX', 'GMEXICOB.MX', 'CEMEXCPO.MX',
    'FEMSAUBD.MX', 'AMXL.MX', 'KOFUBL.MX', 'GFNORTEO.MX', 'BBAJIOO.MX',
    'ALFA.MX', 'ALPEKA.MX', 'ASURB.MX', 'GAPB.MX', 'OMAB.MX', 'AC.MX',
    'GCC.MX', 'LALA.MX', 'MEGA.MX', 'PINFRA.MX', 'TLEVISACPO.MX', 'VESTA.MX',
    'GRUMA.MX', 'HERDEZ.MX', 'CUERVO.MX', 'ORBIA.MX', 'XLK','XLV','XLF','XLE',
    'XLI','XLY','XLP','XLU','XLB','XLRE','XLC','SOXX','ARKK','ARKG','ARKW','ARKF',
    'CIBR','ROBO','ICLN','TAN','LIT','JETS','XHB','KRE','IBB','SPY','QQQ','IWM',
    'DIA','VTI','GLD','SLV','USO','UNG','DBC','NEM','GOLD','FCX','DDOG','NET',
    'CRWD','ZS','BILL','DUOL','CELH','SMCI','HUBS','MNDY','APPN','PCTY','FIVN',
    'RELY','PATH','SMAR','JAMF','EXAS','NVCR','FATE','RXRX','AFRM','UPST','HOOD',
    'SQ','SOFI','NU','PLUG','CHPT','RIVN','LCID','KTOS','RKLB','ACHR','EWZ','EWJ',
    'FXI','KWEB','EWY','EWT','EWH','EWA','EWC','EWG','EWQ','EWU','VWO','EEM','INDA','EWX'
]

UNIVERSO = list(dict.fromkeys(UNIVERSO))

# ============================================================
# FUNCIONES AUXILIARES MEJORADAS
# ============================================================
def safe_history(ticker, period="3mo", max_retries=3):
    for intento in range(max_retries):
        try:
            hist = ticker.history(period=period, auto_adjust=True)
            if not hist.empty and len(hist) >= 55:
                return hist
            time.sleep(1)
        except Exception:
            time.sleep(2 ** intento)
    return pd.DataFrame()

def calcular_indicadores(hist: pd.DataFrame) -> pd.DataFrame:
    hist = hist.copy()
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

    # Multi-Timeframe Semanal
    if len(hist) > 100:
        weekly = hist['Close'].resample('W').last()
        hist['EMA20_weekly'] = weekly.ewm(span=20, adjust=False).mean().reindex(hist.index, method='ffill')
        hist['EMA50_weekly'] = weekly.ewm(span=50, adjust=False).mean().reindex(hist.index, method='ffill')
    return hist

def calcular_score(r: dict, p: dict | None) -> tuple[int, list[str]]:
    score, señales = 0, []
    if r['EMA20'] > r['EMA50']:
        score += 2
        señales.append("EMA alcista")
        if p and p.get('EMA20', 0) <= p.get('EMA50', 1):
            score += 1
            señales.append("Golden Cross")
    rsi = r['RSI']
    if 45 <= rsi <= 65:
        score += 2
        señales.append(f"RSI {rsi:.0f} óptimo")
    elif 30 <= rsi < 45:
        score += 1
        señales.append(f"RSI {rsi:.0f} rebote")
    if r['MACD'] > r['MACD_sig']:
        score += 2
        señales.append("MACD positivo")
        if p and p.get('MACD', 1) <= p.get('MACD_sig', 0):
            score += 1
            señales.append("Cruce MACD")
    if r['Volume'] > r['Vol_avg'] * 1.2:
        score += 1
        señales.append("Volumen alto")
    bp = r.get('BB_pct')
    if bp is not None and not np.isnan(bp):
        if bp < 0.2:
            score += 2
            señales.append("Banda BB inferior")
        elif bp < 0.4:
            score += 1
            señales.append("BB zona baja")
    sk, sd = r.get('STOCH_K', np.nan), r.get('STOCH_D', np.nan)
    if not (np.isnan(sk) or np.isnan(sd)) and 20 <= sk <= 50 and sk > sd:
        score += 1
        señales.append(f"Stoch {sk:.0f}")
    dist = (r['Close'] / r['EMA50'] - 1) * 100
    if -3 <= dist <= 0:
        score += 1
        señales.append("Rebote EMA50")

    # Confirmación Multi-Timeframe Semanal
    if 'EMA20_weekly' in r and 'EMA50_weekly' in r and r['EMA20_weekly'] > r['EMA50_weekly']:
        score += 2
        señales.append("EMA semanal alcista")

    return score, señales

def position_size(precio: float, atr: float) -> dict:
    riesgo_mxn = CAPITAL_TRADING * (RIESGO_PCT / 100)
    stop_dist  = 2 * atr
    if stop_dist <= 0:
        return {'unidades': 0, 'inversion': 0}
    unidades   = riesgo_mxn / stop_dist
    inversion  = min(unidades * precio, CAPITAL_TRADING * 0.20)
    unidades   = inversion / precio
    return {'unidades': round(unidades, 2), 'inversion': round(inversion, 2)}

def obtener_market_regime() -> dict:
    try:
        sp = yf.Ticker("^GSPC").history(period="1y")
        if sp.empty or len(sp) < 200:
            return {'regime': 'DESCONOCIDO', 'score_bonus': 0, 'precio': 0, 'ema200': 0, 'ret_1m': 0, 'rsi_sp500': 0, 'descripcion': 'Sin datos'}
        precio = sp['Close'].iloc[-1]
        ema200 = sp['Close'].ewm(span=200).mean().iloc[-1]
        ema50  = sp['Close'].ewm(span=50).mean().iloc[-1]
        ret_1m = (precio / sp['Close'].iloc[-20] - 1) * 100 if len(sp) >= 20 else 0
        delta = sp['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_sp500 = 100 - (100 / (1 + rs)).iloc[-1] if not loss.empty else 50
        if precio > ema200 and precio > ema50 and ema50 > ema200:
            return {'regime': 'ALCISTA', 'score_bonus': 0, 'precio': precio, 'ema200': ema200, 'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1), 'descripcion': 'S&P 500 sobre EMA50 y EMA200 — condiciones favorables'}
        elif precio > ema200:
            return {'regime': 'LATERAL', 'score_bonus': -1, 'precio': precio, 'ema200': ema200, 'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1), 'descripcion': 'Ser selectivo'}
        else:
            return {'regime': 'BAJISTA', 'score_bonus': -3, 'precio': precio, 'ema200': ema200, 'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1), 'descripcion': 'Mercado bajista — evitar nuevas compras'}
    except:
        return {'regime': 'DESCONOCIDO', 'score_bonus': 0, 'precio': 0, 'ema200': 0, 'ret_1m': 0, 'rsi_sp500': 0, 'descripcion': 'Error al obtener datos'}

# ============================================================
# ANÁLISIS POR ACCIÓN
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

        # Filtro de liquidez
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
# HISTORIAL Y BACKTESTING REALISTA
# ============================================================
def cargar_historial() -> pd.DataFrame:
    if os.path.exists(HISTORICO_FILE):
        df = pd.read_csv(HISTORICO_FILE)
        df['fecha'] = pd.to_datetime(df['fecha'])
        return df
    return pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales'])

def guardar_senal_en_historial(senal: dict, fecha: str):
    df = cargar_historial()
    nueva = pd.DataFrame([{
        'fecha': fecha,
        'simbolo': senal['Símbolo'],
        'score': senal['Score'],
        'precio': senal['Precio MXN'],
        'recomendacion': senal['Recomendación'],
        'señales': senal.get('Señales', '')
    }])
    df = pd.concat([df, nueva], ignore_index=True)
    df['fecha'] = pd.to_datetime(df['fecha'])
    cutoff = datetime.now() - timedelta(days=90)
    df = df[df['fecha'] >= cutoff]
    df.to_csv(HISTORICO_FILE, index=False)

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
            factor = 20.0 if not row['simbolo'].endswith('.MX') else 1.0
            hist_mxn = hist.copy()
            hist_mxn['Close'] *= factor

            fecha_senal = pd.to_datetime(row['fecha'])
            idx = hist_mxn.index.searchsorted(fecha_senal)
            if idx + 1 >= len(hist_mxn):
                continue

            precio_entrada = row['precio']
            atr = hist_mxn['Close'].diff().abs().rolling(14).mean().iloc[idx]
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
# IA CON CACHÉ
# ============================================================
def _calcular_hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()

def _guardar_cache_ia(prompt: str, respuesta: str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = _calcular_hash_prompt(prompt)
    ruta = os.path.join(CACHE_DIR, f"{key}.json")
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({'timestamp': time.time(), 'prompt': prompt, 'respuesta': respuesta}, f, ensure_ascii=False, indent=2)

def _obtener_cache_ia(prompt: str) -> str | None:
    key = _calcular_hash_prompt(prompt)
    ruta = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if time.time() - data.get('timestamp', 0) < CACHE_TTL:
            return data.get('respuesta')
    except:
        pass
    return None

def _construir_prompt(oportunidades: list[dict], regime: dict, usd_mxn: float) -> str:
    resumen = "\n".join([f"- {o['Símbolo']}: Score {o['Score']}/14, RSI {o['RSI']}, Señales: {o['Señales']}" for o in oportunidades[:8]])
    return f"""Eres un analista de mercados financieros. Analiza estas señales de trading en español.

MERCADO HOY:
- Régimen S&P 500: {regime['regime']}
- S&P 500: {regime['precio']:,.0f} | EMA200: {regime['ema200']:,.0f}
- Retorno último mes: {regime['ret_1m']:+.1f}%
- USD/MXN: {usd_mxn:.2f}

OPORTUNIDADES DETECTADAS:
{resumen}

Proporciona en formato conciso:
1. Evaluación del contexto de mercado (2 oraciones)
2. Las 3 mejores oportunidades con razón breve
3. Confianza general: ALTA / MEDIA / BAJA con justificación
4. Advertencia principal si la hay

Sé directo y práctico."""

def analisis_ia(oportunidades: list[dict], regime: dict, usd_mxn: float) -> str:
    if not oportunidades:
        return ""
    prompt = _construir_prompt(oportunidades, regime, usd_mxn)
    cache = _obtener_cache_ia(prompt)
    if cache:
        return cache

    proveedores = [("Gemini", GEMINI_API_KEY), ("Groq", GROQ_API_KEY), ("Anthropic", ANTHROPIC_API_KEY)]
    for nombre, key in proveedores:
        if not key:
            continue
        try:
            if nombre == "Gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
                resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
                texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif nombre == "Groq":
                resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": 800}, timeout=30)
                texto = resp.json()["choices"][0]["message"]["content"]
            else:
                continue
            _guardar_cache_ia(prompt, texto)
            return texto
        except:
            continue
    return "**IA no disponible** — revisa tus API keys en GitHub Secrets."

# ============================================================
# ALERTAS
# ============================================================
def enviar_email(asunto: str, html: str) -> bool:
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"] = EMAIL_REMITENTE
        msg["To"] = EMAIL_DESTINO
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_REMITENTE, EMAIL_PASSWORD)
            s.sendmail(EMAIL_REMITENTE, EMAIL_DESTINO, msg.as_string())
        return True
    except:
        return False

def enviar_whatsapp(mensaje: str) -> bool:
    if not WHATSAPP_NUMERO or not WHATSAPP_APIKEY:
        return False
    try:
        r = requests.get("https://api.callmebot.com/whatsapp.php", params={"phone": WHATSAPP_NUMERO, "apikey": WHATSAPP_APIKEY, "text": mensaje}, timeout=10)
        return r.status_code == 200
    except:
        return False

def construir_email(ops: list[dict], regime: dict, ia_texto: str, hora: str) -> str:
    filas = "".join([f"<tr><td><b>{o['Símbolo']}</b></td><td>{o['Precio MXN']}</td><td>{o['Score']}</td><td>{o['Unidades']}</td><td>${o['Inversión MXN']:,.0f}</td><td>{o['Recomendación']}</td></tr>" for o in ops])
    bloque_ia = f"<h3 style='color:#7b61ff'>🤖 Análisis de IA</h3><div style='background:#f5f3ff;padding:12px;border-left:4px solid #7b61ff;font-size:14px;line-height:1.6'>{ia_texto.replace(chr(10),'<br>')}</div>" if ia_texto else ""
    icono_regime = {'ALCISTA':'🟢','LATERAL':'🟡','BAJISTA':'🔴'}.get(regime['regime'],'⚪')
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto">
    <h2 style="color:#1a73e8">📈 Scanner Trading — {hora}</h2>
    <p style="background:#f1f3f4;padding:10px;border-radius:6px;font-size:14px">
      {icono_regime} Régimen S&P 500: <b>{regime['regime']}</b> | S&P: {regime['precio']:,.0f} | EMA200: {regime['ema200']:,.0f} | Ret. 1m: {regime['ret_1m']:+.1f}%
    </p>
    {bloque_ia}
    <h3 style="color:#34a853">🟢 Oportunidades de COMPRA ({len(ops)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px">
      <tr style="background:#e8f5e9">
        <th>Símbolo</th><th>Precio MXN</th><th>Score</th><th>Unidades</th><th>Inversión</th><th>Recomendación</th>
      </tr>
      {filas if filas else '<tr><td colspan="6" style="text-align:center">Sin señales</td></tr>'}
    </table>
    <p style="color:#999;font-size:11px;margin-top:20px">Scanner autónomo — análisis informativo, no asesoría financiera.</p>
    </body></html>"""

# ============================================================
# MAIN
# ============================================================
def main():
    hora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n{'='*60}")
    print(f"  Scanner Trading 24/7 — VERSIÓN MEJORADA {hora}")
    print(f"{'='*60}\n")

    try:
        usd_data = yf.Ticker("USDMXN=X").history(period="1d")
        usd_mxn = float(usd_data['Close'].iloc[-1]) if not usd_data.empty else 20.0
    except:
        usd_mxn = 20.0
    print(f"USD/MXN: {usd_mxn:.2f}")

    regime = obtener_market_regime()
    print(f"Régimen: {regime['regime']} (bonus score: {regime['score_bonus']})")
    score_minimo_efectivo = 9 if regime['regime'] == 'BAJISTA' else SCORE_MINIMO

    print(f"\nAnalizando {len(UNIVERSO)} activos en paralelo...")
    resultados = []
    args_list = [(sim, usd_mxn, regime['score_bonus']) for sim in UNIVERSO]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(analizar, a): a[0] for a in args_list}
        for i, f in enumerate(as_completed(futures), 1):
            res = f.result()
            if res and res['Score'] >= score_minimo_efectivo:
                resultados.append(res)
            if i % 20 == 0:
                print(f"  {i}/{len(UNIVERSO)} procesados...")

    resultados.sort(key=lambda x: x['Score'], reverse=True)
    print(f"\nOportunidades detectadas: {len(resultados)}")

    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for senal in resultados:
        guardar_senal_en_historial(senal, fecha_hoy)

    print("\nEjecutando BACKTESTING REALISTA (SL/TP + comisión)...")
    hist_df = cargar_historial()
    metrics = backtest_realista(hist_df)
    print(f"  Total señales evaluadas: {metrics['total']}")
    print(f"  Win rate: {metrics['win_rate']}%")
    print(f"  Retorno promedio: {metrics['ret_prom']}%")

    ia_texto = analisis_ia(resultados, regime, usd_mxn) if resultados else ""

    if resultados:
        html = construir_email(resultados, regime, ia_texto, hora)
        asunto = f"📈 Trading Alert {hora} — {len(resultados)} señales | Mercado: {regime['regime']}"
        enviar_email(asunto, html)

        top3 = ", ".join([r['Símbolo'] for r in resultados[:3]])
        confianza = "ALTA" if regime['regime'] == 'ALCISTA' else "MEDIA" if regime['regime'] == 'LATERAL' else "BAJA"
        msg_wa = f"📈 *Scanner Trading* — {hora}\nRégimen: {regime['regime']} | USD/MXN: {usd_mxn:.2f}\n🟢 {len(resultados)} oportunidades\nTop 3: {top3}\nConfianza: {confianza}"
        enviar_whatsapp(msg_wa)

    print(f"\n✅ Scanner completado — {datetime.now().strftime('%H:%M:%S')}\n")

if __name__ == "__main__":
    main()
