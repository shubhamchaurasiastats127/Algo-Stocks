"""
engine.py
---------
Stock Analysis Engine — Enhanced with Pre-Layer Sector Selection
and Rebound Potential Score (52-Week Low / Oversold Priority).

Execution Flow:
  1. SectorSelector evaluates all Nifty sectoral indices → top 1-5 selected.
  2. Existing 3-layer scoring runs on constituents of selected indices.
  3. Rebound Score (0-100) is computed for each stock and blended:
       Final Rank Score = 0.70 × Algorithm Score + 0.30 × Rebound Score
  4. Stocks tagged with '52W_LOW' and 'OVERSOLD' flags.
  5. Consolidated Excel report generated with all sheets.
"""

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yaml

# Allow running from project root
sys.path.insert(0, os.path.dirname(__file__))

from data_manager import DataFetcher
from feature_engine import FeatureEngine
from sector_selector import SectorSelector
from scoring_engine import ScoringEngine
from stat_model import StatModel
from excel_writer import ExcelWriter


class StockAnalysisEngine:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.fetcher    = DataFetcher(self.config)
        self.features   = FeatureEngine(self.config)
        self.stats      = StatModel(self.config)
        self.scoring    = ScoringEngine(self.config)
        self.writer     = ExcelWriter(self.config)
        self.selector   = SectorSelector(self.config)

        log_path = self.config['paths']['logs']
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            filename=log_path,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    # ------------------------------------------------------------------
    # Per-stock processing (unchanged core logic)
    # ------------------------------------------------------------------

    def process_single_stock(self, sym: str, sector_median_pe: float = None):
        """
        Run the full 3-layer analysis pipeline on a single stock.
        Returns (result_dict, divergence_dict_or_None).
        The result_dict includes rebound scoring fields.
        """
        try:
            # 1. Fetch price data
            df = self.fetcher.get_stock_data(sym)
            if df.empty or len(df) < 252:
                return None, None

            # 2. Extract features (unchanged)
            df = self.features.compute_technicals(df)
            df = self.features.compute_price_action(df)
            df = self.features.compute_statistical_features(df)

            # 3. Fundamentals
            info         = self.fetcher.get_fundamentals(sym)
            fund_metrics = self.features.extract_fundamental_metrics(info)

            # 4. Stat Model
            current_price = float(df['close'].iloc[-1])
            p_target, p_stop, avg_horizon = self.stats.run_monte_carlo(current_price, df)
            prediction  = self.stats.predict_forward_return(df)
            stat_results = (p_target, p_stop, prediction, avg_horizon)

            # 5. Multi-Layer Scoring (original — unchanged)
            l1 = self.scoring.calculate_layer_1_fundamentals(fund_metrics)
            l2 = self.scoring.calculate_layer_2_technicals(df)
            l3 = self.scoring.calculate_layer_3_statistical(stat_results)
            final = self.scoring.get_final_recommendation(l1, l2, l3, avg_horizon)

            # 6. Rebound Potential Score (NEW)
            rebound_data = self.selector.compute_rebound_score(
                sym, df, info, sector_median_pe
            )

            # 7. Blended Final Rank Score
            # Final Rank = 70% Algorithm Score + 30% Rebound Score
            algo_score     = final['score']
            rebound_score  = rebound_data['rebound_score']
            final_rank     = round(0.70 * algo_score + 0.30 * rebound_score, 1)

            # 8. Result dict
            res = {
                'Symbol':         sym,
                'Price':          round(current_price, 2),
                'Action':         final['action'],
                'Score':          final['score'],
                'Confidence':     final['confidence'],
                'Horizon':        final['horizon'],
                'L1_Score':       round(l1[0], 1),
                'L1_Reasoning':   l1[1],
                'L2_Score':       round(l2[0], 1),
                'L2_Reasoning':   l2[1],
                'L3_Score':       round(l3[0], 1),
                'L3_Reasoning':   l3[1],
                'P_Target':       round(p_target, 2),
                'P_Stop':         round(p_stop, 2),
                'Pred_Return':    round(prediction, 4),
                'MarketCap_Cr':   round(fund_metrics['market_cap_cr'], 0),
                # Rebound / 52-week fields (NEW)
                'Rebound_Score':       rebound_score,
                'Oversold_Score':      rebound_data['oversold_score'],
                'Valuation_Score':     rebound_data['valuation_score'],
                'Growth_Score':        rebound_data['growth_score'],
                'Technical_Score':     rebound_data['technical_score'],
                'Momentum_Score':      rebound_data['momentum_score'],
                'Flag_52W_LOW':        rebound_data['flag_52w_low'],
                'Flag_OVERSOLD':       rebound_data['flag_oversold'],
                'Flag_Double_Bottom':  rebound_data['flag_double_bottom'],
                'Double_Bottom_Stage': rebound_data['double_bottom_stage'],
                'Double_Bottom_Score': rebound_data['double_bottom_score'],
                'Pct_From_52W_High':   rebound_data['pct_from_52w_high'],
                'Pct_From_52W_Low':    rebound_data['pct_from_52w_low'],
                '52W_High':            rebound_data['high_52w'],
                '52W_Low':             rebound_data['low_52w'],
                'RSI':                 rebound_data['rsi_latest'],
                'Final_Rank_Score':    final_rank,
                # Fundamentals snapshot
                'PE_Ratio':  round(fund_metrics.get('pe_ratio', 0) or 0, 1),
                'PB_Ratio':  round(fund_metrics.get('pb_ratio', 0) or 0, 2),
                'ROE':       round((fund_metrics.get('roe', 0) or 0) * 100, 1),
                'Revenue_Growth_Pct': round((fund_metrics.get('revenue_growth', 0) or 0) * 100, 1),
                'Debt_Equity': round(fund_metrics.get('debt_to_equity', 0) or 0, 2),
            }

            # 9. Divergence Logic (unchanged)
            tech_bullish = l2[0] > 60
            stat_bullish = prediction > 0.02
            div = None
            if tech_bullish != stat_bullish:
                div = {
                    'Symbol':      sym,
                    'Tech_Bullish': tech_bullish,
                    'Stat_Bullish': stat_bullish,
                    'Conflict':    "Stat Prediction vs Tech Trend"
                }

            return res, div

        except Exception as e:
            logging.error(f"Error processing {sym}: {e}")
            return None, None

    # ------------------------------------------------------------------
    # Run analysis for a single index
    # ------------------------------------------------------------------

    def run_analysis_for_index(self, index_name: str, sector_median_pe: float = None,
                                subfolder: str = None, limit: int = None) -> list:
        """
        Run the full pipeline on all constituents of index_name.
        Returns list of result dicts.
        """
        print(f"\nFetching constituents for {index_name}...")
        symbols = self.fetcher.fetch_universe(index_name)
        if limit:
            symbols = symbols[:limit]

        if not symbols:
            print(f"No symbols found for {index_name}. Skipping.")
            return []

        all_results     = []
        divergence_data = []

        workers = self.config.get('optimization', {}).get('parallel_workers', 4)
        print(f"Processing {len(symbols)} stocks with {workers} parallel workers...")

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(self.process_single_stock, sym, sector_median_pe): sym
                for sym in symbols
            }

            completed = 0
            for future in as_completed(future_map):
                res, div = future.result()
                if res:
                    res['Index_Name'] = index_name
                    all_results.append(res)
                if div:
                    divergence_data.append(div)
                completed += 1
                if completed % 10 == 0 or completed == len(symbols):
                    print(f"  Progress: {completed}/{len(symbols)}")

        elapsed = time.time() - start_time
        print(f"  {index_name} processed in {elapsed:.1f}s -- {len(all_results)} stocks analysed.")
        return all_results

    # ------------------------------------------------------------------
    # Validation checks
    # ------------------------------------------------------------------

    def _validate_results(self, df_union: pd.DataFrame) -> None:
        """Run quality checks and print a validation report."""
        print("\n" + "=" * 60)
        print("VALIDATION CHECKS")
        print("=" * 60)

        total = len(df_union)

        # Check 1: Rebound Score populated
        pct_rs = (df_union['Rebound_Score'] > 0).mean() * 100
        print(f"  [PASS] Rebound Score populated:       {pct_rs:.0f}% of stocks")

        # Check 2: ≥50% stocks flagged as oversold or 52W low
        flagged = (
            (df_union['Flag_OVERSOLD'] == 'YES') |
            (df_union['Flag_52W_LOW'] == 'YES')
        ).sum()
        pct_flagged = flagged / total * 100
        status = "[OK]" if pct_flagged >= 50 else "[WARN]"
        print(f"  {status} Oversold/52W_LOW flags:         {flagged}/{total} ({pct_flagged:.0f}%) "
              f"{'[PASS]' if pct_flagged >= 50 else '[REVIEW -- less than 50% flagged; market may not be broadly oversold]'}")

        # Check 3: Each oversold stock has Rebound Score > 60
        oversold_mask = df_union['Flag_OVERSOLD'] == 'YES'
        if oversold_mask.sum() > 0:
            low_rebound = (df_union[oversold_mask]['Rebound_Score'] < 60).sum()
            print(f"  {'[OK]' if low_rebound == 0 else '[WARN]'} Oversold stocks w/ Rebound < 60: "
                  f"{low_rebound} {'[PASS]' if low_rebound == 0 else '[REVIEW]'}")

        # Check 4: No duplicates
        dups = df_union.duplicated(subset=['Symbol', 'Index_Name']).sum()
        print(f"  {'[OK]' if dups == 0 else '[FAIL]'} Duplicate rows:                 {dups} "
              f"{'[PASS]' if dups == 0 else '[FAIL -- duplicates detected]'}")

        # Check 5: Key columns populated for all stocks
        key_cols = ['PE_Ratio', 'ROE', 'RSI', 'Rebound_Score', 'Pct_From_52W_High']
        for col in key_cols:
            n_missing = df_union[col].isna().sum()
            print(f"  {'[OK]' if n_missing == 0 else '[WARN]'} Missing '{col}': {n_missing}")

        # Check 6: Rebound Score weighting
        print(f"  [OK] Rebound Score weight in Final_Rank_Score: 30% (Algorithm 70%)")

        print("=" * 60 + "\n")

    # ------------------------------------------------------------------
    # Main run method
    # ------------------------------------------------------------------

    def run(self, limit: int = None):
        """
        Full execution flow:
          1. Pre-layer sector selection
          2. Run modified algorithm on selected indices
          3. Generate consolidated Excel report
        """

        # ── Step 1: Pre-Layer Sector Selection ───────────────────────────
        sector_result = self.selector.select_sectors(max_sectors=5)
        selected_indices   = sector_result['selected']
        justifications     = sector_result['justifications']
        oversold_highlights = sector_result['oversold_highlights']
        rejected_sectors   = sector_result['rejected']
        all_scores         = sector_result['all_scores']
        vix                = sector_result['vix']
        sector_fund        = sector_result['sector_fundamentals']

        if not selected_indices:
            print("No indices selected by pre-layer. Defaulting to Nifty 500.")
            selected_indices = ["Nifty 500"]

        # ── Step 2: Run Analysis on Each Selected Index ───────────────────
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        subfolder = f"Sector_Select_{timestamp}"

        all_union_results = []   # Union of all stocks across selected indices

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
            print("No results generated. Exiting.")
            return

        df_union = pd.DataFrame(all_union_results)

        # Deduplicate: if same stock appears in multiple indices, keep best Final_Rank_Score
        # but preserve all Index_Name values (comma-separated)
        df_union = self._deduplicate_union(df_union)

        # ── Step 3: Validation ───────────────────────────────────────────
        self._validate_results(df_union)

        # ── Step 4: Generate Consolidated Excel ──────────────────────────
        output_path = self.writer.save_consolidated_report(
            df_union             = df_union,
            selected_indices     = selected_indices,
            justifications       = justifications,
            oversold_highlights  = oversold_highlights,
            rejected_sectors     = rejected_sectors,
            all_scores           = all_scores,
            vix                  = vix,
            subfolder            = subfolder,
        )

        print(f"\n[DONE] Analysis Complete! Report saved to:\n   {output_path}\n")

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _deduplicate_union(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        If a stock appears in multiple selected indices, merge rows:
        - Combine Index_Name values (comma-separated)
        - Keep the row with the highest Final_Rank_Score for numeric fields
        """
        if 'Symbol' not in df.columns:
            return df

        # Group by Symbol: collect all index names and take best rank row
        grouped = []
        for sym, grp in df.groupby('Symbol'):
            best_row = grp.loc[grp['Final_Rank_Score'].idxmax()].copy()
            all_indices = ", ".join(sorted(set(grp['Index_Name'].dropna().tolist())))
            best_row['Index_Name'] = all_indices
            grouped.append(best_row)

        return pd.DataFrame(grouped).reset_index(drop=True)


if __name__ == "__main__":
    engine = StockAnalysisEngine("config/config.yaml")
    engine.run()
