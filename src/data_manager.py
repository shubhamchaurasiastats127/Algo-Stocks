import pandas as pd
import warnings
warnings.filterwarnings("ignore", category=UserWarning, message=".*pandas only supports SQLAlchemy connectable.*")
# pyrefly: ignore [missing-import]
import yfinance as yf
# pyrefly: ignore [missing-import]
import mysql.connector
# pyrefly: ignore [missing-import]
from mysql.connector import pooling
import yaml
import os
import time
from datetime import datetime, timedelta
import json
import logging

class CacheManager:
    def __init__(self, db_config):
        self.db_config = db_config
        self._init_pool()
        self.init_tables()

    def _init_pool(self):
        # Use a connection pool for efficiency
        self.pool = pooling.MySQLConnectionPool(
            pool_name="algo_pool",
            pool_size=10,
            pool_reset_session=True,
            **self.db_config
        )

    def init_tables(self):
        conn = self.pool.get_connection()
        cursor = conn.cursor()
        try:
            # Create indices table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS indices (
                    index_name VARCHAR(100) PRIMARY KEY,
                    csv_url VARCHAR(255) NOT NULL,
                    last_updated DATETIME
                ) ENGINE=InnoDB;
            """)
            
            # Create index_constituents table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS index_constituents (
                    index_name VARCHAR(100),
                    symbol VARCHAR(20),
                    PRIMARY KEY (index_name, symbol),
                    FOREIGN KEY (index_name) REFERENCES indices(index_name) ON DELETE CASCADE,
                    INDEX idx_symbol (symbol)
                ) ENGINE=InnoDB;
            """)
            conn.commit()
            
            # Pre-populate indices table
            default_indices = {
                "Nifty 50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
                "Nifty Next 50": "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv",
                "Nifty 100": "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
                "Nifty 200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
                "Nifty 500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
                "Nifty Midcap 50": "https://archives.nseindia.com/content/indices/ind_niftymidcap50list.csv",
                "Nifty Midcap 100": "https://archives.nseindia.com/content/indices/ind_niftymidcap100list.csv",
                "Nifty Smallcap 50": "https://archives.nseindia.com/content/indices/ind_niftysmallcap50list.csv",
                "Nifty Smallcap 100": "https://archives.nseindia.com/content/indices/ind_niftysmallcap100list.csv",
                "Nifty Bank": "https://archives.nseindia.com/content/indices/ind_niftybanklist.csv",
                "Nifty IT": "https://archives.nseindia.com/content/indices/ind_niftyitlist.csv",
                "Nifty Auto": "https://archives.nseindia.com/content/indices/ind_niftyautolist.csv",
                "Nifty Pharma": "https://archives.nseindia.com/content/indices/ind_niftypharmalist.csv",
                "Nifty FMCG": "https://archives.nseindia.com/content/indices/ind_niftyfmcglist.csv",
                "Nifty Metal": "https://archives.nseindia.com/content/indices/ind_niftymetallist.csv",
                "Nifty Realty": "https://archives.nseindia.com/content/indices/ind_niftyrealtylist.csv",
                "Nifty Energy": "https://archives.nseindia.com/content/indices/ind_niftyenergylist.csv",
                "Nifty Infra": "https://archives.nseindia.com/content/indices/ind_niftyinfralist.csv",
                "Nifty Financial Services": "https://archives.nseindia.com/content/indices/ind_niftyfinancelist.csv",
                "Nifty Private Bank": "https://archives.nseindia.com/content/indices/ind_nifty_privatebanklist.csv",
                "Nifty PSU Bank": "https://archives.nseindia.com/content/indices/ind_niftypsubanklist.csv"
            }
            
            for name, url in default_indices.items():
                cursor.execute("""
                    INSERT INTO indices (index_name, csv_url)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE csv_url = VALUES(csv_url)
                """, (name, url))
            conn.commit()
            
        except Exception as e:
            logging.error(f"Error initializing database tables: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def save_price_data(self, df, symbol):
        if df.empty:
            return
        
        conn = self.pool.get_connection()
        cursor = conn.cursor()
        
        try:
            # Handle MultiIndex columns (common in newer yfinance)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df = df.reset_index()
            # Find the date column (could be 'Date' or 'index')
            date_col = None
            for col in ['Date', 'date', 'index', 'Datetime']:
                if col in df.columns:
                    date_col = col
                    break
            
            if not date_col:
                logging.error(f"Could not find date column for {symbol}. Columns: {df.columns.tolist()}")
                return

            data_list = []
            for _, row in df.iterrows():
                try:
                    data_list.append((
                        symbol,
                        row[date_col].strftime('%Y-%m-%d'),
                        float(row['Open']),
                        float(row['High']),
                        float(row['Low']),
                        float(row['Close']),
                        int(row['Volume'])
                    ))
                except Exception as row_e:
                    continue
            
            if not data_list:
                return

            query = """
                INSERT INTO price_data (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                open=VALUES(open), high=VALUES(high), low=VALUES(low), 
                close=VALUES(close), volume=VALUES(volume)
            """
            
            cursor.executemany(query, data_list)
            conn.commit()
        except Exception as e:
            logging.error(f"Error saving data for {symbol}: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def get_price_data(self, symbol, start_date=None):
        conn = self.pool.get_connection()
        try:
            query = "SELECT date, open, high, low, close, volume FROM price_data WHERE symbol = %s"
            params = [symbol]
            if start_date:
                query += " AND date >= %s"
                params.append(start_date)
            
            df = pd.read_sql(query, conn, params=params)
            
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                df.sort_index(inplace=True)
            return df
        finally:
            conn.close()

    def get_last_date(self, symbol):
        conn = self.pool.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT max(date) FROM price_data WHERE symbol = %s", (symbol,))
            res = cursor.fetchone()[0]
            return res.strftime('%Y-%m-%d') if res else None
        finally:
            cursor.close()
            conn.close()

class DataFetcher:
    def __init__(self, config):
        self.config = config
        self.cache = CacheManager(config['mysql'])
        logging.basicConfig(filename=config['paths']['logs'], level=logging.INFO)

    def fetch_universe(self, index_name="Nifty 500"):
        conn = self.cache.pool.get_connection()
        cursor = conn.cursor()
        try:
            # 1. Fetch CSV URL and last_updated from DB
            cursor.execute("SELECT csv_url, last_updated FROM indices WHERE index_name = %s", (index_name,))
            res = cursor.fetchone()
            if not res:
                logging.error(f"Index {index_name} not found in database configuration.")
                return []
            
            csv_url, last_updated = res
            
            # 2. Check if constituents need refresh (either not fetched yet or older than 7 days)
            needs_refresh = True
            if last_updated:
                age = datetime.now() - last_updated
                if age.days < 7:
                    needs_refresh = False
            
            if needs_refresh:
                logging.info(f"Refreshing constituents for {index_name} from {csv_url}...")
                try:
                    df = pd.read_csv(csv_url)
                    # The column name is "Symbol". Clean up any weird characters/spaces.
                    df.columns = [c.strip() for c in df.columns]
                    if 'Symbol' in df.columns:
                        symbols = df['Symbol'].dropna().str.strip().tolist()
                        
                        # Store in index_constituents
                        cursor.execute("DELETE FROM index_constituents WHERE index_name = %s", (index_name,))
                        
                        insert_query = "INSERT INTO index_constituents (index_name, symbol) VALUES (%s, %s)"
                        insert_data = [(index_name, sym) for sym in symbols]
                        
                        cursor.executemany(insert_query, insert_data)
                        
                        # Update last_updated in indices
                        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        cursor.execute("UPDATE indices SET last_updated = %s WHERE index_name = %s", (now_str, index_name))
                        conn.commit()
                        logging.info(f"Successfully updated {len(symbols)} constituents for {index_name}.")
                    else:
                        logging.error(f"Could not find 'Symbol' column in CSV for {index_name}. Columns: {df.columns.tolist()}")
                except Exception as csv_e:
                    logging.error(f"Failed to download/parse constituents for {index_name}: {csv_e}")
            
            # 3. Retrieve constituents from DB
            cursor.execute("SELECT symbol FROM index_constituents WHERE index_name = %s", (index_name,))
            symbols_db = [r[0] for r in cursor.fetchall()]
            
            return list(dict.fromkeys(symbols_db))
            
        except Exception as e:
            logging.error(f"Error fetching universe for {index_name}: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_stock_data(self, symbol, days=730):
        # 1. Check cache
        last_date_str = self.cache.get_last_date(symbol)
        today = datetime.now().date()
        
        start_fetch = None
        if last_date_str:
            last_date = datetime.strptime(last_date_str, '%Y-%m-%d').date()
            if last_date < today - timedelta(days=1):
                start_fetch = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            start_fetch = (today - timedelta(days=days)).strftime('%Y-%m-%d')

        # 2. Fetch missing from yfinance
        if start_fetch:
            try:
                ticker = f"{symbol}.NS"
                df = yf.download(ticker, start=start_fetch, progress=False)
                if not df.empty:
                    self.cache.save_price_data(df, symbol)
            except Exception as e:
                logging.error(f"Error fetching {symbol}: {e}")

        return self.cache.get_price_data(symbol)

    def get_fundamentals(self, symbol):
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            info = ticker.info
            # Cache fundamentals in MySQL
            self.save_fundamentals(symbol, info)
            return info
        except Exception as e:
            logging.error(f"Error fetching fundamentals for {symbol}: {e}")
            return {}
            
    def save_fundamentals(self, symbol, info):
        conn = self.cache.pool.get_connection()
        cursor = conn.cursor()
        try:
            query = """
                INSERT INTO fundamentals (symbol, last_updated, data_json)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE last_updated=%s, data_json=%s
            """
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            json_data = json.dumps(info)
            cursor.execute(query, (symbol, now_str, json_data, now_str, json_data))
            conn.commit()
        except Exception as e:
            logging.error(f"Error saving fundamentals for {symbol}: {e}")
        finally:
            cursor.close()
            conn.close()
