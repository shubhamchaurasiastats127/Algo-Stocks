import pandas as pd
import numpy as np

class FeatureEngine:
    def __init__(self, config):
        self.config = config

    def compute_technicals(self, df):
        if df.empty or len(df) < 200:
            return df
        
        # Trend filters (Manual SMA)
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        df['sma_200'] = df['close'].rolling(window=200).mean()
        
        # RSI Implementation
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR Implementation
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr_percent'] = tr.rolling(window=14).mean() / df['close']
        
        # Trend Slope (Last 20 days)
        def get_slope(series):
            if len(series) < 20 or np.any(np.isnan(series)):
                return 0.0
            y = series.values
            x = np.arange(len(y))
            return np.polyfit(x, y, 1)[0]
        
        df['trend_slope'] = df['close'].rolling(20).apply(get_slope)
        
        # Relative Strength (Simple vs closing mean)
        df['rel_strength'] = df['close'] / df['close'].rolling(252).mean()
        
        return df

    def compute_price_action(self, df):
        if df.empty or len(df) < 20:
            return df
        
        # Breakout: Close > max(last 20) and Volume > 2x avg(last 20)
        df['max_20'] = df['close'].shift(1).rolling(20).max()
        df['avg_vol_20'] = df['volume'].shift(1).rolling(20).mean()
        
        df['is_breakout'] = (df['close'] > df['max_20']) & (df['volume'] > 1.5 * df['avg_vol_20'])
        
        # Pullback: Close < 20 SMA but Trend is up (50 > 200)
        if 'sma_20' in df.columns and 'sma_50' in df.columns and 'sma_200' in df.columns:
            df['is_pullback'] = (df['close'] < df['sma_20']) & (df['sma_50'] > df['sma_200']) & (df['close'] > df['sma_50'])
        else:
            df['is_pullback'] = False
        
        return df

    def extract_fundamental_metrics(self, info):
        # Extract from yfinance info dict
        metrics = {
            'revenue_growth': info.get('revenueGrowth', 0),
            'eps_growth': info.get('earningsGrowth', 0),
            'profit_margin': info.get('profitMargins', 0),
            'roe': info.get('returnOnEquity', 0),
            'debt_to_equity': info.get('debtToEquity', 0) / 100 if info.get('debtToEquity') else 0,
            'pe_ratio': info.get('trailingPE', 0),
            'pb_ratio': info.get('priceToBook', 0),
            'market_cap_cr': info.get('marketCap', 0) / 10**7
        }
        return metrics

    def compute_statistical_features(self, df):
        if df.empty or len(df) < 30:
            return df
        
        returns = df['close'].pct_change()
        df['return_skew'] = returns.rolling(30).skew()
        df['return_kurt'] = returns.rolling(30).kurt()
        df['volatility_regime'] = returns.rolling(30).std() * np.sqrt(252)
        
        return df
