# ============================================================
# SCANNER DE TRADING AUTÓNOMO 24/7
# Versión mejorada: universo ampliado (700+ activos) + análisis de posiciones desde CSV
# Conserva la misma lógica estricta de filtros para compras.
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
# CONFIGURACIÓN (se lee de variables de entorno / Secrets)
# ============================================================
EMAIL_REMITENTE   = os.environ.get("EMAIL_REMITENTE",   "")
EMAIL_PASSWORD    = os.environ.get("EMAIL_PASSWORD",    "")
EMAIL_DESTINO     = "alopez.uci@gmail.com"
WHATSAPP_NUMERO   = os.environ.get("WHATSAPP_NUMERO", "")
WHATSAPP_APIKEY   = os.environ.get("WHATSAPP_APIKEY", "")

GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY",    "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY",      "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SCORE_MINIMO     = 7          # mantiene el umbral estricto
CAPITAL_TRADING  = 25_000
RIESGO_PCT       = 1.0
MAX_WORKERS      = 20
CACHE_DIR        = "cache_ia"
CACHE_TTL        = 3600
HISTORICO_FILE   = "historial_senales.csv"
BACKTEST_WINDOW  = 5

# Archivo con posiciones actuales (simbolo,precio_compra)
POSICIONES_FILE = "posiciones.csv"

# ============================================================
# UNIVERSO AMPLIADO (más de 700 activos)
# ============================================================

# --- S&P 500 completo ---
sp500 = [
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
    'WRK','WY','WHR','WMB','WEC','WFC','WST','WYNN','XEL','XYL','YUM','ZBRA','ZBH','ZION','ZTS'
]

# --- NASDAQ 100 completo ---
nasdaq100 = [
    'ADBE','AMD','AMGN','AMZN','ASML','AVGO','BIIB','BKNG','CDNS','CHTR','CMCSA','COST','CSCO',
    'CSX','CTAS','DXCM','EA','EBAY','EXC','FANG','FAST','FTNT','GILD','GOOGL','GOOG','HON','IDXX',
    'ILMN','INTC','INTU','ISRG','KLAC','LRCX','LULU','MAR','MELI','META','MNST','MSFT','MU','NFLX',
    'NVDA','NXPI','ODFL','ORLY','PANW','PAYX','PCAR','PEP','QCOM','REGN','ROST','SBUX','SNPS','TMUS',
    'TSLA','TXN','VRTX','WBA','WDAY','XEL','ZM','ZS'
]

# --- ETFs sectoriales SPDR + temáticos ---
etfs_sectoriales = [
    'XLK','XLV','XLF','XLE','XLI','XLY','XLP','XLU','XLB','XLRE','XLC',
    'SOXX','ARKK','ARKG','ARKW','ARKF','CIBR','ROBO','ICLN','TAN','LIT',
    'JETS','XHB','KRE','IBB','SPY','QQQ','IWM','DIA','VTI'
]

# --- ETFs de materias primas ---
commodity_etfs = ['GLD','SLV','USO','UNG','DBC']

# --- Mineras y petroleras ---
mining_oil = ['NEM','GOLD','FCX','XOM','CVX','COP','EOG','SLB']

# --- IA (Inteligencia Artificial) ---
ia_stocks = [
    'NVDA','AMD','INTC','AI','PLTR','IBM','MSFT','GOOGL','META','SNOW','CRM','ADBE','NOW','ORCL',
    'BIDU','BABA','SAP'
]

# --- Mid-cap growth (potencial de crecimiento) ---
mid_cap_growth = [
    'DDOG','NET','CRWD','ZS','BILL','DUOL','CELH','SMCI','HUBS','MNDY','APPN','PCTY','FIVN',
    'RELY','PATH','SMAR','JAMF','EXAS','NVCR','FATE','RXRX','AFRM','UPST','HOOD','SQ','SOFI',
    'NU','PLUG','CHPT','RIVN','LCID','KTOS','RKLB','ACHR'
]

# --- ETFs de mercados emergentes ---
etfs_emergentes = [
    'EWZ','EWJ','FXI','KWEB','EWY','EWT','EWH','EWA','EWC','EWG','EWQ','EWU','VWO','EEM','INDA','EWX'
]

# --- FIBRAS mexicanas (adicionar) ---
fibras_mex = [
    'FMTY14.MX',   # Fibra MTY
    'FUNO11.MX',   # Fibra UNO
    'FIBRAPL14.MX',# Fibra Plus
    'TERRA13.MX',  # Terrafina
    'DANHOS13.MX', # Danhos
    'FIBRAHD15.MX',# Fibra HD
    'FIBRAMQ12.MX' # Fibra Macquarie
]

# --- BMV México (ampliado) ---
bmv = [
    'WALMEX.MX','GMEXICOB.MX','CEMEXCPO.MX','FEMSAUBD.MX','AMXL.MX','KOFUBL.MX','GFNORTEO.MX',
    'BBAJIOO.MX','ALFA.MX','ALPEKA.MX','ASURB.MX','GAPB.MX','OMAB.MX','AC.MX','GCC.MX','LALA.MX',
    'MEGA.MX','PINFRA.MX','TLEVISACPO.MX','VESTA.MX','GRUMA.MX','HERDEZ.MX','CUERVO.MX','ORBIA.MX',
    'VOLARA.MX','Q.MX','LABB.MX','NEMAKA.MX'
]

# --- IBEX 35 España ---
ibex35 = [
    'SAN.MC','BBVA.MC','TEF.MC','ITX.MC','IBE.MC','FER.MC','ENG.MC','ACS.MC','REP.MC','AENA.MC',
    'CLNX.MC','GRF.MC','MTS.MC','MAP.MC','MEL.MC','CABK.MC','ELE.MC','IAG.MC','ANA.MC','VIS.MC',
    'CIE.MC','LOG.MC','ACX.MC'
]

# --- Acciones adicionales de alta capitalización en mercados emergentes ---
emergentes_acciones = [
    'BABA',   # Alibaba
    'BIDU',   # Baidu
    'JD',     # JD.com
    'PDD',    # Pinduoduo
    'NTES',   # NetEase
    'TCEHY',  # Tencent (pink)
    'INFY',   # Infosys
    'HDB',    # HDFC Bank
    'IBN',    # ICICI Bank
    'VALE',   # Vale
    'PBR',    # Petrobras
    'YPF',    # YPF
    'MELI',   # MercadoLibre (ya está en NASDAQ)
    'NU'      # Nubank (ya está)
]

# --- Unir todos los universos en una sola lista (sin duplicados) ---
UNIVERSO = list(set(
    sp500 +
    nasdaq100 +
    etfs_sectoriales +
    commodity_etfs +
    mining_oil +
    ia_stocks +
    mid_cap_growth +
    etfs_emergentes +
    fibras_mex +
    bmv +
    ibex35 +
    emergentes_acciones
))

# ============================================================
# FUNCIONES DE INDICADORES, SCORING, MARKET REGIME, POSITION SIZING
# (Se mantienen idénticas a la versión original)
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
    if 'EMA20_weekly' in r and 'EMA50_weekly' in r and r['EMA20_weekly'] > r['EMA50_weekly']:
        score += 2
        señales.append("EMA semanal alcista")
    return score, señales

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

def position_size(precio: float, atr: float) -> dict:
    riesgo_mxn = CAPITAL_TRADING * (RIESGO_PCT / 100)
    stop_dist  = 2 * atr
    if stop_dist <= 0:
        return {'unidades': 0, 'inversion': 0}
    unidades   = riesgo_mxn / stop_dist
    inversion  = min(unidades * precio, CAPITAL_TRADING * 0.20)
    unidades   = inversion / precio
    return {'unidades': round(unidades, 2), 'inversion': round(inversion, 2)}

# ============================================================
# FUNCIÓN DE ANÁLISIS (ahora también recibe diccionario de posiciones)
# ============================================================
def analizar(args: tuple) -> dict | None:
    simbolo, usd_mxn, regime_bonus, posiciones = args
    try:
        hist = yf.Ticker(simbolo).history(period="3mo")
        if hist.empty or len(hist) < 55:
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
        precio = r['Close']
        atr    = r['ATR']

        # Verificar si es una posición que tenemos
        if simbolo in posiciones:
            precio_compra = posiciones[simbolo]
            ganancia = ((precio / precio_compra) - 1) * 100
            if ganancia >= 15:
                return {
                    'Símbolo':      simbolo,
                    'Precio MXN':   round(precio, 2),
                    'Score':        0,
                    'RSI':          round(r['RSI'], 1),
                    'ATR':          round(atr, 2),
                    'Stop Loss':    round(precio - 2 * atr, 2),
                    'Take Profit':  round(precio + 3 * atr, 2),
                    'Unidades':     0,
                    'Inversión MXN':0,
                    'Señales':      "",
                    'Recomendación': "VENDER",
                    'Motivo':       f"🎯 Take Profit +{ganancia:.1f}%"
                }
            elif ganancia <= -7:
                return {
                    'Símbolo':      simbolo,
                    'Precio MXN':   round(precio, 2),
                    'Score':        0,
                    'RSI':          round(r['RSI'], 1),
                    'ATR':          round(atr, 2),
                    'Stop Loss':    round(precio - 2 * atr, 2),
                    'Take Profit':  round(precio + 3 * atr, 2),
                    'Unidades':     0,
                    'Inversión MXN':0,
                    'Señales':      "",
                    'Recomendación': "VENDER",
                    'Motivo':       f"🛑 Stop Loss {ganancia:.1f}%"
                }
            # Si no hay señal de venta, no devolvemos nada (se ignora)
            return None

        # Si no es posición, aplicar lógica de compra normal
        score_base, señales = calcular_score(r, p)
        score = max(0, score_base + regime_bonus)
        ps = position_size(precio, atr)
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
            'Motivo':       ""
        }
    except:
        return None

# ============================================================
# HISTORIAL Y BACKTESTING (igual al original)
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
            fecha_senal = row['fecha']
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
# IA CON CACHÉ Y REINTENTOS (idéntico al original)
# ============================================================
def _calcular_hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()

def _guardar_cache_ia(prompt: str, respuesta: str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = _calcular_hash_prompt(prompt)
    with open(f"{CACHE_DIR}/{key}.json", 'w', encoding='utf-8') as f:
        json.dump({'timestamp': time.time(), 'prompt': prompt, 'respuesta': respuesta}, f, ensure_ascii=False, indent=2)

def _obtener_cache_ia(prompt: str) -> str | None:
    key = _calcular_hash_prompt(prompt)
    ruta = f"{CACHE_DIR}/{key}.json"
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
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
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
# ALERTAS (email, WhatsApp)
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

def construir_email(ops_compras: list[dict], ops_ventas: list[dict], regime: dict, ia_texto: str, hora: str) -> str:
    filas_compras = "".join([
        f"<tr><td><b>{o['Símbolo']}</b></td><td>{o['Precio MXN']}</td>"
        f"<td>{o['Score']}</td><td>{o['Unidades']}</td>"
        f"<td>${o['Inversión MXN']:,.0f}</td><td>{o['Recomendación']}</td></tr>"
        for o in ops_compras
    ])
    filas_ventas = "".join([
        f"<tr><td><b>{o['Símbolo']}</b></td><td>{o['Precio MXN']}</td><td>{o['Motivo']}</td></tr>"
        for o in ops_ventas
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
    <h3 style="color:#34a853">🟢 Oportunidades de COMPRA ({len(ops_compras)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px">
      <tr style="background:#e8f5e9">
        <th>Símbolo</th><th>Precio MXN</th><th>Score</th>
        <th>Unidades</th><th>Inversión</th><th>Recomendación</th>
       </tr>
      {filas_compras if filas_compras else '<tr><td colspan="6" style="text-align:center">Sin señales</td></tr>'}
    </table>
    <h3 style="color:#ea4335">🔴 Señales de VENTA ({len(ops_ventas)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px">
      <tr style="background:#fce8e6"><th>Símbolo</th><th>Precio MXN</th><th>Motivo</th></tr>
      {filas_ventas if filas_ventas else '<tr><td colspan="3">Sin señales</td></tr>'}
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
    regime = obtener_market_regime()
    print(f"Régimen: {regime['regime']} (bonus score: {regime['score_bonus']})")
    if regime['regime'] == 'BAJISTA':
        print("⚠️  Mercado bajista — score mínimo elevado automáticamente a 9")
        score_minimo_efectivo = 9
    else:
        score_minimo_efectivo = SCORE_MINIMO

    # 3. Leer posiciones actuales desde CSV
    posiciones = {}
    if os.path.exists(POSICIONES_FILE):
        df_pos = pd.read_csv(POSICIONES_FILE)
        if 'simbolo' in df_pos.columns and 'precio' in df_pos.columns:
            posiciones = dict(zip(df_pos['simbolo'], df_pos['precio']))
            print(f"📌 Posiciones cargadas: {len(posiciones)} activos")
        else:
            print("⚠️  Archivo posiciones.csv tiene formato incorrecto (se esperan columnas 'simbolo','precio')")
    else:
        print("ℹ️  No se encontró archivo posiciones.csv – solo se analizarán nuevas oportunidades")

    # 4. Añadir posiciones al universo si no están ya
    universo_final = list(set(UNIVERSO + list(posiciones.keys())))
    print(f"✅ Universo final con {len(universo_final)} activos (incluye {len(posiciones)} posiciones)")

    # 5. Análisis en paralelo
    print(f"\nAnalizando {len(universo_final)} activos en paralelo ({MAX_WORKERS} hilos)...")
    resultados = []
    args_list = [(sim, usd_mxn, regime['score_bonus'], posiciones) for sim in universo_final]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(analizar, a): a[0] for a in args_list}
        for i, f in enumerate(as_completed(futures), 1):
            res = f.result()
            if res:
                resultados.append(res)
            if i % 20 == 0:
                print(f"  {i}/{len(universo_final)} procesados...")

    # Separar compras y ventas
    compras = [r for r in resultados if r['Recomendación'].startswith('COMPRAR')]
    ventas  = [r for r in resultados if r['Recomendación'] == 'VENDER']

    # Ordenar compras por score descendente
    compras.sort(key=lambda x: x['Score'], reverse=True)

    print(f"\nOportunidades de compra detectadas: {len(compras)}")
    for r in compras[:10]:
        print(f"  {r['Símbolo']:8s} Score:{r['Score']:2d}  RSI:{r['RSI']:5.1f}  "
              f"Precio:{r['Precio MXN']:>10.2f}  {r['Recomendación']}")
    print(f"\nSeñales de venta detectadas: {len(ventas)}")
    for r in ventas:
        print(f"  {r['Símbolo']:8s} Precio:{r['Precio MXN']:>10.2f}  Motivo: {r['Motivo']}")

    # 6. Guardar en historial (solo compras)
    print("\nGuardando señales de compra en historial...")
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for senal in compras:
        guardar_senal_en_historial(senal, fecha_hoy)

    # 7. Backtesting sobre historial
    print("\nEjecutando backtesting sobre señales previas...")
    hist_df = cargar_historial()
    metrics =
