# pyrefly: ignore [missing-import]
import os
import sys
import json
import logging
import pandas as pd

# Allow importing from src directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# pyrefly: ignore [missing-import]
from data_manager import DataFetcher

class BacktestDataFetcher(DataFetcher):
    """
    A time-gated subclass of DataFetcher that filters out price data
    occurring after the target simulation date to prevent lookahead bias.
    Also optimizes fundamentals retrieval by fetching directly from MySQL.
    """
    def __init__(self, config: dict, as_of_date):
        super().__init__(config)
        self.as_of_date = as_of_date
        self.as_of_date_str = as_of_date.strftime('%Y-%m-%d')

    def get_stock_data(self, symbol: str, days: int = 730) -> pd.DataFrame:
        """Fetch stock price data directly from MySQL DB cache, fallback to yfinance if empty."""
        df = self.cache.get_price_data(symbol)
        if df.empty:
            df = super().get_stock_data(symbol, days=days)
        if not df.empty:
            df = df[df.index.date <= self.as_of_date]
        return df

    def get_fundamentals(self, symbol: str) -> dict:
        """Fetch cached fundamentals directly from MySQL database to speed up the backtest."""
        conn = self.cache.pool.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT data_json FROM fundamentals WHERE symbol = %s",
                (symbol,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as e:
            logging.error(f"Error loading cached fundamentals for {symbol}: {e}")
        finally:
            cursor.close()
            conn.close()

        # Fallback to fetching live from yfinance if missing from DB cache
        return super().get_fundamentals(symbol)
