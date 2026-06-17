import pandas as pd
# pyrefly: ignore [missing-import]
import numpy as np

class ScoringEngine:
    def __init__(self, config):
        self.config = config

    def calculate_layer_1_fundamentals(self, fund_metrics):
        """Layer 1: Fundamental Health & Valuation"""
        f_score = 0
        reasons = []
        
        # Growth
        rev_g = fund_metrics.get('revenue_growth', 0)
        f_score += min(rev_g * 200, 30)
        if rev_g > 0.15: reasons.append(f"Strong Revenue Growth ({rev_g:.1%})")
        
        # Efficiency
        roe = fund_metrics.get('roe', 0)
        f_score += min(roe * 200, 30)
        if roe > 0.15: reasons.append(f"High ROE ({roe:.1%})")
        
        # Leverage
        de = fund_metrics.get('debt_to_equity', 1.0)
        if de < 1.0: 
            f_score += 20
            reasons.append(f"Low Leverage (D/E: {de:.2f})")
        else:
            f_score += 10
            
        # Margins
        margin = fund_metrics.get('profit_margin', 0)
        f_score += min(margin * 100, 20)
        if margin > 0.10: reasons.append(f"Healthy Margins ({margin:.1%})")
        
        # Valuation Adjustment
        pe = fund_metrics.get('pe_ratio', 100)
        pb = fund_metrics.get('pb_ratio', 10)
        v_score = 0
        if pe < 20: v_score += 50
        elif pe < 40: v_score += 30
        else: v_score += 10
        
        if pb < 3: v_score += 50
        else: v_score += 20

        total_l1 = (f_score * 0.7) + (v_score * 0.3)
        desc = " | ".join(reasons) if reasons else "Average Fundamentals"
        
        return total_l1, desc

    def calculate_layer_2_technicals(self, tech_df):
        """Layer 2: Technical Trend & Price Action"""
        latest = tech_df.iloc[-1]
        t_score = 0
        reasons = []
        
        # Trend Structure
        if latest['close'] > latest['sma_50'] > latest['sma_200']:
            t_score += 40
            reasons.append("Bullish Trend Alignment (Price > SMA50 > SMA200)")
        
        # Momentum
        if 40 < latest['rsi'] < 70:
            t_score += 30
            reasons.append("Constructive RSI (Neutral-Bullish)")
        elif latest['rsi'] > 70:
            t_score += 10
            reasons.append("Overbought RSI")
            
        # Slope
        if latest['trend_slope'] > 0:
            t_score += 30
            reasons.append("Positive Trend Slope")
            
        # Price Action (Bonus/Constraint)
        pa_score = 50
        if latest['is_breakout']:
            pa_score += 40
            reasons.append("Volume Breakout Detected")
        if latest['is_pullback']:
            pa_score += 30
            reasons.append("Bullish Pullback Entry")
            
        total_l2 = (t_score * 0.6) + (min(pa_score, 100) * 0.4)
        desc = " | ".join(reasons) if reasons else "Neutral Setup"
        
        return total_l2, desc

    def calculate_layer_3_statistical(self, stat_results):
        """Layer 3: Statistical Edge"""
        p_target, p_stop, prediction, avg_horizon = stat_results
        s_score = 0
        reasons = []
        
        # Monte Carlo Target Probability
        s_score += (p_target * 70)
        reasons.append(f"MC Target Prob: {p_target:.1%}")
        
        # Ridge Regression Prediction
        if prediction > 0.02:
            s_score += 30
            reasons.append(f"Model Predicts +{prediction:.1%} (10d)")
        elif prediction > 0:
            s_score += 15
            reasons.append(f"Model Predicts Positive Return")
            
        reasons.append(f"Expected Horizon: {avg_horizon:.1f}d")
        desc = " | ".join(reasons)
        return min(s_score, 100), desc
 
    def get_final_recommendation(self, l1, l2, l3, avg_horizon):
        weights = self.config['weights']
        # Re-mapping existing weights to our layers
        # fund + val = L1
        # tech + price = L2
        # stat + risk = L3
        w_l1 = weights['fundamentals'] + weights['valuation']
        w_l2 = weights['technical_trend'] + weights['price_action']
        w_l3 = weights['stat_edge'] + weights['risk_regime']
        
        final_score = (l1[0] * w_l1) + (l2[0] * w_l2) + (l3[0] * w_l3)
        
        # Confidence calculation (How aligned are the layers?)
        # Std dev of scores (low std dev = high alignment = high confidence)
        scores = [l1[0], l2[0], l3[0]]
        alignment = 1 - (np.std(scores) / 100) 
        confidence = alignment * (final_score / 100)
        
        if final_score >= self.config['thresholds']['buy']:
            action = "BUY"
        elif final_score >= self.config['thresholds']['wait']:
            action = "WAIT"
        elif final_score <= self.config['thresholds']['sell']:
            action = "SELL"
        else:
            action = "AVOID"
            
        return {
            'action': action,
            'score': round(final_score, 1),
            'confidence': round(confidence, 2),
            'layer_1': l1,
            'layer_2': l2,
            'layer_3': l3,
            'horizon': f"{round(avg_horizon, 1)} days"
        }
