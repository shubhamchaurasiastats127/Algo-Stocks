import streamlit as st
import pandas as pd
import numpy as np
import yaml
import os
import sys
import subprocess
import time
import plotly.graph_objects as go
from datetime import datetime

# Set page configuration with a premium dark theme feel
st.set_page_config(
    page_title="Algo_Stocks | Simulation & Analysis Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium CSS for styling
st.markdown("""
<style>
    /* Background and global styles */
    .stApp {
        background: linear-gradient(135deg, #0e1117 0%, #161a24 100%);
        color: #e2e8f0;
        font-family: 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Headers styling */
    h1, h2, h3 {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    
    /* Card styling (Glassmorphism style) */
    .metric-card {
        background: rgba(30, 41, 59, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        margin-bottom: 20px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: rgba(99, 102, 241, 0.4);
    }
    
    /* Config form fields card */
    .config-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 15px;
    }
    
    /* Custom buttons */
    .stButton>button {
        background: linear-gradient(90deg, #4f46e5 0%, #6366f1 100%);
        color: white !important;
        border: none;
        padding: 10px 24px;
        font-weight: 600;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        background: linear-gradient(90deg, #4338ca 0%, #4f46e5 100%);
        box-shadow: 0 6px 16px rgba(79, 70, 229, 0.45);
        transform: translateY(-1px);
    }
    
    /* Success/Error containers override */
    .stAlert {
        border-radius: 8px !important;
        background-color: rgba(30, 41, 59, 0.7) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
    }
    
    /* Style metrics values */
    .metric-val {
        font-size: 2.2rem;
        font-weight: 700;
        line-height: 1;
        margin: 10px 0;
    }
    .metric-val-positive {
        color: #10b981; /* Green */
    }
    .metric-val-negative {
        color: #ef4444; /* Red */
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-sub {
        font-size: 0.8rem;
        color: #64748b;
    }
    
    /* Log console styling */
    .log-console {
        background-color: #05070c !important;
        border: 1px solid #1e293b !important;
        border-radius: 8px;
        font-family: 'Courier New', Courier, monospace;
        color: #38bdf8 !important;
        padding: 15px;
        max-height: 400px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Configuration Helpers
# ---------------------------------------------------------------------------

CONFIG_PATH = "config/config.yaml"

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def save_config(config_dict):
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(config_dict, f, default_flow_style=False)


# Load config into session state if not already loaded
if "config" not in st.session_state:
    st.session_state.config = load_config()

config = st.session_state.config


# ---------------------------------------------------------------------------
# Sidebar Configuration Panel
# ---------------------------------------------------------------------------

st.sidebar.image("https://img.icons8.com/nolan/96/combo-chart.png", width=60)
st.sidebar.title("Configuration Engine")
st.sidebar.markdown("Modify execution parameters dynamically. Saving changes will overwrite `config/config.yaml`.")

# Initialize dynamic configurations input in Sidebar
with st.sidebar.expander("⚖️ Factor weights", expanded=True):
    w_fund = st.slider("Fundamentals Weight", 0.0, 1.0, float(config['weights']['fundamentals']), 0.05)
    w_val = st.slider("Valuation Weight", 0.0, 1.0, float(config['weights']['valuation']), 0.05)
    w_tech = st.slider("Technical Trend Weight", 0.0, 1.0, float(config['weights']['technical_trend']), 0.05)
    w_pa = st.slider("Price Action Weight", 0.0, 1.0, float(config['weights']['price_action']), 0.05)
    w_stat = st.slider("Statistical Edge Weight", 0.0, 1.0, float(config['weights']['stat_edge']), 0.05)
    w_risk = st.slider("Risk Regime Weight", 0.0, 1.0, float(config['weights']['risk_regime']), 0.05)
    
    total_weight = w_fund + w_val + w_tech + w_pa + w_stat + w_risk
    if abs(total_weight - 1.0) > 0.001:
        st.warning(f"Total weights must equal 1.00 (Current: {total_weight:.2f})")
    else:
        st.success("Weights normalized (Sum: 1.00)")

with st.sidebar.expander("🛑 Decision Thresholds", expanded=False):
    t_buy = st.number_input("Buy Score Threshold", 0, 100, int(config['thresholds']['buy']))
    t_wait = st.number_input("Wait Score Threshold", 0, 100, int(config['thresholds']['wait']))
    t_avoid = st.number_input("Avoid Score Threshold", 0, 100, int(config['thresholds']['avoid']))
    t_sell = st.number_input("Sell Score Threshold", 0, 100, int(config['thresholds']['sell']))
    stop_loss = st.slider("Stop Loss Pct", 0.0, 0.3, float(config['thresholds']['stop_loss_pct']), 0.01)
    target_profit = st.slider("Target Profit Pct", 0.0, 0.5, float(config['thresholds']['target_profit_pct']), 0.01)

with st.sidebar.expander("🎲 Monte Carlo Simulation", expanded=False):
    mc_iters = st.number_input("Iterations", 100, 20000, int(config['simulation']['iterations']), 100)
    mc_horizon = st.number_input("Horizon Days", 5, 120, int(config['simulation']['horizon_days']))
    mc_target = st.slider("Target Pct", 0.01, 0.25, float(config['simulation']['target_pct']), 0.005)
    mc_stop = st.slider("Stop Pct", 0.005, 0.1, float(config['simulation']['stop_pct']), 0.005)

with st.sidebar.expander("🌌 Universe & Filters", expanded=False):
    u_idx = st.selectbox("Universe Index", ["Nifty 500", "Nifty 200", "Nifty 100", "Nifty 50"], index=0)
    u_mcap = st.number_input("Min Market Cap (Cr)", 100, 10000, int(config['universe']['min_market_cap_cr']))
    u_price = st.number_input("Min Stock Price", 1, 1000, int(config['universe']['min_price']))
    u_vol = st.number_input("Min 20D Avg Volume", 1000, 10000000, int(config['universe']['min_volume_20d_avg']), 10000)

with st.sidebar.expander("🚀 System Optimization", expanded=False):
    parallel = st.number_input("Parallel Workers", 1, 32, int(config['optimization']['parallel_workers']))
    batch = st.number_input("Batch Size", 1, 200, int(config['optimization']['batch_size']))

with st.sidebar.expander("📈 Double Bottom Setup", expanded=False):
    db_lookback = st.number_input("Lookback Days", 30, 252, int(config.get('double_bottom', {}).get('lookback_days', 150)))
    db_max_diff = st.slider("Max Trough Diff Pct", 0.01, 0.15, float(config.get('double_bottom', {}).get('max_diff_pct', 0.05)), 0.01)
    db_min_bounce = st.slider("Min Bounce to Confirm Pct", 0.005, 0.10, float(config.get('double_bottom', {}).get('min_bounce_pct', 0.02)), 0.005)
    db_min_peak_bounce = st.slider("Min Peak Bounce Pct", 0.02, 0.25, float(config.get('double_bottom', {}).get('min_peak_bounce_pct', 0.07)), 0.01)

# Save changes button
if st.sidebar.button("💾 Save Configuration", use_container_width=True):
    config['weights']['fundamentals'] = w_fund
    config['weights']['valuation'] = w_val
    config['weights']['technical_trend'] = w_tech
    config['weights']['price_action'] = w_pa
    config['weights']['stat_edge'] = w_stat
    config['weights']['risk_regime'] = w_risk
    
    config['thresholds']['buy'] = t_buy
    config['thresholds']['wait'] = t_wait
    config['thresholds']['avoid'] = t_avoid
    config['thresholds']['sell'] = t_sell
    config['thresholds']['stop_loss_pct'] = stop_loss
    config['thresholds']['target_profit_pct'] = target_profit
    
    config['simulation']['iterations'] = mc_iters
    config['simulation']['horizon_days'] = mc_horizon
    config['simulation']['target_pct'] = mc_target
    config['simulation']['stop_pct'] = mc_stop
    
    config['universe']['index'] = u_idx
    config['universe']['min_market_cap_cr'] = u_mcap
    config['universe']['min_price'] = u_price
    config['universe']['min_volume_20d_avg'] = u_vol
    
    config['optimization']['parallel_workers'] = parallel
    config['optimization']['batch_size'] = batch
    
    if 'double_bottom' not in config:
        config['double_bottom'] = {}
    config['double_bottom']['lookback_days'] = db_lookback
    config['double_bottom']['max_diff_pct'] = db_max_diff
    config['double_bottom']['min_bounce_pct'] = db_min_bounce
    config['double_bottom']['min_peak_bounce_pct'] = db_min_peak_bounce
    
    save_config(config)
    st.sidebar.success("Configuration updated successfully!")
    st.session_state.config = load_config()


# ---------------------------------------------------------------------------
# Main Dashboard Header
# ---------------------------------------------------------------------------

def run_trade_simulation(picks_df, stop_loss_pct, target_profit_pct, horizon_days, mysql_config):
    symbols = picks_df['Symbol'].tolist()
    if not symbols:
        return []
        
    symbol_prices = {}
    connected = False
    
    try:
        import mysql.connector
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor()
        placeholders = ",".join(["%s"] * len(symbols))
        query = f"SELECT symbol, date, close, high, low FROM price_data WHERE symbol IN ({placeholders}) ORDER BY date"
        cursor.execute(query, tuple(symbols))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        for sym, dt, close, high, low in rows:
            d = dt.date() if isinstance(dt, datetime) or hasattr(dt, 'date') else pd.to_datetime(dt).date()
            if sym not in symbol_prices:
                symbol_prices[sym] = []
            symbol_prices[sym].append({'date': d, 'close': float(close), 'high': float(high), 'low': float(low)})
        connected = True
    except Exception as db_err:
        st.warning(f"⚠️ Local MySQL database not accessible ({db_err}). Falling back to fetching historical price data from Yahoo Finance...")
        
    if not connected:
        import yfinance as yf
        parsed_dates = []
        for _, r in picks_df.iterrows():
            ed = r.get('Entry_Date') or r.get('Entry Date')
            if ed and not pd.isna(ed):
                parsed_dates.append(pd.to_datetime(ed))
        min_date = min(parsed_dates) if parsed_dates else pd.Timestamp.now()
        start_date_str = (min_date - pd.Timedelta(days=5)).strftime('%Y-%m-%d')
        
        yf_symbols = []
        sym_map = {}
        for s in symbols:
            yf_sym = s if s.endswith('.NS') or '^' in s else f"{s}.NS"
            yf_symbols.append(yf_sym)
            sym_map[yf_sym] = s
            
        try:
            unique_yf_symbols = list(set(yf_symbols))
            data = yf.download(unique_yf_symbols, start=start_date_str, progress=False)
            
            for yf_sym in unique_yf_symbols:
                orig_sym = sym_map[yf_sym]
                symbol_prices[orig_sym] = []
                
                if len(unique_yf_symbols) == 1:
                    df_sym = data
                else:
                    if yf_sym in data.columns.get_level_values(0):
                        df_sym = data[yf_sym]
                    else:
                        continue
                        
                if 'Close' not in df_sym.columns:
                    continue
                df_sym = df_sym.dropna(subset=['Close'])
                for dt, row_p in df_sym.iterrows():
                    symbol_prices[orig_sym].append({
                        'date': dt.date(),
                        'close': float(row_p['Close']),
                        'high': float(row_p['High']),
                        'low': float(row_p['Low'])
                    })
        except Exception as yf_err:
            st.error(f"❌ Failed to fetch data from Yahoo Finance: {yf_err}")
            return []
        
    results = []
    
    for idx, row in picks_df.iterrows():
        sym = row['Symbol']
        entry_date = row.get('Entry_Date') or row.get('Entry Date')
        if not entry_date or pd.isna(entry_date):
            continue
            
        if isinstance(entry_date, str):
            entry_dt = pd.to_datetime(entry_date).date()
        elif hasattr(entry_date, 'date'):
            entry_dt = entry_date.date()
        else:
            entry_dt = entry_date
            
        prices = symbol_prices.get(sym, [])
        prices_after = [p for p in prices if p['date'] >= entry_dt]
        prices_after.sort(key=lambda x: x['date'])
        
        if not prices_after:
            continue
            
        entry_price = prices_after[0]['close']
        
        exit_price = entry_price
        exit_date = prices_after[-1]['date']
        exit_reason = "Horizon Expired"
        holding_days = 0
        
        for day_num, day_p in enumerate(prices_after):
            if day_num >= horizon_days:
                exit_price = day_p['close']
                exit_date = day_p['date']
                exit_reason = "Horizon Expired"
                holding_days = day_num
                break
                
            close_p = day_p['close']
            ret = (close_p - entry_price) / entry_price
            
            if ret <= -stop_loss_pct:
                exit_price = close_p
                exit_date = day_p['date']
                exit_reason = "Stop Loss Hit"
                holding_days = day_num
                break
                
            if ret >= target_profit_pct:
                exit_price = close_p
                exit_date = day_p['date']
                exit_reason = "Target Profit Hit"
                holding_days = day_num
                break
                
            exit_price = close_p
            exit_date = day_p['date']
            holding_days = day_num
            
        final_return = (exit_price - entry_price) / entry_price
        
        results.append({
            'Symbol': sym,
            'Sector': row.get('Sector') or row.get('Index_Name') or row.get('Index Name') or 'Other',
            'Rebound_Score': row.get('Rebound_Score') or row.get('Rebound Score') or 0.0,
            'Rank_Score': row.get('Final_Rank_Score') or row.get('Rank Score') or 0.0,
            'Entry_Date': entry_dt,
            'Entry_Price': entry_price,
            'Exit_Date': exit_date,
            'Exit_Price': exit_price,
            'Return': final_return,
            'Holding_Days': holding_days,
            'Exit_Reason': exit_reason,
            'Double_Bottom_Stage': row.get('Double_Bottom_Stage') or row.get('Double Bottom Stage') or 'None',
            'L1_Explanation': row.get('L1_Reasoning') or row.get('L1 Reasoning') or 'Stable Fundamentals',
            'L2_Explanation': row.get('L2_Reasoning') or row.get('L2 Reasoning') or 'Constructive Technical Setup',
            'L3_Explanation': row.get('L3_Reasoning') or row.get('L3 Reasoning') or 'Monte Carlo target verified'
        })
        
    return results

st.title("📈 Algo_Stocks Performance & Simulation Hub")
st.markdown("Track statistical model portfolios, run simulated backtesting runs, and configure system inputs.")

# Tabs
tab_summary, tab_inspector, tab_predict, tab_runner, tab_simulator = st.tabs([
    "📊 Performance Summary", 
    "🔍 Pick Inspector", 
    "🔮 Predict Stocks (Any Date)",
    "⚙️ Run Simulations",
    "💰 Custom Trade Simulator"
])


# ---------------------------------------------------------------------------
# Parsing Excel Helper
# ---------------------------------------------------------------------------

EXCEL_PATH = "output/backtest/Backtest_Performance_Summary.xlsx"

def is_numeric(val):
    if pd.isna(val):
        return False
    if isinstance(val, (int, float, np.integer, np.floating)):
        return not np.isnan(val)
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False

@st.cache_data
def load_excel_data(filepath):
    if not os.path.exists(filepath):
        return None, None, None
    try:
        df_db = pd.read_excel(filepath, sheet_name="Dashboard", header=None)
        
        # Parse sections dynamically
        idx_all = None
        idx_top10 = None
        for i, row in enumerate(df_db.values):
            row_str = str(row[0]) if pd.notna(row[0]) else ""
            if "REBOUND PORTFOLIO PERFORMANCE SUMMARY" in row_str:
                idx_all = i
            elif "CONCENTRATED PORTFOLIO PERFORMANCE SUMMARY" in row_str:
                idx_top10 = i
                
        if idx_all is None or idx_top10 is None:
            return None, None, None

        # Find header for Table 1 (first non-empty row after idx_all)
        header_idx_all = idx_all + 1
        while header_idx_all < len(df_db) and df_db.iloc[header_idx_all].isna().all():
            header_idx_all += 1
        headers_all = [str(h).strip().replace('\n', ' ') for h in df_db.iloc[header_idx_all].tolist()]

        # Find header for Table 2 (first non-empty row after idx_top10)
        header_idx_top10 = idx_top10 + 1
        while header_idx_top10 < len(df_db) and df_db.iloc[header_idx_top10].isna().all():
            header_idx_top10 += 1
        headers_top10 = [str(h).strip().replace('\n', ' ') for h in df_db.iloc[header_idx_top10].tolist()]

        # Table 1: All Selections
        data_all = df_db.iloc[header_idx_all + 1 : idx_top10].copy().reset_index(drop=True)
        data_all = data_all[data_all[0].notna() & (data_all[0] != "Average") & (~data_all[0].astype(str).str.contains("Portfolio|Benchmark|Average", case=False))]
        data_all.columns = headers_all
        
        # Table 2: Top 10 Concentrated Selections
        data_top10 = df_db.iloc[header_idx_top10 + 1 :].copy().reset_index(drop=True)
        data_top10 = data_top10[data_top10[0].notna() & (data_top10[0] != "Average") & (~data_top10[0].astype(str).str.contains("Portfolio|Benchmark|Average", case=False))]
        data_top10.columns = headers_top10
        
        # Find average rows dynamically
        avg_row_all = None
        for i in range(header_idx_all + 1, idx_top10):
            if str(df_db.iloc[i, 0]).strip() == "Average":
                avg_row_all = df_db.iloc[i].tolist()
                break
                
        avg_row_top10 = None
        for i in range(header_idx_top10 + 1, len(df_db)):
            if str(df_db.iloc[i, 0]).strip() == "Average":
                avg_row_top10 = df_db.iloc[i].tolist()
                break

        avg_data = {
            'all': dict(zip(headers_all, avg_row_all)) if avg_row_all else {},
            'top10': dict(zip(headers_top10, avg_row_top10)) if avg_row_top10 else {}
        }
        
        return data_all, data_top10, avg_data
    except Exception as e:
        st.error(f"Error reading performance dashboard: {e}")
        return None, None, None


# Load data
data_all, data_top10, avg_data = load_excel_data(EXCEL_PATH)


# ---------------------------------------------------------------------------
# Tab 1: Performance Summary Dashboard
# ---------------------------------------------------------------------------

with tab_summary:
    if data_all is None or data_top10 is None:
        st.warning("⚠️ No performance results found. Go to 'Run Simulations' tab to execute the pipeline and generate reports.")
    else:
        # ── KPI Row ──
        st.subheader("Performance Highlights (Avg. Monthly Initiation Return)")
        
        # Extract averages safely
        avg_p_all = avg_data['all'].get('Month 6 / Today', 0.0)
        if type(avg_p_all) == str or pd.isna(avg_p_all):
            avg_p_all = avg_data['all'].get('Month 5', 0.0)
            if type(avg_p_all) == str or pd.isna(avg_p_all):
                avg_p_all = avg_data['all'].get('Month 4', 0.0)
        
        avg_p_top10 = avg_data['top10'].get('Month 6 / Today', 0.0)
        if type(avg_p_top10) == str or pd.isna(avg_p_top10):
            avg_p_top10 = avg_data['top10'].get('Month 5', 0.0)
            
        n50_avg = avg_data['all'].get('Nifty 50', 0.0)
        n500_avg = avg_data['all'].get('Nifty 500', 0.0)
        out_n50_avg = avg_data['top10'].get('Outperform vs N50', 0.0)
        
        col1, col2, col3, col4 = st.columns(4)
        
        # Custom visual card rendering helper
        def render_kpi(col, label, value, sub_text, trend_pos=True):
            trend_class = "metric-val-positive" if trend_pos else "metric-val-negative"
            sign = "+" if (value >= 0 and value != 0) else ""
            col.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-val {trend_class}">{sign}{value * 100:.1f}%</div>
                <div class="metric-sub">{sub_text}</div>
            </div>
            """, unsafe_allow_html=True)

        render_kpi(col1, "Concentrated Portfolio (Top 10)", float(avg_p_top10) if pd.notna(avg_p_top10) else 0.0, "Average returns of highest-confidence picks", True)
        render_kpi(col2, "Full Rebound Portfolio", float(avg_p_all) if pd.notna(avg_p_all) else 0.0, "Average returns across all picked candidates", True)
        render_kpi(col3, "Nifty 50 Benchmark", float(n50_avg) if pd.notna(n50_avg) else 0.0, "Average benchmark return over same windows", True)
        
        outperform = float(avg_p_top10) - float(n50_avg) if pd.notna(avg_p_top10) and pd.notna(n50_avg) else 0.0
        render_kpi(col4, "Net Alpha vs Nifty 50", outperform, f"Outperformance margin (Top 10 vs Index)", outperform >= 0)

        # ── Interactive Plotly Chart ──
        st.subheader("📈 Simulated Return Progression over 6 Months")
        
        # Prep monthly values for line chart plotting
        months = ["Month 1", "Month 2", "Month 3", "Month 4", "Month 5", "Month 6 / Today"]
        
        # Clean functions to extract monthly returns from the average row dictionaries
        def get_series_points(avg_dict):
            pts = []
            for m in months:
                val = avg_dict.get(m, None)
                if val is not None and not isinstance(val, str) and not pd.isna(val):
                    pts.append(float(val) * 100)
                else:
                    pts.append(None)
            return pts
            
        y_all = get_series_points(avg_data['all'])
        y_top10 = get_series_points(avg_data['top10'])
        
        # For benchmarks, we need to read monthly returns. Since benchmarks are in the excel run sheets,
        # we can reconstruct benchmark points or pull from averages
        y_n50 = [None] * len(months)
        y_n500 = [None] * len(months)
        # Try to pull standard benchmark rates (T-180 averages across sheets)
        y_n50[-1] = float(n50_avg) * 100 if pd.notna(n50_avg) else None
        y_n500[-1] = float(n500_avg) * 100 if pd.notna(n500_avg) else None
        
        # Reconstruct progress from data_all to map progress curve
        # Let's average values for available months
        curve_all = []
        curve_top10 = []
        curve_n50 = []
        curve_n500 = []
        
        for m in months:
            # Table 1
            vals = []
            if m in data_all.columns:
                for val in data_all[m].values:
                    if is_numeric(val):
                        vals.append(float(val))
            curve_all.append(np.mean(vals) * 100 if vals else None)
            
            # Table 2
            vals_t = []
            if m in data_top10.columns:
                for val in data_top10[m].values:
                    if is_numeric(val):
                        vals_t.append(float(val))
            curve_top10.append(np.mean(vals_t) * 100 if vals_t else None)
            
            # Nifty 50 and 500 benchmarks progress mapping:
            # We can approximate the benchmark monthly returns by averaging the returns across dates for that month
            # Let's pull dates from the excel sheets to build actual index benchmarks
            # For simplicity, we interpolate or show endpoints. Let's make an beautiful plot.
            
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=["Start"] + months, y=[0] + curve_top10, name="Concentrated (Top 10 Picks)", line=dict(color="#10b981", width=3.5), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=["Start"] + months, y=[0] + curve_all, name="Full Rebound Portfolio", line=dict(color="#6366f1", width=2.5), mode='lines+markers'))
        
        # Benchmark endpoints
        fig.add_trace(go.Scatter(x=["Start", "Month 6 / Today"], y=[0, float(n50_avg) * 100], name="Nifty 50 Index (Benchmark)", line=dict(color="#f59e0b", width=2, dash='dash'), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=["Start", "Month 6 / Today"], y=[0, float(n500_avg) * 100], name="Nifty 500 Index (Benchmark)", line=dict(color="#ef4444", width=2, dash='dot'), mode='lines+markers'))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94a3b8'),
            xaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Holding Period"),
            yaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Average Cumulative Return (%)", ticksuffix="%"),
            margin=dict(l=20, r=20, t=10, b=10),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Data Tables ──
        st.subheader("📋 Performance Tables")
        
        # Display data_top10 table formatted
        st.write("**Concentrated Portfolio Summary (Top 10 Picks)**")
        disp_top10 = data_top10.copy()
        # Format percentage columns
        for col in months + ['Nifty 50', 'Nifty 500', 'Outperform vs N50', 'Outperform vs N500']:
            if col in disp_top10.columns:
                disp_top10[col] = disp_top10[col].apply(lambda x: f"{float(x)*100:.1f}%" if (pd.notna(x) and not isinstance(x, str) and x != "—") else "—")
        st.dataframe(disp_top10, use_container_width=True, hide_index=True)
        
        st.write("**Full Rebound Portfolio Summary (All Picks)**")
        disp_all = data_all.copy()
        # Format percentage columns
        for col in months + ['Nifty 50', 'Nifty 500', 'Outperform vs N50', 'Outperform vs N500']:
            if col in disp_all.columns:
                disp_all[col] = disp_all[col].apply(lambda x: f"{float(x)*100:.1f}%" if (pd.notna(x) and not isinstance(x, str) and x != "—") else "—")
        st.dataframe(disp_all, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tab 2: Detailed Picking Inspector
# ---------------------------------------------------------------------------

with tab_inspector:
    if not os.path.exists(EXCEL_PATH):
        st.warning("⚠️ No simulation report found to inspect.")
    else:
        st.subheader("🔍 Individual Run Picker & Stock Breakdown")
        
        # Load dates sheets
        xl = pd.ExcelFile(EXCEL_PATH)
        sheet_names = [s for s in xl.sheet_names if s != "Dashboard"]
        
        selected_sheet = st.selectbox("Select Backtesting Date Run:", sheet_names)
        
        if selected_sheet:
            # Load selected sheet
            # Note: headers are on row 2 (0-indexed)
            df_sheet = pd.read_excel(EXCEL_PATH, sheet_name=selected_sheet, header=2)
            # Clean up column headers by replacing newlines with spaces and stripping whitespace
            df_sheet.columns = [str(c).strip().replace('\n', ' ').replace('  ', ' ') for c in df_sheet.columns]
            
            # Clean dataframe rows: remove blank rows or average summary blocks at the bottom
            # Summary blocks start when "Symbol" or "Sector" has average phrases
            df_sheet = df_sheet[df_sheet['Symbol'].notna()]
            df_sheet_clean = df_sheet[~df_sheet['Symbol'].astype(str).str.contains("Portfolio|Benchmark|Average", case=False)].copy()
            
            # Format Columns
            percent_cols = [c for c in df_sheet_clean.columns if "Return" in str(c)]
            price_cols = [c for c in df_sheet_clean.columns if "Price" in str(c)]
            
            for c in percent_cols:
                df_sheet_clean[c] = df_sheet_clean[c].apply(lambda x: f"{float(x)*100:.1f}%" if (pd.notna(x) and not isinstance(x, str) and x != '—') else "—")
            for c in price_cols:
                df_sheet_clean[c] = df_sheet_clean[c].apply(lambda x: f"₹{float(x):,.2f}" if (pd.notna(x) and not isinstance(x, str) and x != '—') else "—")
            
            df_sheet_clean['Rebound Score'] = df_sheet_clean['Rebound Score'].apply(lambda x: f"{float(x):.1f}" if pd.notna(x) else "—")
            df_sheet_clean['Rank Score'] = df_sheet_clean['Rank Score'].apply(lambda x: f"{float(x):.1f}" if pd.notna(x) else "—")
            
            st.write(f"Showing picks initiated on **{selected_sheet}**:")
            
            # Search filter
            search_query = st.text_input("Filter by Symbol or Sector:", "")
            if search_query:
                df_sheet_clean = df_sheet_clean[
                    df_sheet_clean['Symbol'].astype(str).str.contains(search_query, case=False) |
                    df_sheet_clean['Sector'].astype(str).str.contains(search_query, case=False)
                ]
                
            st.dataframe(df_sheet_clean, use_container_width=True, hide_index=True)
            
            # Show summary comparisons from the bottom of the sheet
            df_summary_vals = df_sheet[df_sheet['Symbol'].astype(str).str.contains("Portfolio|Benchmark|Average", case=False)].copy()
            if not df_summary_vals.empty:
                st.write("**Initiation Averages & Benchmarks Details**")
                
                # Format
                for c in percent_cols:
                    df_summary_vals[c] = df_summary_vals[c].apply(lambda x: f"{float(x)*100:.1f}%" if (pd.notna(x) and not isinstance(x, str) and x != '—') else "—")
                for c in price_cols:
                    df_summary_vals[c] = df_summary_vals[c].apply(lambda x: f"₹{float(x):,.2f}" if (pd.notna(x) and not isinstance(x, str) and x != '—') else "—")
                
                st.dataframe(df_summary_vals[['Symbol', 'Sector'] + percent_cols], use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tab 2.5: Predict & Analyze Strategy on Any Date
# ---------------------------------------------------------------------------

with tab_predict:
    st.subheader("🔮 Predict & Analyze Strategy on Any Date")
    st.markdown("Select a date from the calendar to run the stock selection pipeline or load existing predictions as-of that date. This analyzes pre-layer sector configurations, checks macro/policy drivers, and generates stock-by-stock recommendations with deep justifications.")

    col_p1, col_p2 = st.columns([1, 2])
    target_date = col_p1.date_input("Target Analysis Date:", value=datetime(2026, 6, 7).date(), key="predict_target_date")
    
    date_str = target_date.strftime('%Y-%m-%d')
    date_clean = target_date.strftime('%Y%m%d')
    
    picks_csv = f"output/backtest/run_{date_clean}/picks.csv"
    sector_json = f"output/backtest/run_{date_clean}/sector_results.json"
    
    exists = os.path.exists(picks_csv) and os.path.exists(sector_json)
    
    if exists:
        col_p2.success(f"✅ Found existing analysis files for **{date_str}**.")
    else:
        col_p2.warning(f"⚠️ No analysis files found for **{date_str}**. You need to execute the engine to generate predictions.")

    col_btn1, col_btn2 = st.columns(2)
    run_engine = col_btn1.button("🏃‍♂️ Run Analysis Engine for this Date", use_container_width=True, key="predict_run_engine")
    load_results = False
    
    if exists:
        load_results = col_btn2.button("📂 Load Predictions & Justifications", use_container_width=True, key="predict_load_results") or st.session_state.get(f"loaded_{date_clean}", False)
        if load_results:
            st.session_state[f"loaded_{date_clean}"] = True
    
    # Subprocess execution logic
    log_placeholder = st.empty()
    if run_engine:
        st.info(f"Executing Algo_Stocks analysis pipeline for {date_str}...")
        cmd = [sys.executable, "backtest/backtest_engine.py", "--dates", date_str]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=os.getcwd()
        )
        
        log_lines = []
        while True:
            line = process.stdout.readline()
            if not line:
                break
            log_lines.append(line)
            if len(log_lines) > 100:
                log_lines.pop(0)
            log_placeholder.markdown(f"""
            <div class="log-console">
                {"".join(log_lines).replace('\n', '<br>')}
            </div>
            """, unsafe_allow_html=True)
            
        process.wait()
        
        if process.returncode == 0:
            st.success(f"✅ Analysis for {date_str} completed successfully!")
            st.session_state[f"loaded_{date_clean}"] = True
            load_results = True
            st.rerun()
        else:
            st.error(f"❌ Analysis failed with exit code: {process.returncode}")

    if load_results and os.path.exists(picks_csv) and os.path.exists(sector_json):
        # Load files
        import json
        with open(sector_json, "r") as f:
            sec_data = json.load(f)
        df_picks = pd.read_csv(picks_csv)
        
        # ── 1. Sector Selection Pre-Layer ──
        st.markdown("---")
        st.header("🏢 Sector Selection & Justifications")
        st.markdown(f"**India VIX:** `{sec_data.get('vix', 0.0):.2f}`")
        
        selected_indices = sec_data.get('selected_indices', [])
        justifications = sec_data.get('justifications', {})
        all_scores = sec_data.get('all_scores', {})
        oversold_highlights = sec_data.get('oversold_highlights', {})
        rejected_sectors = sec_data.get('rejected_sectors', [])
        
        st.subheader("Selected Sectors Summary")
        
        # Display selected sectors in card/KPI style
        col_sec = st.columns(len(selected_indices) if selected_indices else 1)
        for i, idx in enumerate(selected_indices):
            score_dict = all_scores.get(idx, {})
            comp_score = score_dict.get('composite', 0.0)
            col_sec[i].markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Rank {i+1} Sector</div>
                <div class="metric-val" style="color: #6366f1; font-size:1.8rem; margin: 5px 0;">{idx}</div>
                <div class="metric-sub" style="font-size:0.95rem; color:#10b981; font-weight:bold;">Score: {comp_score:.1f}/100</div>
            </div>
            """, unsafe_allow_html=True)
            
        # Sector Details & Justifications
        st.subheader("Detailed Sector Rotation Rationale")
        for i, idx in enumerate(selected_indices):
            score_dict = all_scores.get(idx, {})
            comp_score = score_dict.get('composite', 0.0)
            with st.expander(f"💼 {idx} - Score: {comp_score:.1f} | Rotation & Economic Rationale"):
                st.markdown("**Rotational/Macro Justification:**")
                st.info(justifications.get(idx, "No justification details available."))
                
                # Factors breakdown
                st.markdown("**Rotational Factors Breakdown (Scores: 0-100):**")
                col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
                col_f1.metric("A. Econ Rotation", f"{score_dict.get('score_A', 0):.0f}")
                col_f2.metric("B. Seasonality", f"{score_dict.get('score_B', 0):.0f}")
                col_f3.metric("C. Technicals", f"{score_dict.get('score_C', 0):.0f}")
                col_f4.metric("D. Fundamentals", f"{score_dict.get('score_D', 0):.0f}")
                col_f5.metric("E. Policy/Macro", f"{score_dict.get('score_E', 0):.0f}")
                
                # Oversold stocks highlight in this sector
                highlights = oversold_highlights.get(idx, [])
                if highlights:
                    st.markdown(f"**Top Oversold Constituents in {idx}:**")
                    df_hl = pd.DataFrame(highlights)
                    if not df_hl.empty:
                        # Rename/Select columns to look clean
                        col_map = {
                            'symbol': 'Symbol',
                            'rebound_score': 'Rebound Score',
                            'current_price': 'Price (₹)',
                            'pct_from_52w_high': '% from 52W High',
                            'pct_from_52w_low': '% from 52W Low',
                            'rsi_latest': 'RSI (14D)',
                            'pe': 'PE Ratio',
                            'roe': 'ROE (%)',
                            'rev_growth': 'Revenue Growth (%)',
                            'flag_oversold': 'Oversold Flag',
                            'flag_52w_low': '52W Low Flag'
                        }
                        df_hl_disp = df_hl.rename(columns=col_map)
                        disp_cols = [c for c in col_map.values() if c in df_hl_disp.columns]
                        
                        # Formatting
                        for c in ['Price (₹)']:
                            if c in df_hl_disp.columns:
                                df_hl_disp[c] = df_hl_disp[c].apply(lambda x: f"₹{x:,.2f}" if pd.notna(x) else "—")
                        for c in ['Rebound Score', 'RSI (14D)', 'PE Ratio', 'ROE (%)', 'Revenue Growth (%)', '% from 52W High', '% from 52W Low']:
                            if c in df_hl_disp.columns:
                                df_hl_disp[c] = df_hl_disp[c].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
                                
                        st.dataframe(df_hl_disp[disp_cols], use_container_width=True, hide_index=True)
                else:
                    st.warning("No oversold constituents highlighted for this sector.")
                    
        # Rejected Sectors
        if rejected_sectors:
            with st.expander("🚫 Reviewed Sectors Not Selected"):
                df_rej = pd.DataFrame(rejected_sectors, columns=["Index Name", "Reason for Rejection"])
                st.dataframe(df_rej, use_container_width=True, hide_index=True)
                
        # ── 2. Recommended Picks ──
        st.markdown("---")
        st.header("🎯 Stock Analysis Recommendations")
        
        # Search and filters
        col_f_1, col_f_2 = st.columns([1, 1])
        symbol_search = col_f_1.text_input("Search Symbol:", "", key="pred_symbol_search")
        action_filter = col_f_2.multiselect("Filter by Recommendation Action:", 
                                            options=['BUY', 'WAIT', 'AVOID', 'SELL'], 
                                            default=['BUY', 'WAIT'])
        
        df_filtered = df_picks.copy()
        if symbol_search:
            df_filtered = df_filtered[df_filtered['Symbol'].astype(str).str.contains(symbol_search, case=False)]
        if action_filter:
            df_filtered = df_filtered[df_filtered['Action'].isin(action_filter)]
            
        st.subheader(f"Strategy Stock Picks ({len(df_filtered)} stocks found)")
        
        if df_filtered.empty:
            st.warning("No stocks matched the filter criteria.")
        else:
            disp_picks = df_filtered.copy()
            # Clean columns formatting
            disp_picks['Price'] = disp_picks['Price'].apply(lambda x: f"₹{x:,.2f}" if pd.notna(x) else "—")
            disp_picks['Final_Rank_Score'] = disp_picks['Final_Rank_Score'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
            disp_picks['Rebound_Score'] = disp_picks['Rebound_Score'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
            disp_picks['Score'] = disp_picks['Score'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
            disp_picks['Confidence'] = disp_picks['Confidence'].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "—")
            
            show_cols = [
                'Symbol', 'Index_Name', 'Price', 'Action', 'Final_Rank_Score', 
                'Rebound_Score', 'Score', 'Confidence', 'Horizon', 
                'Flag_52W_LOW', 'Flag_OVERSOLD', 'Flag_Double_Bottom', 'Double_Bottom_Stage'
            ]
            st.dataframe(disp_picks[[c for c in show_cols if c in disp_picks.columns]], use_container_width=True, hide_index=True)
            
            # Stock-by-Stock Explanations (Excel-Grade Details)
            st.subheader("🔍 Stock-by-Stock Explanations (Excel-Grade Details)")
            for idx, row in df_filtered.sort_values('Final_Rank_Score', ascending=False).iterrows():
                db_stage = row.get('Double_Bottom_Stage') or 'None'
                
                with st.expander(f"📘 {row['Symbol']} - Action: {row['Action']} | Rank: {row['Final_Rank_Score']:.1f} | Rebound: {row['Rebound_Score']:.1f} | DB Stage: {db_stage}"):
                    col_exp1, col_exp2 = st.columns(2)
                    
                    col_exp1.markdown(f"**Index:** {row['Index_Name']}")
                    col_exp1.markdown(f"**Entry Price:** ₹{row['Price']:.2f}")
                    col_exp1.markdown(f"**Monte Carlo Target:** ₹{row['P_Target']:.2f} (+{(row['P_Target']-row['Price'])/row['Price']*100:+.1f}%)")
                    col_exp1.markdown(f"**Monte Carlo Stop Loss:** ₹{row['P_Stop']:.2f} ({(row['P_Stop']-row['Price'])/row['Price']*100:+.1f}%)")
                    col_exp1.markdown(f"**Predicted Horizon:** {row['Horizon']} days")
                    
                    # Technical & Rebound info
                    st.markdown("**Rebound/Technical metrics:**")
                    rm1, rm2, rm3 = st.columns(3)
                    rm1.metric("RSI (14D)", f"{row['RSI']:.1f}" if pd.notna(row['RSI']) else "—")
                    rm2.metric("% above 52W Low", f"{row['Pct_From_52W_Low']:.1f}%" if pd.notna(row['Pct_From_52W_Low']) else "—")
                    rm3.metric("52W Low Price", f"₹{row['52W_Low']:.2f}" if pd.notna(row['52W_Low']) else "—")
                    
                    # Expose fundamental snaps
                    st.markdown("**Fundamental metrics:**")
                    fm1, fm2, fm3 = st.columns(3)
                    fm1.metric("PE Ratio", f"{row.get('PE_Ratio', 0.0):.1f}" if pd.notna(row.get('PE_Ratio')) else "—")
                    fm2.metric("ROE (%)", f"{row.get('ROE', 0.0):.1f}%" if pd.notna(row.get('ROE')) else "—")
                    fm3.metric("Rev Growth (%)", f"{row.get('Revenue_Growth_Pct', 0.0):.1f}%" if pd.notna(row.get('Revenue_Growth_Pct')) else "—")

                    # Original 3 layers explanations
                    st.markdown("---")
                    st.markdown("**Execution Layer Justifications:**")
                    col_exp2.markdown(f"**Layer 1 (Fundamentals):** {row['L1_Reasoning']}")
                    col_exp2.markdown(f"**Layer 2 (Technical Trend):** {row['L2_Reasoning']}")
                    col_exp2.markdown(f"**Layer 3 (Statistical Edge):** {row['L3_Reasoning']}")


# ---------------------------------------------------------------------------
# Tab 3: Simulation Subprocess Runner
# ---------------------------------------------------------------------------

with tab_runner:
    st.subheader("⚙️ Run Pipeline Backtesting Simulations")
    st.markdown("Trigger full simulation runs. Note that running full simulations involves CPU-heavy Monte Carlo simulations and scans multiple stocks. Progress will be displayed in real time below.")
    
    with st.expander("🛠️ Backtest Parameters & Configurations", expanded=True):
        col_inp1, col_inp2 = st.columns(2)
        bt_dates_str = col_inp1.text_area("Backtest Dates (Comma-separated YYYY-MM-DD):", 
                                          value="2025-12-07, 2026-01-07, 2026-02-07, 2026-03-07, 2026-04-07, 2026-05-07",
                                          help="Dates to execute historical scans and score generation.")
        
        entry_threshold = col_inp2.slider("Entry Score Threshold (Rebound Score):", min_value=30.0, max_value=95.0, value=70.0, step=5.0)
        top_n = col_inp2.slider("Concentrated Portfolio Size (Top N picks):", min_value=3, max_value=20, value=10, step=1)
        
        today_date_anchor = col_inp1.date_input("Today's Date Anchor:", value=datetime(2026, 6, 7).date())
        limit_per_index = col_inp2.number_input("Limit constituents per Index (optional, 0 for unlimited):", min_value=0, value=0, step=1)
        
    col_bt1, col_bt2 = st.columns(2)
    
    run_backtest_btn = col_bt1.button("🏃‍♂️ Run Full Backtest Simulation Pipeline", use_container_width=True)
    run_perf_btn = col_bt2.button("📊 Update Performance Analysis & Report", use_container_width=True)
    
    # Placeholder for live command logs
    log_placeholder = st.empty()
    
    if run_backtest_btn:
        st.info("Initiating backtesting subprocess... Running simulation dates.")
        
        # Execute script via subprocess and redirect stdout
        cmd = [sys.executable, "backtest/backtest_engine.py"]
        if bt_dates_str.strip():
            dates_cleaned = ",".join([d.strip() for d in bt_dates_str.split(",") if d.strip()])
            cmd.extend(["--dates", dates_cleaned])
        if limit_per_index > 0:
            cmd.extend(["--limit", str(limit_per_index)])
            
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=os.getcwd()
        )
        
        log_lines = []
        
        while True:
            line = process.stdout.readline()
            if not line:
                break
            # Append line to console log
            log_lines.append(line)
            # Limit the display log size
            if len(log_lines) > 200:
                log_lines.pop(0)
            
            # Format and display logs dynamically
            log_placeholder.markdown(f"""
            <div class="log-console">
                {"".join(log_lines).replace('\n', '<br>')}
            </div>
            """, unsafe_allow_html=True)
            
        process.wait()
        
        if process.returncode == 0:
            st.success("✅ Backtest simulation completed successfully! Next, run the performance analysis to update Excel dashboard.")
        else:
            st.error(f"❌ Subprocess failed with exit code: {process.returncode}")
            
    if run_perf_btn:
        st.info("Initiating performance tracker subprocess... Pre-loading price history and matching index benchmarks.")
        
        cmd = [sys.executable, "backtest/performance_tracker.py"]
        if bt_dates_str.strip():
            dates_cleaned = ",".join([d.strip() for d in bt_dates_str.split(",") if d.strip()])
            cmd.extend(["--dates", dates_cleaned])
        cmd.extend(["--entry-threshold", str(entry_threshold)])
        cmd.extend(["--top-n", str(top_n)])
        if today_date_anchor:
            cmd.extend(["--today-date", today_date_anchor.strftime("%Y-%m-%d")])
            
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=os.getcwd()
        )
        
        log_lines = []
        
        while True:
            line = process.stdout.readline()
            if not line:
                break
            log_lines.append(line)
            if len(log_lines) > 200:
                log_lines.pop(0)
                
            log_placeholder.markdown(f"""
            <div class="log-console">
                {"".join(log_lines).replace('\n', '<br>')}
            </div>
            """, unsafe_allow_html=True)
            
        process.wait()
        
        if process.returncode == 0:
            st.success("✅ Performance Tracker completed successfully! Excel Report and results cache saved. Reloading page...")
            # Clear caches to force reload the sheet data
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(f"❌ Subprocess failed with exit code: {process.returncode}")

    # Inline Results Rendering
    cache_json_path = "output/backtest/latest_results_cache.json"
    if os.path.exists(cache_json_path):
        import json
        try:
            with open(cache_json_path, "r") as f:
                res_cache = json.load(f)
            
            st.markdown("---")
            st.subheader("📊 Latest Backtest Simulation Results (Inline Dashboard)")
            
            # Calculate and render aggregated KPIs across all runs
            dates_keys = list(res_cache.keys())
            if dates_keys:
                portfolio_final_returns = []
                top_final_returns = []
                n50_final_returns = []
                n500_final_returns = []
                
                for d_key in dates_keys:
                    run_data = res_cache[d_key]
                    stocks = run_data.get('stocks', [])
                    benchmarks = run_data.get('benchmarks', {})
                    dates_list_m = run_data.get('dates', [])
                    m_len = len(dates_list_m)
                    
                    if m_len > 0:
                        # Full portfolio return
                        rets_all = [s['Returns'].get(f'M{m_len}') for s in stocks if s['Returns'].get(f'M{m_len}') is not None]
                        if rets_all:
                            portfolio_final_returns.append(np.mean(rets_all))
                            
                        # Concentrated portfolio return
                        rets_top = [s['Returns'].get(f'M{m_len}') for s in stocks if s.get('In_Top10') and s['Returns'].get(f'M{m_len}') is not None]
                        if rets_top:
                            top_final_returns.append(np.mean(rets_top))
                            
                        # Benchmarks final returns
                        n50_ret = benchmarks.get('Nifty 50', {}).get('returns', {}).get(f'M{m_len}')
                        if n50_ret is not None:
                            n50_final_returns.append(n50_ret)
                            
                        n500_ret = benchmarks.get('Nifty 500', {}).get('returns', {}).get(f'M{m_len}')
                        if n500_ret is not None:
                            n500_final_returns.append(n500_ret)
                
                avg_full = np.mean(portfolio_final_returns) if portfolio_final_returns else 0.0
                avg_top = np.mean(top_final_returns) if top_final_returns else 0.0
                avg_n50 = np.mean(n50_final_returns) if n50_final_returns else 0.0
                avg_n500 = np.mean(n500_final_returns) if n500_final_returns else 0.0
                
                # Render KPI row
                rk1, rk2, rk3, rk4 = st.columns(4)
                
                def render_inline_kpi(col, label, value, sub_text):
                    trend_class = "metric-val-positive" if value >= 0 else "metric-val-negative"
                    sign = "+" if value >= 0 else ""
                    col.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">{label}</div>
                        <div class="metric-val {trend_class}">{sign}{value * 100:.1f}%</div>
                        <div class="metric-sub">{sub_text}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                render_inline_kpi(rk1, "Full Portfolio Avg Return", avg_full, "Average across all run dates")
                render_inline_kpi(rk2, f"Concentrated Avg Return (Top {top_n})", avg_top, "Average return of top picks")
                render_inline_kpi(rk3, "Nifty 50 Index Return", avg_n50, "Benchmark average return")
                
                alpha_val = avg_top - avg_n50
                render_inline_kpi(rk4, "Concentrated Alpha vs N50", alpha_val, "Outperformance margin")
                
                # Plotly progression chart
                st.subheader("📈 Cumulative Forward Return Trajectory")
                
                # We need to construct month-by-month averages across all run dates
                months = ["M1", "M2", "M3", "M4", "M5", "M6"]
                curve_full_y = []
                curve_top_y = []
                
                for m in months:
                    all_m_rets = []
                    top_m_rets = []
                    for d_key in dates_keys:
                        run_data = res_cache[d_key]
                        stocks = run_data.get('stocks', [])
                        rets_m_all = [s['Returns'].get(m) for s in stocks if s['Returns'].get(m) is not None]
                        if rets_m_all:
                            all_m_rets.append(np.mean(rets_m_all))
                            
                        rets_m_top = [s['Returns'].get(m) for s in stocks if s.get('In_Top10') and s['Returns'].get(m) is not None]
                        if rets_m_top:
                            top_m_rets.append(np.mean(rets_m_top))
                            
                    curve_full_y.append(np.mean(all_m_rets) * 100 if all_m_rets else None)
                    curve_top_y.append(np.mean(top_m_rets) * 100 if top_m_rets else None)
                
                fig_inline = go.Figure()
                valid_months_top = [f"Month {i+1}" for i in range(len(curve_top_y)) if curve_top_y[i] is not None]
                valid_vals_top = [val for val in curve_top_y if val is not None]
                if valid_vals_top:
                    fig_inline.add_trace(go.Scatter(x=["Start"] + valid_months_top, y=[0.0] + valid_vals_top, 
                                                    name="Concentrated Portfolio", line=dict(color="#10b981", width=3.5), mode='lines+markers'))
                
                valid_months_full = [f"Month {i+1}" for i in range(len(curve_full_y)) if curve_full_y[i] is not None]
                valid_vals_full = [val for val in curve_full_y if val is not None]
                if valid_vals_full:
                    fig_inline.add_trace(go.Scatter(x=["Start"] + valid_months_full, y=[0.0] + valid_vals_full, 
                                                    name="Full Rebound Portfolio", line=dict(color="#6366f1", width=2.5), mode='lines+markers'))
                
                fig_inline.add_trace(go.Scatter(x=["Start", f"Month {len(dates_keys)}"], y=[0.0, avg_n50 * 100], name="Nifty 50 Index (Benchmark)", line=dict(color="#f59e0b", width=2, dash='dash'), mode='lines+markers'))
                
                fig_inline.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#94a3b8'),
                    xaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Holding Period"),
                    yaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Average Cumulative Return (%)", ticksuffix="%"),
                    margin=dict(l=20, r=20, t=10, b=10),
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_inline, use_container_width=True)
                
                # Detailed date-by-date tables and expanders
                st.subheader("📋 Detailed Simulation Runs")
                selected_run_date = st.selectbox("Select Run Date to Inspect:", dates_keys, key="run_date_selector_inline")
                
                if selected_run_date:
                    run_data = res_cache[selected_run_date]
                    stocks = run_data.get('stocks', [])
                    benchmarks = run_data.get('benchmarks', {})
                    m_dates = run_data.get('dates', [])
                    
                    df_stocks = pd.DataFrame(stocks)
                    
                    if not df_stocks.empty:
                        disp_cols = ['Symbol', 'Sector', 'Rebound_Score', 'Final_Rank_Score', 'Double_Bottom_Stage', 'Entry_Date', 'Entry_Price']
                        
                        df_table = df_stocks.copy()
                        df_table['Entry_Price'] = df_table['Entry_Price'].apply(lambda x: f"₹{float(x):,.2f}" if pd.notna(x) else "—")
                        df_table['Rebound_Score'] = df_table['Rebound_Score'].apply(lambda x: f"{float(x):.1f}" if pd.notna(x) else "—")
                        df_table['Final_Rank_Score'] = df_table['Final_Rank_Score'].apply(lambda x: f"{float(x):.1f}" if pd.notna(x) else "—")
                        
                        # Add month-by-month return columns dynamically
                        for m_idx in range(1, len(m_dates) + 1):
                            col_name = f'Month {m_idx} Return'
                            df_table[col_name] = df_stocks['Returns'].apply(lambda r: f"{r.get(f'M{m_idx}')*100:+.1f}%" if r.get(f'M{m_idx}') is not None else "—")
                            disp_cols.append(col_name)
                            
                        # Sort by Rank Score descending
                        df_table = df_table.sort_values('Final_Rank_Score', ascending=False)
                        st.dataframe(df_table[disp_cols], use_container_width=True, hide_index=True)
                        
                        # Stock Analysis Trade Explanations
                        st.subheader("🔍 Stock-by-Stock Explanations (Excel-Grade Details)")
                        for idx, s_row in df_stocks.sort_values('Final_Rank_Score', ascending=False).iterrows():
                            f_ret = s_row['Returns'].get(f'M{len(m_dates)}')
                            f_ret_str = f"{f_ret*100:+.1f}%" if f_ret is not None else "—"
                            
                            with st.expander(f"📘 {s_row['Symbol']} - Rank: {s_row['Final_Rank_Score']:.1f} | Rebound: {s_row['Rebound_Score']:.1f} | Stage: {s_row['Double_Bottom_Stage']} | Return: {f_ret_str}"):
                                col_desc1, col_desc2 = st.columns(2)
                                col_desc1.markdown(f"**Sector:** {s_row['Sector']}")
                                col_desc1.markdown(f"**Entry Price:** ₹{s_row['Entry_Price']:.2f} (on {s_row['Entry_Date']})")
                                
                                last_m = f"M{len(m_dates)}"
                                last_m_pr = s_row['Prices'].get(last_m)
                                last_m_dt = s_row['Prices'].get(f"{last_m}_Date")
                                col_desc1.markdown(f"**Current/Latest Price:** ₹{last_m_pr:.2f} (on {last_m_dt})" if last_m_pr else "**Price:** —")
                                
                                col_desc2.markdown(f"**Layer 1 (Fundamentals):** {s_row.get('L1_Explanation', 'Stable Fundamentals')}")
                                col_desc2.markdown(f"**Layer 2 (Technical Trend):** {s_row.get('L2_Explanation', 'Constructive Technical Setup')}")
                                col_desc2.markdown(f"**Layer 3 (Statistical Edge):** {s_row.get('L3_Explanation', 'Monte Carlo target verified')}")
            
        except Exception as cache_err:
            st.error(f"Error reading/parsing results cache JSON: {cache_err}")


# ---------------------------------------------------------------------------
# Tab 4: Custom Trade Simulator
# ---------------------------------------------------------------------------

with tab_simulator:
    st.subheader("💰 Dynamic Trade Simulator & Exit Strategy Backtester")
    st.markdown("Initiate simulation runs on specific backtesting dates with your own stop loss and profit targets, modeling when trades would trigger exits.")
    
    if not os.path.exists(EXCEL_PATH):
        st.warning("⚠️ No simulation report found to load dates.")
    else:
        xl = pd.ExcelFile(EXCEL_PATH)
        sheet_names = [s for s in xl.sheet_names if s != "Dashboard"]
        
        col_sim1, col_sim2 = st.columns(2)
        
        # Changed choice from selectbox to multiselect to allow running simulation across multiple dates
        sim_dates = col_sim1.multiselect("Choose Initiation Dates:", sheet_names, default=sheet_names, key="sim_dates_select")
        
        # Trade parameters
        stop_loss_pct = col_sim2.slider("Stop Loss Pct (Min Loss Limit):", 0.01, 0.30, 0.10, 0.01, format="%.2f")
        target_profit_pct = col_sim2.slider("Target Profit Pct (Max Profit Limit):", 0.05, 0.50, 0.25, 0.01, format="%.2f")
        horizon_days = col_sim1.slider("Max Holding Horizon (Trading Days):", 10, 252, 120, 5)
        
        if st.button("🚀 Run Trade Simulation", use_container_width=True):
            if not sim_dates:
                st.error("Please select at least one initiation date.")
            else:
                st.info(f"Simulating trades initiated across {len(sim_dates)} dates...")
                
                all_picks_list = []
                for s_date in sim_dates:
                    date_clean = s_date.replace("-", "")
                    picks_csv_path = f"output/backtest/run_{date_clean}/picks.csv"
                    
                    picks_df = None
                    if os.path.exists(picks_csv_path):
                        picks_df = pd.read_csv(picks_csv_path)
                        picks_df['Entry_Date'] = s_date
                        # Filter for Top Picks
                        picks_df = picks_df[(picks_df['Rebound_Score'] >= 70) | (picks_df['Flag_OVERSOLD'] == 'YES')].copy()
                        if picks_df.empty:
                            picks_df = picks_df.sort_values('Rebound_Score', ascending=False).head(20).copy()
                    else:
                        # Fallback to excel sheet
                        try:
                            df_sheet = pd.read_excel(EXCEL_PATH, sheet_name=s_date, header=2)
                            df_sheet.columns = [str(c).strip().replace('\n', ' ').replace('  ', ' ') for c in df_sheet.columns]
                            picks_df = df_sheet[~df_sheet['Symbol'].astype(str).str.contains("Portfolio|Benchmark|Average", case=False)].copy()
                            picks_df['Entry_Date'] = s_date
                            picks_df['Entry_Price'] = picks_df['Entry Price']
                            picks_df['Rebound_Score'] = picks_df['Rebound Score']
                            picks_df['Final_Rank_Score'] = picks_df['Rank Score']
                            picks_df['Double_Bottom_Stage'] = picks_df['Double Bottom Stage']
                            picks_df['L1_Explanation'] = df_sheet.get('L1 Reasoning') or df_sheet.get('L1_Reasoning') or 'Stable Fundamentals'
                            picks_df['L2_Explanation'] = df_sheet.get('L2 Reasoning') or df_sheet.get('L2_Reasoning') or 'Constructive Technical Setup'
                            picks_df['L3_Explanation'] = df_sheet.get('L3 Reasoning') or df_sheet.get('L3_Reasoning') or 'Monte Carlo target verified'
                        except Exception as e:
                            st.warning(f"Could not load data for sheet {s_date}: {e}")
                            continue
                    
                    if picks_df is not None and not picks_df.empty:
                        all_picks_list.append(picks_df)
                        
                if not all_picks_list:
                    st.error("No pick data found for selected dates.")
                else:
                    combined_picks = pd.concat(all_picks_list, ignore_index=True)
                    
                    # Run simulation
                    results = run_trade_simulation(combined_picks, stop_loss_pct, target_profit_pct, horizon_days, config['mysql'])
                    
                    if not results:
                        st.warning("No price data found to run simulation.")
                    else:
                        df_res = pd.DataFrame(results)
                        
                        # Compute statistics
                        avg_ret = df_res['Return'].mean()
                        win_rate = (df_res['Return'] > 0).mean()
                        avg_hold = df_res['Holding_Days'].mean()
                        
                        # Count exit reasons
                        reasons_counts = df_res['Exit_Reason'].value_counts()
                        
                        # Render KPIs
                        k1, k2, k3, k4 = st.columns(4)
                        
                        def render_sim_kpi(col, label, value, sub_text, is_pct=True):
                            trend_class = "metric-val-positive" if value >= 0 else "metric-val-negative"
                            sign = "+" if (value >= 0 and is_pct and value != 0) else ""
                            disp_val = f"{sign}{value * 100:.1f}%" if is_pct else f"{value:.1f}"
                            col.markdown(f"""
                            <div class="metric-card">
                                <div class="metric-label">{label}</div>
                                <div class="metric-val {trend_class}">{disp_val}</div>
                                <div class="metric-sub">{sub_text}</div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                        render_sim_kpi(k1, "Average Return", avg_ret, "Weighted portfolio return", True)
                        render_sim_kpi(k2, "Win Rate", win_rate, "Percentage of positive trades", True)
                        render_sim_kpi(k3, "Avg Holding Period", avg_hold, "Average days held in trade", False)
                        
                        # Exit reason breakdown string
                        exit_reason_str = "<br>".join([f"• {k}: {v}" for k, v in reasons_counts.items()])
                        k4.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-label">Exit Reasons</div>
                            <div class="metric-sub" style="font-size:0.9rem; color:#ffffff; line-height:1.2; padding-top:5px;">{exit_reason_str}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Detailed table
                        st.subheader("📋 Trade Simulation Performance Breakdown")
                        
                        df_display = df_res.copy()
                        df_display['Return'] = df_display['Return'].apply(lambda x: f"{float(x)*100:+.1f}%")
                        df_display['Entry_Price'] = df_display['Entry_Price'].apply(lambda x: f"₹{float(x):,.2f}")
                        df_display['Exit_Price'] = df_display['Exit_Price'].apply(lambda x: f"₹{float(x):,.2f}")
                        df_display['Rebound_Score'] = df_display['Rebound_Score'].apply(lambda x: f"{float(x):.1f}" if pd.notna(x) else "—")
                        df_display['Rank_Score'] = df_display['Rank_Score'].apply(lambda x: f"{float(x):.1f}" if pd.notna(x) else "—")
                        
                        st.dataframe(df_display[[
                            'Symbol', 'Sector', 'Rebound_Score', 'Rank_Score', 
                            'Entry_Date', 'Entry_Price', 'Exit_Date', 'Exit_Price', 
                            'Return', 'Holding_Days', 'Exit_Reason', 'Double_Bottom_Stage'
                        ]], use_container_width=True, hide_index=True)
                        
                        # Explanation dropdown cards (mimicking Excel justifications)
                        st.subheader("🔍 Stock Analysis Trade Explanations (Excel-Grade Details)")
                        
                        for idx, row in df_res.iterrows():
                            # Highlight the return in title
                            with st.expander(f"📘 {row['Symbol']} ({row['Entry_Date']}) - Rebound Score: {row['Rebound_Score']:.1f} | Stage: {row['Double_Bottom_Stage']} | Return: {row['Return']*100:+.1f}%"):
                                col_exp1, col_exp2 = st.columns(2)
                                col_exp1.markdown(f"**Sector:** {row['Sector']}")
                                col_exp1.markdown(f"**Entry:** {row['Entry_Date']} @ ₹{row['Entry_Price']:.2f}")
                                col_exp1.markdown(f"**Exit:** {row['Exit_Date']} @ ₹{row['Exit_Price']:.2f} ({row['Exit_Reason']})")
                                col_exp1.markdown(f"**Holding Period:** {row['Holding_Days']} trading days")
                                
                                col_exp2.markdown(f"**Fundamental Setup (Layer 1):** {row['L1_Explanation']}")
                                col_exp2.markdown(f"**Technical Trend (Layer 2):** {row['L2_Explanation']}")
                                col_exp2.markdown(f"**Statistical Monte Carlo (Layer 3):** {row['L3_Explanation']}")
