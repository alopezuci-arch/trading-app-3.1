# ============================================================
# SCANNER DE TRADING AUTÓNOMO 24/7
# Versión corregida v3.2: Prioriza Alertas de Venta Técnicas
# basadas en Portafolio Real. Corregida la normalización de
# símbolos mexicanos y la conversión de moneda.
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
EMAIL_REMITENTE   = os.environ.get("EMAIL_REMITENTE",   "")
EMAIL_PASSWORD    = os.environ.get("EMAIL_PASSWORD",    "")
EMAIL_DESTINO     = "alopez.uci@gmail.com"
WHATSAPP_NUMERO   = os.environ.get("WHATSAPP_NUMERO", "")
WHATSAPP_APIKEY   = os.environ.get("WHATSAPP_APIKEY", "")

GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY",    "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY",      "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Persistencia GitHub
GHU_GIST_TOKEN = os.environ.get("GHU_GIST_TOKEN", "")
REPO_OWNER     = "alopezuci-arch"
REPO_NAME      = "trading-app-3.1"
DATA_PATH      = "data"

# Parámetros de Trading
SCORE_MINIMO     = 7
CAPITAL_TRADING  = 100_000
RIESGO_PCT       = 1.0
MAX_WORKERS      = 20
CACHE_DIR        = "cache_ia"
CACHE_TTL        = 3600
HISTORICO_FILE   = "historial_senales.csv"
POSICIONES_FILE  = "posiciones.json"

# ============================================================
# UNIVERSO DE ACTIVOS (Se mantiene igual)
# ============================================================
# (... Mantener las listas sp500, nasdaq100, etfs, bmv, etc. igual que en tu archivo subido ...)
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
    'JETS','XHB','KRE','IBB','SPY','QQQ','IWM','DIA','VTI'
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

# Unir todos los universos en una sola lista (sin duplicados)
UNIVERSO = list(set(
    sp500 + nasdaq100 + etfs_sectoriales + commodity_etfs + mining_oil + 
    ia_stocks + mid_cap_growth + etfs_emergentes + fibras_mex + bmv + ibex35 + emergentes_acciones
))

# ============================================================
# CORRECCIÓN: Conjunto de símbolos mexicanos SIN sufijo .MX
# para identificar activos que no requieren conversión USD/MXN
# ============================================================
mexicanos_con_sufijo = set(fibras_mex + bmv)
MEXICAN_SYMBOLS = {s.replace('.MX', '') for s in mexicanos_con_sufijo}

# UNIVERSO original (con .MX incluido)
UNIVERSO = list(set(
    sp500 + nasdaq100 + etfs_sectoriales + commodity_etfs + mining_oil +
    ia_stocks + mid_cap_growth + etfs_emergentes + fibras_mex + bmv + ibex35 + emergentes_acciones
))

# ============================================================
# CAPA DE PERSISTENCIA — GitHub Repo (sin cambios)
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
        print(f"⚠️  repo leer '{nombre}': {e}")
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
        print(f"⚠️  repo escribir '{nombre}': {e}")
        return False

# ============================================================
# CARGA DE POSICIONES (con normalización de claves)
# ============================================================
def cargar_posiciones_repo() -> dict:
    print("📌 Intentando cargar portafolio desde data/posiciones.json...")
    contenido_json = _repo_leer("posiciones.json")
    posiciones_json = {}

    if contenido_json and contenido_json.strip() not in ("", "{}", "null"):
        try:
            data = json.loads(contenido_json)
            if isinstance(data, dict) and data:
                # Normalizar: eliminar .MX de las claves
                posiciones_json = {}
                for k, v in data.items():
                    clave_limpia = k.upper().replace('.MX', '')
                    posiciones_json[clave_limpia] = float(v)
                print(f"  ✅ Portafolio JSON cargado ({len(posiciones_json)} activos).")
        except Exception as e:
            print(f"  ⚠️ Error parseando posiciones.json: {e}")

    # Respaldo desde transacciones.csv
    print("📌 Validando portafolio contra data/transacciones.csv...")
    csv_contenido = _repo_leer("transacciones.csv")
    posiciones_reconstruidas = {}

    if csv_contenido and len(csv_contenido) > 60:
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(csv_contenido))
            df['simbolo'] = df['simbolo'].str.upper().str.replace('.MX', '')
            df['tipo'] = df['tipo'].str.lower().str.strip()
            df['fecha'] = pd.to_datetime(df['fecha'])

            df_compras = df[df['tipo'] == 'compra'].groupby('simbolo')['cantidad'].sum()
            df_ventas = df[df['tipo'] == 'venta'].groupby('simbolo')['cantidad'].sum()
            df_neto = pd.DataFrame({'compras': df_compras, 'ventas': df_ventas}).fillna(0)
            df_neto['cantidad_actual'] = df_neto['compras'] - df_neto['ventas']
            acciones_abiertas = df_neto[df_neto['cantidad_actual'] > 0.001].index.tolist()

            for sim in acciones_abiertas:
                ultimo_trade_compra = df[
                    (df['simbolo'] == sim) & (df['tipo'] == 'compra')
                ].sort_values('fecha').iloc[-1]
                posiciones_reconstruidas[sim] = float(ultimo_trade_compra['precio'])
            print(f"  ✅ Portafolio reconstruido desde transacciones.csv ({len(posiciones_reconstruidas)} activos).")
        except Exception as e:
            print(f"  ❌ Error reconstruyendo portafolio desde CSV: {e}")

    # Decidir la fuente de verdad
    if not posiciones_json and posiciones_reconstruidas:
        print("⚠️ data/posiciones.json vacío. Sincronizando con CSV...")
        contenido_guardar = json.dumps(posiciones_reconstruidas, indent=2, ensure_ascii=False)
        _repo_escribir("posiciones.json", contenido_guardar, "sincronizar desde CSV")
        return posiciones_reconstruidas
    elif posiciones_json and posiciones_reconstruidas:
        # Limpiar vendidos
        set_json = set(posiciones_json.keys())
        set_csv = set(posiciones_reconstruidas.keys())
        acciones_a_borrar = set_json - set_csv
        if acciones_a_borrar:
            print(f"⚠️ Limpiando {len(acciones_a_borrar)} acciones vendidas del JSON.")
            for sim in acciones_a_borrar:
                del posiciones_json[sim]
            _repo_escribir("posiciones.json", json.dumps(posiciones_json, indent=2), "limpiar vendidos")
        return posiciones_json
    elif not posiciones_json and not posiciones_reconstruidas:
        print("ℹ️ Sin posiciones abiertas.")
        return {}
    return posiciones_json

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
# INDICADORES, SCORING, MARKET REGIME (sin cambios)
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
    stop_dist = 2 * atr
    if stop_dist <= 0:
        return {'unidades': 0, 'inversion': 0}
    unidades = riesgo_mxn / stop_dist
    inversion = min(unidades * precio, CAPITAL_TRADING * 0.20)
    unidades = inversion / precio
    return {'unidades': round(unidades, 2), 'inversion': round(inversion, 2)}

# ============================================================
# FUNCIÓN DE ANÁLISIS (corregida: conversión de moneda y ventas)
# ============================================================
def analizar(args: tuple) -> dict | None:
    simbolo, usd_mxn, regime_bonus, posiciones = args
    try:
        # Descargar datos históricos (el símbolo puede ser sin .MX, pero yfinance acepta)
        hist = yf.Ticker(simbolo).history(period="3mo")
        if hist.empty or len(hist) < 55:
            return None

        # Determinar factor de conversión a MXN usando MEXICAN_SYMBOLS global
        if simbolo in MEXICAN_SYMBOLS:
            factor = 1.0
        else:
            factor = usd_mxn

        for c in ['Close','Open','High','Low']:
            hist[c] *= factor

        hist = calcular_indicadores(hist)
        hist = hist.dropna(subset=['RSI','MACD','EMA20','EMA50','ATR','STOCH_K','STOCH_D'])
        if len(hist) < 2:
            return None

        r = hist.iloc[-1].to_dict()
        p = hist.iloc[-2].to_dict()
        precio = r['Close']
        atr = r['ATR']

        # ========== LÓGICA DE VENTA ==========
        if simbolo in posiciones:
            precio_compra_original = posiciones[simbolo]
            # El precio de compra ya está almacenado en MXN (por normalización)
            # pero si no, aseguramos conversión:
            if simbolo not in MEXICAN_SYMBOLS:
                precio_compra_mxn = precio_compra_original * usd_mxn
            else:
                precio_compra_mxn = precio_compra_original

            ganancia_pct = ((precio / precio_compra_mxn) - 1) * 100
            motivo_venta = ""

            if ganancia_pct >= 20:
                motivo_venta = f"🎯 Take Profit alcanzado (+{ganancia_pct:.1f}%)"
            elif ganancia_pct <= -8:
                motivo_venta = f"🛑 Stop Loss activado ({ganancia_pct:.1f}%)"
            elif r['RSI'] > 75:
                motivo_venta = f"⚠️ RSI Sobrecarga Técnica ({r['RSI']:.0f})"
            elif r['Close'] < r['EMA50'] and p['Close'] >= p['EMA50']:
                motivo_venta = "📉 Precio rompió EMA50 hacia abajo"
            elif r['MACD'] < r['MACD_sig'] and p['MACD'] >= p['MACD_sig']:
                motivo_venta = "❌ Cruce bajista MACD"
            else:
                score_base, _ = calcular_score(r, p)
                score_actual = max(0, score_base + regime_bonus)
                if score_actual < 4:
                    motivo_venta = f"📉 Score deteriorado ({score_actual}/14)"

            if motivo_venta:
                return {
                    'Símbolo': simbolo,
                    'Precio MXN': round(precio, 2),
                    'Recomendación': "VENDER",
                    'Motivo': motivo_venta,
                    'Score': 0, 'RSI': round(r['RSI'], 1), 'ATR': 0, 'Stop Loss': 0, 'Take Profit': 0,
                    'Unidades': 0, 'Inversión MXN': 0, 'Señales': ""
                }
            else:
                return None

        # ========== LÓGICA DE COMPRA ==========
        score_base, señales = calcular_score(r, p)
        score = max(0, score_base + regime_bonus)
        if score < SCORE_MINIMO:
            return None

        ps = position_size(precio, atr)

        if score >= 10:
            rec = "COMPRAR ★★★"
        elif score >= 8:
            rec = "COMPRAR ★★"
        else:
            rec = "COMPRAR"

        return {
            'Símbolo': simbolo,
            'Precio MXN': round(precio, 2),
            'Score': score,
            'RSI': round(r['RSI'], 1),
            'ATR': round(atr, 2),
            'Stop Loss': round(precio - 2 * atr, 2),
            'Take Profit': round(precio + 3 * atr, 2),
            'Unidades': ps['unidades'],
            'Inversión MXN': ps['inversion'],
            'Señales': " | ".join(señales),
            'Recomendación': rec,
            'Motivo': f"Score {score}/14"
        }

    except Exception as e:
        return None

# ============================================================
# HISTORIAL, IA Y ALERTAS (funciones auxiliares)
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

# Funciones de IA (sin cambios)
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
            print(f"  ⚠️ {proveedor} intento {intento+1}/{max_retries} falló: {e}")
            if intento == max_retries - 1: raise
            time.sleep(2 ** intento)
    raise RuntimeError(f"No IA disponible de {proveedor}")

def _ia_gemini(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
    if resp.status_code == 200:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError(f"Gemini {resp.status_code}")

def _ia_groq(prompt: str) -> str:
    resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": 800}, timeout=30)
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError(f"Groq {resp.status_code}")

def _ia_anthropic(prompt: str) -> str:
    resp = requests.post("https://api.anthropic.com/v1/messages",
        headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json={"model": "claude-sonnet-4-20250514", "max_tokens": 800, "messages": [{"role": "user", "content": prompt}]}, timeout=30)
    if resp.status_code == 200:
        return resp.json()["content"][0]["text"]
    raise RuntimeError(f"Anthropic {resp.status_code}")

def _construir_prompt(oportunidades: list[dict], regime: dict, usd_mxn: float, posiciones: dict, ventas: list[dict]) -> str:
    portfolio_str = "\n".join([f"- {sym}: Comprado a {px}" for sym, px in posiciones.items()]) if posiciones else "Sin posiciones abiertas."
    ventas_str = "\n".join([f"- {v['Símbolo']}: {v['Motivo']}" for v in ventas[:5]]) if ventas else "Ninguna"
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

def analisis_ia(oportunidades: list[dict], regime: dict, usd_mxn: float, posiciones: dict, ventas: list[dict]) -> str:
    if not oportunidades and not ventas:
        return ""
    prompt = _construir_prompt(oportunidades, regime, usd_mxn, posiciones, ventas)
    cache = _obtener_cache_ia(prompt)
    if cache:
        print("  ✅ Análisis IA desde caché")
        return cache
    if GEMINI_API_KEY:
        try:
            texto = _llamar_ia_con_reintentos("Gemini", prompt)
            _guardar_cache_ia(prompt, texto)
            return texto
        except: pass
    if GROQ_API_KEY:
        try:
            texto = _llamar_ia_con_reintentos("Groq", prompt)
            _guardar_cache_ia(prompt, texto)
            return texto
        except: pass
    return ""

# Alertas
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
        print(f"✅ Email enviado a {EMAIL_DESTINO}")
        return True
    except Exception as e:   # <-- CORREGIDO: except Exception
        print(f"❌ Error email: {e}")
        return False

def enviar_whatsapp(mensaje: str) -> bool:
    if not WHATSAPP_NUMERO or not WHATSAPP_APIKEY:
        return False
    try:
        r = requests.get("https://api.callmebot.com/whatsapp.php",
            params={"phone": WHATSAPP_NUMERO, "apikey": WHATSAPP_APIKEY, "text": mensaje}, timeout=10)
        print(f"{'✅' if r.status_code==200 else '❌'} WhatsApp: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Error WhatsApp: {e}")
        return False

def construir_email(ops_compras: list[dict], ops_ventas: list[dict], regime: dict, ia_texto: str, hora: str) -> str:
    filas_compras = "".join([
        f"<tr><td><b>{o['Símbolo']}</b></td><td>${o['Precio MXN']:,.2f}</td>"
        f"<td>{o['Score']}</td><td>${o['Stop Loss']:,.2f}</td>"
        f"<td>${o['Inversión MXN']:,.0f}</td><td>{o['Recomendación']}</td></tr>"
        for o in ops_compras
    ])
    filas_ventas = "".join([
        f"<tr><td><b>{o['Símbolo']}</b></td><td>${o['Precio MXN']:,.2f}</td><td>{o['Motivo']}</td></tr>"
        for o in ops_ventas
    ])
    bloque_ia = f"""<h3 style="color:#7b61ff">🤖 Análisis de IA</h3>
        <div style="background:#f5f3ff;padding:12px;border-left:4px solid #7b61ff;">
          {ia_texto.replace(chr(10),'<br>')}
        </div>""" if ia_texto else ""
    icono_regime = {'ALCISTA':'🟢','LATERAL':'🟡','BAJISTA':'🔴'}.get(regime['regime'],'⚪')
    return f"""<html><body style="font-family:Arial;max-width:700px;margin:auto">
    <h2 style="color:#1a73e8">📈 Scanner Trading Real — {hora}</h2>
    <p style="background:#f1f3f4;padding:10px;">{icono_regime} Régimen S&P 500: <b>{regime['regime']}</b> | S&P: {regime['precio']:,.0f}</p>
    
    <h3 style="color:#ea4335">🔴 VENTAS ({len(ops_ventas)})</h3>
    <table border="1" cellpadding="6" style="border-collapse:collapse;width:100%">
      <tr style="background:#fce8e6"><th>Símbolo</th><th>Precio MXN</th><th>Motivo</th></tr>
      {filas_ventas if filas_ventas else '<tr><td colspan="3">Sin señales</td></tr>'}
    </table>

    {bloque_ia}
    
    <h3 style="color:#34a853">🟢 COMPRAS ({len(ops_compras)})</h3>
    <table border="1" cellpadding="6" style="border-collapse:collapse;width:100%">
      <tr style="background:#e8f5e9"><th>Símbolo</th><th>Precio</th><th>Score</th><th>Stop</th><th>Inversión</th><th>Rec.</th></tr>
      {filas_compras if filas_compras else '<tr><td colspan="6">Sin oportunidades</td></tr>'}
    </table>
    <p style="color:#999;font-size:11px;">Scanner v3.2 corregido</p>
    </body></html>"""

def obtener_noticias_recientes(ticker):
    try:
        asset = yf.Ticker(ticker)
        news = asset.news
        if not news:
            return "Sin noticias recientes."
        return " | ".join([n['title'] for n in news[:3]])
    except:
        return "No se pudieron cargar noticias."

# ============================================================
# MAIN (corregido)
# ============================================================
def main():
    hora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n{'='*50}")
    print(f"  Scanner Trading v3.2 (Corregido) — {hora}")
    print(f"{'='*50}\n")

    # Tipo de cambio
    try:
        usd_data = yf.Ticker("USDMXN=X").history(period="1d")
        usd_mxn = float(usd_data['Close'].iloc[-1]) if not usd_data.empty else 20.0
    except:
        usd_mxn = 20.0
    print(f"USD/MXN: {usd_mxn:.2f}")

    # Market regime
    regime = obtener_market_regime()
    print(f"Régimen SP500: {regime['regime']} (bonus: {regime['score_bonus']})")

    score_minimo_efectivo = SCORE_MINIMO + 2 if regime['regime'] == 'BAJISTA' else SCORE_MINIMO
    if regime['regime'] == 'BAJISTA':
        print(f"⚠️ Mercado bajista → Umbral de compra elevado a {score_minimo_efectivo}")

    # Cargar datos persistentes
    print("\n── Sincronizando datos con repositorio central ──")
    posiciones = cargar_posiciones_repo()
    cargar_historial_repo()
    cargar_cache_ia_repo()
    print("── Sincronización inicial completada ──\n")

    # Construir universo final sin sufijo .MX
    universo_sin_sufijo = [s.replace('.MX', '') for s in UNIVERSO]
    universo_final = list(set(universo_sin_sufijo + list(posiciones.keys())))
    print(f"✅ Analizando {len(universo_final)} activos ({len(posiciones)} posiciones propias).")

    # Análisis en paralelo
    args_list = [(sim, usd_mxn, regime['score_bonus'], posiciones) for sim in universo_final]
    resultados = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(analizar, a): a[0] for a in args_list}
        for i, f in enumerate(as_completed(futures), 1):
            res = f.result()
            if res:
                resultados.append(res)
            if i % 50 == 0:
                print(f"  {i}/{len(universo_final)} procesados...")

    # Separar ventas y compras
    ventas_alertas = [r for r in resultados if r['Recomendación'] == 'VENDER']
    compras_alertas = [r for r in resultados if r['Recomendación'].startswith('COMPRAR') and r['Score'] >= score_minimo_efectivo]
    compras_alertas.sort(key=lambda x: x['Score'], reverse=True)

    print(f"\n🚨 Ventas Técnicas: {len(ventas_alertas)}")
    for v in ventas_alertas:
        print(f"  VENDER {v['Símbolo']:8s} MXN:{v['Precio MXN']:>8.2f}  Motivo: {v['Motivo']}")
    print(f"\n📈 Nuevas Compras: {len(compras_alertas)}")
    for c in compras_alertas[:10]:
        print(f"  {c['Símbolo']:8s} Score:{c['Score']:2d}  MXN:{c['Precio MXN']:>8.2f}  {c['Señales']}")

    # Guardar historial (solo compras)
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for senal in compras_alertas:
        guardar_senal_en_historial(senal, fecha_hoy)

    # Backtesting
    print("\nEjecutando backtesting...")
    hist_df = cargar_historial_repo()
    metrics = backtest_historial(hist_df)
    print(f"  Backtest {metrics['total']} señales: WinRate:{metrics['win_rate']}%  RetProm:{metrics['ret_prom']}%")

    # Análisis IA
    ia_texto = analisis_ia(compras_alertas, regime, usd_mxn, posiciones, ventas_alertas)

    # Enviar alertas si hay algo
    if compras_alertas or ventas_alertas:
        html = construir_email(compras_alertas, ventas_alertas, regime, ia_texto, hora)
        con_ventas = f"🚨 VENTAS: {len(ventas_alertas)} | " if ventas_alertas else ""
        asunto = f"📉 Trading Alert {hora} — {con_ventas}Compras: {len(compras_alertas)} | Mercado: {regime['regime']}"
        enviar_email(asunto, html)

        top3_compra = ", ".join([c['Símbolo'] for c in compras_alertas[:3]]) if compras_alertas else "ninguna"
        top3_venta = ", ".join([v['Símbolo'] for v in ventas_alertas[:3]]) if ventas_alertas else "ninguna"
        msg_wa = (f"📉 Trading Alert — {hora}\n"
                  f"Régimen: {regime['regime']}\n"
                  f"🚨 Ventas: {len(ventas_alertas)} ({top3_venta})\n"
                  f"🟢 Compras: {len(compras_alertas)} ({top3_compra})")
        enviar_whatsapp(msg_wa)
    else:
        print("Sin señales que superen el umbral. No se envían alertas.")

    # Sincronizar final
    print("\n── Sincronizando datos finales con repositorio ──")
    sincronizar_historial_repo()
    sincronizar_cache_ia_repo()
    print("── Sincronización final completada ──")
    print(f"\n✅ Scanner completado — {datetime.now().strftime('%H:%M:%S')}\n")

if __name__ == "__main__":
    main()
