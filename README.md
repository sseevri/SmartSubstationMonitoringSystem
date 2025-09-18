# Smart Substation Monitoring System

## Overview

The **Smart Substation Monitoring System** is a web-based dashboard for real-time monitoring of electrical substations. Built using [Plotly Dash](https://dash.plotly.com/), it runs on a Raspberry Pi and displays meter data (e.g., voltage, current, power factor) from multiple meters, sourced from a local SQLite database. The system supports secure user authentication, historical data visualization, encrypted CSV downloads, and Telegram alerts.

## Features
- **Real-Time Dashboard**: Displays live summary readings for five key meters (Transformer, EssentialLoad, NonEssentialLoad, ColonyLoad, DGSetLoad).
- **Meter-Specific Pages**: Provides detailed, real-time parameter tables for each individual meter.
- **Historical Charts**:
    - Visualizes yesterday’s and today’s data on the main dashboard for key parameters like Voltage, Total Current, and Power.
    - **New:** Displays stacked yesterday-vs-today charts for R, Y, and B phase currents on each individual meter page for detailed comparison.
- **Secure Access**: Features user login for the dashboard and a separate, encrypted password for CSV data downloads.
- **Encrypted Configuration**: All sensitive information, including passwords and API keys, is stored in an encrypted `config.json` file, which is not tracked by Git.
- **Data Logging**: Persistently logs all meter data to a local SQLite database.
- **Telegram Bot Integration**: Capable of sending alerts and periodic updates.
- **Audit Logging**: Tracks user logins and other important system events in `dashboard_audit.log`.

---

## Repository Structure
```
SmartSubstationMonitoringSystem/
├── app.py                 # Main Dash application for the web dashboard.
├── datalogger.py          # Handles data logging to the SQLite database.
├── DMF_Reader.py          # Reads raw data from meters.
├── requirements.txt       # Python package dependencies.
├── encrypt_config.py      # Script to encrypt config.json and generate a key.
├── shared_config.py       # Contains shared variables like register maps.
├── telegram_meter_bot.py  # Logic for the Telegram bot.
├── anomaly_detector.py    # Module for detecting anomalies in meter readings.
├── assets/                # CSS and other static assets.
├── docs/                  # Project documentation.
├── config.json            # (Encrypted) Stores all configuration, passwords, and keys.
├── config_key.key         # The key to decrypt config.json. (Must be kept secure!)
└── venv/                  # Python virtual environment folder.
```
⚠️ **Security Note**: `config.json` (once encrypted) and `config_key.key` are highly sensitive and are excluded from Git via `.gitignore`. They must be managed securely on the device running the application.

---

## Prerequisites
- **Hardware**: Raspberry Pi (e.g., Raspberry Pi 4) or other Linux-based system.
- **Software**:
  - Python 3.9+
  - `python3-venv`
  - `libssl-dev` (for compiling the `scrypt` dependency)

---

## Setup Instructions

1. **Clone the Repository**:
   ```bash
   git clone <your-repository-url>
   cd SmartSubstationMonitoringSystem
   ```

2. **Install System Dependencies**:
   *(This is a crucial step to ensure Python packages can be installed correctly)*
   ```bash
   sudo apt-get update
   sudo apt-get install -y libssl-dev
   ```

3. **Set Up Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Create and Encrypt Configuration**:
    a. Create a new file named `config.json` and paste the following template into it.
    b. **Fill in your actual values** for passwords, API keys, and paths. Use plain-text for the passwords in this step; the script will hash them.

    ```json
    {
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
        "admin": "your_dashboard_password"
      },
      "download_password": "your_csv_download_password",
      "whatsapp_api_url": "http://localhost:3000",
      "whatsapp_group_id": "YOUR_WHATSAPP_GROUP_ID",
      "whatsapp_group_name": "IoT_SS_VRI",
      "whatsapp_log_file": "/home/sseevri/SmartSubstationMonitoringSystem/whatsapp_bot.log",
      "whatsapp_server_url": "http://localhost:8002",
      "document_paths": [
        "/home/sseevri/SmartSubstationMonitoringSystem/docs/substation_manual.pdf",
        "/home/sseevri/SmartSubstationMonitoringSystem/docs/maintenance_procedures.txt",
        "/home/sseevri/SmartSubstationMonitoringSystem/docs/equipment_specs.csv"
      ],
      "ollama_model": "tinyllama"
    }
    ```

    c. Run the encryption script. This will generate `config_key.key` and overwrite `config.json` with an encrypted version.
    ```bash
    python encrypt_config.py
    ```
    **Important:** Keep `config_key.key` safe. If you lose it, you will not be able to decrypt your configuration.

---

## Usage

1. **Activate the Environment**:
   ```bash
   source venv/bin/activate
   ```

2. **Start the Monitoring Dashboard**:
   ```bash
   python app.py
   ```

3. **Access the Dashboard**:
   - Open a web browser and go to `http://<your-raspberry-pi-ip>:8050`

---

## Versioning
- **v1.1.0 (Current)**:
  - Added historical phase current charts to individual meter pages.
  - Refactored data-fetching and fixed bugs in datalogger.
- **v1.0**:
  - Initial release with Telegram bot integration and anomaly detection.

---

## Troubleshooting
- **Installation Error for `scrypt`**: If you see an error about `openssl/aes.h` not being found, you are missing the system dependency. Run `sudo apt-get install -y libssl-dev`.
- **Dashboard Issues**: Check `app.log` and `dashboard_audit.log` for errors.

---

## License
This project is licensed under the MIT License.