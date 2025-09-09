import logging
import asyncio
import json
import os
import pandas as pd
from telegram import Bot
from cryptography.fernet import Fernet
from datetime import datetime

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration Loading ---
KEY_FILE = '/home/sseevri/SmartSubstationMonitoringSystem/config_key.key'
CONFIG_FILE = '/home/sseevri/SmartSubstationMonitoringSystem/config.json'

if not os.path.exists(KEY_FILE):
    logger.error(f"Encryption key file {KEY_FILE} not found. Run encrypt_config.py first.")
    exit(1)
with open(KEY_FILE, 'rb') as f:
    key = f.read()

if not os.path.exists(CONFIG_FILE):
    logger.error(f"Configuration file {CONFIG_FILE} not found.")
    exit(1)
with open(CONFIG_FILE, 'r') as f:
    encrypted_config = json.load(f)
cipher = Fernet(key)
config = json.loads(cipher.decrypt(encrypted_config['encrypted_data'].encode()).decode())

# --- Telegram Bot Configuration ---
BOT_TOKEN = "8488896535:AAH1tRUBnzm2ZO5EqJm3YuudZqIHYVUu08o"  # Replace with your actual bot token
CHAT_ID = -4956747914      # Replace with your actual chat ID (can be a group chat ID)

# --- Meter Names (from app.py) ---
meter_names = {
    1: "Transformer",
    2: "EssentialLoad",
    3: "NonEssentialLoad",
    4: "ColonyLoad",
    5: "DGSetLoad"
}

# List of all possible columns that might be needed
ALL_METER_COLUMNS = [
    'Meter_ID', 'DateTime',
    'Vry Phase', 'Vyb Phase', 'Vbr Phase', 'VLL Average',
    'V R phase', 'V Y phase', 'V B phase', 'VLN Average',
    'Current R phase', 'Current Y phase', 'Current B phase', 'Current Total',
    'Watts R phase', 'Watts Y phase', 'Watts B phase', 'Watts Total',
    'Wh Received (Import)', # Changed from 'Wh Received'
    'PF R phase', 'PF Y phase', 'PF B phase', 'PF Average Received'
]

CSV_FILE_PATH = '/home/sseevri/SmartSubstationMonitoringSystem/meter_data.csv' # New global variable

# --- Function to get latest meter readings ---
def get_latest_meter_readings(csv_file_path):
    try:
        if not os.path.exists(csv_file_path):
            logger.error(f"CSV file {csv_file_path} not found.")
            return pd.DataFrame()

        df = pd.read_csv(csv_file_path)

        logger.info(f"df head after reading CSV:\n{df.head()}")

        if df.empty:
            logger.warning("No data available in the CSV file.")
            return pd.DataFrame()

        # Ensure DateTime column is correctly parsed
        # Assuming 'Date' and 'Time' columns exist and need to be combined
        if 'Date' in df.columns and 'Time' in df.columns:
            df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
        elif 'DateTime' in df.columns:
            df['DateTime'] = pd.to_datetime(df['DateTime'])
        else:
            logger.error("Neither 'DateTime' nor 'Date' and 'Time' columns found in CSV.")
            return pd.DataFrame()

        # Sort by DateTime in descending order to get the latest readings
        df = df.sort_values(by='DateTime', ascending=False)
        
        # Get the latest reading for each meter
        latest_readings = df.groupby('Meter_ID').first().reset_index()
        logger.info(f"latest_readings head after groupby:\n{latest_readings.head()}")

        # Added logging for unique Meter_IDs and their max DateTime
        unique_meters_info = df.groupby('Meter_ID')['DateTime'].max().reset_index()
        logger.info(f"Unique Meter_IDs and their latest DateTime in CSV:\n{unique_meters_info}")

        return latest_readings
    except Exception as e:
        logger.error(f"Error fetching meter readings from CSV: {e}")
        return pd.DataFrame()

# Helper function to format values
def format_value(value, decimal_places=2):
    if pd.isna(value):
        return ""  # Return empty string for missing values
    if isinstance(value, (int, float)):
        return f"{value:.{decimal_places}f}"
    return str(value)

# --- Main function to send readings ---
async def send_meter_readings():
    bot = Bot(token=BOT_TOKEN)
    # db_path = config['db_path'] # Removed

    latest_readings_df = get_latest_meter_readings(CSV_FILE_PATH) # Changed to CSV_FILE_PATH

    # Get current date and time for the header
    now = datetime.now()
    header_date = now.strftime("%d/%m/%Y")
    header_time = now.strftime("%H.%M")  # Changed to match desired format

    message_parts = [
        "⚡SSE/E/VRI Substation Monitoring System⚡",
        f"⚡Latest Meter Readings date: {header_date} time {header_time} ⚡",
        "" # Blank line
    ]

    if latest_readings_df.empty:
        message_parts.append("No meter readings available to report.")
    else:
        for meter_id in sorted(meter_names.keys()): # Ensure consistent order
            row_data_for_meter = latest_readings_df[latest_readings_df['Meter_ID'] == meter_id]
            
            if row_data_for_meter.empty:
                # Create a dummy row with default values if no data is available for the meter
                dummy_data = {col: 0.00 for col in ALL_METER_COLUMNS}
                dummy_data['Meter_ID'] = meter_id
                dummy_data['status'] = 'No Data'
                dummy_data['comm_status'] = 'FAILED'
                row = pd.Series(dummy_data)
            else:
                row = row_data_for_meter.iloc[0] # Get the single row for the meter

            meter_name = meter_names.get(meter_id, f"Unknown ({meter_id})")
            status = format_value(row.get('comm_status')) == "FAILED" and "Communication Failed" or format_value(row.get('status', 'N/A'))
            
            message_parts.append(f"* {meter_name} (ID: {meter_id}) - Status: {status} *")

            # Only show Line and Phase Voltage for Transformer (1) and DGSetLoad (5)
            if meter_id in [1, 5]:
                # Line Voltage
                vry = format_value(row.get('Vry Phase'))
                vyb = format_value(row.get('Vyb Phase'))
                vbr = format_value(row.get('Vbr Phase'))
                message_parts.append(f"  Line Voltage: {vry}/{vyb}/{vbr}")

                # Phase Voltage
                vr = format_value(row.get('V R phase'))
                vy = format_value(row.get('V Y phase'))
                vb = format_value(row.get('V B phase'))
                message_parts.append(f"  Phase voltage: {vr}/{vy}/{vb}")

            # Current Total (R/Y/B) - shown for all meters
            cr = format_value(row.get('Current R phase'))
            cy = format_value(row.get('Current Y phase'))
            cb = format_value(row.get('Current B phase'))
            message_parts.append(f"  Current Total: {cr}/{cy}/{cb}")
            
            # KW Total (single value, not phase-separated) - shown for all meters
            wt = format_value(row.get('Watts Total'))
            message_parts.append(f"  KW Total: {wt}")
            
            # KWh - shown for all meters
            wh = format_value(row.get('Wh Received') or row.get('Wh Received (Import)'))
            message_parts.append(f"  KWh: {wh}")

            # PF (single value, not phase-separated) - shown for all meters
            pfa = format_value(row.get('PF Average Received'))
            message_parts.append(f"  PF: {pfa}")

            message_parts.append("") # Add a blank line for separation
    
    message = "\n".join(message_parts)

    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info("Meter readings sent successfully to Telegram.")
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")


if __name__ == '__main__':
    asyncio.run(send_meter_readings())