"""
============================================================
SCANNER DE TRADING AUTÓNOMO 24/7
Con historial de señales, backtesting y caché de IA
============================================================
"""

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
BACKTEST_WINDOW  = 5   # días hábiles para evaluar retorno

# ============================================================
# UNIVERSO COMPLETO (≈700 activos)
# ============================================================
UNIVERSO = list(set([
    # S&P 500 completo
    'MMM','AOS','ABT','ABBV','ACN','ADBE','AMD','AES','AFL','A','APD','AKAM','ALK','ALB',
    'ARE','ALGN','ALLE','LNT','ALL','GOOGL','GOOG','MO','AMZN','AMCR','AEE','AAL','AEP',
    'AXP','AIG','AMT','AWK','AMP','ABC','AME','AMGN','APH','ADI','ANSS','AON','APA','AAPL',
    'AMAT','APTV','ADM','ANET','AJG','AIZ','T','ATO','ADSK','ADP','AZO','AVB','AVY','AXON',
    'BKR','BALL','BAC','BBWI','BAX','BDX','BBY','BIO','BIIB','BLK','BK','BA','BKNG','BWA',
    'BSX','BMY','AVGO','BR','BRO','CDNS','CAT','CBOE','CBRE','CDW','CE','CNC','CNP','CF',
    'CRL','CHTR','CVX','CMG','CB','CHD','CI','CINF','CTAS','CSCO','C','CFG','CLX','CME',
    'CMS','KO','CTSH','CL','CMCSA','CMA','CAG','COP','ED','STZ','COO','CPB','COST','CTVA',
    'CVS','DHI','DHR','DRI','DVA','DE','DAL','DVN','DXCM','FANG','DLR','DFS','DG','DLTR',
    'D','DPZ','DOV','DOW','DTE','DUK','DD','EMN','ETN','EBAY','ECL','EIX','EW','EL','EMR',
    'ENPH','ETR','EOG','EFX','EQIX','EQR','ESS','ELV','EXC','EXPE','EXPD','EXR','XOM',
    'FDS','FICO','FAST','FDX','FITB','FSLR','FE','FIS','FISV','FLT','FMC','F','FTNT','FTV',
    'FCX','GRMN','IT','GNRC','GD','GE','GIS','GM','GPC','GILD','GL','GPN','GS','GWW','HAL',
    'HAS','HCA','HSIC','HSY','HES','HPE','HLT','HOLX','HD','HON','HRL','HST','HWM','HPQ',
    'HUM','HBAN','IBM','IEX','IDXX','ITW','ILMN','INCY','IR','INTC','ICE','IP','IPG','IFF',
    'INTU','ISRG','IVZ','INVH','IQV','IRM','JBHT','JKHY','J','JNJ','JCI','JPM','JNPR','K',
    'KEY','KEYS','KMB','KIM','KMI','KLAC','KHC','KR','LHX','LH','LRCX','LW','LVS','LDOS',
    'LEN','LIN','LYV','LKQ','LMT','L','LOW','LYB','MTB','MRO','MPC','MKTX','MAR','MMC',
    'MLM','MAS','MA','MKC','MCD','MCK','MDT','MRK','MET','MTD','MGM','MCHP','MU','MSFT',
    'MAA','MRNA','MHK','MDLZ','MPWR','MNST','MCO','MS','MOS','MSI','MSCI','NDAQ','NTAP',
    'NFLX','NEM','NEE','NKE','NI','NSC','NTRS','NOC','NRG','NUE','NVDA','NVR','NXPI','ORLY',
    'OXY','ODFL','OMC','OKE','ORCL','OTIS','PCAR','PH','PAYX','PAYC','PYPL','PNR','PEP',
    'PFE','PCG','PM','PSX','PNW','PLD','PGR','PPL','PFG','PG','PWR','POOL','PRU','PEG',
    'PSA','PHM','QCOM','RJF','RTX','O','REGN','RF','RSG','RMD','RVTY','RHI','ROK','ROL',
    'ROP','ROST','RCL','SPGI','CRM','SBAC','STX','SYY','SCHW','STLD','SRE','NOW','SHW',
    'SPG','SLB','SNA','SO','LUV','SWK','SBUX','STT','STE','SYK','SYF','SNPS','TMUS','TROW',
    'TTWO','TPR','TGT','TEL','TDY','TFX','TER','TSLA','TXN','TXT','TMO','TJX','TSCO','TDG',
    'TRV','TRMB','TFC','TYL','TSN','UDR','ULTA','USB','UHS','UNP','UAL','UNH','UPS','URI',
    'VTR','VLO','VTRS','VRSN','VZ','VRTX','VFC','VNO','VMC','WAB','WBA','WMT','WDC','WU',
    'WRK','WY','WHR','WMB','WEC','WFC','WST','WYNN','XEL','XYL','YUM','ZBRA','ZBH','ZION','ZTS',
    # NASDAQ 100 (adicionales)
    'ASML','CDNS','CHTR','CSX','CTAS','EA','LULU','MELI','MNST','NXPI',
    'PANW','PCAR','REGN','SNPS','WDAY','ZM','ZS','SGEN','TTD','TCOM',
    # IA / Tech adicional
    'AI','PLTR','SNOW','BIDU','BABA','SAP','U',
    # ETFs sectoriales SPDR + temáticos
    'XLK','XLV','XLF','XLE','XLI','XLY','XLP','XLU','XLB','XLRE','XLC',
    'SOXX','ARKK','ARKG','ARKW','ARKF','CIBR','ROBO','ICLN','TAN','LIT',
    'JETS','XHB','KRE','IBB','SPY','QQQ','IWM','DIA','VTI',
    # Commodities
    'GLD','SLV','USO','UNG','DBC',
    # Mineras y petroleras
    'NEM','GOLD','FCX',
    # Mid-cap growth
    'DDOG','NET','CRWD','ZS','BILL','DUOL','CELH','SMCI','HUBS','MNDY',
    'APPN','PCTY','FIVN','RELY','PATH','SMAR','JAMF','EXAS','NVCR','FATE',
    'RXRX','AFRM','UPST','HOOD','SQ','SOFI','NU','PLUG','CHPT','RIVN',
    'LCID','KTOS','RKLB','ACHR',
    # ETFs mercados emergentes
    'EWZ','EWJ','FXI','KWEB','EWY','EWT','EWH','EWA','EWC','EWG','EWQ','EWU',
    'VWO','EEM','INDA','EWX',
    # BMV México
    'WALMEX.MX','GMEXICOB.MX','CEMEXCPO.MX','FEMSAUBD.MX','AMXL.MX','KOFUBL.MX',
    'GFNORTEO.MX','BBAJIOO.MX','ALFA.MX','ALPEKA.MX','ASURB.MX','GAPB.MX','OMAB.MX',
    'AC.MX','GCC.MX','LALA.MX','MEGA.MX','PINFRA.MX','TLEVISACPO.MX','VESTA.MX',
    'GRUMA.MX','HERDEZ.MX','CUERVO.MX','ORBIA.MX',
    # IBEX 35
    'SAN.MC','BBVA.MC','TEF.MC','ITX.MC','IBE.MC','FER.MC','ENG.MC','ACS.MC','REP.MC',
    'AENA.MC','CLNX.MC','GRF.MC','MTS.MC','MAP.MC','MEL.MC','CABK.MC','ELE.MC','IAG.MC',
    'ANA.MC','VIS.MC','CIE.MC','LOG.MC','ACX.MC',
]))

# ============================================================
# INDICADORES TÉCNICOS
# ============================================================
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
    hl   = hist['High'] - hist['Low']
    hc   = (hist['High'] - hist['Close'].shift()).abs()
    lc   = (hist['Low']  - hist['Close'].shift()).abs()
    hist['ATR']      = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()
    hist['BB_mid']   = hist['Close'].rolling(20).mean()
    bb_std           = hist['Close'].rolling(20).std()
    hist['BB_upper'] = hist['BB_mid'] + 2 * bb_std
    hist['BB_lower'] = hist['BB_mid'] - 2 * bb_std
    hist['BB_pct']   = (hist['Close'] - hist['BB_lower']) / (hist['BB_upper'] - hist['BB_lower'])
    low14            = hist['Low'].rolling(14).min()
    high14           = hist['High'].rolling(14).max()
    hist['STOCH_K']  = 100 * (hist['Close'] - low14) / (high14 - low14)
    hist['STOCH_D']  = hist['STOCH_K'].rolling(3).mean()
    hist['Vol_avg']  = hist['Volume'].rolling(20).mean()
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
    return score, señales

def obtener_market_regime() -> dict:
    try:
        sp = yf.Ticker("^GSPC").history(period="1y")
        if sp.empty or len(sp) < 200:
            return {'regime': 'DESCONOCIDO', 'score_bonus': 0, 'precio': 0, 'ema200': 0, 'ret_1m': 0}
        precio = sp['Close'].iloc[-1]
        ema200 = sp['Close'].ewm(span=200).mean().iloc[-1]
        ema50  = sp['Close'].ewm(span=50).mean().iloc[-1]
        ret_1m = (precio / sp['Close'].iloc[-20] - 1) * 100 if len(sp) >= 20 else 0
        if precio > ema200 and precio > ema50 and ema50 > ema200:
            return {'regime': 'ALCISTA', 'score_bonus': 0, 'precio': precio, 'ema200': ema200, 'ret_1m': ret_1m}
        elif precio > ema200:
            return {'regime': 'LATERAL', 'score_bonus': -1, 'precio': precio, 'ema200': ema200, 'ret_1m': ret_1m}
        else:
            return {'regime': 'BAJISTA', 'score_bonus': -3, 'precio': precio, 'ema200': ema200, 'ret_1m': ret_1m}
    except:
        return {'regime': 'DESCONOCIDO', 'score_bonus': 0, 'precio': 0, 'ema200': 0, 'ret_1m': 0}

def position_size(precio: float, atr: float) -> dict:
    riesgo_mxn = CAPITAL_TRADING * (RIESGO_PCT / 100)
    stop_dist  = 2 * atr
    if stop_dist <= 0:
        return {'unidades': 0, 'inversion': 0}
    unidades   = riesgo_mxn / stop_dist
    inversion  = min(unidades * precio, CAPITAL_TRADING * 0.20)
    unidades   = inversion / precio
    return {'unidades': round(unidades, 2), 'inversion': round(inversion, 2)}

def analizar(args: tuple) -> dict | None:
    simbolo, usd_mxn, regime_bonus = args
    try:
        hist = yf.Ticker(simbolo).history(period="3mo")
        if hist.empty or len(hist) < 55:
            return None
        factor = 1.0 if simbolo.endswith('.MX') else usd_mxn
        for c in ['Close', 'Open', 'High', 'Low']:
            hist[c] *= factor
        hist = calcular_indicadores(hist)
        hist = hist.dropna(subset=['RSI', 'MACD', 'EMA20', 'EMA50', 'ATR'])
        if len(hist) < 2:
            return None
        r = hist.iloc[-1].to_dict()
        p = hist.iloc[-2].to_dict()
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
            'Símbolo':      simbolo,
            'Precio MXN':   round(precio, 2),
            'Score':        score,
            'RSI':          round(r['RSI'], 1),
            'ATR':          round(atr, 2),
            'Stop Loss':    round(precio - 2 * atr, 2),
            'Take Profit':  round(precio + 3 * atr, 2),
            'Unidades':     ps['unidades'],
            'Inversión MXN':ps['inversion'],
            'Señales':      " | ".join(señales),
            'Recomendación':rec,
        }
    except:
        return None

# ============================================================
# HISTORIAL Y BACKTESTING
# ============================================================
def cargar_historial() -> pd.DataFrame:
    if os.path.exists(HISTORICO_FILE):
        return pd.read_csv(HISTORICO_FILE)
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
    print(f"  ✅ Señal guardada en historial: {senal['Símbolo']} (Score {senal['Score']})")

def backtest_historial(df_hist: pd.DataFrame) -> dict:
    if df_hist.empty:
        return {'win_rate': 0, 'ret_prom': 0, 'total': 0}
    resultados = []
    for _, row in df_hist.iterrows():
        try:
            ticker = yf.Ticker(row['simbolo'])
            end_date = datetime.now()
            start_date = end_date - timedelta(days=180)
            hist = ticker.history(start=start_date, end=end_date)
            if hist.empty:
                continue
            fecha_senal = pd.to_datetime(row['fecha'])
            idx = hist.index.searchsorted(fecha_senal)
            if idx + BACKTEST_WINDOW >= len(hist):
                continue
            precio_entrada = row['precio']
            precio_salida = hist['Close'].iloc[idx + BACKTEST_WINDOW]
            retorno = (precio_salida / precio_entrada - 1) * 100
            resultados.append(retorno)
        except:
            continue
    if resultados:
        win_rate = sum(1 for r in resultados if r > 0) / len(resultados) * 100
        ret_prom = np.mean(resultados)
        return {
            'win_rate': round(win_rate, 1),
            'ret_prom': round(ret_prom, 2),
            'total': len(resultados)
        }
    return {'win_rate': 0, 'ret_prom': 0, 'total': 0}

# ============================================================
# IA CON CACHÉ Y REINTENTOS
# ============================================================
def _calcular_hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()

def _guardar_cache_ia(prompt: str, respuesta: str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = _calcular_hash_prompt(prompt)
    ruta = os.path.join(CACHE_DIR, f"{key}.json")
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': time.time(),
            'prompt': prompt,
            'respuesta': respuesta
        }, f, ensure_ascii=False, indent=2)

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
        else:
            os.remove(ruta)
    except:
        pass
    return None

def _llamar_ia_con_reintentos(proveedor: str, prompt: str, max_retries=3):
    for intento in range(max_retries):
        try:
            if proveedor == "Gemini":
                return _ia_gemini(prompt)
            elif proveedor == "Groq":
                return _ia_groq(prompt)
            elif proveedor == "Anthropic":
                return _ia_anthropic(prompt)
        except Exception as e:
            print(f"  ⚠️  {proveedor} intento {intento+1}/{max_retries} falló: {e}")
            if intento == max_retries - 1:
                raise
            espera = 2 ** intento
            print(f"     Reintentando en {espera} segundos...")
            time.sleep(espera)
    raise RuntimeError(f"No se pudo obtener respuesta de {proveedor} después de {max_retries} intentos.")

def _construir_prompt(oportunidades: list[dict], regime: dict, usd_mxn: float) -> str:
    resumen = "\n".join([
        f"- {o['Símbolo']}: Score {o['Score']}/14, RSI {o['RSI']}, "
        f"Señales: {o['Señales']}, Rec: {o['Recomendación']}"
        for o in oportunidades[:8]
    ])
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
2. Las 3 mejores oportunidades con razón breve de por qué destacan
3. Confianza general: ALTA / MEDIA / BAJA con justificación
4. Advertencia principal si la hay

Sé directo y práctico. No inventes datos."""

def _ia_gemini(prompt: str) -> str:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}")
    resp = requests.post(
        url,
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=30,
    )
    if resp.status_code == 200:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError(f"Gemini {resp.status_code}: {resp.text[:200]}")

def _ia_groq(prompt: str) -> str:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.1-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800,
        },
        timeout=30,
    )
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError(f"Groq {resp.status_code}: {resp.text[:200]}")

def _ia_anthropic(prompt: str) -> str:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 800,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    if resp.status_code == 200:
        return resp.json()["content"][0]["text"]
    raise RuntimeError(f"Anthropic {resp.status_code}: {resp.text[:200]}")

def analisis_ia(oportunidades: list[dict], regime: dict, usd_mxn: float) -> str:
    if not oportunidades:
        return ""
    prompt = _construir_prompt(oportunidades, regime, usd_mxn)
    cache = _obtener_cache_ia(prompt)
    if cache:
        print("  ✅ Análisis IA obtenido desde caché")
        return cache
    proveedores = [
        ("Gemini", GEMINI_API_KEY),
        ("Groq", GROQ_API_KEY),
        ("Anthropic", ANTHROPIC_API_KEY),
    ]
    for nombre, api_key in proveedores:
        if not api_key:
            continue
        try:
            print(f"  Intentando IA con {nombre}...")
            texto = _llamar_ia_con_reintentos(nombre, prompt)
            print(f"  ✅ Análisis IA completado con {nombre}")
            _guardar_cache_ia(prompt, texto)
            return texto
        except Exception as e:
            print(f"  ⚠️  {nombre} falló después de reintentos: {e}")
    print("  ⚠️  Ningún proveedor de IA disponible. Configura al menos uno en GitHub Secrets.")
    return ""

# ============================================================
# ALERTAS (EMAIL Y WHATSAPP)
# ============================================================
def enviar_email(asunto: str, html: str) -> bool:
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD:
        print("⚠️  EMAIL_REMITENTE o EMAIL_PASSWORD no configurados")
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
        print(f"✅ Email enviado a {EMAIL_DESTINO}")
        return True
    except Exception as e:
        print(f"❌ Error email: {e}")
        return False

def enviar_whatsapp(mensaje: str) -> bool:
    if not WHATSAPP_NUMERO or not WHATSAPP_APIKEY:
        print("⚠️  WHATSAPP_NUMERO o WHATSAPP_APIKEY no configurados")
        return False
    try:
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": WHATSAPP_NUMERO, "apikey": WHATSAPP_APIKEY, "text": mensaje},
            timeout=10,
        )
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} WhatsApp: {r.status_code}")
        return ok
    except Exception as e:
        print(f"❌ Error WhatsApp: {e}")
        return False

def construir_email(ops: list[dict], regime: dict, ia_texto: str, hora: str) -> str:
    filas = "".join([
        f"<tr><td><b>{o['Símbolo']}</b></td><td>{o['Precio MXN']}</td>"
        f"<td>{o['Score']}</td><td>{o['Unidades']}</td>"
        f"<td>${o['Inversión MXN']:,.0f}</td><td>{o['Recomendación']}</td></tr>"
        for o in ops
    ])
    bloque_ia = ""
    if ia_texto:
        bloque_ia = f"""
        <h3 style="color:#7b61ff">🤖 Análisis de IA</h3>
        <div style="background:#f5f3ff;padding:12px;border-left:4px solid #7b61ff;font-size:14px;line-height:1.6">
          {ia_texto.replace(chr(10),'<br>')}
        </div>"""
    icono_regime = {'ALCISTA':'🟢','LATERAL':'🟡','BAJISTA':'🔴'}.get(regime['regime'],'⚪')
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto">
    <h2 style="color:#1a73e8">📈 Scanner Trading — {hora}</h2>
    <p style="background:#f1f3f4;padding:10px;border-radius:6px;font-size:14px">
      {icono_regime} Régimen S&P 500: <b>{regime['regime']}</b> |
      S&P: {regime['precio']:,.0f} | EMA200: {regime['ema200']:,.0f} |
      Ret. 1m: {regime['ret_1m']:+.1f}%
    </p>
    {bloque_ia}
    <h3 style="color:#34a853">🟢 Oportunidades de COMPRA ({len(ops)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px">
      <tr style="background:#e8f5e9">
        <th>Símbolo</th><th>Precio MXN</th><th>Score</th>
        <th>Unidades</th><th>Inversión</th><th>Recomendación</th>
      </tr>
      {filas if filas else '<tr><td colspan="6" style="text-align:center">Sin señales</td></tr>'}
    </table>
    <p style="color:#999;font-size:11px;margin-top:20px">
      Scanner autónomo — análisis informativo, no asesoría financiera.<br>
      Capital configurado: ${CAPITAL_TRADING:,.0f} MXN · Riesgo: {RIESGO_PCT}% por operación
    </p>
    </body></html>"""

# ============================================================
# MAIN
# ============================================================
def main():
    hora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n{'='*50}")
    print(f"  Scanner Trading 24/7 — {hora}")
    print(f"{'='*50}\n")

    # 1. Tipo de cambio
    try:
        usd_data = yf.Ticker("USDMXN=X").history(period="1d")
        usd_mxn = float(usd_data['Close'].iloc[-1]) if not usd_data.empty else 20.0
    except:
        usd_mxn = 20.0
    print(f"USD/MXN: {usd_mxn:.2f}")

    # 2. Market regime
    print("Evaluando régimen de mercado...")
    regime = obtener_market_regime()
    print(f"Régimen: {regime['regime']} (bonus score: {regime['score_bonus']})")
    if regime['regime'] == 'BAJISTA':
        print("⚠️  Mercado bajista — score mínimo elevado automáticamente a 9")
        score_minimo_efectivo = 9
    else:
        score_minimo_efectivo = SCORE_MINIMO

    # 3. Análisis en paralelo
    print(f"\nAnalizando {len(UNIVERSO)} activos en paralelo ({MAX_WORKERS} hilos)...")
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
    for r in resultados:
        print(f"  {r['Símbolo']:8s} Score:{r['Score']:2d}  RSI:{r['RSI']:5.1f}  "
              f"Precio:{r['Precio MXN']:>10.2f}  {r['Recomendación']}")

    # 4. Guardar en historial
    print("\nGuardando señales en historial...")
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for senal in resultados:
        guardar_senal_en_historial(senal, fecha_hoy)

    # 5. Backtesting sobre historial
    print("\nEjecutando backtesting sobre señales previas...")
    hist_df = cargar_historial()
    metrics = backtest_historial(hist_df)
    print(f"  Backtest (ventana {BACKTEST_WINDOW} días):")
    print(f"    - Total señales evaluadas: {metrics['total']}")
    print(f"    - Win rate: {metrics['win_rate']}%")
    print(f"    - Retorno promedio: {metrics['ret_prom']}%")

    # 6. Análisis IA
    print("\nConsultando IA para análisis...")
    ia_texto = analisis_ia(resultados, regime, usd_mxn)
    if ia_texto:
        print("\n--- ANÁLISIS IA ---")
        print(ia_texto[:500] + "..." if len(ia_texto) > 500 else ia_texto)

    # 7. Alertas (solo si hay oportunidades)
    if resultados:
        html = construir_email(resultados, regime, ia_texto, hora)
        asunto = (f"📈 Trading Alert {hora} — "
                  f"{len(resultados)} señales | Mercado: {regime['regime']}")
        enviar_email(asunto, html)

        top3 = ", ".join([r['Símbolo'] for r in resultados[:3]])
        confianza = "ALTA" if regime['regime'] == 'ALCISTA' else "MEDIA" if regime['regime'] == 'LATERAL' else "BAJA"
        msg_wa = (f"📈 *Scanner Trading* — {hora}\n"
                  f"Régimen: {regime['regime']} | USD/MXN: {usd_mxn:.2f}\n"
                  f"🟢 {len(resultados)} oportunidades\n"
                  f"Top 3: {top3}\n"
                  f"Confianza: {confianza}\n"
                  f"Ver detalles en tu email")
        enviar_whatsapp(msg_wa)
    else:
        print("Sin oportunidades que superen el umbral. No se envían alertas.")

    print(f"\n✅ Scanner completado — {datetime.now().strftime('%H:%M:%S')}\n")

if __name__ == "__main__":
    main()
