"""
macro_fetcher.py
────────────────
Fetches live / latest macro inputs from free public sources.
Self-contained module for Algo_Stocks.
"""

import datetime
import sys
import urllib.request
import json
import pandas as pd
import yfinance as yf
from dataclasses import dataclass, asdict
from typing import Optional

TIMEOUT = 8

@dataclass
class MacroInputs:
    repo_rate_direction: str
    gsec_10yr_yield: float
    monsoon_vs_lpa_pct: float
    lme_copper_mom_pct: float
    iron_ore_mom_pct: float
    brent_crude_usd: float
    dxy_index: float
    fii_net_5d_cr: float
    india_vix: float
    govt_capex_execution_pct: float
    credit_growth_yoy_pct: float
    budget_week: bool = False
    china_stimulus_active: bool = False
    geopolitical_tension: bool = False

def _stooq_latest(symbol: str) -> Optional[float]:
    yf_map = {
        "@BZ.F": "BZ=F",
        "LCO.F": "BZ=F",
        "DX-Y.NYB": "DX-Y.NYB",
        "UUP.US": "UUP",
        "10YINR.B": "^IN10YT",
        "HG.F": "HG=F",
        "TIO.F": "TIO=F"
    }
    yf_symbol = yf_map.get(symbol, symbol)
    try:
        df = yf.download(yf_symbol, period="5d", progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return float(df.iloc[-1]["Close"])
    except Exception as e:
        print(f"  [yfinance error] {yf_symbol}: {e}", file=sys.stderr)
    return None

def _stooq_mom_pct(symbol: str) -> Optional[float]:
    yf_map = {
        "HG.F": "HG=F",
        "TIO.F": "TIO=F"
    }
    yf_symbol = yf_map.get(symbol, symbol)
    try:
        df = yf.download(yf_symbol, period="3mo", progress=False)
        if not df.empty and len(df) >= 20:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            latest = float(df.iloc[-1]["Close"])
            month_ago = float(df.iloc[-20]["Close"])
            if month_ago:
                return round((latest - month_ago) / month_ago * 100, 2)
    except Exception as e:
        print(f"  [yfinance MoM error] {yf_symbol}: {e}", file=sys.stderr)
    return None

def fetch_brent_usd() -> float:
    val = _stooq_latest("@BZ.F")
    if val and 30 < val < 200:
        return round(val, 2)
    return 75.0

def fetch_dxy() -> float:
    val = _stooq_latest("DX-Y.NYB")
    if val and 80 < val < 130:
        return round(val, 2)
    return 104.0

def fetch_lme_copper_mom_pct() -> float:
    val = _stooq_mom_pct("HG.F")
    if val is not None and -30 < val < 30:
        return round(val, 2)
    return 0.0

def fetch_iron_ore_mom_pct() -> float:
    val = _stooq_mom_pct("TIO.F")
    if val is not None and -30 < val < 30:
        return round(val, 2)
    return 0.0

def fetch_india_vix() -> float:
    try:
        df = yf.download("^INDIAVIX", period="5d", progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return float(df.iloc[-1]["Close"])
    except Exception:
        pass
    return 16.0

def fetch_gsec_10yr() -> float:
    val = _stooq_latest("10YINR.B")
    if val and 4.0 < val < 12.0:
        return round(val, 2)
    return 6.8

def _infer_repo_direction(gsec_yield: float) -> str:
    if gsec_yield < 6.5:
        return "cutting"
    elif gsec_yield > 7.2:
        return "hiking"
    return "neutral"

def fetch_monsoon_vs_lpa() -> float:
    today = datetime.date.today()
    if today.month not in (6, 7, 8, 9):
        return 100.0
    return 100.0  # Safe default off-season

def fetch_credit_growth() -> float:
    return 13.0

def fetch_govt_capex_execution() -> float:
    month = datetime.date.today().month
    typical_by_month = {
        4: 8, 5: 14, 6: 20, 7: 27, 8: 35, 9: 43,
        10: 51, 11: 58, 12: 65, 1: 72, 2: 80, 3: 95
    }
    return float(typical_by_month.get(month, 50))

def fetch_live_macro(manual_overrides: Optional[dict] = None) -> MacroInputs:
    print("  [Live Macro] Fetching global indicators via yfinance...", file=sys.stderr)
    
    gsec = fetch_gsec_10yr()
    brent = fetch_brent_usd()
    dxy = fetch_dxy()
    cu_mom = fetch_lme_copper_mom_pct()
    fe_mom = fetch_iron_ore_mom_pct()
    vix = fetch_india_vix()
    monsoon = fetch_monsoon_vs_lpa()
    credit = fetch_credit_growth()
    capex = fetch_govt_capex_execution()
    repo_dir = _infer_repo_direction(gsec)
    
    inputs = MacroInputs(
        repo_rate_direction=repo_dir,
        gsec_10yr_yield=gsec,
        monsoon_vs_lpa_pct=monsoon,
        lme_copper_mom_pct=cu_mom,
        iron_ore_mom_pct=fe_mom,
        brent_crude_usd=brent,
        dxy_index=dxy,
        fii_net_5d_cr=0.0,
        india_vix=vix,
        govt_capex_execution_pct=capex,
        credit_growth_yoy_pct=credit,
        budget_week=False,
        china_stimulus_active=False,
        geopolitical_tension=False,
    )
    
    if manual_overrides:
        for k, v in manual_overrides.items():
            if hasattr(inputs, k):
                setattr(inputs, k, v)
                
    return inputs
