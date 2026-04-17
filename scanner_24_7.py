# ============================================================
# SCANNER DE TRADING AUTÓNOMO 24/7
# Versión corregida v3.1: Prioriza Alertas de Venta Técnicas basadas en Portafolio Real
# Mantiene la persistencia bidireccional con el App vía GitHub data/
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
# Estas variables deben estar configuradas en los Secrets de tu repositorio de GitHub
EMAIL_REMITENTE   = os.environ.get("EMAIL_REMITENTE",   "")
EMAIL_PASSWORD    = os.environ.get("EMAIL_PASSWORD",    "")
EMAIL_DESTINO     = "alopez.uci@gmail.com"
WHATSAPP_NUMERO   = os.environ.get("WHATSAPP_NUMERO", "")
WHATSAPP_APIKEY   = os.environ.get("WHATSAPP_APIKEY", "")

GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY",    "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY",      "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Persistencia compartida con el app (mismo repo GitHub) ──
# Token requiere scope "repo" completo
GHU_GIST_TOKEN = os.environ.get("GHU_GIST_TOKEN", "")   # PAT con scope repo
REPO_OWNER     = "alopezuci-arch"
REPO_NAME      = "trading-app-3.1"
DATA_PATH      = "data"   # misma carpeta que usa el app en Streamlit Cloud

# Parámetros de Trading
SCORE_MINIMO     = 7        # Umbral normal para compras
CAPITAL_TRADING  = 100_000  # Capital total configurado en la App
RIESGO_PCT       = 1.0      # Riesgo máximo por operación (para position sizing)
MAX_WORKERS      = 20       # Hilos para análisis en paralelo
CACHE_DIR        = "cache_ia"
CACHE_TTL        = 3600     # 1 hora
HISTORICO_FILE   = "historial_senales.csv"
POSICIONES_FILE  = "posiciones.json" # Fuente única de verdad del portafolio

# ============================================================
# CAPA DE PERSISTENCIA — GitHub Repo (idéntica al app)
# Lee y escribe en trading-app-3.1/data/ igual que el app.
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
    """Lee un archivo de data/ en el repo. Devuelve '' si no existe."""
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
    """Escribe/actualiza un archivo en data/ del repo."""
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
        ok = r.status_code in (200, 201)
        if not ok:
            print(f"⚠️  repo escribir '{nombre}': HTTP {r.status_code}")
        return ok
    except Exception as e:
        print(f"⚠️  repo escribir '{nombre}': {e}")
        return False

# === PEGA ESTO EN LUGAR DEL BLOQUE ANTERIOR ===

def cargar_posiciones_repo() -> dict:
    """
    Carga posiciones abiertas desde data/posiciones.json del repo.
    Si el archivo está vacío o desactualizado (fuente única de verdad del app falló),
    reconstruye el portafolio real basándose matemáticamente en data/transacciones.csv.
    """
    print("📌 Intentando cargar portafolio desde data/posiciones.json...")
    
    # 1. Intentar cargar desde posiciones.json (método rápido)
    contenido_json = _repo_leer("posiciones.json")
    posiciones_json = {}
    
    if contenido_json and contenido_json.strip() not in ("", "{}", "null"):
        try:
            data = json.loads(contenido_json)
            if isinstance(data, dict) and data:
                # Asegurar símbolos en mayúsculas y precios como float
                posiciones_json = {k.upper(): float(v) for k, v in data.items()}
                print(f"  ✅ Portafolio JSON cargado ({len(posiciones_json)} activos).")
        except Exception as e:
            print(f"  ⚠️ Error parseando posiciones.json: {e}")

    # 2. CARGAR Y VALIDAR CONTRA transacciones.csv (FUENTE DE RESPALDO DE LA VERDAD)
    # Ya que el historial sí se está guardando bien, lo usaremos para verificar.
    print("📌 Validando portafolio contra data/transacciones.csv...")
    csv_contenido = _repo_leer("transacciones.csv")
    posiciones_reconstruidas = {}
    
    if csv_contenido and len(csv_contenido) > 60:
        try:
            from io import StringIO
            # Asegurarse de importar pandas como pd si no lo has hecho
            df = pd.read_csv(StringIO(csv_contenido))
            
            # Normalizar datos
            df['simbolo'] = df['simbolo'].str.upper().str.strip()
            df['tipo'] = df['tipo'].str.lower().str.strip()
            # Asegurarse de que la fecha sea datetime
            df['fecha'] = pd.to_datetime(df['fecha'])
            
            # Calcular matemáticamente las posiciones abiertas
            # Agrupamos por símbolo y sumamos cantidades de compra y restamos de venta
            df_compras = df[df['tipo'] == 'compra'].groupby('simbolo')['cantidad'].sum()
            df_ventas = df[df['tipo'] == 'venta'].groupby('simbolo')['cantidad'].sum()
            
            # Unimos los dataframes para calcular la cantidad neta actual
            df_neto = pd.DataFrame({'compras': df_compras, 'ventas': df_ventas}).fillna(0)
            df_neto['cantidad_actual'] = df_neto['compras'] - df_neto['ventas']
            
            # Filtrar solo las acciones que tenemos actualmente (cantidad > 0)
            # Usamos una tolerancia pequeña para evitar errores de coma flotante
            acciones_abiertas = df_neto[df_neto['cantidad_actual'] > 0.001].index.tolist()
            
            # Para cada acción abierta, necesitamos encontrar el precio promedio de compra
            # (Lógica simplificada: último precio de compra registrado)
            for sim in acciones_abiertas:
                ultimo_trade_compra = df[
                    (df['simbolo'] == sim) & (df['tipo'] == 'compra')
                ].sort_values('fecha').iloc[-1]
                posiciones_reconstruidas[sim] = float(ultimo_trade_compra['precio'])
                
            print(f"  ✅ Portafolio reconstruido desde transacciones.csv ({len(posiciones_reconstruidas)} activos).")
            
        except Exception as e:
            print(f"  ❌ Error reconstruyendo portafolio desde CSV: {e}")
            # Si el CSV falla catastróficamente, confiamos en lo que obtuvimos del JSON
            return posiciones_json

    # 3. COMPARAR Y DECIDIR LA VERDAD
    # Si positions_json está vacío y logramos reconstruir desde el CSV,
    # el CSV es la verdad. Debemos actualizar el JSON en el repo.
    
    if not posiciones_json and posiciones_reconstruidas:
        print("⚠️data/posiciones.json estaba vacío. Sincronizando con data/transacciones.csv...")
        # Guardar el portafolio reconstruido en el repo para que el App lo vea actualizado
        contenido_a_guardar = json.dumps(
            {k: v for k, v in posiciones_reconstruidas.items()},
            indent=2, ensure_ascii=False
        )
        if _repo_escribir("posiciones.json", contenido_a_guardar, "sincronizar portafolio desde transacciones.csv"):
            print("  ☁️ data/posiciones.json actualizado en GitHub vía API.")
        else:
            print("  ❌ Falló la actualización de posiciones.json en GitHub.")
            
        return posiciones_reconstruidas
        
    # Si ambos existen, el JSON suele ser más preciso (precio promedio), 
    # pero el CSV manda en qué acciones tenemos.
    elif posiciones_json and posiciones_reconstruidas:
        # Asegurarnos de no tener acciones en el JSON que el CSV dice que ya vendimos
        set_json = set(posiciones_json.keys())
        set_csv = set(posiciones_reconstruidas.keys())
        
        # Acciones que están en JSON pero NO en CSV (probablemente vendidas y no sincronizadas)
        acciones_a_borrar = set_json - set_csv
        if acciones_a_borrar:
            print(f"⚠️ Limpiando {len(acciones_a_borrar)} acciones vendidas del portafolio JSON: {list(acciones_a_borrar)}")
            for sim in acciones_a_borrar:
                del posiciones_json[sim]
            
            # Actualizar JSON en repo con la limpieza
            contenido_a_guardar = json.dumps(
                {k: v for k, v in posiciones_json.items()},
                indent=2, ensure_ascii=False
            )
            _repo_escribir("posiciones.json", contenido_a_guardar, "limpiar acciones vendidas")

        return posiciones_json

    # Si ninguno tiene datos
    elif not posiciones_json and not posiciones_reconstruidas:
        print("ℹ️ Sin posiciones abiertas registradas en el repo (JSON vacío, CSV vacío o sin trades).")
        return {}
        
    # Fallback por defecto
    return posiciones_json
def cargar_historial_repo() -> pd.DataFrame:
    """Descarga historial_senales.csv del repo y lo escribe al disco local."""
    cols = ['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales']
    contenido = _repo_leer("historial_senales.csv")
    if contenido and len(contenido) > 60:
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(contenido))
            df['fecha'] = pd.to_datetime(df['fecha'])
            df.to_csv(HISTORICO_FILE, index=False)
            print(f"📊 Historial cargado desde repo: {len(df)} señales previas")
            return df
        except Exception as e:
            print(f"⚠️  Error cargando historial: {e}")
    return pd.DataFrame(columns=cols)

def sincronizar_historial_repo():
    """Sube el historial actualizado al repo al finalizar."""
    if not _repo_disponible() or not os.path.exists(HISTORICO_FILE):
        return
    try:
        with open(HISTORICO_FILE, 'r', encoding='utf-8') as f:
            contenido = f.read()
        if _repo_escribir("historial_senales.csv", contenido, "sincronizar historial señales"):
            print("☁️  Historial sincronizado con repo")
        else:
            print("⚠️  No se pudo sincronizar historial")
    except Exception as e:
        print(f"⚠️  Error sincronizando historial: {e}")

def cargar_cache_ia_repo():
    """Descarga el caché IA desde el repo para evitar llamadas redundantes."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    contenido = _repo_leer("cache_ia_index.json")
    if contenido:
        try:
            cache_index = json.loads(contenido)
            ahora = time.time()
            validos = 0
            for key, entry in cache_index.items():
                if ahora - entry.get('timestamp', 0) < CACHE_TTL:
                    ruta = f"{CACHE_DIR}/{key}.json"
                    with open(ruta, 'w', encoding='utf-8') as f:
                        json.dump(entry, f, ensure_ascii=False)
                    validos += 1
            if validos:
                print(f"🧠 Caché IA restaurado desde repo: {validos} entradas válidas")
        except:
            pass

def sincronizar_cache_ia_repo():
    """Sube el caché IA al repo al finalizar."""
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
            if _repo_escribir("cache_ia_index.json",
                              json.dumps(cache_index, ensure_ascii=False),
                              "sincronizar cache IA"):
                print(f"☁️  Caché IA sincronizado con repo: {len(cache_index)} entradas")
    except Exception as e:
        print(f"⚠️  Error sincronizando caché IA: {e}")

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
# FUNCIONES DE INDICADORES, SCORING, MARKET REGIME (Se mantiene igual)
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
    # Se usan las constantes CAPITAL_TRADING y RIESGO_PCT globales
    riesgo_mxn = CAPITAL_TRADING * (RIESGO_PCT / 100)
    stop_dist  = 2 * atr
    if stop_dist <= 0:
        return {'unidades': 0, 'inversion': 0}
    unidades   = riesgo_mxn / stop_dist
    inversion  = min(unidades * precio, CAPITAL_TRADING * 0.20) # Máx 20% capital por trade
    unidades   = inversion / precio
    return {'unidades': round(unidades, 2), 'inversion': round(inversion, 2)}

# ============================================================
# FUNCIÓN DE ANÁLISIS MEJORADA (Lógica de Portafolio)
# CORRECCIÓN TÉCNICA AQUÍ
# ============================================================
def analizar(args: tuple) -> dict | None:
    # Ahora 'posiciones' es el diccionario cargado de data/posiciones.json
    simbolo, usd_mxn, regime_bonus, posiciones = args
    try:
        hist = yf.Ticker(simbolo).history(period="3mo")
        if hist.empty or len(hist) < 55:
            return None
        
        # Convertir a MXN si aplica
        factor = 1.0 if simbolo.endswith('.MX') else usd_mxn
        for c in ['Close','Open','High','Low']:
            hist[c] *= factor
            
        hist = calcular_indicadores(hist)
        hist = hist.dropna(subset=['RSI','MACD','EMA20','EMA50','ATR','STOCH_K','STOCH_D'])
        if len(hist) < 2:
            return None
            
        r = hist.iloc[-1].to_dict() # Datos de HOY
        p = hist.iloc[-2].to_dict() # Datos de AYER
        precio = r['Close']
        atr    = r['ATR']

        # ============================================================
        # 1. LÓGICA DE VENTA (Solo si el símbolo está en mi portafolio)
        # ============================================================
        if simbolo in posiciones:
            precio_compra = posiciones[simbolo]
            ganancia_pct = ((precio / precio_compra) - 1) * 100

            motivo_venta = ""

            # --- A) Gestión de Riesgo Hard-Coded (TP/SL) ---
            if ganancia_pct >= 20: # Take Profit 20%
                motivo_venta = f"🎯 Take Profit alcanzado (+{ganancia_pct:.1f}%)"
            elif ganancia_pct <= -8: # Stop Loss 8%
                motivo_venta = f"🛑 Stop Loss activado ({ganancia_pct:.1f}%)"

            # --- B) DETECCIÓN TÉCNICA DE VENTA (Independiente del Score de compra) ---
            # Si tengo la acción, busco señales de deterioro técnico para salir.
            elif r['RSI'] > 75: # Muy sobrecomprada
                motivo_venta = f"⚠️ RSI Sobrevendido Técnicamente ({r['RSI']:.0f})"
            
            # Cruce bajista EMA50 (Hoy cierra abajo, ayer cerró arriba)
            elif r['Close'] < r['EMA50'] and p['Close'] >= p['EMA50']:
                motivo_venta = "📉 Precio rompió EMA50 hacia abajo (Señal de Debilidad)"
                
            # Cruce bajista MACD (MACD cruza abajo de la Señal)
            elif r['MACD'] < r['MACD_sig'] and p['MACD'] >= p['MACD_sig']:
                motivo_venta = "❌ Cruce bajista MACD detectado"

            # Score muy bajo (deterioro general de la tendencia alcista)
            if not motivo_venta:
                score_base, _ = calcular_score(r, p)
                score_actual = max(0, score_base + regime_bonus)
                if score_actual < 4:
                    motivo_venta = f"📉 Score deteriorado dramáticamente ({score_actual}/14)"

            if motivo_venta:
                # Retornamos formato de alerta de venta prioridad
                return {
                    'Símbolo':      simbolo,
                    'Precio MXN':   round(precio, 2),
                    'Recomendación': "VENDER",
                    'Motivo':       motivo_venta,
                    # Campos de compra vacíos para compatibilidad
                    'Score': 0, 'RSI': round(r['RSI'], 1), 'ATR': 0, 'Stop Loss': 0, 'Take Profit': 0,
                    'Unidades': 0, 'Inversión MXN': 0, 'Señales': ""
                }
            else:
                # Es posición mía pero no hay señal técnica ni SL/TP de venta. No alertar.
                return None

        # ============================================================
        # 2. LÓGICA DE COMPRA (Normal, solo si NO es posición mía)
        # ============================================================
        score_base, señales = calcular_score(r, p)
        # Aplicar bonus/malus del régimen de mercado
        score = max(0, score_base + regime_bonus)
        
        # Filtro estricto de compra
        if score < SCORE_MINIMO:
            return None
            
        # Calcular position sizing
        ps = position_size(precio, atr)
        
        if score >= 10:
            rec = "COMPRAR ★★★"
        elif score >= 8:
            rec = "COMPRAR ★★"
        else:
            rec = "COMPRAR"
            
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
            'Motivo':       f"Score {score}/14" # Para compras, el motivo es el score
        }
        
    except Exception as e:
        return None

# ============================================================
# HISTORIAL, IA Y ALERTAS (Se mantiene igual)
# ============================================================
# (... Mantener funciones guardar_senal_en_historial, backtest_historial, _calcular_hash_prompt, etc. igual ...)
def guardar_senal_en_historial(senal: dict, fecha: str):
    # Cargar historial local (actualizado desde repo al inicio)
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
    # Mantener últimos 90 días
    cutoff = datetime.now() - timedelta(days=90)
    df = df[df['fecha'] >= cutoff]
    df.to_csv(HISTORICO_FILE, index=False)
    print(f"  ✅ Señal guardada localmente: {senal['Símbolo']} (Score {senal['Score']})")

def backtest_historial(df_hist: pd.DataFrame) -> dict:
    if df_hist.empty:
        return {'win_rate': 0, 'ret_prom': 0, 'total': 0}
    
    # Simulación simple a 5 días
    VENTANA_BT = 5
    resultados = []
    
    # Solo evaluar señales de COMPRAR
    df_compras = df_hist[df_hist['recomendacion'].str.startswith('COMPRAR')].copy()
    
    for _, row in df_compras.iterrows():
        try:
            ticker = yf.Ticker(row['simbolo'])
            # Pedir un poco más de datos para cubrir la ventana
            start_date = row['fecha']
            end_date = row['fecha'] + timedelta(days=VENTANA_BT*2)
            hist = ticker.history(start=start_date, end=end_date)
            if hist.empty or len(hist) < VENTANA_BT:
                continue
            
            precio_entrada = row['precio']
            # Precio de salida aproximado a 5 sesiones
            precio_salida = hist['Close'].iloc[min(VENTANA_BT, len(hist)-1)]
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

# IA
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

    def _construir_prompt(oportunidades: list[dict], regime: dict, usd_mxn: float, posiciones: dict) -> str:
    # Convertimos el portafolio a un formato legible para la IA
    portfolio_str = ""
    if posiciones:
        portfolio_str = "\\n".join([f"- {sym}: Comprado a {px}" for sym, px in posiciones.items()])
    else:
        portfolio_str = "Sin posiciones abiertas actualmente."

    prompt = f"""
    Eres un estratega de fondos de inversión cuantitativos. 
    Contexto de Mercado: Régimen {regime['regime']} (VIX: {regime['vix']:.2f}, USD/MXN: {usd_mxn:.2f}).
    
    MI PORTAFOLIO ACTUAL:
    {portfolio_str}
    
    NUEVAS OPORTUNIDADES DETECTADAS:
    {json.dumps(oportunidades[:10], indent=2)}
    
    TAREA:
    1. Analiza si las nuevas oportunidades complementan mi portafolio actual o si generan demasiado riesgo (por ejemplo, si ya tengo muchas acciones del mismo sector).
    2. Si mi portafolio tiene acciones, dime si alguna de las NUEVAS es tan superior que justifica vender una posición actual para rotar el capital.
    3. Dame un 'Plan de Acción' concreto para hoy.
    
    Responde de forma ejecutiva, breve y en español profesional.
    """
    return prompt

MERCADO HOY:
- Régimen S&P 500: {regime['regime']}
- S&P 500: {regime['precio']:,.0f} | EMA200: {regime['ema200']:,.0f}
- USD/MXN: {usd_mxn:.2f}

OPORTUNIDADES DETECTADAS (Compras):
{resumen}

Proporciona en formato conciso:
1. Evaluación del contexto de mercado (2 oraciones)
2. Las 3 mejores oportunidades de compra con razón breve de por qué destacan
3. Confianza general: ALTA / MEDIA / BAJA
4. Advertencia principal si la hay

Sé directo y práctico."""

def analisis_ia(oportunidades: list[dict], regime: dict, usd_mxn: float) -> str:
    if not oportunidades: return ""
    prompt = _construir_prompt(oportunidades, regime, usd_mxn)
    cache = _obtener_cache_ia(prompt)
    if cache:
        print("  ✅ Análisis IA obtenido desde caché")
        return cache
    
    # Intentar Gemini primero, luego Groq
    if GEMINI_API_KEY:
        try:
            print("  Intentando Gemini...")
            texto = _llamar_ia_con_reintentos("Gemini", prompt)
            _guardar_cache_ia(prompt, texto)
            return texto
        except: pass
    
    if GROQ_API_KEY:
        try:
            print("  Intentando Groq...")
            texto = _llamar_ia_con_reintentos("Groq", prompt)
            _guardar_cache_ia(prompt, texto)
            return texto
        except: pass
        
    return ""

# ALERTAS
def enviar_email(asunto: str, html: str) -> bool:
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD: return False
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
    exceptException as e:
        print(f"❌ Error email: {e}")
        return False

def enviar_whatsapp(mensaje: str) -> bool:
    if not WHATSAPP_NUMERO or not WHATSAPP_APIKEY: return False
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
    
    bloque_ia = f"""<h3 style="color:#7b61ff">🤖 Análisis de IA (Top Compras)</h3>
        <div style="background:#f5f3ff;padding:12px;border-left:4px solid #7b61ff;font-size:14px;line-height:1.6">
          {ia_texto.replace(chr(10),'<br>')}
        </div>""" if ia_texto else ""
        
    icono_regime = {'ALCISTA':'🟢','LATERAL':'🟡','BAJISTA':'🔴'}.get(regime['regime'],'⚪')
    
    return f"""<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto">
    <h2 style="color:#1a73e8">📈 Scanner Trading Real — {hora}</h2>
    <p style="background:#f1f3f4;padding:10px;border-radius:6px;font-size:14px">
      {icono_regime} Régimen S&P 500: <b>{regime['regime']}</b> | S&P: {regime['precio']:,.0f}
    </p>
    
    <h3 style="color:#ea4335">🔴 Señales Prioritarias de VENTA ({len(ops_ventas)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px">
      <tr style="background:#fce8e6"><th>Símbolo</th><th>Precio MXN</th><th>Motivo / Señal</th></tr>
      {filas_ventas if filas_ventas else '<tr><td colspan="3" style="text-align:center">Sin señales</td></tr>'}
     </table>

    {bloque_ia}
    
    <h3 style="color:#34a853">🟢 Oportunidades de COMPRA Detectadas ({len(ops_compras)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px">
      <tr style="background:#e8f5e9"><th>Símbolo</th><th>Precio MXN</th><th>Score</th><th>Stop Loss</th><th>Inversión</th><th>Rec.</th></tr>
      {filas_compras if filas_compras else '<tr><td colspan="6" style="text-align:center">Sin señales</td></tr>'}
     </table>
     
    <p style="color:#999;font-size:11px;margin-top:20px">Scanner autónomo corregido v3.1 — Prioriza portafolio real.</p>
    </body></html>"""

# ============================================================
# OBTENER NOTICIAS POR SI CAE LA ACCIÓN
# ============================================================
def obtener_noticias_recientes(ticker):
    """Obtiene titulares de noticias para darle contexto a la IA."""
    try:
        asset = yf.Ticker(ticker)
        news = asset.news
        if not news:
            return "Sin noticias relevantes recientemente."
        # Tomamos los 3 titulares más nuevos
        titulares = [n['title'] for n in news[:3]]
        return " | ".join(titulares)
    except Exception as e:
        return f"No se pudieron cargar noticias: {e}"

# ============================================================
# MAIN
# ============================================================
def main():
    hora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n{'='*50}")
    print(f"  Scanner Trading v3.1 (Corregido) — {hora}")
    print(f"{'='*50}\n")

    # 1. Tipo de cambio
    try:
        usd_data = yf.Ticker("USDMXN=X").history(period="1d")
        usd_mxn = float(usd_data['Close'].iloc[-1]) if not usd_data.empty else 20.0
    except: usd_mxn = 20.0
    print(f"USD/MXN: {usd_mxn:.2f}")

    # 2. Market regime
    regime = obtener_market_regime()
    print(f"Régimen SP500: {regime['regime']} (malus score: {regime['score_bonus']})")
    
    # Definir Score Mínimo efectivo según régimen
    if regime['regime'] == 'BAJISTA':
        score_minimo_efectivo = SCORE_MINIMO + 2 # Subimos umbral a 9
        print(f"⚠️  Mercado bajista — Umbral de compra elevado a {score_minimo_efectivo}")
    else:
        score_minimo_efectivo = SCORE_MINIMO
    
    def obtener_noticias_recientes(ticker):
    """Obtiene titulares de noticias para darle contexto a la IA."""
    try:
        asset = yf.Ticker(ticker)
        news = asset.news
        if not news: return "Sin noticias relevantes recientemente."
        return " | ".join([n['title'] for n in news[:3]]) # Solo las 3 más nuevas
    except:
        return "No se pudieron cargar noticias."
        
    # 3. CARGAR DATOS PERSISTENTES DESDE REPO GITHUB (data/)
    # Sincronización bidireccional App <-> Scanner
    print("\n── Sincronizando datos con repositorio central ──")
    
   # ==========================================================
    # 4. ANALIZAR POSICIONES ACTUALES (VENTAS CON NOTICIAS)
    # ==========================================================
    posiciones = cargar_posiciones_repo()
    ventas_alertas = []

    if posiciones:
        print(f"🔍 Evaluando {len(posiciones)} posiciones para posibles ventas...")
        for sim, precio_compra in posiciones.items():
            try:
                # Descargamos 3 meses para asegurar que el RSI tenga datos suficientes
                hist = yf.download(sim, period="3mo", interval="1d", progress=False)
                if hist.empty:
                    print(f"⚠️ No se obtuvieron datos para {sim}")
                    continue
                
                # Aseguramos que los precios sean tratados como números decimales (float)
                precio_actual = float(hist['Close'].iloc[-1])
                precio_compra_f = float(precio_compra)
                
                # Cálculo de variación: 0.15 = 15%
                variacion = (precio_actual / precio_compra_f) - 1
                
                # Cálculo de RSI (14 días)
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi_val = 100 - (100 / (1 + rs.iloc[-1]))

                # --- CONDICIÓN TÉCNICA CORREGIDA ---
                # Se activa si: RSI > 65 OR caída > 5% (-0.05) OR ganancia > 10% (0.10)
                if rsi_val > 65 or variacion <= -0.05 or variacion >= 0.10:
                    print(f"⚠️ Alerta en {sim}: Retorno {variacion*100:+.2f}% | RSI: {rsi_val:.2f}")
                    
                    # Buscamos noticias para que la IA decida
                    noticias_contexto = obtener_noticias_recientes(sim)
                    
                    # Definimos el motivo para el correo
                    if variacion >= 0.10: 
                        motivo = "Take Profit (Ganancia)"
                    elif variacion <= -0.05: 
                        motivo = "Stop Loss (Pérdida)"
                    else: 
                        motivo = "Sobrecompra Técnica (RSI)"

                    ventas_alertas.append({
                        'Símbolo': sim,
                        'Precio Compra': precio_compra_f,
                        'Precio Actual': precio_actual,
                        'Retorno': f"{variacion*100:+.2f}%",
                        'RSI': round(rsi_val, 2),
                        'Noticias': noticias_contexto,
                        'Motivo': motivo
                    })
            except Exception as e:
                print(f"❌ Error analizando {sim}: {e}")

    # Continuar con el resto del script...
    cargar_historial_repo()
    cargar_cache_ia_repo()
    print(f"── Sincronización inicial completada ──\n")

    # 4. Crear Universo Final (Combinar Universo Fijo + Posiciones que tengamos)
    # Por si acaso compramos algo fuera del SP500 o BMV principal.
    universo_final = list(set(UNIVERSO + list(posiciones.keys())))
    print(f"✅ Analizando {len(universo_final)} activos ({len(posiciones)} son posiciones propias).")

    # 5. Análisis en paralelo
    resultados = []
    # Pasamos CAPITAL_TRADING y RIESGO_PCT globales implícitamente en position_size
    args_list = [(sim, usd_mxn, regime['score_bonus'], posiciones) for sim in universo_final]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(analizar, a): a[0] for a in args_list}
        for i, f in enumerate(as_completed(futures), 1):
            res = f.result()
            if res: resultados.append(res)
            if i % 50 == 0: print(f"  {i}/{len(universo_final)} procesados...")

    # Separar resultados
    # Ventas técnicas de portafolio
    ventas_alertas = [r for r in resultados if r['Recomendación'] == 'VENDER']
    # Compras nuevas (filtradas por score efectivo)
    compras_alertas = [r for r in resultados if r['Recomendación'].startswith('COMPRAR') and r['Score'] >= score_minimo_efectivo]
    
    # Ordenar compras por Score
    compras_alertas.sort(key=lambda x: x['Score'], reverse=True)

    print(f"\n🚨 Señales Prioritarias de Venta Técnicas Detectadas: {len(ventas_alertas)}")
    for r in ventas_alertas:
        print(f"  VENDER {r['Símbolo']:8s} MXN:{r['Precio MXN']:>8.2f}  Motivo: {r['Motivo']}")
        
    print(f"\n📈 Nuevas Oportunidades de Compra Detectadas: {len(compras_alertas)}")
    for r in compras_alertas[:10]: # Top 10
        print(f"  {r['Símbolo']:8s} Score:{r['Score']:2d}  MXN:{r['Precio MXN']:>8.2f}  {r['Señales']}")

    # 6. Guardar nuevas señales de compra en historial local
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for senal in compras_alertas:
        guardar_senal_en_historial(senal, fecha_hoy)

    # 7. Backtesting sobre historial local actualizado
    print("\nEjecutando backtesting sobre señales previas (ventana 5 días)...")
    hist_df = cargar_historial()
    metrics = backtest_historial(hist_df)
    print(f"  Backtest {metrics['total']} señales: WinRate:{metrics['win_rate']}%  RetProm:{metrics['ret_prom']}%")

    # 8. Análisis IA (Asegúrate de que incluya ventas_alertas)
    ia_texto = analizar_ia(compras_alertas, regime, usd_mxn, posiciones, ventas_alertas)

    # 9. Alertas
    if compras_alertas or ventas_alertas:
        html = construir_email(compras_alertas, ventas_alertas, regime, ia_texto, hora)
        
        # Asunto Priorizando VENTAS
        con_ventas = f"🚨 VENTAS: {len(ventas_alertas)} | " if ventas_alertas else ""
        asunto = (f"📉 Trading Alert {hora} — {con_ventas}"
                  f"Compras: {len(compras_alertas)} | Mercado: {regime['regime']}")
        
        enviar_email(asunto, html)

        # WhatsApp Prioritario
        top3_compra = ", ".join([r['Símbolo'] for r in compras_alertas[:3]]) if compras_alertas else "ninguna"
        top3_venta = ", ".join([r['Símbolo'] for r in ventas_alertas[:3]]) if ventas_alertas else "ninguna"
        
        msg_wa = (f"📉 *Trading Alert Corregido* — {hora}\n"
                  f"Régimen: {regime['regime']}\n"
                  f"🚨 *Ventas (Prioridad):* {len(ventas_alertas)} ({top3_venta})\n"
                  f"🟢 *Compras:* {len(compras_alertas)} ({top3_compra})\n"
                  f"Ver detalles en tu email")
        enviar_whatsapp(msg_wa)
    else:
        print("Sin oportunidades técnicas que superen el umbral. No se envían alertas.")

    # 10. SINCRONIZAR TODO CON EL REPO GITHUB AL FINALIZAR
    # Para que Streamlit Cloud App vea el historial actualizado y caché IA
    print("\n── Sincronizando datos finales con repositorio central ──")
    sincronizar_historial_repo()
    sincronizar_cache_ia_repo()
    print("── Sincronización final completada ──")

    print(f"\n✅ Scanner completado — {datetime.now().strftime('%H:%M:%S')}\n")

if __name__ == "__main__":
    main()
