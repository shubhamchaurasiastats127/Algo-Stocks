# pyrefly: ignore [missing-import]
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

class StatModel:
    def __init__(self, config):
        self.config = config

    def run_monte_carlo(self, current_price, history_df, target_pct=None, stop_pct=None):
        returns = history_df['close'].pct_change().dropna()
        horizon = self.config['simulation']['horizon_days']
        if returns.empty:
            return 0.5, 0.5, float(horizon)
        
        if target_pct is None:
            target_pct = self.config.get('simulation', {}).get('target_pct', 0.06)
        if stop_pct is None:
            stop_pct = self.config.get('simulation', {}).get('stop_pct', 0.015)
        
        mu = returns.mean()
        sigma = returns.std()
        iterations = self.config['simulation']['iterations']
        
        # Simulating drift and volatility
        # Shape: (horizon, iterations)
        daily_returns = np.random.normal(mu, sigma, (horizon, iterations))
        price_paths = current_price * np.cumprod(1 + daily_returns, axis=0)
        
        # Check hitting target or stop
        target_price = current_price * (1 + target_pct)
        stop_price = current_price * (1 - stop_pct)
        
        hit_target_matrix = price_paths >= target_price
        hit_stop_matrix = price_paths <= stop_price
        hit_matrix = hit_target_matrix | hit_stop_matrix
        
        hit_target = np.any(hit_target_matrix, axis=0)
        hit_stop = np.any(hit_stop_matrix, axis=0)
        
        p_target = np.mean(hit_target)
        p_stop = np.mean(hit_stop)
        
        # Calculate first day hitting target or stop for each iteration
        any_hit = np.any(hit_matrix, axis=0)
        first_hit_day = np.where(any_hit, np.argmax(hit_matrix, axis=0) + 1, horizon)
        avg_horizon = float(np.mean(first_hit_day))
        
        return p_target, p_stop, avg_horizon

    def predict_forward_return(self, feature_df):
        # Very simple incremental regression training on available history
        # In a real app, this would be pre-trained or walk-forward
        # For demonstration, we'll use a fixed set of features
        valid_df = feature_df.dropna(subset=['trend_slope', 'rel_strength', 'rsi'])
        if len(valid_df) < 60:
            return 0.0
        
        X = valid_df[['trend_slope', 'rel_strength', 'rsi']]
        y = valid_df['close'].shift(-10) / valid_df['close'] - 1
        y = y.dropna()
        X = X.loc[y.index]
        
        model = Ridge()
        model.fit(X[:-10], y[:-10]) # Avoid lookahead for training
        
        latest_X = X.iloc[[-1]]
        prediction = model.predict(latest_X)[0]
        
        return prediction
