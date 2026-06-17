CREATE DATABASE IF NOT EXISTS algo_stocks;
USE algo_stocks;

CREATE TABLE IF NOT EXISTS price_data (
    symbol VARCHAR(20),
    date DATE,
    open DECIMAL(15, 4),
    high DECIMAL(15, 4),
    low DECIMAL(15, 4),
    close DECIMAL(15, 4),
    volume BIGINT,
    PRIMARY KEY (symbol, date),
    INDEX idx_symbol (symbol),
    INDEX idx_date (date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol VARCHAR(20) PRIMARY KEY,
    last_updated DATETIME,
    data_json JSON
) ENGINE=InnoDB;
