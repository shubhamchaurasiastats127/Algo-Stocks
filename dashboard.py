import streamlit as st
import pandas as pd
import numpy as np
import yaml
import json
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
# Sidebar Panel (Decluttered & Premium)
# ---------------------------------------------------------------------------

st.sidebar.image("https://img.icons8.com/nolan/96/combo-chart.png", width=60)
st.sidebar.title("Algo_Stocks Engine")
st.sidebar.markdown("---")

# Quick DB connection status
db_status = "🔴 Disconnected"
mysql_connected = False
try:
    import mysql.connector
    conn = mysql.connector.connect(**config['mysql'])
    conn.close()
    db_status = "🟢 MySQL Connected"
    mysql_connected = True
except Exception:
    import os
    if os.path.exists("data/stock_cache.db"):
        db_status = "🟡 SQLite Cache Active"
    else:
        db_status = "🔴 DB Error"

st.sidebar.markdown(f"**Database Status:** {db_status}")

# Active configurations summary
st.sidebar.markdown("### Active Parameters")
st.sidebar.markdown(f"**Universe:** `{config['universe']['index']}`")
st.sidebar.markdown(f"**Buy Threshold:** `{config['thresholds']['buy']}`")
st.sidebar.markdown(f"**Target Profit:** `{config['thresholds']['target_profit_pct']*100:.1f}%`")
st.sidebar.markdown(f"**Stop Loss:** `{config['thresholds']['stop_loss_pct']*100:.1f}%`")

st.sidebar.markdown("---")
st.sidebar.caption("Update weights & thresholds in the **Strategy Optimizer** tab.")

# ---------------------------------------------------------------------------
# Helper Functions
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
        try:
            import sys
            import os
            src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src'))
            if src_path not in sys.path:
                sys.path.insert(0, src_path)
            import sqlite3
            from data_manager import SQLiteConnectionWrapper
            sqlite_path = "data/stock_cache.db"
            if os.path.exists(sqlite_path):
                conn = SQLiteConnectionWrapper(sqlite3.connect(sqlite_path))
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
        except Exception as sqlite_err:
            pass
            
        if not connected:
            st.warning(f"⚠️ Local MySQL database and SQLite cache not accessible. Falling back to Yahoo Finance...")
        
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
            data = yf.download(unique_yf_symbols, start=start_date_str, group_by='ticker', progress=False)
            
            for yf_sym in unique_yf_symbols:
                orig_sym = sym_map[yf_sym]
                symbol_prices[orig_sym] = []
                
                if isinstance(data.columns, pd.MultiIndex):
                    if yf_sym in data.columns.get_level_values(0):
                        df_sym = data[yf_sym]
                    else:
                        continue
                else:
                    df_sym = data
                        
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

        # Filter out trailing nan/none/empty headers and their corresponding columns
        valid_indices_all = [i for i, h in enumerate(headers_all) if str(h).lower() not in ('nan', 'none', '')]
        headers_all = [headers_all[i] for i in valid_indices_all]
        
        valid_indices_top10 = [i for i, h in enumerate(headers_top10) if str(h).lower() not in ('nan', 'none', '')]
        headers_top10 = [headers_top10[i] for i in valid_indices_top10]

        # Table 1: All Selections
        data_all = df_db.iloc[header_idx_all + 1 : idx_top10].copy().reset_index(drop=True)
        data_all = data_all[data_all[0].notna() & (data_all[0] != "Average") & (~data_all[0].astype(str).str.contains("Portfolio|Benchmark|Average", case=False))]
        data_all = data_all.iloc[:, valid_indices_all]
        data_all.columns = headers_all
        
        # Table 2: Top 10 Concentrated Selections
        data_top10 = df_db.iloc[header_idx_top10 + 1 :].copy().reset_index(drop=True)
        data_top10 = data_top10[data_top10[0].notna() & (data_top10[0] != "Average") & (~data_top10[0].astype(str).str.contains("Portfolio|Benchmark|Average", case=False))]
        data_top10 = data_top10.iloc[:, valid_indices_top10]
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

        if avg_row_all:
            avg_row_all = [avg_row_all[i] for i in valid_indices_all]
        if avg_row_top10:
            avg_row_top10 = [avg_row_top10[i] for i in valid_indices_top10]

        avg_data = {
            'all': dict(zip(headers_all, avg_row_all)) if avg_row_all else {},
            'top10': dict(zip(headers_top10, avg_row_top10)) if avg_row_top10 else {}
        }
        
        return data_all, data_top10, avg_data
    except Exception as e:
        st.error(f"Error reading performance dashboard: {e}")
        return None, None, None

# Load Excel data if exists
data_all, data_top10, avg_data = load_excel_data(EXCEL_PATH)

st.title("📈 Algo_Stocks Performance & Simulation Hub")
st.markdown("Track statistical model portfolios, configure system inputs, run simulated backtests, and understand the core rotation strategy.")

# Restructured Tabs
tab_portfolio, tab_backtester, tab_weekly_runner, tab_optimizer, tab_explanation = st.tabs([
    "📊 Overall Portfolio Performance", 
    "⚙️ Strategy Runner & Backtester", 
    "📅 Rolling Weekly Backtester",
    "🔧 Strategy Optimizer",
    "📚 In-Depth Strategy Manual"
])

# ---------------------------------------------------------------------------
# Tab 1: Overall Portfolio Performance
# ---------------------------------------------------------------------------
with tab_portfolio:
    if data_all is None or data_top10 is None:
        st.warning("⚠️ No performance results found. Go to 'Strategy Runner & Backtester' to execute simulation backtests.")
    else:
        st.subheader("Performance Highlights (Avg. Weekly Horizon Returns)")
        
        # Extract averages safely (1W, 2W, 3W, 4W)
        avg_p_all = avg_data['all'].get('4 Weeks', 0.0)
        if type(avg_p_all) == str or pd.isna(avg_p_all):
            avg_p_all = avg_data['all'].get('3 Weeks', 0.0)
            if type(avg_p_all) == str or pd.isna(avg_p_all):
                avg_p_all = avg_data['all'].get('2 Weeks', 0.0)
        
        avg_p_top10 = avg_data['top10'].get('4 Weeks', 0.0)
        if type(avg_p_top10) == str or pd.isna(avg_p_top10):
            avg_p_top10 = avg_data['top10'].get('3 Weeks', 0.0)
            if type(avg_p_top10) == str or pd.isna(avg_p_top10):
                avg_p_top10 = avg_data['top10'].get('2 Weeks', 0.0)
            
        n50_avg = avg_data['all'].get('Nifty 50', 0.0)
        n500_avg = avg_data['all'].get('Nifty 500', 0.0)
        
        col1, col2, col3, col4 = st.columns(4)
        
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

        st.subheader("📈 Simulated Return Progression over 4 Weeks")
        
        # Prep weekly values for line chart plotting
        weeks = ["1 Week", "2 Weeks", "3 Weeks", "4 Weeks"]
        
        curve_all = []
        curve_top10 = []
        
        for w in weeks:
            vals = []
            if w in data_all.columns:
                for val in data_all[w].values:
                    if is_numeric(val):
                        vals.append(float(val))
            curve_all.append(np.mean(vals) * 100 if vals else None)
            
            vals_t = []
            if w in data_top10.columns:
                for val in data_top10[w].values:
                    if is_numeric(val):
                        vals_t.append(float(val))
            curve_top10.append(np.mean(vals_t) * 100 if vals_t else None)
            
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=["Start"] + weeks, y=[0.0] + curve_top10, name="Concentrated (Top 10 Picks)", line=dict(color="#10b981", width=3.5), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=["Start"] + weeks, y=[0.0] + curve_all, name="Full Rebound Portfolio", line=dict(color="#6366f1", width=2.5), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=["Start", "4 Weeks"], y=[0.0, float(n50_avg) * 100], name="Nifty 50 Index (Benchmark)", line=dict(color="#f59e0b", width=2, dash='dash'), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=["Start", "4 Weeks"], y=[0.0, float(n500_avg) * 100], name="Nifty 500 Index (Benchmark)", line=dict(color="#ef4444", width=2, dash='dot'), mode='lines+markers'))
        
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

        st.subheader("📋 Performance Tables")
        
        st.write("**Concentrated Portfolio Summary (Top 10 Picks)**")
        disp_top10 = data_top10.copy()
        for col in weeks + ['Nifty 50', 'Nifty 500', 'Outperform vs N50', 'Outperform vs N500']:
            if col in disp_top10.columns:
                disp_top10[col] = disp_top10[col].apply(lambda x: f"{float(x)*100:+.1f}%" if (pd.notna(x) and not isinstance(x, str) and x != "—") else "—")
        st.dataframe(disp_top10, use_container_width=True, hide_index=True)
        
        st.write("**Full Rebound Portfolio Summary (All Picks)**")
        disp_all = data_all.copy()
        for col in weeks + ['Nifty 50', 'Nifty 500', 'Outperform vs N50', 'Outperform vs N500']:
            if col in disp_all.columns:
                disp_all[col] = disp_all[col].apply(lambda x: f"{float(x)*100:+.1f}%" if (pd.notna(x) and not isinstance(x, str) and x != "—") else "—")
        st.dataframe(disp_all, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 2: Strategy Runner & Backtester
# ---------------------------------------------------------------------------
with tab_backtester:
    # Set up sub-tabs
    run_mode = st.radio("Select Action:", ["🔮 Predict & Recommendation (Any Date)", "⚙️ Run Backtest Pipeline", "💰 Exit Strategy Simulator"], horizontal=True)
    
    # ── Sub-Tab 1: Single Date Prediction ──
    if run_mode == "🔮 Predict & Recommendation (Any Date)":
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
                st.info(f"Analysis completed. Now automatically calculating backtest performance returns for {date_str}...")
                
                # Setup tracker command parameters
                tracker_cmd = [
                    sys.executable, 
                    "backtest/performance_tracker.py", 
                    "--dates", date_str,
                    "--entry-threshold", str(config['thresholds'].get('buy', 70.0)),
                    "--top-n", str(config['thresholds'].get('top_n', 10)),
                ]
                # If there's an anchor date in session state, we can use it, else default to today
                anchor_dt = st.session_state.get('pipeline_today_date')
                if anchor_dt:
                    tracker_cmd.extend(["--today-date", anchor_dt.strftime("%Y-%m-%d")])
                else:
                    tracker_cmd.extend(["--today-date", datetime.now().strftime("%Y-%m-%d")])
                
                tracker_process = subprocess.Popen(
                    tracker_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=os.getcwd()
                )
                
                while True:
                    line = tracker_process.stdout.readline()
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
                    
                tracker_process.wait()
                
                if tracker_process.returncode == 0:
                    st.success(f"✅ Analysis and Backtesting Performance for {date_str} completed successfully!")
                    st.session_state[f"loaded_{date_clean}"] = True
                    load_results = True
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"❌ Performance tracking failed with exit code: {tracker_process.returncode}")
            else:
                st.error(f"❌ Analysis failed with exit code: {process.returncode}")

        if load_results and os.path.exists(picks_csv) and os.path.exists(sector_json):
            with open(sector_json, "r") as f:
                sec_data = json.load(f)
            df_picks = pd.read_csv(picks_csv)
            
            st.markdown("---")
            st.header("🏢 Sector Selection & Justifications")
            st.markdown(f"**India VIX:** `{sec_data.get('vix', 0.0):.2f}`")
            
            selected_indices = sec_data.get('selected_indices', [])
            justifications = sec_data.get('justifications', {})
            all_scores = sec_data.get('all_scores', {})
            oversold_highlights = sec_data.get('oversold_highlights', {})
            rejected_sectors = sec_data.get('rejected_sectors', [])
            
            st.subheader("Selected Sectors Summary")
            
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
                
            st.subheader("Detailed Sector Rotation Rationale")
            for i, idx in enumerate(selected_indices):
                score_dict = all_scores.get(idx, {})
                comp_score = score_dict.get('composite', 0.0)
                with st.expander(f"💼 {idx} - Score: {comp_score:.1f} | Rotation & Economic Rationale"):
                    st.markdown("**Rotational/Macro Justification:**")
                    st.info(justifications.get(idx, "No justification details available."))
                    
                    st.markdown("**Rotational Factors Breakdown (Scores: 0-100):**")
                    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
                    col_f1.metric("A. Econ Rotation", f"{score_dict.get('score_A', 0):.0f}")
                    col_f2.metric("B. Seasonality", f"{score_dict.get('score_B', 0):.0f}")
                    col_f3.metric("C. Technicals", f"{score_dict.get('score_C', 0):.0f}")
                    col_f4.metric("D. Fundamentals", f"{score_dict.get('score_D', 0):.0f}")
                    col_f5.metric("E. Policy/Macro", f"{score_dict.get('score_E', 0):.0f}")
                    
                    highlights = oversold_highlights.get(idx, [])
                    if highlights:
                        st.markdown(f"**Top Oversold Constituents in {idx}:**")
                        df_hl = pd.DataFrame(highlights)
                        if not df_hl.empty:
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
                            }
                            df_hl_disp = df_hl.rename(columns=col_map)
                            disp_cols = [c for c in col_map.values() if c in df_hl_disp.columns]
                            
                            for c in ['Price (₹)']:
                                if c in df_hl_disp.columns:
                                    df_hl_disp[c] = df_hl_disp[c].apply(lambda x: f"₹{x:,.2f}" if pd.notna(x) else "—")
                            for c in ['Rebound Score', 'RSI (14D)', 'PE Ratio', 'ROE (%)', 'Revenue Growth (%)', '% from 52W High', '% from 52W Low']:
                                if c in df_hl_disp.columns:
                                    df_hl_disp[c] = df_hl_disp[c].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
                                    
                            st.dataframe(df_hl_disp[disp_cols], use_container_width=True, hide_index=True)
                    else:
                        st.warning("No oversold constituents highlighted for this sector.")
                        
            if rejected_sectors:
                with st.expander("🚫 Reviewed Sectors Not Selected"):
                    df_rej = pd.DataFrame(rejected_sectors, columns=["Index Name", "Reason for Rejection"])
                    st.dataframe(df_rej, use_container_width=True, hide_index=True)
                    
            st.markdown("---")
            st.header("🎯 Stock Analysis Recommendations")
            
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
                        
                        st.markdown("**Rebound/Technical metrics:**")
                        rm1, rm2, rm3 = st.columns(3)
                        rm1.metric("RSI (14D)", f"{row['RSI']:.1f}" if pd.notna(row['RSI']) else "—")
                        rm2.metric("% above 52W Low", f"{row['Pct_From_52W_Low']:.1f}%" if pd.notna(row['Pct_From_52W_Low']) else "—")
                        rm3.metric("52W Low Price", f"₹{row['52W_Low']:.2f}" if pd.notna(row['52W_Low']) else "—")
                        
                        st.markdown("**Fundamental metrics:**")
                        fm1, fm2, fm3 = st.columns(3)
                        fm1.metric("PE Ratio", f"{row.get('PE_Ratio', 0.0):.1f}" if pd.notna(row.get('PE_Ratio')) else "—")
                        fm2.metric("ROE (%)", f"{row.get('ROE', 0.0):.1f}%" if pd.notna(row.get('ROE')) else "—")
                        fm3.metric("Rev Growth (%)", f"{row.get('Revenue_Growth_Pct', 0.0):.1f}%" if pd.notna(row.get('Revenue_Growth_Pct')) else "—")

                        st.markdown("---")
                        st.markdown("**Execution Layer Justifications:**")
                        col_exp2.markdown(f"**Layer 1 (Fundamentals):** {row['L1_Reasoning']}")
                        col_exp2.markdown(f"**Layer 2 (Technical Trend):** {row['L2_Reasoning']}")
                        col_exp2.markdown(f"**Layer 3 (Statistical Edge):** {row['L3_Reasoning']}")

    # ── Sub-Tab 2: Run Backtest Pipeline ──
    elif run_mode == "⚙️ Run Backtest Pipeline":
        st.subheader("⚙️ Run Pipeline Backtesting Simulations")
        st.markdown("Trigger full simulation runs over multiple dates. This runs Monte Carlo simulations and scans multiple stocks, computing 1, 2, 3, and 4 week forward returns.")
        
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
        
        log_placeholder = st.empty()
        
        if run_backtest_btn:
            st.info("Initiating backtesting subprocess... Running simulation dates.")
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
                st.success("✅ Backtest simulation completed successfully! Next, run the performance analysis to update Excel dashboard.")
            else:
                st.error(f"❌ Subprocess failed with exit code: {process.returncode}")
                
        if run_perf_btn:
            st.info("Initiating performance tracker subprocess...")
            
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
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"❌ Subprocess failed with exit code: {process.returncode}")

        # Inline dashboard & date inspector
        cache_json_path = "output/backtest/latest_results_cache.json"
        if os.path.exists(cache_json_path):
            try:
                with open(cache_json_path, "r") as f:
                    res_cache = json.load(f)
                
                st.markdown("---")
                st.subheader("📊 Latest Backtest Simulation Results (Inline Dashboard)")
                
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
                            rets_all = [s['Returns'].get(f'M{m_len}') for s in stocks if s['Returns'].get(f'M{m_len}') is not None]
                            if rets_all:
                                portfolio_final_returns.append(np.mean(rets_all))
                                
                            rets_top = [s['Returns'].get(f'M{m_len}') for s in stocks if s.get('In_Top10') and s['Returns'].get(f'M{m_len}') is not None]
                            if rets_top:
                                top_final_returns.append(np.mean(rets_top))
                                
                            n50_ret = benchmarks.get('Nifty 50', {}).get('returns', {}).get(f'M{m_len}')
                            if n50_ret is not None:
                                n50_final_returns.append(n50_ret)
                                
                            n500_ret = benchmarks.get('Nifty 500', {}).get('returns', {}).get(f'M{m_len}')
                            if n500_ret is not None:
                                n500_final_returns.append(n500_ret)
                    
                    avg_full = np.mean(portfolio_final_returns) if portfolio_final_returns else 0.0
                    avg_top = np.mean(top_final_returns) if top_final_returns else 0.0
                    avg_n50 = np.mean(n50_final_returns) if n50_final_returns else 0.0
                    
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
                    render_inline_kpi(rk2, f"Concentrated Avg Return", avg_top, "Average return of top picks")
                    render_inline_kpi(rk3, "Nifty 50 Index Return", avg_n50, "Benchmark average return")
                    
                    alpha_val = avg_top - avg_n50
                    render_inline_kpi(rk4, "Concentrated Alpha vs N50", alpha_val, "Outperformance margin")
                    
                    st.subheader("📈 Cumulative Forward Return Trajectory")
                    
                    weeks_labels = ["1 Week", "2 Weeks", "3 Weeks", "4 Weeks"]
                    weeks_keys = ["M1", "M2", "M3", "M4"]
                    curve_full_y = []
                    curve_top_y = []
                    
                    for m in weeks_keys:
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
                    valid_weeks_top = [weeks_labels[i] for i in range(len(curve_top_y)) if curve_top_y[i] is not None]
                    valid_vals_top = [val for val in curve_top_y if val is not None]
                    if valid_vals_top:
                        fig_inline.add_trace(go.Scatter(x=["Start"] + valid_weeks_top, y=[0.0] + valid_vals_top, 
                                                        name="Concentrated Portfolio", line=dict(color="#10b981", width=3.5), mode='lines+markers'))
                    
                    valid_weeks_full = [weeks_labels[i] for i in range(len(curve_full_y)) if curve_full_y[i] is not None]
                    valid_vals_full = [val for val in curve_full_y if val is not None]
                    if valid_vals_full:
                        fig_inline.add_trace(go.Scatter(x=["Start"] + valid_weeks_full, y=[0.0] + valid_vals_full, 
                                                        name="Full Rebound Portfolio", line=dict(color="#6366f1", width=2.5), mode='lines+markers'))
                    
                    fig_inline.add_trace(go.Scatter(x=["Start", "4 Weeks"], y=[0.0, avg_n50 * 100], name="Nifty 50 Index (Benchmark)", line=dict(color="#f59e0b", width=2, dash='dash'), mode='lines+markers'))
                    
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
                    
                    st.subheader("📋 Detailed Simulation Runs Inspector")
                    selected_run_date = st.selectbox("Select Run Date to Inspect:", dates_keys, key="run_date_selector_inline")
                    
                    if selected_run_date:
                        run_data = res_cache[selected_run_date]
                        stocks = run_data.get('stocks', [])
                        m_dates = run_data.get('dates', [])
                        
                        df_stocks = pd.DataFrame(stocks)
                        
                        if not df_stocks.empty:
                            disp_cols = ['Symbol', 'Sector', 'Rebound_Score', 'Final_Rank_Score', 'Double_Bottom_Stage', 'Entry_Date', 'Entry_Price']
                            
                            df_table = df_stocks.copy()
                            df_table['Entry_Price'] = df_table['Entry_Price'].apply(lambda x: f"₹{float(x):,.2f}")
                            df_table['Rebound_Score'] = df_table['Rebound_Score'].apply(lambda x: f"{float(x):.1f}")
                            df_table['Final_Rank_Score'] = df_table['Final_Rank_Score'].apply(lambda x: f"{float(x):.1f}")
                            
                            for m_idx in range(1, len(m_dates) + 1):
                                col_name = f'Week {m_idx} Return'
                                df_table[col_name] = df_stocks['Returns'].apply(lambda r: f"{r.get(f'M{m_idx}')*100:+.1f}%" if r.get(f'M{m_idx}') is not None else "—")
                                disp_cols.append(col_name)
                                
                            df_table = df_table.sort_values('Final_Rank_Score', ascending=False)
                            st.dataframe(df_table[disp_cols], use_container_width=True, hide_index=True)
                            
                            st.subheader("🔍 Stock Analysis Trade Explanations (Excel-Grade Details)")
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

    # ── Sub-Tab 2: Run Backtest Pipeline ──
    elif run_mode == "⚙️ Run Backtest Pipeline":
        st.subheader("⚙️ Run Pipeline Backtesting Simulations")
        st.markdown("Trigger full simulation runs. Note that running full simulations involves CPU-heavy Monte Carlo simulations and scans multiple stocks. Progress will be displayed in real time below.")
        
        with st.expander("🛠️ Backtest Parameters & Configurations", expanded=True):
            col_inp1, col_inp2 = st.columns(2)
            bt_dates_str = col_inp1.text_area("Backtest Dates (Comma-separated YYYY-MM-DD):", 
                                              value="2025-12-07, 2026-01-07, 2026-02-07, 2026-03-07, 2026-04-07, 2026-05-07",
                                              help="Dates to execute historical scans and score generation.")
            
            entry_threshold = col_inp2.slider("Entry Score Threshold (Rebound Score):", min_value=30.0, max_value=95.0, value=70.0, step=5.0, key="pipeline_entry_threshold")
            top_n = col_inp2.slider("Concentrated Portfolio Size (Top N picks):", min_value=3, max_value=20, value=10, step=1, key="pipeline_top_n")
            
            today_date_anchor = col_inp1.date_input("Today's Date Anchor:", value=datetime(2026, 6, 7).date(), key="pipeline_today_date")
            limit_per_index = col_inp2.number_input("Limit constituents per Index (optional, 0 for unlimited):", min_value=0, value=0, step=1, key="pipeline_limit_index")
            
        col_bt1, col_bt2 = st.columns(2)
        
        run_backtest_btn = col_bt1.button("🏃‍♂️ Run Full Backtest Simulation Pipeline", use_container_width=True, key="pipeline_run_btn")
        run_perf_btn = col_bt2.button("📊 Update Performance Analysis & Report", use_container_width=True, key="pipeline_perf_btn")
        
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
                    
                    # We need to construct week-by-week averages across all run dates (using 4 weeks)
                    weeks_list = ["M1", "M2", "M3", "M4"]
                    curve_full_y = []
                    curve_top_y = []
                    
                    for m in weeks_list:
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
                    valid_weeks_top = [f"Week {i+1}" for i in range(len(curve_top_y)) if curve_top_y[i] is not None]
                    valid_vals_top = [val for val in curve_top_y if val is not None]
                    if valid_vals_top:
                        fig_inline.add_trace(go.Scatter(x=["Start"] + valid_weeks_top, y=[0.0] + valid_vals_top, 
                                                        name="Concentrated Portfolio", line=dict(color="#10b981", width=3.5), mode='lines+markers'))
                    
                    valid_weeks_full = [f"Week {i+1}" for i in range(len(curve_full_y)) if curve_full_y[i] is not None]
                    valid_vals_full = [val for val in curve_full_y if val is not None]
                    if valid_vals_full:
                        fig_inline.add_trace(go.Scatter(x=["Start"] + valid_weeks_full, y=[0.0] + valid_vals_full, 
                                                        name="Full Rebound Portfolio", line=dict(color="#6366f1", width=2.5), mode='lines+markers'))
                    
                    fig_inline.add_trace(go.Scatter(x=["Start", f"Week {len(dates_keys)}"], y=[0.0, avg_n50 * 100], name="Nifty 50 Index (Benchmark)", line=dict(color="#f59e0b", width=2, dash='dash'), mode='lines+markers'))
                    
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
                            df_table['Entry_Price'] = df_table['Entry_Price'].apply(lambda x: f"₹{float(x):,.2f}")
                            df_table['Rebound_Score'] = df_table['Rebound_Score'].apply(lambda x: f"{float(x):.1f}")
                            df_table['Final_Rank_Score'] = df_table['Final_Rank_Score'].apply(lambda x: f"{float(x):.1f}")
                            
                            # Add week-by-week return columns dynamically
                            for m_idx in range(1, len(m_dates) + 1):
                                col_name = f'Week {m_idx} Return'
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

    # ── Sub-Tab 3: Custom Trade Simulator ──
    elif run_mode == "💰 Exit Strategy Simulator":
        st.subheader("💰 Exit Strategy Simulator & Exit Trigger Backtester")
        st.markdown("Initiate simulation runs on specific backtesting dates with your own stop loss and profit targets, modeling when trades would trigger exits.")
        
        if not os.path.exists(EXCEL_PATH):
            st.warning("⚠️ No simulation report found to load dates.")
        else:
            xl = pd.ExcelFile(EXCEL_PATH)
            sheet_names = [s for s in xl.sheet_names if s != "Dashboard"]
            
            col_sim1, col_sim2 = st.columns(2)
            
            sim_dates = col_sim1.multiselect("Choose Initiation Dates:", sheet_names, default=sheet_names, key="sim_dates_select")
            
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
                            picks_df = picks_df[(picks_df['Rebound_Score'] >= 70) | (picks_df['Flag_OVERSOLD'] == 'YES')].copy()
                            if picks_df.empty:
                                picks_df = picks_df.sort_values('Rebound_Score', ascending=False).head(20).copy()
                        else:
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
                        
                        results = run_trade_simulation(combined_picks, stop_loss_pct, target_profit_pct, horizon_days, config['mysql'])
                        
                        if not results:
                            st.warning("No price data found to run simulation.")
                        else:
                            df_res = pd.DataFrame(results)
                            
                            avg_ret = df_res['Return'].mean()
                            win_rate = (df_res['Return'] > 0).mean()
                            avg_hold = df_res['Holding_Days'].mean()
                            reasons_counts = df_res['Exit_Reason'].value_counts()
                            
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
                            
                            exit_reason_str = "<br>".join([f"• {k}: {v}" for k, v in reasons_counts.items()])
                            k4.markdown(f"""
                            <div class="metric-card">
                                <div class="metric-label">Exit Reasons</div>
                                <div class="metric-sub" style="font-size:0.9rem; color:#ffffff; line-height:1.2; padding-top:5px;">{exit_reason_str}</div>
                            </div>
                            """, unsafe_allow_html=True)
                            
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
                            
                            st.subheader("🔍 Stock Analysis Trade Explanations (Excel-Grade Details)")
                            for idx, row in df_res.iterrows():
                                with st.expander(f"📘 {row['Symbol']} ({row['Entry_Date']}) - Rebound Score: {row['Rebound_Score']:.1f} | Stage: {row['Double_Bottom_Stage']} | Return: {row['Return']*100:+.1f}%"):
                                    col_exp1, col_exp2 = st.columns(2)
                                    col_exp1.markdown(f"**Sector:** {row['Sector']}")
                                    col_exp1.markdown(f"**Entry:** {row['Entry_Date']} @ ₹{row['Entry_Price']:.2f}")
                                    col_exp1.markdown(f"**Exit:** {row['Exit_Date']} @ ₹{row['Exit_Price']:.2f} ({row['Exit_Reason']})")
                                    col_exp1.markdown(f"**Holding Period:** {row['Holding_Days']} trading days")
                                    
                                    col_exp2.markdown(f"**Fundamental Setup (Layer 1):** {row['L1_Explanation']}")
                                    col_exp2.markdown(f"**Technical Trend (Layer 2):** {row['L2_Explanation']}")
                                    col_exp2.markdown(f"**Statistical Monte Carlo (Layer 3):** {row['L3_Explanation']}")

# ---------------------------------------------------------------------------
# Tab 2.5: Rolling Weekly Backtester
# ---------------------------------------------------------------------------
with tab_weekly_runner:
    st.subheader("📅 Rolling Weekly Walk-Forward Backtester")
    st.markdown("Evaluate portfolio returns week-by-week going backward in time, comparing **Top 5, Top 10, Top 15, and All** picks against Nifty 50 and Nifty 500 indexes.")
    
    col_w1, col_w2 = st.columns([1, 2])
    weekly_anchor = col_w1.date_input("Starting Anchor Date:", value=datetime(2026, 6, 1).date(), key="weekly_anchor_date")
    weekly_months = col_w2.slider("Lookback Horizon (Months):", min_value=1, max_value=36, value=2, step=1, key="weekly_lookback_months")
    
    run_weekly_btn = st.button("▶️ Run Walk-Forward Backtest", key="run_weekly_backtest_button")
    
    # Check session state for existing results
    if "weekly_backtest_results" not in st.session_state:
        st.session_state.weekly_backtest_results = None
        
    if run_weekly_btn:
        import datetime as dt_module
        from datetime import date as dt_date, timedelta
        import glob
        import shutil
        from backtest.backtest_engine import BacktestStockAnalysisEngine
        from backtest_selector import BacktestSectorSelector
        
        # Calculate target weekly dates going backward
        target_dates = []
        curr_date = weekly_anchor
        # Estimate end date
        end_date = weekly_anchor - timedelta(days=weekly_months * 30)
        while curr_date >= end_date:
            # Current local date is 2026-06-21
            if curr_date <= dt_module.date(2026, 6, 21):
                target_dates.append(curr_date)
            curr_date -= timedelta(days=7)
            
        if not target_dates:
            st.error("No valid backtest dates found within lookback horizon prior to today's date.")
        else:
            progress_bar = st.progress(0.0)
            status_text = st.empty()
            
            # Setup benchmark data helper
            status_text.text("Reconstructing benchmark indexes...")
            min_date = min(target_dates) - timedelta(days=15)
            days_to_reconstruct = (dt_module.date(2026, 6, 21) - min_date).days + 30
            
            nifty50_prices = {}
            nifty500_prices = {}
            try:
                selector = BacktestSectorSelector(config, dt_module.date(2026, 6, 21))
                n50_series = selector._reconstruct_index("Nifty 50", days=days_to_reconstruct)
                if not n50_series.empty:
                    nifty50_prices = {d.date(): float(v) for d, v in n50_series.items()}
                n500_series = selector._reconstruct_index("Nifty 500", days=days_to_reconstruct)
                if not n500_series.empty:
                    nifty500_prices = {d.date(): float(v) for d, v in n500_series.items()}
            except Exception as e:
                status_text.text(f"Index reconstruction error: {e}. Falling back to yfinance...")
                
            # yfinance fallbacks if needed
            if not nifty50_prices or not nifty500_prices:
                import yfinance as yf
                try:
                    df_n50 = yf.download("^NSEI", start=min_date, end=dt_module.date(2026, 6, 22), progress=False)
                    if not df_n50.empty:
                        if isinstance(df_n50.columns, pd.MultiIndex):
                            df_n50.columns = df_n50.columns.get_level_values(0)
                        nifty50_prices.update({dt.date(): float(row['Close']) for dt, row in df_n50.iterrows()})
                except Exception:
                    pass
                try:
                    df_n500 = yf.download("^CRSLDX", start=min_date, end=dt_module.date(2026, 6, 22), progress=False)
                    if not df_n500.empty:
                        if isinstance(df_n500.columns, pd.MultiIndex):
                            df_n500.columns = df_n500.columns.get_level_values(0)
                        nifty500_prices.update({dt.date(): float(row['Close']) for dt, row in df_n500.iterrows()})
                except Exception:
                    pass
            
            weekly_results = []
            
            for i, T_date in enumerate(target_dates):
                date_str = T_date.strftime('%Y%m%d')
                status_text.text(f"Processing week {i+1}/{len(target_dates)}: {T_date.strftime('%Y-%m-%d')}...")
                
                # Check for cached picks
                picks_csv = f"output/backtest/run_{date_str}/picks.csv"
                if os.path.exists(picks_csv):
                    df_picks = pd.read_csv(picks_csv)
                else:
                    try:
                        engine = BacktestStockAnalysisEngine("config/config.yaml", T_date)
                        df_picks = engine.run(limit=None, run_name=f"run_{date_str}")
                        if not df_picks.empty:
                            out_dir = f"output/backtest/run_{date_str}"
                            os.makedirs(out_dir, exist_ok=True)
                            df_picks.to_csv(picks_csv, index=False)
                    except Exception as engine_err:
                        status_text.text(f"Error running engine for {T_date}: {engine_err}")
                        df_picks = pd.DataFrame()
                
                if df_picks.empty:
                    weekly_results.append({
                        'date': T_date,
                        'picks_count': 0,
                        'top5_ret': 0.0,
                        'top10_ret': 0.0,
                        'top15_ret': 0.0,
                        'all_ret': 0.0,
                        'n50_ret': 0.0,
                        'n500_ret': 0.0,
                        'picks_list': []
                    })
                    progress_bar.progress(float(i + 1) / len(target_dates))
                    continue
                
                # Filter where Action is BUY
                df_buys = df_picks[df_picks['Action'] == 'BUY'].copy()
                if df_buys.empty:
                    df_buys = df_picks.copy()
                
                # Sort by Final_Rank_Score descending
                df_buys = df_buys.sort_values('Final_Rank_Score', ascending=False)
                
                stock_returns = []
                for _, row in df_buys.iterrows():
                    sym = row['Symbol']
                    prices_list = []
                    conn = None
                    try:
                        import mysql.connector
                        conn = mysql.connector.connect(**config['mysql'])
                    except Exception:
                        try:
                            import sqlite3
                            from data_manager import SQLiteConnectionWrapper
                            conn = SQLiteConnectionWrapper(sqlite3.connect("data/stock_cache.db"))
                        except Exception:
                            pass
                    
                    if conn:
                        try:
                            cursor = conn.cursor()
                            query = "SELECT date, close FROM price_data WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date"
                            end_date_fetch = T_date + timedelta(days=10)
                            cursor.execute(query, (sym, T_date.strftime('%Y-%m-%d'), end_date_fetch.strftime('%Y-%m-%d')))
                            rows = cursor.fetchall()
                            for r in rows:
                                dt_val = r[0]
                                if isinstance(dt_val, str):
                                    d = datetime.strptime(dt_val, "%Y-%m-%d").date()
                                elif hasattr(dt_val, 'date'):
                                    d = dt_val.date()
                                else:
                                    d = dt_val
                                prices_list.append({'date': d, 'close': float(r[1])})
                            cursor.close()
                            conn.close()
                        except Exception:
                            if conn:
                                try: conn.close()
                                except Exception: pass
                                
                    if not prices_list:
                        import yfinance as yf
                        try:
                            df_sym = yf.download(f"{sym}.NS", start=T_date, end=T_date + timedelta(days=10), progress=False)
                            if not df_sym.empty:
                                if isinstance(df_sym.columns, pd.MultiIndex):
                                    df_sym.columns = df_sym.columns.get_level_values(0)
                                df_sym = df_sym.dropna(subset=['Close'])
                                for dt, r_s in df_sym.iterrows():
                                    prices_list.append({'date': dt.date(), 'close': float(r_s['Close'])})
                        except Exception:
                            pass
                    
                    if prices_list:
                        prices_list.sort(key=lambda x: x['date'])
                        entry_p = prices_list[0]['close']
                        exit_p = entry_p
                        exit_dt = prices_list[-1]['date']
                        target_exit = prices_list[0]['date'] + timedelta(days=7)
                        
                        df_week_prices = [p for p in prices_list if p['date'] <= target_exit]
                        if df_week_prices:
                            exit_p = df_week_prices[-1]['close']
                            exit_dt = df_week_prices[-1]['date']
                            
                        ret_1w = (exit_p - entry_p) / entry_p if entry_p > 0 else 0.0
                        stock_returns.append({
                            'Symbol': sym,
                            'Sector': row.get('Index_Name') or 'Other',
                            'Base_Rank_Score': row.get('Base_Rank_Score') or row.get('Final_Rank_Score'),
                            'Macro_Sentiment_Multiplier': row.get('Macro_Sentiment_Multiplier', 0.0),
                            'Systemic_Risk_Off': row.get('Systemic_Risk_Off', False),
                            'Combined_Score': row.get('Final_Rank_Score'),
                            'Entry_Date': prices_list[0]['date'],
                            'Entry_Price': entry_p,
                            'Exit_Date': exit_dt,
                            'Exit_Price': exit_p,
                            'Return': ret_1w
                        })
                
                # Reconstruct closest benchmark index prices
                actual_entry_dt = T_date
                actual_exit_dt = T_date + timedelta(days=7)
                if stock_returns:
                    actual_entry_dt = min(s['Entry_Date'] for s in stock_returns)
                    actual_exit_dt = max(s['Exit_Date'] for s in stock_returns)
                
                from performance_tracker import find_closest_date_price
                n50_entry, _ = find_closest_date_price(nifty50_prices, actual_entry_dt, direction='after')
                n50_exit, _ = find_closest_date_price(nifty50_prices, actual_exit_dt, direction='before')
                n500_entry, _ = find_closest_date_price(nifty500_prices, actual_entry_dt, direction='after')
                n500_exit, _ = find_closest_date_price(nifty500_prices, actual_exit_dt, direction='before')
                
                n50_ret = (n50_exit - n50_entry) / n50_entry if n50_entry and n50_exit else 0.0
                n500_ret = (n500_exit - n500_entry) / n500_entry if n500_entry and n500_exit else 0.0
                
                top5_ret = np.mean([s['Return'] for s in stock_returns[:5]]) if len(stock_returns) >= 1 else 0.0
                top10_ret = np.mean([s['Return'] for s in stock_returns[:10]]) if len(stock_returns) >= 1 else 0.0
                top15_ret = np.mean([s['Return'] for s in stock_returns[:15]]) if len(stock_returns) >= 1 else 0.0
                all_ret = np.mean([s['Return'] for s in stock_returns]) if len(stock_returns) >= 1 else 0.0
                
                # Save weekly Excel report
                weekly_excel_dir = f"output/backtest/run_{date_str}"
                os.makedirs(weekly_excel_dir, exist_ok=True)
                weekly_excel_path = os.path.join(weekly_excel_dir, "weekly_performance.xlsx")
                
                with pd.ExcelWriter(weekly_excel_path, engine='xlsxwriter') as wr:
                    summary_df = pd.DataFrame([{
                        'Week Start': T_date.strftime('%Y-%m-%d'),
                        'Week End': (T_date + timedelta(days=7)).strftime('%Y-%m-%d'),
                        'Top 5 Return': float(top5_ret),
                        'Top 10 Return': float(top10_ret),
                        'Top 15 Return': float(top15_ret),
                        'All Picks Return': float(all_ret),
                        'Nifty 50 Return': float(n50_ret),
                        'Nifty 500 Return': float(n500_ret),
                        'Picks Count': len(stock_returns)
                    }])
                    summary_df.to_excel(wr, sheet_name='Summary', index=False)
                    
                    if stock_returns:
                        detailed_df = pd.DataFrame(stock_returns)
                        detailed_df.to_excel(wr, sheet_name='Detailed Picks', index=False)
                
                weekly_results.append({
                    'date': T_date,
                    'picks_count': len(stock_returns),
                    'top5_ret': float(top5_ret) if not np.isnan(top5_ret) else 0.0,
                    'top10_ret': float(top10_ret) if not np.isnan(top10_ret) else 0.0,
                    'top15_ret': float(top15_ret) if not np.isnan(top15_ret) else 0.0,
                    'all_ret': float(all_ret) if not np.isnan(all_ret) else 0.0,
                    'n50_ret': float(n50_ret) if not np.isnan(n50_ret) else 0.0,
                    'n500_ret': float(n500_ret) if not np.isnan(n500_ret) else 0.0,
                    'picks_list': [s['Symbol'] for s in stock_returns]
                })
                
                progress_bar.progress(float(i + 1) / len(target_dates))
            
            st.session_state.weekly_backtest_results = weekly_results
            status_text.text("Backtest completed successfully!")
            progress_bar.empty()
            
    # Display Results
    if st.session_state.weekly_backtest_results is not None:
        weekly_results = st.session_state.weekly_backtest_results
        
        # Sort chronologically for charting and compounded calculations
        sorted_res = sorted(weekly_results, key=lambda x: x['date'])
        
        st.write("---")
        st.subheader("📊 Backtest Performance Breakdown")
        
        p_choice = st.radio("Select Portfolio Size for KPI Cards & Analysis:", ["Top 5", "Top 10", "Top 15", "All Picks"], horizontal=True, key="weekly_kpi_port_size")
        
        # Determine returns list based on selection
        port_ret_key = 'top5_ret' if p_choice == "Top 5" else ('top10_ret' if p_choice == "Top 10" else ('top15_ret' if p_choice == "Top 15" else 'all_ret'))
        
        port_returns = [w[port_ret_key] for w in sorted_res]
        n50_returns = [w['n50_ret'] for w in sorted_res]
        n500_returns = [w['n500_ret'] for w in sorted_res]
        
        # Compute compounded cumulative returns
        port_cum = np.cumprod(1 + np.array(port_returns)) - 1
        n50_cum = np.cumprod(1 + np.array(n50_returns)) - 1
        n500_cum = np.cumprod(1 + np.array(n500_returns)) - 1
        
        final_port_cum = port_cum[-1] if len(port_cum) > 0 else 0.0
        final_n50_cum = n50_cum[-1] if len(n50_cum) > 0 else 0.0
        final_n500_cum = n500_cum[-1] if len(n500_cum) > 0 else 0.0
        
        avg_weekly_port = np.mean(port_returns) if port_returns else 0.0
        avg_weekly_n50 = np.mean(n50_returns) if n50_returns else 0.0
        
        win_rate = np.mean([1 if r > 0 else 0 for r in port_returns]) if port_returns else 0.0
        
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        
        # KPI Card rendering
        def render_weekly_kpi(col, label, value, sub_text, is_pct=True, sign_pos=True):
            trend_class = "metric-val-positive" if value >= 0 else "metric-val-negative"
            sign = "+" if (value >= 0 and value != 0 and sign_pos) else ""
            val_str = f"{sign}{value * 100:.2f}%" if is_pct else f"{value:.2f}"
            col.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-val {trend_class}">{val_str}</div>
                <div class="metric-sub">{sub_text}</div>
            </div>
            """, unsafe_allow_html=True)
            
        render_weekly_kpi(col_k1, f"Portfolio ({p_choice}) Compounded", final_port_cum, "Total compounded return over horizon")
        render_weekly_kpi(col_k2, "Nifty 50 Compounded", final_n50_cum, "Benchmark compounded return")
        render_weekly_kpi(col_k3, "Average Weekly Return", avg_weekly_port, "Mean return of weekly trades")
        render_weekly_kpi(col_k4, "Weekly Win Rate", win_rate, "Ratio of positive weekly returns", is_pct=True, sign_pos=False)
        
        # Cumulative Compounded Returns Line Chart
        st.subheader("📈 Compounded Cumulative Performance Trajectory")
        
        dates_axis = [w['date'].strftime('%Y-%m-%d') for w in sorted_res]
        
        top5_cum = np.cumprod(1 + np.array([w['top5_ret'] for w in sorted_res])) - 1
        top10_cum = np.cumprod(1 + np.array([w['top10_ret'] for w in sorted_res])) - 1
        top15_cum = np.cumprod(1 + np.array([w['top15_ret'] for w in sorted_res])) - 1
        all_cum = np.cumprod(1 + np.array([w['all_ret'] for w in sorted_res])) - 1
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates_axis, y=top5_cum * 100, name="Top 5 Portfolio", line=dict(color="#10b981", width=3), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=dates_axis, y=top10_cum * 100, name="Top 10 Portfolio", line=dict(color="#3b82f6", width=2.5), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=dates_axis, y=top15_cum * 100, name="Top 15 Portfolio", line=dict(color="#8b5cf6", width=2), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=dates_axis, y=all_cum * 100, name="All Recommended Picks", line=dict(color="#ec4899", width=2), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=dates_axis, y=n50_cum * 100, name="Nifty 50 Index", line=dict(color="#f59e0b", width=2, dash='dash'), mode='lines+markers'))
        fig.add_trace(go.Scatter(x=dates_axis, y=n500_cum * 100, name="Nifty 500 Index", line=dict(color="#ef4444", width=2, dash='dot'), mode='lines+markers'))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94a3b8'),
            xaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Backtest Week"),
            yaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Compounded Cumulative Return (%)", ticksuffix="%"),
            margin=dict(l=20, r=20, t=10, b=10),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Weekly Performance Grid Table
        st.subheader("📋 Weekly Performance Summaries")
        
        table_rows = []
        for w in reversed(sorted_res):
            table_rows.append({
                'Date': w['date'].strftime('%Y-%m-%d'),
                'Picks Count': w['picks_count'],
                'Top 5 Return': f"{w['top5_ret']:+.2%}",
                'Top 10 Return': f"{w['top10_ret']:+.2%}",
                'Top 15 Return': f"{w['top15_ret']:+.2%}",
                'All Picks Return': f"{w['all_ret']:+.2%}",
                'Nifty 50': f"{w['n50_ret']:+.2%}",
                'Nifty 500': f"{w['n500_ret']:+.2%}",
                'Alpha vs N50 (Top 10)': f"{(w['top10_ret'] - w['n50_ret']):+.2%}",
                'Picks List': ", ".join(w['picks_list'][:10]) + ("..." if len(w['picks_list']) > 10 else "")
            })
            
        df_table = pd.DataFrame(table_rows)
        st.dataframe(df_table, use_container_width=True, hide_index=True)
        
        # Download Block
        st.write("---")
        st.subheader("📥 Download Weekly Performance Excel Reports")
        st.markdown("Select a target simulation date to download the detailed picks list (including Layer 1-3 scores, macro sentiment multipliers, and entry/exit price details).")
        
        week_options = [w['date'].strftime('%Y-%m-%d') for w in sorted_res]
        selected_download = st.selectbox("Choose Target Week:", week_options, key="select_download_weekly_run")
        
        if selected_download:
            date_clean = selected_download.replace('-', '')
            perf_excel = f"output/backtest/run_{date_clean}/weekly_performance.xlsx"
            import glob
            cons_excels = glob.glob(f"output/backtest/run_{date_clean}/Sector_Select_Consolidated_*.xlsx")
            
            col_dl1, col_dl2 = st.columns(2)
            if os.path.exists(perf_excel):
                with open(perf_excel, "rb") as f:
                    col_dl1.download_button(
                        label=f"📊 Download Weekly Return Performance ({selected_download})",
                        data=f.read(),
                        file_name=f"weekly_performance_{date_clean}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_dl_perf"
                    )
            if cons_excels:
                cons_excel = max(cons_excels, key=os.path.getmtime)
                with open(cons_excel, "rb") as f:
                    col_dl2.download_button(
                        label=f"📚 Download Full Sector & Selection Report ({selected_download})",
                        data=f.read(),
                        file_name=os.path.basename(cons_excel),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_dl_cons"
                    )

# ---------------------------------------------------------------------------
# Tab 3: Strategy Optimizer
# ---------------------------------------------------------------------------
with tab_optimizer:
    st.subheader("🔧 System Configuration & Strategy Optimizer")
    st.markdown("Adjust algorithmic scoring weights, buy/sell decision boundaries, and Monte Carlo engine constraints. Saving modifications updates `config/config.yaml`.")

    with st.form("opt_form"):
        # Section 1: Factor Weights
        st.write("### ⚖️ Multi-Factor Model Weights")
        st.markdown("The Two-Layer engine ranks constituent stocks by combining the core Multi-Layer Algorithm Score (70%) and the Rebound Potential Score (30%). Adjust the weights below to change how the Core Algorithm Score itself is calculated:")
        col_w1, col_w2, col_w3 = st.columns(3)
        w_fund = col_w1.slider("Layer 1: Fundamentals Weight", 0.0, 1.0, float(config['weights']['fundamentals']), 0.05, help="Weight given to profitability, balance sheet strength, and margins.")
        w_val = col_w2.slider("Layer 1: Valuation Weight", 0.0, 1.0, float(config['weights']['valuation']), 0.05, help="Weight given to relative undervaluation (P/E relative to industry/sector).")
        w_tech = col_w3.slider("Layer 2: Technical Trend Weight", 0.0, 1.0, float(config['weights']['technical_trend']), 0.05, help="Weight given to moving averages and trend strength.")
        w_pa = col_w1.slider("Layer 2: Price Action Weight", 0.0, 1.0, float(config['weights']['price_action']), 0.05, help="Weight given to short-term candlestick patterns and structure.")
        w_stat = col_w2.slider("Layer 3: Statistical Edge Weight", 0.0, 1.0, float(config['weights']['stat_edge']), 0.05, help="Weight given to historical win probabilities from Monte Carlo.")
        w_risk = col_w3.slider("Global: Risk Regime Weight", 0.0, 1.0, float(config['weights']['risk_regime']), 0.05, help="Weight given to volatility regime alignment (India VIX).")
        
        # Section 2: Decision Thresholds
        st.write("### 🛑 Decision Boundaries & Trade Parameters")
        st.markdown("Set the thresholds that trigger specific recommendations and trade execution boundaries:")
        col_t1, col_t2 = st.columns(2)
        t_buy = col_t1.number_input("Buy Score Threshold", 0, 100, int(config['thresholds']['buy']), help="Minimum combined score to trigger a BUY recommendation.")
        t_wait = col_t2.number_input("Wait Score Threshold", 0, 100, int(config['thresholds']['wait']), help="Score boundary to trigger a WAIT (hold/watch) stance.")
        t_avoid = col_t1.number_input("Avoid Score Threshold", 0, 100, int(config['thresholds']['avoid']), help="Score below which a stock is flagged as AVOID.")
        t_sell = col_t2.number_input("Sell Score Threshold", 0, 100, int(config['thresholds']['sell']), help="Score below which an active holding triggers a SELL.")
        
        stop_loss = col_t1.slider("Stop Loss Pct", 0.0, 0.30, float(config['thresholds']['stop_loss_pct']), 0.01, format="%.2f", help="Automatic stop loss boundary triggered in trade simulator.")
        target_profit = col_t2.slider("Target Profit Pct", 0.0, 0.50, float(config['thresholds']['target_profit_pct']), 0.01, format="%.2f", help="Automatic profit take boundary triggered in trade simulator.")

        # Section 3: Monte Carlo Simulation
        st.write("### 🎲 Monte Carlo Forecasting Settings")
        st.markdown("Tweak how the statistical forecasting engine projects future returns:")
        col_mc1, col_mc2 = st.columns(2)
        mc_iters = col_mc1.number_input("Iterations", 100, 20000, int(config['simulation']['iterations']), 100, help="Number of random price walks simulated per stock.")
        mc_horizon = col_mc2.number_input("Horizon Days", 5, 120, int(config['simulation']['horizon_days']), help="Forward holding period (in trading days) simulated.")
        mc_target = col_mc1.slider("Target Pct", 0.01, 0.25, float(config['simulation']['target_pct']), 0.005, format="%.3f", help="Target upside boundary for probability calculations.")
        mc_stop = col_mc2.slider("Stop Pct", 0.005, 0.1, float(config['simulation']['stop_pct']), 0.005, format="%.3f", help="Upside boundary for stop loss hit probabilities.")

        # Section 4: Universe & Filters
        st.write("### 🌌 Stock Selection Universe")
        col_u1, col_u2 = st.columns(2)
        u_idx = col_u1.selectbox("Universe Index", ["Nifty 500", "Nifty 200", "Nifty 100", "Nifty 50"], index=0)
        u_mcap = col_u2.number_input("Min Market Cap (Cr)", 100, 50000, int(config['universe']['min_market_cap_cr']))
        u_price = col_u1.number_input("Min Stock Price (₹)", 1, 10000, int(config['universe']['min_price']))
        u_vol = col_u2.number_input("Min 20D Avg Volume", 1000, 10000000, int(config['universe']['min_volume_20d_avg']), 10000)

        # Section 5: Double Bottom Setup
        st.write("### 📈 Double Bottom Pattern Tuning")
        col_db1, col_db2 = st.columns(2)
        db_lookback = col_db1.number_input("Double Bottom Lookback Days", 30, 252, int(config.get('double_bottom', {}).get('lookback_days', 150)))
        db_max_diff = col_db2.slider("Max Trough Difference Pct", 0.01, 0.15, float(config.get('double_bottom', {}).get('max_diff_pct', 0.05)), 0.01, format="%.2f", help="Maximum price divergence allowed between the two troughs.")
        db_min_bounce = col_db1.slider("Min Bounce to Confirm Pct", 0.005, 0.10, float(config.get('double_bottom', {}).get('min_bounce_pct', 0.02)), 0.005, format="%.3f", help="Minimum bounce from trough 2 to confirm accumulation.")
        db_min_peak_bounce = col_db2.slider("Min Peak Bounce Pct", 0.02, 0.25, float(config.get('double_bottom', {}).get('min_peak_bounce_pct', 0.07)), 0.01, format="%.2f", help="Minimum rebound from intermediate peak needed.")

        submit_btn = st.form_submit_button("💾 Save & Apply Configurations", use_container_width=True)
        
        if submit_btn:
            total_weight = w_fund + w_val + w_tech + w_pa + w_stat + w_risk
            if abs(total_weight - 1.0) > 0.001:
                st.error(f"❌ Save aborted! Total weights must sum to exactly 1.00 (Current: {total_weight:.2f})")
            else:
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
                
                if 'double_bottom' not in config:
                    config['double_bottom'] = {}
                config['double_bottom']['lookback_days'] = db_lookback
                config['double_bottom']['max_diff_pct'] = db_max_diff
                config['double_bottom']['min_bounce_pct'] = db_min_bounce
                config['double_bottom']['min_peak_bounce_pct'] = db_min_peak_bounce
                
                save_config(config)
                st.success("💾 Configuration updated successfully!")
                st.session_state.config = load_config()
                st.rerun()

# ---------------------------------------------------------------------------
# Tab 4: In-Depth Strategy Manual
# ---------------------------------------------------------------------------
with tab_explanation:
    st.subheader("📚 Quantitative Algorithmic Architecture & Execution Blueprint")
    st.markdown("This document describes the step-by-step math, filters, and logic that dictate how stocks are selected, ranked, and backtested in the **Algo_Stocks** pipeline.")
    
    st.markdown("---")
    
    st.write("### 🌐 Overview: The Three-Layer Quantitative Selector")
    st.markdown("""
    The strategy is built as an advanced **Three-Layer Selection Architecture** designed to buy deeply oversold quality stocks in supportive macroeconomic environments:
    1. **Layer 1: Sector Selection & Economic Rotation**: Identifies sector rotation cycles, seasonality, policy tailwinds, and VIX volatility to select the top 1-5 indices poised for a rebound.
    2. **Layer 2: Multi-Layer Stock Selection**: Screens and scores individual constituents inside the selected sectors, blending fundamental stability, technical patterns (like Double Bottoms), and statistical edge (via Monte Carlo forecasting) to generate initial recommendations.
    3. **Layer 3: Macro Factor Sentiment Filtering**: Google Trends analytics acts as the final gatekeeper. It monitors daily Indian macro and sector-specific search momentum. Hostile trends filter out candidates, supportive trends prioritize them, and systemic inflation/gold spikes trigger a protective portfolio beta-reduction regime.
    """)
    
    with st.expander("🏢 Layer 1: Rotational Sector Selection (6-Factor Scoring)", expanded=True):
        st.markdown("""
        All sector indices are scored dynamically on a scale of **0-100** based on six factors:
        - **Factor A: Economic Phase sector alignment (20% weight)**: Matches sectors against the current macroeconomic phase. Cyclical sectors (Infra, Metal, Realty) get higher scores during expansion, whereas defensive sectors (FMCG, Pharma) score higher in stagnation or recession.
        - **Factor B: Seasonality matrix (15% weight)**: Models historical monthly return probabilities. (e.g. Realty and IT have strong historical seasonals in Q4-Q1).
        - **Factor C: Technical oversold scoring (30% weight)**: Measures how deeply oversold the index is. Calculates distance from 52-week high, current price vs. SMA 200, and 14-day RSI (RSI between 25-45 scores highest).
        - **Factor D: Fundamental aggregates (20% weight)**: Aggregates median P/E, median ROE, and debt/equity ratios of all constituent stocks. Under-valued, high-quality indices score highest.
        - **Factor E: Policy & Macro drivers (15% weight)**: Dynamically parses interest rates, G-Sec yields, brent crude oil, monsoon status, credit growth, and China stimulus to reward sectors with operational tailwinds (e.g. rate cuts aid banks/realty, good monsoon aids FMCG/auto).
        - **Factor F: Correlation and VIX risk checks (Constraint)**:
          - **VIX Filter**: If India VIX > 22, the portfolio size is restricted to protect capital.
          - **Correlation check**: The engine ensures no two selected sectors have a historical correlation > 0.70. If they do, the lower-scoring sector is swapped for the next highest uncorrelated sector.
        """)
        
    with st.expander("🎯 Layer 2: Multi-Layer Individual Stock Selection", expanded=True):
        st.markdown("""
        Constituents of the selected sectors are subjected to a **3-Execution-Layer filter**:
        
        #### 📊 Execution Layer 1: Fundamental Strength (P/E & Profitability)
        - Calculates profitability stability using Return on Equity (ROE), trailing Price-to-Earnings (PE), and Price-to-Book (PB) ratios.
        - High weight is placed on sustainable earnings growth, debt-to-equity compliance (avoiding highly leveraged traps), and positive revenue momentum.
        
        #### 📈 Execution Layer 2: Technical Rebound & Double Bottom Accumulation
        - **RSI (14D) & 52-Week Low Filter**: Identifies stocks near support bounds. The rebound potential score increases when the stock is close to its 52-week low but stabilizing.
        - **Double Bottom Detection**: Scans the last 150 days of closing price data to check if a stock has completed a structural double bottom:
          - Trough 1 and Trough 2 must be within 5% price difference.
          - Trough 2 must be followed by a minimum bounce (2%) to confirm active accumulation.
          - The peak between troughs must have seen a moderate pullback, confirming a clear consolidation channel.
          
        #### 🎲 Execution Layer 3: Statistical Edge via Monte Carlo Forecasting
        - Executes **5000+ random price walks** (using historical drift and daily volatility) over a forward trading horizon of 5-10 days.
        - Simulates trade targets (+10%) and stop-loss limits (-2.5%) for each path.
        - Computes the probability of hitting the target before the stop loss, outputting the statistical win probability, estimated entry price target, and stop loss.
        """)

    with st.expander("🌐 Layer 3: Macro Factor Sentiment Filtering (Pytrends Gatekeeper)", expanded=True):
        st.markdown("""
        The final gatekeeper runs on daily Google Trends search data in India (`geo='IN'`, `timeframe='today 3-m'` under 270 days) to filter the initial recommendation pool:
        
        #### 🛠️ Data Stabilizing & Normalization:
        - **Partial Data Filter**: Automatically identifies and drops the `isPartial` flag returned for the latest calendar day to avoid feeding incomplete daily trend data into models.
        - **Rolling Z-Score (14-Day)**: Normalizes raw Google Trends search values (scale of 0-100) using a rolling 14-day mean and standard deviation. This extracts search **acceleration/momentum** rather than unstable scalar points.
        
        #### 📋 Directional Sector Matching Matrix:
        - **Banking & NBFCs**: Tracks `Repo Rate` (Negative modifier when rising) and `Home Loan` (Positive modifier when rising).
        - **Automotive**: Tracks `Crude Oil` (Negative input cost modifier when rising) and `Car Loan` (Positive modifier when rising).
        - **Technology / IT**: Tracks `Layoffs` (Negative filter when accelerating) and `Nifty IT` (Positive trend index when rising).
        
        #### 🚨 Global Macro Risk regimes:
        - Tracks `Inflation` and `Gold Price` search trends. If the Z-Score of either keyword exceeds **+2.0**, it signals systemic stress/risk-off mode, triggering a **30% beta-reduction penalty** to the combined scores of all stocks to protect capital.
        - **Pass/Fail Thresholds**: Stocks with negative adjusted scores or experiencing highly hostile sector sentiment trends (sentiment multiplier `< -0.3`) are filtered out completely, leaving only the highest-scoring setup candidates.
        """)

    with st.expander("💰 Exit Strategy & Simulation Rules", expanded=True):
        st.markdown("""
        All simulated trades follow strict execution logic:
        1. **Entry**: Executed at the closing price of the day the stock recommendation switches to BUY.
        2. **Risk Management**:
           - **Stop Loss**: Triggered immediately if the stock price drops below the specified threshold (default: -10.0%).
           - **Target Take-Profit**: Triggered immediately if the stock price rises above the profit take threshold (default: +25.0%).
           - **Time-Horizon Expiry**: If neither Stop Loss nor Profit Target is hit within the maximum holding window (default: 120 trading days), the position is exited at the current closing price.
        """)
