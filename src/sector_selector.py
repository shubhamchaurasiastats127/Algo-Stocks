"""
sector_selector.py
------------------
Pre-Layer Sector Selection Module

Evaluates all Nifty sectoral/thematic indices using a 6-factor scoring
framework to select the top 1-5 indices with the highest potential for
oversold stock rebounds in 1-2 months to 1-2 years.

Factors:
  A. Economic Phase & Sector Rotation Alignment
  B. Seasonality & Quarterly Timing
  C. Technical & Momentum Indicators (RSI, 52-week levels)
  D. Fundamental Valuation (P/E, P/B, ROE, Revenue Growth)
  E. Macro & Policy Drivers
  F. Risk & Diversification (Correlation check, VIX check)

Also computes the Rebound Potential Score for each constituent stock.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


import json
import logging
import math
from datetime import datetime, timedelta

# pyrefly: ignore [missing-import]
import mysql.connector
# pyrefly: ignore [missing-import]
import numpy as np
# pyrefly: ignore [missing-import]
import pandas as pd
# pyrefly: ignore [missing-import]
import yfinance as yf
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from macro_fetcher import fetch_live_macro

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sectoral indices only (exclude broad-market indices from selection)
SECTORAL_INDICES = [
    "Nifty Auto",
    "Nifty Bank",
    "Nifty Energy",
    "Nifty Financial Services",
    "Nifty FMCG",
    "Nifty Infra",
    "Nifty IT",
    "Nifty Metal",
    "Nifty Pharma",
    "Nifty Private Bank",
    "Nifty PSU Bank",
    "Nifty Realty",
]

# For indices without a valid yfinance ticker, we reconstruct from constituents.
# This map is used to attempt a direct fetch first.
INDEX_YF_TICKERS = {
    "Nifty Bank":               "^NSEBANK",
    "Nifty IT":                 "^CNXIT",
    "Nifty Auto":               "^CNXAUTO",
    "Nifty Pharma":             "^CNXPHARMA",
    "Nifty FMCG":               "^CNXFMCG",
    "Nifty Metal":              "^CNXMETAL",
    "Nifty Realty":             "^CNXREALTY",
    "Nifty Energy":             "^CNXENERGY",
    "Nifty Infra":              "^CNXINFRA",
    "Nifty Financial Services": "^CNXFIN",
    "Nifty PSU Bank":           "^CNXPSUBANK",
    "Nifty Private Bank":       "NIFTY_PVT_BANK.NS",
}

# Factor E: Policy / macro driver scores (0-100) — hardcoded rationale for June 2026
MACRO_POLICY_SCORES = {
    "Nifty Auto":               {
        "score": 82,
        "rationale": "Govt EV push (FAME-III), PLI for auto components, rural demand recovery via good monsoon, "
                     "festive season Q2-Q3 tailwind. EV transition accelerating."
    },
    "Nifty Bank":               {
        "score": 75,
        "rationale": "RBI neutral stance (Repo 5.25%); credit growth steady ~14%. NPA ratios at multi-year lows. "
                     "Rate cuts possible in H2 FY27 = margin relief. Capital adequacy strong."
    },
    "Nifty Energy":             {
        "score": 68,
        "rationale": "Renewable capacity expansion; solar/wind PLI scheme. Oil prices stable. "
                     "Govt capex in power sector ₹4L cr FY27. Green hydrogen push."
    },
    "Nifty Financial Services": {
        "score": 72,
        "rationale": "NBFCs and insurance growing rapidly with financial inclusion push. "
                     "Digital lending and fintech adoption accelerating. "
                     "SEBI reforms improving capital markets depth."
    },
    "Nifty FMCG":               {
        "score": 63,
        "rationale": "Rural recovery led by higher MSP and good monsoon. Urban consumption resilient. "
                     "Input costs (palm oil, crude) moderating. Defensive sector with stable cash flows."
    },
    "Nifty Infra":              {
        "score": 85,
        "rationale": "Govt infrastructure capex ₹11.11L cr in Union Budget FY27. "
                     "NHAI road projects, metro rail expansion, smart cities. "
                     "Cement, steel, logistics all benefiting. Infra cycle clearly accelerating."
    },
    "Nifty IT":                 {
        "score": 58,
        "rationale": "US macro recovery driving tech spending. AI-led deal wins. "
                     "Rupee stable. Margin improvement on cost efficiency. "
                     "Cautious outlook: hiring still slow; deal ramp-up takes 2-3 quarters."
    },
    "Nifty Metal":              {
        "score": 70,
        "rationale": "China stimulus improving global steel/aluminium demand. "
                     "Domestic infrastructure capex = steel demand. PLI for specialty steel. "
                     "Volatile but cycles can give 30-40% upside in 2-3 quarters."
    },
    "Nifty Pharma":             {
        "score": 65,
        "rationale": "US FDA clearances for key generic drugs. Healthcare budget up 10%. "
                     "API domestic production push under PLI. Defensive + growth combo."
    },
    "Nifty Private Bank":       {
        "score": 74,
        "rationale": "HDFC Bank, Kotak, Axis consolidating after underperformance. "
                     "Credit growth strong. ROA/ROE metrics improving. "
                     "Rate cut expectations = re-rating potential."
    },
    "Nifty PSU Bank":           {
        "score": 71,
        "rationale": "PSU banks cleaned up NPAs; ROE improving to 10-12%. "
                     "Govt capex disbursals via PSU banks. Dividend yields attractive. "
                     "Historically undervalued vs private banks."
    },
    "Nifty Realty":             {
        "score": 78,
        "rationale": "Housing demand at decadal high. Affordable housing PMAY-Urban. "
                     "Office/commercial real estate demand recovering. "
                     "Low interest rates ahead = EMI affordability up. Q4-Q1 strong seasonality."
    },
}

# Factor B: Seasonality scores by (index, current_month)
# Score = 0-100 depending on how strong this month is for the sector
SEASONALITY_MATRIX = {
    # Month: 1=Jan ... 12=Dec
    "Nifty Auto":               {1:70, 2:65, 3:60, 4:50, 5:55, 6:65, 7:80, 8:85, 9:90, 10:95, 11:90, 12:75},
    "Nifty Bank":               {1:85, 2:80, 3:90, 4:70, 5:65, 6:68, 7:72, 8:70, 9:72, 10:75, 11:78, 12:82},
    "Nifty Energy":             {1:70, 2:72, 3:75, 4:70, 5:68, 6:65, 7:68, 8:72, 9:75, 10:78, 11:75, 12:72},
    "Nifty Financial Services": {1:80, 2:78, 3:88, 4:72, 5:70, 6:72, 7:74, 8:72, 9:74, 10:76, 11:78, 12:82},
    "Nifty FMCG":               {1:72, 2:70, 3:68, 4:65, 5:70, 6:72, 7:80, 8:82, 9:80, 10:85, 11:82, 12:78},
    "Nifty Infra":              {1:88, 2:85, 3:90, 4:75, 5:72, 6:70, 7:68, 8:70, 9:72, 10:75, 11:78, 12:82},
    "Nifty IT":                 {1:70, 2:75, 3:72, 4:80, 5:82, 6:78, 7:75, 8:78, 9:80, 10:76, 11:74, 12:72},
    "Nifty Metal":              {1:75, 2:78, 3:82, 4:80, 5:75, 6:72, 7:74, 8:76, 9:78, 10:80, 11:78, 12:75},
    "Nifty Pharma":             {1:72, 2:74, 3:76, 4:78, 5:75, 6:72, 7:74, 8:76, 9:78, 10:75, 11:72, 12:70},
    "Nifty Private Bank":       {1:82, 2:80, 3:88, 4:72, 5:68, 6:70, 7:72, 8:70, 9:72, 10:75, 11:78, 12:82},
    "Nifty PSU Bank":           {1:82, 2:80, 3:88, 4:72, 5:68, 6:68, 7:70, 8:68, 9:70, 10:72, 11:75, 12:80},
    "Nifty Realty":             {1:90, 2:85, 3:88, 4:70, 5:65, 6:68, 7:70, 8:72, 9:75, 10:78, 11:80, 12:85},
}

# Factor A: Economic phase sector alignment scores
# Current phase: Mid-to-Late Expansion (GDP 7.7% but moderating to 6.6%)
# Strong: Infra, Metal, IT, Realty / Decent: Financials, Energy / Defensive: FMCG, Pharma
ECONOMIC_PHASE_SCORES = {
    "Nifty Auto":               80,   # Early recovery + cyclical; rural recovery catalyst
    "Nifty Bank":               78,   # Mid-expansion financials outperform
    "Nifty Energy":             72,   # Late expansion / commodity cycle
    "Nifty Financial Services": 76,
    "Nifty FMCG":               60,   # Defensive; doesn't outperform in expansion
    "Nifty Infra":              88,   # Strongest in mid-expansion with capex cycle
    "Nifty IT":                 74,   # Tech outperforms mid-expansion
    "Nifty Metal":              78,   # Mid-expansion commodity cycle
    "Nifty Pharma":             62,   # Defensive; lower in expansion phase
    "Nifty Private Bank":       78,
    "Nifty PSU Bank":           72,
    "Nifty Realty":             80,   # Housing boom in expansion phase
}


class SectorSelector:
    """
    Pre-Layer Sector Selection Engine.

    Evaluates all Nifty sectoral indices using a 6-factor framework,
    selects the top 1-5 sectors, and provides detailed justification.
    """

    def __init__(self, config: dict):
        self.config = config
        self.db_config = config['mysql']
        self._conn_pool = None
        self.today = datetime.now().date()
        self.current_month = self.today.month
        self.current_quarter = (self.current_month - 1) // 3 + 1
        
        # Load dynamic macro inputs
        self.macro_inputs = None
        try:
            overrides = self.config.get('macro_overrides', {})
            self.macro_inputs = fetch_live_macro(overrides)
        except Exception as e:
            logger.error(f"Error loading macro fetcher in SectorSelector: {e}")

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _get_conn(self):
        try:
            return mysql.connector.connect(**self.db_config)
        except Exception as e:
            import sqlite3
            from data_manager import SQLiteConnectionWrapper
            sqlite_path = "data/stock_cache.db"
            os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
            return SQLiteConnectionWrapper(sqlite3.connect(sqlite_path))

    def _get_constituents(self, index_name: str) -> list:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT symbol FROM index_constituents WHERE index_name = %s",
                (index_name,)
            )
            return [r[0] for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def _get_price_history(self, symbols: list, days: int = 365) -> pd.DataFrame:
        """Return pivot table (date x symbol) of closing prices."""
        if not symbols:
            return pd.DataFrame()
        start_date = (self.today - timedelta(days=days)).strftime('%Y-%m-%d')
        conn = self._get_conn()
        placeholders = ",".join(["%s"] * len(symbols))
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT symbol, date, close FROM price_data "
                f"WHERE symbol IN ({placeholders}) AND date >= %s ORDER BY date",
                tuple(symbols) + (start_date,)
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=['symbol', 'date', 'close'])
        df['close'] = df['close'].astype(float)
        df['date'] = pd.to_datetime(df['date'])
        pivot = df.pivot(index='date', columns='symbol', values='close')
        return pivot.ffill().bfill()

    def _get_all_price_history(self, symbols: list) -> pd.DataFrame:
        """Return full price history (OHLCV) for a list of symbols."""
        if not symbols:
            return pd.DataFrame()
        conn = self._get_conn()
        placeholders = ",".join(["%s"] * len(symbols))
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT symbol, date, open, high, low, close, volume FROM price_data "
                f"WHERE symbol IN ({placeholders}) ORDER BY date",
                tuple(symbols)
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['date'] = pd.to_datetime(df['date'])
        return df

    def _get_fundamentals(self, symbols: list) -> dict:
        """Return dict of {symbol: info_dict} from cached fundamentals."""
        if not symbols:
            return {}
        conn = self._get_conn()
        placeholders = ",".join(["%s"] * len(symbols))
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT symbol, data_json FROM fundamentals WHERE symbol IN ({placeholders})",
                tuple(symbols)
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        result = {}
        for sym, data_json in rows:
            try:
                result[sym] = json.loads(data_json)
            except Exception:
                result[sym] = {}
        return result

    # ------------------------------------------------------------------
    # Index price reconstruction
    # ------------------------------------------------------------------

    def _reconstruct_index(self, index_name: str, days: int = 365) -> pd.Series:
        """Build a market-cap weighted index price series from constituents."""
        constituents = self._get_constituents(index_name)
        if not constituents:
            return pd.Series(dtype=float)

        price_pivot = self._get_price_history(constituents, days=days)
        if price_pivot.empty:
            return pd.Series(dtype=float)

        fund_data = self._get_fundamentals(constituents)
        weights = {}
        for sym in price_pivot.columns:
            info = fund_data.get(sym, {})
            mcap = info.get('marketCap', 0) or 0
            weights[sym] = float(mcap) if mcap > 0 else 1e10  # fallback: equal weight

        weight_arr = np.array([weights.get(sym, 1e10) for sym in price_pivot.columns])
        total_w = weight_arr.sum()
        if total_w == 0:
            return pd.Series(dtype=float)

        index_series = (price_pivot * weight_arr).sum(axis=1) / total_w
        index_series.name = index_name
        return index_series

    # ------------------------------------------------------------------
    # Factor C: Technical indicators for index series
    # ------------------------------------------------------------------

    def _compute_index_technicals(self, series: pd.Series) -> dict:
        """Compute RSI, returns, and 52-week stats for a reconstructed index series."""
        if series.empty or len(series) < 20:
            return {}

        # Returns
        current = float(series.iloc[-1])
        def pct_change_n(n):
            if len(series) < n + 1:
                return 0.0
            past = float(series.iloc[-(n + 1)])
            return ((current - past) / past * 100) if past != 0 else 0.0

        ret_1m  = pct_change_n(22)
        ret_3m  = pct_change_n(66)
        ret_6m  = pct_change_n(132)
        ret_1y  = pct_change_n(252) if len(series) >= 253 else pct_change_n(len(series) - 1)

        # 52-week high/low
        window = min(252, len(series))
        high_52w = float(series.iloc[-window:].max())
        low_52w  = float(series.iloc[-window:].min())

        pct_from_high = ((current - high_52w) / high_52w * 100) if high_52w != 0 else 0.0
        pct_from_low  = ((current - low_52w)  / low_52w  * 100) if low_52w  != 0 else 0.0

        # RSI (14-day)
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs   = gain / (loss + 1e-9)
        rsi  = float((100 - 100 / (1 + rs)).iloc[-1])

        # SMA
        sma_50  = float(series.rolling(50).mean().iloc[-1])  if len(series) >= 50  else current
        sma_200 = float(series.rolling(200).mean().iloc[-1]) if len(series) >= 200 else current

        return {
            'current':       current,
            'ret_1m':        ret_1m,
            'ret_3m':        ret_3m,
            'ret_6m':        ret_6m,
            'ret_1y':        ret_1y,
            'high_52w':      high_52w,
            'low_52w':       low_52w,
            'pct_from_high': pct_from_high,   # negative = below high
            'pct_from_low':  pct_from_low,    # positive = above low
            'rsi':           rsi,
            'sma_50':        sma_50,
            'sma_200':       sma_200,
        }

    # ------------------------------------------------------------------
    # Factor D: Fundamental aggregates for an index's constituents
    # ------------------------------------------------------------------

    def _compute_index_fundamentals(self, index_name: str) -> dict:
        constituents = self._get_constituents(index_name)
        fund_data = self._get_fundamentals(constituents)

        pe_vals, pb_vals, roe_vals = [], [], []
        rev_growth_vals, eps_growth_vals, de_vals = [], [], []

        for sym, info in fund_data.items():
            pe  = info.get('trailingPE',     None)
            pb  = info.get('priceToBook',    None)
            roe = info.get('returnOnEquity', None)
            rg  = info.get('revenueGrowth',  None)
            eg  = info.get('earningsGrowth', None)
            de  = info.get('debtToEquity',   None)

            if pe  and 0 < pe  < 500:  pe_vals.append(pe)
            if pb  and 0 < pb  < 50:   pb_vals.append(pb)
            if roe and -1 < roe < 2:   roe_vals.append(roe * 100)
            if rg  and -1 < rg  < 5:   rev_growth_vals.append(rg * 100)
            if eg  and -2 < eg  < 10:  eps_growth_vals.append(eg * 100)
            if de  and 0 <= de  < 500: de_vals.append(de / 100)

        def safe_median(lst):
            return float(np.median(lst)) if lst else None

        return {
            'median_pe':         safe_median(pe_vals),
            'median_pb':         safe_median(pb_vals),
            'median_roe':        safe_median(roe_vals),
            'median_rev_growth': safe_median(rev_growth_vals),
            'median_eps_growth': safe_median(eps_growth_vals),
            'median_de':         safe_median(de_vals),
            'n_stocks':          len(constituents),
        }

    # ------------------------------------------------------------------
    # Oversold stock counting for justification
    # ------------------------------------------------------------------

    def _count_oversold_stocks(self, index_name: str) -> dict:
        """Return counts of oversold / 52-week-low stocks in an index."""
        constituents = self._get_constituents(index_name)
        price_pivot = self._get_price_history(constituents, days=365)
        if price_pivot.empty:
            return {'oversold_30_60': 0, 'near_52w_low': 0, 'total': len(constituents)}

        n_oversold    = 0
        n_near_52w_lo = 0
        for sym in price_pivot.columns:
            series = price_pivot[sym].dropna()
            if len(series) < 20:
                continue
            current   = float(series.iloc[-1])
            high_52w  = float(series.max())
            low_52w   = float(series.min())
            pct_down  = (high_52w - current) / high_52w * 100 if high_52w else 0
            pct_above = (current - low_52w)  / low_52w  * 100 if low_52w  else 0

            if 30 <= pct_down <= 60:
                n_oversold += 1
            if 0 <= pct_above <= 15:
                n_near_52w_lo += 1

        return {
            'oversold_30_60': n_oversold,
            'near_52w_low':   n_near_52w_lo,
            'total':          len(constituents),
        }

    # ------------------------------------------------------------------
    # Factor C Scoring
    # ------------------------------------------------------------------

    def _score_technical(self, tech: dict) -> float:
        """Score 0-100 for the index based on technical oversold opportunity."""
        if not tech:
            return 50.0
        score = 0.0

        # RSI oversold zone (best 25-45, decent 45-55)
        rsi = tech.get('rsi', 50)
        if 25 <= rsi <= 45:
            score += 35
        elif 45 < rsi <= 55:
            score += 22
        elif rsi < 25:
            score += 15   # deeply oversold may be structural
        else:
            score += 10

        # Distance from 52-week high (deeper = more rebound potential)
        pct_from_high = tech.get('pct_from_high', 0)  # negative value
        down = abs(pct_from_high)
        if 20 <= down <= 45:
            score += 35
        elif 10 <= down < 20:
            score += 20
        elif 45 < down <= 65:
            score += 18  # could be structural decline
        else:
            score += 8

        # 1-month return (stabilizing is best: -5% to +5%)
        ret_1m = tech.get('ret_1m', 0)
        if -5 <= ret_1m <= 5:
            score += 15
        elif -15 <= ret_1m < -5:
            score += 8
        else:
            score += 4

        # Price vs SMA 200 (below SMA200 = oversold, approaching = reversal)
        current  = tech.get('current', 0)
        sma200   = tech.get('sma_200', current)
        if current < sma200:
            gap = (sma200 - current) / sma200 * 100
            if 5 <= gap <= 25:
                score += 15   # meaningful underperformance, rebound likely
            elif gap < 5:
                score += 10
            else:
                score += 5
        else:
            score += 5   # above SMA200 = already recovered, less rebound upside

        return min(score, 100.0)

    # ------------------------------------------------------------------
    # Factor D Scoring
    # ------------------------------------------------------------------

    def _score_fundamentals(self, fund: dict) -> float:
        """Score 0-100 for the index based on fundamental quality."""
        if not fund:
            return 50.0
        score = 0.0

        # P/E (lower = undervalued)
        pe = fund.get('median_pe')
        if pe is not None:
            if pe < 15:
                score += 30
            elif pe < 25:
                score += 22
            elif pe < 40:
                score += 12
            else:
                score += 5

        # ROE (higher = quality business)
        roe = fund.get('median_roe')
        if roe is not None:
            if roe > 15:
                score += 30
            elif roe > 10:
                score += 22
            elif roe > 5:
                score += 12
            else:
                score += 4

        # Revenue Growth
        rg = fund.get('median_rev_growth')
        if rg is not None:
            if rg > 15:
                score += 20
            elif rg > 8:
                score += 14
            elif rg > 3:
                score += 8
            else:
                score += 3

        # D/E ratio
        de = fund.get('median_de')
        if de is not None:
            if de < 0.5:
                score += 20
            elif de < 1.0:
                score += 14
            elif de < 1.5:
                score += 8
            else:
                score += 3

        return min(score, 100.0)

    # ------------------------------------------------------------------
    # Composite sector score
    # ------------------------------------------------------------------

    def compute_dynamic_macro_score(self, index_name: str) -> dict:
        """
        Dynamically calculate Factor E (Macro & Policy Drivers) score
        for each sector based on live macro indicators.
        """
        if not hasattr(self, 'macro_inputs') or self.macro_inputs is None:
            fallback = MACRO_POLICY_SCORES.get(index_name, {"score": 65, "rationale": "Stable policy environment."})
            return fallback

        macro = self.macro_inputs
        base_score = 65.0
        reasons = []

        if index_name == "Nifty Auto":
            if macro.monsoon_vs_lpa_pct > 95:
                base_score += 10
                reasons.append("Good monsoon (>95% LPA) supports rural demand")
            else:
                base_score -= 10
                reasons.append("Weak monsoon (<95% LPA) headwinds rural demand")
            
            if macro.credit_growth_yoy_pct > 12.0:
                base_score += 5
                reasons.append(f"Strong auto credit growth ({macro.credit_growth_yoy_pct:.1f}%)")
                
            if macro.brent_crude_usd > 85.0:
                base_score -= 10
                reasons.append(f"High fuel prices (Brent crude ${macro.brent_crude_usd:.1f}/bbl)")

        elif index_name == "Nifty Metal":
            avg_metal_mom = (macro.lme_copper_mom_pct + macro.iron_ore_mom_pct) / 2.0
            if avg_metal_mom > 2.0:
                base_score += 15
                reasons.append(f"Rising global metal prices (avg MoM +{avg_metal_mom:.1f}%)")
            elif avg_metal_mom < -2.0:
                base_score -= 15
                reasons.append(f"Declining global metal prices (avg MoM {avg_metal_mom:.1f}%)")
            
            if macro.china_stimulus_active:
                base_score += 10
                reasons.append("China stimulus active - boosts global demand")

        elif index_name == "Nifty IT":
            if macro.dxy_index > 103.0:
                base_score += 10
                reasons.append(f"Strong US Dollar Index (DXY {macro.dxy_index:.1f}) aids margins")
            else:
                base_score -= 5
                reasons.append(f"Moderate/weak DXY index ({macro.dxy_index:.1f})")

        elif index_name in ("Nifty Bank", "Nifty PSU Bank", "Nifty Private Bank", "Nifty Financial Services"):
            if macro.repo_rate_direction == "cutting" or macro.gsec_10yr_yield < 6.8:
                base_score += 10
                reasons.append(f"Rate cuts or low G-Sec yield ({macro.gsec_10yr_yield:.2f}%) reduces cost of funds")
            elif macro.repo_rate_direction == "hiking" or macro.gsec_10yr_yield > 7.2:
                base_score -= 10
                reasons.append(f"Rising yields ({macro.gsec_10yr_yield:.2f}%) squeeze margins")
                
            if macro.credit_growth_yoy_pct > 14.0:
                base_score += 10
                reasons.append(f"Robust system credit growth ({macro.credit_growth_yoy_pct:.1f}%)")
            elif macro.credit_growth_yoy_pct < 10.0:
                base_score -= 5
                reasons.append(f"Slow system credit growth ({macro.credit_growth_yoy_pct:.1f}%)")

        elif index_name == "Nifty Energy":
            if macro.brent_crude_usd > 80.0:
                base_score += 10
                reasons.append(f"High Brent crude prices (${macro.brent_crude_usd:.1f}) boosts upstream margins")
            elif macro.brent_crude_usd < 70.0:
                base_score -= 10
                reasons.append(f"Soft crude prices (${macro.brent_crude_usd:.1f}) headwinds")

        elif index_name == "Nifty Infra":
            if macro.govt_capex_execution_pct > 30.0:
                base_score += 10
                reasons.append(f"Strong Govt Capex execution ({macro.govt_capex_execution_pct:.1f}%)")
            
            if macro.gsec_10yr_yield > 7.1:
                base_score -= 5
                reasons.append("High debt costs (yield >7.1%) headwind for capex")

        elif index_name == "Nifty Realty":
            if macro.repo_rate_direction == "cutting" or macro.gsec_10yr_yield < 6.8:
                base_score += 15
                reasons.append("Rate cuts improve housing affordability")
            elif macro.repo_rate_direction == "hiking" or macro.gsec_10yr_yield > 7.2:
                base_score -= 10
                reasons.append("High home loan rates pressure housing demand")
                
            if macro.credit_growth_yoy_pct > 13.0:
                base_score += 5
                reasons.append("Strong home loan credit growth")

        elif index_name == "Nifty FMCG":
            if macro.monsoon_vs_lpa_pct > 95:
                base_score += 15
                reasons.append("Strong monsoon boosts rural consumption demand")
            else:
                base_score -= 10
                reasons.append("Deficit monsoon headwinds rural FMCG growth")
                
            if macro.brent_crude_usd < 75.0:
                base_score += 5
                reasons.append("Lower crude oil prices reduce packaging & transport costs")

        base_score = max(min(base_score, 100.0), 0.0)
        rationale = " | ".join(reasons) if reasons else "Stable macroeconomic context."
        
        return {"score": base_score, "rationale": rationale}

    def _compute_sector_score(self, index_name: str, tech: dict, fund: dict) -> dict:
        """Compute composite score for a sector across all 6 factors."""
        month = self.current_month

        score_A = float(ECONOMIC_PHASE_SCORES.get(index_name, 65))
        score_B = float(SEASONALITY_MATRIX.get(index_name, {}).get(month, 65))
        score_C = self._score_technical(tech)
        score_D = self._score_fundamentals(fund)
        
        # Call compute_dynamic_macro_score to get dynamic score
        macro_res = self.compute_dynamic_macro_score(index_name)
        score_E = float(macro_res['score'])

        # Composite (weights: A=20%, B=15%, C=30%, D=20%, E=15%)
        composite = (0.20 * score_A + 0.15 * score_B + 0.30 * score_C +
                     0.20 * score_D + 0.15 * score_E)

        return {
            'score_A': score_A,
            'score_B': score_B,
            'score_C': score_C,
            'score_D': score_D,
            'score_E': score_E,
            'composite': composite,
        }

    # ------------------------------------------------------------------
    # VIX fetch
    # ------------------------------------------------------------------

    def _fetch_current_vix(self) -> float:
        """Fetch latest India VIX. Falls back to 15.0 on failure."""
        try:
            df = yf.download("^INDIAVIX", period="5d", progress=False)
            if not df.empty:
                close_col = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
                if isinstance(close_col, pd.DataFrame):
                    close_col = close_col.squeeze()
                if isinstance(close_col, pd.DataFrame):
                    close_col = close_col.iloc[:, 0]
                val = close_col.dropna().iloc[-1]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                return float(val)
        except Exception:
            pass
        return 15.0

    # ------------------------------------------------------------------
    # Correlation check (Factor F)
    # ------------------------------------------------------------------

    def _check_correlation(self, selected_indices: list, index_series_map: dict,
                           all_scores: dict) -> list:
        """
        Ensure no two selected indices have correlation > 0.7 (last 252 days).
        If correlation too high between any pair, swap the lower-ranked one
        with the next best uncorrelated alternative from the ranked list.
        """
        if len(selected_indices) <= 1:
            return selected_indices

        ranked_all = sorted(all_scores.keys(),
                            key=lambda x: all_scores[x]['composite'], reverse=True)

        def get_returns(name):
            s = index_series_map.get(name)
            if s is None or s.empty:
                return None
            return s.pct_change().dropna().tail(252)

        final = list(selected_indices)
        changed = True
        iterations = 0
        while changed and iterations < 20:
            changed = False
            iterations += 1
            for i in range(len(final)):
                for j in range(i + 1, len(final)):
                    r1 = get_returns(final[i])
                    r2 = get_returns(final[j])
                    if r1 is None or r2 is None:
                        continue
                    aligned = r1.align(r2, join='inner')
                    if len(aligned[0]) < 30:
                        continue
                    corr = float(aligned[0].corr(aligned[1]))
                    if corr > 0.70:
                        # Swap the lower-ranked one (j) with next best alternative
                        lower_rank_idx = j
                        lower_name = final[lower_rank_idx]
                        # Find next best index not already selected
                        for alt in ranked_all:
                            if alt in final:
                                continue
                            r_alt = get_returns(alt)
                            if r_alt is None:
                                continue
                            # Check alt's correlation with all retained members
                            ok = True
                            for k, member in enumerate(final):
                                if k == lower_rank_idx:
                                    continue
                                r_m = get_returns(member)
                                if r_m is None:
                                    continue
                                al = r_alt.align(r_m, join='inner')
                                if len(al[0]) < 30:
                                    continue
                                if float(al[0].corr(al[1])) > 0.70:
                                    ok = False
                                    break
                            if ok:
                                logger.info(
                                    f"[Correlation] Swapping {lower_name} (corr={corr:.2f} with "
                                    f"{final[i]}) → {alt}"
                                )
                                final[lower_rank_idx] = alt
                                changed = True
                                break

        return final

    # ------------------------------------------------------------------
    # VIX / Defensive check (Factor F)
    # ------------------------------------------------------------------

    def _apply_vix_defensive_rule(self, selected: list, vix: float,
                                  all_scores: dict) -> list:
        """
        If VIX > 20, ensure at least one defensive sector is included.
        Defensive candidates: Nifty FMCG (least volatile), Nifty Pharma.
        Adds a remark to the sector justification if this rule fires.
        """
        if vix <= 20:
            return selected, False

        defensive_candidates = ["Nifty FMCG", "Nifty Pharma"]
        has_defensive = any(s in defensive_candidates for s in selected)

        if has_defensive:
            return selected, False

        # Pick least volatile defensive (FMCG first, then Pharma)
        for candidate in defensive_candidates:
            if candidate in all_scores:
                # Replace the lowest-ranked selected sector
                selected_copy = sorted(selected, key=lambda x: all_scores[x]['composite'])
                selected_copy[0] = candidate
                logger.info(
                    f"[VIX Rule] VIX={vix:.1f} > 20. Adding defensive sector "
                    f"'{candidate}' (least volatile). Replaced: {selected[0]}"
                )
                return selected_copy, True

        return selected, False

    # ------------------------------------------------------------------
    # Rebound Potential Score for individual stocks
    # ------------------------------------------------------------------

    def _detect_double_bottom(self, sym: str, closes: pd.Series) -> dict:
        """
        Detect a double bottom reversal pattern in the stock price closing series.
        Uses configurable thresholds for scanning and classification.
        """
        db_config = self.config.get('double_bottom', {})
        lookback = int(db_config.get('lookback_days', 150))
        max_diff = float(db_config.get('max_diff_pct', 0.05))
        min_bounce = float(db_config.get('min_bounce_pct', 0.02))
        min_peak_bounce = float(db_config.get('min_peak_bounce_pct', 0.07))

        n = len(closes)
        if n < 60:
            return {
                'pattern': False,
                'stage': 'None',
                'score': 0.0,
                'trough1_price': 0.0,
                'trough2_price': 0.0,
                'peak_price': 0.0,
                'diff_pct': 0.0,
                'bounce_pct': 0.0
            }

        # Focus on the scanning window
        df_window = closes.tail(lookback)
        w_len = len(df_window)
        
        print(f"    [DB Scan] {sym}: Scanning last {lookback} trading days...")

        # Simple local extrema search: a point is local min/max if it is min/max in a surrounding 5-day window
        local_mins = []
        local_maxs = []
        window = 5
        
        for i in range(window, w_len - window):
            idx = df_window.index[i]
            val = float(df_window.iloc[i])
            subset = df_window.iloc[i - window : i + window + 1]
            if val == subset.min():
                local_mins.append((i, idx, val))
            if val == subset.max():
                local_maxs.append((i, idx, val))

        print(f"    [DB Scan] {sym}: Found {len(local_mins)} local minima and {len(local_maxs)} local maxima.")

        if len(local_mins) < 2 or not local_maxs:
            return {
                'pattern': False,
                'stage': 'None',
                'score': 0.0,
                'trough1_price': 0.0,
                'trough2_price': 0.0,
                'peak_price': 0.0,
                'diff_pct': 0.0,
                'bounce_pct': 0.0
            }

        candidates = []
        current_price = float(closes.iloc[-1])

        # Scan pairs of local minima (Trough 1, Trough 2) with a local max (Peak) between them
        for i, (idx1, date1, val1) in enumerate(local_mins):
            for (idx2, date2, val2) in local_mins[i+1:]:
                # Trough separation: at least 15 days, at most 120 days
                if idx2 - idx1 < 15 or idx2 - idx1 > 120:
                    continue

                # Find peaks between troughs
                peaks_between = [(p_idx, p_dt, p_val) for p_idx, p_dt, p_val in local_maxs if idx1 < p_idx < idx2]
                if not peaks_between:
                    continue
                # Get the highest peak in between as our neckline/swing high
                p_idx, p_dt, peak_val = max(peaks_between, key=lambda x: x[2])

                # 1. Price difference between Trough 1 and Trough 2
                diff = abs(val1 - val2) / min(val1, val2)
                if diff > max_diff:
                    continue

                # 2. Peak must represent a meaningful bounce from both troughs
                b1 = (peak_val - val1) / val1
                b2 = (peak_val - val2) / val2
                if b1 < min_peak_bounce or b2 < min_peak_bounce:
                    continue

                # 3. Trough 2 should not break below Trough 1 by more than 3% (support must hold)
                if val2 < val1 * 0.97:
                    continue

                # Stage classification
                stage = 'None'
                db_score = 50.0  # Base score for double bottom setup

                if current_price < val2:
                    stage = 'Breakdown'
                    db_score = 10.0
                elif current_price < val2 * (1 + min_bounce):
                    stage = 'Forming Trough 2'
                    db_score += 5.0
                elif val2 * (1 + min_bounce) <= current_price <= peak_val * 1.02:
                    stage = 'Confirmed Bounce'
                    db_score += 20.0
                    if val2 > val1:
                        db_score += 10.0
                elif peak_val * 1.02 < current_price <= peak_val * 1.15:
                    stage = 'Neckline Breakout'
                    db_score += 15.0
                    if val2 > val1:
                        db_score += 10.0
                elif current_price > peak_val * 1.15:
                    stage = 'Extended Breakout'
                    db_score = 40.0

                candidates.append({
                    'trough1_price': val1,
                    'trough2_price': val2,
                    'peak_price': peak_val,
                    'stage': stage,
                    'score': db_score,
                    'diff_pct': diff * 100,
                    'bounce_pct': min(b1, b2) * 100,
                    'trough2_idx': idx2
                })

        if not candidates:
            return {
                'pattern': False,
                'stage': 'None',
                'score': 0.0,
                'trough1_price': 0.0,
                'trough2_price': 0.0,
                'peak_price': 0.0,
                'diff_pct': 0.0,
                'bounce_pct': 0.0
            }

        # Select candidate: prioritize Confirmed Bounce / Neckline Breakout, then most recent Trough 2
        candidates.sort(key=lambda x: (x['score'], x['trough2_idx']), reverse=True)
        best = candidates[0]

        print(f"    [DB Match] {sym}: Pattern matches! Stage: {best['stage']} (T1: {best['trough1_price']:.2f}, "
              f"Peak: {best['peak_price']:.2f}, T2: {best['trough2_price']:.2f}, Diff: {best['diff_pct']:.1f}%, Bounce: {best['bounce_pct']:.1f}%)")
        logger.info(f"[{sym}] Double Bottom Detected! Stage: {best['stage']} (T1: {best['trough1_price']:.2f}, "
                    f"Peak: {best['peak_price']:.2f}, T2: {best['trough2_price']:.2f}, Diff: {best['diff_pct']:.1f}%)")

        return {
            'pattern': True,
            'stage': best['stage'],
            'score': round(best['score'], 1),
            'trough1_price': round(best['trough1_price'], 2),
            'trough2_price': round(best['trough2_price'], 2),
            'peak_price': round(best['peak_price'], 2),
            'diff_pct': round(best['diff_pct'], 2),
            'bounce_pct': round(best['bounce_pct'], 2)
        }

    def compute_rebound_score(self, sym: str, price_df: pd.DataFrame,
                              fund_info: dict, sector_median_pe: float = None) -> dict:
        """
        Compute the Rebound Potential Score (0-100) for a single stock.

        Returns dict with sub-scores, flags, and the final Rebound Score.
        """
        result = {
            'rebound_score':   0.0,
            'oversold_score':  0.0,
            'valuation_score': 0.0,
            'growth_score':    0.0,
            'technical_score': 0.0,
            'momentum_score':  0.0,
            'flag_52w_low':    'NO',
            'flag_oversold':   'NO',
            'pct_from_52w_high': 0.0,
            'pct_from_52w_low':  0.0,
            'rsi_latest':       50.0,
            'high_52w':         0.0,
            'low_52w':          0.0,
            'flag_double_bottom': 'NO',
            'double_bottom_stage': 'None',
            'double_bottom_score': 0.0,
        }

        if price_df.empty or 'close' not in price_df.columns:
            return result

        closes = price_df['close'].dropna()
        if len(closes) < 20:
            return result

        current = float(closes.iloc[-1])
        window = min(252, len(closes))
        high_52w = float(closes.iloc[-window:].max())
        low_52w  = float(closes.iloc[-window:].min())

        pct_from_high = (current - high_52w) / high_52w * 100 if high_52w else 0.0
        pct_from_low  = (current - low_52w)  / low_52w  * 100 if low_52w  else 0.0

        result['high_52w']           = round(high_52w, 2)
        result['low_52w']            = round(low_52w, 2)
        result['pct_from_52w_high']  = round(pct_from_high, 2)
        result['pct_from_52w_low']   = round(pct_from_low, 2)

        # Flags
        if 0 <= pct_from_low <= 15:
            result['flag_52w_low'] = 'YES'
        down_pct = abs(pct_from_high)
        if 30 <= down_pct <= 60:
            result['flag_oversold'] = 'YES'

        # ---- Oversold Score (30% weight) --------------------------------
        o = 0.0
        # Sub-component 1: Distance from 52W high
        if 30 <= down_pct <= 60:
            o += 100
        elif 60 < down_pct <= 80:
            o += 70
        elif 10 <= down_pct < 30:
            o += 40
        else:
            o += 15

        # Sub-component 2: Distance from 52W low
        if 0 <= pct_from_low <= 15:
            o += 100
        elif 15 < pct_from_low <= 30:
            o += 70
        elif 30 < pct_from_low <= 50:
            o += 40
        else:
            o += 15

        # Sub-component 3: RSI
        delta = closes.diff()
        gain  = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss  = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs    = gain / (loss + 1e-9)
        rsi   = float((100 - 100 / (1 + rs)).iloc[-1])
        result['rsi_latest'] = round(rsi, 1)

        if 25 <= rsi <= 45:
            o += 100
        elif 45 < rsi <= 55:
            o += 70
        elif rsi < 25:
            o += 50   # deeply oversold — could be distressed
        else:
            o += 30

        oversold_score = o / 3.0
        result['oversold_score'] = round(oversold_score, 1)

        # ---- Valuation Score (25% weight) --------------------------------
        pe  = fund_info.get('trailingPE', None)
        pb  = fund_info.get('priceToBook', None)
        v   = 0.0
        if pe and 0 < pe < 500:
            median_pe = sector_median_pe if sector_median_pe else pe
            pe_ratio  = pe / median_pe if median_pe else 1.0
            if pe_ratio < 0.70:
                v += 100
            elif pe_ratio < 1.00:
                v += 80
            elif pe_ratio < 1.30:
                v += 50
            else:
                v += 20
        else:
            v += 40

        if pb and 0 < pb < 50:
            if pb < 1.0:
                v += 100
            elif pb < 1.5:
                v += 85
            elif pb < 2.5:
                v += 60
            else:
                v += 30
        else:
            v += 40

        valuation_score = v / 2.0
        result['valuation_score'] = round(valuation_score, 1)

        # ---- Growth Score (20% weight) ------------------------------------
        rg = fund_info.get('revenueGrowth', None)
        eg = fund_info.get('earningsGrowth', None)
        g  = 0.0
        if rg is not None and rg > -1:
            rg_pct = rg * 100
            if rg_pct > 15:   g += 100
            elif rg_pct > 10: g += 80
            elif rg_pct > 5:  g += 60
            elif rg_pct > 0:  g += 35
            else:              g += 10
        else:
            g += 30
        if eg is not None and eg > -2:
            eg_pct = eg * 100
            if eg_pct > 20:   g += 100
            elif eg_pct > 10: g += 80
            elif eg_pct > 5:  g += 60
            elif eg_pct > 0:  g += 35
            else:              g += 10
        else:
            g += 30

        growth_score = g / 2.0
        result['growth_score'] = round(growth_score, 1)

        # ---- Technical Score (15% weight) ---------------------------------
        t = 0.0
        # Price stabilizing: 20-day SMA direction
        if len(closes) >= 20:
            sma_20_today = float(closes.rolling(20).mean().iloc[-1])
            sma_20_5d    = float(closes.rolling(20).mean().iloc[-6]) if len(closes) >= 25 else sma_20_today
            slope = sma_20_today - sma_20_5d
            if slope >= 0:
                t += 100   # flat/up = stabilizing
            elif slope >= -sma_20_today * 0.005:
                t += 70    # declining slowly
            else:
                t += 30    # still falling

        # Volume on up-days vs down-days (accumulation signal)
        if 'volume' in price_df.columns and len(price_df) >= 20:
            df_tmp     = price_df.tail(20).copy()
            df_tmp['volume'] = pd.to_numeric(df_tmp['volume'], errors='coerce')
            df_tmp['ret']    = df_tmp['close'].pct_change()
            up_vol   = float(df_tmp[df_tmp['ret'] > 0]['volume'].mean())
            down_vol = float(df_tmp[df_tmp['ret'] < 0]['volume'].mean())
            if down_vol and up_vol > down_vol:
                t += 100   # accumulation
            elif down_vol and up_vol > 0.8 * down_vol:
                t += 70
            else:
                t += 40
        else:
            t += 50

        technical_score = t / 2.0
        result['technical_score'] = round(technical_score, 1)

        # ---- Momentum Score (10% weight) ----------------------------------
        m = 0.0
        def _ret(n):
            if len(closes) < n + 1:
                return 0.0
            return (float(closes.iloc[-1]) - float(closes.iloc[-(n + 1)])) / float(closes.iloc[-(n + 1)]) * 100

        ret_1m_s = _ret(22)
        ret_3m_s = _ret(66)

        if -5 <= ret_1m_s <= 5:    m += 100
        elif -15 <= ret_1m_s < -5: m += 70
        else:                       m += 40

        if -10 <= ret_3m_s <= 10:   m += 100
        elif -20 <= ret_3m_s < -10: m += 70
        else:                        m += 40

        momentum_score = m / 2.0
        result['momentum_score'] = round(momentum_score, 1)

        # ---- Final Rebound Score ------------------------------------------
        rebound_score = (
            0.30 * oversold_score  +
            0.25 * valuation_score +
            0.20 * growth_score    +
            0.15 * technical_score +
            0.10 * momentum_score
        )

        # ---- Double Bottom Optimization ------------------------------------
        db_res = self._detect_double_bottom(sym, closes)
        if db_res['pattern']:
            result['flag_double_bottom'] = 'YES'
            result['double_bottom_stage'] = db_res['stage']
            result['double_bottom_score'] = db_res['score']
            
            # Apply dynamic score boost for best returns based on stage configuration
            boost = 0.0
            if db_res['stage'] == 'Confirmed Bounce':
                boost = 20.0
            elif db_res['stage'] == 'Neckline Breakout':
                boost = 15.0
            elif db_res['stage'] == 'Forming Trough 2':
                boost = 5.0
            
            rebound_score = min(rebound_score + boost, 100.0)
            print(f"    [DB Boost] {sym}: Rebound Score boosted by +{boost:.1f} due to stage '{db_res['stage']}' -> New Rebound Score: {rebound_score:.1f}")
        else:
            result['flag_double_bottom'] = 'NO'
            result['double_bottom_stage'] = 'None'
            result['double_bottom_score'] = 0.0

        result['rebound_score'] = round(rebound_score, 1)

        return result

    # ------------------------------------------------------------------
    # Oversold stock highlights for justification
    # ------------------------------------------------------------------

    def _get_top_oversold_stocks(self, index_name: str, sector_median_pe: float,
                                  top_n: int = 5) -> list:
        """Return top-N oversold stocks in an index with Rebound Scores."""
        constituents = self._get_constituents(index_name)
        fund_data    = self._get_fundamentals(constituents)
        highlights   = []

        for sym in constituents:
            price_df = self._get_all_price_history([sym])
            if price_df.empty:
                continue
            sym_df = price_df[price_df['symbol'] == sym].sort_values('date')
            scores = self.compute_rebound_score(
                sym, sym_df, fund_data.get(sym, {}), sector_median_pe
            )
            if scores['rebound_score'] < 40:
                continue
            highlights.append({
                'symbol':       sym,
                **scores,
                'pe':           fund_data.get(sym, {}).get('trailingPE', None),
                'pb':           fund_data.get(sym, {}).get('priceToBook', None),
                'roe':          (fund_data.get(sym, {}).get('returnOnEquity', 0) or 0) * 100,
                'rev_growth':   (fund_data.get(sym, {}).get('revenueGrowth', 0) or 0) * 100,
                'current_price': sym_df['close'].astype(float).iloc[-1] if not sym_df.empty else 0,
            })

        highlights.sort(key=lambda x: x['rebound_score'], reverse=True)
        return highlights[:top_n]

    # ------------------------------------------------------------------
    # Justification text builder
    # ------------------------------------------------------------------

    def _build_justification(self, index_name: str, scores: dict, tech: dict,
                              fund: dict, oversold_count: dict,
                              vix_rule_fired: bool = False,
                              vix_value: float = 0.0) -> str:
        """Build a human-readable justification string for a selected sector."""
        lines = []

        # Economic Phase
        phase_score = scores.get('score_A', 0)
        lines.append(f"[Economic Phase Alignment — {phase_score:.0f}/100]")
        if index_name in ("Nifty Infra", "Nifty Metal"):
            lines.append("  Mid-to-Late expansion phase favours capex-heavy and commodity sectors. "
                         "India GDP growth 7.7% FY26, capex cycle accelerating.")
        elif index_name in ("Nifty FMCG", "Nifty Pharma"):
            lines.append("  Defensive sector; provides stability in uncertain macro. "
                         "Lower cyclical risk, consistent cash flows.")
        else:
            lines.append("  Sector aligned with current mid-expansion phase (GDP 7.7% FY26, "
                         "moderating to 6.6% FY27). Credit/consumption growth intact.")

        # Seasonality
        month_names = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                       7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
        season_score = scores.get('score_B', 0)
        upcoming_q   = f"Q{self.current_quarter}"
        lines.append(f"\n[Seasonality — {season_score:.0f}/100 | Current: {month_names[self.current_month]} ({upcoming_q})]")
        season_rationale = {
            "Nifty Auto":   "Jul-Sep (Q2) monsoon → rural demand + festive pre-stocking; Oct-Dec (Q3) festive season = peak auto sales.",
            "Nifty Bank":   "Q4 (Jan-Mar) strongest for banks (advance tax, year-end credit disbursals). Current Q2 moderate.",
            "Nifty FMCG":   "Q2-Q3 seasonally strong: rural cash flows post-monsoon; festive demand uplift.",
            "Nifty Realty": "Q4 strongest (budget-driven housing push, stamp duty seasonality). Approaching tailwind in 6 months.",
            "Nifty Infra":  "Q4 & Q1 strongest: Govt capex disbursals, NHAI road awards spike in Mar-Apr.",
            "Nifty Metal":  "Q2-Q3: China construction season + India infra ordering = peak demand.",
            "Nifty IT":     "Q1 (Apr-Jun) typically strong on deal closures. Q2 seasonal for increments/attrition.",
            "Nifty Energy":  "Seasonality moderate. Monsoon slows thermal; H2 sees demand pickup.",
            "Nifty Financial Services": "Q4 strongest: year-end AUM resets, insurance renewal surge.",
            "Nifty Pharma": "Steady year-round; marginal uptick Q3-Q4 on US FDA clearing pipeline.",
            "Nifty Private Bank": "Q4 strongest; current Q2 moderate but improving post-rate cycle.",
            "Nifty PSU Bank": "Q4 strongest on govt capex disbursals. Q2 mild seasonality.",
        }
        lines.append(f"  {season_rationale.get(index_name, 'Seasonal trends moderate for current quarter.')}")

        # Technical
        tech_score = scores.get('score_C', 0)
        lines.append(f"\n[Technical Momentum — {tech_score:.0f}/100]")
        if tech:
            lines.append(f"  Index Level: {tech.get('current', 0):,.0f} | "
                         f"52W High: {tech.get('high_52w', 0):,.0f} | "
                         f"52W Low: {tech.get('low_52w', 0):,.0f}")
            lines.append(f"  % from 52W High: {tech.get('pct_from_high', 0):.1f}% | "
                         f"% above 52W Low: {tech.get('pct_from_low', 0):.1f}%")
            lines.append(f"  RSI (14d): {tech.get('rsi', 0):.1f} | "
                         f"Returns: 1M {tech.get('ret_1m', 0):+.1f}%, "
                         f"3M {tech.get('ret_3m', 0):+.1f}%, "
                         f"6M {tech.get('ret_6m', 0):+.1f}%, "
                         f"1Y {tech.get('ret_1y', 0):+.1f}%")
            rsi = tech.get('rsi', 50)
            down = abs(tech.get('pct_from_high', 0))
            if rsi < 45 and down > 20:
                lines.append(f"  >> Sector is OVERSOLD (RSI {rsi:.0f} < 45, down {down:.0f}% from 52W high). "
                             f"High rebound potential when sentiment shifts.")
            elif rsi < 55 and down > 15:
                lines.append(f"  >> Sector is MILDLY OVERSOLD (RSI {rsi:.0f}, down {down:.0f}% from 52W high). "
                             f"Moderate rebound opportunity.")
            else:
                lines.append(f"  >> Sector showing stabilisation. Price action improving.")
        else:
            lines.append("  Technical data not available; scored on constituent aggregates.")

        # Oversold stock counts
        n_os  = oversold_count.get('oversold_30_60', 0)
        n_52w = oversold_count.get('near_52w_low', 0)
        total = oversold_count.get('total', 1)
        lines.append(f"\n[Oversold Stock Opportunity]")
        lines.append(f"  {n_os}/{total} stocks are down 30–60% from 52W high (prime rebound candidates).")
        lines.append(f"  {n_52w}/{total} stocks are within 15% of 52W low (near support, max upside).")

        # Fundamental
        fund_score = scores.get('score_D', 0)
        lines.append(f"\n[Fundamental Valuation — {fund_score:.0f}/100]")
        if fund:
            pe  = fund.get('median_pe')
            pb  = fund.get('median_pb')
            roe = fund.get('median_roe')
            rg  = fund.get('median_rev_growth')
            eg  = fund.get('median_eps_growth')
            de  = fund.get('median_de')
            lines.append(
                f"  Median P/E: {f'{pe:.1f}' if pe else 'N/A'} | "
                f"P/B: {f'{pb:.1f}' if pb else 'N/A'} | "
                f"ROE: {f'{roe:.1f}%' if roe else 'N/A'}"
            )
            lines.append(
                f"  Revenue Growth: {f'{rg:.1f}%' if rg else 'N/A'} | "
                f"EPS Growth: {f'{eg:.1f}%' if eg else 'N/A'} | "
                f"D/E: {f'{de:.2f}' if de else 'N/A'}"
            )
        else:
            lines.append("  Fundamental data aggregated from constituents.")

        # Macro & Policy
        macro_res = self.compute_dynamic_macro_score(index_name)
        macro_score = scores.get('score_E', 0)
        lines.append(f"\n[Macro & Policy Drivers -- {macro_score:.0f}/100]")
        lines.append(f"  {macro_res.get('rationale', 'Strong policy and macro tailwinds expected.')}")

        # VIX Rule Remark
        if vix_rule_fired:
            lines.append(f"\n[*** VIX Defensive Rule Applied ***]")
            lines.append(f"  India VIX = {vix_value:.1f} (> 20 threshold). {index_name} selected as the "
                         f"LEAST VOLATILE defensive sector to provide portfolio stability during elevated "
                         f"market uncertainty. This is a risk management override, not a conviction pick. "
                         f"Monitor VIX - if it falls below 20, consider rotating back to higher-conviction sectors.")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def select_sectors(self, max_sectors: int = 5) -> dict:
        """
        Run the full 6-factor pre-layer evaluation across all sectoral indices.

        Returns:
            dict with keys:
              - 'selected': list of selected index names (ranked)
              - 'justifications': dict {index_name: justification_text}
              - 'oversold_highlights': dict {index_name: list of stock dicts}
              - 'rejected': list of (index_name, reason) tuples
              - 'all_scores': dict {index_name: score_dict}
              - 'vix': float
              - 'sector_fundamentals': dict {index_name: fund_dict}
        """
        logger.info("SectorSelector: Starting sector evaluation...")
        print("\n" + "=" * 60)
        print("PRE-LAYER: Evaluating Nifty Sectoral Indices...")
        print("=" * 60)

        vix = self._fetch_current_vix()
        print(f"India VIX: {vix:.2f} ({'HIGH — Defensive rule active' if vix > 20 else 'Normal range'})")

        all_scores         = {}
        all_tech           = {}
        all_fund           = {}
        all_oversold       = {}
        index_series_map   = {}

        for index_name in SECTORAL_INDICES:
            print(f"  Evaluating: {index_name}...", end=" ")
            try:
                series = self._reconstruct_index(index_name, days=400)
                index_series_map[index_name] = series

                tech = self._compute_index_technicals(series)
                fund = self._compute_index_fundamentals(index_name)
                scores = self._compute_sector_score(index_name, tech, fund)
                oversold = self._count_oversold_stocks(index_name)

                all_scores[index_name]   = scores
                all_tech[index_name]     = tech
                all_fund[index_name]     = fund
                all_oversold[index_name] = oversold

                print(f"Score={scores['composite']:.1f} | RSI={tech.get('rsi', 0):.0f} | "
                      f"Down={abs(tech.get('pct_from_high', 0)):.0f}%")
            except Exception as e:
                logger.error(f"Error evaluating {index_name}: {e}")
                print(f"ERROR: {e}")

        # ---- Factor F: Structural decline filter ----------------------------
        # Reject indices where all stocks are down 70%+ (structural)
        filtered_scores = {}
        for idx, sc in all_scores.items():
            tech = all_tech.get(idx, {})
            down = abs(tech.get('pct_from_high', 0))
            if down > 70:
                logger.warning(f"Excluding {idx}: down {down:.0f}% from 52W high (structural decline risk)")
                continue
            filtered_scores[idx] = sc

        # ---- Rank sectors by composite score --------------------------------
        ranked = sorted(filtered_scores.keys(),
                        key=lambda x: filtered_scores[x]['composite'], reverse=True)

        # Select top N
        selected = ranked[:min(max_sectors, len(ranked))]

        # ---- Factor F: Correlation swap ------------------------------------
        selected = self._check_correlation(selected, index_series_map, filtered_scores)

        # ---- Factor F: VIX defensive rule ----------------------------------
        selected, vix_rule_fired = self._apply_vix_defensive_rule(selected, vix, filtered_scores)
        vix_fired_sector = selected[-1] if vix_rule_fired else None

        # Ensure minimum 2 sectors
        if len(selected) < 2 and len(ranked) >= 2:
            for r in ranked:
                if r not in selected:
                    selected.append(r)
                    if len(selected) >= 2:
                        break

        # ---- Build justifications and highlights ---------------------------
        justifications    = {}
        oversold_highlights = {}

        print("\n" + "=" * 60)
        print("SELECTED SECTORS:")
        print("=" * 60)
        for rank_num, idx in enumerate(selected, 1):
            scores   = all_scores.get(idx, {})
            tech     = all_tech.get(idx, {})
            fund     = all_fund.get(idx, {})
            oversold = all_oversold.get(idx, {})

            fired = vix_rule_fired and idx == vix_fired_sector
            justifications[idx] = self._build_justification(
                idx, scores, tech, fund, oversold, fired, vix
            )
            median_pe = (fund or {}).get('median_pe')
            highlights = self._get_top_oversold_stocks(idx, median_pe, top_n=5)
            oversold_highlights[idx] = highlights

            print(f"\n  {rank_num}. {idx} (Composite: {scores.get('composite', 0):.1f})")
            print(f"     RSI: {tech.get('rsi', 0):.1f} | Down: {abs(tech.get('pct_from_high', 0)):.1f}% from 52W High")
            print(f"     Top oversold stocks: {[h['symbol'] for h in highlights[:3]]}")

        # ---- Build rejected list -------------------------------------------
        rejected = []
        rejected_candidates = [r for r in ranked if r not in selected][:5]
        for r in rejected_candidates:
            tech = all_tech.get(r, {})
            down = abs(tech.get('pct_from_high', 0))
            rsi  = tech.get('rsi', 50)
            sc   = filtered_scores.get(r, {}).get('composite', 0)
            if rsi > 55 and down < 15:
                reason = (f"Not sufficiently oversold (RSI {rsi:.0f} > 55, only {down:.0f}% below 52W high). "
                          f"Composite score: {sc:.1f}. Less rebound potential vs. selected sectors.")
            elif down > 60:
                reason = (f"Down {down:.0f}% from 52W high — risk of structural decline, not merely cyclical. "
                          f"Fundamental validation required before entry. Score: {sc:.1f}.")
            else:
                reason = (f"Lower composite score ({sc:.1f}) vs. selected sectors. "
                          f"RSI {rsi:.0f}, down {down:.0f}% from 52W high. "
                          f"Revisit if macro/technical improves.")
            rejected.append((r, reason))

        print("\n" + "=" * 60)
        print("PRE-LAYER COMPLETE.")
        print("=" * 60 + "\n")

        return {
            'selected':           selected,
            'justifications':     justifications,
            'oversold_highlights': oversold_highlights,
            'rejected':           rejected,
            'all_scores':         all_scores,
            'vix':                vix,
            'sector_fundamentals': all_fund,
        }
