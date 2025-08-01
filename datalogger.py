import sqlite3
from datetime import datetime, timedelta
import logging
import json
from cryptography.fernet import Fernet
import pandas as pd
import os

# Load encryption key from file
KEY_FILE = '/home/sseevri/SmartSubstationMonitoringSystem/config_key.key'
if not os.path.exists(KEY_FILE):
    raise FileNotFoundError(f"Encryption key file {KEY_FILE} not found. Run encrypt_config.py first.")
with open(KEY_FILE, 'rb') as f:
    key = f.read()

# Load and decrypt configuration
with open('/home/sseevri/SmartSubstationMonitoringSystem/config.json', 'r') as f:
    encrypted_config = json.load(f)
cipher = Fernet(key)
config = json.loads(cipher.decrypt(encrypted_config['encrypted_data'].encode()).decode())

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=config['log_file']
)

REGISTER_NAMES = [
    "Watts Total", "Watts R phase", "Watts Y phase", "Watts B phase",
    "VAR Total", "VAR R phase", "VAR Y phase", "VAR B phase",
    "PF Avg (instant)", "PF R phase", "PF Y phase", "PF B phase",
    "VA Total", "VA R phase", "VA Y phase", "VA B phase",
    "VLL Average", "Vry Phase", "Vyb Phase", "Vbr Phase",
    "VLN Average", "V R phase", "V Y phase", "V B phase",
    "Current Total", "Current R phase", "Current Y phase", "Current B phase",
    "Frequency", "Wh Received (Import)", "VAh Received (Import)",
    "VARh Ind Received (Import)", "VARh Cap Received (Import)",
    "Wh Delivered", "VAh Delivered", "VARh Ind Delivered",
    "VARh Cap Delivered", "PF Average Received"
]

def init_db(db_path):
    """Initialize SQLite database (1-year) with monthly retention cleanup."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        columns = ['DateTime TEXT', 'Date TEXT', 'Time TEXT', 'Meter_ID INTEGER'] + [f'"{name}" REAL' for name in REGISTER_NAMES]
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS meter_readings (
            {', '.join(columns)},
            PRIMARY KEY (DateTime, Meter_ID)
        )
        """
        cursor.execute(create_table_sql)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_datetime ON meter_readings (DateTime)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_meter_id ON meter_readings (Meter_ID)")
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database initialization error (1-year): {e}")
        raise
    finally:
        conn.close()

def init_daily_db(db_path):
    """Initialize daily SQLite database, clearing existing data."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS meter_readings")
        columns = ['DateTime TEXT', 'Date TEXT', 'Time TEXT', 'Meter_ID INTEGER'] + [f'"{name}" REAL' for name in REGISTER_NAMES]
        create_table_sql = f"""
        CREATE TABLE meter_readings (
            {', '.join(columns)},
            PRIMARY KEY (DateTime, Meter_ID)
        )
        """
        cursor.execute(create_table_sql)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_datetime ON meter_readings (DateTime)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_meter_id ON meter_readings (Meter_ID)")
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database initialization error (daily): {e}")
        raise
    finally:
        conn.close()

def log_to_db(db_path, date, time_str, meter_id, data):
    """Log meter data to SQLite (1-year) with monthly retention cleanup."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        datetime_str = f"{date} {time_str}"
        values = [datetime_str, date, time_str, meter_id]
        for name in REGISTER_NAMES:
            value = data.get(name)
            values.append(round(value, 2) if value is not None else None)
        placeholders = ','.join(['?' for _ in values])
        insert_sql = f"""
        INSERT OR REPLACE INTO meter_readings (DateTime, Date, Time, Meter_ID, {', '.join(f'"{name}"' for name in REGISTER_NAMES)})
        VALUES ({placeholders})
        """
        cursor.execute(insert_sql, values)
        # Monthly retention cleanup
        if datetime.now().day == 1:
            cutoff_time = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("DELETE FROM meter_readings WHERE DateTime < ?", (cutoff_time,))
            deleted_rows = cursor.rowcount
            logging.info(f"Deleted {deleted_rows} records older than 1 year from {db_path}")
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database logging error (1-year): {e}")
    finally:
        conn.close()

def log_to_daily_db(db_path, date, time_str, meter_id, data):
    """Log meter data to daily SQLite database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        datetime_str = f"{date} {time_str}"
        values = [datetime_str, date, time_str, meter_id]
        for name in REGISTER_NAMES:
            value = data.get(name)
            values.append(round(value, 2) if value is not None else None)
        placeholders = ','.join(['?' for _ in values])
        insert_sql = f"""
        INSERT OR REPLACE INTO meter_readings (DateTime, Date, Time, Meter_ID, {', '.join(f'"{name}"' for name in REGISTER_NAMES)})
        VALUES ({placeholders})
        """
        cursor.execute(insert_sql, values)
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database logging error (daily): {e}")
    finally:
        conn.close()

def copy_daily_to_yearly(daily_db_path, yearly_db_path):
    """Copy all data from daily database to 1-year database."""
    try:
        conn_daily = sqlite3.connect(daily_db_path)
        conn_yearly = sqlite3.connect(yearly_db_path)
        cursor_daily = conn_daily.cursor()
        cursor_yearly = conn_yearly.cursor()
        cursor_daily.execute("SELECT * FROM meter_readings")
        rows = cursor_daily.fetchall()
        columns = ['DateTime', 'Date', 'Time', 'Meter_ID'] + REGISTER_NAMES
        placeholders = ','.join(['?' for _ in columns])
        insert_sql = f"""
        INSERT OR REPLACE INTO meter_readings (DateTime, Date, Time, Meter_ID, {', '.join(f'"{name}"' for name in REGISTER_NAMES)})
        VALUES ({placeholders})
        """
        cursor_yearly.executemany(insert_sql, rows)
        conn_yearly.commit()
        logging.info(f"Copied {len(rows)} records from daily to yearly database")
    except sqlite3.Error as e:
        logging.error(f"Error copying daily to yearly database: {e}")
    finally:
        conn_daily.close()
        conn_yearly.close()

def get_yesterday_data(db_path):
    """Fetch data for yesterday (00:00:00 to 23:59:00) from 1-year database."""
    try:
        conn = sqlite3.connect(db_path)
        yesterday = (datetime.now() - timedelta(days=1)).date()
        start_time = f"{yesterday} 00:00:00"
        end_time = f"{yesterday} 23:59:00"
        query = f"""
        SELECT DateTime, Date, Time, Meter_ID, "VLL Average", "Current Total", "Watts Total", "PF Average Received"
        FROM meter_readings
        WHERE DateTime BETWEEN ? AND ?
        """
        df = pd.read_sql_query(query, conn, params=(start_time, end_time))
        conn.close()
        # Ensure non-negative values
        for col in ["VLL Average", "Current Total", "Watts Total", "PF Average Received"]:
            if col in df.columns:
                df[col] = df[col].clip(lower=0)
        return df
    except sqlite3.Error as e:
        logging.error(f"Error fetching yesterday's data: {e}")
        return pd.DataFrame()

def get_today_data(db_path):
    """Fetch data for today (00:00:00 to now) from daily database."""
    try:
        conn = sqlite3.connect(db_path)
        today = datetime.now().date()
        start_time = f"{today} 00:00:00"
        end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        query = f"""
        SELECT DateTime, Date, Time, Meter_ID, "VLL Average", "Current Total", "Watts Total", "PF Average Received"
        FROM meter_readings
        WHERE DateTime BETWEEN ? AND ?
        """
        df = pd.read_sql_query(query, conn, params=(start_time, end_time))
        conn.close()
        # Ensure non-negative values
        for col in ["VLL Average", "Current Total", "Watts Total", "PF Average Received"]:
            if col in df.columns:
                df[col] = df[col].clip(lower=0)
        return df
    except sqlite3.Error as e:
        logging.error(f"Error fetching today's data: {e}")
        return pd.DataFrame()

def export_to_csv(db_path):
    """Export entire 1-year database to CSV string with Date and Time fields."""
    try:
        conn = sqlite3.connect(db_path)
        query = "SELECT * FROM meter_readings"
        df = pd.read_sql_query(query, conn)
        conn.close()
        # Ensure non-negative values
        for col in df.columns:
            if col not in ['DateTime', 'Date', 'Time', 'Meter_ID']:
                df[col] = df[col].clip(lower=0)
        return df.to_csv(index=False)
    except sqlite3.Error as e:
        logging.error(f"Error exporting database to CSV: {e}")
        return None
