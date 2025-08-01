from cryptography.fernet import Fernet
import json
import os

# Generate or load encryption key
key_file = '/home/sseevri/SmartSubstationMonitoringSystem/config_key.key'
if not os.path.exists(key_file):
    key = Fernet.generate_key()
    with open(key_file, 'wb') as f:
        f.write(key)
else:
    with open(key_file, 'rb') as f:
        key = f.read()

cipher = Fernet(key)

# Define configuration
config = {
    "serial_port": "/dev/ttyACM0",
    "baud_rate": 9600,
    "serial_timeout": 3,
    "polling_interval": 30,
    "sqlite_log_interval": 1800,
    "meter_ids": [1, 2, 3, 4, 5],
    "csv_file": "/home/sseevri/SmartSubstationMonitoringSystem/meter_data.csv",
    "db_path": "/home/sseevri/SmartSubstationMonitoringSystem/meter_data_1year.db",
    "db_daily_path": "/home/sseevri/SmartSubstationMonitoringSystem/meter_data_daily.db",
    "log_file": "/home/sseevri/SmartSubstationMonitoringSystem/modbus_reader.log",
    "audit_log_file": "/home/sseevri/SmartSubstationMonitoringSystem/dashboard_audit.log",
    "dashboard_auth": {
        "admin": "password123"
    },
    "download_password": "secure123"
}

# Encrypt and save configuration
encrypted_data = cipher.encrypt(json.dumps(config).encode()).decode()
with open('/home/sseevri/SmartSubstationMonitoringSystem/config.json', 'w') as f:
    json.dump({"encrypted_data": encrypted_data}, f)

print(f"Configuration encrypted and saved to config.json. Key saved to {key_file}")