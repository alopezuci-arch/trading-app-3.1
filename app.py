# ============================================================
# SISTEMA DE TRADING PROFESIONAL v3.0 — STREAMLIT (FINAL)
# Mejoras: sentimiento noticias, fundamentales profundos, ML predictivo,
# optimización cartera, backtest paramétrico, alertas email/WhatsApp,
# dashboard rendimiento, integración Google Drive.
# ============================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import io
import urllib3
import ssl
import time
import os
import hashlib
import json
import pickle
import warnings
warnings.filterwarnings('ignore')

# ── ML y sentimiento ───────────────────────────────────────────
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from textblob import TextBlob

# ── Google Drive ───────────────────────────────────────────────
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import googleapiclient.http

# ── SSL y warnings ─────────────────────────────────────────────
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# ── Configuración de página ────────────────────────────────────
st.set_page_config(page_title="Trading System v3.0", layout="wide", page_icon="📈")
st.title("📈 Sistema de Trading Personal v3.0 (Mejorado)")

# ============================================================
# CONSTANTES
# ============================================================
EMAIL_DESTINO   = "alopez.uci@gmail.com"
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY",    "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY",      "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
WHATSAPP_NUMERO   = os.environ.get("WHATSAPP_NUMERO", "")
WHATSAPP_APIKEY   = os.environ.get("WHATSAPP_APIKEY", "")
EMAIL_REMITENTE   = os.environ.get("EMAIL_REMITENTE", "")
EMAIL_PASSWORD    = os.environ.get("EMAIL_PASSWORD",  "")
NEWSAPI_KEY       = os.environ.get("NEWSAPI_KEY", "")

# ── Persistencia: GitHub repo como base de datos ─────────────
# Token requiere scope "repo" (o "contents:write").
# El mismo token sirve para el scanner en GitHub Actions.
GHU_GIST_TOKEN = os.environ.get("GHU_GIST_TOKEN", "")   # PAT con scope repo
REPO_OWNER     = "alopezuci-arch"
REPO_NAME      = "trading-app-3.1"
DATA_PATH      = "data"   # carpeta dentro del repo

# ============================================================
# CAPA DE PERSISTENCIA — 3 niveles de respaldo
# 1. GitHub repo  (sobrevive todo — suspensiones, reinicios)
# 2. Descarga ZIP local (el usuario lo guarda en su PC)
# 3. Restauración manual desde botón en el sidebar
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
    """Lee un archivo de la carpeta data/ del repo. Devuelve '' si no existe."""
    if not _repo_disponible():
        return ""
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{DATA_PATH}/{nombre}"
        r = requests.get(url, headers=_gh_headers(), timeout=12)
        if r.status_code == 200:
            import base64
            data = r.json()
            contenido = base64.b64decode(data["content"]).decode("utf-8")
            return contenido
        elif r.status_code == 404:
            return ""   # archivo aún no existe
    except Exception as e:
        pass
    return ""

def _repo_escribir(nombre: str, contenido: str, mensaje: str = "update") -> bool:
    """Escribe/actualiza un archivo en data/ del repo. Devuelve True si tuvo éxito."""
    if not _repo_disponible() or not contenido:
        return False
    import base64
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{DATA_PATH}/{nombre}"
        # Obtener SHA actual (necesario para actualizar)
        r_get = requests.get(url, headers=_gh_headers(), timeout=10)
        sha = r_get.json().get("sha", "") if r_get.status_code == 200 else ""
        payload = {
            "message": f"[trading-app] {mensaje}",
            "content": base64.b64encode(contenido.encode("utf-8")).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=_gh_headers(), json=payload, timeout=15)
        return r.status_code in (200, 201)
    except:
        return False

# ── Operaciones de alto nivel ────────────────────────────────

def repo_cargar_posiciones() -> dict:
    """Lee posiciones.json desde el repo. Devuelve {} si no hay nada."""
    contenido = _repo_leer("posiciones.json")
    if contenido and contenido.strip() not in ("", "{}", "null"):
        try:
            data = json.loads(contenido)
            if isinstance(data, dict) and data:
                return {k.upper(): float(v) for k, v in data.items()}
        except:
            pass
    return {}

def repo_guardar_posiciones(posiciones: dict) -> bool:
    """Guarda posiciones.json en el repo."""
    if not posiciones:
        return repo_guardar_posiciones({})  # limpiar
    contenido = json.dumps(
        {k.upper(): v for k, v in posiciones.items()},
        indent=2, ensure_ascii=False
    )
    return _repo_escribir("posiciones.json", contenido, "actualizar posiciones")

def repo_cargar_transacciones() -> pd.DataFrame:
    """Lee transacciones.csv desde el repo y lo sincroniza al disco local."""
    cols = ['fecha','simbolo','cantidad','precio','tipo','total','notas','ganancia_pct']
    contenido = _repo_leer("transacciones.csv")
    if contenido and len(contenido) > 60:
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(contenido))
            df['fecha'] = pd.to_datetime(df['fecha'])
            if 'ganancia_pct' not in df.columns:
                df['ganancia_pct'] = np.nan
            # Guardar en disco para que cargar_transacciones() local también funcione
            df.to_csv(TRANSACCIONES_FILE, index=False)
            return df
        except:
            pass
    return pd.DataFrame(columns=cols)

def repo_guardar_transacciones() -> bool:
    """Sube transacciones.csv local al repo."""
    if not os.path.exists(TRANSACCIONES_FILE):
        return False
    try:
        with open(TRANSACCIONES_FILE, 'r', encoding='utf-8') as f:
            contenido = f.read()
        return _repo_escribir("transacciones.csv", contenido, "sincronizar transacciones")
    except:
        return False

def repo_cargar_historial() -> pd.DataFrame:
    """Lee historial_senales.csv desde el repo al disco local."""
    cols = ['fecha','simbolo','score','precio','recomendacion','señales']
    contenido = _repo_leer("historial_senales.csv")
    if contenido and len(contenido) > 60:
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(contenido))
            df['fecha'] = pd.to_datetime(df['fecha'])
            df.to_csv("historial_senales.csv", index=False)
            return df
        except:
            pass
    return pd.DataFrame(columns=cols)

def repo_guardar_historial() -> bool:
    """Sube historial_senales.csv al repo."""
    ruta = "historial_senales.csv"
    if not os.path.exists(ruta):
        return False
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            contenido = f.read()
        return _repo_escribir("historial_senales.csv", contenido, "sincronizar historial señales")
    except:
        return False

# ── ML: persistencia con caché en memoria + repo ─────────────

@st.cache_resource
def _ml_cache_global() -> dict:
    """Cache en memoria de modelos ML entrenados. Sobrevive reruns de la misma sesión."""
    return {}

def repo_guardar_modelo_ml(simbolo: str, clf, accuracy: float):
    """Serializa el modelo ML en base64 y lo guarda en el repo."""
    if not _repo_disponible():
        return
    try:
        import base64
        model_b64 = base64.b64encode(pickle.dumps(clf)).decode("ascii")
        meta = json.loads(_repo_leer("ml_meta.json") or "{}")
        meta[simbolo] = {"accuracy": accuracy, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")}
        _repo_escribir("ml_meta.json", json.dumps(meta, indent=2), "ml meta")
        nombre = f"ml_{simbolo.replace('.','_')}.b64"
        _repo_escribir(nombre, model_b64, f"modelo ML {simbolo}")
    except:
        pass
#actualizado el 19 de abril
def repo_cargar_modelo_ml(simbolo: str):
    """Intenta cargar modelo ML desde repo. Devuelve (modelo, accuracy) o (None, 0)."""
    try:
        meta_str = _repo_leer("ml_meta.json")
        if not meta_str:
            return None, 0
        meta = json.loads(meta_str)
        if simbolo not in meta:
            return None, 0
        # Verificar frescura (máx 7 días)
        fecha_str = meta[simbolo].get("fecha", "")
        if fecha_str:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M")
            if (datetime.now() - fecha).total_seconds() > 604800:   # ← 7 días
                return None, 0
        import base64
        nombre = f"ml_{simbolo.replace('.','_')}.b64"
        b64 = _repo_leer(nombre)
        if b64:
            clf = pickle.loads(base64.b64decode(b64.encode("ascii")))
            return clf, meta[simbolo].get("accuracy", 0)
    except:
        pass
    return None, 0

# ── Backup local descargable ──────────────────────────────────

def generar_backup_zip() -> bytes:
    """Genera un ZIP con todos los datos para descarga local."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # posiciones.json
        posiciones = st.session_state.get('PRECIO_COMPRA', {})
        zf.writestr("posiciones.json",
                    json.dumps(posiciones, indent=2, ensure_ascii=False))
        # transacciones.csv
        if os.path.exists(TRANSACCIONES_FILE):
            zf.write(TRANSACCIONES_FILE, "transacciones.csv")
        # historial_senales.csv
        if os.path.exists("historial_senales.csv"):
            zf.write("historial_senales.csv", "historial_senales.csv")
        # readme
        zf.writestr("LEEME.txt",
            f"Backup Trading App — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            "Para restaurar: usa el boton 'Restaurar desde backup' en el sidebar.")
    buf.seek(0)
    return buf.read()

def restaurar_desde_zip(uploaded_file) -> dict:
    """Lee un ZIP de backup y devuelve las posiciones; restaura CSV al disco."""
    import zipfile
    posiciones = {}
    try:
        with zipfile.ZipFile(io.BytesIO(uploaded_file.read())) as zf:
            nombres = zf.namelist()
            if "posiciones.json" in nombres:
                posiciones = json.loads(zf.read("posiciones.json").decode())
            if "transacciones.csv" in nombres:
                with open(TRANSACCIONES_FILE, 'wb') as f:
                    f.write(zf.read("transacciones.csv"))
            if "historial_senales.csv" in nombres:
                with open("historial_senales.csv", 'wb') as f:
                    f.write(zf.read("historial_senales.csv"))
    except Exception as e:
        st.error(f"Error leyendo backup: {e}")
    return posiciones

# ============================================================
# HISTORIAL DE TRANSACCIONES (con campo ganancia_pct)
# ============================================================
TRANSACCIONES_FILE = "transacciones.csv"

def cargar_transacciones() -> pd.DataFrame:
    if os.path.exists(TRANSACCIONES_FILE):
        df = pd.read_csv(TRANSACCIONES_FILE)
        df['fecha'] = pd.to_datetime(df['fecha'])
        # Si el archivo no tiene la columna ganancia_pct, la agregamos con NaN
        if 'ganancia_pct' not in df.columns:
            df['ganancia_pct'] = np.nan
        return df
    return pd.DataFrame(columns=['fecha', 'simbolo', 'cantidad', 'precio', 'tipo', 'total', 'notas', 'ganancia_pct'])

def guardar_transaccion(simbolo: str, cantidad: float, precio: float, tipo: str, notas: str = "", ganancia_pct: float = None):
    df = cargar_transacciones()
    nueva = pd.DataFrame([{
        'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'simbolo': simbolo.upper(),
        'cantidad': cantidad,
        'precio': precio,
        'tipo': tipo,
        'total': round(cantidad * precio, 2),
        'notas': notas,
        'ganancia_pct': ganancia_pct if ganancia_pct is not None else np.nan
    }])
    df = pd.concat([df, nueva], ignore_index=True)
    df.to_csv(TRANSACCIONES_FILE, index=False)

# ============================================================
# PROCESAR VENTAS MANUALES
# ============================================================
def procesar_ventas(input_text: str):
    """Procesa ventas ingresadas manualmente. Calcula ganancia/pérdida usando el precio de compra registrado."""
    if not input_text or not input_text.strip():
        st.sidebar.warning("No se ingresaron ventas.")
        return
    if 'PRECIO_COMPRA' not in st.session_state:
        st.session_state['PRECIO_COMPRA'] = {}
    PRECIO_COMPRA = st.session_state['PRECIO_COMPRA']
    ventas_registradas = 0
    errores = []
    for linea in input_text.strip().split('\n'):
        if not linea.strip():
            continue
        partes = linea.split(',')
        if len(partes) != 3:
            errores.append(f"Formato incorrecto: {linea}. Debe ser SÍMBOLO,CANTIDAD,PRECIO")
            continue
        simbolo = partes[0].strip().upper()
        try:
            cantidad = float(partes[1].strip())
            precio_venta = float(partes[2].strip())
        except:
            errores.append(f"Cantidad o precio inválido: {linea}")
            continue
        if simbolo not in PRECIO_COMPRA:
            errores.append(f"No hay compra registrada para {simbolo}. No se puede registrar la venta.")
            continue
        precio_compra = PRECIO_COMPRA[simbolo]
        ganancia_pct = ((precio_venta / precio_compra) - 1) * 100
        guardar_transaccion(simbolo, cantidad, precio_venta, "venta", notas="Venta manual", ganancia_pct=ganancia_pct)
        # Eliminar la posición de PRECIO_COMPRA (se asume que se vende toda la posición)
        del PRECIO_COMPRA[simbolo]
        ventas_registradas += 1
    if errores:
        for err in errores:
            st.sidebar.error(err)
    if ventas_registradas:
        st.sidebar.success(f"✅ {ventas_registradas} venta(s) registrada(s).")
        st.session_state['PRECIO_COMPRA'] = PRECIO_COMPRA
        # Persistir estado actualizado en repo
        repo_guardar_posiciones(PRECIO_COMPRA)
        repo_guardar_transacciones()
        st.rerun()

# ============================================================
# HISTORIAL DE SEÑALES (para el dashboard de rendimiento)
# ============================================================
def cargar_historial_senales() -> pd.DataFrame:
    """Carga el archivo de historial de señales (CSV) si existe."""
    if os.path.exists("historial_senales.csv"):
        df = pd.read_csv("historial_senales.csv")
        df['fecha'] = pd.to_datetime(df['fecha'])
        return df
    return pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales'])

# ============================================================
# LISTAS DE MERCADOS (completas – mismas que antes)
# ============================================================
@st.cache_data(ttl=3600)
def cargar_listas():
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
    sp100 = [
        'AAPL','MSFT','AMZN','NVDA','META','GOOGL','GOOG','JPM','V','JNJ','WMT','PG','UNH','HD',
        'DIS','MA','BAC','XOM','CVX','KO','PEP','ADBE','CRM','NFLX','TMO','ABT','ACN','AMD','INTC',
        'CMCSA','TXN','QCOM','COST','NKE','MRK','ABBV','LLY','PFE','BMY','CVS','HON','UPS','BA','CAT',
        'GE','IBM','GS','SPGI','MS','PLD','LMT','MDT','ISRG','BLK','AMGN','GILD','FISV','SYK','ZTS',
        'T','VZ','NEE','DUK','SO','MO','PM','MDLZ','SBUX','MCD','LOW','TGT','TJX','ORCL','NOW','INTU',
        'BKNG','UBER','TSLA','AVGO'
    ]
    nasdaq100 = [
        'ADBE','AMD','AMGN','AMZN','ASML','AVGO','BIIB','BKNG','CDNS','CHTR','CMCSA','COST','CSCO',
        'CSX','CTAS','DXCM','EA','EBAY','EXC','FANG','FAST','FTNT','GILD','GOOGL','GOOG','HON','IDXX',
        'ILMN','INTC','INTU','ISRG','KLAC','LRCX','LULU','MAR','MELI','META','MNST','MSFT','MU','NFLX',
        'NVDA','NXPI','ODFL','ORLY','PANW','PAYX','PCAR','PEP','QCOM','REGN','ROST','SBUX','SNPS','TMUS',
        'TSLA','TXN','VRTX','WBA','WDAY','XEL','ZM','ZS'
    ]
    ibex35 = [
        'SAN.MC','BBVA.MC','TEF.MC','ITX.MC','IBE.MC','FER.MC','ENG.MC','ACS.MC','REP.MC','AENA.MC',
        'CLNX.MC','GRF.MC','MTS.MC','MAP.MC','MEL.MC','CABK.MC','ELE.MC','IAG.MC','ANA.MC','VIS.MC',
        'CIE.MC','LOG.MC','ACX.MC'
    ]
    bmv = [
        'WALMEX.MX','GMEXICOB.MX','CEMEXCPO.MX','FEMSAUBD.MX','AMXL.MX','KOFUBL.MX','GFNORTEO.MX',
        'BBAJIOO.MX','ALFA.MX','ALPEKA.MX','ASURB.MX','GAPB.MX','OMAB.MX','AC.MX','GCC.MX','LALA.MX',
        'MEGA.MX','PINFRA.MX','TLEVISACPO.MX','VESTA.MX','GRUMA.MX','HERDEZ.MX','CUERVO.MX','ORBIA.MX'
    ]
    ia_stocks = [
        'NVDA','AMD','INTC','AI','PLTR','IBM','MSFT','GOOGL','META','SNOW','CRM','ADBE','NOW','ORCL',
        'BIDU','BABA','SAP'
    ]
    commodity_etfs = ['GLD','SLV','USO','UNG','DBC']
    mining_oil = ['NEM','GOLD','FCX','XOM','CVX','COP','EOG','SLB']
    etfs_sectoriales = [
        'XLK','XLV','XLF','XLE','XLI','XLY','XLP','XLU','XLB','XLRE','XLC',
        'SOXX','ARKK','ARKG','ARKW','ARKF','CIBR','ROBO','ICLN','TAN','LIT',
        'JETS','XHB','KRE','IBB','SPY','QQQ','IWM','DIA','VTI'
    ]
    mid_cap_growth = [
        'DDOG','NET','CRWD','ZS','BILL','DUOL','CELH','SMCI','HUBS','MNDY','APPN','PCTY','FIVN',
        'RELY','PATH','SMAR','JAMF','EXAS','NVCR','FATE','RXRX','AFRM','UPST','HOOD','SQ','SOFI',
        'NU','PLUG','CHPT','RIVN','LCID','KTOS','RKLB','ACHR'
    ]
    etfs_emergentes = [
        'EWZ','EWJ','FXI','KWEB','EWY','EWT','EWH','EWA','EWC','EWG','EWQ','EWU','VWO','EEM','INDA','EWX'
    ]
    return (sp100, nasdaq100, ibex35, bmv, sp500,
            ia_stocks, commodity_etfs, mining_oil,
            etfs_sectoriales, mid_cap_growth, etfs_emergentes)

(sp100, nasdaq100, ibex35, bmv, sp500,
 ia_stocks, commodity_etfs, mining_oil,
 etfs_sectoriales, mid_cap_growth, etfs_emergentes) = cargar_listas()

universo_recomendado = list(set(sp100 + etfs_sectoriales + mid_cap_growth))

mercado_opciones = {
    "⚡ Prueba rápida (12 tickers)":          ['AAPL','MSFT','NVDA','TSLA','QQQ','SPY','DDOG','NET','CRWD','XLK','XLF','SOXX'],
    "⭐ Recomendado (S&P100 + ETFs + Growth)": universo_recomendado,
    "📊 S&P 100":                              sp100,
    "📊 S&P 500 (completo)":                   sp500,
    "📊 NASDAQ 100":                           nasdaq100,
    "🏛️ ETFs sectoriales (30)":               etfs_sectoriales,
    "🚀 Mid-cap growth (38)":                  mid_cap_growth,
    "🌎 ETFs mercados emergentes (16)":        etfs_emergentes,
    "🤖 IA (Inteligencia Artificial)":         ia_stocks,
    "🪙 Commodities (ETFs)":                   commodity_etfs,
    "⛏️ Mineras y Petroleras":                mining_oil,
    "🇲🇽 BMV México":                          bmv,
    "🇪🇸 IBEX 35":                             ibex35,
    "🌐 Todo USA (S&P500 + ETFs + Growth)":   list(set(sp500 + etfs_sectoriales + mid_cap_growth)),
    "🌍 Global completo":                      list(set(sp500 + nasdaq100 + ibex35 + bmv + ia_stocks + commodity_etfs + mining_oil + etfs_sectoriales + mid_cap_growth + etfs_emergentes)),
}

# ============================================================
# FUNCIONES DE TIPOS DE CAMBIO (siempre visibles en sidebar)
# ============================================================
@st.cache_data(ttl=3600)
def obtener_tipo_cambio() -> tuple[float, float]:
    try:
        usd = yf.Ticker("USDMXN=X").history(period="1d")
        eur = yf.Ticker("EURMXN=X").history(period="1d")
        return (float(usd['Close'].iloc[-1]) if not usd.empty else 20.0,
                float(eur['Close'].iloc[-1]) if not eur.empty else 21.5)
    except:
        return 20.0, 21.5

# Mostrar tipos de cambio siempre en el sidebar
usd_mxn, eur_mxn = obtener_tipo_cambio()
st.sidebar.markdown("### 💱 Tipos de cambio")
st.sidebar.metric("USD/MXN", f"{usd_mxn:.2f}")
st.sidebar.metric("EUR/MXN", f"{eur_mxn:.2f}")
st.sidebar.markdown("---")

# ============================================================
# SIDEBAR (parámetros)
# ============================================================
st.sidebar.header("⚙️ Parámetros")

# ============================================================
# RESTAURAR DATOS AL INICIAR (se ejecuta UNA vez por sesión)
# ============================================================
if 'datos_cargados' not in st.session_state:
    st.session_state['datos_cargados'] = False

if not st.session_state['datos_cargados']:
    with st.sidebar:
        with st.spinner("🔄 Restaurando datos..."):
            # 1. Cargar posiciones desde repo
            posiciones_repo = repo_cargar_posiciones()
            if posiciones_repo:
                st.session_state['PRECIO_COMPRA'] = posiciones_repo
                st.sidebar.success(
                    f"✅ {len(posiciones_repo)} posición(es) restaurada(s): "
                    f"{', '.join(list(posiciones_repo.keys())[:4])}"
                    f"{'...' if len(posiciones_repo) > 4 else ''}"
                )
            else:
                st.session_state.setdefault('PRECIO_COMPRA', {})
                if _repo_disponible():
                    st.sidebar.info("📂 Repo conectado — sin posiciones guardadas.")
                else:
                    st.sidebar.warning(
                        "⚠️ Sin persistencia activa. "
                        "Agrega GHU_GIST_TOKEN en Secrets (scope: repo)."
                    )
            # 2. Cargar transacciones y historial al disco local
            repo_cargar_transacciones()
            repo_cargar_historial()
            st.session_state['datos_cargados'] = True

# ── Controles de backup en sidebar ──────────────────────────
with st.sidebar.expander("💾 Backup de datos", expanded=False):
    # Descargar backup local
    if st.button("📥 Descargar backup ZIP"):
        zip_bytes = generar_backup_zip()
        fecha = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            label="⬇️ Guardar en mi PC",
            data=zip_bytes,
            file_name=f"trading_backup_{fecha}.zip",
            mime="application/zip",
            key="dl_backup"
        )
    st.caption("Guarda el ZIP en tu computadora como respaldo local.")
    st.markdown("---")
    # Restaurar desde backup local
    uploaded_bk = st.file_uploader(
        "📤 Restaurar desde backup ZIP", type="zip", key="upload_backup"
    )
    if uploaded_bk and st.button("🔄 Restaurar ahora"):
        pos_restauradas = restaurar_desde_zip(uploaded_bk)
        if pos_restauradas:
            st.session_state['PRECIO_COMPRA'] = pos_restauradas
            repo_guardar_posiciones(pos_restauradas)
            repo_guardar_transacciones()
            st.success(f"✅ Restaurado: {len(pos_restauradas)} posiciones")
            st.rerun()
        else:
            st.warning("No se encontraron posiciones en el ZIP.")

# ── Estado de conexión al repo ───────────────────────────────
if _repo_disponible():
    st.sidebar.caption("☁️ Repo GitHub conectado")
else:
    st.sidebar.caption("⚫ Sin repo — datos solo en sesión")
mercado_seleccionado = st.sidebar.selectbox("📊 Mercado", list(mercado_opciones.keys()), index=1)

st.sidebar.markdown("### 🔧 Análisis")
fundamentales_check  = st.sidebar.checkbox("📊 Análisis fundamental (profundo)", value=False)
filtro_fundamentales = st.sidebar.checkbox("📊 Solo fundamentales sólidos", value=False) if fundamentales_check else False
backtesting_check    = st.sidebar.checkbox("🧪 Backtesting realista (SL/TP)", value=True)
market_regime_check  = st.sidebar.checkbox("🌡️ Filtrar por Market Regime", value=True)
ia_check = st.sidebar.checkbox("🤖 Análisis IA", value=True)
sentiment_check = st.sidebar.checkbox("📰 Análisis de sentimiento (noticias)", value=False)
ml_check = st.sidebar.checkbox("🧠 Modelo predictivo (ML)", value=False)

st.sidebar.markdown("### 💼 Gestión de capital")
capital_total = st.sidebar.number_input("Capital disponible (MXN)", min_value=1000.0, value=100_000.0, step=1000.0)
riesgo_pct = st.sidebar.slider("Riesgo máximo por operación (%)", min_value=0.5, max_value=3.0, value=1.0, step=0.25)

st.sidebar.markdown("### 🔔 Alertas")
alerta_email    = st.sidebar.checkbox("📧 Alertar por email", value=True)
alerta_whatsapp = st.sidebar.checkbox("💬 Alertar por WhatsApp", value=False)
umbral_score    = st.sidebar.slider("Umbral mínimo para alertar (score)", 4, 10, 7)

st.sidebar.markdown("### 💰 Registrar compra")
compra_input = st.sidebar.text_area("Compra (una por línea)", placeholder="AAPL,10,4465.53\nWALMEX.MX,5,56.13", height=120)

st.sidebar.markdown("### 💰 Registrar venta")
venta_input = st.sidebar.text_area("Venta (una por línea)", placeholder="AAPL,10,4750.00\nWALMEX.MX,5,60.00", height=120)
if st.sidebar.button("📉 REGISTRAR VENTA", type="secondary"):
    procesar_ventas(venta_input)

st.sidebar.markdown("### 📂 Google Drive")
drive_upload = st.sidebar.checkbox("💾 Guardar informe en Google Drive", value=False)

# ============================================================
# FUNCIONES DE ANÁLISIS TÉCNICO, SCORE, BACKTESTING, ETC.
# ============================================================
def safe_history(ticker, period="6mo", max_retries=3):
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

    # Nuevos indicadores 19.04.2026
    hist['ROC'] = (hist['Close'] / hist['Close'].shift(10) - 1) * 100
    low14 = hist['Low'].rolling(14).min()
    high14 = hist['High'].rolling(14).max()
    hist['WILLR'] = -100 * (high14 - hist['Close']) / (high14 - low14)
    hist['OBV'] = (np.sign(hist['Close'].diff()) * hist['Volume']).cumsum()
    hist['ATR_RATIO'] = hist['ATR'] / hist['Close']
    hist['DOW'] = hist.index.dayofweek
    
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

def position_size(precio: float, atr: float, capital: float, riesgo_pct: float) -> dict:
    riesgo_mxn = capital * (riesgo_pct / 100)
    stop_dist  = 2 * atr
    if stop_dist <= 0:
        return {'unidades': 0, 'inversion_mxn': 0, 'pct_capital': 0}
    unidades   = riesgo_mxn / stop_dist
    inversion  = min(unidades * precio, capital * 0.20)
    pct_capital = (inversion / capital) * 100
    return {'unidades': round(unidades, 2), 'inversion_mxn': round(inversion, 2), 'pct_capital': round(pct_capital, 1)}
@st.cache_data(ttl=3600)
def obtener_regimen_diario() -> pd.Series:
    """Devuelve una Serie con el régimen diario del S&P 500 (2=alcista, 1=lateral, 0=bajista)."""
    sp = yf.Ticker("^GSPC").history(period="3y")
    if sp.empty:
        return pd.Series()
    sp['EMA200'] = sp['Close'].ewm(span=200).mean()
    sp['EMA50'] = sp['Close'].ewm(span=50).mean()
    cond_alta = (sp['Close'] > sp['EMA200']) & (sp['Close'] > sp['EMA50']) & (sp['EMA50'] > sp['EMA200'])
    cond_lateral = (sp['Close'] > sp['EMA200']) & (~cond_alta)
    sp['REGIME'] = 0
    sp.loc[cond_lateral, 'REGIME'] = 1
    sp.loc[cond_alta, 'REGIME'] = 2
    return sp['REGIME']

def obtener_fundamentales_profundos(simbolo: str) -> dict:
    try:
        info = yf.Ticker(simbolo).info
        dy = info.get('dividendYield')
        roe = info.get('returnOnEquity')
        rg = info.get('revenueGrowth')
        eg = info.get('earningsGrowth')
        pm = info.get('profitMargins')
        # Nuevos indicadores profundos
        debt_to_equity = info.get('debtToEquity')
        free_cashflow = info.get('freeCashflow')
        roa = info.get('returnOnAssets')
        ebitda_margin = info.get('ebitdaMargins')
        return {
            'P/E (ttm)':       info.get('trailingPE'),
            'P/E forward':     info.get('forwardPE'),
            'P/B':             info.get('priceToBook'),
            'Div Yield (%)':   round(dy * 100, 2) if dy else None,
            'ROE (%)':         round(roe * 100, 2) if roe else None,
            'Rev Growth (%)':  round(rg * 100, 2) if rg else None,
            'EPS Growth (%)':  round(eg * 100, 2) if eg else None,
            'Net Margin (%)':  round(pm * 100, 2) if pm else None,
            'Debt/Equity':     round(debt_to_equity, 2) if debt_to_equity else None,
            'Free Cash Flow':  round(free_cashflow / 1e6, 2) if free_cashflow else None,  # en millones
            'ROA (%)':         round(roa * 100, 2) if roa else None,
            'EBITDA Margin (%)': round(ebitda_margin * 100, 2) if ebitda_margin else None,
        }
    except:
        return {}

def backtest_realista(simbolo: str, precio_entrada: float, atr: float, window_dias=30) -> dict:
    try:
        ticker = yf.Ticker(simbolo)
        hist = safe_history(ticker, "6mo")
        if hist.empty:
            return {'resultado': 0, 'tipo': 'error'}
        factor = 20.0 if not simbolo.endswith('.MX') else 1.0
        hist_mxn = hist.copy()
        hist_mxn['Close'] *= factor
        sl = precio_entrada - 2 * atr
        tp = precio_entrada + 3 * atr
        forward = hist_mxn.iloc[-window_dias:]
        for precio in forward['Close']:
            if precio <= sl:
                ret = (sl / precio_entrada - 1) * 100 - 0.15
                return {'resultado': ret, 'tipo': 'SL'}
            if precio >= tp:
                ret = (tp / precio_entrada - 1) * 100 - 0.15
                return {'resultado': ret, 'tipo': 'TP'}
        ret = (forward['Close'].iloc[-1] / precio_entrada - 1) * 100 - 0.15
        return {'resultado': ret, 'tipo': 'cierre'}
    except:
        return {'resultado': 0, 'tipo': 'error'}

def backtest_optimizar_parametros(hist_anual: pd.DataFrame) -> dict:
    """
    Realiza un grid search sobre umbral de score y multiplicadores de ATR para encontrar la combinación
    que maximiza el win rate en los últimos 6 meses.
    """
    if hist_anual.empty or len(hist_anual) < 200:
        return {'best_score_thresh': 5, 'best_atr_mult': 2, 'best_win_rate': 0}
    best_win_rate = 0
    best_score_thresh = 5
    best_atr_mult = 2
    # Simulación simple: para cada combinación, generar señales de compra en los últimos 6 meses
    for score_thresh in [4,5,6]:
        for atr_mult in [2, 2.5, 3]:
            señales = []
            for i in range(50, len(hist_anual)-10):
                ventana = hist_anual.iloc[:i]
                r = ventana.iloc[-1].to_dict()
                p = ventana.iloc[-2].to_dict() if len(ventana)>=2 else None
                score_base, _ = calcular_score(r, p)
                if score_base >= score_thresh:
                    precio_entrada = hist_anual['Close'].iloc[i]
                    atr = r['ATR']
                    sl = precio_entrada - atr_mult * atr
                    tp = precio_entrada + 1.5 * atr_mult * atr
                    for j in range(i+1, min(i+30, len(hist_anual))):
                        precio_salida = hist_anual['Close'].iloc[j]
                        if precio_salida <= sl:
                            señales.append(0)  # pérdida
                            break
                        if precio_salida >= tp:
                            señales.append(1)  # ganancia
                            break
                    else:
                        señales.append(0)  # no se alcanzó objetivo
            if señales:
                win_rate = sum(señales)/len(señales)*100
                if win_rate > best_win_rate:
                    best_win_rate = win_rate
                    best_score_thresh = score_thresh
                    best_atr_mult = atr_mult
    return {'best_score_thresh': best_score_thresh, 'best_atr_mult': best_atr_mult, 'best_win_rate': round(best_win_rate,1)}

def entrenar_modelo_ml(simbolo: str, usd_mxn: float, eur_mxn: float) -> dict:
    """
    Entrena un modelo predictivo (RandomForest) con:
    - Walk‑forward (últimos 2 años)
    - Target de 3 clases (subida >1.5%, bajada >1.5%, lateral)
    - Feature: régimen de mercado (alcista/lateral/bajista)
    - Validación temporal (TimeSeriesSplit)
    - GridSearch de hiperparámetros
    - Probabilidades calibradas
    - Caché en memoria y persistencia en repo (7 días)
    """
    cache = _ml_cache_global()

    # 1. Caché en memoria (válido 7 días)
    if simbolo in cache:
        entrada = cache[simbolo]
        if (datetime.now() - entrada['ts']).total_seconds() < 604800:
            return {'model': entrada['model'], 'accuracy': entrada['acc'], 'fuente': '⚡ memoria'}

    # 2. Cargar desde repo (si tiene menos de 7 días)
    clf_repo, acc_repo = repo_cargar_modelo_ml(simbolo)
    if clf_repo is not None:
        cache[simbolo] = {'model': clf_repo, 'acc': acc_repo, 'ts': datetime.now()}
        return {'model': clf_repo, 'accuracy': acc_repo, 'fuente': '☁️ repo'}

    # 3. Entrenar desde cero
    try:
        ticker = yf.Ticker(simbolo)
        hist = safe_history(ticker, "3y")   # 3 años de datos
        if hist.empty or len(hist) < 200:
            return None

        # Convertir a MXN
        factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
        for col in ['Close','Open','High','Low']:
            hist[col] *= factor

        # Añadir régimen de mercado como feature
        regime_series = obtener_regimen_diario()
        hist = hist.join(regime_series.rename('REGIME'), how='left')
        hist['REGIME'] = hist['REGIME'].fillna(method='ffill').fillna(1)

        # Calcular indicadores (debe incluir ROC, WILLR, OBV, ATR_RATIO, DOW)
        hist = calcular_indicadores(hist)
        hist = hist.dropna()
        if len(hist) < 200:
            return None

        # Target: 3 clases (subida >1.5%, bajada >1.5%, lateral)
        ret_futuro = (hist['Close'].shift(-5) / hist['Close'] - 1) * 100
        hist['target'] = np.select(
            [ret_futuro > 1.5, ret_futuro < -1.5],
            [2, 0],   # 2=subida, 0=bajada, 1=lateral
            default=1
        )
        hist = hist.dropna()

        # Features (incluir las nuevas y REGIME)
        features = [
            'EMA20', 'EMA50', 'RSI', 'MACD', 'MACD_sig', 'ATR', 'BB_pct',
            'STOCH_K', 'STOCH_D', 'Volume', 'Vol_avg',
            'ROC', 'WILLR', 'OBV', 'ATR_RATIO', 'DOW', 'REGIME'
        ]
        # Asegurar que todas existan
        for f in features:
            if f not in hist.columns:
                hist[f] = 0
        X = hist[features]
        y = hist['target']

        # Walk‑forward: usar solo los últimos 2 años (aprox 504 días)
        if len(X) > 504:
            X = X.tail(504)
            y = y.tail(504)

        # Validación temporal (TimeSeriesSplit)
        from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
        tscv = TimeSeriesSplit(n_splits=3)

        # GridSearch para RandomForest (class_weight='balanced' para manejar desbalanceo)
        from sklearn.ensemble import RandomForestClassifier
        param_grid = {
            'n_estimators': [50, 100],
            'max_depth': [3, 5, 7],
            'min_samples_split': [2, 5],
            'class_weight': ['balanced', None]
        }
        grid = GridSearchCV(RandomForestClassifier(random_state=42),
                            param_grid, cv=tscv, scoring='f1_macro', n_jobs=-1)
        grid.fit(X, y)

        best_clf = grid.best_estimator_
        raw_f1 = grid.best_score_ * 100

        # Calibrar probabilidades (para obtener certeza más realista)
        from sklearn.calibration import CalibratedClassifierCV
        calibrated_clf = CalibratedClassifierCV(best_clf, method='sigmoid', cv=3)
        calibrated_clf.fit(X, y)

        # Evaluación final (F1 macro)
        from sklearn.metrics import f1_score
        y_pred = calibrated_clf.predict(X)
        final_f1 = f1_score(y, y_pred, average='macro') * 100

        # Guardar en caché y repo
        cache[simbolo] = {'model': calibrated_clf, 'acc': round(final_f1, 1), 'ts': datetime.now()}
        repo_guardar_modelo_ml(simbolo, calibrated_clf, final_f1)

        return {'model': calibrated_clf, 'accuracy': round(final_f1, 1), 'fuente': '🔄 entrenado'}

    except Exception as e:
        print(f"Error entrenando ML para {simbolo}: {e}")
        return None

def analizar_sentimiento(simbolo: str) -> dict:
    """
    Obtiene noticias recientes de NewsAPI (últimos 3 días) y calcula sentimiento promedio con TextBlob.
    Retorna {'sentimiento': 'positivo/negativo/neutral', 'score': -1..1, 'noticias': list}
    """
    if not NEWSAPI_KEY:
        return {'sentimiento': 'Sin clave', 'score': 0, 'noticias': []}
    try:
        from_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        url = 'https://newsapi.org/v2/everything'
        params = {
            'q': simbolo.split('.')[0],
            'from': from_date,
            'sortBy': 'relevancy',
            'language': 'en',
            'pageSize': 5,
            'apiKey': NEWSAPI_KEY
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return {'sentimiento': 'Error API', 'score': 0, 'noticias': []}
        data = resp.json()
        if data['status'] != 'ok':
            return {'sentimiento': 'Sin noticias', 'score': 0, 'noticias': []}
        articles = data['articles']
        if not articles:
            return {'sentimiento': 'Sin noticias', 'score': 0, 'noticias': []}
        scores = []
        titles = []
        for art in articles[:3]:
            titulo = art['title']
            titles.append(titulo)
            blob = TextBlob(titulo)
            scores.append(blob.sentiment.polarity)
        avg_score = np.mean(scores)
        if avg_score > 0.1:
            sentimiento = 'positivo'
        elif avg_score < -0.1:
            sentimiento = 'negativo'
        else:
            sentimiento = 'neutral'
        return {'sentimiento': sentimiento, 'score': round(avg_score,2), 'noticias': titles}
    except Exception as e:
        return {'sentimiento': 'Error', 'score': 0, 'noticias': []}

def optimizar_cartera(compras_df: pd.DataFrame, capital: float, usd_mxn: float, eur_mxn: float) -> pd.DataFrame:
    """
    Dada una lista de acciones con señal de compra, asigna pesos óptimos usando la matriz de correlación
    histórica (últimos 3 meses) y maximiza el ratio de Sharpe. Retorna DataFrame con asignación.
    """
    if compras_df.empty or len(compras_df) < 2:
        return compras_df
    symbols = compras_df['Símbolo'].tolist()
    # Obtener datos históricos de precios en MXN
    precios = {}
    for sim in symbols:
        try:
            ticker = yf.Ticker(sim)
            hist = safe_history(ticker, "6mo")
            if hist.empty:
                continue
            factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
            precios[sim] = hist['Close'] * factor
        except:
            continue
    if not precios or len(precios) < 2:
        return compras_df
    # Crear DataFrame de retornos diarios
    df_prices = pd.DataFrame(precios)
    df_prices = df_prices.dropna()
    if df_prices.empty:
        return compras_df
    returns = df_prices.pct_change().dropna()
    # Matriz de covarianza
    cov = returns.cov() * 252  # anualizada
    # Suponemos rendimiento esperado proporcional al score (simple)
    expected_returns = compras_df.set_index('Símbolo')['Score'] / 100
    # Optimización de cartera: maximizar Sharpe (pesos sin restricciones)
    # Usamos fórmula analítica: pesos = inv(cov) * ret / (suma de pesos)
    try:
        inv_cov = np.linalg.pinv(cov.values)
        ret_vec = expected_returns.reindex(cov.index).values
        w = inv_cov @ ret_vec
        w = w / w.sum()
        w = np.maximum(w, 0)  # sin cortos
        w = w / w.sum()
        asignacion = {}
        for i, sym in enumerate(cov.index):
            asignacion[sym] = w[i]
    except:
        # fallback: pesos iguales
        n = len(cov.index)
        asignacion = {sym: 1/n for sym in cov.index}
    # Asignar inversión
    compras_df['Peso Cartera'] = compras_df['Símbolo'].map(asignacion).fillna(0)
    compras_df['Inversión Asignada'] = compras_df['Peso Cartera'] * capital
    compras_df['Unidades Ajustadas'] = compras_df['Inversión Asignada'] / compras_df['Precio (MXN)'].astype(float)
    return compras_df

# ============================================================
# ALERTAS Y GRÁFICOS
# ============================================================
def enviar_email(asunto: str, cuerpo_html: str) -> bool:
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = EMAIL_REMITENTE
        msg["To"]      = EMAIL_DESTINO
        msg.attach(MIMEText(cuerpo_html, "html"))
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

def construir_email_html(compras_df: pd.DataFrame, ventas_df: pd.DataFrame, resumen_ia: str = "") -> str:
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    filas_compra = "".join([f"<tr><td><b>{r['Símbolo']}</b></td><td>{r['Precio (MXN)']}</td><td>{r.get('Score','')}</td><td>{r.get('Motivo','')}</td></tr>" for _, r in compras_df.iterrows()])
    filas_venta = "".join([f"<tr><td><b>{r['Símbolo']}</b></td><td>{r['Precio (MXN)']}</td><td>{r.get('Motivo','')}</td></tr>" for _, r in ventas_df.iterrows()])
    bloque_ia = f"<h3 style='color:#7b61ff'>🤖 Análisis de IA</h3><div style='background:#f5f3ff;padding:12px 16px;border-left:4px solid #7b61ff;border-radius:4px;font-size:14px;line-height:1.6'>{resumen_ia.replace(chr(10), '<br>')}</div>" if resumen_ia else ""
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px">
    <h2 style="color:#1a73e8">📈 Alerta de Trading — {fecha}</h2>
    {bloque_ia}
    <h3 style="color:#34a853">🟢 Señales de COMPRA ({len(compras_df)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
      <tr style="background:#e8f5e9"><th>Símbolo</th><th>Precio (MXN)</th><th>Score</th><th>Motivo</th></tr>
      {filas_compra if filas_compra else '<tr><td colspan="4">Sin señales</td></tr>'}
    </table>
    <h3 style="color:#ea4335">🔴 Señales de VENTA ({len(ventas_df)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
      <tr style="background:#fce8e6"><th>Símbolo</th><th>Precio (MXN)</th><th>Motivo</th></tr>
      {filas_venta if filas_venta else '<tr><td colspan="3">Sin señales</td></tr>'}
    </table>
    <p style="color:#666;font-size:12px;margin-top:20px">Generado por Sistema de Trading Personal v3.0</p>
    </body></html>"""

def grafico_enriquecido(simbolo: str, usd_mxn: float, eur_mxn: float) -> go.Figure:
    hist = safe_history(yf.Ticker(simbolo), "6mo")
    if hist.empty:
        return go.Figure()
    factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
    for col in ['Close','Open','High','Low']:
        hist[col] *= factor
    hist = calcular_indicadores(hist)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, row_heights=[0.5, 0.18, 0.18, 0.14], vertical_spacing=0.03, subplot_titles=[f"{simbolo} — Precio (MXN)", "RSI (14)", "MACD", "Volumen"])
    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Precio"), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA20'], line=dict(color='#ff9800', width=1.5), name='EMA20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA50'], line=dict(color='#e91e63', width=1.5), name='EMA50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], line=dict(color='#7e57c2', width=1.5), name='RSI'), row=2, col=1)
    colors_hist = ['#26a69a' if v >= 0 else '#ef5350' for v in hist['MACD_hist'].fillna(0)]
    fig.add_trace(go.Bar(x=hist.index, y=hist['MACD_hist'], marker_color=colors_hist, name='MACD Hist'), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD'], line=dict(color='#2196f3', width=1.5), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD_sig'], line=dict(color='#ff5722', width=1.5), name='Señal'), row=3, col=1)
    vol_colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(hist['Close'], hist['Open'])]
    fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], marker_color=vol_colors, name='Volumen'), row=4, col=1)
    fig.update_layout(template='plotly_dark', height=750, xaxis_rangeslider_visible=False, legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1))
    return fig

def dashboard_rendimiento(df_hist: pd.DataFrame) -> None:
    """Muestra gráfico de rendimiento acumulado y tabla de win rate por score."""
    if df_hist.empty:
        st.info("Aún no hay suficientes datos históricos para mostrar rendimiento.")
        return
    # Calcular retornos simulados para cada señal (asumiendo compra a precio y cierre a 5 días)
    df_hist['fecha'] = pd.to_datetime(df_hist['fecha'])
    df_hist = df_hist.sort_values('fecha')
    returns = []
    for _, row in df_hist.iterrows():
        try:
            ticker = yf.Ticker(row['simbolo'])
            end_date = datetime.now()
            start_date = end_date - timedelta(days=180)
            hist = ticker.history(start=start_date, end=end_date)
            if hist.empty:
                continue
            idx = hist.index.searchsorted(row['fecha'])
            if idx + 5 >= len(hist):
                continue
            ret = (hist['Close'].iloc[idx+5] / row['precio'] - 1) * 100
            returns.append(ret)
        except:
            continue
    if returns:
        df_hist['retorno'] = returns
        df_hist['ret_acum'] = (1 + df_hist['retorno']/100).cumprod()
        fig = px.line(df_hist, x='fecha', y='ret_acum', title='Rendimiento acumulado de señales')
        st.plotly_chart(fig, use_container_width=True)
        # Win rate por rango de score
        df_hist['score_range'] = pd.cut(df_hist['score'], bins=[0,4,6,8,14], labels=['0-3','4-5','6-7','8+'])
        win_rate = df_hist.groupby('score_range')['retorno'].apply(lambda x: (x>0).mean()*100).reset_index()
        win_rate.columns = ['Score', 'Win Rate (%)']
        st.dataframe(win_rate, use_container_width=True)
    else:
        st.info("No hay suficientes datos para calcular rendimiento.")

def guardar_en_drive(contenido_bytes: bytes, nombre_archivo: str):
    """Guarda el archivo en Google Drive usando autenticación OAuth2."""
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    creds = None
    token_file = 'token.json'
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
    service = build('drive', 'v3', credentials=creds)
    # Buscar carpeta "Trading" o crearla
    folder_id = None
    results = service.files().list(q="name='Trading' and mimeType='application/vnd.google-apps.folder' and trashed=false", fields="files(id)").execute()
    folders = results.get('files', [])
    if folders:
        folder_id = folders[0]['id']
    else:
        folder_metadata = {'name': 'Trading', 'mimeType': 'application/vnd.google-apps.folder'}
        folder = service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
    # Subir archivo
    file_metadata = {'name': nombre_archivo, 'parents': [folder_id]}
    media = googleapiclient.http.MediaIoBaseUpload(io.BytesIO(contenido_bytes), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    st.success(f"Archivo guardado en Google Drive (carpeta 'Trading')")

# ============================================================
# ANÁLISIS IA
# ============================================================
def _calcular_hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()

def _guardar_cache_ia(prompt: str, respuesta: str):
    os.makedirs("cache_ia", exist_ok=True)
    key = _calcular_hash_prompt(prompt)
    with open(f"cache_ia/{key}.json", 'w', encoding='utf-8') as f:
        json.dump({'timestamp': time.time(), 'prompt': prompt, 'respuesta': respuesta}, f, ensure_ascii=False, indent=2)

def _obtener_cache_ia(prompt: str) -> str | None:
    key = _calcular_hash_prompt(prompt)
    ruta = f"cache_ia/{key}.json"
    if not os.path.exists(ruta):
        return None
    with open(ruta, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if time.time() - data.get('timestamp', 0) < 3600:
        return data.get('respuesta')
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
    errores = []
    for nombre, key in proveedores:
        if not key:
            continue
        try:
            if nombre == "Gemini":
                url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={key}"
                resp = requests.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=30
                )
                if resp.status_code != 200:
                    errores.append(f"Gemini {resp.status_code}: {resp.text[:200]}")
                    continue
                texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

            elif nombre == "Groq":
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model":    "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 800,
                    },
                    timeout=30,
                )
                if resp.status_code != 200:
                    errores.append(f"Groq {resp.status_code}: {resp.text[:200]}")
                    continue
                texto = resp.json()["choices"][0]["message"]["content"]

            else:
                continue

            _guardar_cache_ia(prompt, texto)
            return texto

        except Exception as e:
            errores.append(f"{nombre}: {str(e)}")
            continue

    detalle = " | ".join(errores) if errores else "sin keys configuradas"
    return f"**IA no disponible** — {detalle}"

# ============================================================
# FUNCIÓN ANALIZAR ACCIÓN (DEFINICIÓN COMPLETA)
# ============================================================
def analizar_accion(args: tuple) -> dict | None:
    simbolo, precio_compra_dict, usd_mxn, eur_mxn, incluir_fund, incluir_bt, regime_bonus, capital, riesgo_pct = args
    try:
        periodo = "6mo" if incluir_bt else "3mo"
        ticker = yf.Ticker(simbolo)
        hist = safe_history(ticker, periodo)
        if hist.empty:
            return None

        factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
        for col in ['Close','Open','High','Low']:
            hist[col] *= factor

        hist = calcular_indicadores(hist)
        hist = hist.dropna(subset=['RSI','MACD','EMA20','EMA50','ATR','STOCH_K','STOCH_D'])
        if len(hist) < 2:
            return None

        ultimo = hist.iloc[-1].to_dict()
        penultimo = hist.iloc[-2].to_dict()

        if ultimo['Volume'] < (500_000 if not simbolo.endswith('.MX') else 1_000_000):
            return None

        precio = ultimo['Close']
        atr = ultimo['ATR']
        score_base, señales = calcular_score(ultimo, penultimo)
        score = max(0, score_base + regime_bonus)

        ps = position_size(precio, atr, capital, riesgo_pct)

        p_compra = precio_compra_dict.get(simbolo)
        señales_venta = []
        if p_compra:
            ganancia = ((precio / p_compra) - 1) * 100
            if ganancia >= 15:
                señales_venta.append(f"🎯 Take Profit +{ganancia:.1f}%")
            elif ganancia <= -7:
                señales_venta.append(f"🛑 Stop Loss {ganancia:.1f}%")

        if señales_venta:
            recomendacion = "VENDER"
            motivo = señales_venta[0]
        elif score >= 8:
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
            'Símbolo': simbolo,
            'Precio (MXN)': round(precio, 2),
            'Score': score,
            'RSI': round(ultimo['RSI'], 1),
            'ATR': round(atr, 2),
            'Stop Loss': round(precio - 2 * atr, 2),
            'Take Profit': round(precio + 3 * atr, 2),
            'Unidades': ps['unidades'],
            'Inversión (MXN)': ps['inversion_mxn'],
            '% Capital': ps['pct_capital'],
            'Dist EMA50': round((precio / ultimo['EMA50'] - 1) * 100, 2),
            'Recomendación': recomendacion,
            'Motivo': motivo,
            'Señales': " | ".join(señales),
        }

        if incluir_fund:
            resultado.update(obtener_fundamentales_profundos(simbolo))

        if incluir_bt and recomendacion.startswith("COMPRAR"):
            bt = backtest_realista(simbolo, precio, atr)
            resultado['BT Resultado'] = f"{bt['resultado']:.2f}% ({bt['tipo']})"

        return resultado
    except Exception:
        return None

# ============================================================
# BOTÓN DE ANÁLISIS
# ============================================================
if st.sidebar.button("🔍 ANALIZAR", type="primary"):
    # ── Cargar compras previas del session_state (persisten entre reruns) ──
    PRECIO_COMPRA = dict(st.session_state.get('PRECIO_COMPRA', {}))

    # ── Agregar/actualizar con lo que el usuario escribió ahora ──
    if compra_input and compra_input.strip():
        for linea in compra_input.strip().split('\n'):
            if not linea.strip():
                continue
            linea = linea.strip()
            if '=' in linea:
                partes = linea.split('=', 1)
                if len(partes) == 2:
                    sim = partes[0].strip().upper()
                    resto = partes[1].strip()
                    if ',' in resto:
                        try:
                            cant_str, prec_str = resto.split(',', 1)
                            cantidad = float(cant_str.strip())
                            precio = float(prec_str.strip())
                        except:
                            continue
                    else:
                        cantidad = 1.0
                        precio = float(resto)
            else:
                partes = linea.split(',')
                if len(partes) == 3:
                    sim = partes[0].strip().upper()
                    try:
                        cantidad = float(partes[1].strip())
                        precio = float(partes[2].strip())
                    except:
                        continue
                else:
                    continue
            guardar_transaccion(sim, cantidad, precio, "compra")
            PRECIO_COMPRA[sim] = precio
        if PRECIO_COMPRA:
            st.sidebar.success(f"✅ {len(PRECIO_COMPRA)} compra(s) registrada(s).")
            # Persistir en repo inmediatamente
            repo_guardar_posiciones(PRECIO_COMPRA)
            repo_guardar_transacciones()

    usd_mxn, eur_mxn = obtener_tipo_cambio()
    regime_data = obtener_market_regime()
    regime_bonus = regime_data['score_bonus'] if market_regime_check else 0
    trade_capital = capital_total * 0.25

    # ── Panel Core + Satélite (aparece solo después de ANALIZAR) ──
    etf_cap   = round(capital_total * 0.65, 2)
    trade_cap = round(capital_total * 0.25, 2)
    conv_cap  = round(capital_total * 0.10, 2)
    st.markdown("### 💼 Estrategia recomendada: Core + Satélite")
    c1, c2, c3 = st.columns(3)
    c1.metric("🏛️ Core — ETFs (65%)",         f"${etf_cap:,.0f} MXN",
              help="VOO, QQQ, IVV — comprar y mantener, no tocar")
    c2.metric("⚡ Satélite — Trading (25%)",   f"${trade_cap:,.0f} MXN",
              help="Tu sistema activo con este scanner")
    c3.metric("🎯 Alta convicción (10%)",       f"${conv_cap:,.0f} MXN",
              help="1-2 ideas con investigación fundamental profunda")
    st.caption(f"Position sizing sobre ${trade_cap:,.0f} MXN · "
               f"Riesgo por operación: {riesgo_pct}% = "
               f"${trade_cap * riesgo_pct / 100:,.0f} MXN máx. por trade")
    st.markdown("---")

    lista_acciones = mercado_opciones[mercado_seleccionado].copy()  # copia para no modificar original
    # 🔧 Añadir símbolos registrados en PRECIO_COMPRA (incluso si no están en la lista)
    if PRECIO_COMPRA:
        for sim in PRECIO_COMPRA.keys():
            if sim not in lista_acciones:
                lista_acciones.append(sim)

    total = len(lista_acciones)

    with st.spinner(f"Analizando {total} acciones en paralelo..."):
        resultados = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        completados = 0
        args_list = [
            (sim, PRECIO_COMPRA, usd_mxn, eur_mxn, fundamentales_check,
             backtesting_check, regime_bonus, trade_capital, riesgo_pct)
            for sim in lista_acciones
        ]

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(analizar_accion, args): args[0] for args in args_list}
            for future in as_completed(futures):
                completados += 1
                status_text.text(f"Procesando {completados}/{total}: {futures[future]}")
                res = future.result()
                if res:
                    resultados.append(res)
                progress_bar.progress(completados / total)

        status_text.empty()
        progress_bar.empty()

    if not resultados:
        st.warning("⚠️ No se encontraron resultados. Verifica tu conexión o el mercado seleccionado.")
        st.stop()

    df = pd.DataFrame(resultados)

    # Añadir fundamentales profundos
    if fundamentales_check:
        # Ya se añaden en analizar_accion, pero si se añaden nuevos campos, los traemos
        pass

    ventas = df[(df['Recomendación'] == 'VENDER') & (df['Símbolo'].isin(PRECIO_COMPRA.keys()))].copy() if PRECIO_COMPRA else pd.DataFrame()
    compras = df[df['Recomendación'].str.startswith('COMPRAR')].sort_values('Score', ascending=False).copy()
    observar = df[df['Recomendación'] == 'OBSERVAR'].sort_values('Score', ascending=False).copy()

    # Añadir sentimiento a las compras
    if sentiment_check and not compras.empty:
        with st.spinner("Analizando sentimiento de noticias..."):
            for idx, row in compras.iterrows():
                sent = analizar_sentimiento(row['Símbolo'])
                compras.at[idx, 'Sentimiento'] = sent['sentimiento']
                compras.at[idx, 'Sentimiento Score'] = sent['score']
                compras.at[idx, 'Noticias'] = "; ".join(sent['noticias'][:2]) if sent['noticias'] else ""

    # Añadir predicción ML
    if ml_check and not compras.empty:
        with st.spinner("🧠 Cargando modelos predictivos..."):
            for idx, row in compras.iterrows():
                model_info = entrenar_modelo_ml(row['Símbolo'], usd_mxn, eur_mxn)
                if model_info:
                    fuente = model_info.get('fuente', '')
                    compras.at[idx, 'ML Predicción'] = f"{fuente} Subida {model_info['accuracy']}%"
                else:
                    compras.at[idx, 'ML Predicción'] = "No disponible"

    # Optimización de cartera
    if not compras.empty:
        compras = optimizar_cartera(compras, trade_capital, usd_mxn, eur_mxn)

    st.session_state['df'] = df
    st.session_state['compras'] = compras
    st.session_state['ventas'] = ventas
    st.session_state['observar'] = observar
    st.session_state['PRECIO_COMPRA'] = PRECIO_COMPRA
    st.session_state['usd_mxn'] = usd_mxn
    st.session_state['eur_mxn'] = eur_mxn
    st.session_state['regime'] = regime_data
    st.session_state['capital'] = capital_total
    st.session_state['ultima_actualizacion'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # Persistir posiciones y transacciones en el repo
    if PRECIO_COMPRA:
        repo_guardar_posiciones(PRECIO_COMPRA)
    repo_guardar_transacciones()

    if ia_check and not compras.empty:
        with st.spinner("🤖 Analizando con IA..."):
            texto_ia = analisis_ia(compras.head(8).to_dict('records'), regime_data, usd_mxn)
            st.session_state['analisis_ia'] = texto_ia

    # Alertas (email, WhatsApp)
    compras_alerta = compras[compras['Score'] >= umbral_score]
    resumen_ia = st.session_state.get('analisis_ia', '')
    if (alerta_email or alerta_whatsapp) and (not compras_alerta.empty or not ventas.empty):
        with st.spinner("📤 Enviando alertas..."):
            if alerta_email:
                html = construir_email_html(compras_alerta, ventas, resumen_ia)
                enviar_email(f"📈 Alerta Trading {datetime.now().strftime('%d/%m %H:%M')}", html)
            if alerta_whatsapp:
                # No enviar WhatsApp si estamos en GitHub Actions (solo el scanner lo hará)
                if os.environ.get("GITHUB_ACTIONS") == "true":
                    print("⚠️ Omitiendo WhatsApp desde app.py (ejecución automática)")
                else:
                    n_compras = len(compras_alerta)
                    n_ventas = len(ventas)
                    top3 = ", ".join(compras_alerta.head(3)['Símbolo'].tolist()) if n_compras else "ninguna"
                    msg = (f"📈 *Alerta Trading* {datetime.now().strftime('%d/%m %H:%M')}\n"
                           f"🟢 Compras: {n_compras} (Top: {top3})\n🔴 Ventas: {n_ventas}\nUmbral score: {umbral_score}")
                    enviar_whatsapp(msg)

    # Backtesting con optimización de parámetros (opcional)
    if backtesting_check:
        with st.spinner("Optimizando parámetros con backtesting..."):
            # Tomar datos históricos del S&P 500 (o de un índice representativo) para optimizar
            sp_hist = yf.Ticker("^GSPC").history(period="2y")
            if not sp_hist.empty:
                sp_hist = calcular_indicadores(sp_hist)
                opt = backtest_optimizar_parametros(sp_hist)
                st.session_state['param_opt'] = opt
                st.info(f"Optimización backtest: mejor umbral score = {opt['best_score_thresh']}, multiplicador ATR = {opt['best_atr_mult']}, win rate = {opt['best_win_rate']}%")

    st.success(f"✅ Análisis completado. {len(compras)} oportunidades de compra.")
    st.rerun()

# ============================================================
# PRESENTACIÓN DE RESULTADOS (después del análisis)
# ============================================================
if 'df' in st.session_state:
    df = st.session_state['df']
    compras = st.session_state['compras']
    ventas = st.session_state['ventas']
    observar = st.session_state['observar']
    usd_mxn = st.session_state['usd_mxn']
    eur_mxn = st.session_state['eur_mxn']
    regime_data = st.session_state['regime']

    st.markdown(f"**Última actualización:** {st.session_state.get('ultima_actualizacion', 'Nunca')}")

    icono_regime = {'ALCISTA':'🟢','LATERAL':'🟡','BAJISTA':'🔴','DESCONOCIDO':'⚪'}.get(regime_data.get('regime','DESCONOCIDO'),'⚪')
    with st.expander(f"{icono_regime} Market Regime: **{regime_data.get('regime','DESCONOCIDO')}** — {regime_data.get('descripcion','')}", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("S&P 500", f"{regime_data.get('precio',0):,.0f}")
        c2.metric("EMA 200", f"{regime_data.get('ema200',0):,.0f}")
        c3.metric("RSI S&P", f"{regime_data.get('rsi_sp500',0)}")
        c4.metric("Ret. 1 mes", f"{regime_data.get('ret_1m',0):+.1f}%")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Compras", len(compras))
    col2.metric("🔴 Ventas", len(ventas))
    col3.metric("👀 Observar", len(observar))
    col4.metric("🚫 Evitar", len(df[df['Recomendación'] == 'EVITAR']))

    # Dashboard de rendimiento
    st.subheader("📊 Dashboard de rendimiento de señales")
    df_hist = cargar_historial_senales()
    dashboard_rendimiento(df_hist)

    # Tabs (ahora 6)
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🟢 COMPRAS", "🔴 VENTAS", "🟡 OBSERVAR", "🔍 TODAS", "📜 HISTORIAL", "📊 VENTAS HISTÓRICAS"])

    cols_base = ['Símbolo','Precio (MXN)','Score','RSI','ATR','Stop Loss','Take Profit','Unidades','Inversión (MXN)','% Capital','Dist EMA50','Recomendación','Motivo','Señales']

    with tab1:
        if not compras.empty:
            available_base = [col for col in cols_base if col in compras.columns]
            extra_cols = [col for col in compras.columns if col not in cols_base]
            st.dataframe(compras[available_base + extra_cols], use_container_width=True)
        else:
            st.info("Sin oportunidades de compra en este momento.")

    with tab2:
        if not ventas.empty:
            available_base = [col for col in cols_base if col in ventas.columns]
            st.dataframe(ventas[available_base], use_container_width=True)
        else:
            st.info("Ninguna señal de venta para tus compras registradas.")

    with tab3:
        if not observar.empty:
            available_base = [col for col in cols_base if col in observar.columns]
            st.dataframe(observar[available_base], use_container_width=True)
        else:
            st.info("No hay acciones en observación.")

    with tab4:
        st.dataframe(df, use_container_width=True)

    with tab5:
        df_trans = cargar_transacciones()
        if not df_trans.empty:
            st.dataframe(df_trans.sort_values('fecha', ascending=False), use_container_width=True)
            csv = df_trans.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar historial (CSV)",
                data=csv,
                file_name=f"transacciones_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("Aún no hay transacciones registradas.")

    with tab6:
        st.subheader("📊 Historial de ventas mensual")
        df_trans = cargar_transacciones()
        if not df_trans.empty:
            ventas_df = df_trans[df_trans['tipo'] == 'venta'].copy()
            if not ventas_df.empty:
                ventas_df['mes'] = ventas_df['fecha'].dt.to_period('M')
                resumen_mensual = ventas_df.groupby('mes').agg(
                    ventas=('tipo', 'count'),
                    ganancia_promedio=('ganancia_pct', 'mean'),
                    ganancia_total=('ganancia_pct', lambda x: x.sum()),
                    aciertos=('ganancia_pct', lambda x: (x > 0).sum())
                ).reset_index()
                resumen_mensual['win_rate'] = (resumen_mensual['aciertos'] / resumen_mensual['ventas'] * 100).round(1)
                st.dataframe(resumen_mensual, use_container_width=True)

                st.subheader("Detalle de ventas")
                st.dataframe(ventas_df[['fecha','simbolo','cantidad','precio','ganancia_pct']].sort_values('fecha', ascending=False), use_container_width=True)

                win_rate_total = (ventas_df['ganancia_pct'] > 0).mean() * 100
                st.metric("Win rate global", f"{win_rate_total:.1f}%")
            else:
                st.info("Aún no hay ventas registradas.")
        else:
            st.info("No hay transacciones aún.")

    # Descarga de Excel
    st.divider()
    try:
        import openpyxl
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            compras.to_excel(writer, index=False, sheet_name='Compras')
            ventas.to_excel(writer, index=False, sheet_name='Ventas')
            observar.to_excel(writer, index=False, sheet_name='Observar')
            df.to_excel(writer, index=False, sheet_name='Todos')
        excel_bytes = output.getvalue()
        st.download_button(
            label="📥 Descargar informe Excel",
            data=excel_bytes,
            file_name=f"trading_v3_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        if drive_upload:
            guardar_en_drive(excel_bytes, f"trading_v3_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    except ImportError:
        st.warning("⚠️ openpyxl no instalado. Instálalo para habilitar la descarga Excel.")

    if 'analisis_ia' in st.session_state and st.session_state['analisis_ia']:
        with st.expander("🤖 Análisis de IA", expanded=True):
            st.markdown(st.session_state['analisis_ia'])

    # Selector de gráfico
    if not df.empty:
        st.subheader("🔎 Explorar cualquier acción analizada")
        todos_simbolos = df['Símbolo'].tolist()
        sim_elegido = st.selectbox("Selecciona un símbolo para ver su gráfico completo", todos_simbolos, key="selector_grafico")
        if sim_elegido:
            fila = df[df['Símbolo'] == sim_elegido].iloc[0]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Precio (MXN)", fila['Precio (MXN)'])
            c2.metric("Score", fila['Score'])
            c3.metric("RSI", fila['RSI'])
            c4.metric("Recomendación", fila['Recomendación'])
            if st.session_state.get('PRECIO_COMPRA', {}).get(sim_elegido):
                precio_compra = st.session_state['PRECIO_COMPRA'][sim_elegido]
                precio_actual = float(str(fila['Precio (MXN)']).replace(',',''))
                ganancia_pct = (precio_actual / precio_compra - 1) * 100
                st.metric(f"Tu compra en {precio_compra:.2f} MXN", f"{precio_actual:.2f} MXN", delta=f"{ganancia_pct:+.2f}%", delta_color="normal" if ganancia_pct >= 0 else "inverse")
            fig = grafico_enriquecido(sim_elegido, usd_mxn, eur_mxn)
            st.plotly_chart(fig, use_container_width=True)

st.caption("v3.0 — Con ML, sentimiento, optimización cartera, backtest paramétrico, Google Drive • Adrian López")
