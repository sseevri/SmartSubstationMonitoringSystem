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

# --- Data Source Configuration ---
CSV_FILE_PATH = '/home/sseevri/SmartSubstationMonitoringSystem/meter_data.csv'

# --- Anomaly Detection Thresholds (Example values, adjust as needed) ---
VOLTAGE_NOMINAL = 415.0 # Nominal Line-to-Line Voltage
VOLTAGE_PHASE_NOMINAL = 240.0 # Nominal Line-to-Neutral Voltage

THRESHOLD_UNDER_VOLTAGE_PERCENT = 0.10 # 10% below nominal
THRESHOLD_HIGH_VOLTAGE_PERCENT = 0.10  # 10% above nominal
THRESHOLD_SINGLE_PHASING_PERCENT = 0.50 # If one phase is 50% lower than others
THRESHOLD_POWER_FAILURE_CURRENT = 5.0 # Current below this indicates potential power failure

# --- Helper function to format values ---
def format_value(value, decimal_places=2):
    if pd.isna(value):
        return "0.00"
    if isinstance(value, (int, float)):
        return f"{value:.{decimal_places}f}"
    return str(value)

# --- Function to get latest meter readings from CSV ---
def get_latest_meter_readings(csv_file_path):
    try:
        if not os.path.exists(csv_file_path):
            logger.error(f"CSV file {csv_file_path} not found.")
            return pd.DataFrame()

        df = pd.read_csv(csv_file_path)

        if df.empty:
            logger.warning("No data available in the CSV file.")
            return pd.DataFrame()

        if 'Date' in df.columns and 'Time' in df.columns:
            df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
        elif 'DateTime' in df.columns:
            df['DateTime'] = pd.to_datetime(df['DateTime'])
        else:
            logger.error("Neither 'DateTime' nor 'Date' and 'Time' columns found in CSV.")
            return pd.DataFrame()

        df = df.sort_values(by='DateTime', ascending=False)
        latest_readings = df.groupby('Meter_ID').first().reset_index()
        return latest_readings
    except Exception as e:
        logger.error(f"Error fetching meter readings from CSV: {e}")
        return pd.DataFrame()

# --- Anomaly Detection Functions ---
def detect_voltage_anomalies(meter_id, row, anomalies):
    meter_name = meter_names.get(meter_id, f"Unknown ({meter_id})")
    
    # Line-to-Line Voltage (Vry Phase, Vyb Phase, Vbr Phase)
    vlls = [row.get('Vry Phase'), row.get('Vyb Phase'), row.get('Vbr Phase')]
    vlls = [v for v in vlls if pd.notna(v)] # Filter out NaN

    if vlls:
        for vll in vlls:
            if vll < VOLTAGE_NOMINAL * (1 - THRESHOLD_UNDER_VOLTAGE_PERCENT):
                anomalies.append(f"  - Under Voltage (Line-Line) for {meter_name}: {format_value(vll)}V")
            elif vll > VOLTAGE_NOMINAL * (1 + THRESHOLD_HIGH_VOLTAGE_PERCENT):
                anomalies.append(f"  - High Voltage (Line-Line) for {meter_name}: {format_value(vll)}V")

    # Line-to-Neutral Voltage (V R phase, V Y phase, V B phase)
    vlns = [row.get('V R phase'), row.get('V Y phase'), row.get('V B phase')]
    vlns = [v for v in vlns if pd.notna(v)] # Filter out NaN

    if vlns:
        for vln in vlns:
            if vln < VOLTAGE_PHASE_NOMINAL * (1 - THRESHOLD_UNDER_VOLTAGE_PERCENT):
                anomalies.append(f"  - Under Voltage (Line-Neutral) for {meter_name}: {format_value(vln)}V")
            elif vln > VOLTAGE_PHASE_NOMINAL * (1 + THRESHOLD_HIGH_VOLTAGE_PERCENT):
                anomalies.append(f"  - High Voltage (Line-Neutral) for {meter_name}: {format_value(vln)}V")

def detect_single_phasing(meter_id, row, anomalies):
    meter_name = meter_names.get(meter_id, f"Unknown ({meter_id})")
    vlns = [row.get('V R phase'), row.get('V Y phase'), row.get('V B phase')]
    vlns = [v for v in vlns if pd.notna(v)]

    if len(vlns) == 3: # Only check if all three phase voltages are available
        min_v = min(vlns)
        max_v = max(vlns)
        if max_v > 0 and min_v < max_v * (1 - THRESHOLD_SINGLE_PHASING_PERCENT):
            anomalies.append(f"  - Potential Single Phasing for {meter_name}: R:{format_value(vlns[0])}V, Y:{format_value(vlns[1])}V, B:{format_value(vlns[2])}V")
    elif len(vlns) < 3 and len(vlns) > 0: # If some phases are missing but not all are zero
        anomalies.append(f"  - Missing Phase(s) detected for {meter_name}: Only {len(vlns)} phase(s) reporting voltage.")

def detect_power_supply_failure(meter_id, row, anomalies):
    meter_name = meter_names.get(meter_id, f"Unknown ({meter_id})")
    
    # Check if all voltages are near zero
    vlls = [row.get('Vry Phase'), row.get('Vyb Phase'), row.get('Vbr Phase')]
    vlns = [row.get('V R phase'), row.get('V Y phase'), row.get('V B phase')]
    currents = [row.get('Current R phase'), row.get('Current Y phase'), row.get('Current B phase')]

    all_voltages_near_zero = all(pd.isna(v) or v < THRESHOLD_POWER_FAILURE_CURRENT for v in vlls + vlns)
    all_currents_near_zero = all(pd.isna(c) or c < THRESHOLD_POWER_FAILURE_CURRENT for c in currents)

    if all_voltages_near_zero and all_currents_near_zero:
        anomalies.append(f"  - Power Supply Failure detected for {meter_name}: All voltages and currents are near zero.")

# --- Main Anomaly Detection and Reporting Function ---
async def run_anomaly_detection():
    bot = Bot(token=BOT_TOKEN)
    
    latest_readings_df = get_latest_meter_readings(CSV_FILE_PATH)

    if latest_readings_df.empty:
        message = "Anomaly Detector: No meter readings available to analyze." 
    else:
        anomaly_messages = []
        for meter_id in sorted(meter_names.keys()):
            row_data_for_meter = latest_readings_df[latest_readings_df['Meter_ID'] == meter_id]
            
            if row_data_for_meter.empty:
                anomaly_messages.append(f"* {meter_names.get(meter_id, f'Unknown ({meter_id})')} (ID: {meter_id}): No recent data. *")
                continue
            
            row = row_data_for_meter.iloc[0]
            meter_anomalies = []

            detect_voltage_anomalies(meter_id, row, meter_anomalies)
            detect_single_phasing(meter_id, row, meter_anomalies)
            detect_power_supply_failure(meter_id, row, meter_anomalies)

            if meter_anomalies:
                anomaly_messages.append(f"* Anomalies for {meter_names.get(meter_id, f'Unknown ({meter_id})')} (ID: {meter_id}) *:")
                anomaly_messages.extend(meter_anomalies)
                anomaly_messages.append("") # Blank line for separation
        
        if anomaly_messages:
            message = "⚡ Power System Anomaly Alert! ⚡\n\n" + "\n".join(anomaly_messages)
            try:
                await bot.send_message(chat_id=CHAT_ID, text=message)
                logger.info("Anomaly detection report sent successfully to Telegram.")
            except Exception as e:
                logger.error(f"Failed to send anomaly report: {e}")
        else:
            logger.info("No anomalies detected. No message sent to Telegram.") # Log, but don't send message

if __name__ == '__main__':
    asyncio.run(run_anomaly_detection())
