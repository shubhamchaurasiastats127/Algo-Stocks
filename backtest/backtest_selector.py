# pyrefly: ignore [missing-import]
import os
import sys
import logging
from datetime import datetime, timedelta
# pyrefly: ignore [missing-import]
import pandas as pd
# pyrefly: ignore [missing-import]
import numpy as np
# pyrefly: ignore [missing-import]
import yfinance as yf

# Allow importing from src directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# pyrefly: ignore [missing-import]
from sector_selector import SectorSelector

class BacktestSectorSelector(SectorSelector):
    """
    Subclass of SectorSelector modified for backtesting to prevent lookahead bias.
    Time-gates all index reconstructions, stock histories, and India VIX queries
    to the target simulation date.
    """
    def __init__(self, config: dict, as_of_date):
        super().__init__(config)
        self.today = as_of_date
        self.current_month = self.today.month
        self.current_quarter = (self.current_month - 1) // 3 + 1

    def _get_price_history(self, symbols: list, days: int = 365) -> pd.DataFrame:
        """Return pivot table (date x symbol) of closing prices capped at self.today."""
        if not symbols:
            return pd.DataFrame()
        start_date = (self.today - timedelta(days=days)).strftime('%Y-%m-%d')
        end_date = self.today.strftime('%Y-%m-%d')
        conn = self._get_conn()
        placeholders = ",".join(["%s"] * len(symbols))
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT symbol, date, close FROM price_data "
                f"WHERE symbol IN ({placeholders}) AND date >= %s AND date <= %s ORDER BY date",
                tuple(symbols) + (start_date, end_date)
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
        """Return full OHLCV price history capped at self.today."""
        if not symbols:
            return pd.DataFrame()
        conn = self._get_conn()
        placeholders = ",".join(["%s"] * len(symbols))
        end_date = self.today.strftime('%Y-%m-%d')
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT symbol, date, open, high, low, close, volume FROM price_data "
                f"WHERE symbol IN ({placeholders}) AND date <= %s ORDER BY date",
                tuple(symbols) + (end_date,)
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

    def _fetch_current_vix(self) -> float:
        """Fetch VIX close price as of the target simulation date."""
        try:
            start_date = (self.today - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = (self.today + timedelta(days=1)).strftime('%Y-%m-%d')
            df = yf.download("^INDIAVIX", start=start_date, end=end_date, progress=False)
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
        except Exception as e:
            logging.error(f"Error fetching historical VIX for {self.today}: {e}")
        return 15.0
