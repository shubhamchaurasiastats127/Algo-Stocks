import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pytrends.request import TrendReq

# Setup logging
logger = logging.getLogger("MacroSentimentFilter")
logging.basicConfig(level=logging.INFO)

class PytrendsClientWrapper:
    """
    Robust wrapper around TrendReq to handle connection initialization, 
    automatic retries, backoff, and graceful recovery from HTTP 429 Rate Limits.
    """
    def __init__(self, retries=3, backoff_factor=2):
        self.retries = retries
        self.backoff_factor = backoff_factor
        self._init_client()

    def _init_client(self):
        # Timezone offset 330 is UTC+5:30 (India Standard Time)
        self.pytrends = TrendReq(hl='en-IN', tz=330, timeout=(10, 25))

    def fetch_interest_over_time(self, keywords, timeframe='today 3-m', geo='IN'):
        """
        Fetch interest over time with retries and exponential backoff.
        """
        for attempt in range(self.retries):
            try:
                logger.info(f"Fetching Google Trends for keywords: {keywords} (Attempt {attempt+1})")
                self.pytrends.build_payload(keywords, timeframe=timeframe, geo=geo)
                df = self.pytrends.interest_over_time()
                if df is not None and not df.empty:
                    return df
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Error fetching data on attempt {attempt+1}: {e}")
                if attempt < self.retries - 1:
                    sleep_time = self.backoff_factor ** attempt
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                    self._init_client()  # Re-initialize client on failure
                else:
                    logger.error("All retries exhausted for fetching Google Trends data.")
                    raise e
        return pd.DataFrame()

class MacroSentimentEngine:
    """
    Layer 3: Macro Factor Sentiment Filtering Engine
    Pulls daily search trends, cleans/normalizes data, maps macro trends to sectors,
    handles general macro risk-off regimes, and prioritizes/filters Layer 1 & 2 stocks.
    """
    def __init__(self, zscore_window=14, risk_off_threshold=2.0):
        self.zscore_window = zscore_window
        self.risk_off_threshold = risk_off_threshold
        self.client = PytrendsClientWrapper()

    def clean_trends_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cleans interest over time data:
        1. Detects and removes the 'isPartial' column/flag to avoid feeding incomplete trends.
        2. Fills missing values.
        """
        if df.empty:
            return df
        
        df_cleaned = df.copy()
        
        # Clean 'isPartial' column
        if 'isPartial' in df_cleaned.columns:
            # Filter out rows where isPartial is True (usually the latest day)
            df_cleaned = df_cleaned[df_cleaned['isPartial'] != 'True']
            df_cleaned = df_cleaned[df_cleaned['isPartial'] != True]
            df_cleaned = df_cleaned.drop(columns=['isPartial'])
            
        return df_cleaned

    def calculate_rolling_zscore(self, series: pd.Series) -> pd.Series:
        """
        Calculate the 14-day rolling Z-Score of the trend line.
        This normalizes the scale and measures momentum/acceleration.
        """
        rolling_mean = series.rolling(window=self.zscore_window, min_periods=5).mean()
        rolling_std = series.rolling(window=self.zscore_window, min_periods=5).std()
        
        # Prevent division by zero
        rolling_std = rolling_std.replace(0, np.nan).fillna(1.0)
        
        z_scores = (series - rolling_mean) / rolling_std
        return z_scores.fillna(0.0)

    def calculate_sentiment_multipliers(self, trends_df: pd.DataFrame) -> dict:
        """
        Computes rolling Z-Scores for all macro keywords and returns
        the latest multiplier state for each sector and global risk-off state.
        """
        multipliers = {
            'Bank': 0.0,
            'Auto': 0.0,
            'IT': 0.0,
            'risk_off_active': False
        }
        
        if trends_df.empty:
            return multipliers

        # 1. Calculate Rolling Z-Scores for all columns
        z_scores_df = pd.DataFrame(index=trends_df.index)
        for col in trends_df.columns:
            z_scores_df[col] = self.calculate_rolling_zscore(trends_df[col])
            
        # Get the latest daily Z-score value
        latest = z_scores_df.iloc[-1]
        logger.info(f"Latest rolling trend Z-Scores: \n{latest.to_string()}")

        # 2. Sector Mapping Directional Logic
        # PRIVATE/PSU BANKS & NBFC: Repo Rate (Negative) vs Home Loan (Positive)
        repo_rate_z = latest.get('Repo Rate', 0.0)
        home_loan_z = latest.get('Home Loan', 0.0)
        # Scale to [-1.0, 1.0] range
        multipliers['Bank'] = np.clip(home_loan_z - repo_rate_z, -1.0, 1.0)

        # AUTOMOTIVE: Crude Oil (Negative input cost) vs Car Loan (Positive)
        crude_oil_z = latest.get('Crude Oil', 0.0)
        car_loan_z = latest.get('Car Loan', 0.0)
        multipliers['Auto'] = np.clip(car_loan_z - crude_oil_z, -1.0, 1.0)

        # TECH / IT SERVICES: Nifty IT (Positive) vs Layoffs (Negative)
        layoffs_z = latest.get('Layoffs', 0.0)
        nifty_it_z = latest.get('Nifty IT', 0.0)
        multipliers['IT'] = np.clip(nifty_it_z - layoffs_z, -1.0, 1.0)

        # 3. Global Macro Risk-Off Regimes
        inflation_z = latest.get('Inflation', 0.0)
        gold_price_z = latest.get('Gold Price', 0.0)
        
        # Risk-off triggers if either Gold Price or Inflation Z-Score exceeds +2.0
        if inflation_z > self.risk_off_threshold or gold_price_z > self.risk_off_threshold:
            multipliers['risk_off_active'] = True
            logger.warning(
                f"🚨 SYSTEMIC RISK-OFF REGIME TRIGGERED! "
                f"Inflation Z-Score: {inflation_z:.2f} | Gold Price Z-Score: {gold_price_z:.2f}"
            )
            
        return multipliers

    def apply_filter(self, df_stocks: pd.DataFrame, top_n=5, as_of_date=None) -> pd.DataFrame:
        """
        Executes Layer 3 filtering and prioritization:
        - Maps incoming stocks to their macro proxies.
        - Calculates the combined score and applies risk-off portfolio reduction.
        - Filters out negative/hostile scoring stocks.
        """
        # Validate required columns
        required_cols = {'Ticker', 'Sector', 'Base_Score'}
        if not required_cols.issubset(df_stocks.columns):
            raise ValueError(f"Input DataFrame must contain columns: {required_cols}")
            
        # Determine timeframe based on as_of_date
        timeframe = 'today 3-m'
        if as_of_date is not None:
            from datetime import date, timedelta
            if isinstance(as_of_date, str):
                try:
                    as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        as_of_date = pd.to_datetime(as_of_date).date()
                    except Exception:
                        pass
            elif hasattr(as_of_date, 'date'):
                as_of_date = as_of_date.date()
                
            if isinstance(as_of_date, (datetime, date)):
                start_date = as_of_date - timedelta(days=90)
                timeframe = f"{start_date.strftime('%Y-%m-%d')} {as_of_date.strftime('%Y-%m-%d')}"
            
        # Define keywords for India trends
        keywords = ["Repo Rate", "Home Loan", "Crude Oil", "Car Loan", "Layoffs", "Nifty IT", "Inflation", "Gold Price"]
        
        # Fetch Google Trends data
        # Note: Trends limit is 5 keywords per query. We split keywords into batches of max 5.
        batch1 = ["Repo Rate", "Home Loan", "Crude Oil", "Car Loan", "Layoffs"]
        batch2 = ["Nifty IT", "Inflation", "Gold Price"]
        
        try:
            df_trends1 = self.client.fetch_interest_over_time(batch1, timeframe=timeframe)
            df_trends2 = self.client.fetch_interest_over_time(batch2, timeframe=timeframe)
            
            df_trends1 = self.clean_trends_data(df_trends1)
            df_trends2 = self.clean_trends_data(df_trends2)
            
            # Combine trend series
            trends_df = pd.concat([df_trends1, df_trends2], axis=1)
            # Remove duplicate columns if any
            trends_df = trends_df.loc[:, ~trends_df.columns.duplicated()]
        except Exception as e:
            logger.error(f"Failed to fetch trends data for timeframe {timeframe}: {e}. Falling back to default baseline neutral scoring.")
            trends_df = pd.DataFrame()

        # Compute sentiment multipliers
        multipliers = self.calculate_sentiment_multipliers(trends_df)
        
        final_picks = []
        for idx, row in df_stocks.iterrows():
            ticker = row['Ticker']
            sector = row['Sector']
            base_score = row['Base_Score']
            
            # Get the sector sentiment multiplier
            # Bounded between -1.0 (extreme hostile) and +1.0 (extreme supportive)
            sentiment_mult = 0.0
            sector_lower = str(sector).lower()
            if any(s in sector_lower for s in ['banking', 'financial services', 'nbfc', 'bank', 'finance']):
                sentiment_mult = multipliers['Bank']
            elif any(s in sector_lower for s in ['auto', 'automotive']):
                sentiment_mult = multipliers['Auto']
            elif any(s in sector_lower for s in ['it', 'tech', 'software']):
                sentiment_mult = multipliers['IT']
                
            # Base logic: final combined score combines base score and macro sentiment
            # Combined Score = Base_Score * (1.0 + Sentiment_Multiplier)
            combined_score = base_score * (1.0 + sentiment_mult)
            
            # Systemic risk-off beta-reduction filter (Scale down entire portfolio score by 30% if triggered)
            if multipliers['risk_off_active']:
                combined_score *= 0.70
                
            final_picks.append({
                'Ticker': ticker,
                'Sector': sector,
                'Base_Score': base_score,
                'Macro_Sentiment_Multiplier': sentiment_mult,
                'Systemic_Risk_Off': multipliers['risk_off_active'],
                'Combined_Score': round(combined_score, 2)
            })
            
        df_results = pd.DataFrame(final_picks)
        
        # FILTER RULES: 
        # 1. Filter out stocks with combined score <= 0
        # 2. Filter out stocks where macro sentiment is highly hostile (multiplier < -0.3)
        df_filtered = df_results[
            (df_results['Combined_Score'] > 0) & 
            (df_results['Macro_Sentiment_Multiplier'] >= -0.3)
        ].copy()
        
        # Sort by Combined_Score descending and pick top_n
        df_sorted = df_filtered.sort_values('Combined_Score', ascending=False)
        return df_sorted.head(top_n).reset_index(drop=True)

# ------------------------------------------------------------------
# Test & Demo Sandbox Execution
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Mock data outputted from Layer 1 & 2
    mock_input_stocks = pd.DataFrame([
        {'Ticker': 'HDFCBANK.NS', 'Sector': 'Banking', 'Base_Score': 85.0},
        {'Ticker': 'SBI.NS', 'Sector': 'Banking', 'Base_Score': 72.0},
        {'Ticker': 'MARUTI.NS', 'Sector': 'Auto', 'Base_Score': 88.0},
        {'Ticker': 'TATAMOTORS.NS', 'Sector': 'Auto', 'Base_Score': 90.0},
        {'Ticker': 'TCS.NS', 'Sector': 'IT', 'Base_Score': 92.0},
        {'Ticker': 'INFY.NS', 'Sector': 'IT', 'Base_Score': 78.0},
        {'Ticker': 'RELIANCE.NS', 'Sector': 'Oil & Gas', 'Base_Score': 80.0} # Neutral Sector
    ])
    
    print("\n--- Initial Recommended Pool (Layer 1 & 2 Outputs) ---")
    print(mock_input_stocks)
    
    engine = MacroSentimentEngine()
    
    try:
        final_basket = engine.apply_filter(mock_input_stocks, top_n=5)
        print("\n--- Final Filtered Portfolio Basket (Layer 3 Outputs) ---")
        print(final_basket)
    except Exception as err:
        print(f"Test Execution Failed: {err}")
