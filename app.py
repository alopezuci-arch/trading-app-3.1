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
import urllib3
import ssl
import time
import os
import hashlib
import json
import pickle
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
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
GHU_GIST_TOKEN = os.environ.get("GHU_GIST_TOKEN", "")
REPO_OWNER     = "alopezuci-arch"
REPO_NAME      = "trading-app-3.1"
DATA_PATH      = "data"

# Archivos de persistencia (definidos aquí para evitar NameError en funciones posteriores)
TRANSACCIONES_FILE = "transacciones.csv"
HISTORIAL_FILE     = "historial_senales.csv"

# ============================================================
# PERSISTENCIA (mismo código que tenías, no cambio nada esencial)
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
        return repo_guardar_posiciones({})
    contenido = json.dumps({k.upper(): v for k, v in posiciones.items()}, indent=2, ensure_ascii=False)
    return _repo_escribir("posiciones.json", contenido, "actualizar posiciones")
def repo_cargar_transacciones() -> pd.DataFrame:
    cols = ['fecha','simbolo','cantidad','precio','tipo','total','notas','ganancia_pct']
    contenido = _repo_leer("transacciones.csv")
    
    # Eliminamos el len > 60 para que lea archivos aunque sean pequeños
    if contenido and contenido.strip():
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(contenido))
            
            # 1. Limpieza de nombres de columnas (quita espacios invisibles)
            df.columns = [c.strip() for c in df.columns]
            
            # 2. Aseguramos que la columna de ganancia exista y sea numérica
            if 'ganancia_pct' not in df.columns:
                df['ganancia_pct'] = np.nan
            else:
                df['ganancia_pct'] = pd.to_numeric(df['ganancia_pct'], errors='coerce')
            
            # 3. Convertimos la fecha forzando errores a NaT (Not a Time)
            df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
            
            # Guardamos copia local para consistencia del sistema
            df.to_csv(TRANSACCIONES_FILE, index=False)
            return df
        except Exception as e:
            st.error(f"Error procesando transacciones desde GitHub: {e}")
            
    return pd.DataFrame(columns=cols)

def repo_guardar_transacciones() -> bool:
    # Esta función se mantiene casi igual pero asegura la codificación correcta
    if not os.path.exists(TRANSACCIONES_FILE):
        return False
    try:
        with open(TRANSACCIONES_FILE, 'r', encoding='utf-8') as f:
            contenido = f.read()
        if not contenido.strip():
            return False
        return _repo_escribir("transacciones.csv", contenido, "sincronizar transacciones")
    except Exception as e:
        st.error(f"Error al subir a GitHub: {e}")
        return False
        
def repo_cargar_historial() -> pd.DataFrame:
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
    ruta = "historial_senales.csv"
    if not os.path.exists(ruta):
        return False
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            contenido = f.read()
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
        nombre = f"ml_{simbolo.replace('.','_')}.b64"
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
        nombre = f"ml_{simbolo.replace('.','_')}.b64"
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
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        posiciones = st.session_state.get('PRECIO_COMPRA', {})
        zf.writestr("posiciones.json", json.dumps(posiciones, indent=2, ensure_ascii=False))
        if os.path.exists(TRANSACCIONES_FILE):
            zf.write(TRANSACCIONES_FILE, "transacciones.csv")
        if os.path.exists("historial_senales.csv"):
            zf.write("historial_senales.csv", "historial_senales.csv")
        zf.writestr("LEEME.txt", f"Backup Trading App — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
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
        df = pd.read_csv(TRANSACCIONES_FILE)
        df['fecha'] = pd.to_datetime(df['fecha'])
        if 'ganancia_pct' not in df.columns:
            df['ganancia_pct'] = np.nan
        return df
    return pd.DataFrame(columns=['fecha','simbolo','cantidad','precio','tipo','total','notas','ganancia_pct'])
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

def procesar_ventas(input_text: str):
    if not input_text or not input_text.strip():
        st.sidebar.warning("No se ingresaron ventas.")
        return
    
    posiciones = repo_cargar_posiciones()
    ventas_registradas = 0
    
    for linea in input_text.strip().split('\n'):
        partes = linea.split(',')
        if len(partes) != 3: continue
        
        simbolo = partes[0].strip().upper()
        try:
            cant_vender = float(partes[1].strip())
            precio_venta = float(partes[2].strip())
        except: continue

        if simbolo in posiciones:
            pos = posiciones[simbolo]
            precio_compra_promedio = pos['precio']
            
            # Cálculo de ganancia real sobre el promedio
            ganancia_pct = ((precio_venta / precio_compra_promedio) - 1) * 100
            
            guardar_transaccion(simbolo, cant_vender, precio_venta, "venta", 
                               notas="Venta manual (PPP)", ganancia_pct=ganancia_pct)
            
            # Actualizamos o eliminamos la posición
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
        st.toast(f"✅ {ventas_registradas} ventas registradas", icon="💰")  # <--- línea opcional para más visibilidad
        time.sleep(1)  # Pequeña pausa para que el mensaje se vea antes del rerun
        st.rerun()


def procesar_compras_ppp(input_text: str):
    posiciones = repo_cargar_posiciones()
    compras_ok = 0
    
    for linea in input_text.strip().split('\n'):
        partes = linea.split(',')
        if len(partes) != 3: continue
        
        simbolo = partes[0].strip().upper()
        cant_nueva = float(partes[1].strip())
        precio_nuevo = float(partes[2].strip())
        
        if simbolo in posiciones:
            # Lógica de Promedio Ponderado
            cant_actual = posiciones[simbolo]['cantidad']
            prec_actual = posiciones[simbolo]['precio']
            
            nueva_cantidad_total = cant_actual + cant_nueva
            nuevo_ppp = ((cant_actual * prec_actual) + (cant_nueva * precio_nuevo)) / nueva_cantidad_total
            
            posiciones[simbolo] = {'cantidad': nueva_cantidad_total, 'precio': nuevo_ppp}
        else:
            posiciones[simbolo] = {'cantidad': cant_nueva, 'precio': precio_nuevo}
        
        guardar_transaccion(simbolo, cant_nueva, precio_nuevo, "compra", notas="Compra manual (PPP)")
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
            # Asegurar que la columna 'fecha' existe y es convertible
            if 'fecha' in df.columns:
                df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
                # Eliminar filas con fecha inválida
                df = df.dropna(subset=['fecha'])
            else:
                # Si no hay columna fecha, crear una vacía
                df['fecha'] = pd.NaT
            
            # Asegurar que existe la columna ganancia_pct
            if 'ganancia_pct' not in df.columns:
                df['ganancia_pct'] = np.nan
            else:
                df['ganancia_pct'] = pd.to_numeric(df['ganancia_pct'], errors='coerce')
            
            # Asegurar otras columnas necesarias
            columnas_necesarias = ['simbolo', 'score', 'precio', 'recomendacion', 'señales']
            for col in columnas_necesarias:
                if col not in df.columns:
                    df[col] = ''
            return df
        except Exception as e:
            st.error(f"Error al cargar historial: {e}")
    # Si no existe o hay error, devolver DataFrame vacío con todas las columnas necesarias
    return pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])
    
def guardar_senal_en_historial(senal: dict, fecha: str):
    import re
    # Cargar historial existente o crear DataFrame vacío
    if os.path.exists(HISTORIAL_FILE):
        try:
            df = pd.read_csv(HISTORIAL_FILE, on_bad_lines='skip')
            # Limpiar fechas
            if 'fecha' in df.columns:
                df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
                df = df.dropna(subset=['fecha'])
            else:
                df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])
        except:
            df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])
    else:
        df = pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales', 'ganancia_pct'])

    # Extraer ganancia porcentual si es señal de venta
    ganancia = None
        # Extraer ganancia porcentual si es señal de venta
    ganancia = None
    if senal['Recomendación'] == "VENDER" and 'Motivo' in senal:
        motivo = senal['Motivo']
        # Intento 1: patrón estándar con signo y decimales
        match = re.search(r'([+-]\d+(?:\.\d+)?)%', motivo)
        if not match:
            # Intento 2: buscar cualquier número decimal (puede ser sin signo explícito)
            match = re.search(r'(\d+(?:\.\d+)?)%', motivo)
        if match:
            ganancia = float(match.group(1))
        else:
            # Depuración: mostrar el motivo que no se pudo parsear
            st.warning(f"No se pudo extraer ganancia de: {motivo}")

    nueva = pd.DataFrame([{
        'fecha': pd.to_datetime(fecha, errors='coerce'),
        'simbolo': senal['Símbolo'],
        'score': senal['Score'],
        'precio': senal['Precio MXN'],
        'recomendacion': senal['Recomendación'],
        'señales': senal.get('Señales', ''),
        'ganancia_pct': ganancia
    }])

    df = pd.concat([df, nueva], ignore_index=True)
    # Mantener solo últimos 90 días
    cutoff = datetime.now() - timedelta(days=90)
    df = df[df['fecha'] >= cutoff]
    st.write(f"DEBUG: Guardando señal - simbolo: {senal['Símbolo']}, ganancia: {ganancia}")
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
        
#Analisis de ADN de exito      
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
# LISTAS DE MERCADO (sin cambios)
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
        hist['REGIME'] = hist['REGIME'].fillna(method='ffill').fillna(1)
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

def analizar_sentimiento(simbolo: str) -> dict:
    if not NEWSAPI_KEY:
        return {'sentimiento': 'Sin clave', 'score': 0, 'noticias': []}
    try:
        from_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        url = 'https://newsapi.org/v2/everything'
        params = {'q': simbolo.split('.')[0], 'from': from_date, 'sortBy': 'relevancy', 'language': 'en', 'pageSize': 5, 'apiKey': NEWSAPI_KEY}
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
    except:
        return {'sentimiento': 'Error', 'score': 0, 'noticias': []}
    
def optimizar_cartera(compras_df: pd.DataFrame, capital: float, usd_mxn: float, eur_mxn: float) -> pd.DataFrame:
    """Asigna pesos óptimos a las señales de compra usando Markowitz (max Sharpe)"""
    if compras_df.empty:
        return compras_df
    
    n = len(compras_df)
    symbols = compras_df['Símbolo'].tolist()
    
    # Obtener precios históricos
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
        r = requests.get("https://api.callmebot.com/whatsapp.php", params={"phone": WHATSAPP_NUMERO, "apikey": WHATSAPP_APIKEY, "text": mensaje}, timeout=10)
        return r.status_code == 200
    except:
        return False

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
        hist[col] *= factor
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

#Aquí 20 de abril del 26 a las 01:20 hrs añadir funcion de dashboard
def dashboard_rendimiento_ventas(df_hist: pd.DataFrame) -> None:
    # Depuración
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
                                 json={"model": "llama-3.3-70b-versatile", "messages": [{"role":"user","content":prompt}], "max_tokens":500}, timeout=30)
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
    (simbolo, precio_compra_dict, usd_mxn, eur_mxn, incluir_fund, incluir_bt,
     regime_bonus, capital, riesgo_pct, trailing_enabled, trailing_pct) = args
    try:
        periodo = "6mo" if incluir_bt else "3mo"
        ticker = yf.Ticker(simbolo)

        # ========== OBTENER PRECIO ACTUAL DE FORMA ROBUSTA ==========
        # Priorizar método de la cartera (info) y luego safe_history de 2d
        precio_actual = None
        try:
            info = ticker.info
            precio_info = info.get('regularMarketPrice') or info.get('currentPrice')
            if precio_info:
                precio_actual = float(precio_info)
        except:
            pass

        if precio_actual is None:
            hist_2d = safe_history(ticker, period="2d")
            if not hist_2d.empty:
                precio_actual = float(hist_2d['Close'].iloc[-1])

        if precio_actual is None:
            # Último fallback: usar el precio del historial largo (pero puede fallar por bloqueo)
            hist_temp = safe_history(ticker, period="2d")
            if hist_temp.empty:
                return None
            precio_actual = float(hist_temp['Close'].iloc[-1])

        factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
        precio_actual_mxn = precio_actual * factor

        # ========== INDICADORES (necesitan historial largo) ==========
        hist = safe_history(ticker, periodo)
        if hist.empty or len(hist) < 20:
            return None

        for col in ['Close', 'Open', 'High', 'Low']:
            hist[col] = hist[col] * factor

        hist = calcular_indicadores(hist)
        hist = hist.dropna(subset=['RSI', 'MACD', 'EMA20', 'EMA50', 'ATR', 'STOCH_K', 'STOCH_D'])
        if len(hist) < 2:
            return None

        ultimo = hist.iloc[-1].to_dict()
        penultimo = hist.iloc[-2].to_dict()
        # No sobrescribimos precio_actual_mxn con ultimo['Close'], pero lo guardamos por si algo
        atr = ultimo['ATR']
        score_base, señales = calcular_score(ultimo, penultimo)
        score = max(0, score_base + regime_bonus)

        ps = position_size(precio_actual_mxn, atr, capital, riesgo_pct)

        p_compra = precio_compra_dict.get(simbolo)
        señales_venta = []
        if p_compra:
            ganancia = ((precio_actual_mxn / p_compra) - 1) * 100

            # Depuración para INTC
            if simbolo == 'INTC':
                st.write(f"DEBUG INTC: p_compra={p_compra:.2f}, actual={precio_actual_mxn:.2f}, ganancia={ganancia:.2f}%")

            # === TRAILING STOP DINÁMICO (sin cambios) ===
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
            # ====================================

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
            'RSI': round(ultimo['RSI'], 1),
            'ATR': round(atr, 2),
            'Stop Loss': round(precio_actual_mxn - 2 * atr, 2),
            'Take Profit': round(precio_actual_mxn + 3 * atr, 2),
            'Unidades': ps['unidades'],
            'Inversión (MXN)': ps['inversion_mxn'],
            '% Capital': ps['pct_capital'],
            'Dist EMA50': round((precio_actual_mxn / ultimo['EMA50'] - 1) * 100, 2),
            'Recomendación': recomendacion,
            'Motivo': motivo,
            'Señales': " | ".join(señales),
        }
        if incluir_fund:
            resultado.update(obtener_fundamentales_profundos(simbolo))
        if incluir_bt and recomendacion.startswith("COMPRAR"):
            bt = backtest_realista(simbolo, precio_actual_mxn, atr)
            resultado['BT Resultado'] = f"{bt['resultado']:.2f}% ({bt['tipo']})"
        return resultado
    except Exception as e:
        print(f"[analizar_accion] {simbolo}: {type(e).__name__}: {e}")
        return None

# ============================================================
# SIDEBAR Y RESTAURACIÓN DE DATOS (mismo código que tenías, lo resumo)
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
        zip_bytes = generar_backup_zip()  # función definida antes, omitida por brevedad pero debe existir
        st.download_button("Guardar ZIP", data=zip_bytes, file_name="backup.zip")
    uploaded_bk = st.file_uploader("Restaurar ZIP", type="zip")
    if uploaded_bk and st.button("Restaurar"):
        pos_restauradas = restaurar_desde_zip(uploaded_bk)  # definida antes
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

#Añadido el 23 de abril a las 01:13 am
st.sidebar.markdown("### 📉 Trailing Stop")
trailing_enabled = st.sidebar.checkbox("Activar Trailing Stop dinámico", value=False)
trailing_pct = st.sidebar.slider("Trailing stop (%)", 1.0, 10.0, 5.0, 0.5, disabled=not trailing_enabled)
#filtro de alta confianza 23-04-3036 13:01 hrs
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
#de aquí hasta el siguiente apartado 12:48 pm
if st.sidebar.button("🔍 ANALIZAR", type="primary"):
    PRECIO_COMPRA = dict(st.session_state.get('PRECIO_COMPRA', {}))
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
                    PRECIO_COMPRA[sim] = precio
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
    if PRECIO_COMPRA:
        for sim in PRECIO_COMPRA.keys():
            if sim not in lista_acciones:
                lista_acciones.append(sim)

    total = len(lista_acciones)
    st.info(f"Analizando {total} acciones...")

    with st.spinner(f"Analizando {total} acciones en paralelo..."):
        resultados = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        completados = 0
        args_list = [
            (sim, PRECIO_COMPRA, usd_mxn, eur_mxn, fundamentales_check,
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
    ventas = df[(df['Recomendación'] == 'VENDER') & (df['Símbolo'].isin(PRECIO_COMPRA.keys()))].copy() if PRECIO_COMPRA else pd.DataFrame()
    compras = df[df['Recomendación'].str.startswith('COMPRAR')].sort_values('Score', ascending=False).copy()
    observar = df[df['Recomendación'] == 'OBSERVAR'].sort_values('Score', ascending=False).copy()
   
    #Aquí 20 de abril del 26 a las 13:17 hrs
    # ========== GUARDAR SEÑALES EN HISTORIAL ==========
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _, row in df.iterrows():
        # Construir un diccionario similar a 'senal' para cada fila
        senal = {
            'Símbolo': row['Símbolo'],
            'Precio MXN': row['Precio (MXN)'],
            'Score': row['Score'],
            'Recomendación': row['Recomendación'],
            'Motivo': row.get('Motivo', ''),
            'Señales': row.get('Señales', '')
        }
        # --- Línea de depuración ---
        if senal['Recomendación'] == "VENDER":
            st.write(f"DEBUG: Señal de venta encontrada: {senal['Símbolo']} - {senal['Motivo']}")
        
        guardar_senal_en_historial(senal, fecha_actual)
    #hasta aca

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
    st.session_state['ventas'] = ventas
    st.session_state['observar'] = observar
    st.session_state['PRECIO_COMPRA'] = PRECIO_COMPRA
    st.session_state['usd_mxn'] = usd_mxn
    st.session_state['eur_mxn'] = eur_mxn
    st.session_state['regime'] = regime_data
    st.session_state['capital'] = capital_total
    st.session_state['ultima_actualizacion'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    if PRECIO_COMPRA:
        repo_guardar_posiciones(PRECIO_COMPRA)
    repo_guardar_transacciones()

    # ========== IA ==========
    if ia_check and not compras.empty:
        with st.spinner("🤖 Analizando con IA..."):
            texto_ia = analisis_ia(compras.head(8).to_dict('records'), regime_data, usd_mxn)
            st.session_state['analisis_ia'] = texto_ia

    # ========== ALERTAS ==========
    compras_alerta = compras  # sin filtrar por score
    resumen_ia = st.session_state.get('analisis_ia', '')

    # === DEPURACIÓN: ver qué se va a enviar ===
    st.write("DEBUG compras (primeras 3):", compras.head(3) if not compras.empty else "Vacío")
    st.write("DEBUG ventas (primeras 3):", ventas.head(3) if not ventas.empty else "Vacío")
    st.write("DEBUG umbral_score:", umbral_score)
    st.write("DEBUG compras_alerta (primeras 3):", compras_alerta.head(3) if not compras_alerta.empty else "Vacío")
    # =====================================
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

    # ========== BACKTESTING ==========
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
    col1.metric("✅ Compras", len(compras))
    col2.metric("🔴 Ventas", len(ventas))
    col3.metric("👀 Observar", len(observar))
    col4.metric("🚫 Evitar", len(df[df['Recomendación'] == 'EVITAR']))
    
    # ========== TABLAS Y SECCIONES ORGANIZADAS EN PESTAÑAS ==========
    st.subheader("📊 Resultados detallados")
    (tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8) = st.tabs([
        "🟢 COMPRAS", "🔴 VENTAS", "🟡 OBSERVAR", "🔍 TODAS",
        "💼 CARTERA", "📜 HISTORIAL", "🏆 TOP 10", "📊 BACKTEST VENTAS"
    ])

    # --- Pestaña 1: Compras ---
    with tab1:
        if not compras.empty:
            cols_compras = ['Símbolo','Precio (MXN)','Score','RSI','ATR','Stop Loss','Take Profit',
                            'Unidades','Inversión (MXN)','% Capital','Peso Cartera','Inversión Asignada',
                            'Unidades Ajustadas','Recomendación','Motivo','Señales']
            st.dataframe(compras[[c for c in cols_compras if c in compras.columns]], width='stretch')
        else:
            st.info("Sin compras.")

    # --- Pestaña 2: Ventas ---
    with tab2:
        if not ventas.empty:
            cols_ventas = ['Símbolo','Precio (MXN)','Score','RSI','Stop Loss','Take Profit','Recomendación','Motivo']
            st.dataframe(ventas[[c for c in cols_ventas if c in ventas.columns]], width='stretch')
        else:
            st.info("Sin ventas.")

    # --- Pestaña 3: Observar ---
    with tab3:
        if not observar.empty:
            cols_obs = ['Símbolo','Precio (MXN)','Score','RSI','Stop Loss','Take Profit','Motivo']
            st.dataframe(observar[[c for c in cols_obs if c in observar.columns]], width='stretch')
        else:
            st.info("Sin observaciones.")

    # --- Pestaña 4: Todas las acciones ---
    with tab4:
        st.dataframe(df, width='stretch')
        
    # --- Pestaña 5: Cartera actual ---
    with tab5:
        st.subheader("Posiciones abiertas")
        posiciones_json = repo_cargar_posiciones() 
        
        if posiciones_json:
            filas_cartera = []
            for simb, datos in posiciones_json.items():
                p_compra = datos.get('precio', 0)
                cant = datos.get('cantidad', 0)

                # Determinar factor de conversión a MXN según el sufijo del símbolo
                if simb.endswith('.MX'):
                    factor = 1.0
                elif simb.endswith('.MC'):
                    factor = st.session_state.get('eur_mxn', eur_mxn)
                else:
                    factor = st.session_state.get('usd_mxn', usd_mxn)

                # Obtener precio en MXN
                p_actual_mxn = None
                if 'df' in locals() and not df.empty and simb in df['Símbolo'].values:
                    # El precio en df ya está en MXN
                    p_actual_mxn = df[df['Símbolo'] == simb]['Precio (MXN)'].iloc[0]
                else:
                    # Obtener precio original y convertir
                    p_original = obtener_precio_actual(simb)
                    if p_original is not None:
                        p_actual_mxn = p_original * factor
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
                    # Asegurar que fecha sea datetime (ya lo es, pero por seguridad)
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
                precio_compra = st.session_state['PRECIO_COMPRA'][sim_elegido]
                ganancia = (fila['Precio (MXN)'] / precio_compra - 1) * 100
                st.metric("Ganancia actual", f"{ganancia:+.2f}%")
            fig = grafico_enriquecido(sim_elegido, usd_mxn, eur_mxn)
            st.plotly_chart(fig, width='stretch')

else:
    st.info("🔍 Aún no has ejecutado un análisis. Ve a la barra lateral y haz clic en 'ANALIZAR' para obtener señales de trading.")

st.caption("v3.0 — Corregido y optimizado por Adrian López")
