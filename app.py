# ============================================
# SISTEMA DE TRADING PROFESIONAL - STREAMLIT
# ============================================

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import time
import requests
import urllib3
import ssl

# Configuración SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# --------------------------------------------------
# Configuración de la página
# --------------------------------------------------
st.set_page_config(page_title="Trading System", layout="wide", page_icon="📈")
st.title("📈 Mi Sistema de Trading Personal")
st.markdown(f"**Última actualización:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")

# --------------------------------------------------
# Sidebar - Parámetros y compras
# --------------------------------------------------
st.sidebar.header("⚙️ Parámetros")

# Selector de mercado
mercado_opciones = {
    "Prueba (AAPL, MSFT, NVDA)": ['AAPL', 'MSFT', 'NVDA'],
    "S&P 100": None,  # se cargarán después
    "S&P 500 (completo)": None,
    "NASDAQ 100": None,
    "IBEX 35": None,
    "BMV": None,
    "Todos (completo)": None
}
mercado_seleccionado = st.sidebar.selectbox("📊 Mercado", list(mercado_opciones.keys()), index=0)

# Cargar listas de acciones (se hará después de definir las listas)
# Las definiremos más abajo y luego las asignaremos a mercado_opciones.

# Registro de compras
st.sidebar.markdown("### 💰 Registrar compras")
compra_input = st.sidebar.text_area(
    "Formato: SÍMBOLO=PRECIO (MXN)",
    placeholder="AAPL=4465.53, WALMEX.MX=56.13",
    height=100
)

# Checkbox para análisis de noticias (requiere API key)
noticias_check = st.sidebar.checkbox("📰 Analizar noticias (requiere API key)", value=False)
if noticias_check:
    hf_api_key = st.sidebar.text_input("🔑 Hugging Face API Key (opcional)", type="password", help="Obtén una gratis en huggingface.co")
else:
    hf_api_key = None

# Botón de análisis
if st.sidebar.button("🔍 ANALIZAR", type="primary"):
    # --------------------------------------------------
    # Cargar listas de acciones
    # --------------------------------------------------
    @st.cache_data(ttl=3600)
    def obtener_sp500():
        try:
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            tables = pd.read_html(url)
            sp500 = tables[0]['Symbol'].tolist()
            sp500 = [s.replace('.', '-') for s in sp500]
            return sp500
        except:
            return []

    @st.cache_data(ttl=3600)
    def cargar_listas():
        sp500 = obtener_sp500()
        sp100 = [
            'AAPL', 'MSFT', 'AMZN', 'NVDA', 'META', 'GOOGL', 'GOOG', 'BRK-B', 'JPM', 'V',
            'JNJ', 'WMT', 'PG', 'UNH', 'HD', 'DIS', 'MA', 'BAC', 'XOM', 'CVX',
            'KO', 'PEP', 'ADBE', 'CRM', 'NFLX', 'TMO', 'ABT', 'ACN', 'AMD', 'INTC',
            'CMCSA', 'TXN', 'QCOM', 'COST', 'NKE', 'MRK', 'ABBV', 'LLY', 'PFE', 'BMY',
            'CVS', 'HON', 'UPS', 'BA', 'CAT', 'GE', 'IBM', 'GS', 'SPGI', 'MS',
            'PLD', 'LMT', 'MDT', 'ISRG', 'BLK', 'AMGN', 'GILD', 'FISV', 'SYK', 'ZTS',
            'T', 'VZ', 'NEE', 'DUK', 'SO', 'MO', 'PM', 'MDLZ', 'SBUX', 'MCD',
            'LOW', 'TGT', 'TJX', 'ORCL', 'NOW', 'INTU', 'BKNG', 'UBER', 'TSLA', 'AVGO'
        ]
        nasdaq100 = [
            'ADBE', 'AMD', 'AMGN', 'AMZN', 'ASML', 'AVGO', 'BIIB', 'BKNG', 'CDNS', 'CHTR',
            'CMCSA', 'COST', 'CSCO', 'CSX', 'CTAS', 'DXCM', 'EA', 'EBAY', 'EXC', 'FANG',
            'FAST', 'FTNT', 'GILD', 'GOOGL', 'GOOG', 'HON', 'IDXX', 'ILMN', 'INTC', 'INTU',
            'ISRG', 'KDP', 'KLAC', 'LRCX', 'LULU', 'MAR', 'MELI', 'META', 'MNST', 'MSFT',
            'MU', 'NFLX', 'NVDA', 'NXPI', 'ODFL', 'ORLY', 'PANW', 'PAYX', 'PCAR', 'PDD',
            'PEP', 'QCOM', 'REGN', 'ROST', 'SBUX', 'SGEN', 'SIRI', 'SNPS', 'SPLK', 'SWKS',
            'TCOM', 'TEAM', 'TMUS', 'TSLA', 'TTD', 'TXN', 'VRTX', 'WBA', 'WDAY', 'XEL',
            'ZM', 'ZS'
        ]
        ibex35 = [
            'SAN.MC', 'BBVA.MC', 'TEF.MC', 'ITX.MC', 'IBE.MC', 'FER.MC', 'ENG.MC',
            'ACS.MC', 'REP.MC', 'AENA.MC', 'CLNX.MC', 'GRF.MC', 'MTS.MC', 'MAP.MC',
            'MEL.MC', 'CABK.MC', 'ELE.MC', 'SGRE.MC', 'SLR.MC', 'UNI.MC', 'IAG.MC',
            'ANA.MC', 'VIS.MC', 'CIE.MC', 'LOG.MC', 'ACX.MC', 'FLR.MC', 'ECR.MC',
            'FCC.MC', 'GAM.MC', 'IDR.MC', 'LRE.MC', 'NTGY.MC', 'PHM.MC', 'TRE.MC'
        ]
        bmv = [
            'WALMEX.MX', 'GMEXICOB.MX', 'CEMEXCPO.MX', 'FEMSAUBD.MX', 'AMXL.MX',
            'KOFUBL.MX', 'GFNORTEO.MX', 'BBAJIOO.MX', 'ALFA.MX', 'ALPEKA.MX',
            'ASURB.MX', 'GAPB.MX', 'OMAB.MX', 'AC.MX', 'GCARSOA1.MX',
            'GCC.MX', 'LALA.MX', 'MEGA.MX', 'PINFRA.MX', 'RA.MX',
            'TLEVISACPO.MX', 'VESTA.MX', 'VOLARA.MX', 'Q.MX', 'LABB.MX',
            'GRUMA.MX', 'HERDEZ.MX', 'CUERVO.MX', 'NEMAKA.MX', 'ORBIA.MX'
        ]
        return sp100, nasdaq100, ibex35, bmv, sp500

    sp100, nasdaq100, ibex35, bmv, sp500 = cargar_listas()

    # Asignar listas a las opciones
    mercado_opciones["S&P 100"] = sp100
    mercado_opciones["S&P 500 (completo)"] = sp500
    mercado_opciones["NASDAQ 100"] = nasdaq100
    mercado_opciones["IBEX 35"] = ibex35
    mercado_opciones["BMV"] = bmv
    mercado_opciones["Todos (completo)"] = sp500 + nasdaq100 + ibex35 + bmv

    # Obtener lista seleccionada
    lista_acciones = mercado_opciones[mercado_seleccionado]

    # --------------------------------------------------
    # Obtener tipos de cambio
    # --------------------------------------------------
    @st.cache_data(ttl=3600)
    def obtener_tipo_cambio():
        try:
            usd = yf.Ticker("USDMXN=X").history(period="1d")
            usd_mxn = usd['Close'].iloc[-1] if not usd.empty else 20.0
            eur = yf.Ticker("EURMXN=X").history(period="1d")
            eur_mxn = eur['Close'].iloc[-1] if not eur.empty else 21.5
            return float(usd_mxn), float(eur_mxn)
        except:
            return 20.0, 21.5

    usd_mxn, eur_mxn = obtener_tipo_cambio()
    st.sidebar.metric("USD/MXN", f"{usd_mxn:.2f}")
    st.sidebar.metric("EUR/MXN", f"{eur_mxn:.2f}")

    # --------------------------------------------------
    # Procesar compras
    # --------------------------------------------------
    PRECIO_COMPRA = {}
    if compra_input:
        for par in compra_input.replace('\n', ',').split(','):
            if '=' in par:
                sim, precio = par.split('=')
                sim = sim.strip().upper()
                try:
                    PRECIO_COMPRA[sim] = float(precio.strip())
                except:
                    pass
        if PRECIO_COMPRA:
            st.sidebar.success(f"{len(PRECIO_COMPRA)} compras registradas.")

    # --------------------------------------------------
    # Función de análisis técnico (igual a la de Colab)
    # --------------------------------------------------
    def analizar_accion(simbolo):
        try:
            ticker = yf.Ticker(simbolo)
            hist = ticker.history(period="3mo")
            if hist.empty or len(hist) < 50:
                return None

            # Conversión a MXN
            if simbolo.endswith('.MX'):
                factor = 1.0
            elif simbolo.endswith('.MC'):
                factor = eur_mxn
            else:
                factor = usd_mxn

            hist['Close'] = hist['Close'] * factor
            hist['Open'] = hist['Open'] * factor
            hist['High'] = hist['High'] * factor
            hist['Low'] = hist['Low'] * factor

            # Indicadores
            hist['EMA20'] = hist['Close'].ewm(span=20, adjust=False).mean()
            hist['EMA50'] = hist['Close'].ewm(span=50, adjust=False).mean()

            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            hist['RSI'] = 100 - (100 / (1 + rs))

            hist['EMA12'] = hist['Close'].ewm(span=12, adjust=False).mean()
            hist['EMA26'] = hist['Close'].ewm(span=26, adjust=False).mean()
            hist['MACD'] = hist['EMA12'] - hist['EMA26']
            hist['MACD_signal'] = hist['MACD'].ewm(span=9, adjust=False).mean()

            ultimo = hist.iloc[-1].to_dict()
            penultimo = hist.iloc[-2].to_dict() if len(hist) >= 2 else None

            precio = ultimo['Close']
            ema20 = ultimo['EMA20']
            ema50 = ultimo['EMA50']
            rsi = ultimo['RSI']
            vol = ultimo['Volume']
            macd = ultimo['MACD']
            macd_signal = ultimo['MACD_signal']

            compra = []
            if ema20 > ema50:
                compra.append("EMA alcista")
            if 50 <= rsi <= 70:
                compra.append(f"RSI {rsi:.0f}")
            vol_medio = hist['Volume'].rolling(20).mean().iloc[-1]
            if vol > vol_medio * 1.2:
                compra.append("Volumen alto")
            if macd > macd_signal:
                compra.append("MACD+")

            venta = []
            if simbolo in PRECIO_COMPRA:
                precio_compra = PRECIO_COMPRA[simbolo]
                ganancia = ((precio / precio_compra) - 1) * 100
                if ganancia >= 15:
                    venta.append(f"🎯 Take Profit +{ganancia:.1f}%")
                elif ganancia <= -7:
                    venta.append(f"🛑 Stop Loss {ganancia:.1f}%")
                if penultimo and penultimo['EMA20'] > penultimo['EMA50'] and ema20 < ema50:
                    venta.append("⚠️ Tendencia bajista")
                if rsi > 80 and penultimo and rsi < penultimo['RSI']:
                    venta.append("📉 RSI sobrecomprado")

            if venta:
                recomendacion = "VENDER"
                motivo = venta[0]
            elif len(compra) >= 3:
                recomendacion = "COMPRAR"
                motivo = f"{len(compra)}/4 señales"
            elif len(compra) >= 2:
                recomendacion = "OBSERVAR"
                motivo = "Posible compra"
            else:
                recomendacion = "EVITAR"
                motivo = "Sin señales"

            dist_ema50 = ((precio / ema50) - 1) * 100

            return {
                'Símbolo': simbolo,
                'Precio (MXN)': f"{precio:.2f}",
                'RSI': f"{rsi:.0f}" if not np.isnan(rsi) else "N/A",
                'Distancia EMA50': f"{dist_ema50:.1f}%",
                'Recomendación': recomendacion,
                'Motivo': motivo
            }
        except:
            return None

    # --------------------------------------------------
    # Función de análisis de noticias con IA (Hugging Face)
    # --------------------------------------------------
    def analizar_noticias(simbolo):
        if not noticias_check or not hf_api_key:
            return "No se solicitó análisis de noticias."
        try:
            # Buscar noticias recientes (simulado con NewsAPI, pero usaremos una alternativa gratuita)
            # Para evitar depender de NewsAPI (requiere clave), usaremos una búsqueda con Google News RSS vía API de terceros.
            # Aquí simulamos con una respuesta estática para no complicar la primera versión.
            # En la versión real, integraríamos NewsAPI o scraping de Google News.
            # Por ahora retornamos un mensaje de que la funcionalidad está en desarrollo.
            return "Funcionalidad de análisis de noticias con IA en desarrollo. Próximamente."
        except Exception as e:
            return f"Error: {e}"

    # --------------------------------------------------
    # Ejecutar análisis
    # --------------------------------------------------
    with st.spinner(f"Analizando {len(lista_acciones)} acciones..."):
        resultados = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        for i, sim in enumerate(lista_acciones):
            status_text.text(f"Analizando {i+1}/{len(lista_acciones)}: {sim}")
            res = analizar_accion(sim)
            if res:
                resultados.append(res)
            progress_bar.progress((i+1)/len(lista_acciones))
            time.sleep(0.3)  # Pausa para no saturar Yahoo
        status_text.empty()
        progress_bar.empty()

    df = pd.DataFrame(resultados)

    if df.empty:
        st.warning("⚠️ No se encontraron oportunidades en este análisis.")
        st.stop()

    # --------------------------------------------------
    # Mostrar resultados
    # --------------------------------------------------
    ventas = df[df['Recomendación'] == 'VENDER']
    compras = df[df['Recomendación'] == 'COMPRAR']
    observar = df[df['Recomendación'] == 'OBSERVAR']

    tab1, tab2, tab3 = st.tabs(["🟢 COMPRAS", "🔴 VENTAS", "🟡 OBSERVACIÓN"])

    with tab1:
        if not compras.empty:
            st.dataframe(compras[['Símbolo','Precio (MXN)','RSI','Distancia EMA50','Motivo']], use_container_width=True)
        else:
            st.info("No hay oportunidades de compra en este momento.")

    with tab2:
        if not ventas.empty:
            st.dataframe(ventas[['Símbolo','Precio (MXN)','RSI','Distancia EMA50','Motivo']], use_container_width=True)
        else:
            st.info("No hay señales de venta.")

    with tab3:
        if not observar.empty:
            st.dataframe(observar[['Símbolo','Precio (MXN)','RSI','Distancia EMA50','Motivo']].head(15), use_container_width=True)
        else:
            st.info("No hay acciones en observación.")

    # --------------------------------------------------
    # Análisis de noticias para acciones destacadas
    # --------------------------------------------------
    if noticias_check and hf_api_key and (not compras.empty or not ventas.empty):
        st.subheader("📰 Análisis de noticias con IA")
        for nombre, df_cat in [('COMPRA', compras), ('VENTA', ventas)]:
            if not df_cat.empty:
                with st.expander(f"{nombre} - Noticias relevantes"):
                    for _, row in df_cat.iterrows():
                        sim = row['Símbolo']
                        st.markdown(f"**{sim}**")
                        noticias = analizar_noticias(sim)
                        st.write(noticias)
                        st.divider()

    # --------------------------------------------------
    # Gráficos de la mejor oportunidad
    # --------------------------------------------------
    if not compras.empty:
        mejor = compras.iloc[0]['Símbolo']
        st.subheader(f"📊 Gráfico de la mejor oportunidad: {mejor}")
        ticker = yf.Ticker(mejor)
        hist_raw = ticker.history(period="3mo")
        if not hist_raw.empty:
            if mejor.endswith('.MX'):
                factor = 1.0
            elif mejor.endswith('.MC'):
                factor = eur_mxn
            else:
                factor = usd_mxn
            hist_raw['Close'] = hist_raw['Close'] * factor
            hist_raw['Open'] = hist_raw['Open'] * factor
            hist_raw['High'] = hist_raw['High'] * factor
            hist_raw['Low'] = hist_raw['Low'] * factor
            hist_raw['EMA20'] = hist_raw['Close'].ewm(span=20, adjust=False).mean()
            hist_raw['EMA50'] = hist_raw['Close'].ewm(span=50, adjust=False).mean()

            fig = go.Figure(data=[go.Candlestick(
                x=hist_raw.index,
                open=hist_raw['Open'],
                high=hist_raw['High'],
                low=hist_raw['Low'],
                close=hist_raw['Close'],
                name='Velas'
            )])
            fig.add_trace(go.Scatter(x=hist_raw.index, y=hist_raw['EMA20'],
                                     line=dict(color='orange', width=2), name='EMA20'))
            fig.add_trace(go.Scatter(x=hist_raw.index, y=hist_raw['EMA50'],
                                     line=dict(color='red', width=2), name='EMA50'))
            fig.update_layout(title=f"{mejor} - Precio y Medias (MXN)",
                              xaxis_title="Fecha", yaxis_title="Precio (MXN)",
                              template='plotly_dark', height=600)
            st.plotly_chart(fig, use_container_width=True)

        # RSI de las mejores compras
        top10 = compras.head(10)
        if not top10.empty:
            st.subheader("📊 RSI de las mejores oportunidades")
            fig_rsi = px.bar(top10, x='Símbolo', y='RSI', color='RSI',
                             color_continuous_scale='RdYlGn',
                             title="RSI (14 días)")
            fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Sobrecompra")
            fig_rsi.add_hline(y=50, line_dash="dash", line_color="orange", annotation_text="Zona alcista")
            fig_rsi.update_layout(showlegend=False, height=500)
            st.plotly_chart(fig_rsi, use_container_width=True)

    # --------------------------------------------------
    # Descargar Excel (opcional)
    # --------------------------------------------------
    st.download_button(
        label="📥 Descargar informe Excel",
        data=df.to_csv(index=False).encode('utf-8'),
        file_name=f"informe_trading_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )