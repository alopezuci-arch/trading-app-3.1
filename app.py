# ============================================================
# SISTEMA DE TRADING PROFESIONAL v2.0 — STREAMLIT
# Mejoras: score ponderado, ATR dinámico, análisis paralelo,
# backtesting, alertas email + WhatsApp, gráficos enriquecidos
# ============================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import io
import urllib3
import ssl
import time

# ── SSL ────────────────────────────────────────────────────
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# ── Configuración de página ────────────────────────────────
st.set_page_config(page_title="Trading System v2", layout="wide", page_icon="📈")
st.title("📈 Sistema de Trading Personal v2.0")
st.markdown(f"**Última actualización:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")

# ============================================================
# CONSTANTES DE ALERTAS
# ============================================================
EMAIL_DESTINO   = "alopez.uci@gmail.com"

# ── WhatsApp vía CallMeBot (gratis) ─────────────────────────
# Instrucciones de activación en: https://www.callmebot.com/blog/free-api-whatsapp-messages/
# 1. Agrega el número +34 644 66 83 41 a tus contactos como "CallMeBot"
# 2. Envía: "I allow callmebot to send me messages"
# 3. Recibirás tu API key por WhatsApp
WHATSAPP_NUMERO = ""    # ← tu número con código país, ej: "521234567890"
WHATSAPP_APIKEY = ""    # ← API key que te envía CallMeBot

# ── Email SMTP (Gmail) ──────────────────────────────────────
# Usa una contraseña de aplicación Gmail (no tu contraseña normal):
# Mi cuenta → Seguridad → Verificación en 2 pasos → Contraseñas de aplicación
EMAIL_REMITENTE = ""    # ← tu email Gmail
EMAIL_PASSWORD  = ""    # ← contraseña de aplicación de 16 caracteres

# ============================================================
# LISTAS DE MERCADOS
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
    sp100    = ['AAPL','MSFT','AMZN','NVDA','META','GOOGL','GOOG','JPM','V','JNJ','WMT','PG',
                'UNH','HD','DIS','MA','BAC','XOM','CVX','KO','PEP','ADBE','CRM','NFLX','TMO',
                'ABT','ACN','AMD','INTC','CMCSA','TXN','QCOM','COST','NKE','MRK','ABBV','LLY',
                'PFE','BMY','CVS','HON','UPS','BA','CAT','GE','IBM','GS','SPGI','MS','PLD',
                'LMT','MDT','ISRG','BLK','AMGN','GILD','FISV','SYK','ZTS','T','VZ','NEE','DUK',
                'SO','MO','PM','MDLZ','SBUX','MCD','LOW','TGT','TJX','ORCL','NOW','INTU','BKNG',
                'UBER','TSLA','AVGO']
    nasdaq100 = ['ADBE','AMD','AMGN','AMZN','ASML','AVGO','BIIB','BKNG','CDNS','CHTR','CMCSA',
                 'COST','CSCO','CSX','CTAS','DXCM','EA','EBAY','EXC','FANG','FAST','FTNT','GILD',
                 'GOOGL','GOOG','HON','IDXX','ILMN','INTC','INTU','ISRG','KLAC','LRCX','LULU',
                 'MAR','MELI','META','MNST','MSFT','MU','NFLX','NVDA','NXPI','ODFL','ORLY','PANW',
                 'PAYX','PCAR','PEP','QCOM','REGN','ROST','SBUX','SNPS','TMUS','TSLA','TXN','VRTX',
                 'WBA','WDAY','XEL','ZM','ZS']
    ibex35   = ['SAN.MC','BBVA.MC','TEF.MC','ITX.MC','IBE.MC','FER.MC','ENG.MC','ACS.MC','REP.MC',
                'AENA.MC','CLNX.MC','GRF.MC','MTS.MC','MAP.MC','MEL.MC','CABK.MC','ELE.MC','IAG.MC',
                'ANA.MC','VIS.MC','CIE.MC','LOG.MC','ACX.MC']
    bmv      = ['WALMEX.MX','GMEXICOB.MX','CEMEXCPO.MX','FEMSAUBD.MX','AMXL.MX','KOFUBL.MX',
                'GFNORTEO.MX','BBAJIOO.MX','ALFA.MX','ALPEKA.MX','ASURB.MX','GAPB.MX','OMAB.MX',
                'AC.MX','GCC.MX','LALA.MX','MEGA.MX','PINFRA.MX','TLEVISACPO.MX','VESTA.MX',
                'GRUMA.MX','HERDEZ.MX','CUERVO.MX','ORBIA.MX']
    ia_stocks      = ['NVDA','AMD','INTC','AI','PLTR','IBM','MSFT','GOOGL','META','SNOW','CRM',
                      'ADBE','NOW','ORCL','BIDU','BABA','SAP']
    commodity_etfs = ['GLD','SLV','USO','UNG','DBC']
    mining_oil     = ['NEM','GOLD','FCX','XOM','CVX','COP','EOG','SLB']

    return sp100, nasdaq100, ibex35, bmv, sp500, ia_stocks, commodity_etfs, mining_oil

sp100, nasdaq100, ibex35, bmv, sp500, ia_stocks, commodity_etfs, mining_oil = cargar_listas()

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("⚙️ Parámetros")

mercado_opciones = {
    "Prueba (AAPL, MSFT, NVDA, TSLA)": ['AAPL','MSFT','NVDA','TSLA'],
    "S&P 100":                          sp100,
    "S&P 500 (completo)":               sp500,
    "NASDAQ 100":                       nasdaq100,
    "IBEX 35":                          ibex35,
    "BMV":                              bmv,
    "IA (Inteligencia Artificial)":     ia_stocks,
    "Commodities (ETFs)":               commodity_etfs,
    "Mineras y Petroleras":             mining_oil,
    "Todos (completo)":                 list(set(sp500 + nasdaq100 + ibex35 + bmv +
                                                  ia_stocks + commodity_etfs + mining_oil)),
}
mercado_seleccionado = st.sidebar.selectbox("📊 Mercado", list(mercado_opciones.keys()), index=0)

# Opciones de análisis
st.sidebar.markdown("### 🔧 Análisis")
fundamentales_check  = st.sidebar.checkbox("📊 Análisis fundamental", value=False)
filtro_fundamentales = st.sidebar.checkbox("📊 Solo fundamentales sólidos", value=False) if fundamentales_check else False
backtesting_check    = st.sidebar.checkbox("🧪 Backtesting (últimos 6 meses)", value=False)
market_regime_check  = st.sidebar.checkbox("🌡️ Filtrar por Market Regime", value=True,
                           help="Si el S&P 500 está en tendencia bajista (bajo su EMA200), oculta señales de compra arriesgadas.")

# Position sizing
st.sidebar.markdown("### 💼 Gestión de capital")
capital_total = st.sidebar.number_input(
    "Capital disponible (MXN)", min_value=1000.0, value=100_000.0, step=1000.0,
    help="Total que destinas a trading activo (no incluyas tu parte de ETFs)."
)
riesgo_pct = st.sidebar.slider(
    "Riesgo máximo por operación (%)", min_value=0.5, max_value=3.0, value=1.0, step=0.25,
    help="Porcentaje de tu capital que estás dispuesto a perder en una sola operación. 1% es conservador, 2% moderado."
)

# Alertas
st.sidebar.markdown("### 🔔 Alertas")
alerta_email    = st.sidebar.checkbox("📧 Alertar por email", value=True)
alerta_whatsapp = st.sidebar.checkbox("💬 Alertar por WhatsApp", value=False)
umbral_score    = st.sidebar.slider("Umbral mínimo para alertar (score)", 4, 10, 7)

# Compras registradas
st.sidebar.markdown("### 💰 Registrar compras")
compra_input = st.sidebar.text_area(
    "Formato: SÍMBOLO=PRECIO (MXN)",
    placeholder="AAPL=4465.53\nWALMEX.MX=56.13",
    height=100
)

# ============================================================
# FUNCIONES DE ALERTAS
# ============================================================
def enviar_email(asunto: str, cuerpo_html: str):
    """Envía alerta por email vía Gmail SMTP."""
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD:
        st.warning("⚠️ Configura EMAIL_REMITENTE y EMAIL_PASSWORD para recibir alertas por correo.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = EMAIL_REMITENTE
        msg["To"]      = EMAIL_DESTINO
        msg.attach(MIMEText(cuerpo_html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_REMITENTE, EMAIL_PASSWORD)
            server.sendmail(EMAIL_REMITENTE, EMAIL_DESTINO, msg.as_string())
        return True
    except Exception as e:
        st.error(f"Error al enviar email: {e}")
        return False

def enviar_whatsapp(mensaje: str):
    """
    Envía alerta por WhatsApp vía CallMeBot (API gratuita).
    Activación:
      1. Agrega +34 644 66 83 41 como contacto "CallMeBot"
      2. Envíale: "I allow callmebot to send me messages"
      3. Recibirás tu API key por WhatsApp
    Docs: https://www.callmebot.com/blog/free-api-whatsapp-messages/
    """
    if not WHATSAPP_NUMERO or not WHATSAPP_APIKEY:
        st.warning("⚠️ Configura WHATSAPP_NUMERO y WHATSAPP_APIKEY para recibir alertas por WhatsApp.")
        return False
    try:
        url = "https://api.callmebot.com/whatsapp.php"
        params = {
            "phone":   WHATSAPP_NUMERO,
            "apikey":  WHATSAPP_APIKEY,
            "text":    mensaje,
        }
        r = requests.get(url, params=params, timeout=10)
        return r.status_code == 200
    except Exception as e:
        st.error(f"Error al enviar WhatsApp: {e}")
        return False

def construir_email_html(compras_df: pd.DataFrame, ventas_df: pd.DataFrame) -> str:
    """Construye el cuerpo HTML del correo de alertas."""
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    filas_compra = ""
    for _, r in compras_df.iterrows():
        filas_compra += (
            f"<tr><td><b>{r['Símbolo']}</b></td><td>{r['Precio (MXN)']}</td>"
            f"<td>{r.get('Score','')}</td><td>{r.get('Motivo','')}</td></tr>"
        )
    filas_venta = ""
    for _, r in ventas_df.iterrows():
        filas_venta += (
            f"<tr><td><b>{r['Símbolo']}</b></td><td>{r['Precio (MXN)']}</td>"
            f"<td>{r.get('Motivo','')}</td></tr>"
        )
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px">
    <h2 style="color:#1a73e8">📈 Alerta de Trading — {fecha}</h2>

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

    <p style="color:#666;font-size:12px;margin-top:20px">
      Generado por Sistema de Trading Personal v2.0<br>
      Este mensaje es informativo, no constituye asesoría financiera.
    </p>
    </body></html>
    """

# ============================================================
# ANÁLISIS TÉCNICO
# ============================================================
def calcular_indicadores(hist: pd.DataFrame) -> pd.DataFrame:
    """Calcula todos los indicadores técnicos sobre el DataFrame de precios."""
    # EMAs
    hist['EMA20'] = hist['Close'].ewm(span=20, adjust=False).mean()
    hist['EMA50'] = hist['Close'].ewm(span=50, adjust=False).mean()

    # RSI (14)
    delta = hist['Close'].diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs    = gain / loss
    hist['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    hist['EMA12']       = hist['Close'].ewm(span=12, adjust=False).mean()
    hist['EMA26']       = hist['Close'].ewm(span=26, adjust=False).mean()
    hist['MACD']        = hist['EMA12'] - hist['EMA26']
    hist['MACD_signal'] = hist['MACD'].ewm(span=9, adjust=False).mean()
    hist['MACD_hist']   = hist['MACD'] - hist['MACD_signal']

    # ATR (14) — Average True Range
    high_low   = hist['High'] - hist['Low']
    high_close = (hist['High'] - hist['Close'].shift()).abs()
    low_close  = (hist['Low']  - hist['Close'].shift()).abs()
    tr         = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    hist['ATR'] = tr.rolling(14).mean()

    # Bollinger Bands (20, 2σ)
    hist['BB_mid']   = hist['Close'].rolling(20).mean()
    bb_std           = hist['Close'].rolling(20).std()
    hist['BB_upper'] = hist['BB_mid'] + 2 * bb_std
    hist['BB_lower'] = hist['BB_mid'] - 2 * bb_std
    hist['BB_pct']   = (hist['Close'] - hist['BB_lower']) / (hist['BB_upper'] - hist['BB_lower'])

    # Estocástico (14, 3)
    low14  = hist['Low'].rolling(14).min()
    high14 = hist['High'].rolling(14).max()
    hist['STOCH_K'] = 100 * (hist['Close'] - low14) / (high14 - low14)
    hist['STOCH_D'] = hist['STOCH_K'].rolling(3).mean()

    # Volumen promedio (20 días)
    hist['Vol_avg'] = hist['Volume'].rolling(20).mean()

    return hist

def calcular_score(row_data: dict, penultimo: dict | None) -> tuple[int, list[str]]:
    """
    Sistema de puntaje ponderado (0–14 puntos).
    Retorna (score, lista_de_señales).
    """
    precio      = row_data['Close']
    ema20       = row_data['EMA20']
    ema50       = row_data['EMA50']
    rsi         = row_data['RSI']
    macd        = row_data['MACD']
    macd_signal = row_data['MACD_signal']
    vol         = row_data['Volume']
    vol_avg     = row_data['Vol_avg']
    bb_pct      = row_data['BB_pct']
    stoch_k     = row_data['STOCH_K']
    stoch_d     = row_data['STOCH_D']
    atr         = row_data['ATR']

    score   = 0
    señales = []

    # 1. Tendencia EMA (peso 2)
    if ema20 > ema50:
        score += 2
        señales.append("EMA alcista (+2)")
        # Golden cross (extra peso)
        if penultimo and penultimo.get('EMA20', 0) <= penultimo.get('EMA50', 1):
            score += 1
            señales.append("Golden Cross (+1)")

    # 2. RSI en zona alcista sin sobrecompra (peso 2)
    if 45 <= rsi <= 65:
        score += 2
        señales.append(f"RSI óptimo {rsi:.0f} (+2)")
    elif 30 <= rsi < 45:
        score += 1
        señales.append(f"RSI rebote {rsi:.0f} (+1)")

    # 3. MACD positivo (peso 2)
    if macd > macd_signal:
        score += 2
        señales.append("MACD positivo (+2)")
        # Cruce reciente
        if penultimo and penultimo.get('MACD', 1) <= penultimo.get('MACD_signal', 0):
            score += 1
            señales.append("Cruce MACD (+1)")

    # 4. Volumen alto (peso 1)
    if vol > vol_avg * 1.2:
        score += 1
        señales.append("Volumen alto (+1)")

    # 5. Bollinger: precio cerca de banda inferior (peso 2)
    if bb_pct is not None and not np.isnan(bb_pct):
        if bb_pct < 0.2:
            score += 2
            señales.append("Cerca banda BB inferior (+2)")
        elif bb_pct < 0.4:
            score += 1
            señales.append("BB zona baja (+1)")

    # 6. Estocástico (peso 1)
    if not (np.isnan(stoch_k) or np.isnan(stoch_d)):
        if 20 <= stoch_k <= 50 and stoch_k > stoch_d:
            score += 1
            señales.append(f"Stoch alcista {stoch_k:.0f} (+1)")

    # 7. Precio cerca de EMA50 (soporte) (peso 1)
    dist_ema50 = (precio / ema50 - 1) * 100
    if -3 <= dist_ema50 <= 0:
        score += 1
        señales.append("Rebote en EMA50 (+1)")

    return score, señales

def detectar_venta(row_data: dict, penultimo: dict | None, precio_compra: float | None,
                    usd_mxn: float) -> list[str]:
    """Detecta señales de venta. Retorna lista de motivos."""
    precio  = row_data['Close']
    ema20   = row_data['EMA20']
    ema50   = row_data['EMA50']
    rsi     = row_data['RSI']
    atr     = row_data['ATR']
    señales = []

    # 1. Take Profit / Stop Loss dinámico con ATR
    if precio_compra:
        ganancia    = (precio / precio_compra - 1) * 100
        stop_loss   = precio_compra - (2 * atr)
        take_profit = precio_compra + (3 * atr)

        if precio >= take_profit:
            señales.append(f"🎯 Take Profit ATR +{ganancia:.1f}%")
        elif precio <= stop_loss:
            señales.append(f"🛑 Stop Loss ATR {ganancia:.1f}%")
        elif ganancia >= 20:
            señales.append(f"🎯 Ganancia excepcional +{ganancia:.1f}%")

    # 2. Death Cross
    if penultimo and penultimo.get('EMA20', 1) >= penultimo.get('EMA50', 0) and ema20 < ema50:
        señales.append("⚠️ Death Cross")

    # 3. RSI sobrecomprado y bajando
    if rsi > 78 and penultimo and rsi < penultimo.get('RSI', 100):
        señales.append(f"📉 RSI sobrecomprado {rsi:.0f}")

    # 4. MACD cruce bajista
    if penultimo:
        if (penultimo.get('MACD', 0) >= penultimo.get('MACD_signal', 0) and
                row_data['MACD'] < row_data['MACD_signal']):
            señales.append("📉 Cruce MACD bajista")

    return señales

# ============================================================
# BACKTESTING SIMPLE
# ============================================================
def backtest_señal(hist: pd.DataFrame, umbral_score: int = 5, ventana_forward: int = 10) -> dict:
    """
    Evalúa qué tan efectivas habrían sido las señales de compra
    en los últimos 6 meses, midiendo el retorno a N días vista.
    """
    entradas   = []
    retornos   = []

    for i in range(50, len(hist) - ventana_forward):
        ventana   = hist.iloc[:i].copy()
        row_data  = ventana.iloc[-1].to_dict()
        penultimo = ventana.iloc[-2].to_dict() if len(ventana) >= 2 else None

        # Verificar que no haya NaN críticos
        if any(np.isnan(row_data.get(c, np.nan)) for c in ['RSI','MACD','EMA20','EMA50','ATR']):
            continue

        score, _ = calcular_score(row_data, penultimo)
        if score >= umbral_score:
            precio_entrada = hist['Close'].iloc[i]
            precio_salida  = hist['Close'].iloc[i + ventana_forward]
            retorno        = (precio_salida / precio_entrada - 1) * 100
            entradas.append(i)
            retornos.append(retorno)

    if not retornos:
        return {'entradas': 0, 'win_rate': 0.0, 'retorno_promedio': 0.0, 'retorno_max': 0.0, 'retorno_min': 0.0}

    return {
        'entradas':          len(retornos),
        'win_rate':          sum(1 for r in retornos if r > 0) / len(retornos) * 100,
        'retorno_promedio':  np.mean(retornos),
        'retorno_max':       np.max(retornos),
        'retorno_min':       np.min(retornos),
    }

# ============================================================
# ANÁLISIS FUNDAMENTAL
# ============================================================
@st.cache_data(ttl=86400)
def obtener_fundamentales(simbolo: str) -> dict:
    try:
        info = yf.Ticker(simbolo).info
        dy = info.get('dividendYield')
        roe = info.get('returnOnEquity')
        rg  = info.get('revenueGrowth')
        eg  = info.get('earningsGrowth')
        pm  = info.get('profitMargins')
        return {
            'P/E (ttm)':       info.get('trailingPE'),
            'P/E forward':     info.get('forwardPE'),
            'P/B':             info.get('priceToBook'),
            'Div Yield (%)':   round(dy * 100, 2) if dy else None,
            'ROE (%)':         round(roe * 100, 2) if roe else None,
            'Rev Growth (%)':  round(rg * 100, 2) if rg else None,
            'EPS Growth (%)':  round(eg * 100, 2) if eg else None,
            'Net Margin (%)':  round(pm * 100, 2) if pm else None,
        }
    except:
        return {}

def puntaje_fundamental(row: pd.Series) -> int:
    score = 0
    if pd.notna(row.get('ROE (%)'))        and row['ROE (%)'] > 15:        score += 1
    if pd.notna(row.get('Rev Growth (%)')) and row['Rev Growth (%)'] > 10: score += 1
    if pd.notna(row.get('EPS Growth (%)')) and row['EPS Growth (%)'] > 10: score += 1
    if pd.notna(row.get('Net Margin (%)')) and row['Net Margin (%)'] > 10: score += 1
    if pd.notna(row.get('P/E (ttm)'))      and row['P/E (ttm)'] < 25:      score += 1
    return score

# ============================================================
# FUNCIÓN PRINCIPAL DE ANÁLISIS POR ACCIÓN
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

# ============================================================
# MARKET REGIME — contexto del mercado general
# ============================================================
@st.cache_data(ttl=3600)
def obtener_market_regime() -> dict:
    """
    Evalúa el estado del mercado usando el S&P 500 como referencia.
    Retorna régimen: ALCISTA / LATERAL / BAJISTA y métricas clave.
    """
    try:
        sp = yf.Ticker("^GSPC").history(period="1y")
        if sp.empty or len(sp) < 200:
            return {'regime': 'DESCONOCIDO', 'color': 'gray', 'descripcion': 'Sin datos suficientes'}

        precio_actual = sp['Close'].iloc[-1]
        ema50         = sp['Close'].ewm(span=50).mean().iloc[-1]
        ema200        = sp['Close'].ewm(span=200).mean().iloc[-1]
        rsi_sp        = 100 - (100 / (1 + (
            sp['Close'].diff().where(lambda x: x > 0, 0).rolling(14).mean() /
            (-sp['Close'].diff().where(lambda x: x < 0, 0)).rolling(14).mean()
        ))).iloc[-1]

        # Rendimiento últimos 20 días (1 mes)
        ret_1m = (precio_actual / sp['Close'].iloc[-20] - 1) * 100 if len(sp) >= 20 else 0

        sobre_ema200 = precio_actual > ema200
        sobre_ema50  = precio_actual > ema50
        ema50_sobre_200 = ema50 > ema200   # Golden/Death cross de índice

        if sobre_ema200 and sobre_ema50 and ema50_sobre_200:
            regime      = 'ALCISTA'
            color       = 'green'
            descripcion = 'S&P 500 sobre EMA50 y EMA200 — condiciones favorables para compras'
            score_bonus = 0    # sin penalización
        elif sobre_ema200 and not sobre_ema50:
            regime      = 'LATERAL'
            color       = 'orange'
            descripcion = 'S&P 500 por debajo de EMA50 pero sobre EMA200 — ser selectivo'
            score_bonus = -1   # reducir score mínimo requerido
        else:
            regime      = 'BAJISTA'
            color       = 'red'
            descripcion = 'S&P 500 bajo su EMA200 — evitar nuevas compras, proteger posiciones'
            score_bonus = -3   # penalización severa al score

        return {
            'regime':       regime,
            'color':        color,
            'descripcion':  descripcion,
            'score_bonus':  score_bonus,
            'precio_sp500': round(precio_actual, 2),
            'ema50_sp500':  round(ema50, 2),
            'ema200_sp500': round(ema200, 2),
            'rsi_sp500':    round(rsi_sp, 1),
            'ret_1m':       round(ret_1m, 2),
        }
    except Exception as e:
        return {'regime': 'DESCONOCIDO', 'color': 'gray', 'descripcion': f'Error: {e}',
                'score_bonus': 0, 'precio_sp500': 0, 'ema50_sp500': 0,
                'ema200_sp500': 0, 'rsi_sp500': 0, 'ret_1m': 0}

# ============================================================
# POSITION SIZING — cuánto invertir por operación
# ============================================================
def calcular_position_size(precio: float, atr: float, capital: float, riesgo_pct: float) -> dict:
    """
    Position sizing basado en ATR (volatilidad real).

    Lógica:
      riesgo_mxn   = capital × riesgo_pct / 100     (lo que puedes perder)
      stop_distancia = 2 × ATR                       (dónde va el stop loss)
      unidades     = riesgo_mxn / stop_distancia     (cuántas acciones comprar)
      inversion    = unidades × precio               (capital a invertir)
    """
    try:
        riesgo_mxn     = capital * (riesgo_pct / 100)
        stop_distancia = 2 * atr
        if stop_distancia <= 0:
            return {'unidades': 0, 'inversion_mxn': 0, 'pct_capital': 0}

        unidades     = riesgo_mxn / stop_distancia
        inversion    = unidades * precio
        pct_capital  = (inversion / capital) * 100

        # Cap: nunca más del 20% del capital en una sola posición
        if pct_capital > 20:
            inversion   = capital * 0.20
            unidades    = inversion / precio
            pct_capital = 20.0

        return {
            'unidades':      round(unidades, 2),
            'inversion_mxn': round(inversion, 2),
            'pct_capital':   round(pct_capital, 1),
        }
    except:
        return {'unidades': 0, 'inversion_mxn': 0, 'pct_capital': 0}

def analizar_accion(args: tuple) -> dict | None:
    simbolo, precio_compra_dict, usd_mxn, eur_mxn, incluir_fund, incluir_bt, regime_bonus, capital, riesgo_pct = args
    try:
        periodo = "6mo" if incluir_bt else "3mo"
        hist    = yf.Ticker(simbolo).history(period=periodo)

        if hist.empty or len(hist) < 55:
            return None

        # Factor de conversión a MXN
        if simbolo.endswith('.MX'):
            factor = 1.0
        elif simbolo.endswith('.MC'):
            factor = eur_mxn
        else:
            factor = usd_mxn

        for col in ['Close','Open','High','Low']:
            hist[col] = hist[col] * factor

        # Calcular indicadores
        hist = calcular_indicadores(hist)

        # Eliminar filas con NaN en columnas críticas
        hist = hist.dropna(subset=['RSI','MACD','EMA20','EMA50','ATR','STOCH_K','STOCH_D'])
        if len(hist) < 2:
            return None

        ultimo    = hist.iloc[-1].to_dict()
        penultimo = hist.iloc[-2].to_dict()

        precio     = ultimo['Close']
        ema50      = ultimo['EMA50']
        rsi        = ultimo['RSI']
        atr        = ultimo['ATR']
        dist_ema50 = (precio / ema50 - 1) * 100

        # Score de compra + ajuste por régimen de mercado
        score_base, señales_compra = calcular_score(ultimo, penultimo)
        score = max(0, score_base + regime_bonus)
        if regime_bonus < 0:
            señales_compra.append(f"Mercado {'lateral' if regime_bonus == -1 else 'bajista'} ({regime_bonus:+d})")

        # Señales de venta
        p_compra      = precio_compra_dict.get(simbolo)
        señales_venta = detectar_venta(ultimo, penultimo, p_compra, usd_mxn)

        # Stop Loss / Take Profit dinámico
        sl = round(precio - 2 * atr, 2) if p_compra is None else round(p_compra - 2 * atr, 2)
        tp = round(precio + 3 * atr, 2) if p_compra is None else round(p_compra + 3 * atr, 2)

        # Position sizing
        ps = calcular_position_size(precio, atr, capital, riesgo_pct)

        # Recomendación
        if señales_venta:
            recomendacion = "VENDER"
            motivo        = señales_venta[0]
        elif score >= 8:
            recomendacion = "COMPRAR ★★★"
            motivo        = f"Score {score}/14"
        elif score >= 6:
            recomendacion = "COMPRAR ★★"
            motivo        = f"Score {score}/14"
        elif score >= 4:
            recomendacion = "OBSERVAR"
            motivo        = f"Score {score}/14"
        else:
            recomendacion = "EVITAR"
            motivo        = f"Score {score}/14"

        resultado = {
            'Símbolo':          simbolo,
            'Precio (MXN)':     round(precio, 2),
            'Score':            score,
            'RSI':              round(rsi, 1),
            'ATR':              round(atr, 2),
            'Stop Loss':        sl,
            'Take Profit':      tp,
            'Dist EMA50':       f"{dist_ema50:.1f}%",
            'Unidades':         ps['unidades'],
            'Inversión (MXN)':  ps['inversion_mxn'],
            '% Capital':        f"{ps['pct_capital']}%",
            'Recomendación':    recomendacion,
            'Motivo':           motivo,
            'Señales':          " | ".join(señales_compra) if señales_compra else "—",
        }

        # Fundamentales (opcional)
        if incluir_fund:
            resultado.update(obtener_fundamentales(simbolo))

        # Backtesting (opcional)
        if incluir_bt:
            bt = backtest_señal(hist, umbral_score=5)
            resultado['BT Entradas']  = bt['entradas']
            resultado['BT Win Rate']  = f"{bt['win_rate']:.1f}%"
            resultado['BT Ret Prom']  = f"{bt['retorno_promedio']:.1f}%"

        return resultado

    except Exception:
        return None

# ============================================================
# GRÁFICO ENRIQUECIDO (candlestick + EMAs + RSI + MACD + Vol)
# ============================================================
def grafico_enriquecido(simbolo: str, usd_mxn: float, eur_mxn: float) -> go.Figure:
    hist = yf.Ticker(simbolo).history(period="3mo")
    if hist.empty:
        return go.Figure()

    factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
    for col in ['Close','Open','High','Low']:
        hist[col] = hist[col] * factor

    hist = calcular_indicadores(hist)

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        row_heights=[0.5, 0.18, 0.18, 0.14],
        vertical_spacing=0.03,
        subplot_titles=[f"{simbolo} — Precio (MXN)", "RSI (14)", "MACD", "Volumen"]
    )

    # ── Velas + EMAs + Bollinger
    fig.add_trace(go.Candlestick(
        x=hist.index, open=hist['Open'], high=hist['High'],
        low=hist['Low'], close=hist['Close'], name="Precio",
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA20'],
        line=dict(color='#ff9800', width=1.5), name='EMA20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA50'],
        line=dict(color='#e91e63', width=1.5), name='EMA50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_upper'],
        line=dict(color='#78909c', width=1, dash='dot'), name='BB sup', opacity=0.6), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_lower'],
        line=dict(color='#78909c', width=1, dash='dot'), name='BB inf',
        fill='tonexty', fillcolor='rgba(120,144,156,0.08)', opacity=0.6), row=1, col=1)

    # ── RSI
    fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'],
        line=dict(color='#7e57c2', width=1.5), name='RSI'), row=2, col=1)
    for nivel, color, dash in [(70,'red','dash'), (50,'orange','dot'), (30,'green','dash')]:
        fig.add_hline(y=nivel, line_dash=dash, line_color=color, opacity=0.5, row=2, col=1)

    # ── MACD
    colors_hist = ['#26a69a' if v >= 0 else '#ef5350' for v in hist['MACD_hist'].fillna(0)]
    fig.add_trace(go.Bar(x=hist.index, y=hist['MACD_hist'],
        marker_color=colors_hist, name='MACD Hist', opacity=0.6), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD'],
        line=dict(color='#2196f3', width=1.5), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD_signal'],
        line=dict(color='#ff5722', width=1.5), name='Señal'), row=3, col=1)

    # ── Volumen
    vol_colors = ['#26a69a' if c >= o else '#ef5350'
                  for c, o in zip(hist['Close'], hist['Open'])]
    fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'],
        marker_color=vol_colors, name='Volumen', opacity=0.7), row=4, col=1)

    fig.update_layout(
        template='plotly_dark', height=750,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        margin=dict(l=50, r=30, t=60, b=30)
    )
    return fig

# ============================================================
# BOTÓN PRINCIPAL: ANALIZAR
# ============================================================
if st.sidebar.button("🔍 ANALIZAR", type="primary"):

    # Procesar compras
    PRECIO_COMPRA: dict[str, float] = {}
    if compra_input:
        for par in compra_input.replace('\n', ',').split(','):
            if '=' in par:
                sim, precio = par.split('=', 1)
                try:
                    PRECIO_COMPRA[sim.strip().upper()] = float(precio.strip())
                except ValueError:
                    pass
        if PRECIO_COMPRA:
            st.sidebar.success(f"✅ {len(PRECIO_COMPRA)} compra(s) registrada(s).")

    # Tipos de cambio
    usd_mxn, eur_mxn = obtener_tipo_cambio()
    st.sidebar.metric("USD/MXN", f"{usd_mxn:.2f}")
    st.sidebar.metric("EUR/MXN", f"{eur_mxn:.2f}")

    # ── Market Regime ───────────────────────────────────────
    regime_data  = obtener_market_regime()
    regime_bonus = regime_data['score_bonus'] if market_regime_check else 0

    color_map = {'ALCISTA': '🟢', 'LATERAL': '🟡', 'BAJISTA': '🔴', 'DESCONOCIDO': '⚪'}
    icono = color_map.get(regime_data['regime'], '⚪')

    with st.expander(f"{icono} Market Regime: **{regime_data['regime']}** — {regime_data['descripcion']}", expanded=True):
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("S&P 500",    f"{regime_data['precio_sp500']:,.0f}")
        r2.metric("EMA 200",    f"{regime_data['ema200_sp500']:,.0f}",
                  delta=f"{((regime_data['precio_sp500']/regime_data['ema200_sp500'])-1)*100:+.1f}%" if regime_data['ema200_sp500'] else None)
        r3.metric("RSI S&P",    f"{regime_data['rsi_sp500']}")
        r4.metric("Ret. 1 mes", f"{regime_data['ret_1m']:+.1f}%")

        if market_regime_check and regime_data['regime'] == 'BAJISTA':
            st.warning("⚠️ Mercado bajista detectado. Las señales de compra están penalizadas. Considera proteger posiciones existentes.")
        elif market_regime_check and regime_data['regime'] == 'LATERAL':
            st.info("ℹ️ Mercado lateral. Solo compras con score muy alto (≥8) son recomendables.")

    # ── Estrategia Core + Satélite ──────────────────────────
    with st.expander("💼 Estrategia recomendada: Core + Satélite"):
        etf_capital   = round(capital_total * 0.65, 2)
        trade_capital = round(capital_total * 0.25, 2)
        conv_capital  = round(capital_total * 0.10, 2)
        c1, c2, c3 = st.columns(3)
        c1.metric("🏛️ Core — ETFs (65%)",    f"${etf_capital:,.0f} MXN",
                  help="VOO, QQQ, IVV — comprar y mantener, no tocar")
        c2.metric("⚡ Satélite — Trading (25%)", f"${trade_capital:,.0f} MXN",
                  help="Tu sistema activo con este scanner")
        c3.metric("🎯 Alta convicción (10%)", f"${conv_capital:,.0f} MXN",
                  help="1-2 ideas con investigación fundamental profunda")
        st.caption(f"Position sizing activo sobre ${trade_capital:,.0f} MXN · Riesgo por operación: {riesgo_pct}% = ${trade_capital*riesgo_pct/100:,.0f} MXN máx. por trade")

    # ── Análisis en paralelo ────────────────────────────────
    lista_acciones = mercado_opciones[mercado_seleccionado]
    total          = len(lista_acciones)
    st.info(f"📊 Analizando {total} acciones en paralelo (máx 10 hilos)...")

    resultados   = []
    progress_bar = st.progress(0)
    status_text  = st.empty()
    completados  = 0

    args_list = [
        (sim, PRECIO_COMPRA, usd_mxn, eur_mxn, fundamentales_check, backtesting_check,
         regime_bonus, capital_total * 0.25, riesgo_pct)
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

    # Guardar en session_state para que persistan al interactuar con el selectbox
    st.session_state['df']            = df
    st.session_state['PRECIO_COMPRA'] = PRECIO_COMPRA
    st.session_state['usd_mxn']       = usd_mxn
    st.session_state['eur_mxn']       = eur_mxn
    st.session_state['fund_check']    = fundamentales_check
    st.session_state['bt_check']      = backtesting_check
    st.session_state['regime']        = regime_data
    st.session_state['capital']       = capital_total

    # Añadir puntaje fundamental si aplica
    if fundamentales_check and 'ROE (%)' in df.columns:
        df['Score Fund'] = df.apply(puntaje_fundamental, axis=1)

    # ── Separar categorías ──────────────────────────────────
    # VENTAS: solo mostrar acciones que el usuario registró con precio de compra
    if PRECIO_COMPRA:
        ventas = df[
            (df['Recomendación'] == 'VENDER') &
            (df['Símbolo'].isin(PRECIO_COMPRA.keys()))
        ].copy()
    else:
        ventas = pd.DataFrame()   # sin compras registradas → pestaña vacía

    compras = df[df['Recomendación'].str.startswith('COMPRAR')].sort_values('Score', ascending=False).copy()
    observar= df[df['Recomendación'] == 'OBSERVAR'].sort_values('Score', ascending=False).copy()
    evitar  = df[df['Recomendación'] == 'EVITAR'].copy()

    # ── Filtro fundamental (FIX del bug original) ───────────
    if filtro_fundamentales and 'ROE (%)' in compras.columns:
        compras = compras[
            compras['ROE (%)'].notna() &
            compras['Rev Growth (%)'].notna() &
            (compras['ROE (%)'] > 10) &
            (compras['Rev Growth (%)'] > 5)
        ]

    # ── Métricas resumen ────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Compras",    len(compras))
    col2.metric("🔴 Ventas",     len(ventas))
    col3.metric("👀 Observar",   len(observar))
    col4.metric("🚫 Evitar",     len(evitar))

    # ── Alertas automáticas ─────────────────────────────────
    compras_alerta = compras[compras['Score'] >= umbral_score]
    if (alerta_email or alerta_whatsapp) and (not compras_alerta.empty or not ventas.empty):
        with st.spinner("📤 Enviando alertas..."):

            if alerta_email:
                html   = construir_email_html(compras_alerta, ventas)
                ok     = enviar_email(f"📈 Alerta Trading {datetime.now().strftime('%d/%m %H:%M')}", html)
                if ok:
                    st.success(f"📧 Email enviado a {EMAIL_DESTINO}")

            if alerta_whatsapp:
                n_compras = len(compras_alerta)
                n_ventas  = len(ventas)
                top3      = ", ".join(compras_alerta.head(3)['Símbolo'].tolist()) if n_compras else "ninguna"
                msg       = (
                    f"📈 *Alerta Trading* {datetime.now().strftime('%d/%m %H:%M')}\n"
                    f"🟢 Compras: {n_compras} (Top: {top3})\n"
                    f"🔴 Ventas: {n_ventas}\n"
                    f"Umbral score: {umbral_score}"
                )
                ok = enviar_whatsapp(msg)
                if ok:
                    st.success("💬 WhatsApp enviado")

    # ── Tabs de resultados ──────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["🟢 COMPRAS", "🔴 VENTAS", "🟡 OBSERVAR", "🔍 TODAS"])

    # Columnas a mostrar
    cols_base = ['Símbolo','Precio (MXN)','Score','RSI','ATR','Stop Loss','Take Profit',
                 'Unidades','Inversión (MXN)','% Capital',
                 'Dist EMA50','Recomendación','Motivo','Señales']
    cols_fund = [c for c in df.columns if c not in cols_base]

    def show_df(frame, cols_extra=None):
        cols = cols_base + (cols_extra or [])
        cols = [c for c in cols if c in frame.columns]
        st.dataframe(frame[cols].reset_index(drop=True), use_container_width=True)

    with tab1:
        if not compras.empty:
            show_df(compras, cols_fund if fundamentales_check else [])
        else:
            st.info("Sin oportunidades de compra en este momento.")

    with tab2:
        if not ventas.empty:
            st.caption(f"Mostrando señales de venta únicamente para tus {len(PRECIO_COMPRA)} acción(es) registradas.")
            show_df(ventas, cols_fund if fundamentales_check else [])
        elif PRECIO_COMPRA:
            st.info("✅ Ninguna de tus acciones registradas tiene señal de venta en este momento.")
        else:
            st.warning("⚠️ No has registrado ninguna compra. Ingresa tus acciones en el panel lateral con el formato SÍMBOLO=PRECIO para recibir recomendaciones de venta.")

    with tab3:
        show_df(observar.head(20), cols_fund if fundamentales_check else [])

    with tab4:
        st.dataframe(df.reset_index(drop=True), use_container_width=True)

    # ── Gráfico de la mejor oportunidad ─────────────────────
    if not compras.empty:
        mejor = compras.iloc[0]['Símbolo']
        st.subheader(f"📊 Análisis completo: {mejor}")
        fig = grafico_enriquecido(mejor, usd_mxn, eur_mxn)
        st.plotly_chart(fig, use_container_width=True)

        # Gráfico de score — top 10 compras
        top10 = compras.head(10)
        fig_score = px.bar(
            top10, x='Símbolo', y='Score',
            color='Score', color_continuous_scale='RdYlGn',
            text='Score',
            title="Top 10 — Score ponderado de compra (máx 14 pts)"
        )
        fig_score.add_hline(y=8, line_dash="dash", line_color="green", annotation_text="Compra fuerte")
        fig_score.add_hline(y=6, line_dash="dash", line_color="orange", annotation_text="Compra moderada")
        fig_score.update_traces(textposition='outside')
        fig_score.update_layout(showlegend=False, height=420, template='plotly_dark')
        st.plotly_chart(fig_score, use_container_width=True)

        # Backtesting (si activo)
        if backtesting_check and 'BT Win Rate' in compras.columns:
            st.subheader("🧪 Resultados de Backtesting (últimos 6 meses)")
            bt_cols = ['Símbolo','Score','BT Entradas','BT Win Rate','BT Ret Prom']
            bt_df   = compras[[c for c in bt_cols if c in compras.columns]].head(15)
            st.dataframe(bt_df.reset_index(drop=True), use_container_width=True)

    # ── Exportar Excel ──────────────────────────────────────
    try:
        import openpyxl  # noqa: F401
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            compras.to_excel(writer,  index=False, sheet_name='Compras')
            ventas.to_excel(writer,   index=False, sheet_name='Ventas')
            observar.to_excel(writer, index=False, sheet_name='Observar')
            df.to_excel(writer,       index=False, sheet_name='Todos')

        st.download_button(
            label="📥 Descargar informe Excel (todas las hojas)",
            data=output.getvalue(),
            file_name=f"trading_v2_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except ImportError:
        st.warning("⚠️ openpyxl no está instalado. Agrega 'openpyxl' a tu requirements.txt para habilitar la descarga Excel.")
        # Fallback: descargar como CSV
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar como CSV (alternativa)",
            data=csv_data,
            file_name=f"trading_v2_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

# ============================================================
# SELECTOR DE GRÁFICO — fuera del bloque del botón para que
# no desaparezca al cambiar la selección (session_state persiste)
# ============================================================
if 'df' in st.session_state:
    _df      = st.session_state['df']
    _usd_mxn = st.session_state['usd_mxn']
    _eur_mxn = st.session_state['eur_mxn']
    _capital = st.session_state.get('capital', 100_000)

    # Resumen de capital comprometido en compras activas
    pc = st.session_state.get('PRECIO_COMPRA', {})
    if pc:
        st.divider()
        st.subheader("💼 Resumen de tu portafolio activo")
        rows = []
        for sim, precio_compra in pc.items():
            fila_df = _df[_df['Símbolo'] == sim]
            if not fila_df.empty:
                f = fila_df.iloc[0]
                precio_actual = float(str(f['Precio (MXN)']).replace(',',''))
                ganancia_pct  = (precio_actual / precio_compra - 1) * 100
                rows.append({
                    'Símbolo':        sim,
                    'Comprado a':     precio_compra,
                    'Precio actual':  precio_actual,
                    'Ganancia %':     f"{ganancia_pct:+.2f}%",
                    'Score':          f['Score'],
                    'Recomendación':  f['Recomendación'],
                    'Inversión (MXN)':f.get('Inversión (MXN)', '—'),
                })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.divider()
    st.subheader("🔎 Explorar cualquier acción analizada")

    todos_simbolos = _df['Símbolo'].tolist()
    sim_elegido = st.selectbox(
        "Selecciona un símbolo para ver su gráfico completo",
        todos_simbolos,
        key="selector_grafico"
    )

    if sim_elegido:
        # Mostrar datos de esa acción
        fila = _df[_df['Símbolo'] == sim_elegido].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Precio (MXN)", fila['Precio (MXN)'])
        c2.metric("Score",        fila['Score'])
        c3.metric("RSI",          fila['RSI'])
        c4.metric("Recomendación",fila['Recomendación'])

        # Precio de compra registrado (si aplica)
        pc = st.session_state.get('PRECIO_COMPRA', {})
        if sim_elegido in pc:
            precio_compra = pc[sim_elegido]
            precio_actual = float(str(fila['Precio (MXN)']).replace(',',''))
            ganancia_pct  = (precio_actual / precio_compra - 1) * 100
            color         = "normal" if ganancia_pct >= 0 else "inverse"
            st.metric(
                f"Tu compra en {precio_compra:.2f} MXN",
                f"{precio_actual:.2f} MXN",
                delta=f"{ganancia_pct:+.2f}%",
                delta_color=color
            )

        fig2 = grafico_enriquecido(sim_elegido, _usd_mxn, _eur_mxn)
        st.plotly_chart(fig2, use_container_width=True)
