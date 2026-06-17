# pyrefly: ignore [missing-import]
import os
import sys
import logging
from datetime import datetime, timedelta, date
# pyrefly: ignore [missing-import]
import pandas as pd
# pyrefly: ignore [missing-import]
import numpy as np
# pyrefly: ignore [missing-import]
import yaml
# pyrefly: ignore [missing-import]
import xlsxwriter

# Allow importing from src and backtest directories
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# pyrefly: ignore [missing-import]
from backtest_selector import BacktestSectorSelector
# pyrefly: ignore [missing-import]
from data_manager import DataFetcher

def safe_mean(lst):
    if not lst:
        return 0.0
    cleaned = [x for x in lst if x is not None and not (isinstance(x, float) and np.isnan(x))]
    if not cleaned:
        return 0.0
    return float(np.mean(cleaned))

def find_closest_date_price(price_dict: dict, target_date, direction: str = 'after'):
    """
    Find the price in price_dict closest to target_date.
    If direction == 'after', check target_date, then target_date + 1, + 2, ...
    If direction == 'before', check target_date, then target_date - 1, - 2, ...
    """
    curr = target_date
    for _ in range(15):  # Check up to 15 days ahead/behind
        if curr in price_dict:
            return price_dict[curr], curr
        if direction == 'after':
            curr += timedelta(days=1)
        else:
            curr -= timedelta(days=1)
    return None, None

def load_all_stock_prices(config: dict, symbols: list, start_date, end_date) -> dict:
    """Pre-load all closing prices for symbols in a single query to optimize performance."""
    if not symbols:
        return {}
    # pyrefly: ignore [missing-import]
    import mysql.connector
    conn = mysql.connector.connect(**config['mysql'])
    placeholders = ",".join(["%s"] * len(symbols))
    query = f"""
        SELECT symbol, date, close 
        FROM price_data 
        WHERE symbol IN ({placeholders}) AND date >= %s AND date <= %s
    """
    cursor = conn.cursor()
    cursor.execute(query, tuple(symbols) + (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    data = {}
    for sym, dt, close in rows:
        d = dt if isinstance(dt, datetime) or type(dt) == datetime.date else pd.to_datetime(dt).date()
        if hasattr(d, 'date'):
            d = d.date()
        if sym not in data:
            data[sym] = {}
        data[sym][d] = float(close)
    return data

def get_monthly_dates(start_date, today_date) -> list:
    """Generate same-day-of-month dates at monthly intervals from start_date to today_date."""
    dates = []
    curr = start_date
    while True:
        month = curr.month + 1
        year = curr.year
        if month > 12:
            month = 1
            year += 1
        day = min(start_date.day, 28)  # Safe day mapping (using 7th is always safe)
        next_curr = datetime(year, month, day).date()
        if next_curr > today_date:
            break
        dates.append(next_curr)
        curr = next_curr
    if not dates or dates[-1] < today_date:
        # If today_date is not in the list, append it as the final checkpoint
        if dates and (today_date - dates[-1]).days < 10:
            pass  # Avoid duplicated final month if very close
        else:
            dates.append(today_date)
    return dates

def run_performance_tracker(backtest_dates=None, entry_threshold=70.0, top_n_picks=10, today_date=None):
    config_path = os.path.join(os.path.dirname(__file__), '../config/config.yaml')
    with open(config_path) as f:
        config = yaml.safe_load(f)
        
    print("Ensuring Nifty 50 constituents are populated in database...")
    fetcher = DataFetcher(config)
    fetcher.fetch_universe("Nifty 50")
    print("Ensuring Nifty 500 constituents are populated in database...")
    fetcher.fetch_universe("Nifty 500")
        
    if backtest_dates is None:
        backtest_dates = [
            datetime(2025, 12, 7).date(),
            datetime(2026, 1, 7).date(),
            datetime(2026, 2, 7).date(),
            datetime(2026, 3, 7).date(),
            datetime(2026, 4, 7).date(),
            datetime(2026, 5, 7).date(),
        ]
    
    if today_date is None:
        today_date = datetime(2026, 6, 7).date()  # June 7, 2026 (local today)
    
    print("=" * 65)
    print("RUNNING PERFORMANCE TRACKER")
    print("=" * 65)
    
    # ── Step 1: Pre-load Nifty 50 and Nifty 500 reconstructed index series ──
    print("Reconstructing benchmark index series...")
    nifty50_prices = {}
    nifty500_prices = {}
    
    try:
        # Build selector to reconstruct indexes over the whole backtest window (May 2025 - June 2026)
        selector = BacktestSectorSelector(config, today_date)
        n50_series = selector._reconstruct_index("Nifty 50", days=400)
        if not n50_series.empty:
            nifty50_prices = {d.date(): float(v) for d, v in n50_series.items()}
            
        n500_series = selector._reconstruct_index("Nifty 500", days=400)
        if not n500_series.empty:
            nifty500_prices = {d.date(): float(v) for d, v in n500_series.items()}
            
        print("  Reconstruction complete.")
    except Exception as e:
        print(f"  [ERROR] Index reconstruction failed: {e}")
        
    # ── Step 2: Read picks and pre-load all stock prices ──
    all_picks = {}
    all_symbols = set()
    
    for r_date in backtest_dates:
        date_str = r_date.strftime('%Y%m%d')
        picks_path = os.path.join(config['paths']['output_folder'], f"backtest/run_{date_str}/picks.csv")
        
        if not os.path.exists(picks_path):
            print(f"  [WARN] Picks file not found for {r_date}: {picks_path}")
            continue
            
        df = pd.read_csv(picks_path)
        # Filter for "Top Rebound Picks" sheet criteria: Rebound_Score >= entry_threshold or Flag_OVERSOLD == YES
        df_picks = df[(df['Rebound_Score'] >= entry_threshold) | (df['Flag_OVERSOLD'] == 'YES')].copy()
        if df_picks.empty:
            # Fallback to top_n_picks * 2 by Rebound_Score if empty
            df_picks = df.sort_values('Rebound_Score', ascending=False).head(top_n_picks * 2).copy()
            
        all_picks[r_date] = df_picks
        all_symbols.update(df_picks['Symbol'].tolist())
        
    print(f"Loaded picks for {len(all_picks)} dates. Found {len(all_symbols)} unique symbols.")
    
    # Pre-load stock prices
    print("Pre-loading historical stock prices from DB...")
    stock_prices = load_all_stock_prices(config, list(all_symbols), datetime(2025, 11, 20).date(), today_date)
    print("  Prices loaded.")

    # ── Step 3: Compute forward returns ──
    backtest_results = {}
    
    for r_date in backtest_dates:
        if r_date not in all_picks:
            continue
            
        df_picks = all_picks[r_date]
        m_dates = get_monthly_dates(r_date, today_date)
        
        # We track two portfolios: Full Rebound Picks and Top N Rebound Picks by Final_Rank_Score
        df_top10 = df_picks.sort_values('Final_Rank_Score', ascending=False).head(top_n_picks)
        
        portfolio_results = []
        
        for idx, row in df_picks.iterrows():
            sym = row['Symbol']
            sym_prices = stock_prices.get(sym, {})
            
            # Entry Price (closest trading day on or before run_date)
            entry_price, entry_dt = find_closest_date_price(sym_prices, r_date, direction='before')
            if not entry_price:
                continue
                
            stock_data = {
                'Symbol': sym,
                'Sector': row['Index_Name'],
                'Rebound_Score': row['Rebound_Score'],
                'Final_Rank_Score': row['Final_Rank_Score'],
                'Double_Bottom_Stage': row.get('Double_Bottom_Stage', 'None'),
                'L1_Explanation': row.get('L1_Reasoning') or row.get('L1 Reasoning') or 'Stable Fundamentals',
                'L2_Explanation': row.get('L2_Reasoning') or row.get('L2 Reasoning') or 'Constructive Technical Setup',
                'L3_Explanation': row.get('L3_Reasoning') or row.get('L3 Reasoning') or 'Monte Carlo target verified',
                'Entry_Date': entry_dt,
                'Entry_Price': entry_price,
                'In_Top10': sym in df_top10['Symbol'].tolist(),
                'Prices': {},
                'Returns': {}
            }
            
            # Get prices and returns at monthly checkpoints
            for m_idx, m_dt in enumerate(m_dates, 1):
                direction = 'before' if m_dt == today_date else 'after'
                p, dt = find_closest_date_price(sym_prices, m_dt, direction=direction)
                stock_data['Prices'][f'M{m_idx}'] = p
                stock_data['Prices'][f'M{m_idx}_Date'] = dt
                
                if p and entry_price:
                    ret = (p - entry_price) / entry_price
                    stock_data['Returns'][f'M{m_idx}'] = ret
                else:
                    stock_data['Returns'][f'M{m_idx}'] = None
                    
            portfolio_results.append(stock_data)
            
        # Benchmark returns (Nifty 50 and Nifty 500)
        benchmarks = {
            'Nifty 50': {'entry_price': None, 'prices': {}, 'returns': {}},
            'Nifty 500': {'entry_price': None, 'prices': {}, 'returns': {}}
        }
        
        n50_entry, _ = find_closest_date_price(nifty50_prices, r_date, direction='before')
        n500_entry, _ = find_closest_date_price(nifty500_prices, r_date, direction='before')
        
        benchmarks['Nifty 50']['entry_price'] = n50_entry
        benchmarks['Nifty 500']['entry_price'] = n500_entry
        
        for m_idx, m_dt in enumerate(m_dates, 1):
            direction = 'before' if m_dt == today_date else 'after'
            n50_p, _ = find_closest_date_price(nifty50_prices, m_dt, direction=direction)
            benchmarks['Nifty 50']['prices'][f'M{m_idx}'] = n50_p
            if n50_p and n50_entry:
                benchmarks['Nifty 50']['returns'][f'M{m_idx}'] = (n50_p - n50_entry) / n50_entry
            else:
                benchmarks['Nifty 50']['returns'][f'M{m_idx}'] = None
                
            n500_p, _ = find_closest_date_price(nifty500_prices, m_dt, direction=direction)
            benchmarks['Nifty 500']['prices'][f'M{m_idx}'] = n500_p
            if n500_p and n500_entry:
                benchmarks['Nifty 500']['returns'][f'M{m_idx}'] = (n500_p - n500_entry) / n500_entry
            else:
                benchmarks['Nifty 500']['returns'][f'M{m_idx}'] = None
                
        backtest_results[r_date] = {
            'stocks': portfolio_results,
            'benchmarks': benchmarks,
            'dates': m_dates
        }
        print(f"  Calculated performance for run date {r_date} ({len(portfolio_results)} stock picks).")

    # ── Step 4: Write Master Excel Report ──
    master_report_path = os.path.join(config['paths']['output_folder'], "backtest/Backtest_Performance_Summary.xlsx")
    os.makedirs(os.path.dirname(master_report_path), exist_ok=True)
    
    print(f"Writing master Excel report to {master_report_path}...")
    wb = xlsxwriter.Workbook(master_report_path)
    
    # Formats
    fmt_title = wb.add_format({'bold': True, 'font_size': 16, 'font_color': '#FFFFFF', 'bg_color': '#1F3864', 'align': 'center', 'valign': 'vcenter'})
    fmt_subtitle = wb.add_format({'font_size': 10, 'font_color': '#595959', 'italic': True})
    fmt_header = wb.add_format({'bold': True, 'font_size': 10, 'font_color': '#FFFFFF', 'bg_color': '#1F4E78', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
    fmt_header_green = wb.add_format({'bold': True, 'font_size': 10, 'font_color': '#FFFFFF', 'bg_color': '#2E75B6', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
    fmt_body = wb.add_format({'font_size': 10, 'border': 1, 'valign': 'vcenter'})
    fmt_body_center = wb.add_format({'font_size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
    fmt_body_num = wb.add_format({'font_size': 10, 'border': 1, 'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter'})
    fmt_body_pct = wb.add_format({'font_size': 10, 'border': 1, 'num_format': '0.0%', 'align': 'right', 'valign': 'vcenter'})
    fmt_body_pct_bold = wb.add_format({'font_size': 10, 'border': 1, 'bold': True, 'num_format': '0.0%', 'align': 'right', 'valign': 'vcenter'})
    fmt_bold_label = wb.add_format({'bold': True, 'font_size': 10, 'border': 1, 'valign': 'vcenter', 'bg_color': '#F2F2F2'})
    fmt_bold_num_pct = wb.add_format({'bold': True, 'font_size': 10, 'border': 1, 'num_format': '0.0%', 'align': 'right', 'valign': 'vcenter', 'bg_color': '#F2F2F2'})
    fmt_outperf_pos = wb.add_format({'bold': True, 'font_size': 10, 'border': 1, 'font_color': '#375623', 'bg_color': '#E2EFDA', 'num_format': '+0.0%', 'align': 'right', 'valign': 'vcenter'})
    fmt_outperf_neg = wb.add_format({'bold': True, 'font_size': 10, 'border': 1, 'font_color': '#C00000', 'bg_color': '#FCE4D6', 'num_format': '0.0%', 'align': 'right', 'valign': 'vcenter'})

    # ── Sheet 1: Dashboard ──
    ws_db = wb.add_worksheet("Dashboard")
    ws_db.set_column('A:A', 15)
    ws_db.set_column('B:B', 38)
    ws_db.set_column('C:C', 10)
    ws_db.set_column('D:I', 12)
    ws_db.set_column('J:K', 14)
    ws_db.set_column('L:M', 15)
    
    ws_db.merge_range('A1:M2', "ALGORITHM BACKTESTING & PERFORMANCE DASHBOARD", fmt_title)
    ws_db.write('A4', "Generated:", fmt_subtitle)
    ws_db.write('B4', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), fmt_subtitle)
    
    ws_db.write('A6', ">> REBOUND PORTFOLIO PERFORMANCE SUMMARY (ALL SELECTIONS)", wb.add_format({'bold': True, 'font_size': 12, 'font_color': '#1F3864'}))
    
    headers = [
        "Run Date", "Selected Sectors", "Picks Count", 
        "Month 1", "Month 2", "Month 3", "Month 4", "Month 5", "Month 6 / Today",
        "Nifty 50", "Nifty 500", "Outperform vs N50", "Outperform vs N500"
    ]
    
    row_num = 7
    for col_idx, h in enumerate(headers):
        ws_db.write(row_num, col_idx, h, fmt_header)
        
    row_num += 1
    
    # Store rows for calculating averages later
    dashboard_rows = []
    
    for r_date in backtest_dates:
        if r_date not in backtest_results:
            continue
            
        res = backtest_results[r_date]
        stocks = res['stocks']
        benchmarks = res['benchmarks']
        m_dates = res['dates']
        
        # Get selected sectors names
        sectors = sorted(list(set([s['Sector'] for s in stocks])))
        sectors_str = ", ".join(sectors)
        
        # Calc average returns at each month end
        avg_rets = []
        for m_idx in range(1, 7):
            m_key = f'M{m_idx}'
            rets = [s['Returns'].get(m_key) for s in stocks if s['Returns'].get(m_key) is not None]
            avg_rets.append(safe_mean(rets) if rets else None)
            
        n50_final = benchmarks['Nifty 50']['returns'][f'M{len(m_dates)}']
        n500_final = benchmarks['Nifty 500']['returns'][f'M{len(m_dates)}']
        portfolio_final = avg_rets[len(m_dates) - 1]
        
        # Write to Dashboard
        ws_db.write(row_num, 0, r_date.strftime('%Y-%m-%d'), fmt_body_center)
        ws_db.write(row_num, 1, sectors_str, fmt_body)
        ws_db.write(row_num, 2, len(stocks), fmt_body_center)
        
        # Month 1 - Month 6
        for m_idx in range(6):
            val = avg_rets[m_idx]
            if val is not None:
                ws_db.write(row_num, 3 + m_idx, val, fmt_body_pct)
            else:
                ws_db.write(row_num, 3 + m_idx, "—", fmt_body_center)
                
        # Nifty 50 & Nifty 500 final
        ws_db.write(row_num, 9, n50_final if n50_final is not None else "—", fmt_body_pct)
        ws_db.write(row_num, 10, n500_final if n500_final is not None else "—", fmt_body_pct)
        
        # Outperformance
        if portfolio_final is not None and n50_final is not None:
            diff_50 = portfolio_final - n50_final
            fmt = fmt_outperf_pos if diff_50 >= 0 else fmt_outperf_neg
            ws_db.write(row_num, 11, diff_50, fmt)
        else:
            ws_db.write(row_num, 11, "—", fmt_body_center)
            
        if portfolio_final is not None and n500_final is not None:
            diff_500 = portfolio_final - n500_final
            fmt = fmt_outperf_pos if diff_500 >= 0 else fmt_outperf_neg
            ws_db.write(row_num, 12, diff_500, fmt)
        else:
            ws_db.write(row_num, 12, "—", fmt_body_center)
            
        dashboard_rows.append({
            'picks_count': len(stocks),
            'm_rets': avg_rets,
            'n50': n50_final,
            'n500': n500_final
        })
        row_num += 1
        
    # Write average row
    ws_db.write(row_num, 0, "Average", fmt_bold_label)
    ws_db.write(row_num, 1, "All Simulation Runs", fmt_bold_label)
    
    total_picks = sum([x['picks_count'] for x in dashboard_rows])
    ws_db.write(row_num, 2, total_picks / len(dashboard_rows) if dashboard_rows else 0, fmt_bold_label)
    
    for m_idx in range(6):
        vals = [x['m_rets'][m_idx] for x in dashboard_rows if x['m_rets'][m_idx] is not None]
        mean_val = safe_mean(vals) if vals else 0
        ws_db.write(row_num, 3 + m_idx, mean_val, fmt_bold_num_pct)
        
    n50_avg = safe_mean([x['n50'] for x in dashboard_rows if x['n50'] is not None])
    n500_avg = safe_mean([x['n500'] for x in dashboard_rows if x['n500'] is not None])
    ws_db.write(row_num, 9, n50_avg, fmt_bold_num_pct)
    ws_db.write(row_num, 10, n500_avg, fmt_bold_num_pct)
    
    # Average Outperformance
    avg_portfolio_final = safe_mean([x['m_rets'][len(get_monthly_dates(d, today_date)) - 1] for d, x in zip(backtest_dates, dashboard_rows)])
    diff_n50_avg = avg_portfolio_final - n50_avg
    ws_db.write(row_num, 11, diff_n50_avg, fmt_outperf_pos if diff_n50_avg >= 0 else fmt_outperf_neg)
    
    diff_n500_avg = avg_portfolio_final - n500_avg
    ws_db.write(row_num, 12, diff_n500_avg, fmt_outperf_pos if diff_n500_avg >= 0 else fmt_outperf_neg)

    # ── Section: Concentration Portfolio Dashboard (Top N Picks only) ──
    row_num += 3
    ws_db.write(row_num, 0, f">> CONCENTRATED PORTFOLIO PERFORMANCE SUMMARY (TOP {top_n_picks} PICKS)", wb.add_format({'bold': True, 'font_size': 12, 'font_color': '#1E6B3C'}))
    row_num += 1
    
    for col_idx, h in enumerate(headers):
        ws_db.write(row_num, col_idx, h, wb.add_format({'bold': True, 'font_size': 10, 'font_color': '#FFFFFF', 'bg_color': '#1E6B3C', 'border': 1, 'align': 'center', 'valign': 'vcenter'}))
    row_num += 1
    
    dashboard_top10_rows = []
    
    for r_date in backtest_dates:
        if r_date not in backtest_results:
            continue
            
        res = backtest_results[r_date]
        stocks = [s for s in res['stocks'] if s['In_Top10']]
        benchmarks = res['benchmarks']
        m_dates = res['dates']
        
        sectors = sorted(list(set([s['Sector'] for s in stocks])))
        sectors_str = ", ".join(sectors)
        
        avg_rets = []
        for m_idx in range(1, 7):
            m_key = f'M{m_idx}'
            rets = [s['Returns'].get(m_key) for s in stocks if s['Returns'].get(m_key) is not None]
            avg_rets.append(np.mean(rets) if rets else None)
            
        n50_final = benchmarks['Nifty 50']['returns'][f'M{len(m_dates)}']
        n500_final = benchmarks['Nifty 500']['returns'][f'M{len(m_dates)}']
        portfolio_final = avg_rets[len(m_dates) - 1]
        
        ws_db.write(row_num, 0, r_date.strftime('%Y-%m-%d'), fmt_body_center)
        ws_db.write(row_num, 1, sectors_str, fmt_body)
        ws_db.write(row_num, 2, len(stocks), fmt_body_center)
        
        for m_idx in range(6):
            val = avg_rets[m_idx]
            if val is not None:
                ws_db.write(row_num, 3 + m_idx, val, fmt_body_pct)
            else:
                ws_db.write(row_num, 3 + m_idx, "—", fmt_body_center)
                
        ws_db.write(row_num, 9, n50_final if n50_final is not None else "—", fmt_body_pct)
        ws_db.write(row_num, 10, n500_final if n500_final is not None else "—", fmt_body_pct)
        
        if portfolio_final is not None and n50_final is not None:
            diff_50 = portfolio_final - n50_final
            fmt = fmt_outperf_pos if diff_50 >= 0 else fmt_outperf_neg
            ws_db.write(row_num, 11, diff_50, fmt)
        else:
            ws_db.write(row_num, 11, "—", fmt_body_center)
            
        if portfolio_final is not None and n500_final is not None:
            diff_500 = portfolio_final - n500_final
            fmt = fmt_outperf_pos if diff_500 >= 0 else fmt_outperf_neg
            ws_db.write(row_num, 12, diff_500, fmt)
        else:
            ws_db.write(row_num, 12, "—", fmt_body_center)
            
        dashboard_top10_rows.append({
            'picks_count': len(stocks),
            'm_rets': avg_rets,
            'n50': n50_final,
            'n500': n500_final
        })
        row_num += 1
        
    # Write average row for top 10
    ws_db.write(row_num, 0, "Average", fmt_bold_label)
    ws_db.write(row_num, 1, f"Concentrated Portfolio (Top {top_n_picks} Picks)", fmt_bold_label)
    ws_db.write(row_num, 2, top_n_picks, fmt_bold_label)
    
    for m_idx in range(6):
        vals = [x['m_rets'][m_idx] for x in dashboard_top10_rows if x['m_rets'][m_idx] is not None]
        mean_val = safe_mean(vals) if vals else 0
        ws_db.write(row_num, 3 + m_idx, mean_val, fmt_bold_num_pct)
        
    n50_avg_10 = safe_mean([x['n50'] for x in dashboard_top10_rows if x['n50'] is not None])
    n500_avg_10 = safe_mean([x['n500'] for x in dashboard_top10_rows if x['n500'] is not None])
    ws_db.write(row_num, 9, n50_avg_10, fmt_bold_num_pct)
    ws_db.write(row_num, 10, n500_avg_10, fmt_bold_num_pct)
    
    avg_top10_portfolio_final = safe_mean([x['m_rets'][len(get_monthly_dates(d, today_date)) - 1] for d, x in zip(backtest_dates, dashboard_top10_rows)])
    diff_n50_avg_10 = avg_top10_portfolio_final - n50_avg_10
    ws_db.write(row_num, 11, diff_n50_avg_10, fmt_outperf_pos if diff_n50_avg_10 >= 0 else fmt_outperf_neg)
    
    diff_n500_avg_10 = avg_top10_portfolio_final - n500_avg_10
    ws_db.write(row_num, 12, diff_n500_avg_10, fmt_outperf_pos if diff_n500_avg_10 >= 0 else fmt_outperf_neg)

    # ── Sheets 2-7: Individual Date Backtests ──
    for r_date in backtest_dates:
        if r_date not in backtest_results:
            continue
            
        res = backtest_results[r_date]
        stocks = res['stocks']
        benchmarks = res['benchmarks']
        m_dates = res['dates']
        
        sheet_name = r_date.strftime('%Y-%m-%d')
        ws = wb.add_worksheet(sheet_name)
        
        ws.set_column('A:A', 10)  # Symbol
        ws.set_column('B:B', 22)  # Sector
        ws.set_column('C:C', 10)  # Rebound
        ws.set_column('D:D', 10)  # Rank Score
        ws.set_column('E:E', 12)  # Buy Date
        ws.set_column('F:F', 12)  # Buy Price
        ws.set_column('G:G', 16)  # Double Bottom Stage
        
        # Format month cols dynamically
        for m_idx in range(len(m_dates)):
            offset = 7 + (m_idx * 3)
            ws.set_column(offset, offset, 11)      # Date
            ws.set_column(offset + 1, offset + 1, 10)  # Price
            ws.set_column(offset + 2, offset + 2, 10)  # Return
            
        ws.merge_range(0, 0, 0, 6 + len(m_dates) * 3, f"BACKTEST PERFORMANCE FOR PORTFOLIO INITIATED ON {r_date.strftime('%B %d, %Y')}", fmt_title)
        
        # Table headers
        dt_hdrs = ["Symbol", "Sector", "Rebound\nScore", "Rank\nScore", "Entry Date", "Entry Price", "Double Bottom\nStage"]
        for col_idx, h in enumerate(dt_hdrs):
            ws.write(2, col_idx, h, fmt_header)
            
        for m_idx, m_dt in enumerate(m_dates, 1):
            offset = 7 + (m_idx - 1) * 3
            ws.write(2, offset, f"Month {m_idx}\nDate", fmt_header)
            ws.write(2, offset + 1, f"Month {m_idx}\nPrice", fmt_header)
            ws.write(2, offset + 2, f"Month {m_idx}\nReturn", fmt_header_green)
            
        r_num = 3
        
        # Sort stocks so top 10 (concentrated ones) appear first and are highlighted/identified
        stocks_sorted = sorted(stocks, key=lambda x: x['Final_Rank_Score'], reverse=True)
        
        for s in stocks_sorted:
            # Check if Concentrated Portfolio (Top 10)
            row_fmt = wb.add_format({'font_size': 10, 'border': 1, 'bg_color': '#FCF8E3'}) if s['In_Top10'] else fmt_body
            row_fmt_num = wb.add_format({'font_size': 10, 'border': 1, 'num_format': '#,##0.00', 'align': 'right', 'bg_color': '#FCF8E3'}) if s['In_Top10'] else fmt_body_num
            row_fmt_pct = wb.add_format({'font_size': 10, 'border': 1, 'num_format': '0.0%', 'align': 'right', 'bg_color': '#FCF8E3'}) if s['In_Top10'] else fmt_body_pct
            
            # Sanitise fields to avoid xlsxwriter TypeError on NaN/null values
            sym_val = str(s['Symbol']) if pd.notna(s['Symbol']) else '—'
            sector_val = str(s['Sector']) if pd.notna(s['Sector']) else '—'
            rebound_val = float(s['Rebound_Score']) if pd.notna(s['Rebound_Score']) else 0.0
            rank_val = float(s['Final_Rank_Score']) if pd.notna(s['Final_Rank_Score']) else 0.0
            entry_date_val = s['Entry_Date'].strftime('%Y-%m-%d') if (s['Entry_Date'] and pd.notna(s['Entry_Date'])) else '—'
            entry_price_val = float(s['Entry_Price']) if pd.notna(s['Entry_Price']) else 0.0
            
            db_stage_val = s.get('Double_Bottom_Stage', 'None')
            if pd.isna(db_stage_val) or not db_stage_val:
                db_stage_val = 'None'
            db_stage_val = str(db_stage_val)
            
            ws.write(r_num, 0, sym_val, wb.add_format({'font_size': 10, 'border': 1, 'bold': s['In_Top10'], 'align': 'center', 'bg_color': '#FCF8E3' if s['In_Top10'] else '#FFFFFF'}))
            ws.write(r_num, 1, sector_val, row_fmt)
            ws.write(r_num, 2, rebound_val, row_fmt_num)
            ws.write(r_num, 3, rank_val, row_fmt_num)
            ws.write(r_num, 4, entry_date_val, row_fmt)
            ws.write(r_num, 5, entry_price_val, row_fmt_num)
            ws.write(r_num, 6, db_stage_val, row_fmt)
            
            for m_idx in range(1, len(m_dates) + 1):
                offset = 7 + (m_idx - 1) * 3
                m_key = f'M{m_idx}'
                
                m_dt_val = s['Prices'].get(f'{m_key}_Date')
                m_pr_val = s['Prices'].get(m_key)
                m_rt_val = s['Returns'].get(m_key)
                
                ws.write(r_num, offset, m_dt_val.strftime('%Y-%m-%d') if m_dt_val else '—', row_fmt)
                ws.write(r_num, offset + 1, m_pr_val if m_pr_val is not None else '—', row_fmt_num)
                ws.write(r_num, offset + 2, m_rt_val if m_rt_val is not None else '—', row_fmt_pct)
                
            r_num += 1
            
        # Write average performance summaries below table
        r_num += 1
        
        # Row for full portfolio average
        ws.write(r_num, 1, "Full Portfolio Average (All Selections)", fmt_bold_label)
        ws.write(r_num, 2, len(stocks_sorted), fmt_bold_label)
        for m_idx in range(1, len(m_dates) + 1):
            offset = 7 + (m_idx - 1) * 3
            m_key = f'M{m_idx}'
            rets = [s['Returns'].get(m_key) for s in stocks_sorted if s['Returns'].get(m_key) is not None]
            avg_val = safe_mean(rets) if rets else 0
            ws.write(r_num, offset + 2, avg_val, fmt_bold_num_pct)
            
        r_num += 1
        
        # Row for top 10 concentrated average
        ws.write(r_num, 1, f"Concentrated Portfolio Average (Top {top_n_picks} Picks)", wb.add_format({'bold': True, 'font_size': 10, 'border': 1, 'valign': 'vcenter', 'bg_color': '#FCF8E3'}))
        ws.write(r_num, 2, len([s for s in stocks_sorted if s['In_Top10']]), wb.add_format({'bold': True, 'font_size': 10, 'border': 1, 'valign': 'vcenter', 'bg_color': '#FCF8E3'}))
        for m_idx in range(1, len(m_dates) + 1):
            offset = 7 + (m_idx - 1) * 3
            m_key = f'M{m_idx}'
            rets = [s['Returns'].get(m_key) for s in stocks_sorted if s['In_Top10'] and s['Returns'].get(m_key) is not None]
            avg_val = safe_mean(rets) if rets else 0
            ws.write(r_num, offset + 2, avg_val, wb.add_format({'bold': True, 'font_size': 10, 'border': 1, 'num_format': '0.0%', 'align': 'right', 'valign': 'vcenter', 'bg_color': '#FCF8E3'}))
            
        r_num += 2
        
        # Write benchmark comparison rows
        for b_name in ['Nifty 50', 'Nifty 500']:
            b_data = benchmarks[b_name]
            ws.write(r_num, 1, f"Benchmark: {b_name} Index", fmt_bold_label)
            ws.write(r_num, 5, b_data['entry_price'] if b_data['entry_price'] is not None else '—', wb.add_format({'bold': True, 'border': 1, 'num_format': '#,##0.00', 'align': 'right', 'bg_color': '#F2F2F2'}))
            
            for m_idx in range(1, len(m_dates) + 1):
                offset = 7 + (m_idx - 1) * 3
                m_key = f'M{m_idx}'
                m_pr = b_data['prices'].get(m_key)
                m_rt = b_data['returns'].get(m_key)
                ws.write(r_num, offset + 1, m_pr if m_pr is not None else '—', wb.add_format({'border': 1, 'num_format': '#,##0.00', 'align': 'right', 'bg_color': '#F2F2F2'}))
                ws.write(r_num, offset + 2, m_rt if m_rt is not None else '—', fmt_bold_num_pct)
            r_num += 1
            
    wb.close()
    print(f"\n[DONE] Performance tracker complete! Master Report saved to:\n   {master_report_path}\n")
    
    # Save to JSON Cache
    try:
        import json
        cache_file = os.path.join(config['paths']['output_folder'], "backtest/latest_results_cache.json")
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        
        def sanitize_results(data):
            if isinstance(data, dict):
                return {str(k): sanitize_results(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [sanitize_results(x) for x in data]
            elif isinstance(data, (datetime, date)):
                return data.isoformat()
            elif isinstance(data, float) and (np.isnan(data) or np.isinf(data)):
                return None
            elif isinstance(data, np.integer):
                return int(data)
            elif isinstance(data, np.floating):
                return float(data)
            elif isinstance(data, np.ndarray):
                return sanitize_results(data.tolist())
            else:
                return data
                
        sanitized = sanitize_results(backtest_results)
        with open(cache_file, "w") as f:
            json.dump(sanitized, f, indent=4)
        print(f"Saved results cache to {cache_file}")
    except Exception as json_err:
        print(f"Failed to save results cache JSON: {json_err}")
        
    return backtest_results

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dates', type=str, help='Comma-separated YYYY-MM-DD dates')
    parser.add_argument('--entry-threshold', type=float, default=70.0)
    parser.add_argument('--top-n', type=int, default=10)
    parser.add_argument('--today-date', type=str, default=None)
    args = parser.parse_args()
    
    dates_list = None
    if args.dates:
        dates_list = [datetime.strptime(d.strip(), "%Y-%m-%d").date() for d in args.dates.split(",") if d.strip()]
        
    today_dt = None
    if args.today_date:
        today_dt = datetime.strptime(args.today_date.strip(), "%Y-%m-%d").date()
        
    run_performance_tracker(
        backtest_dates=dates_list,
        entry_threshold=args.entry_threshold,
        top_n_picks=args.top_n,
        today_date=today_dt
    )
