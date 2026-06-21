# pyrefly: ignore [missing-import]
import os
import sys
import logging
from datetime import datetime, date
# pyrefly: ignore [missing-import]
import numpy as np
# pyrefly: ignore [missing-import]
import pandas as pd
# pyrefly: ignore [missing-import]
import yaml

# Allow importing from src and backtest directories
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# pyrefly: ignore [missing-import]
from engine import StockAnalysisEngine
from backtest_data_manager import BacktestDataFetcher
from backtest_selector import BacktestSectorSelector

class BacktestStockAnalysisEngine(StockAnalysisEngine):
    """
    Subclass of StockAnalysisEngine that swaps in BacktestDataFetcher and
    BacktestSectorSelector for time-gated historical runs.
    """
    def __init__(self, config_path: str, as_of_date: datetime.date):
        super().__init__(config_path)
        self.as_of_date = as_of_date
        
        # Swapping in time-gated components
        self.fetcher = BacktestDataFetcher(self.config, as_of_date)
        self.selector = BacktestSectorSelector(self.config, as_of_date)

    def run(self, limit: int = None, run_name: str = None) -> pd.DataFrame:
        """
        Runs the sector selection and stock picking pipeline for the historical date.
        Generates standard reports and returns the final union DataFrame.
        """
        # ---- Step 1: Pre-Layer Sector Selection ----
        sector_result = self.selector.select_sectors(max_sectors=5)
        selected_indices = sector_result['selected']
        justifications = sector_result['justifications']
        oversold_highlights = sector_result['oversold_highlights']
        rejected_sectors = sector_result['rejected']
        all_scores = sector_result['all_scores']
        vix = sector_result['vix']
        sector_fund = sector_result['sector_fundamentals']

        if not selected_indices:
            print(f"[{self.as_of_date}] No indices selected. Defaulting to Nifty 500.")
            selected_indices = ["Nifty 500"]

        # ---- Step 2: Run Analysis on constituents of selected indices ----
        subfolder = f"backtest/{run_name}" if run_name else "backtest/run"
        all_union_results = []
        
        for index_name in selected_indices:
            fund = sector_fund.get(index_name, {})
            sector_median_pe = (fund or {}).get('median_pe')
            results = self.run_analysis_for_index(
                index_name,
                sector_median_pe=sector_median_pe,
                subfolder=subfolder,
                limit=limit
            )
            all_union_results.extend(results)

        if not all_union_results:
            print(f"[{self.as_of_date}] No results generated. Skipping.")
            return pd.DataFrame()

        df_union = pd.DataFrame(all_union_results)
        df_union = self._deduplicate_union(df_union)
        
        # Initialize default L3 columns in case filter is skipped
        df_union['Macro_Sentiment_Multiplier'] = 0.0
        df_union['Systemic_Risk_Off'] = False
        df_union['Combined_Score'] = df_union['Final_Rank_Score']
        df_union['Base_Rank_Score'] = df_union['Final_Rank_Score']
        
        # ---- Step 2.5: Apply Layer 3 Macro Sentiment Filter ----
        try:
            from macro_sentiment_filter import MacroSentimentEngine
            print(f"[{self.as_of_date}] Applying Layer 3 Macro Sentiment Filter...")
            mse = MacroSentimentEngine()
            
            # Map columns for filter input
            df_for_filter = df_union.copy()
            df_for_filter['Ticker'] = df_for_filter['Symbol']
            df_for_filter['Sector'] = df_for_filter['Index_Name']
            df_for_filter['Base_Score'] = df_for_filter['Final_Rank_Score']
            
            df_filtered_l3 = mse.apply_filter(df_for_filter, top_n=len(df_for_filter), as_of_date=self.as_of_date)
            
            if not df_filtered_l3.empty:
                # Merge the L3 filter scores back into the original df_union columns
                df_filtered_l3 = df_filtered_l3.rename(columns={'Ticker': 'Symbol'})
                df_union_base = df_union.drop(columns=['Macro_Sentiment_Multiplier', 'Systemic_Risk_Off', 'Combined_Score', 'Base_Rank_Score'])
                df_union = df_union_base.merge(
                    df_filtered_l3[['Symbol', 'Macro_Sentiment_Multiplier', 'Systemic_Risk_Off', 'Combined_Score']], 
                    on='Symbol', 
                    how='inner'
                )
                # Keep track of original score
                df_union['Base_Rank_Score'] = df_union['Final_Rank_Score']
                # Update Final_Rank_Score to be Combined_Score
                df_union['Final_Rank_Score'] = df_union['Combined_Score']
                # Sort by new Final_Rank_Score descending
                df_union = df_union.sort_values('Final_Rank_Score', ascending=False).reset_index(drop=True)
            else:
                print(f"[{self.as_of_date}] Warning: Layer 3 filter returned empty results. Keeping unfiltered results.")
        except Exception as e:
            print(f"[{self.as_of_date}] Error running Layer 3 Macro Sentiment filter: {e}. Skipping filter.")
            
        # Validate results
        self._validate_results(df_union)

        # ---- Step 3: Save Consolidated Report ----
        output_path = self.writer.save_consolidated_report(
            df_union=df_union,
            selected_indices=selected_indices,
            justifications=justifications,
            oversold_highlights=oversold_highlights,
            rejected_sectors=rejected_sectors,
            all_scores=all_scores,
            vix=vix,
            subfolder=subfolder,
        )
        print(f"[{self.as_of_date}] Consolidated Excel saved: {output_path}")

        # ---- Step 4: Save Sector Results JSON ----
        import json
        out_dir = os.path.join(self.config['paths']['output_folder'], subfolder)
        os.makedirs(out_dir, exist_ok=True)
        json_path = os.path.join(out_dir, "sector_results.json")

        def sanitize_for_json(obj):
            if isinstance(obj, dict):
                return {str(k): sanitize_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_for_json(x) for x in obj]
            elif isinstance(obj, (datetime, date)):
                return obj.isoformat()
            elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
                return None
            elif isinstance(obj, (np.integer, np.floating)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return sanitize_for_json(obj.tolist())
            else:
                return obj

        sanitized_results = sanitize_for_json({
            'selected_indices': selected_indices,
            'justifications': justifications,
            'oversold_highlights': oversold_highlights,
            'rejected_sectors': rejected_sectors,
            'all_scores': all_scores,
            'vix': vix
        })

        with open(json_path, "w") as f:
            json.dump(sanitized_results, f, indent=4)
        print(f"[{self.as_of_date}] Sector Selection metadata saved: {json_path}")
        
        return df_union

def run_backtest(limit: int = None, backtest_dates: list = None):
    """
    Main orchestrator of backtesting. Runs simulated stock picks.
    """
    config_path = os.path.join(os.path.dirname(__file__), '../config/config.yaml')
    
    if backtest_dates is None:
        # Target backtest dates (approx 7th of each month, 6 months back)
        backtest_dates = [
            datetime(2025, 12, 7).date(),  # T-180
            datetime(2026, 1, 7).date(),   # T-150
            datetime(2026, 2, 7).date(),   # T-120
            datetime(2026, 3, 7).date(),   # T-90
            datetime(2026, 4, 7).date(),   # T-60
            datetime(2026, 5, 7).date(),   # T-30
        ]
    
    print("=" * 65)
    print("STARTING ALGO_STOCKS BACKTEST PROCESS")
    print(f"Target Dates: {[d.strftime('%Y-%m-%d') for d in backtest_dates]}")
    print("=" * 65)
    
    for run_date in backtest_dates:
        date_str = run_date.strftime('%Y%m%d')
        print(f"\n>>> Running simulation for date: {run_date} (T-{date_str})")
        
        # Ensure numpy random seed is fixed for MC simulation reproducibility
        np.random.seed(42)
        
        engine = BacktestStockAnalysisEngine(config_path, run_date)
        df_union = engine.run(limit=limit, run_name=f"run_{date_str}")
        
        if not df_union.empty:
            out_dir = os.path.join(engine.config['paths']['output_folder'], f"backtest/run_{date_str}")
            os.makedirs(out_dir, exist_ok=True)
            picks_path = os.path.join(out_dir, "picks.csv")
            df_union.to_csv(picks_path, index=False)
            print(f"Saved picks to {picks_path}")
            
    print("\nBacktesting simulation runs complete. Next: Run performance tracker.")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--dates', type=str, help='Comma-separated list of YYYY-MM-DD dates')
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()
    
    limit_val = args.limit
    if args.test:
        limit_val = 2
        print("Running in TEST mode (limit=2 per index)")
        
    dates_list = None
    if args.dates:
        dates_list = [datetime.strptime(d.strip(), "%Y-%m-%d").date() for d in args.dates.split(",") if d.strip()]
        
    run_backtest(limit=limit_val, backtest_dates=dates_list)
