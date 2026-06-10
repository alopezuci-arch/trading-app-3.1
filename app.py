# ============================================================
# SISTEMA DE TRADING PROFESIONAL v3.0 — STREAMLIT (FINAL)
# CORREGIDO: muestra resultados, sin filtros excesivos
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
import time
import os
import hashlib
import json
import pickle
import warnings
import logging
import certifi
warnings.filterwarnings('ignore')

import yfinance as yf
from curl_cffi import requests as curl_requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
SSL_VERIFY_PATH = certifi.where()

# Parche para yfinance: reemplazar la sesión de requests por curl_requests
import yfinance as yf
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)
SSL_VERIFY_PATH = certifi.where()

# --- Sesión con impersonación de navegador para evitar bloqueos de Yahoo en Streamlit Cloud ---
try:
    from curl_cffi import requests as curl_requests
    _YF_SESSION = curl_requests.Session(impersonate="chrome")
    try:
        _YF_SESSION.verify = True
    except Exception:
        pass
except Exception:
    _YF_SESSION = None

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from textblob import TextBlob

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import googleapiclient.http

st.set_page_config(page_title="Trading System v3.0", layout="wide", page_icon="📈")
st.title("📈 Sistema de Trading Personal v3.0 (Mejorado)")

# ============================================================
# CONSTANTES
# ============================================================
EMAIL_DESTINO = "alopez.uci@gmail.com"

def get_secret(nombre, default=""):
    try:
        return st.secrets.get(nombre, default)
    except Exception:
        return os.environ.get(nombre, default)

GEMINI_API_KEY    = get_secret("GEMINI_API_KEY")
GROQ_API_KEY      = get_secret("GROQ_API_KEY")
ANTHROPIC_API_KEY = get_secret("ANTHROPIC_API_KEY")
WHATSAPP_NUMERO   = get_secret("WHATSAPP_NUMERO")
WHATSAPP_APIKEY   = get_secret("WHATSAPP_APIKEY")
EMAIL_REMITENTE   = get_secret("EMAIL_REMITENTE")
EMAIL_PASSWORD    = get_secret("EMAIL_PASSWORD")
NEWSAPI_KEY       = get_secret("NEWSAPI_KEY")
GHU_GIST_TOKEN    = get_secret("GHU_GIST_TOKEN")
REPO_OWNER     = "alopezuci-arch"
REPO_NAME      = "trading-app-3.1"
DATA_PATH      = "data"

# Archivos de persistencia
TRANSACCIONES_FILE = "transacciones.csv"
HISTORIAL_FILE     = "historial_senales.csv"

# Parámetros de fiabilidad ML (Fase 2)
ML_WINDOW_MONTHS = 24          # Ventana deslizante de entrenamiento (evita regímenes demasiado antiguos)
ML_TEST_MONTHS = 6             # Últimos meses reservados estrictamente para prueba out-of-sample
WF_TRAIN_MONTHS = 24           # Ventana de entrenamiento en walk-forward
WF_PREDICT_MONTHS = 1          # Horizonte de predicción por iteración en walk-forward
WF_MIN_OBS_TEST = 8            # Mínimo de observaciones para aceptar cada bloque de prueba
FEATURE_IMPORTANCE_ZERO_TH = 0.01

MEXICAN_SYMBOLS_BASE = {
    'WALMEX', 'GMEXICOB', 'CEMEXCPO', 'FEMSAUBD', 'AMXL', 'KOFUBL', 'GFNORTEO',
    'BBAJIOO', 'ALFA', 'ALPEKA', 'ASURB', 'GAPB', 'OMAB', 'AC', 'GCC', 'LALA',
    'MEGA', 'PINFRA', 'TLEVISACPO', 'VESTA', 'GRUMA', 'HERDEZ', 'CUERVO', 'ORBIA',
    'VOLARA', 'Q', 'LABB', 'NEMAKA', 'FMTY14', 'FUNO11', 'FIBRAPL14', 'TERRA13',
    'DANHOS13', 'FIBRAHD15', 'FIBRAMQ12'
}


def normalizar_simbolo(simbolo: str) -> str:
    """Normaliza símbolos bursátiles y corrige alias frecuentes.

    Evita errores por espacios invisibles, símbolos BMV sin sufijo y
    tickers capturados manualmente con variantes incorrectas.
    """
    if simbolo is None:
        return ""

    # Elimina espacios normales y espacios Unicode como NBSP.
    s = str(simbolo).upper()
    s = "".join(ch for ch in s if not ch.isspace())

    if not s or s in {"NAN", "NONE"}:
        return ""

    alias = {
        "SMSN": "SMSN.L",
        "SMSNN": "SMSN.L",
        "SAMSUNG": "SMSN.L",
    }
    if s in alias:
        return alias[s]

    # Instrumentos especiales e instrumentos con sufijo explícito.
    if s.startswith("^") or "=" in s or "/" in s:
        return s
    if s.endswith(".MX"):
        return s
    if "." in s and not s.endswith("."):
        return s

    return f"{s}.MX" if s in MEXICAN_SYMBOLS_BASE else s

def _crear_ticker(simbolo: str):
    simbolo_norm = normalizar_simbolo(simbolo)
    return yf.Ticker(simbolo_norm, session=_YF_SESSION) if _YF_SESSION else yf.Ticker(simbolo_norm)


def _normalizar_diccionario_posiciones(posiciones: dict) -> dict:
    posiciones_norm = {}
    for k, v in (posiciones or {}).items():
        simbolo = normalizar_simbolo(k)
        if not simbolo:
            continue
        if isinstance(v, dict):
            posiciones_norm[simbolo] = {
                "cantidad": float(v.get("cantidad", 1.0)),
                "precio": float(v.get("precio", 0.0))
            }
        else:
            posiciones_norm[simbolo] = {"cantidad": 1.0, "precio": float(v)}
    return posiciones_norm

# ============================================================
# PERSISTENCIA (mismo código que tenías, sin cambios esenciales)
# ============================================================
def _gh_headers() -> dict:
    return {"Authorization": f"token {GHU_GIST_TOKEN}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
def _repo_disponible() -> bool:
    return bool(GHU_GIST_TOKEN)
def _repo_leer(nombre: str) -> str:
    if not _repo_disponible():
        return ""
    try:
        import base64
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{DATA_PATH}/{nombre}"
        r = requests.get(url, headers=_gh_headers(), timeout=12, verify=SSL_VERIFY_PATH)
        if r.status_code == 200:
            return base64.b64decode(r.json()["content"]).decode("utf-8")
        if r.status_code == 404:
            return ""
        st.warning(f"No se pudo leer '{nombre}' desde GitHub (HTTP {r.status_code}).")
    except Exception as e:
        st.warning(f"Error de conexión al leer '{nombre}' desde GitHub: {e}")
        logger.exception("Error leyendo archivo del repo: %s", nombre)
    return ""

def _repo_escribir(nombre: str, contenido: str, mensaje: str = "update") -> bool:
    if not _repo_disponible() or contenido is None:
        return False
    import base64
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{DATA_PATH}/{nombre}"
        r_get = requests.get(url, headers=_gh_headers(), timeout=10, verify=SSL_VERIFY_PATH)
        sha = r_get.json().get("sha", "") if r_get.status_code == 200 else ""
        payload = {
            "message": f"[trading-app] {mensaje}",
            "content": base64.b64encode(contenido.encode("utf-8")).decode("ascii")
        }
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=_gh_headers(), json=payload, timeout=15, verify=SSL_VERIFY_PATH)
        if r.status_code not in (200, 201):
            st.warning(f"No se pudo guardar '{nombre}' en GitHub (HTTP {r.status_code}).")
            return False
        return True
    except Exception as e:
        st.error(f"Error al guardar '{nombre}' en GitHub: {e}")
        logger.exception("Error escribiendo archivo del repo: %s", nombre)
        return False


def repo_cargar_posiciones() -> dict:
    contenido = _repo_leer("posiciones.json")
    if not contenido:
        return {}

    try:
        data = json.loads(contenido)
        if not isinstance(data, dict):
            st.warning("El archivo de posiciones tiene un formato inválido. Se usará cartera vacía.")
            return {}
        return _normalizar_diccionario_posiciones(data)
    except Exception as e:
        st.error(f"Error al leer posiciones: {e}")
        logger.exception("Error parseando posiciones.json")
        return {}


def repo_guardar_posiciones(posiciones: dict) -> bool:
    """Guarda posiciones normalizadas, incluso cuando la cartera está vacía."""
    try:
        posiciones_norm = _normalizar_diccionario_posiciones(posiciones)
        contenido = json.dumps(posiciones_norm, indent=2, ensure_ascii=False)
        return _repo_escribir("posiciones.json", contenido, "actualizar posiciones")
    except Exception as e:
        st.error(f"Error al guardar posiciones: {e}")
        logger.exception("Error guardando posiciones")
        return False
def repo_cargar_transacciones() -> pd.DataFrame:
    cols = ['fecha','simbolo','cantidad','precio','tipo','total','notas','ganancia_pct']
    contenido = _repo_leer("transacciones.csv")
    if contenido and contenido.strip():
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(contenido))
            df.columns = [c.strip() for c in df.columns]
            if 'ganancia_pct' not in df.columns:
                df['ganancia_pct'] = np.nan
            else:
                df['ganancia_pct'] = pd.to_numeric(df['ganancia_pct'], errors='coerce')
            df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
            if 'simbolo' in df.columns:
                df['simbolo'] = df['simbolo'].astype(str).apply(normalizar_simbolo)
            df.to_csv(TRANSACCIONES_FILE, index=False)
            return df
        except Exception as e:
            st.error(f"Error procesando transacciones desde GitHub: {e}")
            logger.exception("Error cargando transacciones desde repo")
    return pd.DataFrame(columns=cols)
def reconstruir_posiciones_desde_transacciones() -> dict:
    df = repo_cargar_transacciones()

    if df is None or df.empty:
        return {}

    df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
    df['simbolo'] = df['simbolo'].astype(str).apply(normalizar_simbolo)
    df['tipo'] = df['tipo'].astype(str).str.lower().str.strip()
    df['cantidad'] = pd.to_numeric(df['cantidad'], errors='coerce').fillna(0)
    df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0)

    df = df.dropna(subset=['fecha'])
    df = df[df['tipo'].isin(['compra', 'venta'])]
    df = df.sort_values('fecha')

    posiciones = {}

    for _, row in df.iterrows():
        simbolo = row['simbolo']
        tipo = row['tipo']
        cantidad = float(row['cantidad'])
        precio = float(row['precio'])

        if not simbolo or cantidad <= 0:
            continue

        if tipo == 'compra':
            if simbolo not in posiciones:
                posiciones[simbolo] = {
                    'cantidad': 0.0,
                    'precio': 0.0,
                    'costo_total': 0.0
                }

            posiciones[simbolo]['costo_total'] += cantidad * precio
            posiciones[simbolo]['cantidad'] += cantidad
            posiciones[simbolo]['precio'] = (
                posiciones[simbolo]['costo_total'] / posiciones[simbolo]['cantidad']
            )

        elif tipo == 'venta':
            if simbolo not in posiciones:
                continue

            cant_actual = posiciones[simbolo]['cantidad']
            precio_promedio = posiciones[simbolo]['precio']

            nueva_cantidad = cant_actual - cantidad

            if nueva_cantidad <= 0:
                del posiciones[simbolo]
            else:
                posiciones[simbolo]['cantidad'] = nueva_cantidad
                posiciones[simbolo]['costo_total'] = nueva_cantidad * precio_promedio
                posiciones[simbolo]['precio'] = precio_promedio

    posiciones_limpias = {}

    for simbolo, datos in posiciones.items():
        if datos['cantidad'] > 0:
            posiciones_limpias[simbolo] = {
                'cantidad': round(datos['cantidad'], 6),
                'precio': round(datos['precio'], 2)
            }

    return posiciones_limpias

def repo_guardar_transacciones() -> bool:
    if not os.path.exists(TRANSACCIONES_FILE):
        return False
    try:
        df = pd.read_csv(TRANSACCIONES_FILE)
        if 'simbolo' in df.columns:
            df['simbolo'] = df['simbolo'].astype(str).apply(normalizar_simbolo)
        contenido = df.to_csv(index=False)
        if not contenido.strip():
            return False
        return _repo_escribir("transacciones.csv", contenido, "sincronizar transacciones")
    except Exception as e:
        st.error(f"Error al sincronizar transacciones: {e}")
        logger.exception("Error guardando transacciones")
        return False
        
def repo_cargar_historial() -> pd.DataFrame:
    cols = ['fecha','simbolo','score','precio','recomendacion','señales']
    contenido = _repo_leer("historial_senales.csv")
    if contenido and len(contenido) > 60:
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(contenido))
            df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
            if 'simbolo' in df.columns:
                df['simbolo'] = df['simbolo'].astype(str).apply(normalizar_simbolo)
            df.to_csv("historial_senales.csv", index=False)
            return df
        except Exception as e:
            st.error(f"Error al cargar historial desde GitHub: {e}")
            logger.exception("Error cargando historial")
    return pd.DataFrame(columns=cols)

def repo_guardar_historial() -> bool:
    ruta = "historial_senales.csv"
    if not os.path.exists(ruta):
        return False
    try:
        df = pd.read_csv(ruta)
        if 'simbolo' in df.columns:
            df['simbolo'] = df['simbolo'].astype(str).apply(normalizar_simbolo)
        contenido = df.to_csv(index=False)
        return _repo_escribir("historial_senales.csv", contenido, "sincronizar historial señales")
    except Exception as e:
        st.error(f"Error al sincronizar historial: {e}")
        logger.exception("Error guardando historial")
        return False

def _data_file_path(nombre: str) -> str:
    os.makedirs(DATA_PATH, exist_ok=True)
    return os.path.join(DATA_PATH, nombre)


def _leer_data_local(nombre: str, default: str = "") -> str:
    ruta = _data_file_path(nombre)
    if not os.path.exists(ruta):
        return default
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        logger.exception("No se pudo leer archivo local %s", ruta)
        return default


def _escribir_data_local(nombre: str, contenido: str) -> bool:
    ruta = _data_file_path(nombre)
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        return True
    except Exception:
        logger.exception("No se pudo escribir archivo local %s", ruta)
        return False


def _parse_fecha_meta(fecha_str: str):
    if not fecha_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(fecha_str, fmt)
        except Exception:
            continue
    return None


@st.cache_resource
def _ml_cache_global() -> dict:
    return {}


def repo_guardar_modelo_ml(simbolo: str, clf, meta_entry: dict):
    try:
        import base64
        simbolo = normalizar_simbolo(simbolo)
        model_b64 = base64.b64encode(pickle.dumps(clf)).decode("ascii")

        meta_txt = _repo_leer("ml_meta.json") or _leer_data_local("ml_meta.json", "{}")
        meta = json.loads(meta_txt or "{}")
        meta[simbolo] = meta_entry

        meta_str = json.dumps(meta, indent=2, ensure_ascii=False)
        _escribir_data_local("ml_meta.json", meta_str)

        nombre = f"ml_{simbolo.replace('.','_')}.b64"
        _escribir_data_local(nombre, model_b64)

        if _repo_disponible():
            _repo_escribir("ml_meta.json", meta_str, "ml meta")
            _repo_escribir(nombre, model_b64, f"modelo ML {simbolo}")
    except Exception:
        logger.exception("No se pudo guardar el modelo ML de %s", simbolo)


def repo_cargar_modelo_ml(simbolo: str):
    simbolo = normalizar_simbolo(simbolo)
    try:
        meta_txt = _repo_leer("ml_meta.json") or _leer_data_local("ml_meta.json", "{}")
        meta = json.loads(meta_txt or "{}")
        if simbolo not in meta:
            return None, None

        fecha = _parse_fecha_meta(meta[simbolo].get("fecha", ""))
        if fecha and (datetime.now() - fecha).total_seconds() > 604800:
            return None, meta.get(simbolo)

        import base64
        nombre = f"ml_{simbolo.replace('.','_')}.b64"
        b64 = _repo_leer(nombre) or _leer_data_local(nombre, "")
        if b64:
            clf = pickle.loads(base64.b64decode(b64.encode("ascii")))
            return clf, meta.get(simbolo)
    except Exception:
        logger.exception("No se pudo cargar el modelo ML de %s", simbolo)
    return None, None

def generar_backup_zip() -> bytes:
    """Genera un ZIP con posiciones completas, no solo precios.

    Antes guardaba st.session_state['PRECIO_COMPRA'], lo cual destruye
    cantidades porque ese diccionario solo contiene precios.
    """
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        posiciones = repo_cargar_posiciones() or st.session_state.get('POSICIONES', {})
        zf.writestr("posiciones.json", json.dumps(posiciones, indent=2, ensure_ascii=False))

        if os.path.exists(TRANSACCIONES_FILE):
            zf.write(TRANSACCIONES_FILE, "transacciones.csv")
        if os.path.exists("historial_senales.csv"):
            zf.write("historial_senales.csv", "historial_senales.csv")

        zf.writestr("LEEME.txt", f"Backup Trading App — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    buf.seek(0)
    return buf.read()

def restaurar_desde_zip(uploaded_file) -> dict:
    import zipfile
    posiciones = {}
    try:
        with zipfile.ZipFile(io.BytesIO(uploaded_file.read())) as zf:
            if "posiciones.json" in zf.namelist():
                posiciones_raw = json.loads(zf.read("posiciones.json").decode())
                posiciones = _normalizar_diccionario_posiciones(posiciones_raw)
            if "transacciones.csv" in zf.namelist():
                with open(TRANSACCIONES_FILE, 'wb') as f:
                    f.write(zf.read("transacciones.csv"))
            if "historial_senales.csv" in zf.namelist():
                with open("historial_senales.csv", 'wb') as f:
                    f.write(zf.read("historial_senales.csv"))
    except Exception as e:
        st.error(f"Error leyendo backup: {e}")
    return posiciones

# ============================================================
# HISTORIAL Y TRANSACCIONES
# ============================================================
def cargar_transacciones() -> pd.DataFrame:
    if os.path.exists(TRANSACCIONES_FILE):
        try:
            df = pd.read_csv(TRANSACCIONES_FILE)
            df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
            if 'simbolo' in df.columns:
                df['simbolo'] = df['simbolo'].astype(str).apply(normalizar_simbolo)
            if 'ganancia_pct' not in df.columns:
                df['ganancia_pct'] = np.nan
            return df
        except Exception as e:
            st.error(f"Error al leer transacciones locales: {e}")
            logger.exception("Error leyendo transacciones.csv")
    return pd.DataFrame(columns=['fecha','simbolo','cantidad','precio','tipo','total','notas','ganancia_pct'])

def guardar_transaccion(simbolo: str, cantidad: float, precio: float, tipo: str, notas: str = "", ganancia_pct: float = None):
    """Guarda una transacción con validación anti-duplicados.

    Evita que Streamlit registre la misma compra/venta varias veces por rerun
    o doble clic. Considera duplicado si símbolo, cantidad, precio y tipo
    coinciden dentro de una ventana de 90 segundos.
    """
    try:
        simbolo_norm = normalizar_simbolo(simbolo)
        tipo_norm = str(tipo).lower().strip()
        cantidad = float(cantidad)
        precio = float(precio)

        if not simbolo_norm:
            st.error("No se pudo guardar la transacción: símbolo inválido.")
            return False
        if tipo_norm not in {"compra", "venta"}:
            st.error("No se pudo guardar la transacción: tipo inválido.")
            return False
        if cantidad <= 0 or precio <= 0:
            st.error("No se pudo guardar la transacción: cantidad/precio deben ser mayores a cero.")
            return False

        df = cargar_transacciones()
        ahora = datetime.now()

        if df is not None and not df.empty:
            df_check = df.copy()
            df_check['fecha'] = pd.to_datetime(df_check['fecha'], errors='coerce')
            df_check['simbolo'] = df_check['simbolo'].astype(str).apply(normalizar_simbolo)
            df_check['tipo'] = df_check['tipo'].astype(str).str.lower().str.strip()
            df_check['cantidad'] = pd.to_numeric(df_check['cantidad'], errors='coerce')
            df_check['precio'] = pd.to_numeric(df_check['precio'], errors='coerce')

            ventana = ahora - timedelta(seconds=90)
            duplicado = df_check[
                (df_check['fecha'] >= ventana) &
                (df_check['simbolo'] == simbolo_norm) &
                (df_check['tipo'] == tipo_norm) &
                (df_check['cantidad'].round(6) == round(cantidad, 6)) &
                (df_check['precio'].round(4) == round(precio, 4))
            ]
            if not duplicado.empty:
                st.warning(f"Transacción duplicada ignorada: {simbolo_norm} {cantidad} @ {precio}")
                return False

        nueva = pd.DataFrame([{
            'fecha': ahora.strftime("%Y-%m-%d %H:%M:%S"),
            'simbolo': simbolo_norm,
            'cantidad': cantidad,
            'precio': precio,
            'tipo': tipo_norm,
            'total': round(cantidad * precio, 2),
            'notas': notas,
            'ganancia_pct': ganancia_pct if ganancia_pct is not None else np.nan
        }])
        df = pd.concat([df, nueva], ignore_index=True)
        df.to_csv(TRANSACCIONES_FILE, index=False)
        return True
    except Exception as e:
        st.error(f"Error al guardar transacción: {e}")
        logger.exception("Error guardando transacción")
        return False

def procesar_ventas(input_text: str):
    if not input_text or not input_text.strip():
        st.sidebar.warning("No se ingresaron ventas.")
        return

    posiciones = repo_cargar_posiciones()
    ventas_registradas = 0

    for linea in input_text.strip().split('\n'):
        partes = linea.split(',')
        if len(partes) != 3:
            st.sidebar.warning(f"Formato inválido en venta: '{linea}'. Usa SIMBOLO,CANTIDAD,PRECIO")
            continue

        simbolo = normalizar_simbolo(partes[0])
        if not simbolo:
            st.sidebar.warning(f"Símbolo inválido en venta: '{partes[0]}'.")
            continue

        try:
            cant_vender = float(partes[1].strip())
            precio_venta = float(partes[2].strip())
        except Exception:
            st.sidebar.warning(f"Cantidad/precio inválidos en venta: '{linea}'.")
            continue

        if simbolo in posiciones:
            pos = posiciones[simbolo]
            precio_compra_promedio = pos['precio']
            ganancia_pct = ((precio_venta / precio_compra_promedio) - 1) * 100
            if not guardar_transaccion(simbolo, cant_vender, precio_venta, "venta",
                               notas="Venta manual (PPP)", ganancia_pct=ganancia_pct):
                continue
            nueva_cant = pos['cantidad'] - cant_vender
            if nueva_cant <= 0:
                del posiciones[simbolo]
            else:
                posiciones[simbolo]['cantidad'] = nueva_cant
            ventas_registradas += 1

    if ventas_registradas:
        repo_guardar_posiciones(posiciones)
        repo_guardar_transacciones()
        st.session_state['PRECIO_COMPRA'] = {k: v['precio'] for k, v in posiciones.items()}
        st.sidebar.success(f"✅ {ventas_registradas} ventas procesadas.")
        st.toast(f"✅ {ventas_registradas} ventas registradas", icon="💰")
        time.sleep(1)
        st.rerun()

def procesar_compras_ppp(input_text: str):
    posiciones = repo_cargar_posiciones()
    compras_ok = 0
    for linea in input_text.strip().split('\n'):
        partes = linea.split(',')
        if len(partes) != 3:
            st.sidebar.warning(f"Formato inválido en compra: '{linea}'. Usa SIMBOLO,CANTIDAD,PRECIO")
            continue

        simbolo = normalizar_simbolo(partes[0])
        if not simbolo:
            st.sidebar.warning(f"Símbolo inválido en compra: '{partes[0]}'.")
            continue

        try:
            cant_nueva = float(partes[1].strip())
            precio_nuevo = float(partes[2].strip())
        except Exception:
            st.sidebar.warning(f"Cantidad/precio inválidos en compra: '{linea}'.")
            continue

        if simbolo in posiciones:
            cant_actual = posiciones[simbolo]['cantidad']
            prec_actual = posiciones[simbolo]['precio']
            nueva_cantidad_total = cant_actual + cant_nueva
            nuevo_ppp = ((cant_actual * prec_actual) + (cant_nueva * precio_nuevo)) / nueva_cantidad_total
            posiciones[simbolo] = {'cantidad': nueva_cantidad_total, 'precio': nuevo_ppp}
        else:
            posiciones[simbolo] = {'cantidad': cant_nueva, 'precio': precio_nuevo}
        if guardar_transaccion(simbolo, cant_nueva, precio_nuevo, "compra", notas="Compra manual (PPP)"):
            compras_ok += 1

    if compras_ok:
        repo_guardar_posiciones(posiciones)
        repo_guardar_transacciones()
        st.session_state['PRECIO_COMPRA'] = {k: v['precio'] for k, v in posiciones.items()}
        st.sidebar.success(f"✅ {compras_ok} compras promediadas.")
        st.rerun()

def cargar_historial_senales() -> pd.DataFrame:
    if os.path.exists(HISTORIAL_FILE):
        try:
            df = pd.read_csv(HISTORIAL_FILE, on_bad_lines='skip')
            if 'fecha' in df.columns:
                df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
                df = df.dropna(subset=['fecha'])
            else:
                df['fecha'] = pd.NaT
            if 'simbolo' in df.columns:
                df['simbolo'] = df['simbolo'].astype(str).apply(normalizar_simbolo)
            if 'ganancia_pct' not in df.columns:
                df['ganancia_pct'] = np.nan
            else:
                df['ganancia_pct'] = pd.to_numeric(df['ganancia_pct'], errors='coerce')
            columnas_necesarias = ['simbolo', 'score', 'precio', 'recomendacion', 'señales']
            for col in columnas_necesarias:
                if col not in df.columns:
                    df[col] = ''
            return df
        except Exception as e:
            st.error(f"Error al cargar historial: {e}")
            logger.exception("Error leyendo historial de señales")
    return pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])

def guardar_senal_en_historial(senal: dict, fecha: str):
    import re
    try:
        if os.path.exists(HISTORIAL_FILE):
            try:
                df = pd.read_csv(HISTORIAL_FILE, on_bad_lines='skip')
                if 'fecha' in df.columns:
                    df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
                    df = df.dropna(subset=['fecha'])
                else:
                    df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])
            except Exception:
                df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])
        else:
            df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])

        ganancia = None
        if senal['Recomendación'] == "VENDER" and 'Motivo' in senal:
            motivo = senal['Motivo']
            match = re.search(r'([+-]?\d+(?:\.\d+)?)%', motivo)
            if match:
                ganancia = float(match.group(1))
            else:
                st.warning(f"No se pudo extraer ganancia de: {motivo}")

        nueva = pd.DataFrame([{
            'fecha': pd.to_datetime(fecha, errors='coerce'),
            'simbolo': normalizar_simbolo(senal['Símbolo']),
            'score': senal['Score'],
            'precio': senal['Precio MXN'],
            'recomendacion': senal['Recomendación'],
            'señales': senal.get('Señales', ''),
            'ganancia_pct': ganancia
        }])

        df = pd.concat([df, nueva], ignore_index=True)
        cutoff = datetime.now() - timedelta(days=90)
        df = df[df['fecha'] >= cutoff]
        df.to_csv(HISTORIAL_FILE, index=False)
    except Exception as e:
        st.error(f"Error al guardar señal en historial: {e}")
        logger.exception("Error guardando señal en historial")

def dashboard_rendimiento_real():
    st.subheader("📊 Rendimiento Real de mi Cartera")
    df_trans = cargar_transacciones() 
    if df_trans is not None and not df_trans.empty:
        df_trans['tipo'] = df_trans['tipo'].astype(str).str.strip().str.lower()
        ventas = df_trans[df_trans['tipo'] == 'venta'].copy()
        ventas['ganancia_pct'] = pd.to_numeric(ventas['ganancia_pct'], errors='coerce')
        ventas = ventas.dropna(subset=['ganancia_pct'])
        if not ventas.empty:
            ventas['ganancia_mxn'] = ventas['total'] * (ventas['ganancia_pct'] / 100) / (1 + ventas['ganancia_pct'] / 100)
            ventas['ganancia_mxn'] = ventas['ganancia_mxn'].round(2)
            aciertos = ventas[ventas['ganancia_pct'] > 0]
            win_rate = (len(aciertos) / len(ventas)) * 100
            ganancia_total_mxn = ventas['ganancia_mxn'].sum()
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Win Rate Real", f"{win_rate:.1f}%")
            col2.metric("Ventas", len(ventas))
            col3.metric("Ganancia Promedio %", f"{ventas['ganancia_pct'].mean():.2f}%")
            col4.metric("💰 Ganancia Total (MXN)", f"${ganancia_total_mxn:,.2f}")
            fig = px.bar(ventas, x='fecha', y='ganancia_pct', color='ganancia_pct',
                         hover_data=['simbolo', 'notas', 'ganancia_mxn'],
                         title="Historial Real de Trading",
                         labels={'ganancia_mxn': 'Ganancia (MXN)'},
                         color_continuous_scale=[(0, "red"), (0.5, "yellow"), (1, "green")])
            st.plotly_chart(fig, width='stretch', key="dash_real_definitivo")
        else:
            st.warning("Se leyó el archivo pero no se detectaron filas de 'venta' con porcentaje de ganancia.")
    else:
        st.error("No se pudieron cargar datos desde el repositorio. Revisa la conexión con GitHub.")
        
def analizar_adn_exito():
    st.subheader("🧬 ADN de tus Aciertos (Aprendizaje ML)")

    df_hist = cargar_historial_senales()

    if df_hist.empty or 'ganancia_pct' not in df_hist.columns:
        st.write("Sin datos históricos de señales para analizar.")
        return

    df_hist['ganancia_pct'] = pd.to_numeric(
        df_hist['ganancia_pct'],
        errors='coerce'
    )

    aciertos = df_hist[df_hist['ganancia_pct'] > 0].copy()

    if aciertos.empty:
        st.write(
            "El modelo está esperando más cierres de ventas para identificar patrones de éxito."
        )
        return

    if 'señales' not in aciertos.columns:
        st.write("No hay columna de señales para analizar.")
        return

    señales_limpias = (
        aciertos['señales']
        .fillna('')
        .astype(str)
        .tolist()
    )

    todas_senales = ",".join(señales_limpias).split(',')

    from collections import Counter

    conteo = Counter([
        s.strip()
        for s in todas_senales
        if s
        and s.strip()
        and s.strip().lower() not in ['nan', 'none']
    ])

    if not conteo:
        st.write(
            "No se detectaron señales técnicas suficientes en operaciones ganadoras."
        )
        return

    st.write(
        "Factores técnicos detectados en tus operaciones ganadoras:"
    )

    for factor, count in conteo.most_common(5):
        st.success(
            f"✔️ {factor}: Identificado en {count} aciertos"
        )

# ============================================================
# LISTAS DE MERCADO (asegúrate de que devuelvan 11 elementos)
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
        'TSM','ARM','MRVL','ON','SMH','VRT','CEG','GEV','OKLO','SMR','APP','MDB','TECL','CCJ','BWXT','EME','BOTZ',
        'URA'
        
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

# Ahora sí, asignamos las 11 variables con el orden correcto
(sp100, nasdaq100, ibex35, bmv, sp500,
 ia_stocks, commodity_etfs, mining_oil,
 etfs_sectoriales, mid_cap_growth, etfs_emergentes) = cargar_listas()

# Creación de mercado_opciones
universo_recomendado = list(set(sp100 + etfs_sectoriales + mid_cap_growth))
mercado_opciones = {
    "⚡ Prueba rápida (12 tickers)": ['AAPL','MSFT','NVDA','TSLA','QQQ','SPY','DDOG','NET','CRWD','XLK','XLF','SOXX'],
    "⭐ Recomendado (S&P100 + ETFs + Growth)": universo_recomendado,
    "📊 S&P 100": sp100,
    "📊 S&P 500 (completo)": sp500,
    "📊 NASDAQ 100": nasdaq100,
    "🏛️ ETFs sectoriales (30)": etfs_sectoriales,
    "🚀 Mid-cap growth (38)": mid_cap_growth,
    "🌎 ETFs mercados emergentes (16)": etfs_emergentes,
    "🤖 IA (Inteligencia Artificial)": ia_stocks,
    "🪙 Commodities (ETFs)": commodity_etfs,
    "⛏️ Mineras y Petroleras": mining_oil,
    "🇲🇽 BMV México": bmv,
    "🇪🇸 IBEX 35": ibex35,
    "🌐 Todo USA (S&P500 + ETFs + Growth)": list(set(sp500 + etfs_sectoriales + mid_cap_growth)),
    "🌍 Global completo": list(set(sp500 + nasdaq100 + ibex35 + bmv + ia_stocks + commodity_etfs + mining_oil + etfs_sectoriales + mid_cap_growth + etfs_emergentes)),
}
# ============================================================
# FUNCIONES AUXILIARES (TIPO CAMBIO, INDICADORES, ETC.)
# ============================================================
@st.cache_data(ttl=1800)
def obtener_tipo_cambio() -> tuple[float, float]:
    try:
        usd = _crear_ticker("USDMXN=X").history(period="5d")
        eur = _crear_ticker("EURMXN=X").history(period="5d")

        usd_mxn = None
        eur_mxn = None

        if usd is not None and not usd.empty:
            usd_mxn = float(usd["Close"].dropna().iloc[-1])

        if eur is not None and not eur.empty:
            eur_mxn = float(eur["Close"].dropna().iloc[-1])

        if usd_mxn and eur_mxn:
            return usd_mxn, eur_mxn

    except Exception as e:
        print(f"[tipo_cambio Yahoo] Error: {e}")

    # Fallback alternativo usando exchangerate.host
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=MXN",
            timeout=10,
            verify=SSL_VERIFY_PATH
        )
        data = r.json()
        usd_mxn = float(data["rates"]["MXN"])

        r2 = requests.get(
            "https://api.frankfurter.app/latest?from=EUR&to=MXN",
            timeout=10,
            verify=SSL_VERIFY_PATH
        )
        data2 = r2.json()
        eur_mxn = float(data2["rates"]["MXN"])

        return usd_mxn, eur_mxn

    except Exception as e:
        print(f"[tipo_cambio fallback] Error: {e}")

    # Último recurso, pero ya no debería usarse casi nunca
    return 18.50, 20.10

def safe_history(ticker, period="6mo", max_retries=3):
    simbolo = ticker.ticker if hasattr(ticker, "ticker") else ""

    for intento in range(max_retries):
        try:
            hist = ticker.history(period=period, auto_adjust=True)
            if hist is not None and not hist.empty and len(hist) >= 20:
                return hist
            time.sleep(1 + intento)
        except Exception as e:
            msg = str(e)
            if "Rate limit" in msg or "429" in msg or "Too Many Requests" in msg:
                time.sleep(2 ** intento)
            else:
                time.sleep(1)

    # Fallback Stooq para tickers USA
    try:
        simbolo_stooq = simbolo.replace(".MX", "").replace(".MC", "").lower() + ".us"
        url = f"https://stooq.com/q/d/l/?s={simbolo_stooq}&i=d"
        df = pd.read_csv(url)

        if df is not None and not df.empty:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")
            df = df.rename(columns={
                "Open": "Open",
                "High": "High",
                "Low": "Low",
                "Close": "Close",
                "Volume": "Volume"
            })

            if period == "6mo":
                df = df[df.index >= datetime.now() - timedelta(days=190)]
            elif period == "1y":
                df = df[df.index >= datetime.now() - timedelta(days=370)]
            elif period == "2y":
                df = df[df.index >= datetime.now() - timedelta(days=740)]
            elif period == "3y":
                df = df[df.index >= datetime.now() - timedelta(days=1110)]

            return df

    except Exception as e:
        print(f"[safe_history Stooq] {simbolo}: {e}")

    return pd.DataFrame()

def obtener_precio_actual(simbolo: str) -> float | None:
    simbolo_norm = normalizar_simbolo(simbolo)
    try:
        ticker = _crear_ticker(simbolo_norm)
        precio = ticker.info.get('regularMarketPrice') or ticker.info.get('currentPrice')
        if precio:
            return float(precio)
        hist = safe_history(ticker, period="2d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception as e:
        logger.warning("No se pudo obtener precio actual para %s: %s", simbolo_norm, e)
    return None

def convertir_precio_mxn(simbolo: str, precio_original: float, usd_mxn: float, eur_mxn: float) -> float:
    simbolo_norm = normalizar_simbolo(simbolo)
    if simbolo_norm.endswith('.MX'):
        return precio_original
    elif simbolo_norm.endswith('.MC'):
        return precio_original * eur_mxn
    else:
        return precio_original * usd_mxn

def calcular_indicadores(hist: pd.DataFrame) -> pd.DataFrame:
    # ... (tu código original, sin cambios)
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
    rango14 = (high14 - low14).replace(0, np.nan)
    hist['STOCH_K'] = 100 * (hist['Close'] - low14) / rango14
    hist['STOCH_D'] = hist['STOCH_K'].rolling(3).mean()
    hist['Vol_avg'] = hist['Volume'].rolling(20).mean()
    hist['ROC'] = (hist['Close'] / hist['Close'].shift(10) - 1) * 100
    hist['WILLR'] = -100 * (high14 - hist['Close']) / rango14
    hist['OBV'] = (np.sign(hist['Close'].diff()) * hist['Volume']).cumsum()
    hist['ATR_RATIO'] = hist['ATR'] / hist['Close']
    hist['DOW'] = hist.index.dayofweek
    if len(hist) > 100:
        weekly = hist['Close'].resample('W').last()
        hist['EMA20_weekly'] = weekly.ewm(span=20, adjust=False).mean().reindex(hist.index, method='ffill')
        hist['EMA50_weekly'] = weekly.ewm(span=50, adjust=False).mean().reindex(hist.index, method='ffill')
    return hist

def calcular_score(r: dict, p: dict | None) -> tuple[int, list[str]]:
    # ... (tu código original)
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
    # ... (tu código original)
    try:
        sp = _crear_ticker("^GSPC").history(period="1y")
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
                    'descripcion': 'S&P 500 sobre EMA50 y EMA200'}
        elif precio > ema200:
            return {'regime': 'LATERAL', 'score_bonus': -1, 'precio': precio, 'ema200': ema200,
                    'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1),
                    'descripcion': 'Ser selectivo'}
        else:
            return {'regime': 'BAJISTA', 'score_bonus': -3, 'precio': precio, 'ema200': ema200,
                    'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1),
                    'descripcion': 'Evitar nuevas compras'}
    except:
        return {'regime': 'DESCONOCIDO', 'score_bonus': 0, 'precio': 0, 'ema200': 0,
                'ret_1m': 0, 'rsi_sp500': 0, 'descripcion': 'Error al obtener datos'}

def position_size(precio: float, atr: float, capital: float, riesgo_pct: float) -> dict:
    riesgo_mxn = capital * (riesgo_pct / 100)
    stop_dist = 2 * atr
    if stop_dist <= 0:
        return {'unidades': 0, 'inversion_mxn': 0, 'pct_capital': 0}
    unidades = riesgo_mxn / stop_dist
    inversion = min(unidades * precio, capital * 0.20)
    pct_capital = (inversion / capital) * 100
    return {'unidades': round(unidades, 2), 'inversion_mxn': round(inversion, 2), 'pct_capital': round(pct_capital, 1)}

@st.cache_data(ttl=3600)
def obtener_regimen_diario() -> pd.Series:
    sp = _crear_ticker("^GSPC").history(period="3y")
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
    # ... (tu código original)
    try:
        info = _crear_ticker(simbolo).info
        dy = info.get('dividendYield')
        roe = info.get('returnOnEquity')
        rg = info.get('revenueGrowth')
        eg = info.get('earningsGrowth')
        pm = info.get('profitMargins')
        debt_to_equity = info.get('debtToEquity')
        free_cashflow = info.get('freeCashflow')
        roa = info.get('returnOnAssets')
        ebitda_margin = info.get('ebitdaMargins')
        return {
            'P/E (ttm)': info.get('trailingPE'),
            'P/E forward': info.get('forwardPE'),
            'P/B': info.get('priceToBook'),
            'Div Yield (%)': round(dy * 100, 2) if dy else None,
            'ROE (%)': round(roe * 100, 2) if roe else None,
            'Rev Growth (%)': round(rg * 100, 2) if rg else None,
            'EPS Growth (%)': round(eg * 100, 2) if eg else None,
            'Net Margin (%)': round(pm * 100, 2) if pm else None,
            'Debt/Equity': round(debt_to_equity, 2) if debt_to_equity else None,
            'Free Cash Flow': round(free_cashflow / 1e6, 2) if free_cashflow else None,
            'ROA (%)': round(roa * 100, 2) if roa else None,
            'EBITDA Margin (%)': round(ebitda_margin * 100, 2) if ebitda_margin else None,
        }
    except:
        return {}

def backtest_realista(simbolo: str, precio_entrada: float, atr: float, window_dias=30) -> dict:
    try:
        ticker = _crear_ticker(simbolo)
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
    # ... (tu código original)
    if hist_anual.empty or len(hist_anual) < 200:
        return {'best_score_thresh': 5, 'best_atr_mult': 2, 'best_win_rate': 0}
    best_win_rate = 0
    best_score_thresh = 5
    best_atr_mult = 2
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
                            señales.append(0)
                            break
                        if precio_salida >= tp:
                            señales.append(1)
                            break
                    else:
                        señales.append(0)
            if señales:
                win_rate = sum(señales)/len(señales)*100
                if win_rate > best_win_rate:
                    best_win_rate = win_rate
                    best_score_thresh = score_thresh
                    best_atr_mult = atr_mult
    return {'best_score_thresh': best_score_thresh, 'best_atr_mult': best_atr_mult, 'best_win_rate': round(best_win_rate,1)}

@st.cache_data(ttl=86400)
def get_backtest_optimization():
    try:
        sp_ticker = _crear_ticker("^GSPC")
        sp_hist = safe_history(sp_ticker, period="2y", max_retries=2)

        if sp_hist is None or sp_hist.empty or len(sp_hist) < 200:
            return {
                'best_score_thresh': 5,
                'best_atr_mult': 2,
                'best_win_rate': 0
            }

        sp_hist = calcular_indicadores(sp_hist)
        opt = backtest_optimizar_parametros(sp_hist)
        return opt

    except Exception as e:
        print(f"[get_backtest_optimization] Error: {e}")
        return {
            'best_score_thresh': 5,
            'best_atr_mult': 2,
            'best_win_rate': 0
        }

def simular_ignorar_senal(simbolo: str, precio_actual: float, condicion: str, usd_mxn: float, eur_mxn: float) -> dict:
    """
    Simula el rendimiento histórico si se ignora una señal de venta.
    condicion: 'TP' (Take Profit), 'SL' (Stop Loss), 'RSI_alto', 'Score_bajo', etc.
    """
    try:
        ticker = _crear_ticker(simbolo)
        hist = safe_history(ticker, "3y")
        if hist.empty or len(hist) < 100:
            return {'error': 'Datos insuficientes'}
        
        # Convertir a MXN
        factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
        for col in ['Close','Open','High','Low']:
            hist[col] *= factor
        
        hist = calcular_indicadores(hist)
        hist = hist.dropna()
        
        # Definir días forward a evaluar
        horizontes = [5, 10, 20]  # días hábiles
        
        # Función para detectar condiciones similares en el pasado
        def condicion_pasada(row_idx, df):
            row = df.iloc[row_idx]
            if condicion == 'TP':
                # Buscar momentos donde la ganancia desde mínimo reciente superó 15%
                # Simplificado: mirar si el precio está un 15% por encima de la EMA50 o similar
                # Usamos una heurística: retorno 15% en los últimos 30 días
                ret_30d = (row['Close'] / df.iloc[max(0,row_idx-30)]['Close'] - 1) * 100 if row_idx>=30 else 0
                return ret_30d >= 15
            elif condicion == 'SL':
                ret_30d = (row['Close'] / df.iloc[max(0,row_idx-30)]['Close'] - 1) * 100
                return ret_30d <= -7
            elif condicion == 'RSI_alto':
                return row['RSI'] > 70
            elif condicion == 'Score_bajo':
                # Recalcular score en ese momento
                prev = df.iloc[row_idx-1].to_dict() if row_idx>0 else None
                score, _ = calcular_score(row.to_dict(), prev)
                return score < 4
            else:
                return True  # por defecto, todas las fechas
        
        resultados = {h: [] for h in horizontes}
        for i in range(50, len(hist) - max(horizontes)):
            if condicion_pasada(i, hist):
                precio_actual_pasado = hist['Close'].iloc[i]
                for h in horizontes:
                    precio_futuro = hist['Close'].iloc[i + h]
                    ret = (precio_futuro / precio_actual_pasado - 1) * 100
                    resultados[h].append(ret)
        
        stats = {}
        for h in horizontes:
            if resultados[h]:
                stats[f'ret_{h}d'] = round(np.mean(resultados[h]), 2)
                stats[f'win_rate_{h}d'] = round((np.array(resultados[h]) > 0).mean() * 100, 1)
                stats[f'mediana_{h}d'] = round(np.median(resultados[h]), 2)
            else:
                stats[f'ret_{h}d'] = None
                stats[f'win_rate_{h}d'] = None
        
        return stats
    except Exception as e:
        return {'error': str(e)}

def _construir_dataset_ml(hist: pd.DataFrame, simbolo: str, usd_mxn: float, eur_mxn: float):
    factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
    for col in ['Close', 'Open', 'High', 'Low']:
        hist[col] *= factor

    regime_series = obtener_regimen_diario()
    hist = hist.join(regime_series.rename('REGIME'), how='left')
    hist['REGIME'] = hist['REGIME'].ffill().fillna(1)

    hist = calcular_indicadores(hist)
    hist = hist.dropna().copy()
    if hist.empty:
        return None, None

    # Ventana deslizante: se limita el entrenamiento a los últimos X meses
    # para evitar aprender patrones de regímenes muy antiguos que ya no aplican.
    fecha_fin = hist.index.max()
    fecha_inicio_ventana = fecha_fin - pd.DateOffset(months=ML_WINDOW_MONTHS)
    hist = hist[hist.index >= fecha_inicio_ventana].copy()

    ret_futuro_5d = (hist['Close'].shift(-5) / hist['Close'] - 1) * 100
    hist['target'] = np.select([ret_futuro_5d > 1.5, ret_futuro_5d < -1.5], [2, 0], default=1)
    hist['ret_1d'] = hist['Close'].pct_change().shift(-1)

    features = [
        'EMA20', 'EMA50', 'RSI', 'MACD', 'MACD_sig', 'ATR', 'BB_pct',
        'STOCH_K', 'STOCH_D', 'Volume', 'Vol_avg', 'ROC', 'WILLR',
        'OBV', 'ATR_RATIO', 'DOW', 'REGIME'
    ]
    for feature in features:
        if feature not in hist.columns:
            hist[feature] = 0.0

    hist = hist.dropna(subset=features + ['target', 'ret_1d']).copy()
    return hist, features


def _split_train_test_temporal(df_modelo: pd.DataFrame):
    fecha_fin = df_modelo.index.max()
    inicio_test = fecha_fin - pd.DateOffset(months=ML_TEST_MONTHS)

    df_test = df_modelo[df_modelo.index >= inicio_test].copy()
    df_train = df_modelo[df_modelo.index < inicio_test].copy()

    # Fallback de seguridad cuando el corte por meses deja muy pocas observaciones
    if len(df_test) < 15:
        corte = int(len(df_modelo) * 0.2)
        corte = max(15, corte)
        df_train = df_modelo.iloc[:-corte].copy()
        df_test = df_modelo.iloc[-corte:].copy()

    return df_train, df_test


def _calcular_metricas_clasificacion(y_true, y_pred, y_proba):
    metricas = {
        'f1': round(float(f1_score(y_true, y_pred, average='macro', zero_division=0) * 100), 2),
        'precision': round(float(precision_score(y_true, y_pred, average='macro', zero_division=0) * 100), 2),
        'recall': round(float(recall_score(y_true, y_pred, average='macro', zero_division=0) * 100), 2),
        'auc_roc': None,
    }
    try:
        if y_proba is not None and len(np.unique(y_true)) > 1:
            metricas['auc_roc'] = round(float(roc_auc_score(y_true, y_proba, multi_class='ovr', average='macro')), 4)
    except Exception:
        metricas['auc_roc'] = None
    return metricas


def _guardar_walk_forward(simbolo: str, resultados: dict):
    try:
        ruta = _data_file_path("walk_forward_results.json")
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = json.load(f)
        else:
            contenido = {}

        contenido[simbolo] = {
            'actualizado_en': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **resultados,
        }

        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(contenido, f, indent=2, ensure_ascii=False)
    except Exception:
        logger.exception("No se pudo guardar walk_forward_results.json para %s", simbolo)


def _ejecutar_walk_forward(df_modelo: pd.DataFrame, features: list, best_params: dict):
    df = df_modelo.sort_index().copy()
    if len(df) < 120:
        return {'estado': 'insuficiente_data'}

    fecha_actual = df.index.min() + pd.DateOffset(months=WF_TRAIN_MONTHS)
    fecha_max = df.index.max()

    resultados = []
    folds = []

    params_rf = {
        'n_estimators': best_params.get('n_estimators', 100),
        'max_depth': best_params.get('max_depth', 5),
        'min_samples_split': best_params.get('min_samples_split', 2),
        'class_weight': best_params.get('class_weight', 'balanced'),
        'random_state': 42,
    }

    while fecha_actual < fecha_max:
        inicio_train = fecha_actual - pd.DateOffset(months=WF_TRAIN_MONTHS)
        fin_test = fecha_actual + pd.DateOffset(months=WF_PREDICT_MONTHS)

        train_df = df[(df.index > inicio_train) & (df.index <= fecha_actual)].copy()
        test_df = df[(df.index > fecha_actual) & (df.index <= fin_test)].copy()

        fecha_actual = fin_test

        if len(train_df) < 60 or len(test_df) < WF_MIN_OBS_TEST:
            continue
        if train_df['target'].nunique() < 2:
            continue

        rf = RandomForestClassifier(**params_rf)
        rf.fit(train_df[features], train_df['target'])
        pred = rf.predict(test_df[features])

        señales = np.where(pred == 2, 1, np.where(pred == 0, -1, 0))
        retorno_estrategia = señales * test_df['ret_1d'].values
        retorno_bh = test_df['ret_1d'].values

        bloque = pd.DataFrame({
            'fecha': test_df.index,
            'ret_estrategia': retorno_estrategia,
            'ret_buy_hold': retorno_bh,
        })
        resultados.append(bloque)

        folds.append({
            'train_inicio': str(train_df.index.min().date()),
            'train_fin': str(train_df.index.max().date()),
            'test_inicio': str(test_df.index.min().date()),
            'test_fin': str(test_df.index.max().date()),
            'obs_test': int(len(test_df)),
            'retorno_estrategia_pct': round(float(((1 + retorno_estrategia).prod() - 1) * 100), 2),
            'retorno_buy_hold_pct': round(float(((1 + retorno_bh).prod() - 1) * 100), 2),
        })

    if not resultados:
        return {'estado': 'sin_folds_validos'}

    total = pd.concat(resultados).sort_values('fecha')
    total['capital_estrategia'] = (1 + total['ret_estrategia']).cumprod()
    total['capital_bh'] = (1 + total['ret_buy_hold']).cumprod()

    retorno_total_estrategia = float((total['capital_estrategia'].iloc[-1] - 1) * 100)
    retorno_total_bh = float((total['capital_bh'].iloc[-1] - 1) * 100)

    return {
        'estado': 'ok',
        'parametros': {'ventana_train_meses': WF_TRAIN_MONTHS, 'horizonte_test_meses': WF_PREDICT_MONTHS},
        'resumen': {
            'retorno_acumulado_estrategia_pct': round(retorno_total_estrategia, 2),
            'retorno_acumulado_buy_hold_pct': round(retorno_total_bh, 2),
            'diferencia_pct': round(retorno_total_estrategia - retorno_total_bh, 2),
            'folds_validos': len(folds),
        },
        'folds': folds,
    }


def entrenar_modelo_ml(simbolo: str, usd_mxn: float, eur_mxn: float) -> dict:
    simbolo = normalizar_simbolo(simbolo)
    cache = _ml_cache_global()

    if simbolo in cache:
        entrada = cache[simbolo]
        if (datetime.now() - entrada['ts']).total_seconds() < 604800:
            return entrada['payload']

    clf_repo, meta_repo = repo_cargar_modelo_ml(simbolo)
    if clf_repo is not None and meta_repo:
        payload_repo = {
            'model': clf_repo,
            'accuracy': meta_repo.get('metricas_out_of_sample', {}).get('f1', meta_repo.get('accuracy', 0)),
            'accuracy_in_sample': meta_repo.get('metricas_in_sample', {}).get('f1', meta_repo.get('accuracy', 0)),
            'metricas_out_of_sample': meta_repo.get('metricas_out_of_sample', {}),
            'feature_importance': meta_repo.get('feature_importance', {}),
            'fuente': '☁️ repo',
            'fecha_entrenamiento': meta_repo.get('fecha', ''),
        }
        cache[simbolo] = {'payload': payload_repo, 'ts': datetime.now()}
        return payload_repo

    try:
        ticker = _crear_ticker(simbolo)
        hist = safe_history(ticker, "3y")
        if hist.empty or len(hist) < 200:
            return None

        df_modelo, features = _construir_dataset_ml(hist, simbolo, usd_mxn, eur_mxn)
        if df_modelo is None or len(df_modelo) < 120:
            return None

        df_train, df_test = _split_train_test_temporal(df_modelo)
        if len(df_train) < 60 or len(df_test) < 15:
            return None
        if df_train['target'].nunique() < 2:
            return None

        X_train, y_train = df_train[features], df_train['target']
        X_test, y_test = df_test[features], df_test['target']

        n_splits_cv = min(4, max(2, min(8, len(X_train) // 40)))
        tscv = TimeSeriesSplit(n_splits=n_splits_cv)
        param_grid = {
            'n_estimators': [50, 100],
            'max_depth': [3, 5, 7],
            'min_samples_split': [2, 5],
            'class_weight': ['balanced', None],
        }

        grid = GridSearchCV(
            RandomForestClassifier(random_state=42),
            param_grid,
            cv=tscv,
            scoring='f1_macro',
            n_jobs=-1,
        )
        grid.fit(X_train, y_train)
        best_clf = grid.best_estimator_

        cv_cal = TimeSeriesSplit(n_splits=min(3, max(2, len(X_train) // 60)))
        calibrated_clf = CalibratedClassifierCV(best_clf, method='sigmoid', cv=cv_cal)
        calibrated_clf.fit(X_train, y_train)

        y_pred_train = calibrated_clf.predict(X_train)
        y_pred_test = calibrated_clf.predict(X_test)
        y_proba_test = calibrated_clf.predict_proba(X_test) if hasattr(calibrated_clf, 'predict_proba') else None

        metricas_train = _calcular_metricas_clasificacion(y_train, y_pred_train, None)
        metricas_test = _calcular_metricas_clasificacion(y_test, y_pred_test, y_proba_test)

        importance_values = getattr(best_clf, 'feature_importances_', np.zeros(len(features)))
        importance_dict = {f: round(float(v), 6) for f, v in zip(features, importance_values)}
        importance_ordenada = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
        features_casi_cero = [f for f, v in importance_ordenada if v <= FEATURE_IMPORTANCE_ZERO_TH]

        wf_result = _ejecutar_walk_forward(df_modelo, features, grid.best_params_)
        _guardar_walk_forward(simbolo, wf_result)

        fecha_entreno = datetime.now().strftime("%Y-%m-%d %H:%M")
        meta_entry = {
            'accuracy': metricas_test.get('f1', 0),
            'fecha': fecha_entreno,
            'fecha_ultimo_entrenamiento': fecha_entreno,
            'ventana_meses': ML_WINDOW_MONTHS,
            'validacion': 'TimeSeriesSplit',
            'periodo_test_out_of_sample': {
                'inicio': str(df_test.index.min().date()),
                'fin': str(df_test.index.max().date()),
                'meses': ML_TEST_MONTHS,
                'observaciones': int(len(df_test)),
            },
            'metricas_in_sample': metricas_train,
            'metricas_out_of_sample': metricas_test,
            'feature_importance': {
                'top': [{'feature': f, 'importancia': v} for f, v in importance_ordenada[:10]],
                'todas': importance_dict,
                'cercanas_a_cero': features_casi_cero,
                'umbral_cero': FEATURE_IMPORTANCE_ZERO_TH,
            },
            'parametros_modelo': grid.best_params_,
            'walk_forward': wf_result.get('resumen', {'estado': wf_result.get('estado', 'nd')}),
        }

        repo_guardar_modelo_ml(simbolo, calibrated_clf, meta_entry)

        payload = {
            'model': calibrated_clf,
            'accuracy': metricas_test.get('f1', 0),
            'accuracy_in_sample': metricas_train.get('f1', 0),
            'metricas_out_of_sample': metricas_test,
            'feature_importance': meta_entry['feature_importance'],
            'fuente': '🔄 entrenado',
            'fecha_entrenamiento': fecha_entreno,
        }
        cache[simbolo] = {'payload': payload, 'ts': datetime.now()}
        return payload

    except Exception:
        logger.exception("Error entrenando ML para %s", simbolo)
        st.warning(f"No se pudo entrenar el modelo ML para {simbolo}. Se continuará sin ML.")
        return None

def analizar_sentimiento(simbolo: str) -> dict:
    # ... (tu código original)
    simbolo = normalizar_simbolo(simbolo)
    if not NEWSAPI_KEY:
        return {'sentimiento': 'Sin clave', 'score': 0, 'noticias': []}
    try:
        from_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        url = 'https://newsapi.org/v2/everything'
        params = {'q': simbolo.split('.')[0], 'from': from_date, 'sortBy': 'relevancy', 'language': 'en', 'pageSize': 5, 'apiKey': NEWSAPI_KEY}
        resp = requests.get(url, params=params, timeout=10, verify=SSL_VERIFY_PATH)
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
    except:
        return {'sentimiento': 'Error', 'score': 0, 'noticias': []}
    
def optimizar_cartera(compras_df: pd.DataFrame, capital: float, usd_mxn: float, eur_mxn: float) -> pd.DataFrame:
    # ... (tu código original)
    if compras_df.empty:
        return compras_df
    n = len(compras_df)
    symbols = compras_df['Símbolo'].tolist()
    precios = {}
    for sim in symbols:
        try:
            ticker = _crear_ticker(sim)
            hist = safe_history(ticker, "6mo")
            if hist.empty:
                continue
            factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
            precios[sim] = hist['Close'] * factor
        except:
            continue
    if len(precios) < 2:
        compras_df['Peso Cartera'] = 1.0 / n
        compras_df['Inversión Asignada'] = compras_df['Peso Cartera'] * capital
        compras_df['Unidades Ajustadas'] = compras_df['Inversión Asignada'] / compras_df['Precio (MXN)'].astype(float)
        return compras_df
    df_prices = pd.DataFrame(precios).dropna()
    if df_prices.empty:
        compras_df['Peso Cartera'] = 1.0 / n
        compras_df['Inversión Asignada'] = compras_df['Peso Cartera'] * capital
        compras_df['Unidades Ajustadas'] = compras_df['Inversión Asignada'] / compras_df['Precio (MXN)'].astype(float)
        return compras_df
    returns = df_prices.pct_change().dropna()
    cov = returns.cov() * 252
    expected_returns = compras_df.set_index('Símbolo')['Score'] / 100
    try:
        inv_cov = np.linalg.pinv(cov.values)
        ret_vec = expected_returns.reindex(cov.index).values
        w = inv_cov @ ret_vec
        w = w / w.sum()
        w = np.maximum(w, 0)
        w = w / w.sum()
        asignacion = {sym: w[i] for i, sym in enumerate(cov.index)}
    except:
        asignacion = {sym: 1.0 / n for sym in symbols}
    compras_df['Peso Cartera'] = compras_df['Símbolo'].map(asignacion).fillna(1.0 / n)
    compras_df['Inversión Asignada'] = compras_df['Peso Cartera'] * capital
    compras_df['Unidades Ajustadas'] = compras_df['Inversión Asignada'] / compras_df['Precio (MXN)'].astype(float)
    return compras_df

# ============================================================
# ALERTAS Y GRÁFICOS (simplificados pero funcionales)
# ============================================================
def enviar_email(asunto: str, cuerpo_html: str) -> bool:
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"] = EMAIL_REMITENTE
        msg["To"] = EMAIL_DESTINO
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
        r = requests.get("https://api.callmebot.com/whatsapp.php", params={"phone": WHATSAPP_NUMERO, "apikey": WHATSAPP_APIKEY, "text": mensaje}, timeout=10, verify=SSL_VERIFY_PATH)
        return r.status_code == 200
    except:
        return False

def construir_email_html(compras_df: pd.DataFrame, ventas_df: pd.DataFrame, resumen_ia: str = "") -> str:
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    filas_compra = ""
    for _, r in compras_df.iterrows():
        filas_compra += f"<tr><td><b>{r['Símbolo']}</b> Zurich<br> </td>was{r['Precio (MXN)']} </td>was{r.get('Score', '')} <table>was{r.get('Motivo', '')} </tr>"
    filas_venta = ""
    for _, r in ventas_df.iterrows():
        filas_venta += f"<tr><td><b>{r['Símbolo']}</b> </td>was{r['Precio (MXN)']} </td>was{r.get('Motivo', '')} </td></tr>"
    bloque_ia = f"<h3 style='color:#7b61ff'>🤖 Análisis de IA</h3><div style='background:#f5f3ff;padding:12px 16px;border-left:4px solid #7b61ff;border-radius:4px;font-size:14px;line-height:1.6'>{resumen_ia.replace(chr(10), '<br>')}</div>" if resumen_ia else ""
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px">
    <h2 style="color:#1a73e8">📈 Alerta de Trading — {fecha}</h2>
    {bloque_ia}
    <h3 style="color:#34a853">🟢 Señales de COMPRA ({len(compras_df)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
      <tr style="background:#e8f5e9"><th>Símbolo</th><th>Precio (MXN)</th><th>Score</th><th>Motivo</th> <tr>
      {filas_compra if filas_compra else '<tr><td colspan="4">Sin señales</td>'}
     </table>
    <h3 style="color:#ea4335">🔴 Señales de VENTA ({len(ventas_df)})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
      <tr style="background:#fce8e6"><th>Símbolo</th><th>Precio (MXN)</th><th>Motivo</th> </tr>
      {filas_venta if filas_venta else '<tr><td colspan="3">Sin señales</td>'}
     </table>
    <p style="color:#666;font-size:12px;margin-top:20px">Generado por Sistema de Trading Personal v3.0</p>
    </body></html>"""

def grafico_enriquecido(simbolo: str, usd_mxn: float, eur_mxn: float) -> go.Figure:
    # ... (tu código original)
    hist = safe_history(_crear_ticker(simbolo), "6mo")
    if hist.empty:
        return go.Figure()
    factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
    for col in ['Close','Open','High','Low']:
        hist[col] *= factor
    hist = calcular_indicadores(hist)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                        row_heights=[0.5,0.18,0.18,0.14], 
                        vertical_spacing=0.03,
                        subplot_titles=(f"{simbolo} — Precio (MXN)", "RSI (14)", "MACD", "Volumen"))
    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], 
                                 low=hist['Low'], close=hist['Close'], name="Precio"), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA20'], line=dict(color='#ff9800', width=1.5), name='EMA20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA50'], line=dict(color='#e91e63', width=1.5), name='EMA50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], line=dict(color='#7e57c2', width=1.5), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1, annotation_text="Sobrecompra")
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1, annotation_text="Sobreventa")
    colors_hist = ['#26a69a' if v >= 0 else '#ef5350' for v in hist['MACD_hist'].fillna(0)]
    fig.add_trace(go.Bar(x=hist.index, y=hist['MACD_hist'], marker_color=colors_hist, name='MACD Hist'), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD'], line=dict(color='#2196f3', width=1.5), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD_sig'], line=dict(color='#ff5722', width=1.5), name='Señal'), row=3, col=1)
    vol_colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(hist['Close'], hist['Open'])]
    fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], marker_color=vol_colors, name='Volumen'), row=4, col=1)
    fig.update_layout(template='plotly_dark', height=750, xaxis_rangeslider_visible=False,
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1))
    return fig

def dashboard_rendimiento(df_hist: pd.DataFrame) -> None:
    if df_hist.empty:
        st.info("Sin historial suficiente.")
        return
    df_hist = df_hist.sort_values('fecha')
    returns = []
    for _, row in df_hist.iterrows():
        try:
            ticker = _crear_ticker(row['simbolo'])
            hist = ticker.history(start=row['fecha'] - timedelta(days=5), end=row['fecha'] + timedelta(days=10))
            if hist.empty:
                continue
            idx = hist.index.searchsorted(row['fecha'])
            if idx + 5 < len(hist):
                ret = (hist['Close'].iloc[idx+5] / row['precio'] - 1) * 100
                returns.append(ret)
        except:
            continue
    if returns:
        df_hist['retorno'] = returns
        df_hist['ret_acum'] = (1 + df_hist['retorno']/100).cumprod()
        st.plotly_chart(px.line(df_hist, x='fecha', y='ret_acum', title='Rendimiento acumulado'), width='stretch')

def dashboard_rendimiento_ventas(df_hist: pd.DataFrame) -> None:
    st.write(f"Depuración: historial_senales.csv tiene {len(df_hist)} filas")
    if 'recomendacion' in df_hist.columns:
        st.write(f"Ventas en historial: {len(df_hist[df_hist['recomendacion'] == 'VENDER'])}")
    else:
        st.write("La columna 'recomendacion' no existe en el historial.")
    if df_hist.empty:
        st.info("Sin historial de ventas suficiente.")
        return
    if 'recomendacion' not in df_hist.columns:
        st.info("El historial no contiene información de recomendaciones.")
        return
    df_ventas = df_hist[df_hist['recomendacion'] == "VENDER"].copy()
    if 'ganancia_pct' not in df_ventas.columns:
        st.info("No hay datos de ganancia en el historial.")
        return
    df_ventas = df_ventas.dropna(subset=['ganancia_pct'])
    if df_ventas.empty:
        st.info("No hay ventas registradas con ganancia/pérdida en el historial.")
        return
    total_ventas = len(df_ventas)
    if total_ventas < 10:
        st.warning(f"⚠️ Solo tienes {total_ventas} operación(es) registrada(s). Las estadísticas son poco fiables con pocas muestras.")
    df_ventas = df_ventas.sort_values('fecha')
    df_ventas['factor'] = (1 + df_ventas['ganancia_pct']/100).cumprod()
    fig = px.line(df_ventas, x='fecha', y='factor', 
                  title='Crecimiento acumulado de $1 invertido en las señales de VENTA',
                  labels={'factor': 'Multiplicador del capital (1 = capital inicial)', 'fecha': 'Fecha'})
    fig.update_layout(yaxis_tickformat = '.2f')
    fig.add_hline(y=1, line_dash="dash", line_color="gray", annotation_text="Capital inicial")
    st.plotly_chart(fig, width='stretch')
    win_rate = (df_ventas['ganancia_pct'] > 0).mean() * 100
    ganancia_promedio = df_ventas['ganancia_pct'].mean()
    ganancia_media = df_ventas['ganancia_pct'].median()
    ganancia_total_pct = (df_ventas['factor'].iloc[-1] - 1) * 100
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏆 Win Rate", f"{win_rate:.1f}%")
    col2.metric("📈 Ganancia promedio", f"{ganancia_promedio:.2f}%")
    col3.metric("📊 Ganancia mediana", f"{ganancia_media:.2f}%")
    col4.metric("🔢 Total señales", total_ventas)
    if total_ventas > 0:
        if win_rate > 70:
            rendimiento = "excelente"
        elif win_rate > 50:
            rendimiento = "bueno"
        else:
            rendimiento = "mejorable"
        st.info(f"📊 **Resumen:** Hasta ahora has registrado {total_ventas} señal(es) de venta. "
                f"Tuviste un acierto del {win_rate:.1f}% con una ganancia promedio del {ganancia_promedio:.2f}%. "
                f"Tu capital habría crecido un {ganancia_total_pct:.1f}% si hubieras seguido todas las señales. "
                f"**Este desempeño es {rendimiento}.**")
    fig_hist = px.histogram(df_ventas, x='ganancia_pct', nbins=20, 
                            title='Distribución de ganancias/pérdidas de las señales de venta',
                            labels={'ganancia_pct': 'Ganancia (%)'})
    st.plotly_chart(fig_hist, width='stretch')
    st.subheader("Últimas señales de venta")
    st.dataframe(df_ventas[['fecha', 'simbolo', 'ganancia_pct', 'score']]
                 .tail(10).sort_values('fecha', ascending=False)
                 .style.format({'ganancia_pct': '{:.2f}%'}),
                 width='stretch')

# ============================================================
# ANÁLISIS IA
# ============================================================
def _calcular_hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()
def _guardar_cache_ia(prompt: str, respuesta: str):
    os.makedirs("cache_ia", exist_ok=True)
    key = _calcular_hash_prompt(prompt)
    with open(f"cache_ia/{key}.json", 'w', encoding='utf-8') as f:
        json.dump({'timestamp': time.time(), 'prompt': prompt, 'respuesta': respuesta}, f)
def _obtener_cache_ia(prompt: str) -> str | None:
    key = _calcular_hash_prompt(prompt)
    ruta = f"cache_ia/{key}.json"
    if not os.path.exists(ruta):
        return None
    with open(ruta, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if time.time() - data.get('timestamp',0) < 3600:
        return data.get('respuesta')
    return None
def _construir_prompt(oportunidades: list[dict], regime: dict, usd_mxn: float) -> str:
    resumen = "\n".join([f"- {o['Símbolo']}: Score {o['Score']}, RSI {o['RSI']}" for o in oportunidades[:8]])
    return f"""Eres analista. Mercado: {regime['regime']}, USD/MXN {usd_mxn:.2f}. Oportunidades: {resumen}. Da un análisis breve."""
def analisis_ia(oportunidades: list[dict], regime: dict, usd_mxn: float) -> str:
    if not oportunidades:
        return ""
    prompt = _construir_prompt(oportunidades, regime, usd_mxn)
    cache = _obtener_cache_ia(prompt)
    if cache:
        return cache
    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            resp = requests.post(url, json={"contents": [{"parts":[{"text":prompt}]}]}, timeout=30, verify=SSL_VERIFY_PATH)
            if resp.status_code == 200:
                texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                _guardar_cache_ia(prompt, texto)
                return texto
        except Exception as e:
            logger.warning("No se pudo consultar Gemini: %s", e)
    if GROQ_API_KEY:
        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                                 json={"model": "llama-3.3-70b-versatile", "messages": [{"role":"user","content":prompt}], "max_tokens":500}, timeout=30, verify=SSL_VERIFY_PATH)
            if resp.status_code == 200:
                texto = resp.json()["choices"][0]["message"]["content"]
                _guardar_cache_ia(prompt, texto)
                return texto
        except Exception as e:
            logger.warning("No se pudo consultar Groq: %s", e)
    return "IA no disponible."

# ============================================================
# FUNCIÓN ANALIZAR ACCIÓN (CORREGIDA: SIN FILTRO DE VOLUMEN EXCESIVO)
# ============================================================
def analizar_accion(args: tuple) -> dict | None:
    (simbolo, precio_compra_dict, precios_actuales, usd_mxn, eur_mxn, incluir_fund, incluir_bt,
     regime_bonus, capital, riesgo_pct, trailing_enabled, trailing_pct) = args
    simbolo = normalizar_simbolo(simbolo)
    try:
        periodo = "6mo" if incluir_bt else "3mo"
        ticker = _crear_ticker(simbolo)

        if simbolo in precios_actuales:
            precio_actual_mxn = precios_actuales[simbolo]
        else:
            precio_actual = obtener_precio_actual(simbolo)
            if precio_actual is None:
                return None
            precio_actual_mxn = convertir_precio_mxn(simbolo, precio_actual, usd_mxn, eur_mxn)

        hist = safe_history(ticker, period=periodo)
        if hist.empty or len(hist) < 20:
            atr = precio_actual_mxn * 0.02
            score = 0
            señales = []
            ultimo = {}
        else:
            factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
            for col in ['Close', 'Open', 'High', 'Low']:
                hist[col] = hist[col] * factor
            hist = calcular_indicadores(hist)
            hist = hist.dropna(subset=['RSI', 'MACD', 'EMA20', 'EMA50', 'ATR', 'STOCH_K', 'STOCH_D'])
            if len(hist) >= 2:
                ultimo = hist.iloc[-1].to_dict()
                penultimo = hist.iloc[-2].to_dict()
                atr = ultimo['ATR']
                score_base, señales = calcular_score(ultimo, penultimo)
                score = max(0, score_base + regime_bonus)
            else:
                atr = precio_actual_mxn * 0.02
                score = 0
                señales = []
                ultimo = {}

        ps = position_size(precio_actual_mxn, atr, capital, riesgo_pct)

        p_compra = precio_compra_dict.get(simbolo)
        if p_compra is None and simbolo.endswith('.MX'):
            p_compra = precio_compra_dict.get(simbolo.replace('.MX', ''))
        señales_venta = []
        if p_compra:
            ganancia = ((precio_actual_mxn / p_compra) - 1) * 100
            if simbolo == 'INTC':
                st.write(f"🔍 INTC: compra={p_compra:.2f}, actual={precio_actual_mxn:.2f}, ganancia={ganancia:.2f}%")
            if trailing_enabled and ganancia > 0:
                if 'HIGHEST_PRICE' not in st.session_state:
                    st.session_state['HIGHEST_PRICE'] = {}
                highest = st.session_state['HIGHEST_PRICE'].get(simbolo, p_compra)
                if precio_actual_mxn > highest:
                    highest = precio_actual_mxn
                    st.session_state['HIGHEST_PRICE'][simbolo] = highest
                trailing_stop_price = highest * (1 - trailing_pct / 100)
                if precio_actual_mxn <= trailing_stop_price:
                    señales_venta.append(f"📉 Trailing Stop activado (máx {highest:.2f} → stop {trailing_stop_price:.2f})")
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
            'Precio (MXN)': round(precio_actual_mxn, 2),
            'Score': score,
            'RSI': round(ultimo['RSI'], 1) if ultimo else 50,
            'ATR': round(atr, 2),
            'Stop Loss': round(precio_actual_mxn - 2 * atr, 2),
            'Take Profit': round(precio_actual_mxn + 3 * atr, 2),
            'Unidades': ps['unidades'],
            'Inversión (MXN)': ps['inversion_mxn'],
            '% Capital': ps['pct_capital'],
            'Dist EMA50': round((precio_actual_mxn / ultimo['EMA50'] - 1) * 100, 2) if ultimo else 0,
            'Recomendación': recomendacion,
            'Motivo': motivo,
            'Señales': " | ".join(señales)
        }
        if incluir_fund:
            resultado.update(obtener_fundamentales_profundos(simbolo))
        if incluir_bt and recomendacion.startswith("COMPRAR") and ultimo:
            bt = backtest_realista(simbolo, precio_actual_mxn, atr)
            resultado['BT Resultado'] = f"{bt['resultado']:.2f}% ({bt['tipo']})"
        return resultado
    except Exception as e:
        print(f"[analizar_accion] {simbolo}: {type(e).__name__}: {e}")
        return None

# ============================================================
# SIDEBAR Y RESTAURACIÓN DE DATOS
# ============================================================
usd_mxn, eur_mxn = obtener_tipo_cambio()
st.sidebar.markdown("### 💱 Tipos de cambio")
st.sidebar.metric("USD/MXN", f"{usd_mxn:.2f}")
st.sidebar.metric("EUR/MXN", f"{eur_mxn:.2f}")
st.sidebar.markdown("---")

st.sidebar.header("⚙️ Parámetros")

if 'datos_cargados' not in st.session_state:
    st.session_state['datos_cargados'] = False
if not st.session_state['datos_cargados']:
    with st.sidebar:
        with st.spinner("🔄 Restaurando datos..."):
            posiciones_repo = repo_cargar_posiciones()
            if posiciones_repo:
                st.session_state['PRECIO_COMPRA'] = {
                    normalizar_simbolo(k): (v.get('precio', 0.0) if isinstance(v, dict) else float(v))
                    for k, v in posiciones_repo.items()
                }
                st.sidebar.success(f"✅ {len(posiciones_repo)} posiciones restauradas.")
            else:
                st.session_state.setdefault('PRECIO_COMPRA', {})
                if _repo_disponible():
                    st.sidebar.info("📂 Repo conectado — sin posiciones.")
                else:
                    st.sidebar.warning("⚠️ Sin persistencia activa.")
            repo_cargar_transacciones()
            repo_cargar_historial()
            st.session_state['datos_cargados'] = True

with st.sidebar.expander("💾 Backup", expanded=False):
    if st.button("📥 Descargar backup ZIP"):
        zip_bytes = generar_backup_zip()
        st.download_button("Guardar ZIP", data=zip_bytes, file_name="backup.zip")
    uploaded_bk = st.file_uploader("Restaurar ZIP", type="zip")
    if uploaded_bk and st.button("Restaurar"):
        pos_restauradas = restaurar_desde_zip(uploaded_bk)
        if pos_restauradas:
            repo_guardar_posiciones(pos_restauradas)
            st.session_state['POSICIONES'] = pos_restauradas
            st.session_state['PRECIO_COMPRA'] = {k: v['precio'] for k, v in pos_restauradas.items()}
            st.rerun()

if _repo_disponible():
    st.sidebar.caption("☁️ Repo GitHub conectado")
else:
    st.sidebar.caption("⚫ Sin repo")

mercado_seleccionado = st.sidebar.selectbox("📊 Mercado", list(mercado_opciones.keys()), index=1)

st.sidebar.markdown("### 🔧 Análisis")
fundamentales_check = st.sidebar.checkbox("📊 Análisis fundamental (profundo)", value=False)
filtro_fundamentales = False
if fundamentales_check:
    filtro_fundamentales = st.sidebar.checkbox("📊 Solo fundamentales sólidos", value=False)
backtesting_check    = st.sidebar.checkbox("🧪 Backtesting realista (SL/TP)", value=True)
market_regime_check  = st.sidebar.checkbox("🌡️ Filtrar por Market Regime", value=True)
ia_check = st.sidebar.checkbox("🤖 Análisis IA", value=True)
sentiment_check = st.sidebar.checkbox("📰 Análisis de sentimiento (noticias)", value=False)
ml_check = st.sidebar.checkbox("🧠 Modelo predictivo (ML)", value=False)

st.sidebar.markdown("### 💼 Gestión de capital")
capital_total = st.sidebar.number_input("Capital (MXN)", min_value=1000.0, value=100_000.0, step=1000.0)
riesgo_pct = st.sidebar.slider("Riesgo por operación (%)", 0.5, 3.0, 1.0, 0.25)

st.sidebar.markdown("### 📉 Trailing Stop")
trailing_enabled = st.sidebar.checkbox("Activar Trailing Stop dinámico", value=False)
trailing_pct = st.sidebar.slider("Trailing stop (%)", 1.0, 10.0, 5.0, 0.5, disabled=not trailing_enabled)

st.sidebar.markdown("### 🎯 Filtro de Alta Confianza")
alta_confianza = st.sidebar.checkbox("Mostrar solo señales de alta confianza", value=False)
if alta_confianza:
    filtro_score = st.sidebar.checkbox("Score >= 8", value=True)
    filtro_rsi = st.sidebar.checkbox("RSI entre 45 y 65", value=True)
    filtro_ml = st.sidebar.checkbox("ML predicción positiva", value=False)
    filtro_sentimiento = st.sidebar.checkbox("Sentimiento positivo", value=False)

st.sidebar.markdown("### 🔔 Alertas")
alerta_email = st.sidebar.checkbox("📧 Alertas email", value=True)
alerta_whatsapp = st.sidebar.checkbox("💬 Alertas WhatsApp", value=False)
umbral_score = st.sidebar.slider("Umbral score para alertar", 4, 10, 7)

st.sidebar.markdown("### 💰 Registrar compra")
compra_input = st.sidebar.text_area("Compra", placeholder="AAPL,10,4465.53\nWALMEX.MX,5,56.13", height=120, key="compra_input")
if st.sidebar.button("🛒 REGISTRAR COMPRA", key="btn_registrar_compra"):
    if compra_input and compra_input.strip():
        procesar_compras_ppp(compra_input)
    else:
        st.sidebar.warning("Ingresa compras con formato: SIMBOLO,CANTIDAD,PRECIO")

st.sidebar.markdown("### 💰 Registrar venta")
venta_input = st.sidebar.text_area("Venta", placeholder="AAPL,10,4750.00", height=120)
if st.sidebar.button("📉 REGISTRAR VENTA"):
    procesar_ventas(venta_input)

if st.sidebar.button("♻️ RECONSTRUIR CARTERA"):
    posiciones = reconstruir_posiciones_desde_transacciones()

    if posiciones:
        repo_guardar_posiciones(posiciones)
        st.session_state['POSICIONES'] = posiciones
        st.session_state['PRECIO_COMPRA'] = {
            k: v['precio'] for k, v in posiciones.items()
        }
        st.sidebar.success("✅ Cartera reconstruida desde transacciones.csv")
        st.rerun()
    else:
        st.sidebar.warning("No se pudo reconstruir. Revisa transacciones.csv.")

st.sidebar.markdown("### 📂 Google Drive")
drive_upload = st.sidebar.checkbox("💾 Guardar en Drive", value=False)

if st.sidebar.button("🔍 ANALIZAR", type="primary"):
    posiciones_actuales = repo_cargar_posiciones()
    st.session_state['POSICIONES'] = posiciones_actuales
    st.session_state['PRECIO_COMPRA'] = {k: v['precio'] for k, v in posiciones_actuales.items()}
    PRECIO_COMPRA = st.session_state['PRECIO_COMPRA']
    st.session_state['HIGHEST_PRICE'] = {}

    # Las compras se registran exclusivamente con el botón "REGISTRAR COMPRA"
    # para evitar duplicados al presionar ANALIZAR.

    usd_mxn, eur_mxn = obtener_tipo_cambio()
    regime_data = obtener_market_regime()
    regime_bonus = regime_data['score_bonus'] if market_regime_check else 0
    trade_capital = capital_total * 0.25

    lista_acciones = mercado_opciones[mercado_seleccionado].copy()
    if PRECIO_COMPRA:
        for sim in PRECIO_COMPRA.keys():
            if sim not in lista_acciones:
                lista_acciones.append(sim)

    total = len(lista_acciones)
    st.info(f"Analizando {total} acciones...")

    precios_actuales = {}
    if PRECIO_COMPRA:
        st.info("🔄 Obteniendo precios actuales de la cartera...")
        for sim in PRECIO_COMPRA.keys():
            precio = obtener_precio_actual(sim)
            if precio is not None:
                precios_actuales[sim] = convertir_precio_mxn(sim, precio, usd_mxn, eur_mxn)
            time.sleep(0.5)
        st.info(f"✅ Precios obtenidos para {len(precios_actuales)} posiciones.")

    with st.spinner(f"Analizando {total} acciones en paralelo..."):
        resultados = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        completados = 0
        args_list = [
            (sim, PRECIO_COMPRA, precios_actuales, usd_mxn, eur_mxn, fundamentales_check,
             backtesting_check, regime_bonus, trade_capital, riesgo_pct,
             trailing_enabled, trailing_pct)
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
        st.error("⚠️ No se obtuvieron resultados para ningún símbolo.\n\n"
                 "**Causa más probable en Streamlit Cloud:** Yahoo Finance está bloqueando las "
                 "peticiones de `yfinance` (rate-limit 429 sobre IPs compartidas).\n\n"
                 "**Soluciones:**\n"
                 "1. Espera 10-30 min y vuelve a intentar.\n"
                 "2. Asegúrate de que `curl_cffi` esté en `requirements.txt` (ya se usa "
                 "impersonación de Chrome en esta versión).\n"
                 "3. Revisa los logs de Streamlit Cloud (Manage app → Logs) para ver el error exacto "
                 "de yfinance.\n"
                 "4. Si persiste, despliega en Render/Railway (IP dedicada) o usa una API alternativa "
                 "(Alpha Vantage, Finnhub).")
        st.stop()

    df = pd.DataFrame(resultados)
    st.success(f"✅ Análisis completado. Se obtuvieron {len(df)} resultados.")
    ventas = df[(df['Recomendación'] == 'VENDER') & (df['Símbolo'].isin(PRECIO_COMPRA.keys()))].copy() if PRECIO_COMPRA else pd.DataFrame()
    compras = df[df['Recomendación'].str.startswith('COMPRAR')].sort_values('Score', ascending=False).copy()
    observar = df[df['Recomendación'] == 'OBSERVAR'].sort_values('Score', ascending=False).copy()
    
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _, row in df.iterrows():
        senal = {
            'Símbolo': row['Símbolo'],
            'Precio MXN': row['Precio (MXN)'],
            'Score': row['Score'],
            'Recomendación': row['Recomendación'],
            'Motivo': row.get('Motivo', ''),
            'Señales': row.get('Señales', '')
        }
        if senal['Recomendación'] == "VENDER":
            st.write(f"DEBUG: Señal de venta encontrada: {senal['Símbolo']} - {senal['Motivo']}")
        guardar_senal_en_historial(senal, fecha_actual)

    if alta_confianza:
        filtro = pd.Series([True] * len(compras))
        if filtro_score:
            filtro = filtro & (compras['Score'] >= 8)
        if filtro_rsi:
            filtro = filtro & (compras['RSI'].between(45, 65))
        if filtro_ml and 'ML Predicción' in compras.columns:
            if 'ML F1 OOS (%)' in compras.columns:
                f1_oos = pd.to_numeric(compras['ML F1 OOS (%)'], errors='coerce').fillna(0)
                filtro = filtro & (f1_oos >= 50)
            else:
                filtro = filtro & (compras['ML Predicción'].str.contains("F1 OOS", na=False))
        if filtro_sentimiento and 'Sentimiento' in compras.columns:
            filtro = filtro & (compras['Sentimiento'] == 'positivo')
        compras = compras[filtro].copy()
        if compras.empty:
            st.warning("⚠️ No hay señales que cumplan los criterios de alta confianza. Desactiva el filtro para ver todas.")
    
    if filtro_fundamentales and fundamentales_check and not compras.empty:
        required_cols = ['ROE (%)', 'Debt/Equity', 'EPS Growth (%)', 'Net Margin (%)']
        if all(col in compras.columns for col in required_cols):
            for col in required_cols:
                compras[col] = pd.to_numeric(compras[col], errors='coerce')
            mask = (
                (compras['ROE (%)'].fillna(-999) > 5) &
                (compras['Debt/Equity'].fillna(999) < 2) &
                (compras['EPS Growth (%)'].fillna(-999) > 0) &
                (compras['Net Margin (%)'].fillna(-999) > 0)
            )
            filtradas = compras[mask].copy()
            if filtradas.empty:
                st.warning("⚠️ No hay acciones que cumplan los criterios fundamentales sólidos.")
            else:
                st.success(f"✅ Filtro fundamental aplicado: {len(compras)} → {len(filtradas)} acciones")
                compras = filtradas
        else:
            st.warning("⚠️ No se encontraron datos fundamentales. Asegúrate de activar 'Análisis fundamental (profundo)'.")

    if sentiment_check and not compras.empty:
        with st.spinner("Analizando sentimiento..."):
            for idx, row in compras.iterrows():
                sent = analizar_sentimiento(row['Símbolo'])
                compras.at[idx, 'Sentimiento'] = sent['sentimiento']
                compras.at[idx, 'Sentimiento Score'] = sent['score']
                compras.at[idx, 'Noticias'] = "; ".join(sent['noticias'][:2])

    if ml_check and not compras.empty:
        with st.spinner("🧠 Cargando modelos ML..."):
            for idx, row in compras.iterrows():
                model_info = entrenar_modelo_ml(row['Símbolo'], usd_mxn, eur_mxn)
                if model_info:
                    metricas_oos = model_info.get('metricas_out_of_sample', {})
                    f1_oos = metricas_oos.get('f1', model_info.get('accuracy', 0))
                    auc_oos = metricas_oos.get('auc_roc')
                    f1_in = model_info.get('accuracy_in_sample')

                    texto_auc = f" | AUC OOS {auc_oos}" if auc_oos is not None else ""
                    compras.at[idx, 'ML Predicción'] = f"{model_info['fuente']} F1 OOS {f1_oos}%{texto_auc}"
                    compras.at[idx, 'ML F1 OOS (%)'] = f1_oos
                    compras.at[idx, 'ML F1 In-Sample (%)'] = f1_in if f1_in is not None else np.nan
                    compras.at[idx, 'ML AUC OOS'] = auc_oos if auc_oos is not None else np.nan

                    top_features = model_info.get('feature_importance', {}).get('top', [])
                    if top_features:
                        compras.at[idx, 'Top Feature ML'] = top_features[0].get('feature', '')
                else:
                    compras.at[idx, 'ML Predicción'] = "No disponible"

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

    # IMPORTANTE:
    # No guardar PRECIO_COMPRA aquí porque solo contiene precios,
    # no cantidades. Si lo guardamos, posiciones.json queda con cantidad = 1.
    repo_guardar_transacciones()

    if ia_check and not compras.empty:
        with st.spinner("🤖 Analizando con IA..."):
            texto_ia = analisis_ia(
                compras.head(8).to_dict('records'),
                regime_data,
                usd_mxn
            )
            st.session_state['analisis_ia'] = texto_ia
    else:
        st.session_state['analisis_ia'] = ""

    # ========== MOTOR DE ALERTAS DE VENTA (CORREGIDO CON CONVERSIÓN) ==========
    posiciones_json = repo_cargar_posiciones()
    alertas_vender = []
    if posiciones_json:
        for simbolo, datos in posiciones_json.items():
            p_compra = datos.get('precio', 0) if isinstance(datos, dict) else datos
            if p_compra <= 0:
                continue
            # Intentar obtener precio actual desde df (ya en MXN) o desde función
            p_actual_mxn = None
            if simbolo in df['Símbolo'].values:
                p_actual_mxn = df[df['Símbolo'] == simbolo]['Precio (MXN)'].iloc[0]
            if p_actual_mxn is None or pd.isna(p_actual_mxn):
                precio_original = obtener_precio_actual(simbolo)
                if precio_original is not None:
                    p_actual_mxn = convertir_precio_mxn(simbolo, precio_original, usd_mxn, eur_mxn)
                else:
                    continue
            ganancia = ((p_actual_mxn / p_compra) - 1) * 100
            if ganancia >= 15.0 or ganancia <= -7.0:
                motivo = f"🎯 Take Profit +{ganancia:.2f}%" if ganancia >= 15 else f"🛑 Stop Loss {ganancia:.2f}%"
                alertas_vender.append({
                    'Símbolo': simbolo,
                    'Precio Compra': round(p_compra, 2),
                    'Precio Actual': round(p_actual_mxn, 2),
                    'Ganancia (%)': round(ganancia, 2),
                    'Recomendación': 'VENDER',
                    'Motivo': motivo
                })
    st.session_state['alertas_venta_final'] = alertas_vender

    compras_alerta = compras
    resumen_ia = st.session_state.get('analisis_ia', '')

    if (alerta_email or alerta_whatsapp) and (not compras_alerta.empty or not ventas.empty):
        with st.spinner("📤 Enviando alertas..."):
            if alerta_email:
                html = construir_email_html(compras_alerta, ventas, resumen_ia)
                enviar_email(f"📈 Alerta Trading {datetime.now().strftime('%d/%m %H:%M')}", html)
            if alerta_whatsapp and os.environ.get("GITHUB_ACTIONS") != "true":
                n_compras = len(compras_alerta)
                n_ventas = len(ventas)
                top3 = ", ".join(compras_alerta.head(3)['Símbolo'].tolist()) if n_compras else "ninguna"
                msg = (f"📈 *Alerta Trading* {datetime.now().strftime('%d/%m %H:%M')}\n"
                       f"🟢 Compras: {n_compras} (Top: {top3})\n🔴 Ventas: {n_ventas}\nUmbral: {umbral_score}")
                enviar_whatsapp(msg)

    if backtesting_check:
        with st.spinner("Optimizando backtesting..."):
            opt = get_backtest_optimization()
            if opt:
                st.session_state['param_opt'] = opt
                st.info(f"Backtest: mejor umbral score = {opt['best_score_thresh']}, ATR mult = {opt['best_atr_mult']}, win rate = {opt['best_win_rate']}%")

    st.success(f"✅ Análisis completado. {len(compras)} oportunidades de compra.")
    st.rerun()

# ============================================================
# PRESENTACIÓN DE RESULTADOS (si existen)
# ============================================================
if 'usd_mxn' not in st.session_state:
    usd_mxn, eur_mxn = obtener_tipo_cambio()
    st.session_state['usd_mxn'] = usd_mxn
    st.session_state['eur_mxn'] = eur_mxn

usd_mxn = st.session_state['usd_mxn']
eur_mxn = st.session_state['eur_mxn']

if 'df' in st.session_state:
    df = st.session_state['df']
    compras = st.session_state['compras']
    ventas = st.session_state['ventas']
    observar = st.session_state['observar']
    regime_data = st.session_state['regime']
    capital_total = st.session_state.get('capital', 100000.0)

    st.markdown(f"**Última actualización:** {st.session_state.get('ultima_actualizacion', 'Nunca')}")

    # ========== PANEL CORE + SATÉLITE ==========
    etf_cap = round(capital_total * 0.65, 2)
    trade_cap = round(capital_total * 0.25, 2)
    conv_cap = round(capital_total * 0.10, 2)
    st.markdown("### 💼 Estrategia recomendada: Core + Satélite")
    col1, col2, col3 = st.columns(3)
    col1.metric("🏛️ Core ETFs (65%)", f"${etf_cap:,.0f} MXN")
    col2.metric("⚡ Trading (25%)", f"${trade_cap:,.0f} MXN")
    col3.metric("🎯 Alta convicción (10%)", f"${conv_cap:,.0f} MXN")
    st.markdown("---")

    # ========== INDICADOR DE FILTRO ACTIVO ==========
    if alta_confianza and not compras.empty:
        total_original = len(df[df['Recomendación'].str.startswith('COMPRAR')])
        st.info(f"🔍 Filtro de alta confianza activado: {len(compras)} señales de {total_original} totales")

    # ========== MARKET REGIME ==========
    icono_regime = {'ALCISTA':'🟢','LATERAL':'🟡','BAJISTA':'🔴','DESCONOCIDO':'⚪'}.get(regime_data.get('regime','DESCONOCIDO'),'⚪')
    with st.expander(f"{icono_regime} Market Regime: {regime_data.get('regime','DESCONOCIDO')} — {regime_data.get('descripcion','')}", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("S&P 500", f"{regime_data.get('precio',0):,.0f}")
        c2.metric("EMA 200", f"{regime_data.get('ema200',0):,.0f}")
        c3.metric("RSI S&P", f"{regime_data.get('rsi_sp500',0)}")
        c4.metric("Ret. 1 mes", f"{regime_data.get('ret_1m',0):+.1f}%")
    
    col1, col2, col3, col4 = st.columns(4)
    alertas_vender = st.session_state.get('alertas_venta_final', [])
    total_ventas_combined = len(ventas) + len(alertas_vender)
    col1.metric("✅ Compras", len(compras))
    col2.metric("🔴 Ventas", total_ventas_combined)
    col3.metric("👀 Observar", len(observar))
    col4.metric("🚫 Evitar", len(df[df['Recomendación'] == 'EVITAR']))
    
    # ========== TABLAS Y SECCIONES ORGANIZADAS EN PESTAÑAS ==========
    st.subheader("📊 Resultados detallados")
    (tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8) = st.tabs([
        "🟢 COMPRAS", "🔴 VENTAS", "🟡 OBSERVAR", "🔍 TODAS",
        "💼 CARTERA", "📜 HISTORIAL", "🏆 TOP 10", "📊 BACKTEST VENTAS"
    ])

    with tab1:
        if not compras.empty:
            cols_compras = ['Símbolo','Precio (MXN)','Score','RSI','ATR','Stop Loss','Take Profit',
                            'ML Predicción','ML F1 OOS (%)','ML AUC OOS','ML F1 In-Sample (%)','Top Feature ML',
                            'Unidades','Inversión (MXN)','% Capital','Peso Cartera','Inversión Asignada',
                            'Unidades Ajustadas','Recomendación','Motivo','Señales']
            st.dataframe(compras[[c for c in cols_compras if c in compras.columns]], width='stretch')
        else:
            st.info("Sin compras.")
    with tab2:
        if alertas_vender:
            st.error("🚨 POSICIONES DE TU CARTERA EN OBJETIVO (VENDER)")
            df_alertas = pd.DataFrame(alertas_vender)
            st.dataframe(df_alertas[['Símbolo','Precio Compra','Precio Actual','Ganancia (%)','Motivo']], width='stretch')
            st.divider()
        st.subheader("📉 Señales Técnicas de Venta")
        if not ventas.empty:
            cols_ventas = ['Símbolo','Precio (MXN)','Score','RSI','Stop Loss','Take Profit','Recomendación','Motivo']
            st.dataframe(ventas[[c for c in cols_ventas if c in ventas.columns]], width='stretch')
        else:
            st.info("No hay señales técnicas de venta en el escáner.")
        if not alertas_vender and ventas.empty:
            st.info("Sin ventas. Tus posiciones abiertas no han alcanzado Take Profit (+15%) ni Stop Loss (-7%).")
    with tab3:
        if not observar.empty:
            cols_obs = ['Símbolo','Precio (MXN)','Score','RSI','Stop Loss','Take Profit','Motivo']
            st.dataframe(observar[[c for c in cols_obs if c in observar.columns]], width='stretch')
        else:
            st.info("Sin observaciones.")
    with tab4:
        st.dataframe(df, width='stretch')
    with tab5:
        st.subheader("Posiciones abiertas")
        posiciones_json = repo_cargar_posiciones()
        if posiciones_json:
            filas_cartera = []
            for simb, datos in posiciones_json.items():
                p_compra = datos.get('precio', 0)
                cant = datos.get('cantidad', 0)
                p_actual_mxn = None
                if simb in df['Símbolo'].values:
                    p_actual_mxn = df[df['Símbolo'] == simb]['Precio (MXN)'].iloc[0]
                else:
                    precio_original = obtener_precio_actual(simb)
                    if precio_original is not None:
                        p_actual_mxn = convertir_precio_mxn(simb, precio_original, usd_mxn, eur_mxn)
                    else:
                        p_actual_mxn = p_compra
                filas_cartera.append({
                    'Símbolo': simb,
                    'Títulos': cant,
                    'Precio Compra': p_compra,
                    'Precio Actual': p_actual_mxn,
                    'Ganancia (%)': ((p_actual_mxn / p_compra) - 1) * 100 if p_compra > 0 else 0
                })
            df_cartera = pd.DataFrame(filas_cartera)
            st.dataframe(
                df_cartera.style.format({
                    'Precio Compra': '${:,.2f}',
                    'Precio Actual': '${:,.2f}',
                    'Ganancia (%)': '{:.2f}%'
                }),
                width='stretch'
            )
        else:
            st.info("No hay posiciones registradas.")
    with tab6:
        st.subheader("Historial de transacciones")
        df_trans = cargar_transacciones()
        if not df_trans.empty:
            st.dataframe(df_trans.sort_values('fecha', ascending=False), width='stretch')
            ventas_df = df_trans[df_trans['tipo'] == 'venta'].copy()
            if not ventas_df.empty and 'ganancia_pct' in ventas_df.columns:
                ventas_df['ganancia_pct'] = pd.to_numeric(ventas_df['ganancia_pct'], errors='coerce')
                ventas_con_ganancia = ventas_df.dropna(subset=['ganancia_pct'])
                if not ventas_con_ganancia.empty:
                    ventas_con_ganancia['ganancia_mxn'] = ventas_con_ganancia['total'] * (ventas_con_ganancia['ganancia_pct'] / 100) / (1 + ventas_con_ganancia['ganancia_pct'] / 100)
                    ventas_con_ganancia['ganancia_mxn'] = ventas_con_ganancia['ganancia_mxn'].round(2)
                    ganancia_total_mxn = ventas_con_ganancia['ganancia_mxn'].sum()
                    win_rate = (ventas_con_ganancia['ganancia_pct'] > 0).mean() * 100
                    ganancia_promedio = ventas_con_ganancia['ganancia_pct'].mean()
                    col_wr, col_gp, col_total = st.columns(3)
                    col_wr.metric("🏆 Win Rate", f"{win_rate:.1f}%")
                    col_gp.metric("📈 Ganancia promedio por venta", f"{ganancia_promedio:.2f}%")
                    col_total.metric("💰 Ganancia Total (MXN)", f"${ganancia_total_mxn:,.2f}")
                    st.dataframe(ventas_con_ganancia[['fecha','simbolo','cantidad','precio','total','ganancia_pct','ganancia_mxn','notas']].sort_values('fecha', ascending=False), width='stretch')
                    fig = px.bar(ventas_con_ganancia, x='fecha', y='ganancia_pct', color='ganancia_pct',
                                 hover_data=['simbolo', 'notas', 'ganancia_mxn'],
                                 title='Rendimiento de ventas cerradas',
                                 color_continuous_scale=['red', 'yellow', 'green'])
                    st.plotly_chart(fig, width='stretch')
                    st.subheader("📆 Rendimiento Mensual (MXN)")
                    ventas_con_ganancia['fecha'] = pd.to_datetime(ventas_con_ganancia['fecha'])
                    ventas_con_ganancia['mes'] = ventas_con_ganancia['fecha'].dt.to_period('M')
                    monthly = ventas_con_ganancia.groupby('mes').agg(
                        ganancia_total_mxn=('ganancia_mxn', 'sum'),
                        num_operaciones=('ganancia_mxn', 'count'),
                        ganancia_promedio_pct=('ganancia_pct', 'mean'),
                        win_count=('ganancia_pct', lambda x: (x > 0).sum())
                    ).reset_index()
                    monthly['win_rate'] = (monthly['win_count'] / monthly['num_operaciones']) * 100
                    monthly['mes_str'] = monthly['mes'].astype(str)
                    fig_monthly = px.bar(monthly, x='mes_str', y='ganancia_total_mxn',
                                         title='Ganancia Neta Mensual (MXN)',
                                         labels={'ganancia_total_mxn': 'Ganancia (MXN)', 'mes_str': 'Mes'},
                                         text='ganancia_total_mxn')
                    fig_monthly.update_traces(texttemplate='$%{text:.2f}', textposition='outside')
                    st.plotly_chart(fig_monthly, width='stretch')
                    st.dataframe(monthly[['mes_str', 'num_operaciones', 'ganancia_total_mxn', 'ganancia_promedio_pct', 'win_rate']].rename(columns={
                        'mes_str': 'Mes', 'num_operaciones': 'Operaciones', 'ganancia_total_mxn': 'Ganancia Total (MXN)',
                        'ganancia_promedio_pct': 'Ganancia Promedio (%)', 'win_rate': 'Win Rate (%)'
                    }).style.format({
                        'Ganancia Total (MXN)': '${:,.2f}',
                        'Ganancia Promedio (%)': '{:.2f}%',
                        'Win Rate (%)': '{:.1f}%'
                    }), width='stretch')
                else:
                    st.info("Aún no hay ventas con ganancia registrada.")
            else:
                st.info("No hay ventas registradas aún.")
        else:
            st.info("No hay transacciones registradas.")
    with tab7:
        if not compras.empty:
            st.subheader("Top 10 señales de compra (Score y zona RSI)")
            top10 = compras.nlargest(10, 'Score').copy()
            top10['RSI'] = pd.to_numeric(top10['RSI'], errors='coerce')
            def zona_rsi(rsi):
                if rsi > 70:
                    return 'Sobrecompra'
                elif rsi < 30:
                    return 'Sobreventa'
                else:
                    return 'Neutral'
            top10['Zona'] = top10['RSI'].apply(zona_rsi)
            fig = px.bar(top10, x='Símbolo', y='Score', color='Zona',
                         color_discrete_map={'Sobrecompra': '#ef553b', 'Neutral': '#636efa', 'Sobreventa': '#00cc96'},
                         title='Top 10 por Score (color según RSI)',
                         labels={'Score': 'Puntuación (máx 14)'},
                         text='Score')
            fig.add_hline(y=7, line_dash="dash", line_color="orange", annotation_text="Umbral compra")
            fig.add_hline(y=4, line_dash="dash", line_color="gray", annotation_text="Umbral observar")
            fig.update_traces(textposition='outside')
            fig.update_layout(height=450, xaxis_tickangle=-45)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No hay señales de compra para mostrar el top.")
    with tab8:
        st.subheader("📈 Rendimiento histórico de señales de VENTA (TP/SL)")
        df_hist = cargar_historial_senales()
        dashboard_rendimiento_ventas(df_hist)
        st.divider()
        dashboard_rendimiento_real()
        analizar_adn_exito()
            # ===== SIMULACIÓN DE SEÑALES DE VENTA PENDIENTES =====
        st.subheader("🚨 ¿Qué pasa si IGNORAS estas señales de venta?")
        
        # Obtener señales de venta pendientes
        alertas_pendientes = st.session_state.get('alertas_venta_final', [])
        # También las señales técnicas de venta (dataframe ventas)
        df_ventas_tecnicas = st.session_state.get('ventas', pd.DataFrame())
        
        pendientes = []
        for a in alertas_pendientes:
            pendientes.append({
                'Símbolo': a['Símbolo'],
                'Tipo': 'TP/SL',
                'Precio Actual': a['Precio Actual'],
                'Motivo': a['Motivo']
            })
        if not df_ventas_tecnicas.empty:
            for _, row in df_ventas_tecnicas.iterrows():
                pendientes.append({
                    'Símbolo': row['Símbolo'],
                    'Tipo': 'Técnica',
                    'Precio Actual': row['Precio (MXN)'],
                    'Motivo': row['Motivo']
                })
        
        if pendientes:
            # Eliminar duplicados por símbolo (priorizar TP/SL si ambos existen)
            simbolos_vistos = set()
            pendientes_unicos = []
            for p in pendientes:
                if p['Símbolo'] not in simbolos_vistos:
                    simbolos_vistos.add(p['Símbolo'])
                    pendientes_unicos.append(p)
            
            st.info(f"📊 Analizando {len(pendientes_unicos)} señales de venta activas...")
            
            with st.spinner("Ejecutando simulaciones históricas..."):
                resultados_sim = []
                for p in pendientes_unicos:
                    # Determinar condición según el motivo
                    motivo = p['Motivo'].lower()
                    if 'take profit' in motivo or 'ganancia' in motivo:
                        cond = 'TP'
                    elif 'stop loss' in motivo or 'pérdida' in motivo:
                        cond = 'SL'
                    elif 'rsi' in motivo:
                        cond = 'RSI_alto'
                    else:
                        cond = 'Score_bajo'
                    
                    sim = simular_ignorar_senal(p['Símbolo'], p['Precio Actual'], cond, usd_mxn, eur_mxn)
                    if 'error' not in sim:
                        resultados_sim.append({
                            'Símbolo': p['Símbolo'],
                            'Tipo': p['Tipo'],
                            'Retorno promedio (5d)': f"{sim.get('ret_5d',0):.1f}%",
                            'Acierto 5d': f"{sim.get('win_rate_5d',0):.0f}%",
                            'Retorno promedio (10d)': f"{sim.get('ret_10d',0):.1f}%",
                            'Acierto 10d': f"{sim.get('win_rate_10d',0):.0f}%",
                        })
                    else:
                        resultados_sim.append({
                            'Símbolo': p['Símbolo'],
                            'Tipo': p['Tipo'],
                            'Retorno promedio (5d)': 'Sin datos',
                            'Acierto 5d': '-',
                            'Retorno promedio (10d)': '-',
                            'Acierto 10d': '-',
                        })
            
            if resultados_sim:
                df_sim = pd.DataFrame(resultados_sim)
                st.dataframe(df_sim, width='stretch')
                
                st.markdown("""
                **💡 Interpretación:**
                - *Retorno promedio (5d)*: Si hubieras ignorado esta señal de venta, en el pasado el precio **subió (positivo) o bajó (negativo)** en promedio después de 5 días.
                - *Acierto 5d*: Porcentaje de veces que **ignorar la señal habría sido rentable** (precio final > precio actual).
                - Si el retorno es **negativo** y el acierto **bajo (<50%)**, conviene hacer caso a la señal de venta.
                """)
            else:
                st.warning("No se pudo simular ninguna señal.")
        else:
            st.info("No hay señales de venta pendientes para simular.")

    if 'analisis_ia' in st.session_state and st.session_state['analisis_ia']:
        with st.expander("🤖 Análisis de IA", expanded=True):
            st.markdown(st.session_state['analisis_ia'])

    if not df.empty:
        col_ok = 'Símbolo' if 'Símbolo' in df.columns else df.columns[0]
        todos_simbolos = df[col_ok].tolist()
        sim_elegido = st.selectbox("Selecciona un símbolo para ver su gráfico completo", todos_simbolos, key="selector_grafico")
        if sim_elegido:
            fila = df[df['Símbolo'] == sim_elegido].iloc[0]
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Precio (MXN)", fila['Precio (MXN)'])
            col_b.metric("Score", fila['Score'])
            col_c.metric("RSI", fila['RSI'])
            col_d.metric("Recomendación", fila['Recomendación'])
            if st.session_state.get('PRECIO_COMPRA', {}).get(sim_elegido):
                precio_compra = st.session_state['PRECIO_COMPRA'][sim_elegido]
                ganancia = (fila['Precio (MXN)'] / precio_compra - 1) * 100
                st.metric("Ganancia actual", f"{ganancia:+.2f}%")
            fig = grafico_enriquecido(sim_elegido, usd_mxn, eur_mxn)
            st.plotly_chart(fig, width='stretch')

else:
    st.info("🔍 Aún no has ejecutado un análisis. Ve a la barra lateral y haz clic en 'ANALIZAR' para obtener señales de trading.")

st.caption("v3.0 — Corregido y optimizado por Adrian López")
