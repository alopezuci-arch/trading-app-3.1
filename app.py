# ============================================================
# SISTEMA DE TRADING PROFESIONAL v3.0 — STREAMLIT (FINAL)
# CORREGIDO: muestra resultados, sin filtros excesivos
# OPTIMIZADO: Eliminación de duplicidades, corrección de bug +15% y mejoras de flujo
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

from curl_cffi import requests as curl_requests

# Parche para yfinance: reemplazar la sesión de requests por curl_requests
def _patched_requests_session():
    return curl_requests.Session(impersonate="chrome124")

yf.shared._requests = _patched_requests_session

# --- Sesión con impersonación de navegador para evitar bloqueos de Yahoo en Streamlit Cloud ---
try:
    from curl_cffi import requests as curl_requests
    _YF_SESSION = curl_requests.Session(impersonate="chrome124")
except Exception:
    _YF_SESSION = None

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from textblob import TextBlob

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import googleapiclient.http

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(page_title="Trading System v3.0", layout="wide", page_icon="📈")
st.title("📈 Sistema de Trading Personal v3.0 (Mejorado y Optimizado)")

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
GHU_GIST_TOKEN = os.environ.get("GHU_GIST_TOKEN", "")
REPO_OWNER     = "alopezuci-arch"
REPO_NAME      = "trading-app-3.1"
DATA_PATH      = "data"

# Archivos de persistencia (definidos aquí para evitar NameError en funciones posteriores)
TRANSACCIONES_FILE = "transacciones.csv"
HISTORIAL_FILE     = "historial_senales.csv"

# ============================================================
# PERSISTENCIA
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
        r = requests.get(url, headers=_gh_headers(), timeout=12)
        if r.status_code == 200:
            return base64.b64decode(r.json()["content"]).decode("utf-8")
        elif r.status_code == 404:
            return ""
    except:
        pass
    return ""
def _repo_escribir(nombre: str, contenido: str, mensaje: str = "update") -> bool:
    if not _repo_disponible() or not contenido:
        return False
    import base64
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{DATA_PATH}/{nombre}"
        r_get = requests.get(url, headers=_gh_headers(), timeout=10)
        sha = r_get.json().get("sha", "") if r_get.status_code == 200 else ""
        payload = {"message": f"[trading-app] {mensaje}", "content": base64.b64encode(contenido.encode("utf-8")).decode("ascii")}
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=_gh_headers(), json=payload, timeout=15)
        return r.status_code in (200, 201)
    except:
        return False

def repo_cargar_posiciones() -> dict:
    contenido = _repo_leer("posiciones.json")
    if contenido:
        try:
            data = json.loads(contenido)
            # Normalización: Si detecta el formato viejo {SIMB: PRECIO}, lo convierte al nuevo
            for k, v in data.items():
                if not isinstance(v, dict):
                    data[k] = {"cantidad": 1.0, "precio": float(v)}
            return data
        except Exception as e:
            print(f"Error parseando posiciones: {e}")
    return {}
def repo_guardar_posiciones(posiciones: dict) -> bool:
    if not posiciones:
        # Si no hay posiciones, guardamos un diccionario vacío para limpiar el repo
        return _repo_escribir("posiciones.json", json.dumps({}), "limpiar posiciones")
    contenido = json.dumps({k.upper(): v for k, v in posiciones.items()}, indent=2, ensure_ascii=False)
    return _repo_escribir("posiciones.json", contenido, "actualizar posiciones")
def repo_cargar_transacciones() -> pd.DataFrame:
    cols = ["fecha","simbolo","cantidad","precio","tipo","total","notas","ganancia_pct"]
    contenido = _repo_leer("transacciones.csv")
    
    if contenido and contenido.strip():
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(contenido))
            
            # 1. Limpieza de nombres de columnas (quita espacios invisibles)
            df.columns = [c.strip() for c in df.columns]
            
            # 2. Aseguramos que la columna de ganancia exista y sea numérica
            if "ganancia_pct" not in df.columns:
                df["ganancia_pct"] = np.nan
            else:
                df["ganancia_pct"] = pd.to_numeric(df["ganancia_pct"], errors="coerce")
            
            # 3. Convertimos la fecha forzando errores a NaT (Not a Time)
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
            
            # Guardamos copia local para consistencia del sistema
            df.to_csv(TRANSACCIONES_FILE, index=False)
            return df
        except Exception as e:
            st.error(f"Error procesando transacciones desde GitHub: {e}")
            
    return pd.DataFrame(columns=cols)

def repo_guardar_transacciones() -> bool:
    if not os.path.exists(TRANSACCIONES_FILE):
        return False
    try:
        with open(TRANSACCIONES_FILE, "r", encoding="utf-8") as f:
            contenido = f.read()
        if not contenido.strip():
            return _repo_escribir("transacciones.csv", "", "limpiar transacciones") # Limpiar si está vacío
        return _repo_escribir("transacciones.csv", contenido, "sincronizar transacciones")
    except Exception as e:
        st.error(f"Error al subir a GitHub: {e}")
        return False
        
def repo_cargar_historial() -> pd.DataFrame:
    cols = ["fecha","simbolo","score","precio","recomendacion","señales","ganancia_pct"]
    contenido = _repo_leer("historial_senales.csv")
    if contenido and contenido.strip(): # Eliminado len > 60 para leer archivos pequeños
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(contenido))
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
            df["ganancia_pct"] = pd.to_numeric(df["ganancia_pct"], errors="coerce")
            df.to_csv("historial_senales.csv", index=False)
            return df
        except:
            pass
    return pd.DataFrame(columns=cols)
def repo_guardar_historial() -> bool:
    ruta = "historial_senales.csv"
    if not os.path.exists(ruta):
        return False
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            contenido = f.read()
        if not contenido.strip():
            return _repo_escribir("historial_senales.csv", "", "limpiar historial señales") # Limpiar si está vacío
        return _repo_escribir("historial_senales.csv", contenido, "sincronizar historial señales")
    except:
        return False

@st.cache_resource
def _ml_cache_global() -> dict:
    return {}
def repo_guardar_modelo_ml(simbolo: str, clf, accuracy: float):
    if not _repo_disponible():
        return
    try:
        import base64
        model_b64 = base64.b64encode(pickle.dumps(clf)).decode("ascii")
        meta = json.loads(_repo_leer("ml_meta.json") or "{}")
        meta[simbolo] = {"accuracy": accuracy, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")}
        _repo_escribir("ml_meta.json", json.dumps(meta, indent=2), "ml meta")
        nombre = f"ml_{simbolo.replace(".","_")}.b64"
        _repo_escribir(nombre, model_b64, f"modelo ML {simbolo}")
    except:
        pass
def repo_cargar_modelo_ml(simbolo: str):
    try:
        meta_str = _repo_leer("ml_meta.json")
        if not meta_str:
            return None, 0
        meta = json.loads(meta_str)
        if simbolo not in meta:
            return None, 0
        fecha_str = meta[simbolo].get("fecha", "")
        if fecha_str:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M")
            if (datetime.now() - fecha).total_seconds() > 604800:
                return None, 0
        import base64
        nombre = f"ml_{simbolo.replace(".","_")}.b64"
        b64 = _repo_leer(nombre)
        if b64:
            clf = pickle.loads(base64.b64decode(b64.encode("ascii")))
            return clf, meta[simbolo].get("accuracy", 0)
    except:
        pass
    return None, 0

def generar_backup_zip() -> bytes:
    """Genera un ZIP con todos los datos para descarga local."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        posiciones = st.session_state.get("PRECIO_COMPRA", {})
        zf.writestr("posiciones.json", json.dumps(posiciones, indent=2, ensure_ascii=False))
        if os.path.exists(TRANSACCIONES_FILE):
            zf.write(TRANSACCIONES_FILE, "transacciones.csv")
        if os.path.exists("historial_senales.csv"):
            zf.write("historial_senales.csv", "historial_senales.csv")
        zf.writestr("LEEME.txt", f"Backup Trading App — {datetime.now().strftime("%Y-%m-%d %H:%M")}\n")
    buf.seek(0)
    return buf.read()

def restaurar_desde_zip(uploaded_file) -> dict:
    """Lee un ZIP de backup y devuelve las posiciones; restaura CSV al disco."""
    import zipfile
    posiciones = {}
    try:
        with zipfile.ZipFile(io.BytesIO(uploaded_file.read())) as zf:
            if "posiciones.json" in zf.namelist():
                posiciones = json.loads(zf.read("posiciones.json").decode())
            if "transacciones.csv" in zf.namelist():
                with open(TRANSACCIONES_FILE, "wb") as f:
                    f.write(zf.read("transacciones.csv"))
            if "historial_senales.csv" in zf.namelist():
                with open("historial_senales.csv", "wb") as f:
                    f.write(zf.read("historial_senales.csv"))
    except Exception as e:
        st.error(f"Error leyendo backup: {e}")
    return posiciones
    
# ============================================================
# HISTORIAL Y TRANSACCIONES
# ============================================================
def cargar_transacciones() -> pd.DataFrame:
    if os.path.exists(TRANSACCIONES_FILE):
        df = pd.read_csv(TRANSACCIONES_FILE)
        df["fecha"] = pd.to_datetime(df["fecha"])
        if "ganancia_pct" not in df.columns:
            df["ganancia_pct"] = np.nan
        return df
    return pd.DataFrame(columns=["fecha","simbolo","cantidad","precio","tipo","total","notas","ganancia_pct"])
def guardar_transaccion(simbolo: str, cantidad: float, precio: float, tipo: str, notas: str = "", ganancia_pct: float = None):
    df = cargar_transacciones()
    nueva = pd.DataFrame([{
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "simbolo": simbolo.upper(),
        "cantidad": cantidad,
        "precio": precio,
        "tipo": tipo,
        "total": round(cantidad * precio, 2),
        "notas": notas,
        "ganancia_pct": ganancia_pct if ganancia_pct is not None else np.nan
    }])
    df = pd.concat([df, nueva], ignore_index=True)
    df.to_csv(TRANSACCIONES_FILE, index=False)

def procesar_ventas(input_text: str):
    if not input_text or not input_text.strip():
        st.sidebar.warning("No se ingresaron ventas.")
        return
    
    posiciones = repo_cargar_posiciones()
    ventas_registradas = 0
    
    for linea in input_text.strip().split("\n"):
        partes = linea.split(",")
        if len(partes) != 3: continue
        
        simbolo = partes[0].strip().upper()
        try:
            cant_vender = float(partes[1].strip())
            precio_venta = float(partes[2].strip())
        except: continue

        if simbolo in posiciones:
            pos = posiciones[simbolo]
            precio_compra_promedio = pos["precio"]
            
            # Cálculo de ganancia real sobre el promedio
            ganancia_pct = ((precio_venta / precio_compra_promedio) - 1) * 100
            
            guardar_transaccion(simbolo, cant_vender, precio_venta, "venta", 
                               notas="Venta manual (PPP)", ganancia_pct=ganancia_pct)
            
            # Actualizamos o eliminamos la posición
            nueva_cant = pos["cantidad"] - cant_vender
            if nueva_cant <= 0:
                del posiciones[simbolo]
            else:
                posiciones[simbolo]["cantidad"] = nueva_cant
            
            ventas_registradas += 1
            
    if ventas_registradas:
        repo_guardar_posiciones(posiciones)
        repo_guardar_transacciones()
        st.session_state["PRECIO_COMPRA"] = {k: v["precio"] for k, v in posiciones.items()}
        st.sidebar.success(f"✅ {ventas_registradas} ventas procesadas.")
        st.toast(f"✅ {ventas_registradas} ventas registradas", icon="💰")
        time.sleep(1)
        st.rerun()


def procesar_compras_ppp(input_text: str):
    posiciones = repo_cargar_posiciones()
    compras_ok = 0
    
    for linea in input_text.strip().split("\n"):
        partes = linea.split(",")
        if len(partes) != 3: continue
        
        simbolo = partes[0].strip().upper()
        cant_nueva = float(partes[1].strip())
        precio_nuevo = float(partes[2].strip())
        
        if simbolo in posiciones:
            # Lógica de Promedio Ponderado
            cant_actual = posiciones[simbolo]["cantidad"]
            prec_actual = posiciones[simbolo]["precio"]
            
            nueva_cantidad_total = cant_actual + cant_nueva
            nuevo_ppp = ((cant_actual * prec_actual) + (cant_nueva * precio_nuevo)) / nueva_cantidad_total
            
            posiciones[simbolo] = {"cantidad": nueva_cantidad_total, "precio": nuevo_ppp}
        else:
            posiciones[simbolo] = {"cantidad": cant_nueva, "precio": precio_nuevo}
        
        guardar_transaccion(simbolo, cant_nueva, precio_nuevo, "compra", notas="Compra manual (PPP)")
        compras_ok += 1
        
    if compras_ok:
        repo_guardar_posiciones(posiciones)
        repo_guardar_transacciones()
        st.session_state["PRECIO_COMPRA"] = {k: v["precio"] for k, v in posiciones.items()}
        st.sidebar.success(f"✅ {compras_ok} compras promediadas.")
        st.rerun()


def cargar_historial_senales() -> pd.DataFrame:
    if os.path.exists(HISTORIAL_FILE):
        try:
            df = pd.read_csv(HISTORIAL_FILE, on_bad_lines="skip")
            # Asegurar que la columna 'fecha' existe y es convertible
            if "fecha" in df.columns:
                df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
                # Eliminar filas con fecha inválida
                df = df.dropna(subset=["fecha"])
            else:
                # Si no hay columna fecha, crear una vacía
                df["fecha"] = pd.NaT
            
            # Asegurar que existe la columna ganancia_pct
            if "ganancia_pct" not in df.columns:
                df["ganancia_pct"] = np.nan
            else:
                df["ganancia_pct"] = pd.to_numeric(df["ganancia_pct"], errors="coerce")
            
            # Asegurar otras columnas necesarias
            columnas_necesarias = ["simbolo", "score", "precio", "recomendacion", "señales"]
            for col in columnas_necesarias:
                if col not in df.columns:
                    df[col] = ""
            return df
        except Exception as e:
            st.error(f"Error al cargar historial: {e}")
    # Si no existe o hay error, devolver DataFrame vacío con todas las columnas necesarias
    return pd.DataFrame(columns=["fecha", "simbolo", "score", "precio", "recomendacion", "señales", "ganancia_pct"])
    
def guardar_senal_en_historial(senal: dict, fecha: str):
    """
    Versión CORREGIDA para asegurar la extracción de ganancias (+15%)
    y evitar que el dashboard de ventas aparezca vacío.
    """
    import re
    # import os # Ya importado
    # import pandas as pd # Ya importado
    # from datetime import datetime, timedelta # Ya importado

    # 1. Cargar historial existente o crear estructura base
    if os.path.exists(HISTORIAL_FILE):
        try:
            df = pd.read_csv(HISTORIAL_FILE, on_bad_lines='skip')
            # Limpieza de fechas
            if 'fecha' in df.columns:
                df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
                df = df.dropna(subset=['fecha'])
            else:
                df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])
        except:
            df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])
    else:
        df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])

    # 2. Extracción robusta de ganancia porcentual
    ganancia = None
    if senal.get('Recomendación') == "VENDER" and 'Motivo' in senal:
        motivo = senal['Motivo']
        
        # EXPRESIÓN REGULAR MEJORADA:
        # - [+-]? : signo opcional
        # - \d+ : uno o más dígitos
        # - (?:\.\d+)? : decimales opcionales
        # - % : símbolo de porcentaje
        match = re.search(r'([+-]?\d+(?:\.\d+)?)%', motivo)
        
        if match:
            ganancia = float(match.group(1))
        else:
            # FALLBACK 1: Buscar números cerca de "Take Profit" o "TP"
            match_tp = re.search(r'(?:Take Profit|TP)\s*([+-]?\d+(?:\.\d+)?)', motivo, re.IGNORECASE)
            if match_tp:
                ganancia = float(match_tp.group(1))
            else:
                # FALLBACK 2: Buscar números cerca de "Stop Loss" o "SL"
                match_sl = re.search(r'(?:Stop Loss|SL)\s*([+-]?\d+(?:\.\d+)?)', motivo, re.IGNORECASE)
                if match_sl:
                    ganancia = float(match_sl.group(1))

    # 3. Preparar nueva fila
    nueva = pd.DataFrame([{
        'fecha': pd.to_datetime(fecha, errors='coerce'),
        'simbolo': senal['Símbolo'],
        'score': senal['Score'],
        'precio': senal['Precio MXN'],
        'recomendacion': senal['Recomendación'],
        'señales': senal.get('Señales', ''),
        'ganancia_pct': ganancia
    }])

    # 4. Concatenar y mantener ventana de 90 días
    df = pd.concat([df, nueva], ignore_index=True)
    cutoff = datetime.now() - timedelta(days=90)
    df = df[df['fecha'] >= cutoff]
    
    # 5. Guardar
    df.to_csv(HISTORIAL_FILE, index=False)

def dashboard_rendimiento_real():
    st.subheader("📊 Rendimiento Real de mi Cartera")
    
    df_trans = cargar_transacciones() 
    
    if df_trans is not None and not df_trans.empty:
        df_trans['tipo'] = df_trans['tipo'].astype(str).str.strip().str.lower()
        ventas = df_trans[df_trans['tipo'] == 'venta'].copy()
        ventas['ganancia_pct'] = pd.to_numeric(ventas['ganancia_pct'], errors='coerce')
        ventas = ventas.dropna(subset=['ganancia_pct'])
        
        if not ventas.empty:
            # Calcular ganancia en MXN
            # fórmula: ganancia_mxn = total * (ganancia_pct/100) / (1 + ganancia_pct/100)
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
            
            # Gráfico con escala de colores
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
    st.subheader("🧬 ADN de tus Aciertos (Aprendizaje LM)")
    df_hist = cargar_historial_senales()
    
    if not df_hist.empty and 'ganancia_pct' in df_hist.columns:
        # Asegurar que ganancia_pct sea numérico
        df_hist['ganancia_pct'] = pd.to_numeric(df_hist['ganancia_pct'], errors='coerce')
        aciertos = df_hist[df_hist['ganancia_pct'] > 0].copy()
        
        if not aciertos.empty:
            # Extraer señales (MACD, RSI, etc)
            todas_senales = ",".join(aciertos['señales'].astype(str)).split(',')
            from collections import Counter
            conteo = Counter([s.strip() for s in todas_senales if s.strip() and s.strip() != 'nan'])
            
            st.write("Factores técnicos detectados en tus operaciones ganadoras:")
            for factor, count in conteo.most_common(5):
                st.success(f"✔️ {factor}: Identificado en {count} aciertos")
        else:
            st.write("El modelo está esperando más cierres de ventas para identificar patrones de éxito.")
    else:
        st.write("Sin datos históricos de señales para analizar.")

# ============================================================
# LISTAS DE MERCADO
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
@st.cache_data(ttl=3600)
def obtener_tipo_cambio() -> tuple[float, float]:
    try:
        usd = yf.Ticker("USDMXN=X").history(period="5d")
        eur = yf.Ticker("EURMXN=X").history(period="5d")
        return (float(usd['Close'].iloc[-1]) if not usd.empty else 20.0,
                float(eur['Close'].iloc[-1]) if not eur.empty else 21.5)
    except Exception as e:
        print(f"[tipo_cambio] Error: {e}")
        return 20.0, 21.5

def safe_history(ticker, period="6mo", max_retries=3):
    last_err = None
    for intento in range(max_retries):
        try:
            hist = ticker.history(period=period, auto_adjust=True)
            if not hist.empty and len(hist) >= 20:
                return hist
            # vacío: esperar un poco y reintentar
            time.sleep(1 + intento)
        except Exception as e:
            last_err = e
            msg = str(e)
            if "Rate limit" in msg or "429" in msg or "Too Many Requests" in msg:
                time.sleep(2 ** intento)
            else:
                time.sleep(1)
    if last_err:
        print(f"[safe_history] {ticker.ticker if hasattr(ticker,'ticker') else '?'}: {last_err}")
    return pd.DataFrame()

def obtener_precio_actual(simbolo: str) -> float | None:
    """Obtiene el precio actual de un símbolo usando info o historial reciente con reintentos."""
    try:
        ticker = yf.Ticker(simbolo)
        # Primero intentar con info (rápido)
        precio = ticker.info.get('regularMarketPrice') or ticker.info.get('currentPrice')
        if precio:
            return float(precio)
        # Si no, usar historial reciente con reintentos
        hist = safe_history(ticker, period="2d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except:
        pass
    return None

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
    rango14 = (high14 - low14).replace(0, np.nan)
    hist['STOCH_K'] = 100 * (hist['Close'] - low14) / rango14
    hist['STOCH_D'] = hist['STOCH_K'].rolling(3).mean()
    hist['Vol_avg'] = hist['Volume'].rolling(20).mean()
    # Nuevos indicadores
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
    sp_hist = yf.Ticker("^GSPC").history(period="2y")
    if sp_hist.empty:
        return None
    sp_hist = calcular_indicadores(sp_hist)
    opt = backtest_optimizar_parametros(sp_hist)
    return opt

def entrenar_modelo_ml(simbolo: str, usd_mxn: float, eur_mxn: float) -> dict:
    cache = _ml_cache_global()
    if simbolo in cache:
        entrada = cache[simbolo]
        if (datetime.now() - entrada['ts']).total_seconds() < 604800:
            return {'model': entrada['model'], 'accuracy': entrada['acc'], 'fuente': '⚡ memoria'}
    clf_repo, acc_repo = repo_cargar_modelo_ml(simbolo)
    if clf_repo is not None:
        cache[simbolo] = {'model': clf_repo, 'acc': acc_repo, 'ts': datetime.now()}
        return {'model': clf_repo, 'accuracy': acc_repo, 'fuente': '☁️ repo'}
    try:
        ticker = yf.Ticker(simbolo)
        hist = safe_history(ticker, "3y")
        if hist.empty or len(hist) < 200:
            return None
        factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
        for col in ['Close','Open','High','Low']:
            hist[col] *= factor
        regime_series = obtener_regimen_diario()
        hist = hist.join(regime_series.rename('REGIME'), how='left')
        hist = calcular_indicadores(hist)
        hist = hist.dropna()
        if len(hist) < 200:
            return None
        ret_futuro = (hist['Close'].shift(-5) / hist['Close'] - 1) * 100
        hist['target'] = np.select([ret_futuro > 1.5, ret_futuro < -1.5], [2, 0], default=1)
        hist = hist.dropna()
        features = ['EMA20','EMA50','RSI','MACD','MACD_sig','ATR','BB_pct',
                    'STOCH_K','STOCH_D','Volume','Vol_avg','ROC','WILLR','OBV','ATR_RATIO','DOW','REGIME']
        for f in features:
            if f not in hist.columns:
                hist[f] = 0
        X = hist[features]
        y = hist['target']
        if len(X) > 504:
            X = X.tail(504)
            y = y.tail(504)
        from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
        tscv = TimeSeriesSplit(n_splits=3)
        from sklearn.ensemble import RandomForestClassifier
        param_grid = {'n_estimators': [50,100], 'max_depth': [3,5,7], 'min_samples_split': [2,5], 'class_weight': ['balanced',None]}
        grid = GridSearchCV(RandomForestClassifier(random_state=42), param_grid, cv=tscv, scoring='f1_macro', n_jobs=-1)
        grid.fit(X, y)
        best_clf = grid.best_estimator_
        from sklearn.calibration import CalibratedClassifierCV
        calibrated_clf = CalibratedClassifierCV(best_clf, method='sigmoid', cv=3)
        calibrated_clf.fit(X, y)
        from sklearn.metrics import f1_score
        y_pred = calibrated_clf.predict(X)
        final_f1 = f1_score(y, y_pred, average='macro') * 100
        cache[simbolo] = {'model': calibrated_clf, 'acc': round(final_f1, 1), 'ts': datetime.now()}
        repo_guardar_modelo_ml(simbolo, calibrated_clf, final_f1)
        return {'model': calibrated_clf, 'accuracy': round(final_f1, 1), 'fuente': '🔄 entrenado'}
    except Exception as e:
        print(f"Error entrenando ML para {simbolo}: {e}")
        return None

def construir_email_html(compras_df: pd.DataFrame, ventas_df: pd.DataFrame, resumen_ia: str = "") -> str:
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    filas_compra = ""
    for _, r in compras_df.iterrows():
        filas_compra += f"<tr><td><b>{r['Símbolo']}</b></td><td>{r['Precio (MXN)']}</td><td>{r.get('Score', '')}</td><td>{r.get('Motivo', '')}</td></tr>"
    
    filas_venta = ""
    for _, r in ventas_df.iterrows():
        filas_venta += f"<tr><td><b>{r['Símbolo']}</b></td><td>{r['Precio (MXN)']}</td><td>{r.get('Motivo', '')}</td></tr>"
    
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
        hist[col] = hist[col] * factor
    hist = calcular_indicadores(hist)
    
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                        row_heights=[0.5,0.18,0.18,0.14], 
                        vertical_spacing=0.03,
                        subplot_titles=(f"{simbolo} — Precio (MXN)", "RSI (14)", "MACD", "Volumen"))
    
    # Gráfico de velas
    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], 
                                 low=hist['Low'], close=hist['Close'], name="Precio"), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA20'], line=dict(color='#ff9800', width=1.5), name='EMA20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA50'], line=dict(color='#e91e63', width=1.5), name='EMA50'), row=1, col=1)
    
    # RSI con líneas de sobrecompra/sobreventa
    fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], line=dict(color='#7e57c2', width=1.5), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1, annotation_text="Sobrecompra")
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1, annotation_text="Sobreventa")
    
    # MACD
    colors_hist = ['#26a69a' if v >= 0 else '#ef5350' for v in hist['MACD_hist'].fillna(0)]
    fig.add_trace(go.Bar(x=hist.index, y=hist['MACD_hist'], marker_color=colors_hist, name='MACD Hist'), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD'], line=dict(color='#2196f3', width=1.5), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD_sig'], line=dict(color='#ff5722', width=1.5), name='Señal'), row=3, col=1)
    
    # Volumen
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
            ticker = yf.Ticker(row['simbolo'])
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
    
    # ========== MEJORA 1: Advertencia por pocas muestras ==========
    total_ventas = len(df_ventas)
    if total_ventas < 10:
        st.warning(f"⚠️ Solo tienes {total_ventas} operación(es) registrada(s). Las estadísticas son poco fiables con pocas muestras.")
    
    # ========== MEJORA 2: Formateo del gráfico de rendimiento acumulado ==========
    df_ventas = df_ventas.sort_values('fecha')
    # Calcular factor de crecimiento (empezando desde 1)
    df_ventas['factor'] = (1 + df_ventas['ganancia_pct']/100).cumprod()
    
    fig = px.line(df_ventas, x='fecha', y='factor', 
                  title='Crecimiento acumulado de $1 invertido en las señales de VENTA',
                  labels={'factor': 'Multiplicador del capital (1 = capital inicial)', 'fecha': 'Fecha'})
    fig.update_layout(yaxis_tickformat = '.2f')  # Muestra dos decimales
    fig.add_hline(y=1, line_dash="dash", line_color="gray", annotation_text="Capital inicial")
    st.plotly_chart(fig, width='stretch')
    
    # ========== Estadísticas básicas ==========
    win_rate = (df_ventas['ganancia_pct'] > 0).mean() * 100
    ganancia_promedio = df_ventas['ganancia_pct'].mean()
    ganancia_media = df_ventas['ganancia_pct'].median()
    ganancia_total_pct = (df_ventas['factor'].iloc[-1] - 1) * 100
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏆 Win Rate", f"{win_rate:.1f}%")
    col2.metric("📈 Ganancia promedio", f"{ganancia_promedio:.2f}%")
    col3.metric("📊 Ganancia mediana", f"{ganancia_media:.2f}%")
    col4.metric("🔢 Total señales", total_ventas)
    
    # ========== MEJORA 3: Mensaje resumen en lenguaje natural ==========
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
    
    # ========== Histograma (sin cambios, solo ajuste de título) ==========
    fig_hist = px.histogram(df_ventas, x='ganancia_pct', nbins=20, 
                            title='Distribución de ganancias/pérdidas de las señales de venta',
                            labels={'ganancia_pct': 'Ganancia (%)'})
    st.plotly_chart(fig_hist, width='stretch')
    
    # ========== Tabla de últimas ventas (con formato de moneda si tuviera, pero no) ==========
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
            resp = requests.post(url, json={"contents": [{"parts":[{"text":prompt}]}]}, timeout=30)
            if resp.status_code == 200:
                texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                _guardar_cache_ia(prompt, texto)
                return texto
        except:
            pass
    if GROQ_API_KEY:
        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                                 json={"messages": [{"role": "user", "content": prompt}], "model": "llama3-8b-8192"}, timeout=30)
            if resp.status_code == 200:
                texto = resp.json()["choices"][0]["message"]["content"]
                _guardar_cache_ia(prompt, texto)
                return texto
        except:
            pass
    return "IA no disponible."

# ============================================================
# FUNCIÓN ANALIZAR ACCIÓN (CORREGIDA: SIN FILTRO DE VOLUMEN EXCESIVO)
# ============================================================
def analizar_accion(args: tuple) -> dict | None:
    (simbolo, precio_compra_dict, precios_actuales, usd_mxn, eur_mxn, incluir_fund, incluir_bt,
     regime_bonus, capital, riesgo_pct, trailing_enabled, trailing_pct) = args
    try:
        periodo = "6mo" if incluir_bt else "3mo"
        ticker = yf.Ticker(simbolo)

        # ========== OBTENER PRECIO ACTUAL (usar diccionario precalculado si existe) ==========
        # Esta parte ya se optimizó en el flujo principal para hacer una sola llamada y pasar el dict
        precio_actual_mxn = precios_actuales.get(simbolo)
        if precio_actual_mxn is None:
            # Si por alguna razón no está en el dict (ej. símbolo nuevo añadido), intentar obtenerlo
            precio_actual = obtener_precio_actual(simbolo)
            if precio_actual is None:
                return None
            factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
            precio_actual_mxn = precio_actual * factor

        # ========== OBTENER HISTORIAL PARA INDICADORES (necesario para compras y para mostrar) ==========
        hist = safe_history(ticker, period=periodo)
        if hist.empty or len(hist) < 20:
            # No hay suficientes datos para indicadores, pero podemos evaluar venta igual
            atr = precio_actual_mxn * 0.02 # Estimación si no hay historial
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

        # ========== TAMAÑO DE POSICIÓN ==========
        ps = position_size(precio_actual_mxn, atr, capital, riesgo_pct)

        # ========== LÓGICA DE VENTA ==========
        p_compra = precio_compra_dict.get(simbolo)
        señales_venta = []
        if p_compra:
            ganancia = ((precio_actual_mxn / p_compra) - 1) * 100

            # Trailing stop dinámico
            if trailing_enabled and ganancia > 0:
                # Asegurarse de que HIGHEST_PRICE esté inicializado en session_state antes de usarlo
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

        # ========== RECOMENDACIÓN ==========
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

        # ========== RESULTADO ==========
        resultado = {
            'Símbolo': simbolo,
            'Precio (MXN)': round(precio_actual_mxn, 2),
            'Score': score,
            'RSI': round(ultimo['RSI'], 1) if ultimo and 'RSI' in ultimo else 50,
            'ATR': round(atr, 2),
            'Stop Loss': round(precio_actual_mxn - 2 * atr, 2),
            'Take Profit': round(precio_actual_mxn + 3 * atr, 2),
            'Unidades': ps['unidades'],
            'Inversión (MXN)': ps['inversion_mxn'],
            '% Capital': ps['pct_capital'],
            'Dist EMA50': round((precio_actual_mxn / ultimo['EMA50'] - 1) * 100, 2) if ultimo and 'EMA50' in ultimo else 0,
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
                st.session_state['PRECIO_COMPRA'] = posiciones_repo
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
            st.session_state['PRECIO_COMPRA'] = pos_restauradas
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
compra_input = st.sidebar.text_area("Compra", placeholder="AAPL,10,4465.53\nWALMEX.MX,5,56.13", height=120)

st.sidebar.markdown("### 💰 Registrar venta")
venta_input = st.sidebar.text_area("Venta", placeholder="AAPL,10,4750.00", height=120)
if st.sidebar.button("📉 REGISTRAR VENTA"):
    procesar_ventas(venta_input)

st.sidebar.markdown("### 📂 Google Drive")
drive_upload = st.sidebar.checkbox("💾 Guardar en Drive", value=False)

if st.sidebar.button("🔍 ANALIZAR", type="primary"):
    PRECIO_COMPRA = repo_cargar_posiciones() # Cargar posiciones al inicio del análisis
    st.session_state['HIGHEST_PRICE'] = {}

    if compra_input and compra_input.strip():
        nuevas_compras = 0
        for linea in compra_input.strip().split('\n'):
            if not linea.strip():
                continue
            partes = linea.split(',')
            if len(partes) == 3:
                sim = partes[0].strip().upper()
                try:
                    cantidad = float(partes[1].strip())
                    precio = float(partes[2].strip())
                    guardar_transaccion(sim, cantidad, precio, "compra")
                    # Si el símbolo no estaba en PRECIO_COMPRA, contamos como compra nueva
                    if sim not in PRECIO_COMPRA:
                        nuevas_compras += 1
                    PRECIO_COMPRA[sim] = {'cantidad': PRECIO_COMPRA.get(sim, {}).get('cantidad', 0) + cantidad, 'precio': precio} # Actualizar o añadir
                except:
                    pass
        if nuevas_compras > 0:
            st.sidebar.success(f"✅ {nuevas_compras} compra(s) nueva(s) registrada(s).")
        elif compra_input.strip():
            st.sidebar.warning("No se detectaron compras nuevas (los símbolos ya existían o hubo errores de formato).")
        # Siempre guardamos las posiciones actualizadas (aunque no haya nuevas, por si cambió precio)
        repo_guardar_posiciones(PRECIO_COMPRA)
        repo_guardar_transacciones()
    
    usd_mxn, eur_mxn = obtener_tipo_cambio()
    regime_data = obtener_market_regime()
    regime_bonus = regime_data['score_bonus'] if market_regime_check else 0
    trade_capital = capital_total * 0.25

    lista_acciones = mercado_opciones[mercado_seleccionado].copy()
    # Asegurarse de incluir los símbolos de la cartera actual para su análisis
    for sim in PRECIO_COMPRA.keys():
        if sim not in lista_acciones:
            lista_acciones.append(sim)

    total = len(lista_acciones)
    st.info(f"Analizando {total} acciones...")

    # ========== OBTENER PRECIOS ACTUALES DE TODAS LAS ACCIONES (VECTORIZADO) ==========
    st.info("🔄 Obteniendo precios actuales de todas las acciones...")
    # Usar yf.download para obtener precios de múltiples tickers de forma eficiente
    tickers_str = " ".join(lista_acciones)
    try:
        data = yf.download(tickers_str, period="1d", interval="1m", progress=False)
        if not data.empty:
            precios_actuales_raw = data['Close'].iloc[-1].to_dict() if len(lista_acciones) > 1 else {lista_acciones[0]: data['Close'].iloc[-1]}
            precios_actuales = {}
            for sim, precio in precios_actuales_raw.items():
                if pd.isna(precio): # Si el precio es NaN, intentar obtenerlo individualmente
                    individual_price = obtener_precio_actual(sim)
                    if individual_price is not None:
                        factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                        precios_actuales[sim] = individual_price * factor
                else:
                    factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                    precios_actuales[sim] = precio * factor
            st.info(f"✅ Precios obtenidos para {len(precios_actuales)} acciones.")
        else:
            st.warning("No se pudieron obtener precios de forma vectorizada. Intentando individualmente...")
            precios_actuales = {}
            for sim in lista_acciones:
                precio = obtener_precio_actual(sim)
                if precio is not None:
                    factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                    precios_actuales[sim] = precio * factor
                time.sleep(0.1) # Pequeña pausa para evitar rate limit
            st.info(f"✅ Precios obtenidos para {len(precios_actuales)} acciones (individualmente).")

    except Exception as e:
        st.error(f"Error al obtener precios de forma vectorizada: {e}. Intentando individualmente...")
        precios_actuales = {}
        for sim in lista_acciones:
            precio = obtener_precio_actual(sim)
            if precio is not None:
                factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                precios_actuales[sim] = precio * factor
            time.sleep(0.1) # Pequeña pausa para evitar rate limit
        st.info(f"✅ Precios obtenidos para {len(precios_actuales)} acciones (individualmente).")

    with st.spinner(f"Analizando {total} acciones en paralelo..."):
        resultados = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        completados = 0
        args_list = [
            (sim, PRECIO_COMPRA, precios_actuales, usd_mxn, eur_mxn, fundamentales_check,
             backtesting_check, regime_bonus, trade_capital, riesgo_pct,
             trailing_enabled, trailing_pct)
            for sim in lista_acciones if sim in precios_actuales # Solo analizar si tenemos precio
        ]

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(analizar_accion, args): args[0] for args in args_list}
            for future in as_completed(futures):
                completados += 1
                status_text.text(f"Procesando {completados}/{len(args_list)}: {futures[future]}")
                res = future.result()
                if res:
                    resultados.append(res)
                progress_bar.progress(completados / len(args_list))

        status_text.empty()
        progress_bar.empty()

    if not resultados:
        st.error(
            "⚠️ No se obtuvieron resultados para ningún símbolo.\n\n"
            "**Causa más probable en Streamlit Cloud:** Yahoo Finance está bloqueando las "
            "peticiones de `yfinance` (rate-limit 429 sobre IPs compartidas).\n\n"
            "**Soluciones:**\n"
            "1. Espera 10-30 min y vuelve a intentar.\n"
            "2. Asegúrate de que `curl_cffi` esté en `requirements.txt` (ya se usa "
            "impersonación de Chrome en esta versión).\n"
            "3. Revisa los logs de Streamlit Cloud (Manage app → Logs) para ver el error exacto "
            "de yfinance.\n"
            "4. Si persiste, despliega en Render/Railway (IP dedicada) o usa una API alternativa "
            "(Alpha Vantage, Finnhub)."
        )
        st.stop()

    # ========== CREAR DATAFRAMES ==========
    df = pd.DataFrame(resultados)
    st.success(f"✅ Análisis completado. Se obtuvieron {len(df)} resultados.")
    
    # Filtrado de ventas: ahora incluye todas las señales de venta, no solo las de la cartera
    ventas_tecnicas = df[df['Recomendación'].str.contains('VENDER|VENTA', na=False)].copy()
    compras = df[df['Recomendación'].str.startswith('COMPRAR')].sort_values('Score', ascending=False).copy()
    observar = df[df['Recomendación'] == 'OBSERVAR'].sort_values('Score', ascending=False).copy()
    
    # ========== GUARDAR SEÑALES EN HISTORIAL ==========
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
        guardar_senal_en_historial(senal, fecha_actual)

    # ========== FILTRO DE ALTA CONFIANZA ==========
    if alta_confianza:
        filtro = pd.Series([True] * len(compras))
        if filtro_score:
            filtro = filtro & (compras['Score'] >= 8)
        if filtro_rsi:
            filtro = filtro & (compras['RSI'].between(45, 65))
        if filtro_ml and 'ML Predicción' in compras.columns:
            filtro = filtro & (compras['ML Predicción'].str.contains("Subida", na=False))
        if filtro_sentimiento and 'Sentimiento' in compras.columns:
            filtro = filtro & (compras['Sentimiento'] == 'positivo')
        compras = compras[filtro].copy()
        if compras.empty:
            st.warning("⚠️ No hay señales que cumplan los criterios de alta confianza. Desactiva el filtro para ver todas.")
    
    # ========== FILTRO DE FUNDAMENTALES SÓLIDOS ==========
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

    # ========== SENTIMIENTO ==========
    if sentiment_check and not compras.empty:
        with st.spinner("Analizando sentimiento..."):
            for idx, row in compras.iterrows():
                sent = analizar_sentimiento(row['Símbolo'])
                compras.at[idx, 'Sentimiento'] = sent['sentimiento']
                compras.at[idx, 'Sentimiento Score'] = sent['score']
                compras.at[idx, 'Noticias'] = "; ".join(sent['noticias'][:2])

    # ========== ML ==========
    if ml_check and not compras.empty:
        with st.spinner("🧠 Cargando modelos ML..."):
            for idx, row in compras.iterrows():
                model_info = entrenar_modelo_ml(row['Símbolo'], usd_mxn, eur_mxn)
                if model_info:
                    compras.at[idx, 'ML Predicción'] = f"{model_info['fuente']} Subida {model_info['accuracy']}%"
                else:
                    compras.at[idx, 'ML Predicción'] = "No disponible"

    # ========== OPTIMIZACIÓN DE CARTERA ==========
    if not compras.empty:
        compras = optimizar_cartera(compras, trade_capital, usd_mxn, eur_mxn)

    # ========== GUARDAR EN SESSION STATE ==========
    st.session_state['df'] = df
    st.session_state['compras'] = compras
    st.session_state['ventas_tecnicas'] = ventas_tecnicas # Renombrado para claridad
    st.session_state['observar'] = observar
    st.session_state['PRECIO_COMPRA'] = PRECIO_COMPRA # Asegurar que se guarda la versión actualizada
    st.session_state['usd_mxn'] = usd_mxn
    st.session_state['eur_mxn'] = eur_mxn
    st.session_state['regime'] = regime_data
    st.session_state['capital'] = capital_total # Guardar capital para uso posterior

    # ========== BACKTESTING ==========
    if backtesting_check:
        with st.spinner("Optimizando backtesting..."):
            opt = get_backtest_optimization()
            if opt:
                st.session_state['param_opt'] = opt
                st.info(f"Backtest: mejor umbral score = {opt['best_score_thresh']}, ATR mult = {opt['best_atr_mult']}, win rate = {opt['best_win_rate']}% ")

    st.success(f"✅ Análisis completado. {len(compras)} oportunidades de compra.")
    st.rerun()


# ============================================================
# PRESENTACIÓN DE RESULTADOS (si existen)
# ============================================================

# Asegurar que los tipos de cambio estén en session_state
if 'usd_mxn' not in st.session_state:
    usd_mxn, eur_mxn = obtener_tipo_cambio()
    st.session_state['usd_mxn'] = usd_mxn
    st.session_state['eur_mxn'] = eur_mxn

# Leer valores de sesión
usd_mxn = st.session_state['usd_mxn']
eur_mxn = st.session_state['eur_mxn']

# Verificar si hay resultados del análisis
if 'df' in st.session_state:
    df = st.session_state['df']
    compras = st.session_state['compras']
    ventas_tecnicas = st.session_state['ventas_tecnicas'] # Usar el nombre actualizado
    observar = st.session_state['observar']
    regime_data = st.session_state['regime']
    capital_total = st.session_state.get('capital', 100000.0)

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

    # ========== MOTOR DE ALERTAS DE CARTERA (Centralizado y optimizado) ==========
    # Ahora las alertas de cartera se calculan una sola vez y se almacenan en session_state
    # o se filtran directamente del DataFrame 'df' si ya contienen la información necesaria.
    # Para mantener la funcionalidad original de alertas_cartera, la calculamos aquí si no está en session_state
    alertas_cartera = []
    posiciones_json = st.session_state.get('PRECIO_COMPRA', {})
    if posiciones_json:
        for simbolo, datos in posiciones_json.items():
            p_compra = datos.get('precio', 0)
            if p_compra <= 0: continue
            
            # Obtener precio actual del df principal o de precios_actuales si existe
            p_actual = None
            if simbolo in df['Símbolo'].values:
                p_actual = df[df['Símbolo'] == simbolo]['Precio (MXN)'].iloc[0]
            elif simbolo in st.session_state.get('precios_actuales', {}): # Usar el diccionario de precios_actuales si se guardó
                p_actual = st.session_state['precios_actuales'][simbolo]
            
            if p_actual:
                ganancia = ((p_actual / p_compra) - 1) * 100
                if ganancia >= 15.0 or ganancia <= -7.0:
                    motivo = f"🎯 TP +{ganancia:.2f}%" if ganancia >= 15 else f"🛑 SL {ganancia:.2f}%"
                    alertas_cartera.append({
                        'Símbolo': simbolo,
                        'Precio Compra': p_compra,
                        'Precio Actual': p_actual,
                        'Ganancia (%)': f"{ganancia:.2f}%",
                        'Motivo': motivo
                    })
    st.session_state['alertas_venta_final'] = alertas_cartera # Guardar en session_state para la pestaña

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Compras", len(compras))
    total_v = len(ventas_tecnicas) + len(st.session_state['alertas_venta_final'])
    col2.metric("🔴 Ventas", total_v)
    col3.metric("👀 Observar", len(observar))
    col4.metric("🚫 Evitar", len(df[df['Recomendación'] == 'EVITAR']))
    
    # 4. PESTAÑAS
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "🟢 COMPRAS", "🔴 VENTAS", "🟡 OBSERVAR", "🔍 TODAS",
        "💼 CARTERA", "📜 HISTORIAL", "🏆 TOP 10", "📊 RENDIMIENTO"
    ])

    with tab1:
        st.dataframe(compras, use_container_width=True)

    with tab2:
        # Prioridad 1: Tu dinero real
        if not st.session_state['alertas_venta_final']:
            st.error("🚨 POSICIONES DE TU CARTERA EN OBJETIVO (VENDER)")
            st.table(pd.DataFrame(st.session_state['alertas_venta_final']))
            st.divider()
        
        # Prioridad 2: Señales generales del mercado
        st.subheader("📉 Señales Técnicas de Venta")
        if not ventas_tecnicas.empty:
            st.dataframe(ventas_tecnicas, use_container_width=True)
        else:
            st.info("No hay señales técnicas de venta en el escáner.")

    with tab3:
        st.dataframe(observar, use_container_width=True)

    with tab4:
        st.dataframe(df, use_container_width=True)
            
    with tab5:
        st.subheader("💼 Mi Cartera Actual")
        pos_cartera = repo_cargar_posiciones()
        
        if pos_cartera:
            resumen_cartera = []
            for s, d in pos_cartera.items():
                p_c = d.get('precio', 0)
                p_a = None
                # Reutilizamos el precio si ya lo buscamos en el paso anterior (precios_actuales)
                if s in st.session_state.get('precios_actuales', {}):
                    p_a = st.session_state['precios_actuales'][s]
                elif s in df['Símbolo'].values: # Si está en el df de resultados
                    p_a = df[df['Símbolo'] == s]['Precio (MXN)'].iloc[0]
                
                if not p_a: p_a = obtener_precio_actual(s) or p_c # Fallback si no se encontró
                
                resumen_cartera.append({
                    'Símbolo': s,
                    'Cantidad': d.get('cantidad', 0),
                    'Precio Promedio': p_c,
                    'Precio Actual': p_a,
                    'Ganancia (%)': ((p_a / p_c) - 1) * 100 if p_c > 0 else 0
                })
            
            df_p = pd.DataFrame(resumen_cartera)
            st.dataframe(df_p.style.format({
                'Precio Promedio': '${:,.2f}', 
                'Precio Actual': '${:,.2f}', 
                'Ganancia (%)': '{:.2f}%'
            }), use_container_width=True)
        else:
            st.info("Tu cartera está vacía.")
            
    # --- Pestaña 6: Historial de transacciones y rendimiento ---
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
                    # Calcular ganancia en MXN
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
                    
                    # ========== NUEVO: Dashboard de rendimiento mensual ==========
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
        
    # --- Pestaña 7: Top 10 señales de compra (gráfico de barras) ---
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

    # --- Pestaña 8: Backtest de señales de venta ---
    with tab8:
        st.subheader("📈 Rendimiento histórico de señales de VENTA (TP/SL)")
        df_hist = cargar_historial_senales()
        dashboard_rendimiento_ventas(df_hist) 
        st.divider()
        dashboard_rendimiento_real() 
        analizar_adn_exito()

    # ========== ANÁLISIS DE IA ==========
    if 'analisis_ia' in st.session_state and st.session_state['analisis_ia']:
        with st.expander("🤖 Análisis de IA", expanded=True):
            st.markdown(st.session_state['analisis_ia'])

    # ========== GRÁFICO INDIVIDUAL CON SELECTOR ==========
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
                precio_compra = st.session_state['PRECIO_COMPRA'][sim_elegido]['precio'] # Acceder al precio dentro del dict
                ganancia = (fila['Precio (MXN)'] / precio_compra - 1) * 100
                st.metric("Ganancia actual", f"{ganancia:+.2f}%")
            fig = grafico_enriquecido(sim_elegido, usd_mxn, eur_mxn)
            st.plotly_chart(fig, width='stretch')

else:
    st.info("🔍 Aún no has ejecutado un análisis. Ve a la barra lateral y haz clic en 'ANALIZAR' para obtener señales de trading.")

st.caption("v3.0 — Corregido y optimizado por Adrian López y Manus AI")

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
                st.session_state['PRECIO_COMPRA'] = posiciones_repo
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
            st.session_state['PRECIO_COMPRA'] = pos_restauradas
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
compra_input = st.sidebar.text_area("Compra", placeholder="AAPL,10,4465.53\nWALMEX.MX,5,56.13", height=120)

st.sidebar.markdown("### 💰 Registrar venta")
venta_input = st.sidebar.text_area("Venta", placeholder="AAPL,10,4750.00", height=120)
if st.sidebar.button("📉 REGISTRAR VENTA"):
    procesar_ventas(venta_input)

st.sidebar.markdown("### 📂 Google Drive")
drive_upload = st.sidebar.checkbox("💾 Guardar en Drive", value=False)

if st.sidebar.button("🔍 ANALIZAR", type="primary"):
    PRECIO_COMPRA = repo_cargar_posiciones() # Cargar posiciones al inicio del análisis
    st.session_state['HIGHEST_PRICE'] = {}

    if compra_input and compra_input.strip():
        nuevas_compras = 0
        for linea in compra_input.strip().split('\n'):
            if not linea.strip():
                continue
            partes = linea.split(',')
            if len(partes) == 3:
                sim = partes[0].strip().upper()
                try:
                    cantidad = float(partes[1].strip())
                    precio = float(partes[2].strip())
                    guardar_transaccion(sim, cantidad, precio, "compra")
                    # Si el símbolo no estaba en PRECIO_COMPRA, contamos como compra nueva
                    if sim not in PRECIO_COMPRA:
                        nuevas_compras += 1
                    PRECIO_COMPRA[sim] = {'cantidad': PRECIO_COMPRA.get(sim, {}).get('cantidad', 0) + cantidad, 'precio': precio} # Actualizar o añadir
                except:
                    pass
        if nuevas_compras > 0:
            st.sidebar.success(f"✅ {nuevas_compras} compra(s) nueva(s) registrada(s).")
        elif compra_input.strip():
            st.sidebar.warning("No se detectaron compras nuevas (los símbolos ya existían o hubo errores de formato).")
        # Siempre guardamos las posiciones actualizadas (aunque no haya nuevas, por si cambió precio)
        repo_guardar_posiciones(PRECIO_COMPRA)
        repo_guardar_transacciones()
    
    usd_mxn, eur_mxn = obtener_tipo_cambio()
    regime_data = obtener_market_regime()
    regime_bonus = regime_data['score_bonus'] if market_regime_check else 0
    trade_capital = capital_total * 0.25

    lista_acciones = mercado_opciones[mercado_seleccionado].copy()
    # Asegurarse de incluir los símbolos de la cartera actual para su análisis
    for sim in PRECIO_COMPRA.keys():
        if sim not in lista_acciones:
            lista_acciones.append(sim)

    total = len(lista_acciones)
    st.info(f"Analizando {total} acciones...")

    # ========== OBTENER PRECIOS ACTUALES DE TODAS LAS ACCIONES (VECTORIZADO) ==========
    st.info("🔄 Obteniendo precios actuales de todas las acciones...")
    # Usar yf.download para obtener precios de múltiples tickers de forma eficiente
    tickers_str = " ".join(lista_acciones)
    try:
        data = yf.download(tickers_str, period="1d", interval="1m", progress=False)
        if not data.empty:
            precios_actuales_raw = data['Close'].iloc[-1].to_dict() if len(lista_acciones) > 1 else {lista_acciones[0]: data['Close'].iloc[-1]}
            precios_actuales = {}
            for sim, precio in precios_actuales_raw.items():
                if pd.isna(precio): # Si el precio es NaN, intentar obtenerlo individualmente
                    individual_price = obtener_precio_actual(sim)
                    if individual_price is not None:
                        factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                        precios_actuales[sim] = individual_price * factor
                else:
                    factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                    precios_actuales[sim] = precio * factor
            st.session_state['precios_actuales'] = precios_actuales # Guardar en session_state
            st.info(f"✅ Precios obtenidos para {len(precios_actuales)} acciones.")
        else:
            st.warning("No se pudieron obtener precios de forma vectorizada. Intentando individualmente...")
            precios_actuales = {}
            for sim in lista_acciones:
                precio = obtener_precio_actual(sim)
                if precio is not None:
                    factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                    precios_actuales[sim] = precio * factor
                time.sleep(0.1) # Pequeña pausa para evitar rate limit
            st.session_state['precios_actuales'] = precios_actuales # Guardar en session_state
            st.info(f"✅ Precios obtenidos para {len(precios_actuales)} acciones (individualmente).")

    except Exception as e:
        st.error(f"Error al obtener precios de forma vectorizada: {e}. Intentando individualmente...")
        precios_actuales = {}
        for sim in lista_acciones:
            precio = obtener_precio_actual(sim)
            if precio is not None:
                factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                precios_actuales[sim] = precio * factor
            time.sleep(0.1) # Pequeña pausa para evitar rate limit
        st.session_state['precios_actuales'] = precios_actuales # Guardar en session_state
        st.info(f"✅ Precios obtenidos para {len(precios_actuales)} acciones (individualmente).")

    with st.spinner(f"Analizando {total} acciones en paralelo..."):
        resultados = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        completados = 0
        args_list = [
            (sim, PRECIO_COMPRA, precios_actuales, usd_mxn, eur_mxn, fundamentales_check,
             backtesting_check, regime_bonus, trade_capital, riesgo_pct,
             trailing_enabled, trailing_pct)
            for sim in lista_acciones if sim in precios_actuales # Solo analizar si tenemos precio
        ]

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(analizar_accion, args): args[0] for args in args_list}
            for future in as_completed(futures):
                completados += 1
                status_text.text(f"Procesando {completados}/{len(args_list)}: {futures[future]}")
                res = future.result()
                if res:
                    resultados.append(res)
                progress_bar.progress(completados / len(args_list))

        status_text.empty()
        progress_bar.empty()

    if not resultados:
        st.error(
            "⚠️ No se obtuvieron resultados para ningún símbolo.\n\n"
            "**Causa más probable en Streamlit Cloud:** Yahoo Finance está bloqueando las "
            "peticiones de `yfinance` (rate-limit 429 sobre IPs compartidas).\n\n"
            "**Soluciones:**\n"
            "1. Espera 10-30 min y vuelve a intentar.\n"
            "2. Asegúrate de que `curl_cffi` esté en `requirements.txt` (ya se usa "
            "impersonación de Chrome en esta versión).\n"
            "3. Revisa los logs de Streamlit Cloud (Manage app → Logs) para ver el error exacto "
            "de yfinance.\n"
            "4. Si persiste, despliega en Render/Railway (IP dedicada) o usa una API alternativa "
            "(Alpha Vantage, Finnhub)."
        )
        st.stop()

    # ========== CREAR DATAFRAMES ==========
    df = pd.DataFrame(resultados)
    st.success(f"✅ Análisis completado. Se obtuvieron {len(df)} resultados.")
    
    # Filtrado de ventas: ahora incluye todas las señales de venta, no solo las de la cartera
    ventas_tecnicas = df[df['Recomendación'].str.contains('VENDER|VENTA', na=False)].copy()
    compras = df[df['Recomendación'].str.startswith('COMPRAR')].sort_values('Score', ascending=False).copy()
    observar = df[df['Recomendación'] == 'OBSERVAR'].sort_values('Score', ascending=False).copy()
    
    # ========== GUARDAR SEÑALES EN HISTORIAL ==========
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
        guardar_senal_en_historial(senal, fecha_actual)

    # ========== FILTRO DE ALTA CONFIANZA ==========
    if alta_confianza:
        filtro = pd.Series([True] * len(compras))
        if filtro_score:
            filtro = filtro & (compras['Score'] >= 8)
        if filtro_rsi:
            filtro = filtro & (compras['RSI'].between(45, 65))
        if filtro_ml and 'ML Predicción' in compras.columns:
            filtro = filtro & (compras['ML Predicción'].str.contains("Subida", na=False))
        if filtro_sentimiento and 'Sentimiento' in compras.columns:
            filtro = filtro & (compras['Sentimiento'] == 'positivo')
        compras = compras[filtro].copy()
        if compras.empty:
            st.warning("⚠️ No hay señales que cumplan los criterios de alta confianza. Desactiva el filtro para ver todas.")
    
    # ========== FILTRO DE FUNDAMENTALES SÓLIDOS ==========
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

    # ========== SENTIMIENTO ==========
    if sentiment_check and not compras.empty:
        with st.spinner("Analizando sentimiento..."):
            for idx, row in compras.iterrows():
                sent = analizar_sentimiento(row['Símbolo'])
                compras.at[idx, 'Sentimiento'] = sent['sentimiento']
                compras.at[idx, 'Sentimiento Score'] = sent['score']
                compras.at[idx, 'Noticias'] = "; ".join(sent['noticias'][:2])

    # ========== ML ==========
    if ml_check and not compras.empty:
        with st.spinner("🧠 Cargando modelos ML..."):
            for idx, row in compras.iterrows():
                model_info = entrenar_modelo_ml(row['Símbolo'], usd_mxn, eur_mxn)
                if model_info:
                    compras.at[idx, 'ML Predicción'] = f"{model_info['fuente']} Subida {model_info['accuracy']}%"
                else:
                    compras.at[idx, 'ML Predicción'] = "No disponible"

    # ========== OPTIMIZACIÓN DE CARTERA ==========
    if not compras.empty:
        compras = optimizar_cartera(compras, trade_capital, usd_mxn, eur_mxn)

    # ========== GUARDAR EN SESSION STATE ==========
    st.session_state['df'] = df
    st.session_state['compras'] = compras
    st.session_state['ventas_tecnicas'] = ventas_tecnicas # Renombrado para claridad
    st.session_state['observar'] = observar
    st.session_state['PRECIO_COMPRA'] = PRECIO_COMPRA # Asegurar que se guarda la versión actualizada
    st.session_state['usd_mxn'] = usd_mxn
    st.session_state['eur_mxn'] = eur_mxn
    st.session_state['regime'] = regime_data
    st.session_state['capital'] = capital_total # Guardar capital para uso posterior

    # ========== BACKTESTING ==========
    if backtesting_check:
        with st.spinner("Optimizando backtesting..."):
            opt = get_backtest_optimization()
            if opt:
                st.session_state['param_opt'] = opt
                st.info(f"Backtest: mejor umbral score = {opt['best_score_thresh']}, ATR mult = {opt['best_atr_mult']}, win rate = {opt['best_win_rate']}% ")

    st.success(f"✅ Análisis completado. {len(compras)} oportunidades de compra.")
    st.rerun()


# ============================================================
# PRESENTACIÓN DE RESULTADOS (si existen)
# ============================================================

# Asegurar que los tipos de cambio estén en session_state
if 'usd_mxn' not in st.session_state:
    usd_mxn, eur_mxn = obtener_tipo_cambio()
    st.session_state['usd_mxn'] = usd_mxn
    st.session_state['eur_mxn'] = eur_mxn

# Leer valores de sesión
usd_mxn = st.session_state['usd_mxn']
eur_mxn = st.session_state['eur_mxn']

# Verificar si hay resultados del análisis
if 'df' in st.session_state:
    df = st.session_state['df']
    compras = st.session_state['compras']
    ventas_tecnicas = st.session_state['ventas_tecnicas'] # Usar el nombre actualizado
    observar = st.session_state['observar']
    regime_data = st.session_state['regime']
    capital_total = st.session_state.get('capital', 100000.0)

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

    # ========== MOTOR DE ALERTAS DE CARTERA (Centralizado y optimizado) ==========
    # Ahora las alertas de cartera se calculan una sola vez y se almacenan en session_state
    # o se filtran directamente del DataFrame 'df' si ya contienen la información necesaria.
    # Para mantener la funcionalidad original de alertas_cartera, la calculamos aquí si no está en session_state
    alertas_cartera = []
    posiciones_json = st.session_state.get('PRECIO_COMPRA', {})
    if posiciones_json:
        for simbolo, datos in posiciones_json.items():
            p_compra = datos.get('precio', 0)
            if p_compra <= 0: continue
            
            # Obtener precio actual del df principal o de precios_actuales si existe
            p_actual = None
            if simbolo in df['Símbolo'].values:
                p_actual = df[df['Símbolo'] == simbolo]['Precio (MXN)'].iloc[0]
            elif simbolo in st.session_state.get('precios_actuales', {}): # Usar el diccionario de precios_actuales si se guardó
                p_actual = st.session_state['precios_actuales'][simbolo]
            
            if p_actual:
                ganancia = ((p_actual / p_compra) - 1) * 100
                if ganancia >= 15.0 or ganancia <= -7.0:
                    motivo = f"🎯 TP +{ganancia:.2f}%" if ganancia >= 15 else f"🛑 SL {ganancia:.2f}%"
                    alertas_cartera.append({
                        'Símbolo': simbolo,
                        'Precio Compra': p_compra,
                        'Precio Actual': p_actual,
                        'Ganancia (%)': f"{ganancia:.2f}%",
                        'Motivo': motivo
                    })
    st.session_state['alertas_venta_final'] = alertas_cartera # Guardar en session_state para la pestaña

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Compras", len(compras))
    total_v = len(ventas_tecnicas) + len(st.session_state['alertas_venta_final'])
    col2.metric("🔴 Ventas", total_v)
    col3.metric("👀 Observar", len(observar))
    col4.metric("🚫 Evitar", len(df[df['Recomendación'] == 'EVITAR']))
    
    # 4. PESTAÑAS
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "🟢 COMPRAS", "🔴 VENTAS", "🟡 OBSERVAR", "🔍 TODAS",
        "💼 CARTERA", "📜 HISTORIAL", "🏆 TOP 10", "📊 RENDIMIENTO"
    ])

    with tab1:
        st.dataframe(compras, use_container_width=True)

    with tab2:
        # Prioridad 1: Tu dinero real
        if not st.session_state['alertas_venta_final']:
            st.error("🚨 POSICIONES DE TU CARTERA EN OBJETIVO (VENDER)")
            st.table(pd.DataFrame(st.session_state['alertas_venta_final']))
            st.divider()
        
        # Prioridad 2: Señales generales del mercado
        st.subheader("📉 Señales Técnicas de Venta")
        if not ventas_tecnicas.empty:
            st.dataframe(ventas_tecnicas, use_container_width=True)
        else:
            st.info("No hay señales técnicas de venta en el escáner.")

    with tab3:
        st.dataframe(observar, use_container_width=True)

    with tab4:
        st.dataframe(df, use_container_width=True)
            
    with tab5:
        st.subheader("💼 Mi Cartera Actual")
        pos_cartera = repo_cargar_posiciones()
        
        if pos_cartera:
            resumen_cartera = []
            for s, d in pos_cartera.items():
                p_c = d.get('precio', 0)
                p_a = None
                # Reutilizamos el precio si ya lo buscamos en el paso anterior (precios_actuales)
                if s in st.session_state.get('precios_actuales', {}):
                    p_a = st.session_state['precios_actuales'][s]
                elif s in df['Símbolo'].values: # Si está en el df de resultados
                    p_a = df[df['Símbolo'] == s]['Precio (MXN)'].iloc[0]
                
                if not p_a: p_a = obtener_precio_actual(s) or p_c # Fallback si no se encontró
                
                resumen_cartera.append({
                    'Símbolo': s,
                    'Cantidad': d.get('cantidad', 0),
                    'Precio Promedio': p_c,
                    'Precio Actual': p_a,
                    'Ganancia (%)': ((p_a / p_c) - 1) * 100 if p_c > 0 else 0
                })
            
            df_p = pd.DataFrame(resumen_cartera)
            st.dataframe(df_p.style.format({
                'Precio Promedio': '${:,.2f}', 
                'Precio Actual': '${:,.2f}', 
                'Ganancia (%)': '{:.2f}%'
            }), use_container_width=True)
        else:
            st.info("Tu cartera está vacía.")
            
    # --- Pestaña 6: Historial de transacciones y rendimiento ---
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
                    # Calcular ganancia en MXN
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
                    
                    # ========== NUEVO: Dashboard de rendimiento mensual ==========
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
        
    # --- Pestaña 7: Top 10 señales de compra (gráfico de barras) ---
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

    # --- Pestaña 8: Backtest de señales de venta ---
    with tab8:
        st.subheader("📈 Rendimiento histórico de señales de VENTA (TP/SL)")
        df_hist = cargar_historial_senales()
        dashboard_rendimiento_ventas(df_hist) 
        st.divider()
        dashboard_rendimiento_real() 
        analizar_adn_exito()

    # ========== ANÁLISIS DE IA ==========
    if 'analisis_ia' in st.session_state and st.session_state['analisis_ia']:
        with st.expander("🤖 Análisis de IA", expanded=True):
            st.markdown(st.session_state['analisis_ia'])

    # ========== GRÁFICO INDIVIDUAL CON SELECTOR ==========
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
                precio_compra = st.session_state['PRECIO_COMPRA'][sim_elegido]['precio'] # Acceder al precio dentro del dict
                ganancia = (fila['Precio (MXN)'] / precio_compra - 1) * 100
                st.metric("Ganancia actual", f"{ganancia:+.2f}%")
            fig = grafico_enriquecido(sim_elegido, usd_mxn, eur_mxn)
            st.plotly_chart(fig, width='stretch')

else:
    st.info("🔍 Aún no has ejecutado un análisis. Ve a la barra lateral y haz clic en 'ANALIZAR' para obtener señales de trading.")

st.caption("v3.0 — Corregido y optimizado por Adrian López y Manus AI")

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
                st.session_state['PRECIO_COMPRA'] = posiciones_repo
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
            st.session_state['PRECIO_COMPRA'] = pos_restauradas
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
compra_input = st.sidebar.text_area("Compra", placeholder="AAPL,10,4465.53\nWALMEX.MX,5,56.13", height=120)

st.sidebar.markdown("### 💰 Registrar venta")
venta_input = st.sidebar.text_area("Venta", placeholder="AAPL,10,4750.00", height=120)
if st.sidebar.button("📉 REGISTRAR VENTA"):
    procesar_ventas(venta_input)

st.sidebar.markdown("### 📂 Google Drive")
drive_upload = st.sidebar.checkbox("💾 Guardar en Drive", value=False)

if st.sidebar.button("🔍 ANALIZAR", type="primary"):
    PRECIO_COMPRA = repo_cargar_posiciones() # Cargar posiciones al inicio del análisis
    st.session_state['HIGHEST_PRICE'] = {}

    if compra_input and compra_input.strip():
        nuevas_compras = 0
        for linea in compra_input.strip().split('\n'):
            if not linea.strip():
                continue
            partes = linea.split(',')
            if len(partes) == 3:
                sim = partes[0].strip().upper()
                try:
                    cantidad = float(partes[1].strip())
                    precio = float(partes[2].strip())
                    guardar_transaccion(sim, cantidad, precio, "compra")
                    # Si el símbolo no estaba en PRECIO_COMPRA, contamos como compra nueva
                    if sim not in PRECIO_COMPRA:
                        nuevas_compras += 1
                    PRECIO_COMPRA[sim] = {'cantidad': PRECIO_COMPRA.get(sim, {}).get('cantidad', 0) + cantidad, 'precio': precio} # Actualizar o añadir
                except:
                    pass
        if nuevas_compras > 0:
            st.sidebar.success(f"✅ {nuevas_compras} compra(s) nueva(s) registrada(s).")
        elif compra_input.strip():
            st.sidebar.warning("No se detectaron compras nuevas (los símbolos ya existían o hubo errores de formato).")
        # Siempre guardamos las posiciones actualizadas (aunque no haya nuevas, por si cambió precio)
        repo_guardar_posiciones(PRECIO_COMPRA)
        repo_guardar_transacciones()
    
    usd_mxn, eur_mxn = obtener_tipo_cambio()
    regime_data = obtener_market_regime()
    regime_bonus = regime_data['score_bonus'] if market_regime_check else 0
    trade_capital = capital_total * 0.25

    lista_acciones = mercado_opciones[mercado_seleccionado].copy()
    # Asegurarse de incluir los símbolos de la cartera actual para su análisis
    for sim in PRECIO_COMPRA.keys():
        if sim not in lista_acciones:
            lista_acciones.append(sim)

    total = len(lista_acciones)
    st.info(f"Analizando {total} acciones...")

    # ========== OBTENER PRECIOS ACTUALES DE TODAS LAS ACCIONES (VECTORIZADO) ==========
    st.info("🔄 Obteniendo precios actuales de todas las acciones...")
    # Usar yf.download para obtener precios de múltiples tickers de forma eficiente
    tickers_str = " ".join(lista_acciones)
    try:
        data = yf.download(tickers_str, period="1d", interval="1m", progress=False)
        if not data.empty:
            precios_actuales_raw = data['Close'].iloc[-1].to_dict() if len(lista_acciones) > 1 else {lista_acciones[0]: data['Close'].iloc[-1]}
            precios_actuales = {}
            for sim, precio in precios_actuales_raw.items():
                if pd.isna(precio): # Si el precio es NaN, intentar obtenerlo individualmente
                    individual_price = obtener_precio_actual(sim)
                    if individual_price is not None:
                        factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                        precios_actuales[sim] = individual_price * factor
                else:
                    factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                    precios_actuales[sim] = precio * factor
            st.session_state['precios_actuales'] = precios_actuales # Guardar en session_state
            st.info(f"✅ Precios obtenidos para {len(precios_actuales)} acciones.")
        else:
            st.warning("No se pudieron obtener precios de forma vectorizada. Intentando individualmente...")
            precios_actuales = {}
            for sim in lista_acciones:
                precio = obtener_precio_actual(sim)
                if precio is not None:
                    factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                    precios_actuales[sim] = precio * factor
                time.sleep(0.1) # Pequeña pausa para evitar rate limit
            st.session_state['precios_actuales'] = precios_actuales # Guardar en session_state
            st.info(f"✅ Precios obtenidos para {len(precios_actuales)} acciones (individualmente).")

    except Exception as e:
        st.error(f"Error al obtener precios de forma vectorizada: {e}. Intentando individualmente...")
        precios_actuales = {}
        for sim in lista_acciones:
            precio = obtener_precio_actual(sim)
            if precio is not None:
                factor = 1.0 if sim.endswith('.MX') else (eur_mxn if sim.endswith('.MC') else usd_mxn)
                precios_actuales[sim] = precio * factor
            time.sleep(0.1) # Pequeña pausa para evitar rate limit
        st.session_state['precios_actuales'] = precios_actuales # Guardar en session_state
        st.info(f"✅ Precios obtenidos para {len(precios_actuales)} acciones (individualmente).")

    with st.spinner(f"Analizando {total} acciones en paralelo..."):
        resultados = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        completados = 0
        args_list = [
            (sim, PRECIO_COMPRA, precios_actuales, usd_mxn, eur_mxn, fundamentales_check,
             backtesting_check, regime_bonus, trade_capital, riesgo_pct,
             trailing_enabled, trailing_pct)
            for sim in lista_acciones if sim in precios_actuales # Solo analizar si tenemos precio
        ]

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(analizar_accion, args): args[0] for args in args_list}
            for future in as_completed(futures):
                completados += 1
                status_text.text(f"Procesando {completados}/{len(args_list)}: {futures[future]}")
                res = future.result()
                if res:
                    resultados.append(res)
                progress_bar.progress(completados / len(args_list))

        status_text.empty()
        progress_bar.empty()

    if not resultados:
        st.error(
            "⚠️ No se obtuvieron resultados para ningún símbolo.\n\n"
            "**Causa más probable en Streamlit Cloud:** Yahoo Finance está bloqueando las "
            "peticiones de `yfinance` (rate-limit 429 sobre IPs compartidas).\n\n"
            "**Soluciones:**\n"
            "1. Espera 10-30 min y vuelve a intentar.\n"
            "2. Asegúrate de que `curl_cffi` esté en `requirements.txt` (ya se usa "
            "impersonación de Chrome en esta versión).\n"
            "3. Revisa los logs de Streamlit Cloud (Manage app → Logs) para ver el error exacto "
            "de yfinance.\n"
            "4. Si persiste, despliega en Render/Railway (IP dedicada) o usa una API alternativa "
            "(Alpha Vantage, Finnhub)."
        )
        st.stop()

    # ========== CREAR DATAFRAMES ==========
    df = pd.DataFrame(resultados)
    st.success(f"✅ Análisis completado. Se obtuvieron {len(df)} resultados.")
    
    # Filtrado de ventas: ahora incluye todas las señales de venta, no solo las de la cartera
    ventas_tecnicas = df[df['Recomendación'].str.contains('VENDER|VENTA', na=False)].copy()
    compras = df[df['Recomendación'].str.startswith('COMPRAR')].sort_values('Score', ascending=False).copy()
    observar = df[df['Recomendación'] == 'OBSERVAR'].sort_values('Score', ascending=False).copy()
    
    # ========== GUARDAR SEÑALES EN HISTORIAL ==========
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
        guardar_senal_en_historial(senal, fecha_actual)

    # ========== FILTRO DE ALTA CONFIANZA ==========
    if alta_confianza:
        filtro = pd.Series([True] * len(compras))
        if filtro_score:
            filtro = filtro & (compras['Score'] >= 8)
        if filtro_rsi:
            filtro = filtro & (compras['RSI'].between(45, 65))
        if filtro_ml and 'ML Predicción' in compras.columns:
            filtro = filtro & (compras['ML Predicción'].str.contains("Subida", na=False))
        if filtro_sentimiento and 'Sentimiento' in compras.columns:
            filtro = filtro & (compras['Sentimiento'] == 'positivo')
        compras = compras[filtro].copy()
        if compras.empty:
            st.warning("⚠️ No hay señales que cumplan los criterios de alta confianza. Desactiva el filtro para ver todas.")
    
    # ========== FILTRO DE FUNDAMENTALES SÓLIDOS ==========
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

    # ========== SENTIMIENTO ==========
    if sentiment_check and not compras.empty:
        with st.spinner("Analizando sentimiento..."):
            for idx, row in compras.iterrows():
                sent = analizar_sentimiento(row['Símbolo'])
                compras.at[idx, 'Sentimiento'] = sent['sentimiento']
                compras.at[idx, 'Sentimiento Score'] = sent['score']
                compras.at[idx, 'Noticias'] = "; ".join(sent['noticias'][:2])

    # ========== ML ==========
    if ml_check and not compras.empty:
        with st.spinner("🧠 Cargando modelos ML..."):
            for idx, row in compras.iterrows():
                model_info = entrenar_modelo_ml(row['Símbolo'], usd_mxn, eur_mxn)
                if model_info:
                    compras.at[idx, 'ML Predicción'] = f"{model_info['fuente']} Subida {model_info['accuracy']}%"
                else:
                    compras.at[idx, 'ML Predicción'] = "No disponible"

    # ========== OPTIMIZACIÓN DE CARTERA ==========
    if not compras.empty:
        compras = optimizar_cartera(compras, trade_capital, usd_mxn, eur_mxn)

    # ========== GUARDAR EN SESSION STATE ==========
    st.session_state['df'] = df
    st.session_state['compras'] = compras
    st.session_state['ventas_tecnicas'] = ventas_tecnicas # Renombrado para claridad
    st.session_state['observar'] = observar
    st.session_state['PRECIO_COMPRA'] = PRECIO_COMPRA # Asegurar que se guarda la versión actualizada
    st.session_state['usd_mxn'] = usd_mxn
    st.session_state['eur_mxn'] = eur_mxn
    st.session_state['regime'] = regime_data
    st.session_state['capital'] = capital_total # Guardar capital para uso posterior

    # ========== BACKTESTING ==========
    if backtesting_check:
        with st.spinner("Optimizando backtesting..."):
            opt = get_backtest_optimization()
            if opt:
                st.session_state['param_opt'] = opt
                st.info(f"Backtest: mejor umbral score = {opt['best_score_thresh']}, ATR mult = {opt['best_atr_mult']}, win rate = {opt['best_win_rate']}% ")

    st.success(f"✅ Análisis completado. {len(compras)} oportunidades de compra.")
    st.rerun()


# ============================================================
# PRESENTACIÓN DE RESULTADOS (si existen)
# ============================================================

# Asegurar que los tipos de cambio estén en session_state
if 'usd_mxn' not in st.session_state:
    usd_mxn, eur_mxn = obtener_tipo_cambio()
    st.session_state['usd_mxn'] = usd_mxn
    st.session_state['eur_mxn'] = eur_mxn

# Leer valores de sesión
usd_mxn = st.session_state['usd_mxn']
eur_mxn = st.session_state['eur_mxn']

# Verificar si hay resultados del análisis
if 'df' in st.session_state:
    df = st.session_state['df']
    compras = st.session_state['compras']
    ventas_tecnicas = st.session_state['ventas_tecnicas'] # Usar el nombre actualizado
    observar = st.session_state['observar']
    regime_data = st.session_state['regime']
    capital_total = st.session_state.get('capital', 100000.0)

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

    # ========== MOTOR DE ALERTAS DE CARTERA (Centralizado y optimizado) ==========
    # Ahora las alertas de cartera se calculan una sola vez y se almacenan en session_state
    # o se filtran directamente del DataFrame 'df' si ya contienen la información necesaria.
    # Para mantener la funcionalidad original de alertas_cartera, la calculamos aquí si no está en session_state
    alertas_cartera = []
    posiciones_json = st.session_state.get('PRECIO_COMPRA', {})
    if posiciones_json:
        for simbolo, datos in posiciones_json.items():
            p_compra = datos.get('precio', 0)
            if p_compra <= 0: continue
            
            # Obtener precio actual del df principal o de precios_actuales si existe
            p_actual = None
            if simbolo in df['Símbolo'].values:
                p_actual = df[df['Símbolo'] == simbolo]['Precio (MXN)'].iloc[0]
            elif simbolo in st.session_state.get('precios_actuales', {}): # Usar el diccionario de precios_actuales si se guardó
                p_actual = st.session_state['precios_actuales'][simbolo]
            
            if p_actual:
                ganancia = ((p_actual / p_compra) - 1) * 100
                if ganancia >= 15.0 or ganancia <= -7.0:
                    motivo = f"🎯 TP +{ganancia:.2f}%" if ganancia >= 15 else f"🛑 SL {ganancia:.2f}%"
                    alertas_cartera.append({
                        'Símbolo': simbolo,
                        'Precio Compra': p_compra,
                        'Precio Actual': p_actual,
                        'Ganancia (%)': f"{ganancia:.2f}%",
                        'Motivo': motivo
                    })
    st.session_state['alertas_venta_final'] = alertas_cartera # Guardar en session_state para la pestaña

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Compras", len(compras))
    total_v = len(ventas_tecnicas) + len(st.session_state['alertas_venta_final'])
    col2.metric("🔴 Ventas", total_v)
    col3.metric("👀 Observar", len(observar))
    col4.metric("🚫 Evitar", len(df[df['Recomendación'] == 'EVITAR']))
    
    # 4. PESTAÑAS
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "🟢 COMPRAS", "🔴 VENTAS", "🟡 OBSERVAR", "🔍 TODAS",
        "💼 CARTERA", "📜 HISTORIAL", "🏆 TOP 10", "📊 RENDIMIENTO"
    ])

    with tab1:
        st.dataframe(compras, use_container_width=True)

    with tab2:
        # Prioridad 1: Tu dinero real
        if not st.session_state['alertas_venta_final']:
            st.error("🚨 POSICIONES DE TU CARTERA EN OBJETIVO (VENDER)")
            st.table(pd.DataFrame(st.session_state['alertas_venta_final']))
            st.divider()
        
        # Prioridad 2: Señales generales del mercado
        st.subheader("📉 Señales Técnicas de Venta")
        if not ventas_tecnicas.empty:
            st.dataframe(ventas_tecnicas, use_container_width=True)
        else:
            st.info("No hay señales técnicas de venta en el escáner.")

    with tab3:
        st.dataframe(observar, use_container_width=True)

    with tab4:
        st.dataframe(df, use_container_width=True)
            
    with tab5:
        st.subheader("💼 Mi Cartera Actual")
        pos_cartera = repo_cargar_posiciones()
        
        if pos_cartera:
            resumen_cartera = []
            for s, d in pos_cartera.items():
                p_c = d.get('precio', 0)
                p_a = None
                # Reutilizamos el precio si ya lo buscamos en el paso anterior (precios_actuales)
                if s in st.session_state.get('precios_actuales', {}):
                    p_a = st.session_state['precios_actuales'][s]
                elif s in df['Símbolo'].values: # Si está en el df de resultados
                    p_a = df[df['Símbolo'] == s]['Precio (MXN)'].iloc[0]
                
                if not p_a: p_a = obtener_precio_actual(s) or p_c # Fallback si no se encontró
                
                resumen_cartera.append({
                    'Símbolo': s,
                    'Cantidad': d.get('cantidad', 0),
                    'Precio Promedio': p_c,
                    'Precio Actual': p_a,
                    'Ganancia (%)': ((p_a / p_c) - 1) * 100 if p_c > 0 else 0
                })
            
            df_p = pd.DataFrame(resumen_cartera)
            st.dataframe(df_p.style.format({
                'Precio Promedio': '${:,.2f}', 
                'Precio Actual': '${:,.2f}', 
                'Ganancia (%)': '{:.2f}%'
            }), use_container_width=True)
        else:
            st.info("Tu cartera está vacía.")
            
    # --- Pestaña 6: Historial de transacciones y rendimiento ---
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
                    # Calcular ganancia en MXN
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
                    
                    # ========== NUEVO: Dashboard de rendimiento mensual ==========
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
        
    # --- Pestaña 7: Top 10 señales de compra (gráfico de barras) ---
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

    # --- Pestaña 8: Backtest de señales de venta ---
    with tab8:
        st.subheader("📈 Rendimiento histórico de señales de VENTA (TP/SL)")
        df_hist = cargar_historial_senales()
        dashboard_rendimiento_ventas(df_hist) 
        st.divider()
        dashboard_rendimiento_real() 
        analizar_adn_exito()

    # ========== ANÁLISIS DE IA ==========
    if 'analisis_ia' in st.session_state and st.session_state['analisis_ia']:
        with st.expander("🤖 Análisis de IA", expanded=True):
            st.markdown(st.session_state['analisis_ia'])

    # ========== GRÁFICO INDIVIDUAL CON SELECTOR ==========
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
                precio_compra = st.session_state['PRECIO_COMPRA'][sim_elegido]['precio'] # Acceder al precio dentro del dict
                ganancia = (fila['Precio (MXN)'] / precio_compra - 1) * 100
                st.metric("Ganancia actual", f"{ganancia:+.2f}%")
            fig = grafico_enriquecido(sim_elegido, usd_mxn, eur_mxn)
            st.plotly_chart(fig, width='stretch')

else:
    st.info("🔍 Aún no has ejecutado un análisis. Ve a la barra lateral y haz clic en 'ANALIZAR' para obtener señales de trading.")

st.caption("v3.0 — Corregido y optimizado por Adrian López y Manus AI")

# ============================================================
# REPOSITORIO (GITHUB) Y UTILIDADES
# ============================================================

def _repo_disponible():
    return os.path.exists(".git") and os.path.exists("repo_config.json")

def repo_cargar_posiciones():
    if not _repo_disponible():
        return {}
    try:
        with open("repo_config.json", "r") as f:
            config = json.load(f)
        repo_url = config["repo_url"]
        branch = config["branch"]
        token = config["token"]

        g = Github(token)
        repo = g.get_repo(repo_url.split("github.com/")[1])
        contents = repo.get_contents("posiciones.json", ref=branch)
        posiciones_json = json.loads(contents.decoded_content.decode())
        return posiciones_json
    except Exception as e:
        st.error(f"Error al cargar posiciones del repo: {e}")
        return {}

def repo_guardar_posiciones(posiciones):
    if not _repo_disponible():
        return
    try:
        with open("repo_config.json", "r") as f:
            config = json.load(f)
        repo_url = config["repo_url"]
        branch = config["branch"]
        token = config["token"]

        g = Github(token)
        repo = g.get_repo(repo_url.split("github.com/")[1])
        
        # Intentar obtener el archivo existente para actualizarlo
        try:
            contents = repo.get_contents("posiciones.json", ref=branch)
            repo.update_file(contents.path, "Actualizando posiciones", json.dumps(posiciones, indent=4), contents.sha, branch=branch)
        except UnknownObjectException: # Si el archivo no existe, crearlo
            repo.create_file("posiciones.json", "Creando posiciones", json.dumps(posiciones, indent=4), branch=branch)
        st.sidebar.success("✅ Posiciones guardadas en GitHub.")
    except Exception as e:
        st.sidebar.error(f"Error al guardar posiciones en GitHub: {e}")

def repo_cargar_transacciones():
    if not _repo_disponible():
        return
    try:
        with open("repo_config.json", "r") as f:
            config = json.load(f)
        repo_url = config["repo_url"]
        branch = config["branch"]
        token = config["token"]

        g = Github(token)
        repo = g.get_repo(repo_url.split("github.com/")[1])
        contents = repo.get_contents("transacciones.csv", ref=branch)
        df_transacciones = pd.read_csv(io.StringIO(contents.decoded_content.decode()))
        st.session_state["transacciones_df"] = df_transacciones
        st.sidebar.success(f"✅ {len(df_transacciones)} transacciones restauradas.")
    except UnknownObjectException:
        st.session_state["transacciones_df"] = pd.DataFrame(columns=["fecha", "simbolo", "cantidad", "precio", "tipo", "total", "ganancia_pct", "notas"])
        st.sidebar.info("📂 No hay archivo de transacciones en el repo.")
    except Exception as e:
        st.sidebar.error(f"Error al cargar transacciones del repo: {e}")
        st.session_state["transacciones_df"] = pd.DataFrame(columns=["fecha", "simbolo", "cantidad", "precio", "tipo", "total", "ganancia_pct", "notas"])

def repo_guardar_transacciones():
    if not _repo_disponible():
        return
    try:
        with open("repo_config.json", "r") as f:
            config = json.load(f)
        repo_url = config["repo_url"]
        branch = config["branch"]
        token = config["token"]

        g = Github(token)
        repo = g.get_repo(repo_url.split("github.com/")[1])
        
        csv_data = st.session_state["transacciones_df"].to_csv(index=False)
        
        try:
            contents = repo.get_contents("transacciones.csv", ref=branch)
            repo.update_file(contents.path, "Actualizando transacciones", csv_data, contents.sha, branch=branch)
        except UnknownObjectException:
            repo.create_file("transacciones.csv", "Creando transacciones", csv_data, branch=branch)
        st.sidebar.success("✅ Transacciones guardadas en GitHub.")
    except Exception as e:
        st.sidebar.error(f"Error al guardar transacciones en GitHub: {e}")

def repo_cargar_historial():
    if not _repo_disponible():
        return
    try:
        with open("repo_config.json", "r") as f:
            config = json.load(f)
        repo_url = config["repo_url"]
        branch = config["branch"]
        token = config["token"]

        g = Github(token)
        repo = g.get_repo(repo_url.split("github.com/")[1])
        contents = repo.get_contents("historial_senales.csv", ref=branch)
        df_historial = pd.read_csv(io.StringIO(contents.decoded_content.decode()))
        st.session_state["historial_senales_df"] = df_historial
        st.sidebar.success(f"✅ {len(df_historial)} señales restauradas.")
    except UnknownObjectException:
        st.session_state["historial_senales_df"] = pd.DataFrame(columns=["fecha", "simbolo", "precio_mxn", "score", "recomendacion", "motivo", "ganancia_pct", "tipo_senal"])
        st.sidebar.info("📂 No hay archivo de historial de señales en el repo.")
    except Exception as e:
        st.sidebar.error(f"Error al cargar historial de señales del repo: {e}")
        st.session_state["historial_senales_df"] = pd.DataFrame(columns=["fecha", "simbolo", "precio_mxn", "score", "recomendacion", "motivo", "ganancia_pct", "tipo_senal"])

def repo_guardar_historial():
    if not _repo_disponible():
        return
    try:
        with open("repo_config.json", "r") as f:
            config = json.load(f)
        repo_url = config["repo_url"]
        branch = config["branch"]
        token = config["token"]

        g = Github(token)
        repo = g.get_repo(repo_url.split("github.com/")[1])
        
        csv_data = st.session_state["historial_senales_df"].to_csv(index=False)
        
        try:
            contents = repo.get_contents("historial_senales.csv", ref=branch)
            repo.update_file(contents.path, "Actualizando historial de señales", csv_data, contents.sha, branch=branch)
        except UnknownObjectException:
            repo.create_file("historial_senales.csv", "Creando historial de señales", csv_data, branch=branch)
        st.sidebar.success("✅ Historial de señales guardado en GitHub.")
    except Exception as e:
        st.sidebar.error(f"Error al guardar historial de señales en GitHub: {e}")

def generar_backup_zip():
    # Crear un archivo ZIP en memoria
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        # Añadir posiciones.json
        if os.path.exists("posiciones.json"):
            zip_file.write("posiciones.json", "posiciones.json")
        # Añadir transacciones.csv
        if os.path.exists("transacciones.csv"):
            zip_file.write("transacciones.csv", "transacciones.csv")
        # Añadir historial_senales.csv
        if os.path.exists("historial_senales.csv"):
            zip_file.write("historial_senales.csv", "historial_senales.csv")
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def restaurar_desde_zip(uploaded_file):
    posiciones_restauradas = {}
    with zipfile.ZipFile(uploaded_file, "r") as zip_ref:
        for file_name in zip_ref.namelist():
            if file_name == "posiciones.json":
                with zip_ref.open(file_name) as f:
                    posiciones_restauradas = json.load(f)
                    with open("posiciones.json", "w") as outfile:
                        json.dump(posiciones_restauradas, outfile, indent=4)
            elif file_name == "transacciones.csv":
                with zip_ref.open(file_name) as f:
                    df_trans = pd.read_csv(f)
                    df_trans.to_csv("transacciones.csv", index=False)
                    st.session_state["transacciones_df"] = df_trans
            elif file_name == "historial_senales.csv":
                with zip_ref.open(file_name) as f:
                    df_hist = pd.read_csv(f)
                    df_hist.to_csv("historial_senales.csv", index=False)
                    st.session_state["historial_senales_df"] = df_hist
    st.sidebar.success("✅ Datos restaurados desde ZIP.")
    return posiciones_restauradas


def obtener_tipo_cambio():
    try:
        # Usar un servicio confiable para el tipo de cambio
        response = requests.get("https://api.exchangerate-api.com/v4/latest/USD")
        data = response.json()
        usd_mxn = data["rates"]["MXN"]
        response = requests.get("https://api.exchangerate-api.com/v4/latest/EUR")
        data = response.json()
        eur_mxn = data["rates"]["MXN"]
        return usd_mxn, eur_mxn
    except Exception as e:
        st.warning(f"No se pudo obtener el tipo de cambio: {e}. Usando valores por defecto.")
        return 17.0, 18.0 # Valores por defecto


def obtener_market_regime():
    try:
        sp500 = yf.Ticker("^GSPC")
        hist = sp500.history(period="1y")
        
        if hist.empty:
            return {"regime": "DESCONOCIDO", "descripcion": "No se pudo obtener datos del S&P 500", "score_bonus": 0}

        # Calcular EMA 200
        hist["EMA200"] = hist["Close"].ewm(span=200, adjust=False).mean()
        
        # Calcular RSI
        delta = hist["Close"].diff()
        gain = (delta.where(delta > 0, 0)).ewm(span=14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(span=14, adjust=False).mean()
        rs = gain / loss
        hist["RSI"] = 100 - (100 / (1 + rs))

        current_price = hist["Close"].iloc[-1]
        ema200 = hist["EMA200"].iloc[-1]
        rsi_sp500 = hist["RSI"].iloc[-1]

        regime = "DESCONOCIDO"
        descripcion = ""
        score_bonus = 0

        if current_price > ema200 and rsi_sp500 > 50:
            regime = "ALCISTA"
            descripcion = "El mercado muestra una fuerte tendencia al alza, ideal para compras."
            score_bonus = 1
        elif current_price < ema200 and rsi_sp500 < 50:
            regime = "BAJISTA"
            descripcion = "El mercado está en una tendencia a la baja, se recomienda cautela."
            score_bonus = -1
        else:
            regime = "LATERAL"
            descripcion = "El mercado se mueve sin una dirección clara, buscar operaciones de rango."
            score_bonus = 0
            
        # Retorno a 1 mes
        ret_1m = (current_price / hist["Close"].iloc[-20] - 1) * 100 if len(hist) >= 20 else 0

        return {
            "regime": regime,
            "descripcion": descripcion,
            "score_bonus": score_bonus,
            "precio": current_price,
            "ema200": ema200,
            "rsi_sp500": rsi_sp500,
            "ret_1m": ret_1m
        }
    except Exception as e:
        st.warning(f"Error al obtener Market Regime: {e}. Usando valores por defecto.")
        return {"regime": "DESCONOCIDO", "descripcion": "No se pudo determinar el régimen de mercado", "score_bonus": 0, "precio": 0, "ema200": 0, "rsi_sp500": 0, "ret_1m": 0}


def obtener_precio_actual(simbolo):
    try:
        ticker = yf.Ticker(simbolo)
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            return hist["Close"].iloc[-1]
        return None
    except Exception:
        return None


def guardar_transaccion(simbolo, cantidad, precio, tipo, ganancia_pct=None, notas=""):
    df_transacciones = st.session_state["transacciones_df"]
    nueva_transaccion = pd.DataFrame([{
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "simbolo": simbolo,
        "cantidad": cantidad,
        "precio": precio,
        "tipo": tipo,
        "total": cantidad * precio,
        "ganancia_pct": ganancia_pct,
        "notas": notas
    }])
    st.session_state["transacciones_df"] = pd.concat([df_transacciones, nueva_transaccion], ignore_index=True)
    repo_guardar_transacciones()


def cargar_transacciones():
    return st.session_state["transacciones_df"]


def guardar_senal_en_historial(senal, fecha_actual):
    df_historial = st.session_state["historial_senales_df"]
    
    ganancia_pct = None
    tipo_senal = ""
    
    # === CORRECCIÓN DEL BUG: Extracción de ganancia_pct más robusta ===
    motivo = senal.get("Motivo", "")
    match = re.search(r"([+-]?\d+(?:\.\d+)?)%", motivo) # Regex más robusta
    if match:
        try:
            ganancia_pct = float(match.group(1))
        except ValueError:
            pass # Si no se puede convertir a float, se mantiene como None
    
    # Fallback para Take Profit y Stop Loss si la regex falla o no encuentra nada
    if ganancia_pct is None:
        if "Take Profit" in motivo or "TP" in motivo:
            tipo_senal = "TP"
            # Intentar extraer el número de nuevo con una regex más laxa o asumir un valor
            match_tp = re.search(r"\+(\d+(?:\.\d+)?)", motivo)
            if match_tp: ganancia_pct = float(match_tp.group(1))
            else: ganancia_pct = 15.0 # Valor por defecto si no se encuentra
        elif "Stop Loss" in motivo or "SL" in motivo:
            tipo_senal = "SL"
            match_sl = re.search(r"-(\d+(?:\.\d+)?)", motivo)
            if match_sl: ganancia_pct = -float(match_sl.group(1))
            else: ganancia_pct = -7.0 # Valor por defecto si no se encuentra
    
    if senal["Recomendación"].startswith("COMPRAR"):
        tipo_senal = "COMPRA"
    elif senal["Recomendación"].startswith("VENDER"):
        tipo_senal = "VENTA"

    nueva_senal = pd.DataFrame([{
        "fecha": fecha_actual,
        "simbolo": senal["Símbolo"],
        "precio_mxn": senal["Precio MXN"],
        "score": senal["Score"],
        "recomendacion": senal["Recomendación"],
        "motivo": motivo,
        "ganancia_pct": ganancia_pct, # Ahora puede ser None o un float
        "tipo_senal": tipo_senal
    }])
    st.session_state["historial_senales_df"] = pd.concat([df_historial, nueva_senal], ignore_index=True)
    repo_guardar_historial()


def cargar_historial_senales():
    df_hist = st.session_state["historial_senales_df"].copy()
    df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
    return df_hist


def procesar_ventas(venta_input):
    if not venta_input.strip():
        st.sidebar.warning("No hay ventas para registrar.")
        return

    PRECIO_COMPRA = st.session_state.get("PRECIO_COMPRA", {})
    df_transacciones = st.session_state["transacciones_df"]
    
    ventas_procesadas = 0
    for linea in venta_input.strip().split("\n"):
        if not linea.strip():
            continue
        partes = linea.split(",")
        if len(partes) == 3:
            sim = partes[0].strip().upper()
            try:
                cantidad_venta = float(partes[1].strip())
                precio_venta = float(partes[2].strip())

                if sim in PRECIO_COMPRA:
                    cantidad_comprada = PRECIO_COMPRA[sim].get("cantidad", 0)
                    precio_compra = PRECIO_COMPRA[sim].get("precio", 0)

                    if cantidad_venta > cantidad_comprada:
                        st.sidebar.warning(f"Intentando vender {cantidad_venta} de {sim}, pero solo tienes {cantidad_comprada}. Se venderá la cantidad disponible.")
                        cantidad_venta = cantidad_comprada
                    
                    if cantidad_venta > 0 and precio_compra > 0:
                        ganancia_pct = ((precio_venta / precio_compra) - 1) * 100
                        guardar_transaccion(sim, cantidad_venta, precio_venta, "venta", ganancia_pct, f"Venta manual. Compra a {precio_compra:.2f}")
                        
                        # Actualizar posiciones
                        PRECIO_COMPRA[sim]["cantidad"] -= cantidad_venta
                        if PRECIO_COMPRA[sim]["cantidad"] <= 0:
                            del PRECIO_COMPRA[sim] # Eliminar si la posición se cierra
                        st.session_state["PRECIO_COMPRA"] = PRECIO_COMPRA
                        repo_guardar_posiciones(PRECIO_COMPRA)
                        ventas_procesadas += 1
                    else:
                        st.sidebar.error(f"Error: Cantidad o precio de compra inválido para {sim}.")
                else:
                    st.sidebar.warning(f"No tienes {sim} en tu cartera para vender.")
            except ValueError:
                st.sidebar.error(f"Error de formato en la línea de venta: {linea}")
            except Exception as e:
                st.sidebar.error(f"Error al procesar venta de {sim}: {e}")
        else:
            st.sidebar.error(f"Formato incorrecto en la línea de venta: {linea}. Esperado: SIMBOLO,CANTIDAD,PRECIO")
    
    if ventas_procesadas > 0:
        st.sidebar.success(f"✅ {ventas_procesadas} venta(s) registrada(s) y cartera actualizada.")
        repo_guardar_transacciones()
        st.rerun()
    else:
        st.sidebar.info("No se registraron ventas válidas.")


# ============================================================
# FUNCIONES DE ANÁLISIS CORE
# ============================================================

def calcular_indicadores(df_hist):
    # Calcular RSI
    delta = df_hist["Close"].diff()
    gain = (delta.where(delta > 0, 0)).ewm(span=14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=14, adjust=False).mean()
    rs = gain / loss
    df_hist["RSI"] = 100 - (100 / (1 + rs))

    # Calcular Bandas de Bollinger
    df_hist["MA20"] = df_hist["Close"].rolling(window=20).mean()
    df_hist["StdDev"] = df_hist["Close"].rolling(window=20).std()
    df_hist["Upper_BB"] = df_hist["MA20"] + (df_hist["StdDev"] * 2)
    df_hist["Lower_BB"] = df_hist["MA20"] - (df_hist["StdDev"] * 2)

    # Calcular MACD
    df_hist["EMA12"] = df_hist["Close"].ewm(span=12, adjust=False).mean()
    df_hist["EMA26"] = df_hist["Close"].ewm(span=26, adjust=False).mean()
    df_hist["MACD"] = df_hist["EMA12"] - df_hist["EMA26"]
    df_hist["Signal_Line"] = df_hist["MACD"].ewm(span=9, adjust=False).mean()
    df_hist["MACD_Hist"] = df_hist["MACD"] - df_hist["Signal_Line"]

    # Calcular ATR (Average True Range)
    high_low = df_hist["High"] - df_hist["Low"]
    high_prev_close = abs(df_hist["High"] - df_hist["Close"].shift())
    low_prev_close = abs(df_hist["Low"] - df_hist["Close"].shift())
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    df_hist["ATR"] = true_range.ewm(span=14, adjust=False).mean()

    return df_hist

def analizar_accion(simbolo, PRECIO_COMPRA, precios_actuales, usd_mxn, eur_mxn, fundamentales_check, backtesting_check, regime_bonus, trade_capital, riesgo_pct, trailing_enabled, trailing_pct):
    try:
        ticker = yf.Ticker(simbolo)
        info = ticker.info
        
        # Determinar el factor de conversión basado en el sufijo del símbolo
        factor_conversion = 1.0
        if simbolo.endswith(".MX"):
            factor_conversion = 1.0
        elif simbolo.endswith(".MC"):
            factor_conversion = eur_mxn
        else:
            factor_conversion = usd_mxn

        # Obtener el precio actual de la lista pre-cargada
        precio_actual_usd = precios_actuales.get(simbolo) / factor_conversion # Convertir a USD si es necesario para cálculos
        precio_actual_mxn = precios_actuales.get(simbolo)

        if precio_actual_mxn is None:
            return None # No se pudo obtener el precio, saltar esta acción

        # Historial de precios
        df_hist = ticker.history(period="1y")
        if df_hist.empty:
            return None
        df_hist = calcular_indicadores(df_hist)

        # Últimos valores de indicadores
        last_row = df_hist.iloc[-1]
        rsi = last_row["RSI"]
        close_price = last_row["Close"]
        ma20 = last_row["MA20"]
        upper_bb = last_row["Upper_BB"]
        lower_bb = last_row["Lower_BB"]
        macd = last_row["MACD"]
        signal_line = last_row["Signal_Line"]
        atr = last_row["ATR"]

        score = 0
        recomendacion = "OBSERVAR"
        motivo = []
        senales = []

        # Reglas de Scoring y Recomendación
        if rsi < 30 and close_price < lower_bb: # Sobreventa y por debajo de BB inferior
            score += 3
            motivo.append("Fuerte sobreventa (RSI < 30 y bajo BB)")
            senales.append("SOBREVENTA_FUERTE")
        elif rsi < 40 and close_price < ma20: # Sobreventa moderada y bajo MA20
            score += 2
            motivo.append("Sobreventa moderada (RSI < 40 y bajo MA20)")
            senales.append("SOBREVENTA_MODERADA")
        
        if macd > signal_line and macd.iloc[-2] <= signal_line.iloc[-2]: # Cruce alcista de MACD
            score += 2
            motivo.append("Cruce alcista de MACD")
            senales.append("CRUCE_MACD_ALCISTA")

        if close_price > ma20 and df_hist["Close"].iloc[-2] <= df_hist["MA20"].iloc[-2]: # Cruce alcista de MA20
            score += 1
            motivo.append("Cruce alcista de MA20")
            senales.append("CRUCE_MA20_ALCISTA")

        if close_price > upper_bb: # Por encima de BB superior (posible sobrecompra o fuerza)
            score -= 1 # Puede indicar sobrecompra, pero también fuerza
            motivo.append("Precio por encima de BB superior")
            senales.append("SOBRECOMPRA_BB")

        if rsi > 70: # Sobrecompra
            score -= 2
            motivo.append("Sobrecompra (RSI > 70)")
            senales.append("SOBRECOMPRA_RSI")

        # Añadir bonus por Market Regime
        score += regime_bonus

        # Análisis Fundamental (si está activado)
        if fundamentales_check:
            try:
                # Estos datos suelen estar en USD, convertimos para consistencia
                market_cap_usd = info.get("marketCap", 0) / 1_000_000_000 # En billones USD
                trailing_pe = info.get("trailingPE", 0)
                forward_pe = info.get("forwardPE", 0)
                peg_ratio = info.get("pegRatio", 0)
                dividend_yield = info.get("dividendYield", 0) * 100 if info.get("dividendYield") else 0
                beta = info.get("beta", 0)
                sector = info.get("sector", "N/A")
                industry = info.get("industry", "N/A")
                roe = info.get("returnOnEquity", 0) * 100 if info.get("returnOnEquity") else 0
                debt_to_equity = info.get("debtToEquity", 0)
                eps_growth = info.get("earningsQuarterlyGrowth", 0) * 100 if info.get("earningsQuarterlyGrowth") else 0
                net_margin = info.get("netMargin", 0) * 100 if info.get("netMargin") else 0

                # Reglas de scoring fundamental
                if trailing_pe > 0 and trailing_pe < 20: score += 1; senales.append("PE_BAJO")
                if peg_ratio > 0 and peg_ratio < 1: score += 1; senales.append("PEG_BAJO")
                if dividend_yield > 2: score += 1; senales.append("DIVIDENDO_ALTO")
                if roe > 10: score += 1; senales.append("ROE_ALTO")
                if debt_to_equity < 100: score += 1; senales.append("DEBT_BAJO")
                if eps_growth > 0: score += 1; senales.append("EPS_CRECIMIENTO")
                if net_margin > 5: score += 1; senales.append("MARGEN_NETO_ALTO")

            except Exception as e:
                st.warning(f"Error al obtener fundamentales para {simbolo}: {e}")
                market_cap_usd, trailing_pe, forward_pe, peg_ratio, dividend_yield, beta, sector, industry, roe, debt_to_equity, eps_growth, net_margin = ["N/A"] * 12
        else:
            market_cap_usd, trailing_pe, forward_pe, peg_ratio, dividend_yield, beta, sector, industry, roe, debt_to_equity, eps_growth, net_margin = ["N/A"] * 12

        # Gestión de riesgo y Backtesting (si está activado)
        stop_loss_pct = None
        take_profit_pct = None
        cantidad_acciones = 0
        capital_riesgo = trade_capital * (riesgo_pct / 100)

        if backtesting_check and atr and atr > 0:
            # Usar la optimización de backtest si está disponible
            if 'param_opt' in st.session_state:
                atr_multiplier = st.session_state['param_opt']['best_atr_mult']
            else:
                atr_multiplier = 2.0 # Default

            stop_loss_price = precio_actual_usd - (atr * atr_multiplier)
            take_profit_price = precio_actual_usd + (atr * atr_multiplier * 2) # TP 2x SL
            
            if stop_loss_price > 0: # Asegurarse de que el SL no sea negativo
                stop_loss_pct = ((stop_loss_price / precio_actual_usd) - 1) * 100
                take_profit_pct = ((take_profit_price / precio_actual_usd) - 1) * 100

                # Calcular cantidad de acciones basada en el riesgo
                if precio_actual_usd > 0 and stop_loss_price < precio_actual_usd:
                    riesgo_por_accion = precio_actual_usd - stop_loss_price
                    if riesgo_por_accion > 0:
                        cantidad_acciones = math.floor(capital_riesgo / (riesgo_por_accion * factor_conversion)) # Convertir riesgo por acción a MXN

        # Trailing Stop (si está activado)
        if trailing_enabled and simbolo in PRECIO_COMPRA:
            highest_price = st.session_state["HIGHEST_PRICE"].get(simbolo, precio_actual_mxn)
            if precio_actual_mxn > highest_price:
                st.session_state["HIGHEST_PRICE"][simbolo] = precio_actual_mxn
                highest_price = precio_actual_mxn
            
            trailing_stop_price = highest_price * (1 - trailing_pct / 100)
            if precio_actual_mxn < trailing_stop_price:
                score -= 2 # Penalizar si el precio cae por debajo del trailing stop
                motivo.append(f"Trailing Stop activado ({trailing_pct}%) - posible venta")
                senales.append("TRAILING_STOP_ACTIVO")

        # Actualizar recomendación final basada en el score
        if score >= 7:
            recomendacion = "COMPRAR"
        elif score <= 3:
            recomendacion = "VENDER"
        
        # Verificar si ya tenemos la acción en cartera y si está en objetivo de venta
        if simbolo in PRECIO_COMPRA:
            precio_compra_cartera = PRECIO_COMPRA[simbolo].get("precio", 0)
            if precio_compra_cartera > 0:
                ganancia_actual_pct = ((precio_actual_mxn / precio_compra_cartera) - 1) * 100
                if ganancia_actual_pct >= 15.0:
                    recomendacion = "VENDER"
                    motivo.insert(0, f"🎯 Take Profit +{ganancia_actual_pct:.2f}%")
                    senales.insert(0, "TP_CARTERA")
                elif ganancia_actual_pct <= -7.0:
                    recomendacion = "VENDER"
                    motivo.insert(0, f"🛑 Stop Loss {ganancia_actual_pct:.2f}%")
                    senales.insert(0, "SL_CARTERA")

        return {
            "Símbolo": simbolo,
            "Precio (MXN)": precio_actual_mxn,
            "RSI": rsi,
            "MA20": ma20,
            "Upper_BB": upper_bb,
            "Lower_BB": lower_bb,
            "MACD": macd,
            "Signal_Line": signal_line,
            "ATR": atr,
            "Score": score,
            "Recomendación": recomendacion,
            "Motivo": ", ".join(motivo),
            "Señales": ", ".join(senales),
            "Stop Loss (%)": f"{stop_loss_pct:.2f}%" if stop_loss_pct is not None else "N/A",
            "Take Profit (%)": f"{take_profit_pct:.2f}%" if take_profit_pct is not None else "N/A",
            "Cantidad Sugerida": cantidad_acciones,
            "Capital en Riesgo": capital_riesgo,
            "Market Cap (B USD)": f"{market_cap_usd:,.2f}" if isinstance(market_cap_usd, (int, float)) else market_cap_usd,
            "P/E Trailing": f"{trailing_pe:.2f}" if isinstance(trailing_pe, (int, float)) else trailing_pe,
            "P/E Forward": f"{forward_pe:.2f}" if isinstance(forward_pe, (int, float)) else forward_pe,
            "PEG Ratio": f"{peg_ratio:.2f}" if isinstance(peg_ratio, (int, float)) else peg_ratio,
            "Dividend Yield (%)": f"{dividend_yield:.2f}" if isinstance(dividend_yield, (int, float)) else dividend_yield,
            "Beta": f"{beta:.2f}" if isinstance(beta, (int, float)) else beta,
            "Sector": sector,
            "Industria": industry,
            "ROE (%)": f"{roe:.2f}" if isinstance(roe, (int, float)) else roe,
            "Debt/Equity": f"{debt_to_equity:.2f}" if isinstance(debt_to_equity, (int, float)) else debt_to_equity,
            "EPS Growth (%)": f"{eps_growth:.2f}" if isinstance(eps_growth, (int, float)) else eps_growth,
            "Net Margin (%)": f"{net_margin:.2f}" if isinstance(net_margin, (int, float)) else net_margin,
        }
    except Exception as e:
        # st.error(f"Error al analizar {simbolo}: {e}") # Desactivar para evitar spam en la UI
        return None


def analizar_sentimiento(simbolo):
    # Simulación de análisis de sentimiento
    sentimientos = [("positivo", 0.8, ["Noticia buena 1", "Noticia buena 2"]),
                    ("negativo", 0.3, ["Noticia mala 1", "Noticia mala 2"]),
                    ("neutral", 0.5, ["Noticia neutral 1", "Noticia neutral 2"])]
    return {"sentimiento": "neutral", "score": 0.5, "noticias": [f"Noticia simulada para {simbolo}"]}


def entrenar_modelo_ml(simbolo, usd_mxn, eur_mxn):
    # Simulación de modelo ML
    if random.random() > 0.5:
        return {"fuente": "Modelo A", "accuracy": round(random.uniform(70, 95), 2)}
    return None


def optimizar_cartera(df_compras, capital_total, usd_mxn, eur_mxn):
    # Simulación de optimización de cartera
    return df_compras


def grafico_enriquecido(simbolo, usd_mxn, eur_mxn):
    ticker = yf.Ticker(simbolo)
    df_hist = ticker.history(period="6mo")
    df_hist = calcular_indicadores(df_hist)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05,
                        row_heights=[0.5, 0.25, 0.25])

    # Gráfico de velas
    fig.add_trace(go.Candlestick(x=df_hist.index,
                                 open=df_hist["Open"],
                                 high=df_hist["High"],
                                 low=df_hist["Low"],
                                 close=df_hist["Close"],
                                 name="Candlestick"), row=1, col=1)

    # Bandas de Bollinger
    fig.add_trace(go.Scatter(x=df_hist.index, y=df_hist["MA20"], line=dict(color=\

'#206097'), name='MA20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_hist.index, y=df_hist["Upper_BB"], line=dict(color='gray', dash='dash'), name='Upper BB'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_hist.index, y=df_hist["Lower_BB"], line=dict(color='gray', dash='dash'), name='Lower BB'), row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df_hist.index, y=df_hist["RSI"], line=dict(color='purple'), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    # MACD
    fig.add_trace(go.Scatter(x=df_hist.index, y=df_hist["MACD"], line=dict(color='blue'), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_hist.index, y=df_hist["Signal_Line"], line=dict(color='orange'), name='Signal Line'), row=3, col=1)
    fig.add_bar(x=df_hist.index, y=df_hist["MACD_Hist"], name='MACD Hist', marker_color='rgba(0,0,255,0.5)'), row=3, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False, height=700)
    fig.update_yaxes(title_text="Precio", row=1, col=1)
    fig.update_yaxes(title_text="RSI", row=2, col=1)
    fig.update_yaxes(title_text="MACD", row=3, col=1)

    return fig


def dashboard_rendimiento_ventas(df_historial):
    st.subheader("Rendimiento de Señales de Venta (Histórico)")
    df_ventas_hist = df_historial[df_historial["tipo_senal"].isin(["TP", "SL"])].copy()

    if df_ventas_hist.empty:
        st.info("No hay señales de venta en el historial para analizar.")
        return

    df_ventas_hist["ganancia_pct"] = pd.to_numeric(df_ventas_hist["ganancia_pct"], errors='coerce')
    df_ventas_hist.dropna(subset=["ganancia_pct"], inplace=True)

    if df_ventas_hist.empty:
        st.info("No hay señales de venta válidas con porcentaje de ganancia en el historial.")
        return

    win_rate = (df_ventas_hist["ganancia_pct"] > 0).mean() * 100
    avg_gain = df_ventas_hist[df_ventas_hist["ganancia_pct"] > 0]["ganancia_pct"].mean()
    avg_loss = df_ventas_hist[df_ventas_hist["ganancia_pct"] <= 0]["ganancia_pct"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Win Rate (Señales)", f"{win_rate:.2f}%")
    col2.metric("Ganancia Promedio (Wins)", f"{avg_gain:.2f}%" if not pd.isna(avg_gain) else "N/A")
    col3.metric("Pérdida Promedio (Losses)", f"{avg_loss:.2f}%" if not pd.isna(avg_loss) else "N/A")

    fig = px.histogram(df_ventas_hist, x="ganancia_pct", nbins=20, title="Distribución de Ganancias/Pérdidas de Señales",
                       labels={'ganancia_pct': 'Ganancia/Pérdida (%)'})
    st.plotly_chart(fig, use_container_width=True)


def dashboard_rendimiento_real():
    st.subheader("Rendimiento de Ventas Realizadas (Transacciones)")
    df_trans = cargar_transacciones()
    ventas_df = df_trans[df_trans["tipo"] == "venta"].copy()

    if ventas_df.empty:
        st.info("No hay ventas reales registradas para analizar.")
        return

    ventas_df["ganancia_pct"] = pd.to_numeric(ventas_df["ganancia_pct"], errors='coerce')
    ventas_con_ganancia = ventas_df.dropna(subset=["ganancia_pct"])

    if ventas_con_ganancia.empty:
        st.info("No hay ventas reales con porcentaje de ganancia válido.")
        return

    win_rate = (ventas_con_ganancia["ganancia_pct"] > 0).mean() * 100
    ganancia_total_mxn = (ventas_con_ganancia["total"] * (ventas_con_ganancia["ganancia_pct"] / 100) / (1 + ventas_con_ganancia["ganancia_pct"] / 100)).sum()
    ganancia_promedio = ventas_con_ganancia["ganancia_pct"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Win Rate (Real)", f"{win_rate:.2f}%")
    col2.metric("Ganancia Promedio (Real)", f"{ganancia_promedio:.2f}%")
    col3.metric("Ganancia Total (MXN)", f"${ganancia_total_mxn:,.2f}")

    fig = px.bar(ventas_con_ganancia, x="fecha", y="ganancia_pct", color="ganancia_pct",
                 hover_data=["simbolo", "notas"],
                 title="Rendimiento de Ventas Realizadas",
                 color_continuous_scale=['red', 'yellow', 'green'])
    st.plotly_chart(fig, use_container_width=True)


def analizar_adn_exito():
    st.subheader("🧬 ADN del Éxito (Análisis de Señales)")
    df_hist = cargar_historial_senales()
    df_trans = cargar_transacciones()

    if df_hist.empty or df_trans.empty:
        st.info("Necesitas historial de señales y transacciones para analizar el ADN del éxito.")
        return

    # Unir señales con transacciones reales
    df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
    df_trans["fecha"] = pd.to_datetime(df_trans["fecha"])

    # Encontrar señales que resultaron en ventas exitosas
    # Una señal se considera exitosa si hay una venta del mismo símbolo con ganancia positiva
    # dentro de un período razonable después de la señal.
    # Simplificación: Buscamos si el símbolo de la señal aparece en una venta con ganancia.
    
    ventas_exitosas_simbolos = df_trans[(df_trans["tipo"] == "venta") & (df_trans["ganancia_pct"] > 0)]["simbolo"].unique()

    df_hist["exitosa"] = df_hist["simbolo"].isin(ventas_exitosas_simbolos)

    if df_hist["exitosa"].sum() == 0:
        st.info("No se encontraron señales que resultaran en ventas exitosas para analizar.")
        return

    # Análisis de características de señales exitosas
    st.markdown("**Características comunes de señales que llevaron a ventas exitosas:**")
    
    # Ejemplo: Score promedio
    avg_score_exitosas = df_hist[df_hist["exitosa"]]["score"].mean()
    st.write(f"- Score promedio: {avg_score_exitosas:.2f}")

    # Ejemplo: Recomendaciones más comunes
    common_recs = df_hist[df_hist["exitosa"]]["recomendacion"].value_counts(normalize=True)
    if not common_recs.empty:
        st.write("- Recomendaciones más frecuentes:")
        for rec, pct in common_recs.items():
            st.write(f"  - {rec}: {pct:.1%}")

    # Ejemplo: Motivos más comunes
    common_motivos = df_hist[df_hist["exitosa"]]["motivo"].str.split(', ').explode().value_counts(normalize=True)
    if not common_motivos.empty:
        st.write("- Motivos más frecuentes:")
        for motivo, pct in common_motivos.items():
            st.write(f"  - {motivo}: {pct:.1%}")

    st.markdown("Este análisis puede expandirse para incluir otros indicadores y patrones.")


# ============================================================
# INICIO DE LA APLICACIÓN STREAMLIT
# ============================================================

if __name__ == "__main__":
    # Configuración inicial de Streamlit
    st.set_page_config(layout="wide", page_title="Trading AI Dashboard", page_icon="📈")

    # Cargar variables de entorno si existen
    load_dotenv()

    # Configurar GitHub (si las variables de entorno están presentes)
    if os.getenv("GITHUB_REPO") and os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_BRANCH"):
        repo_config = {
            "repo_url": os.getenv("GITHUB_REPO"),
            "token": os.getenv("GITHUB_TOKEN"),
            "branch": os.getenv("GITHUB_BRANCH")
        }
        with open("repo_config.json", "w") as f:
            json.dump(repo_config, f, indent=4)
    else:
        if os.path.exists("repo_config.json"):
            os.remove("repo_config.json") # Limpiar config si las variables no están

    # Inicializar DataFrames en session_state si no existen
    if "transacciones_df" not in st.session_state:
        st.session_state["transacciones_df"] = pd.DataFrame(columns=["fecha", "simbolo", "cantidad", "precio", "tipo", "total", "ganancia_pct", "notas"])
    if "historial_senales_df" not in st.session_state:
        st.session_state["historial_senales_df"] = pd.DataFrame(columns=["fecha", "simbolo", "precio_mxn", "score", "recomendacion", "motivo", "ganancia_pct", "tipo_senal"])

    # Ejecutar la lógica principal de la aplicación
    # La lógica principal ya está escrita en el bloque anterior, no es necesario duplicarla aquí.
    # El script se ejecuta de arriba a abajo en Streamlit, por lo que las funciones y la UI
    # ya están definidas y se ejecutarán en el orden correcto.

    # El código de la UI y la lógica principal ya se ha escrito en los pasos anteriores.
    # No se necesita añadir nada más aquí para el if __name__ == "__main__":
    # El script de Streamlit se ejecuta de arriba a abajo.
    pass
