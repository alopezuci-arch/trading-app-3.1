# ============================================================
# SISTEMA DE TRADING PROFESIONAL v2.0 — STREAMLIT
# Versión con persistencia de resultados (session_state)
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

# ── SSL ────────────────────────────────────────────────────
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# ── Configuración de página ────────────────────────────────
st.set_page_config(page_title="Trading System v2", layout="wide", page_icon="📈")
st.title("📈 Sistema de Trading Personal v2.0")

# ============================================================
# CONSTANTES DE ALERTAS (se leen de Secrets / entorno)
# ============================================================
EMAIL_DESTINO   = "alopez.uci@gmail.com"
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY",    "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY",      "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
WHATSAPP_NUMERO   = os.environ.get("WHATSAPP_NUMERO", "")
WHATSAPP_APIKEY   = os.environ.get("WHATSAPP_APIKEY", "")
EMAIL_REMITENTE   = os.environ.get("EMAIL_REMITENTE", "")
EMAIL_PASSWORD    = os.environ.get("EMAIL_PASSWORD",  "")

# ============================================================
# LISTAS DE MERCADOS (completas)
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
# ============================================================
# HISTORIAL DE TRANSACCIONES
# ============================================================
TRANSACCIONES_FILE = "transacciones.csv"

def cargar_transacciones() -> pd.DataFrame:
    """Carga el archivo de transacciones si existe, o devuelve DataFrame vacío."""
    if os.path.exists(TRANSACCIONES_FILE):
        df = pd.read_csv(TRANSACCIONES_FILE)
        # Asegurar formato de fecha
        df['fecha'] = pd.to_datetime(df['fecha'])
        return df
    return pd.DataFrame(columns=['fecha', 'simbolo', 'cantidad', 'precio', 'tipo', 'total', 'notas'])

def guardar_transaccion(simbolo: str, cantidad: float, precio: float, tipo: str, notas: str = ""):
    """Agrega una nueva transacción al archivo CSV."""
    df = cargar_transacciones()
    nueva = pd.DataFrame([{
        'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'simbolo': simbolo.upper(),
        'cantidad': cantidad,
        'precio': precio,
        'tipo': tipo,
        'total': round(cantidad * precio, 2),
        'notas': notas
    }])
    df = pd.concat([df, nueva], ignore_index=True)
    df.to_csv(TRANSACCIONES_FILE, index=False)
    print(f"✅ Transacción registrada: {tipo.upper()} {cantidad} {simbolo} @ ${precio:.2f}")
    
# ============================================================
# SIDEBAR (controles)
# ============================================================
st.sidebar.header("⚙️ Parámetros")

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
    "🌍 Global completo":                      list(set(
        sp500 + nasdaq100 + ibex35 + bmv +
        ia_stocks + commodity_etfs + mining_oil +
        etfs_sectoriales + mid_cap_growth + etfs_emergentes
    )),
}
mercado_seleccionado = st.sidebar.selectbox("📊 Mercado", list(mercado_opciones.keys()), index=1)

# Opciones de análisis
st.sidebar.markdown("### 🔧 Análisis")
fundamentales_check  = st.sidebar.checkbox("📊 Análisis fundamental", value=False)
filtro_fundamentales = st.sidebar.checkbox("📊 Solo fundamentales sólidos", value=False) if fundamentales_check else False
backtesting_check    = st.sidebar.checkbox("🧪 Backtesting (últimos 6 meses)", value=False)
market_regime_check  = st.sidebar.checkbox("🌡️ Filtrar por Market Regime", value=True)
ia_check = st.sidebar.checkbox("🤖 Análisis IA", value=True)

# Gestión de capital
st.sidebar.markdown("### 💼 Gestión de capital")
capital_total = st.sidebar.number_input("Capital disponible (MXN)", min_value=1000.0, value=100_000.0, step=1000.0)
riesgo_pct = st.sidebar.slider("Riesgo máximo por operación (%)", min_value=0.5, max_value=3.0, value=1.0, step=0.25)

# Alertas
st.sidebar.markdown("### 🔔 Alertas")
alerta_email    = st.sidebar.checkbox("📧 Alertar por email", value=True)
alerta_whatsapp = st.sidebar.checkbox("💬 Alertar por WhatsApp", value=False)
umbral_score    = st.sidebar.slider("Umbral mínimo para alertar (score)", 4, 10, 7)

st.sidebar.markdown("### 💰 Registrar compra")
compra_input = st.sidebar.text_area(
    "Formato: SÍMBOLO,CANTIDAD,PRECIO (MXN)\nEjemplo:\nAAPL,10,4465.53\nWALMEX.MX,5,56.13",
    placeholder="AAPL,10,4465.53\nWALMEX.MX,5,56.13",
    height=120
)
)

# ============================================================
# FUNCIONES AUXILIARES (indicadores, scoring, etc.)
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
    hist['MACD_hist'] = hist['MACD'] - hist['MACD_sig']
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
            return {'regime': 'DESCONOCIDO', 'score_bonus': 0, 'precio': 0, 'ema200': 0, 'ret_1m': 0, 'rsi_sp500': 0, 'descripcion': 'Sin datos'}
        precio = sp['Close'].iloc[-1]
        ema200 = sp['Close'].ewm(span=200).mean().iloc[-1]
        ema50  = sp['Close'].ewm(span=50).mean().iloc[-1]
        ret_1m = (precio / sp['Close'].iloc[-20] - 1) * 100 if len(sp) >= 20 else 0
        # RSI del S&P 500 (simple, solo para mostrar)
        delta = sp['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_sp500 = 100 - (100 / (1 + rs)).iloc[-1] if not loss.empty else 50
        if precio > ema200 and precio > ema50 and ema50 > ema200:
            return {'regime': 'ALCISTA', 'score_bonus': 0, 'precio': precio, 'ema200': ema200, 'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1), 'descripcion': 'S&P 500 sobre EMA50 y EMA200 — condiciones favorables para compras'}
        elif precio > ema200:
            return {'regime': 'LATERAL', 'score_bonus': -1, 'precio': precio, 'ema200': ema200, 'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1), 'descripcion': 'S&P 500 por debajo de EMA50 pero sobre EMA200 — ser selectivo'}
        else:
            return {'regime': 'BAJISTA', 'score_bonus': -3, 'precio': precio, 'ema200': ema200, 'ret_1m': ret_1m, 'rsi_sp500': round(rsi_sp500, 1), 'descripcion': 'S&P 500 bajo su EMA200 — evitar nuevas compras, proteger posiciones'}
    except:
        return {'regime': 'DESCONOCIDO', 'score_bonus': 0, 'precio': 0, 'ema200': 0, 'ret_1m': 0, 'rsi_sp500': 0, 'descripcion': 'Error al obtener datos'}

def position_size(precio: float, atr: float, capital: float, riesgo_pct: float) -> dict:
    riesgo_mxn = capital * (riesgo_pct / 100)
    stop_dist  = 2 * atr
    if stop_dist <= 0:
        return {'unidades': 0, 'inversion_mxn': 0, 'pct_capital': 0}
    unidades   = riesgo_mxn / stop_dist
    inversion  = unidades * precio
    pct_capital = (inversion / capital) * 100
    if pct_capital > 20:
        inversion   = capital * 0.20
        unidades    = inversion / precio
        pct_capital = 20.0
    return {
        'unidades':      round(unidades, 2),
        'inversion_mxn': round(inversion, 2),
        'pct_capital':   round(pct_capital, 1)
    }

def obtener_tipo_cambio() -> tuple[float, float]:
    try:
        usd = yf.Ticker("USDMXN=X").history(period="1d")
        eur = yf.Ticker("EURMXN=X").history(period="1d")
        return (float(usd['Close'].iloc[-1]) if not usd.empty else 20.0,
                float(eur['Close'].iloc[-1]) if not eur.empty else 21.5)
    except:
        return 20.0, 21.5

@st.cache_data(ttl=86400)
def obtener_fundamentales(simbolo: str) -> dict:
    try:
        info = yf.Ticker(simbolo).info
        dy = info.get('dividendYield')
        roe = info.get('returnOnEquity')
        rg = info.get('revenueGrowth')
        eg = info.get('earningsGrowth')
        pm = info.get('profitMargins')
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

def analizar_accion(args: tuple) -> dict | None:
    simbolo, precio_compra_dict, usd_mxn, eur_mxn, incluir_fund, incluir_bt, regime_bonus, capital, riesgo_pct = args
    try:
        periodo = "6mo" if incluir_bt else "3mo"
        hist    = yf.Ticker(simbolo).history(period=periodo)
        if hist.empty or len(hist) < 55:
            return None
        if simbolo.endswith('.MX'):
            factor = 1.0
        elif simbolo.endswith('.MC'):
            factor = eur_mxn
        else:
            factor = usd_mxn
        for col in ['Close','Open','High','Low']:
            hist[col] = hist[col] * factor
        hist = calcular_indicadores(hist)
        hist = hist.dropna(subset=['RSI','MACD','EMA20','EMA50','ATR','STOCH_K','STOCH_D'])
        if len(hist) < 2:
            return None
        ultimo    = hist.iloc[-1].to_dict()
        penultimo = hist.iloc[-2].to_dict() if len(hist) >= 2 else None
        precio     = ultimo['Close']
        ema50      = ultimo['EMA50']
        rsi        = ultimo['RSI']
        atr        = ultimo['ATR']
        dist_ema50 = (precio / ema50 - 1) * 100
        score_base, señales_compra = calcular_score(ultimo, penultimo)
        score = max(0, score_base + regime_bonus)
        if regime_bonus < 0:
            señales_compra.append(f"Mercado {'lateral' if regime_bonus == -1 else 'bajista'} ({regime_bonus:+d})")
        p_compra      = precio_compra_dict.get(simbolo)
        señales_venta = []
        if p_compra:
            ganancia = ((precio / p_compra) - 1) * 100
            if ganancia >= 15:
                señales_venta.append(f"🎯 Take Profit +{ganancia:.1f}%")
            elif ganancia <= -7:
                señales_venta.append(f"🛑 Stop Loss {ganancia:.1f}%")
        sl = round(precio - 2 * atr, 2)
        tp = round(precio + 3 * atr, 2)
        ps = position_size(precio, atr, capital, riesgo_pct)
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
        if incluir_fund:
            resultado.update(obtener_fundamentales(simbolo))
        if incluir_bt:
            # backtest simple (placeholder)
            resultado['BT Entradas'] = 0
            resultado['BT Win Rate'] = "0%"
            resultado['BT Ret Prom'] = "0%"
        return resultado
    except Exception as e:
        return None

def puntaje_fundamental(row: pd.Series) -> int:
    score = 0
    if pd.notna(row.get('ROE (%)'))        and row['ROE (%)'] > 15:        score += 1
    if pd.notna(row.get('Rev Growth (%)')) and row['Rev Growth (%)'] > 10: score += 1
    if pd.notna(row.get('EPS Growth (%)')) and row['EPS Growth (%)'] > 10: score += 1
    if pd.notna(row.get('Net Margin (%)')) and row['Net Margin (%)'] > 10: score += 1
    if pd.notna(row.get('P/E (ttm)'))      and row['P/E (ttm)'] < 25:      score += 1
    return score

# ============================================================
# ALERTAS
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
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": WHATSAPP_NUMERO, "apikey": WHATSAPP_APIKEY, "text": mensaje},
            timeout=10,
        )
        return r.status_code == 200
    except:
        return False

def construir_email_html(compras_df: pd.DataFrame, ventas_df: pd.DataFrame, resumen_ia: str = "") -> str:
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    filas_compra = "".join([
        f"<tr><td><b>{r['Símbolo']}</b></td><td>{r['Precio (MXN)']}</td><td>{r.get('Score','')}</td><td>{r.get('Motivo','')}</td></tr>"
        for _, r in compras_df.iterrows()
    ])
    filas_venta = "".join([
        f"<tr><td><b>{r['Símbolo']}</b></td><td>{r['Precio (MXN)']}</td><td>{r.get('Motivo','')}</td></tr>"
        for _, r in ventas_df.iterrows()
    ])
    bloque_ia = ""
    if resumen_ia:
        bloque_ia = f"""
        <h3 style="color:#7b61ff">🤖 Análisis de IA</h3>
        <div style="background:#f5f3ff;padding:12px 16px;border-left:4px solid #7b61ff;border-radius:4px;font-size:14px;line-height:1.6">
          {resumen_ia.replace(chr(10), '<br>')}
        </div>"""
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
    <p style="color:#666;font-size:12px;margin-top:20px">
      Generado por Sistema de Trading Personal v2.0 con IA<br>
      Este mensaje es informativo, no constituye asesoría financiera.
    </p>
    </body></html>"""

def analisis_ia_claude(oportunidades: list[dict], regime: dict, usd_mxn: float) -> str:
    """IA placeholder. Puedes reemplazar con llamada real a Gemini/Groq/Anthropic."""
    if not oportunidades:
        return ""
    return "**Análisis IA:** Las condiciones de mercado actuales favorecen las posiciones de compra en los sectores tecnológico y de semiconductores. Las oportunidades con mayor score presentan buenos fundamentales y momentum. Se recomienda mantener stop loss dinámico según ATR."

# ============================================================
# GRÁFICO ENRIQUECIDO
# ============================================================
def grafico_enriquecido(simbolo: str, usd_mxn: float, eur_mxn: float) -> go.Figure:
    hist = yf.Ticker(simbolo).history(period="3mo")
    if hist.empty:
        return go.Figure()
    factor = 1.0 if simbolo.endswith('.MX') else (eur_mxn if simbolo.endswith('.MC') else usd_mxn)
    for col in ['Close','Open','High','Low']:
        hist[col] = hist[col] * factor
    hist = calcular_indicadores(hist)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True,
                        row_heights=[0.5, 0.18, 0.18, 0.14],
                        vertical_spacing=0.03,
                        subplot_titles=[f"{simbolo} — Precio (MXN)", "RSI (14)", "MACD", "Volumen"])
    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'],
                                 low=hist['Low'], close=hist['Close'], name="Precio",
                                 increasing_line_color='#26a69a', decreasing_line_color='#ef5350'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA20'], line=dict(color='#ff9800', width=1.5), name='EMA20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA50'], line=dict(color='#e91e63', width=1.5), name='EMA50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_upper'], line=dict(color='#78909c', width=1, dash='dot'), name='BB sup', opacity=0.6), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_lower'], line=dict(color='#78909c', width=1, dash='dot'), name='BB inf',
                             fill='tonexty', fillcolor='rgba(120,144,156,0.08)', opacity=0.6), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], line=dict(color='#7e57c2', width=1.5), name='RSI'), row=2, col=1)
    for nivel, color, dash in [(70,'red','dash'), (50,'orange','dot'), (30,'green','dash')]:
        fig.add_hline(y=nivel, line_dash=dash, line_color=color, opacity=0.5, row=2, col=1)
    colors_hist = ['#26a69a' if v >= 0 else '#ef5350' for v in hist['MACD_hist'].fillna(0)]
    fig.add_trace(go.Bar(x=hist.index, y=hist['MACD_hist'], marker_color=colors_hist, name='MACD Hist', opacity=0.6), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD'], line=dict(color='#2196f3', width=1.5), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD_sig'], line=dict(color='#ff5722', width=1.5), name='Señal'), row=3, col=1)
    vol_colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(hist['Close'], hist['Open'])]
    fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], marker_color=vol_colors, name='Volumen', opacity=0.7), row=4, col=1)
    fig.update_layout(template='plotly_dark', height=750, xaxis_rangeslider_visible=False,
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                      margin=dict(l=50, r=30, t=60, b=30))
    return fig

# ============================================================
# BOTÓN DE ANÁLISIS (SOLO ACTUALIZA st.session_state)
# ============================================================
# Procesar compras registradas (nuevo formato y antiguo)
PRECIO_COMPRA = {}
if compra_input:
    for linea in compra_input.strip().split('\n'):
        if not linea.strip():
            continue
        # Intentar formato "SÍMBOLO=CANTIDAD,PRECIO" o "SÍMBOLO=PRECIO"
        if '=' in linea:
            partes = linea.split('=', 1)
            if len(partes) == 2:
                sim = partes[0].strip().upper()
                resto = partes[1].strip()
                if ',' in resto:
                    cant_str, prec_str = resto.split(',', 1)
                    try:
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

        # Guardar transacción en historial
        guardar_transaccion(sim, cantidad, precio, "compra")
        PRECIO_COMPRA[sim] = precio

if PRECIO_COMPRA:
    st.sidebar.success(f"✅ {len(PRECIO_COMPRA)} compra(s) registrada(s).")

    usd_mxn, eur_mxn = obtener_tipo_cambio()
    regime_data = obtener_market_regime()
    regime_bonus = regime_data['score_bonus'] if market_regime_check else 0
    trade_capital = capital_total * 0.25  # Capital destinado a trading activo

    lista_acciones = mercado_opciones[mercado_seleccionado]
    total = len(lista_acciones)

    with st.spinner(f"Analizando {total} acciones..."):
        resultados = []
        args_list = [
            (sim, PRECIO_COMPRA, usd_mxn, eur_mxn, fundamentales_check, backtesting_check,
             regime_bonus, trade_capital, riesgo_pct)
            for sim in lista_acciones
        ]
        completados = 0
        progress_bar = st.progress(0)
        status_text = st.empty()
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
            st.warning("⚠️ No se encontraron resultados.")
            st.stop()

        df = pd.DataFrame(resultados)

        # Añadir puntaje fundamental
        if fundamentales_check and 'ROE (%)' in df.columns:
            df['Score Fund'] = df.apply(puntaje_fundamental, axis=1)

        # Separar categorías
        if PRECIO_COMPRA:
            ventas = df[(df['Recomendación'] == 'VENDER') & (df['Símbolo'].isin(PRECIO_COMPRA.keys()))].copy()
        else:
            ventas = pd.DataFrame()
        compras = df[df['Recomendación'].str.startswith('COMPRAR')].sort_values('Score', ascending=False).copy()
        observar = df[df['Recomendación'] == 'OBSERVAR'].sort_values('Score', ascending=False).copy()

        # Filtrar fundamentales
        if filtro_fundamentales and 'ROE (%)' in compras.columns:
            compras = compras[
                compras['ROE (%)'].notna() & compras['Rev Growth (%)'].notna() &
                (compras['ROE (%)'] > 10) & (compras['Rev Growth (%)'] > 5)
            ]

        # Guardar en session_state
        st.session_state['df'] = df
        st.session_state['compras'] = compras
        st.session_state['ventas'] = ventas
        st.session_state['observar'] = observar
        st.session_state['PRECIO_COMPRA'] = PRECIO_COMPRA
        st.session_state['usd_mxn'] = usd_mxn
        st.session_state['eur_mxn'] = eur_mxn
        st.session_state['fund_check'] = fundamentales_check
        st.session_state['regime'] = regime_data
        st.session_state['capital'] = capital_total
        st.session_state['ultima_actualizacion'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        # Análisis IA
        if ia_check and not compras.empty:
            tiene_key = GEMINI_API_KEY or GROQ_API_KEY or ANTHROPIC_API_KEY
            if tiene_key:
                with st.spinner("🤖 Analizando oportunidades con IA..."):
                    top_ops = compras.head(8).to_dict('records')
                    texto_ia = analisis_ia_claude(top_ops, regime_data, usd_mxn)
                    st.session_state['analisis_ia'] = texto_ia
            else:
                st.session_state['analisis_ia'] = ""

        # Alertas (solo se envían al ejecutar el análisis)
        compras_alerta = compras[compras['Score'] >= umbral_score]
        resumen_ia = st.session_state.get('analisis_ia', '')
        if (alerta_email or alerta_whatsapp) and (not compras_alerta.empty or not ventas.empty):
            with st.spinner("📤 Enviando alertas..."):
                if alerta_email:
                    html = construir_email_html(compras_alerta, ventas, resumen_ia)
                    enviar_email(f"📈 Alerta Trading {datetime.now().strftime('%d/%m %H:%M')}", html)
                if alerta_whatsapp:
                    n_compras = len(compras_alerta)
                    n_ventas = len(ventas)
                    top3 = ", ".join(compras_alerta.head(3)['Símbolo'].tolist()) if n_compras else "ninguna"
                    msg = (f"📈 *Alerta Trading* {datetime.now().strftime('%d/%m %H:%M')}\n"
                           f"🟢 Compras: {n_compras} (Top: {top3})\n🔴 Ventas: {n_ventas}\nUmbral score: {umbral_score}")
                    enviar_whatsapp(msg)

        st.success(f"✅ Análisis completado. {len(compras)} oportunidades de compra encontradas.")
        st.rerun()

# ============================================================
# PRESENTACIÓN DE RESULTADOS (basada en session_state)
# ============================================================
if 'df' in st.session_state:
    df = st.session_state['df']
    compras = st.session_state['compras']
    ventas = st.session_state['ventas']
    observar = st.session_state['observar']
    usd_mxn = st.session_state['usd_mxn']
    eur_mxn = st.session_state['eur_mxn']
    fundamentales_check = st.session_state['fund_check']
    regime_data = st.session_state['regime']

    st.markdown(f"**Última actualización:** {st.session_state.get('ultima_actualizacion', 'Nunca')}")
    evitar = df[df['Recomendación'] == 'EVITAR']
    # Mostrar resumen del market regime
    icono_regime = {'ALCISTA':'🟢','LATERAL':'🟡','BAJISTA':'🔴','DESCONOCIDO':'⚪'}.get(regime_data.get('regime','DESCONOCIDO'),'⚪')
    with st.expander(f"{icono_regime} Market Regime: **{regime_data.get('regime','DESCONOCIDO')}** — {regime_data.get('descripcion','')}", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("S&P 500",    f"{regime_data.get('precio',0):,.0f}")
        c2.metric("EMA 200",    f"{regime_data.get('ema200',0):,.0f}")
        c3.metric("RSI S&P",    f"{regime_data.get('rsi_sp500',0)}")
        c4.metric("Ret. 1 mes", f"{regime_data.get('ret_1m',0):+.1f}%")

    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Compras",    len(compras))
    col2.metric("🔴 Ventas",     len(ventas))
    col3.metric("👀 Observar",   len(observar))
    col4.metric("🚫 Evitar",     len(evitar))

    # Tabs de resultados
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🟢 COMPRAS", "🔴 VENTAS", "🟡 OBSERVAR", "🔍 TODAS", "📜 HISTORIAL", "🚫 Evitar"])

    cols_base = ['Símbolo','Precio (MXN)','Score','RSI','ATR','Stop Loss','Take Profit',
                 'Unidades','Inversión (MXN)','% Capital','Dist EMA50','Recomendación','Motivo','Señales']
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
            st.caption(f"Mostrando señales de venta únicamente para tus {len(st.session_state.get('PRECIO_COMPRA',{}))} acción(es) registradas.")
            show_df(ventas, cols_fund if fundamentales_check else [])
        elif st.session_state.get('PRECIO_COMPRA'):
            st.info("✅ Ninguna de tus acciones registradas tiene señal de venta en este momento.")
        else:
            st.warning("⚠️ No has registrado ninguna compra. Ingresa tus acciones en el panel lateral para recibir recomendaciones de venta.")

    with tab3:
        show_df(observar.head(20), cols_fund if fundamentales_check else [])

    with tab4:
        st.dataframe(df.reset_index(drop=True), use_container_width=True)

    with tab5:
        st.subheader("📜 Historial de señales guardadas")
        historial_path = "historial_senales.csv"
        if os.path.exists(historial_path):
            df_hist = pd.read_csv(historial_path)
            df_hist['fecha'] = pd.to_datetime(df_hist['fecha'])
            st.dataframe(df_hist.sort_values('fecha', ascending=False).head(50), use_container_width=True)
            st.subheader("🧪 Evaluación de efectividad (backtesting)")
            with st.spinner("Calculando retornos históricos..."):
                resultados_bt = []
                for _, row in df_hist.iterrows():
                    try:
                        ticker = yf.Ticker(row['simbolo'])
                        start = row['fecha']
                        end = datetime.now()
                        hist = ticker.history(start=start, end=end)
                        if hist.empty:
                            continue
                        idx = hist.index.searchsorted(start)
                        if idx + 5 >= len(hist):
                            continue
                        precio_entrada = row['precio']
                        precio_salida = hist['Close'].iloc[idx + 5]
                        ret = (precio_salida / precio_entrada - 1) * 100
                        resultados_bt.append(ret)
                    except:
                        continue
                if resultados_bt:
                    win_rate = sum(1 for r in resultados_bt if r > 0) / len(resultados_bt) * 100
                    ret_prom = np.mean(resultados_bt)
                    cola, colb, colc = st.columns(3)
                    cola.metric("📊 Total señales evaluadas", len(resultados_bt))
                    colb.metric("✅ Win rate", f"{win_rate:.1f}%")
                    colc.metric("📈 Retorno promedio", f"{ret_prom:.2f}%")
                    st.caption("Backtesting sobre señales pasadas, usando ventana de 5 días hábiles.")
                else:
                    st.info("No hay suficientes datos históricos para backtesting aún.")
        else:
            st.info("Aún no hay historial de señales. El scanner automático generará el archivo después de algunas ejecuciones.")

    # Análisis IA (si existe)
    if 'analisis_ia' in st.session_state and st.session_state['analisis_ia']:
        with st.expander("🤖 Análisis de IA", expanded=True):
            st.markdown(st.session_state['analisis_ia'])
            st.caption("Este análisis es generado por IA con fines informativos. No constituye asesoría financiera.")

    # Gráfico de la mejor oportunidad
    if not compras.empty:
        mejor = compras.iloc[0]['Símbolo']
        st.subheader(f"📊 Análisis completo: {mejor}")
        fig = grafico_enriquecido(mejor, usd_mxn, eur_mxn)
        st.plotly_chart(fig, use_container_width=True)

        top10 = compras.head(10)
        fig_score = px.bar(top10, x='Símbolo', y='Score', color='Score', color_continuous_scale='RdYlGn', text='Score', title="Top 10 — Score ponderado de compra (máx 14 pts)")
        fig_score.add_hline(y=8, line_dash="dash", line_color="green", annotation_text="Compra fuerte")
        fig_score.add_hline(y=6, line_dash="dash", line_color="orange", annotation_text="Compra moderada")
        fig_score.update_traces(textposition='outside')
        fig_score.update_layout(showlegend=False, height=420, template='plotly_dark')
        st.plotly_chart(fig_score, use_container_width=True)

    # Descarga Excel
    try:
        import openpyxl  # noqa: F401
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            compras.to_excel(writer, index=False, sheet_name='Compras')
            ventas.to_excel(writer, index=False, sheet_name='Ventas')
            observar.to_excel(writer, index=False, sheet_name='Observar')
            df.to_excel(writer, index=False, sheet_name='Todos')
        st.download_button(
            label="📥 Descargar informe Excel",
            data=output.getvalue(),
            file_name=f"trading_v2_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except ImportError:
        st.warning("⚠️ openpyxl no instalado. No se puede generar Excel.")
# ============================================================
# HISTORIAL DE TRANSACCIONES (NUEVO)
# ============================================================
st.divider()
st.subheader("📜 Historial de transacciones")
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
    st.info("Aún no hay transacciones registradas. Usa el panel lateral para añadir compras.")
# ============================================================
# SELECTOR DE GRÁFICO PARA EXPLORAR ACCIONES
# ============================================================
if 'df' in st.session_state:
    st.divider()
    st.subheader("🔎 Explorar cualquier acción analizada")
    todos_simbolos = st.session_state['df']['Símbolo'].tolist()
    sim_elegido = st.selectbox("Selecciona un símbolo para ver su gráfico completo", todos_simbolos, key="selector_grafico")
    if sim_elegido:
        fila = st.session_state['df'][st.session_state['df']['Símbolo'] == sim_elegido].iloc[0]
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
        fig2 = grafico_enriquecido(sim_elegido, st.session_state['usd_mxn'], st.session_state['eur_mxn'])
        st.plotly_chart(fig2, use_container_width=True)
