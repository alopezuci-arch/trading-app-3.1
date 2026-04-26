import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests as curl_requests
import time
import warnings

# --- CONFIGURACIÓN DE SEGURIDAD Y ENTORNO ---
warnings.filterwarnings('ignore')
st.set_page_config(
    page_title="La Abi - chuela | Market Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Parche de Resiliencia para evitar bloqueos de Yahoo Finance
def _patched_session():
    return curl_requests.Session(impersonate="chrome124")
yf.shared._requests = _patched_session

# ============================================================
# CAPA 1: LÓGICA FINANCIERA ESCALABLE (BACKEND)
# ============================================================
class TradingEngine:
    """Procesamiento multihilo y cálculos vectorizados."""
    
    @staticmethod
    def calcular_indicadores(df):
        """Cálculos en bloque (Vectorizados) para máxima velocidad."""
        if df.empty or len(df) < 20: return df
        
        # RSI con método de suavizado estándar
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # Medias Móviles Exponenciales
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        # Volatilidad Relativa
        df['Volatilidad'] = df['Close'].pct_change().rolling(window=10).std()
        
        return df

    @staticmethod
    def ADN_exito_score(data):
        """Lógica de scoring personalizada para 'La Abi - chuela'."""
        score = 0
        rsi = data.get('RSI', 50)
        precio = data.get('Precio', 0)
        ema20 = data.get('EMA_20', 0)
        ema50 = data.get('EMA_50', 0)

        # 1. Análisis de Sobreventa (Oportunidad)
        if rsi <= 35: score += 40  # Muy atractivo
        elif rsi <= 50: score += 20
        
        # 2. Análisis de Tendencia (Confirmación)
        if precio > ema20: score += 30
        if ema20 > ema50: score += 30
        
        return min(score, 100)

    @classmethod
    def procesar_activo(cls, ticker_sym, usd_rate):
        """Unidad de trabajo para los hilos de ejecución."""
        try:
            ticker = yf.Ticker(ticker_sym)
            hist = ticker.history(period="1y", interval="1d", timeout=7)
            if hist.empty or len(hist) < 20: return None
            
            df = cls.calcular_indicadores(hist)
            u = df.iloc[-1]
            p = df.iloc[-2]
            
            row = {
                "Símbolo": ticker_sym,
                "Precio (USD)": u['Close'],
                "Precio (MXN)": round(u['Close'] * usd_rate, 2),
                "Variación %": round(((u['Close'] / p['Close']) - 1) * 100, 2),
                "RSI": round(u['RSI'], 2),
                "EMA_20": u['EMA_20'],
                "EMA_50": u['EMA_50'],
                "Precio": u['Close']
            }
            
            row["Score"] = cls.ADN_exito_score(row)
            row["Recomendación"] = "COMPRA" if row["Score"] >= 70 else "MANTENER" if row["Score"] >= 40 else "EVITAR"
            return row
        except:
            return None

# ============================================================
# CAPA 2: INTERFAZ Y ORQUESTACIÓN (FRONTEND)
# ============================================================
def main():
    # --- Sidebar de Control ---
    st.sidebar.markdown(f"## 🥑 La Abi - chuela \n**v4.5 Enterprise**")
    st.sidebar.divider()
    
    # Parámetros de Escalabilidad
    with st.sidebar.expander("⚙️ Configuración de Red", expanded=False):
        num_threads = st.slider("Hilos en paralelo", 1, 20, 12)
        timeout_api = st.slider("Timeout API (seg)", 5, 15, 7)

    # Universo de Activos
    input_tickers = st.sidebar.text_area(
        "Lista de Tickers", 
        "AAPL, MSFT, GOOGL, AMZN, TSLA, META, NVDA, NFLX, AMD, PYPL, DIS, BABA",
        help="Separa los símbolos por comas"
    )
    tickers = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]

    # --- Lógica de Tipo de Cambio (Caché optimizada) ---
    @st.cache_data(ttl=3600)
    def get_exchange_rate():
        try:
            data = yf.download("USDMXN=X", period="1d", interval="1m", progress=False)
            return data['Close'].iloc[-1]
        except: return 18.50 # Fallback seguro

    usd_rate = get_exchange_rate()

    # --- Ejecución del Escáner ---
    if st.sidebar.button("🚀 Lanzar Escaneo Masivo", use_container_width=True):
        st.session_state['ejecutado'] = True
        progreso = st.progress(0)
        status = st.empty()
        
        resultados = []
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {executor.submit(TradingEngine.procesar_activo, t, usd_rate): t for t in tickers}
            
            for i, future in enumerate(as_completed(futures)):
                res = future.result()
                if res: resultados.append(res)
                progreso.progress((i + 1) / len(tickers))
                status.caption(f"Analizando: {futures[future]}...")
        
        st.session_state['df_master'] = pd.DataFrame(resultados)
        status.empty()
        progreso.empty()

    # --- Dashboard de Resultados ---
    if st.session_state.get('ejecutado'):
        df = st.session_state['df_master']
        
        # 1. KPIs Superiores
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Activos OK", len(df))
        c2.metric("Oportunidades", len(df[df['Score'] >= 70]))
        c3.metric("USD/MXN", f"${usd_rate:.2f}")
        c4.metric("Sentimiento", "Bullish" if df['Score'].mean() > 50 else "Cautela")

        # 2. Tabla Maestra Escalable
        st.subheader("📋 Monitor de Mercado")
        
        def color_score(val):
            color = '#00ff00' if val >= 70 else '#ff9900' if val >= 40 else '#ff4b4b'
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            df.sort_values(by="Score", ascending=False).style.applymap(color_score, subset=['Score']),
            use_container_width=True,
            column_config={
                "Score": st.column_config.ProgressColumn("Puntaje ADN", min_value=0, max_value=100),
                "Variación %": st.column_config.NumberColumn(format="%.2f%%"),
                "Precio (MXN)": st.column_config.NumberColumn(format="$%.2f")
            },
            hide_index=True
        )

        # 3. Análisis Visual (Heatmap de Oportunidad)
        st.divider()
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.subheader("🎯 Mapa de Valor vs RSI")
            fig = go.Figure(data=go.Scatter(
                x=df['RSI'], y=df['Score'],
                mode='markers+text',
                text=df['Símbolo'],
                textposition="top center",
                marker=dict(
                    size=15,
                    color=df['Score'],
                    colorscale='RdYlGn',
                    showscale=True,
                    line=dict(width=1, color='white')
                )
            ))
            fig.update_layout(xaxis_title="RSI (Bajo = Sobreventa)", yaxis_title="Score ADN", height=450)
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.subheader("🔥 Top Oportunidades (Score > 70)")
            top_df = df[df['Score'] >= 70][['Símbolo', 'RSI', 'Recomendación']].reset_index(drop=True)
            if not top_df.empty:
                st.table(top_df)
            else:
                st.info("Buscando señales fuertes en el mercado...")

if __name__ == "__main__":
    if 'ejecutado' not in st.session_state:
        st.session_state['ejecutado'] = False
    main()
