# ============================================================
# SCANNER DE TRADING AUTÓNOMO 24/7
# Con historial de señales, backtesting, caché de IA y alertas
# ============================================================

import os
import smtplib
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import json
import hashlib
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# CONFIGURACIÓN (se lee de variables de entorno / Secrets)
# ============================================================
EMAIL_REMITENTE   = os.environ.get("EMAIL_REMITENTE",   "")
EMAIL_PASSWORD    = os.environ.get("EMAIL_PASSWORD",    "")
EMAIL_DESTINO     = "alopez.uci@gmail.com"
WHATSAPP_NUMERO   = os.environ.get("WHATSAPP_NUMERO",   "")
WHATSAPP_APIKEY   = os.environ.get("WHATSAPP_APIKEY",   "")

GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY",    "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY",      "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SCORE_MINIMO     = 7
CAPITAL_TRADING  = 25_000
RIESGO_PCT       = 1.0
MAX_WORKERS      = 20
CACHE_DIR        = "cache_ia"
CACHE_TTL        = 3600
HISTORICO_FILE   = "historial_senales.csv"
BACKTEST_WINDOW  = 5

# ============================================================
# UNIVERSO COMPLETO (≈700 activos)
# ============================================================
UNIVERSO = list(set([
    # ... (la lista completa de símbolos que ya tienes en app.py) ...
    # Por brevedad no la repito aquí; asegúrate de incluirla.
]))

# ============================================================
# FUNCIONES DE INDICADORES, SCORING, MARKET REGIME, POSITION SIZING
# ============================================================
# (Aquí van todas las funciones: calcular_indicadores, calcular_score,
#  obtener_market_regime, position_size, analizar, etc. – igual que en app.py)
# ... (copia las funciones desde tu app.py) ...

# ============================================================
# HISTORIAL Y BACKTESTING
# ============================================================
def cargar_historial() -> pd.DataFrame:
    if os.path.exists(HISTORICO_FILE):
        df = pd.read_csv(HISTORICO_FILE)
        df['fecha'] = pd.to_datetime(df['fecha'])
        return df
    return pd.DataFrame(columns=['fecha', 'simbolo', 'score', 'precio', 'recomendacion', 'señales'])

def guardar_senal_en_historial(senal: dict, fecha: str):
    df = cargar_historial()
    nueva = pd.DataFrame([{
        'fecha': fecha,
        'simbolo': senal['Símbolo'],
        'score': senal['Score'],
        'precio': senal['Precio MXN'],
        'recomendacion': senal['Recomendación'],
        'señales': senal.get('Señales', '')
    }])
    df = pd.concat([df, nueva], ignore_index=True)
    df['fecha'] = pd.to_datetime(df['fecha'])
    cutoff = datetime.now() - timedelta(days=90)
    df = df[df['fecha'] >= cutoff]
    df.to_csv(HISTORICO_FILE, index=False)
    print(f"  ✅ Señal guardada en historial: {senal['Símbolo']} (Score {senal['Score']})")

def backtest_historial(df_hist: pd.DataFrame) -> dict:
    if df_hist.empty:
        return {'win_rate': 0, 'ret_prom': 0, 'total': 0}
    resultados = []
    for _, row in df_hist.iterrows():
        try:
            ticker = yf.Ticker(row['simbolo'])
            end_date = datetime.now()
            start_date = end_date - timedelta(days=180)
            hist = ticker.history(start=start_date, end=end_date)
            if hist.empty:
                continue
            fecha_senal = row['fecha']
            idx = hist.index.searchsorted(fecha_senal)
            if idx + BACKTEST_WINDOW >= len(hist):
                continue
            precio_entrada = row['precio']
            precio_salida = hist['Close'].iloc[idx + BACKTEST_WINDOW]
            retorno = (precio_salida / precio_entrada - 1) * 100
            resultados.append(retorno)
        except:
            continue
    if resultados:
        win_rate = sum(1 for r in resultados if r > 0) / len(resultados) * 100
        ret_prom = np.mean(resultados)
        return {
            'win_rate': round(win_rate, 1),
            'ret_prom': round(ret_prom, 2),
            'total': len(resultados)
        }
    return {'win_rate': 0, 'ret_prom': 0, 'total': 0}

# ============================================================
# IA CON CACHÉ Y REINTENTOS (igual que en app.py)
# ============================================================
# ... (copia las funciones de caché y IA desde tu app.py) ...

# ============================================================
# ALERTAS (email, WhatsApp) — igual que en app.py
# ============================================================
# ... (copia las funciones enviar_email, enviar_whatsapp, construir_email) ...

# ============================================================
# MAIN
# ============================================================
def main():
    hora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n{'='*50}")
    print(f"  Scanner Trading 24/7 — {hora}")
    print(f"{'='*50}\n")

    # 1. Tipo de cambio
    try:
        usd_data = yf.Ticker("USDMXN=X").history(period="1d")
        usd_mxn  = float(usd_data['Close'].iloc[-1]) if not usd_data.empty else 20.0
    except:
        usd_mxn = 20.0
    print(f"USD/MXN: {usd_mxn:.2f}")

    # 2. Market regime
    regime = obtener_market_regime()
    print(f"Régimen: {regime['regime']} (bonus score: {regime['score_bonus']})")
    score_minimo_efectivo = 9 if regime['regime'] == 'BAJISTA' else SCORE_MINIMO

    # 3. Análisis en paralelo
    print(f"\nAnalizando {len(UNIVERSO)} activos en paralelo ({MAX_WORKERS} hilos)...")
    resultados = []
    args_list = [(sim, usd_mxn, regime['score_bonus']) for sim in UNIVERSO]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(analizar, a): a[0] for a in args_list}
        for i, f in enumerate(as_completed(futures), 1):
            res = f.result()
            if res and res['Score'] >= score_minimo_efectivo:
                resultados.append(res)
            if i % 20 == 0:
                print(f"  {i}/{len(UNIVERSO)} procesados...")

    resultados.sort(key=lambda x: x['Score'], reverse=True)
    print(f"\nOportunidades detectadas: {len(resultados)}")
    for r in resultados:
        print(f"  {r['Símbolo']:8s} Score:{r['Score']:2d}  RSI:{r['RSI']:5.1f}  "
              f"Precio:{r['Precio MXN']:>10.2f}  {r['Recomendación']}")

    # 4. Guardar en historial
    print("\nGuardando señales en historial...")
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for senal in resultados:
        guardar_senal_en_historial(senal, fecha_hoy)

    # 5. Backtesting sobre historial
    print("\nEjecutando backtesting sobre señales previas...")
    hist_df = cargar_historial()
    metrics = backtest_historial(hist_df)
    print(f"  Backtest (ventana {BACKTEST_WINDOW} días):")
    print(f"    - Total señales evaluadas: {metrics['total']}")
    print(f"    - Win rate: {metrics['win_rate']}%")
    print(f"    - Retorno promedio: {metrics['ret_prom']}%")

    # 6. Análisis IA
    print("\nConsultando IA para análisis...")
    ia_texto = analisis_ia(resultados, regime, usd_mxn)
    if ia_texto:
        print("\n--- ANÁLISIS IA ---")
        print(ia_texto[:500] + "..." if len(ia_texto) > 500 else ia_texto)

    # 7. Alertas
    if resultados:
        html = construir_email(resultados, regime, ia_texto, hora)
        asunto = (f"📈 Trading Alert {hora} — "
                  f"{len(resultados)} señales | Mercado: {regime['regime']}")
        enviar_email(asunto, html)

        top3 = ", ".join([r['Símbolo'] for r in resultados[:3]])
        confianza = "ALTA" if regime['regime'] == 'ALCISTA' else "MEDIA" if regime['regime'] == 'LATERAL' else "BAJA"
        msg_wa = (f"📈 *Scanner Trading* — {hora}\n"
                  f"Régimen: {regime['regime']} | USD/MXN: {usd_mxn:.2f}\n"
                  f"🟢 {len(resultados)} oportunidades\n"
                  f"Top 3: {top3}\n"
                  f"Confianza: {confianza}\n"
                  f"Ver detalles en tu email")
        enviar_whatsapp(msg_wa)
    else:
        print("Sin oportunidades que superen el umbral. No se envían alertas.")

    print(f"\n✅ Scanner completado — {datetime.now().strftime('%H:%M:%S')}\n")

if __name__ == "__main__":
    main()
