import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import requests
import base64
from typing import List, Dict, Any, Optional

# --- CONFIGURACIÓN DE ESTADO DE ALTA DISPONIBILIDAD ---
st.set_page_config(page_title="La Abi - chuela | Market Intelligence", layout="wide")

# --- CAPA DE ABSTRACCIÓN DE DATOS (DATA ACCESS LAYER) ---
class MarketDataEngine:
    """Clase optimizada para concurrencia y manejo masivo de activos."""
    
    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self.results = []

    @st.cache_data(ttl=900) # Caché de 15 min para evitar throttling de API
    def _fetch_single_ticker(ticker_sym: str) -> Optional[Dict]:
        try:
            ticker = yf.Ticker(ticker_sym)
            hist = ticker.history(period="1y", interval="1d", timeout=5)
            if hist.empty or len(hist) < 30:
                return None
            
            # Cálculo de indicadores vectorizado (Escalabilidad de CPU)
            close = hist['Close']
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return {
                "Símbolo": ticker_sym,
                "Precio": close.iloc[-1],
                "RSI": rsi.iloc[-1],
                "Variación %": ((close.iloc[-1] / close.iloc[-2]) - 1) * 100
            }
        except Exception:
            return None

    def run_parallel_scan(self, workers: int = 10):
        """Ejecución multihilo para procesamiento masivo."""
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(MarketDataEngine._fetch_single_ticker, t): t for t in self.tickers}
            for future in as_completed(futures):
                res = future.result()
                if res:
                    self.results.append(res)
        return pd.DataFrame(self.results)

# --- SISTEMA DE PERSISTENCIA BASADO EN SECRETS ---
class CloudStorage:
    """Simulación de capa de persistencia escalable."""
    @staticmethod
    def sync_to_cloud(data: pd.DataFrame):
        # Aquí se integraría con AWS S3, MongoDB o GitHub API
        # Por ahora, usamos el estado de sesión de forma eficiente
        st.session_state['last_sync'] = datetime.now()
        return True

# --- INTERFAZ DE USUARIO MODULAR ---
def render_header():
    st.title("📈 La Abi - chuela: Enterprise Scanner")
    st.markdown("---")

def render_dashboard(df: pd.DataFrame):
    if df.empty:
        st.warning("No se encontraron datos para los activos seleccionados.")
        return

    # Métricas de alto nivel
    cols = st.columns(4)
    cols[0].metric("Activos Analizados", len(df))
    cols[1].metric("Promedio RSI", f"{df['RSI'].mean():.2f}")
    cols[2].metric("Top Ganador", df.loc[df['Variación %'].idxmax()]['Símbolo'])
    cols[3].metric("Última Sincronización", st.session_state.get('last_sync', 'N/A').strftime("%H:%M:%S"))

    # Tabla dinámica escalable
    st.dataframe(
        df.sort_values("RSI", ascending=False),
        use_container_width=True,
        column_config={
            "RSI": st.column_config.ProgressColumn("Nivel RSI", min_value=0, max_value=100),
            "Precio": st.column_config.NumberColumn(format="$%.2f")
        }
    )

# --- FLUJO PRINCIPAL ---
def main():
    render_header()
    
    # Simulación de carga de universo de activos (Escalable a miles)
    universos = {
        "S&P 500": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "BRK-B"],
        "Crypto Top": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"]
    }
    
    seleccion = st.sidebar.multiselect("Seleccionar Universos", list(universos.keys()), default=["S&P 500"])
    
    # Aplanamos la lista de tickers
    tickers_to_scan = []
    for u in seleccion:
        tickers_to_scan.extend(universos[u])

    if st.sidebar.button("Ejecutar Análisis Global"):
        with st.spinner("Procesando datos en paralelo..."):
            engine = MarketDataEngine(tickers_to_scan)
            df_final = engine.run_parallel_scan()
            CloudStorage.sync_to_cloud(df_final)
            st.session_state['df_cache'] = df_final
            
    if 'df_cache' in st.session_state:
        render_dashboard(st.session_state['df_cache'])

if __name__ == "__main__":
    main()
