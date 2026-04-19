# ============================================================
# SCANNER DE TRADING AUTÓNOMO 24/7
# Versión corregida v3.6: Sin filtro de volumen, logs mejorados
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
# CONFIGURACIÓN (variables de entorno)
# ============================================================

EMAIL_REMITENTE = os.environ.get("EMAIL_REMITENTE", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_DESTINO = "alopez.uci@gmail.com"

WHATSAPP_NUMERO = os.environ.get("WHATSAPP_NUMERO", "")
WHATSAPP_APIKEY = os.environ.get("WHATSAPP_APIKEY", "")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Persistencia GitHub
GHU_GIST_TOKEN = os.environ.get("GHU_GIST_TOKEN", "")
REPO_OWNER = "alopezuci-arch"
REPO_NAME = "trading-app-3.1"
DATA_PATH = "data"

# Parámetros de Trading
SCORE_MINIMO = 7
CAPITAL_TRADING = 100_000
RIESGO_PCT = 1.0
MAX_WORKERS = 20
CACHE_DIR = "cache_ia"
CACHE_TTL = 3600
HISTORICO_FILE = "historial_senales.csv"
POSICIONES_FILE = "posiciones.json"

# ============================================================
# UNIVERSO DE ACTIVOS (incluye TECL)
# ============================================================

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

nasdaq100 = [
'ADBE','AMD','AMGN','AMZN','ASML','AVGO','BIIB','BKNG','CDNS','CHTR','CMCSA','COST','CSCO',
'CSX','CTAS','DXCM','EA','EBAY','EXC','FANG','FAST','FTNT','GILD','GOOGL','GOOG','HON','IDXX',
'ILMN','INTC','INTU','ISRG','KLAC','LRCX','LULU','MAR','MELI','META','MNST','MSFT','MU','NFLX',
'NVDA','NXPI','ODFL','ORLY','PANW','PAYX','PCAR','PEP','QCOM','REGN','ROST','SBUX','SNPS','TMUS',
'TSLA','TXN','VRTX','WBA','WDAY','XEL','ZM','ZS'
]

etfs_sectoriales = [
'XLK','XLV','XLF','XLE','XLI','XLY','XLP','XLU','XLB','XLRE','XLC',
'SOXX','ARKK','ARKG','ARKW','ARKF','CIBR','ROBO','ICLN','TAN','LIT',
'JETS','XHB','KRE','IBB','SPY','QQQ','IWM','DIA','VTI',
'TECL'  # ✅ TECL agregado
]

commodity_etfs = ['GLD','SLV','USO','UNG','DBC']

mining_oil = ['NEM','GOLD','FCX','XOM','CVX','COP','EOG','SLB']

ia_stocks = [
'NVDA','AMD','INTC','AI','PLTR','IBM','MSFT','GOOGL','META','SNOW','CRM','ADBE','NOW','ORCL',
'BIDU','BABA','SAP'
]

mid_cap_growth = [
'DDOG','NET','CRWD','ZS','BILL','DUOL','CELH','SMCI','HUBS','MNDY','APPN','PCTY','FIVN',
'RELY','PATH','SMAR','JAMF','EXAS','NVCR','FATE','RXRX','AFRM','UPST','HOOD','SQ','SOFI',
'NU','PLUG','CHPT','RIVN','LCID','KTOS','RKLB','ACHR'
]

etfs_emergentes = [
'EWZ','EWJ','FXI','KWEB','EWY','EWT','EWH','EWA','EWC','EWG','EWQ','EWU','VWO','EEM','INDA','EWX'
]

fibras_mex = [
'FMTY14.MX', 'FUNO11.MX', 'FIBRAPL14.MX','TERRA13.MX','DANHOS13.MX','FIBRAHD15.MX','FIBRAMQ12.MX'
]

bmv = [
'WALMEX.MX','GMEXICOB.MX','CEMEXCPO.MX','FEMSAUBD.MX','AMXL.MX','KOFUBL.MX','GFNORTEO.MX',
'BBAJIOO.MX','ALFA.MX','ALPEKA.MX','ASURB.MX','GAPB.MX','OMAB.MX','AC.MX','GCC.MX','LALA.MX',
'MEGA.MX','PINFRA.MX','TLEVISACPO.MX','VESTA.MX','GRUMA.MX','HERDEZ.MX','CUERVO.MX','ORBIA.MX',
'VOLARA.MX','Q.MX','LABB.MX','NEMAKA.MX'
]

ibex35 = [
'SAN.MC','BBVA.MC','TEF.MC','ITX.MC','IBE.MC','FER.MC','ENG.MC','ACS.MC','REP.MC','AENA.MC',
'CLNX.MC','GRF.MC','MTS.MC','MAP.MC','MEL.MC','CABK.MC','ELE.MC','IAG.MC','ANA.MC','VIS.MC',
'CIE.MC','LOG.MC','ACX.MC'
]

emergentes_acciones = [
'BABA','BIDU','JD','PDD','NTES','TCEHY','INFY','HDB','IBN','VALE','PBR','YPF','MELI','NU'
]

# Universo base
UNIVERSO_BASE = list(set(
    sp500 + nasdaq100 + etfs_sectoriales + commodity_etfs + mining_oil +
    ia_stocks + mid_cap_growth + etfs_emergentes + fibras_mex + bmv + ibex35 + emergentes_acciones
))

# ============================================================
# CORRECCIÓN: Conjunto de símbolos mexicanos SIN sufijo .MX
# ============================================================

mexicanos_con_sufijo = set(fibras_mex + bmv)
MEXICAN_SYMBOLS = {s.replace('.MX', '') for s in mexicanos_con_sufijo}

# ============================================================
# CAPA DE PERSISTENCIA — GitHub Repo
# ============================================================

def _gh_headers() -> dict:
    return {
        "Authorization": f"token {GHU_GIST_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def _repo_disponible() -> bool:
    return bool(GHU_GIST_TOKEN)

def _repo_leer(nombre: str) -> str:
    if not _repo_disponible():
        return ""
    try:
        import base64
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{DATA_PATH}/{nombre}"
        r = requests.get(url, headers=_gh_headers(), timeout=12)
        if r.status_code == 200:
            return base64.b64decode(r.json()["content"]).decode("utf-8")
    except Exception as e:
        print(f"⚠️ repo leer '{nombre}': {e}")
    return ""

def _repo_escribir(nombre: str, contenido: str, mensaje: str = "update") -> bool:
    if not _repo_disponible() or not contenido:
        return False
    import base64
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{DATA_PATH}/{nombre}"
        r_get = requests.get(url, headers=_gh_headers(), timeout=10)
        sha = r_get.json().get("sha", "") if r_get.status_code == 200 else ""
        payload = {
            "message": f"[scanner] {mensaje}",
            "content": base64.b64encode(contenido.encode("utf-8")).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=_gh_headers(), json=payload, timeout=15)
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"⚠️ repo escribir '{nombre}': {e}")
        return False

# ============================================================
# CARGA DE POSICIONES (normalización de claves)
# ============================================================
def cargar_posiciones_repo() -> dict:
    import os
    print("📌 Intentando cargar portafolio...")
    posiciones = {}

    # 1. Intentar cargar desde archivo local data/posiciones.json
    ruta_posiciones = os.path.join("data", "posiciones.json")
    if os.path.exists(ruta_posiciones):
        try:
            with open(ruta_posiciones, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        clave_limpia = k.upper().replace('.MX', '')
                        posiciones[clave_limpia] = float(v)
                    print(f" ✅ Portafolio cargado desde {ruta_posiciones} ({len(posiciones)} activos).")
                    return posiciones
        except Exception as e:
            print(f" ⚠️ Error leyendo {ruta_posiciones}: {e}")

    # 2. Intentar cargar desde data/transacciones.csv
    ruta_csv = os.path.join("data", "transacciones.csv")
    if os.path.exists(ruta_csv):
        try:
            df = pd.read_csv(ruta_csv)
            df['simbolo'] = df['simbolo'].str.upper().str.replace('.MX', '')
            df['tipo'] = df['tipo'].str.lower().str.strip()
            df['fecha'] = pd.to_datetime(df['fecha'])

            # Calcular cantidad neta por símbolo
            from collections import defaultdict
            neto = defaultdict(float)
            for _, row in df.iterrows():
                if row['tipo'] == 'compra':
                    neto[row['simbolo']] += row['cantidad']
                else:
                    neto[row['simbolo']] -= row['cantidad']

            for sim, cant in neto.items():
                if cant > 0.001:
                    # Obtener el último precio de compra (por si hubo múltiples compras)
                    compras_sim = df[(df['simbolo'] == sim) & (df['tipo'] == 'compra')].sort_values('fecha')
                    if not compras_sim.empty:
                        posiciones[sim] = float(compras_sim.iloc[-1]['precio'])
            print(f" ✅ Portafolio reconstruido desde {ruta_csv} ({len(posiciones)} activos).")
            return posiciones
        except Exception as e:
            print(f" ⚠️ Error leyendo {ruta_csv}: {e}")

    # 3. Fallback: intentar desde GitHub (usando DATA_PATH)
    if _repo_disponible():
        print("📡 Intentando cargar desde GitHub...")
        contenido_json = _repo_leer("posiciones.json")  # _repo_leer ya usa DATA_PATH
        if contenido_json and contenido_json.strip() not in ("", "{}", "null"):
            try:
                data = json.loads(contenido_json)
                if isinstance(data, dict):
                    for k, v in data.items():
                        clave_limpia = k.upper().replace('.MX', '')
                        posiciones[clave_limpia] = float(v)
                    print(f" ✅ Portafolio cargado desde GitHub ({len(posiciones)} activos).")
                    return posiciones
            except Exception as e:
                print(f" ⚠️ Error parseando posiciones.json de GitHub: {e}")

    print("ℹ️ Sin posiciones abiertas.")
    return posiciones    
# ============================================================
# HISTORIAL
# ============================================================

def cargar_historial_repo() -> pd.DataFrame:
    cols = ['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales']
    contenido = _repo_leer("historial_senales.csv")

    if contenido and len(contenido) > 60:
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(contenido))
            df['fecha'] = pd.to_datetime(df['fecha'])
            df.to_csv(HISTORICO_FILE, index=False)
            print(f"📊 Historial cargado: {len(df)} señales")
            return df
        except Exception as e:
            print(f"⚠️ Error cargando historial: {e}")

    return pd.DataFrame(columns=cols)

def sincronizar_historial_repo():
    if not _repo_disponible() or not os.path.exists(HISTORICO_FILE):
        return
    try:
        with open(HISTORICO_FILE, 'r', encoding='utf-8') as f:
            contenido = f.read()
        _repo_escribir("historial_senales.csv", contenido, "sincronizar historial")
        print("☁️ Historial sincronizado con repo")
    except Exception as e:
        print(f"⚠️ Error sincronizando historial: {e}")

# ============================================================
# CARGA Y SINCRONIZACIÓN DE CACHÉ IA
# ============================================================

def cargar_cache_ia_repo():
    os.makedirs(CACHE_DIR, exist_ok=True)
    contenido = _repo_leer("cache_ia_index.json")

    if contenido:
        try:
            cache_index = json.loads(contenido)
            ahora = time.time()

            for key, entry in cache_index.items():
                if ahora - entry.get('timestamp', 0) < CACHE_TTL:
                    ruta = f"{CACHE_DIR}/{key}.json"
                    with open(ruta, 'w', encoding='utf-8') as f:
                        json.dump(entry, f, ensure_ascii=False)
            print("🧠 Caché IA restaurado")
        except:
            pass

def sincronizar_cache_ia_repo():
    if not _repo_disponible() or not os.path.exists(CACHE_DIR):
        return
    try:
        cache_index = {}
        for fname in os.listdir(CACHE_DIR):
            if fname.endswith('.json'):
                with open(f"{CACHE_DIR}/{fname}", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if time.time() - data.get('timestamp', 0) < CACHE_TTL:
                    cache_index[fname.replace('.json', '')] = data

        if cache_index:
            _repo_escribir("cache_ia_index.json", json.dumps(cache_index), "sincronizar cache IA")
            print("☁️ Caché IA sincronizado")

    except Exception as e:
        print(f"⚠️ Error sincronizando caché IA: {e}")

# ============================================================
# INDICADORES, SCORING, MARKET REGIME
# ============================================================

def calcular_indicadores(hist: pd.DataFrame) -> pd.DataFrame:
    hist = hist.copy()

    hist['EMA20'] = hist['Close'].ewm(span=20, adjust=False).mean()
    hist['EMA50'] = hist['Close'].ewm(span=50, adjust=False).mean()

    delta = hist['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    hist['RSI'] = 100 - (100 / (1 + gain / loss))

    hist['EMA12'] = hist['Close'].ewm(span=12, adjust=False).mean()
    hist['EMA26'] = hist['Close'].ewm(span=26, adjust=False).mean()
    hist['MACD'] = hist['EMA12'] - hist['EMA26']
    hist['MACD_sig'] = hist['MACD'].ewm(span=9, adjust=False).mean()
    hist['MACD_hist'] = hist['MACD'] - hist['MACD_sig']

    hl = hist['High'] - hist['Low']
    hc = (hist['High'] - hist['Close'].shift()).abs()
    lc = (hist['Low'] - hist['Close'].shift()).abs()
    hist['ATR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

    hist['BB_mid'] = hist['Close'].rolling(20).mean()
    bb_std = hist['Close'].rolling(20).std()
    hist['BB_upper'] = hist['BB_mid'] + 2 * bb_std
    hist['BB_lower'] = hist['BB_mid'] - 2 * bb_std
    hist['BB_pct'] = (hist['Close'] - hist['BB_lower']) / (hist['BB_upper'] - hist['BB_lower'])

    low14 = hist['Low'].rolling(14).min()
    high14 = hist['High'].rolling(14).max()
    hist['STOCH_K'] = 100 * (hist['Close'] - low14) / (high14 - low14)
    hist['STOCH_D'] = hist['STOCH_K'].rolling(3).mean()

    hist['Vol_avg'] = hist['Volume'].rolling(20).mean()

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
            return {'regime': 'DESCONOCIDO', 'score_bonus': 0, 'precio': 0, 'ema200': 0,
                    'ret_1m': 0, 'rsi_sp500': 0, 'descripcion': 'Sin datos'}

        precio = sp['Close'].iloc[-1]
        ema200 = sp['Close'].ewm(span=200).mean().iloc[-1]
        ema50 = sp['Close'].ewm(span=50).mean().iloc[-1]

        ret_1m = (precio / sp['Close'].iloc[-20] - 1) * 100 if len(sp) >= 20 else 0

        delta = sp['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_sp500 = 100 - (100 / (1 + rs)).iloc[-1] if not loss.empty else 50

        if precio > ema200 and precio > ema50 and ema50 > ema200:
            return {'regime': 'ALCISTA', 'score_bonus': 0, 'precio': precio, 'ema200': ema200,
                    'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1),
                    'descripcion': 'S&P 500 sobre EMA50 y EMA200 — condiciones favorables'}

        elif precio > ema200:
            return {'regime': 'LATERAL', 'score_bonus': -1, 'precio': precio, 'ema200': ema200,
                    'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1),
                    'descripcion': 'Ser selectivo'}

        else:
            return {'regime': 'BAJISTA', 'score_bonus': -3, 'precio': precio, 'ema200': ema200,
                    'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1),
                    'descripcion': 'Mercado bajista — evitar nuevas compras'}

    except:
        return {'regime': 'DESCONOCIDO', 'score_bonus': 0, 'precio': 0, 'ema200': 0,
                'ret_1m': 0, 'rsi_sp500': 0, 'descripcion': 'Error al obtener datos'}

def position_size(precio: float, atr: float) -> dict:
    riesgo_mxn = CAPITAL_TRADING * (RIESGO_PCT / 100)
    stop_dist = 2 * atr

    if stop_dist <= 0:
        return {'unidades': 0, 'inversion': 0}

    unidades = riesgo_mxn / stop_dist
    inversion = min(unidades * precio, CAPITAL_TRADING * 0.20)
    unidades = inversion / precio

    return {'unidades': round(unidades, 2), 'inversion': round(inversion, 2)}

# ============================================================
# FUNCIÓN ANALIZAR (SIN FILTRO DE VOLUMEN, CON LOGS OPCIONALES)
# ============================================================

def analizar(args) -> dict | None:
    simbolo, usd_mxn, eur_mxn, regime_bonus, posiciones = args
    debug = simbolo in ['T', 'AMD', 'TECL']  # activar logs para estos

    try:
        if debug:
            print(f"\n🔍 Analizando {simbolo}...")
            print(f"   posiciones.keys() = {list(posiciones.keys())}")
            print(f"   usd_mxn={usd_mxn}, eur_mxn={eur_mxn}")

        # Determinar tipo de cambio
        if simbolo.endswith('.MX'):
            factor = 1.0
        elif simbolo.endswith('.MC'):
            factor = eur_mxn
        else:
            factor = usd_mxn

        ticker = yf.Ticker(simbolo)
        hist = ticker.history(period="6mo")  # Cambiado a 6 meses para más datos
        if hist.empty:
            if debug: print(f"   ❌ hist vacío")
            return None
        if debug: print(f"   ✅ hist obtenido, len={len(hist)}")

        # Convertir a MXN
        for col in ['Open', 'High', 'Low', 'Close']:
            hist[col] = hist[col] * factor

        hist = calcular_indicadores(hist)
        hist = hist.dropna(subset=['RSI', 'MACD', 'EMA20', 'EMA50', 'ATR', 'STOCH_K', 'STOCH_D'])
        if len(hist) < 2:
            if debug: print(f"   ❌ después de dropna, hist tiene solo {len(hist)} filas")
            return None

        ultimo = hist.iloc[-1].to_dict()
        penultimo = hist.iloc[-2].to_dict()
        precio_actual = ultimo['Close']
        atr = ultimo['ATR']

        if debug:
            print(f"   precio_actual (MXN) = {precio_actual:.2f}")
            print(f"   ATR = {atr:.2f}")

        score_base, señales = calcular_score(ultimo, penultimo)
        score = max(0, score_base + regime_bonus)

        ps = position_size(precio_actual, atr)

        simbolo_limpio = simbolo.replace('.MX', '')
        precio_compra = posiciones.get(simbolo_limpio)
        if debug:
            print(f"   simbolo_limpio = {simbolo_limpio}")
            print(f"   precio_compra = {precio_compra}")

        recomendacion = "EVITAR"
        motivo = ""
        senales_venta = []

        # Lógica de venta
        if precio_compra is not None:
            ganancia_pct = ((precio_actual / precio_compra) - 1) * 100
            if debug:
                print(f"   ganancia_pct = {ganancia_pct:.2f}%")
            if ganancia_pct >= 15:
                recomendacion = "VENDER"
                motivo = f"🎯 Take Profit +{ganancia_pct:.1f}%"
                senales_venta.append(motivo)
                print(f"🔔 Venta detectada: {simbolo_limpio} - {motivo}")
            elif ganancia_pct <= -7:
                recomendacion = "VENDER"
                motivo = f"🛑 Stop Loss {ganancia_pct:.1f}%"
                senales_venta.append(motivo)
                print(f"🔔 Venta detectada: {simbolo_limpio} - {motivo}")
        else:
            if debug:
                print(f"   ⚠️ No hay precio de compra para {simbolo_limpio}")

        # Lógica de compra solo si no es venta
        if recomendacion != "VENDER":
            if score >= 8:
                recomendacion = "COMPRAR ★★★"
                motivo = f"Score {score}/14"
            elif score >= 6:
                recomendacion = "COMPRAR ★★"
                motivo = f"Score {score}/14"
            elif score >= 4:
                recomendacion = "OBSERVAR"
                motivo = f"Score {score}/14"
            else:
                recomendacion = "EVITAR"
                motivo = f"Score {score}/14"

        resultado = {
            'Símbolo': simbolo_limpio,
            'Precio MXN': round(precio_actual, 2),
            'Score': score,
            'RSI': round(ultimo['RSI'], 1),
            'ATR': round(atr, 2),
            'Stop Loss': round(precio_actual - 2 * atr, 2),
            'Take Profit': round(precio_actual + 3 * atr, 2),
            'Unidades': ps['unidades'],
            'Inversión MXN': ps['inversion'],
            '% Capital': round((ps['inversion'] / CAPITAL_TRADING) * 100, 1),
            'Dist EMA50': round((precio_actual / ultimo['EMA50'] - 1) * 100, 2),
            'Recomendación': recomendacion,
            'Motivo': motivo,
            'Señales': " | ".join(señales + senales_venta)
        }
        return resultado

    except Exception as e:
        if debug:
            print(f"   ❌ Excepción: {e}")
        return None

# ============================================================
# HISTORIAL, IA Y ALERTAS
# ============================================================

def guardar_senal_en_historial(senal: dict, fecha: str):
    if os.path.exists(HISTORICO_FILE):
        df = pd.read_csv(HISTORICO_FILE)
        df['fecha'] = pd.to_datetime(df['fecha'])
    else:
        df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales'])

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

def backtest_historial(df_hist: pd.DataFrame) -> dict:
    if df_hist.empty:
        return {'win_rate': 0, 'ret_prom': 0, 'total': 0}

    VENTANA_BT = 5
    resultados = []

    df_compras = df_hist[df_hist['recomendacion'].str.startswith('COMPRAR')].copy()

    for _, row in df_compras.iterrows():
        try:
            ticker = yf.Ticker(row['simbolo'])
            start_date = row['fecha']
            end_date = row['fecha'] + timedelta(days=VENTANA_BT*2)

            hist = ticker.history(start=start_date, end=end_date)
            if hist.empty or len(hist) < VENTANA_BT:
                continue

            precio_entrada = row['precio']
            precio_salida = hist['Close'].iloc[min(VENTANA_BT, len(hist)-1)]

            retorno = (precio_salida / precio_entrada - 1) * 100
            resultados.append(retorno)

        except:
            continue

    if resultados:
        win_rate = sum(1 for r in resultados if r > 0) / len(resultados) * 100
        ret_prom = np.mean(resultados)
        return {'win_rate': round(win_rate, 1), 'ret_prom': round(ret_prom, 2), 'total': len(resultados)}

    return {'win_rate': 0, 'ret_prom': 0, 'total': 0}

# ============================================================
# IA (sin cambios relevantes)
# ============================================================

def _calcular_hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()

def _guardar_cache_ia(prompt: str, respuesta: str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = _calcular_hash_prompt(prompt)
    with open(f"{CACHE_DIR}/{key}.json", 'w', encoding='utf-8') as f:
        json.dump({'timestamp': time.time(), 'prompt': prompt, 'respuesta': respuesta},
                  f, ensure_ascii=False, indent=2)

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
            print(f" ⚠️ {proveedor} intento {intento+1}/{max_retries} falló: {e}")

        if intento == max_retries - 1:
            raise

        time.sleep(2 ** intento)

    raise RuntimeError(f"No IA disponible de {proveedor}")

def _ia_gemini(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)

    if resp.status_code == 200:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    raise RuntimeError(f"Gemini {resp.status_code}")

def _ia_groq(prompt: str) -> str:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile",
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 800},
        timeout=30
    )

    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]

    raise RuntimeError(f"Groq {resp.status_code}")

def _ia_anthropic(prompt: str) -> str:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"Content-Type": "application/json",
                 "x-api-key": ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01"},
        json={"model": "claude-sonnet-4-20250514",
              "max_tokens": 800,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=30
    )

    if resp.status_code == 200:
        return resp.json()["content"][0]["text"]

    raise RuntimeError(f"Anthropic {resp.status_code}")

def _construir_prompt(oportunidades: list[dict], regime: dict, usd_mxn: float,
                      posiciones: dict, ventas: list[dict]) -> str:

    portfolio_str = "\n".join(
        [f"- {sym}: Comprado a {px}" for sym, px in posiciones.items()]
    ) if posiciones else "Sin posiciones abiertas."

    ventas_str = "\n".join(
        [f"- {v['Símbolo']}: {v['Motivo']}" for v in ventas[:5]]
    ) if ventas else "Ninguna"

    prompt = f"""
Eres un estratega cuantitativo.

Contexto: Régimen {regime['regime']}, USD/MXN: {usd_mxn:.2f}

PORTAFOLIO ACTUAL:
{portfolio_str}

SEÑALES DE VENTA (prioritarias):
{ventas_str}

NUEVAS OPORTUNIDADES DE COMPRA:
{json.dumps(oportunidades[:10], indent=2)}

TAREA:
1. Analiza si las nuevas compras complementan o aumentan riesgo.
2. Si alguna venta es crítica, indícalo.
3. Da un plan de acción concreto.

Respuesta breve en español.
"""
    return prompt

def analisis_ia(oportunidades: list[dict], regime: dict, usd_mxn: float,
                posiciones: dict, ventas: list[dict]) -> str:

    if not oportunidades and not ventas:
        return ""

    prompt = _construir_prompt(oportunidades, regime, usd_mxn, posiciones, ventas)

    cache = _obtener_cache_ia(prompt)
    if cache:
        print(" ✅ Análisis IA desde caché")
        return cache

    if GEMINI_API_KEY:
        try:
            texto = _llamar_ia_con_reintentos("Gemini", prompt)
            _guardar_cache_ia(prompt, texto)
            return texto
        except:
            pass

    if GROQ_API_KEY:
        try:
            texto = _llamar_ia_con_reintentos("Groq", prompt)
            _guardar_cache_ia(prompt, texto)
            return texto
        except:
            pass

    return ""

# ============================================================
# ALERTAS
# ============================================================

def enviar_email(asunto: str, html: str) -> bool:
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD:
        print("❌ Email no configurado (faltan credenciales)")
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
        return False

    try:
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": WHATSAPP_NUMERO,
                    "apikey": WHATSAPP_APIKEY,
                    "text": mensaje},
            timeout=10
        )

        print(f"{'✅' if r.status_code==200 else '❌'} WhatsApp: {r.status_code}")
        return r.status_code == 200

    except Exception as e:
        print(f"❌ Error WhatsApp: {e}")
        return False

def construir_email(ops_compras: list[dict], ops_ventas: list[dict],
                    regime: dict, ia_texto: str, hora: str) -> str:

    filas_compras = "".join([
        f"<tr><td><b>{o['Símbolo']}</b></td><td>${o['Precio MXN']:,.2f}</td>"
        f"<td>{o['Score']}</td><td>${o['Stop Loss']:,.2f}</td>"
        f"<td>${o['Inversión MXN']:,.0f}</td><td>{o['Recomendación']}</td></tr>"
        for o in ops_compras
    ])

    filas_ventas = "".join([
        f"<tr><td><b>{o['Símbolo']}</b></td><td>${o['Precio MXN']:,.2f}</td>"
        f"<td>{o['Motivo']}</td></tr>"
        for o in ops_ventas
    ])

    bloque_ia = f"""
    <h3 style="color:#7b61ff">🤖 Análisis de IA</h3>
    <div style="background:#f5f3ff;padding:12px;border-left:4px solid #7b61ff;">
    {ia_texto.replace(chr(10),'<br>')}
    </div>
    """ if ia_texto else ""

    icono_regime = {
        'ALCISTA':'🟢',
        'LATERAL':'🟡',
        'BAJISTA':'🔴'
    }.get(regime['regime'],'⚪')

    return f"""
<html><body style="font-family:Arial;max-width:700px;margin:auto">

<h2 style="color:#1a73e8">📈 Scanner Trading Real — {hora}</h2>

<p style="background:#f1f3f4;padding:10px;">
{icono_regime} Régimen S&P 500: <b>{regime['regime']}</b> | S&P: {regime['precio']:,.0f}
</p>

<h3 style="color:#ea4335">🔴 VENTAS ({len(ops_ventas)})</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;width:100%">
<tr style="background:#fce8e6"><th>Símbolo</th><th>Precio MXN</th><th>Motivo</th></tr>
{filas_ventas}
</table>

<h3 style="color:#34a853">🟢 COMPRAS ({len(ops_compras)})</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;width:100%">
<tr style="background:#e6f4ea"><th>Símbolo</th><th>Precio MXN</th><th>Score</th><th>Stop Loss</th><th>Inversión</th><th>Recomendación</th></tr>
{filas_compras}
</table>

{bloque_ia}

</body></html>
"""

# ============================================================
# EJECUCIÓN PRINCIPAL DEL SCANNER
# ============================================================

def ejecutar_scanner():

    print("🚀 Iniciando scanner 24/7...")

    # 1. Cargar posiciones reales
    posiciones = cargar_posiciones_repo()
    print(f"📊 Posiciones activas: {list(posiciones.keys())}")

    # 2. Cargar historial
    historial = cargar_historial_repo()

    # 3. Cargar caché IA
    cargar_cache_ia_repo()

    # 4. Obtener régimen de mercado
    regime = obtener_market_regime()
    regime_bonus = regime.get('score_bonus', 0)

    # 5. Obtener tipo de cambio USD/MXN y EUR/MXN
    try:
        usd_mxn = yf.Ticker("MXN=X").history(period="1d")['Close'].iloc[-1]
        eur_mxn = yf.Ticker("EURMXN=X").history(period="1d")['Close'].iloc[-1]
    except:
        usd_mxn = 20.0
        eur_mxn = 21.5

    print(f"💱 USD/MXN = {usd_mxn:.2f}, EUR/MXN = {eur_mxn:.2f}")

    # 6. Construir lista de símbolos: universo base + todas las posiciones
    simbolos_unicos = set(UNIVERSO_BASE) | set(posiciones.keys())
    lista_simbolos = list(simbolos_unicos)
    print(f"📈 Analizando {len(lista_simbolos)} símbolos (incluye {len(posiciones)} posiciones)")

    # 7. Ejecutar análisis en paralelo
    args_list = [(sim, usd_mxn, eur_mxn, regime_bonus, posiciones) for sim in lista_simbolos]

    resultados = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(analizar, args) for args in args_list]
        for f in as_completed(futures):
            r = f.result()
            if r:
                resultados.append(r)

    print(f"🔍 Total resultados obtenidos: {len(resultados)}")

    # 8. Separar compras y ventas
    ops_ventas = [r for r in resultados if r['Recomendación'] == "VENDER"]
    ops_compras = [r for r in resultados if r['Recomendación'].startswith("COMPRAR")]

    print(f"🟢 Compras: {len(ops_compras)}")
    print(f"🔴 Ventas: {len(ops_ventas)}")
    for v in ops_ventas:
        print(f"   ✅ {v['Símbolo']} - {v['Motivo']}")

    # 9. Guardar historial
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for senal in resultados:
        guardar_senal_en_historial(senal, fecha)

    sincronizar_historial_repo()
    sincronizar_cache_ia_repo()

    # 10. IA
    ia_texto = ""
    if ops_compras or ops_ventas:
        ia_texto = analisis_ia(ops_compras, regime, usd_mxn, posiciones, ops_ventas)

    # 11. Construir email
    hora = datetime.now().strftime("%d/%m %H:%M")
    html = construir_email(ops_compras, ops_ventas, regime, ia_texto, hora)

    # 12. Enviar email
    enviar_email("📈 Scanner Trading — Actualización", html)

       # 13. Enviar WhatsApp (formato completo, similar al antiguo de app.py)
    
        if ops_compras or ops_ventas:
        # Calcular top 3 compras (por score)
        top_compras = sorted(ops_compras, key=lambda x: x['Score'], reverse=True)[:3]
        top_nombres = [c['Símbolo'] for c in top_compras] if top_compras else ["ninguna"]
        
        # Determinar confianza básica basada en número de compras/ventas y régimen
        if regime['regime'] == 'ALCISTA' and len(ops_compras) > 10:
            confianza = "ALTA"
        elif regime['regime'] == 'LATERAL' or len(ops_compras) > 5:
            confianza = "MEDIA"
        else:
            confianza = "BAJA"
        
        # Construir mensaje
        mensaje = (
            f"📊 *Scanner Trading* – {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            f"📈 Régimen: {regime['regime']} | USD/MXN: {usd_mxn:.2f}\n\n"
            f"🟢 *Compras*: {len(ops_compras)} (Top: {', '.join(top_nombres)})\n"
            f"🔴 *Ventas*: {len(ops_ventas)}\n"
        )
        # Si hay ventas, agregar detalles
        if ops_ventas:
            mensaje += "\n*Ventas detectadas:*\n"
            for v in ops_ventas[:5]:  # máximo 5 para no exceder límite de WhatsApp
                mensaje += f"  • {v['Símbolo']}: {v['Motivo']}\n"
        
        mensaje += f"\n🎯 Confianza: {confianza}\n"
        mensaje += "📧 Ver detalles en tu email"
        
        enviar_whatsapp(mensaje)

    print("✅ Scanner finalizado.")

# ============================================================
# EJECUCIÓN DIRECTA
# ============================================================

if __name__ == "__main__":
    ejecutar_scanner()
