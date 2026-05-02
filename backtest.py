#!/usr/bin/env python3
"""
Backtest simple para Trading App v3.1

- Lee historial_senales.csv y transacciones.csv
- Simula ejecución de señales (compra=+1, venta=-1, observar/evitar=0)
- Compara contra buy-and-hold del mismo universo temporal
- Calcula Sharpe ratio y máximo drawdown
- Guarda resultados en data/backtest_results.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

MEXICAN_SYMBOLS_BASE = {
    'WALMEX', 'GMEXICOB', 'CEMEXCPO', 'FEMSAUBD', 'AMXL', 'KOFUBL', 'GFNORTEO',
    'BBAJIOO', 'ALFA', 'ALPEKA', 'ASURB', 'GAPB', 'OMAB', 'AC', 'GCC', 'LALA',
    'MEGA', 'PINFRA', 'TLEVISACPO', 'VESTA', 'GRUMA', 'HERDEZ', 'CUERVO', 'ORBIA',
    'VOLARA', 'Q', 'LABB', 'NEMAKA', 'FMTY14', 'FUNO11', 'FIBRAPL14', 'TERRA13',
    'DANHOS13', 'FIBRAHD15', 'FIBRAMQ12'
}


def _normalizar_simbolo(simbolo: str) -> str:
    s = str(simbolo).upper().strip()
    if not s:
        return s
    if s.endswith('.MX') or s.startswith('^') or '/' in s or '=' in s:
        return s
    if '.' in s:
        return s
    return f"{s}.MX" if s in MEXICAN_SYMBOLS_BASE else s


def _resolver_archivo(nombre: str) -> Optional[Path]:
    candidatos = [DATA_DIR / nombre, ROOT / nombre]
    for ruta in candidatos:
        if ruta.exists():
            return ruta
    return None


def _normalizar_recomendacion(txt: str) -> int:
    r = str(txt).upper()
    if "COMPRAR" in r:
        return 1
    if "VENDER" in r:
        return -1
    return 0


def _descargar_retornos_1d(simbolo: str, inicio: pd.Timestamp, fin: pd.Timestamp) -> Dict[pd.Timestamp, float]:
    simbolos_prueba = [str(simbolo)]
    simbolo_norm = _normalizar_simbolo(simbolo)
    if simbolo_norm not in simbolos_prueba:
        simbolos_prueba.append(simbolo_norm)

    for sym in simbolos_prueba:
        try:
            hist = yf.download(
                sym,
                start=(inicio - pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
                end=(fin + pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=False,
                threads=False,
            )
            if hist.empty or "Close" not in hist.columns:
                continue

            closes = hist["Close"].astype(float)
            ret_next = closes.shift(-1) / closes - 1
            ret_next.index = pd.to_datetime(ret_next.index).tz_localize(None)
            return {idx.normalize(): float(val) for idx, val in ret_next.dropna().items()}
        except Exception:
            continue
    return {}


def _calcular_sharpe(retornos: pd.Series) -> Optional[float]:
    if retornos.empty:
        return None
    std = float(retornos.std(ddof=1))
    if std == 0:
        return None
    return round(float((retornos.mean() / std) * np.sqrt(252)), 4)


def _calcular_max_drawdown(retornos: pd.Series) -> Optional[float]:
    if retornos.empty:
        return None
    capital = (1 + retornos).cumprod()
    max_prev = capital.cummax()
    dd = capital / max_prev - 1
    return round(float(dd.min() * 100), 2)


def ejecutar_backtest() -> dict:
    historial_path = _resolver_archivo("historial_senales.csv")
    trans_path = _resolver_archivo("transacciones.csv")

    if historial_path is None:
        raise FileNotFoundError("No se encontró historial_senales.csv en raíz ni en data/")

    df_hist = pd.read_csv(historial_path)
    if df_hist.empty:
        raise ValueError("historial_senales.csv está vacío")

    df_hist["fecha"] = pd.to_datetime(df_hist["fecha"], errors="coerce")
    df_hist = df_hist.dropna(subset=["fecha", "simbolo", "recomendacion"]).copy()
    df_hist["fecha_dia"] = df_hist["fecha"].dt.normalize()
    df_hist["senal"] = df_hist["recomendacion"].map(_normalizar_recomendacion)
    df_hist = df_hist[df_hist["senal"] != 0].copy()

    if df_hist.empty:
        raise ValueError("No hay señales COMPRAR/VENDER para backtest")

    inicio = df_hist["fecha_dia"].min()
    fin = df_hist["fecha_dia"].max()

    retornos_por_simbolo: Dict[str, Dict[pd.Timestamp, float]] = {}
    for simbolo in sorted(df_hist["simbolo"].astype(str).unique()):
        retornos_por_simbolo[simbolo] = _descargar_retornos_1d(simbolo, inicio, fin)

    filas = []
    for row in df_hist.itertuples(index=False):
        mapa = retornos_por_simbolo.get(str(row.simbolo), {})
        ret_1d = mapa.get(pd.Timestamp(row.fecha_dia))
        if ret_1d is None:
            continue
        filas.append(
            {
                "fecha": pd.Timestamp(row.fecha_dia),
                "simbolo": str(row.simbolo),
                "senal": int(row.senal),
                "ret_1d": float(ret_1d),
                "ret_estrategia": float(ret_1d * int(row.senal)),
                "ret_buy_hold": float(ret_1d),
            }
        )

    if not filas:
        resultado = {
            "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "estado": "sin_datos_de_mercado",
            "mensaje": "No fue posible alinear señales con precios históricos descargados.",
            "sugerencia": "Verifica conectividad a Yahoo Finance o símbolos fuera de catálogo.",
        }
        salida = DATA_DIR / "backtest_results.json"
        with open(salida, "w", encoding="utf-8") as f:
            json.dump(resultado, f, indent=2, ensure_ascii=False)
        return resultado

    df_bt = pd.DataFrame(filas)
    diarios = (
        df_bt.groupby("fecha", as_index=True)[["ret_estrategia", "ret_buy_hold"]]
        .mean()
        .sort_index()
    )

    capital_estrategia = (1 + diarios["ret_estrategia"]).cumprod()
    capital_bh = (1 + diarios["ret_buy_hold"]).cumprod()

    resultado = {
        "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "periodo": {
            "inicio": str(diarios.index.min().date()),
            "fin": str(diarios.index.max().date()),
            "dias": int(len(diarios)),
        },
        "universo": {
            "simbolos": sorted(df_bt["simbolo"].unique().tolist()),
            "num_simbolos": int(df_bt["simbolo"].nunique()),
            "senales_usadas": int(len(df_bt)),
        },
        "rendimiento": {
            "estrategia_pct": round(float((capital_estrategia.iloc[-1] - 1) * 100), 2),
            "buy_and_hold_pct": round(float((capital_bh.iloc[-1] - 1) * 100), 2),
            "diferencia_pct": round(float((capital_estrategia.iloc[-1] - capital_bh.iloc[-1]) * 100), 2),
        },
        "riesgo": {
            "sharpe_estrategia": _calcular_sharpe(diarios["ret_estrategia"]),
            "sharpe_buy_and_hold": _calcular_sharpe(diarios["ret_buy_hold"]),
            "max_drawdown_estrategia_pct": _calcular_max_drawdown(diarios["ret_estrategia"]),
            "max_drawdown_buy_and_hold_pct": _calcular_max_drawdown(diarios["ret_buy_hold"]),
        },
    }

    if trans_path is not None:
        try:
            df_trans = pd.read_csv(trans_path)
            df_trans["tipo"] = df_trans["tipo"].astype(str).str.lower().str.strip()
            df_trans["total"] = pd.to_numeric(df_trans.get("total"), errors="coerce").fillna(0.0)
            compras = float(df_trans.loc[df_trans["tipo"] == "compra", "total"].sum())
            ventas = float(df_trans.loc[df_trans["tipo"] == "venta", "total"].sum())

            ganancia_pct = pd.to_numeric(df_trans.get("ganancia_pct"), errors="coerce")
            ventas_con_ganancia = ganancia_pct.dropna()

            resultado["transacciones"] = {
                "monto_compras": round(compras, 2),
                "monto_ventas": round(ventas, 2),
                "pnl_realizado_aprox": round(ventas - compras, 2),
                "ventas_con_ganancia_registrada": int(len(ventas_con_ganancia)),
                "ganancia_pct_promedio_ventas": round(float(ventas_con_ganancia.mean()), 2)
                if not ventas_con_ganancia.empty
                else None,
            }
        except Exception as e:
            resultado["transacciones"] = {"error": f"No se pudo procesar transacciones.csv: {e}"}

    salida = DATA_DIR / "backtest_results.json"
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)

    return resultado


if __name__ == "__main__":
    res = ejecutar_backtest()
    print(json.dumps(res, indent=2, ensure_ascii=False))
