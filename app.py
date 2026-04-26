import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests as curl_requests
import time

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="La Abi - chuela | Enterprise Trading System", layout="wide")

# --- PARCHE DE RESILIENCIA PARA YAHOO FINANCE ---
def _patched_session():
    return curl_requests.Session(impersonate="chrome124")

yf.shared._requests = _patched_session

# ============================================================
# CLASE NÚCLEO: INTELIGENCIA DE MERCADO
# ============================================================
class TradingEngine:
    """Gestiona el escaneo masivo y la lógica de indicadores técnicos."""
    
    @staticmethod
    def calcular_indicadores(df):
        """Cálculos vectorizados de alta velocidad."""
        if df.empty or len(df) < 14: return df
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # Medias Móviles
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        # Volatilidad (ATR simplificado)
        df['Volatilidad'] = df['Close'].pct_change().rolling(window=10).std()
        
        return df

    @staticmethod
    def generar_score(fila):
        """Lógica de ADN de éxito del código anterior integrada."""
        score = 0
        # Puntos por RSI (Zona de valor)
        if 30 <= fila['RSI'] <= 50: score += 40
        elif fila['RSI'] < 30: score += 20
        
        # Puntos por Tendencia
        if fila['Precio'] > fila['EMA_20']: score += 30
        if fila['EMA_20'] > fila['EMA_50']: score += 30
        
        return score

    @classmethod
    @st.cache_data(ttl=600)
    def procesar_activo(cls, ticker_sym, usd_rate):
        """Procesa un solo activo con reintentos."""
        try:
            ticker = yf.Ticker(ticker_sym)
            hist = ticker.history(period="1y", interval="1d", timeout=10)
            if hist.empty: return None
            
            df = cls.calcular_indicadores(hist)
            ultimo = df.iloc[-1]
            penultimo = df.iloc[-2]
            
            precio_mxn = ultimo['Close'] * usd_rate
            
            data = {
                "Símbolo": ticker_sym,
                "Precio (MXN)": round(precio_mxn, 2),
                "RSI": round(ultimo['RSI'], 2),
                "EMA_20": ultimo['EMA_20'],
                "EMA_50": ultimo['EMA_50'],
                "Precio": ultimo['Close'],
                "Variación %": round(((ultimo['Close'] / penultimo['Close']) - 1) * 100, 2)
            }
            
            data["Score"] = cls.generar_score(data)
            data["Recomendación"] = "COMPRA" if data["Score"] >= 70 else "NEUTRAL"
            return data
        except Exception:
            return None

# ============================================================
# CAPA DE INTERFAZ (UI MODULAR)
# ============================================================
def main():
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2422/2422796.png", width=100)
    st.sidebar.title("La Abi - chuela v4.0")
    
    # 1. Gestión de Divisas (Caché funcional)
    @st.cache_data(ttl=3600)
    def get_usd_mxn():
        try:
            d = yf.download("USDMXN=X", period="1d", interval="1m", progress=False)
            return d['Close'].iloc[-1]
        except: return 20.0

    usd_rate = get_usd_mxn()
    
    # 2. Selección de Universo
    universo_input = st.sidebar.text_area("Lista de Tickers (separados por coma)", 
                                        "AAPL, MSFT, GOOGL, TSLA, AMZN, META, NVDA, AMD, NFLX")
    tickers = [t.strip().upper() for t in universo_input.split(",")]
    
    num_threads = st.sidebar.slider("Hilos de procesamiento (Escalabilidad)", 1, 20, 10)

    # 3. Ejecución del Escáner
    if st.sidebar.button("🔍 Iniciar Escaneo de Alto Rendimiento"):
        st.session_state['ejecutado'] = True
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        resultados = []
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {executor.submit(TradingEngine.procesar_activo, t, usd_rate): t for t in tickers}
            
            for i, future in enumerate(as_completed(futures)):
                res = future.result()
                if res: resultados.append(res)
                progress_bar.progress((i + 1) / len(tickers))
                status_text.text(f"Procesando: {futures[future]}")
        
        st.session_state['df_resultados'] = pd.DataFrame(resultados)
        st.success(f"Análisis completado: {len(resultados)} activos procesados.")

    # 4. Visualización de Resultados (Dashboard Integrado)
    if st.session_state.get('ejecutado'):
        df = st.session_state['df_resultados']
        
        # Métricas principales
        m1, m2, m3 = st.columns(3)
        m1.metric("Tipo de Cambio", f"${usd_rate:.2f} MXN")
        m2.metric("Oportunidades de Compra", len(df[df['Recomendación'] == 'COMPRA']))
        m3.metric("RSI Promedio", f"{df['RSI'].mean():.1f}")

        # Tabla Maestra
        st.subheader("📋 Resultados del Escaneo")
        st.dataframe(
            df.sort_values(by="Score", ascending=False),
            use_container_width=True,
            column_config={
                "Score": st.column_config.ProgressColumn("Puntaje ADN", min_value=0, max_value=100),
                "Variación %": st.column_config.NumberColumn(format="%.2f%%"),
                "Precio (MXN)": st.column_config.NumberColumn(format="$%.2f")
            }
        )

        # Gráfico de Dispersión (Sentiment vs Value)
        st.subheader("📊 Mapa de Oportunidades")
        fig = go.Figure(data=go.Scatter(
            x=df['RSI'], y=df['Score'],
            mode='markers+text',
            text=df['Símbolo'],
            marker=dict(size=df['Variación %'].abs()*5, color=df['Score'], colorscale='Viridis', showscale=True)
        ))
        fig.update_layout(xaxis_title="RSI (Sobreventa < 30)", yaxis_title="Score de Éxito")
        st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()
