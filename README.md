# Smart Substation Monitoring System

## Overview

The **Smart Substation Monitoring System** is a web-based dashboard for real-time monitoring of electrical substations. Built using [Plotly Dash](https://dash.plotly.com/), it runs on a Raspberry Pi and displays meter data (e.g., voltage, current, power factor) from multiple meters, sourced from `meter_data.csv` and `daily_data.db`. The system supports secure access, data visualization, and CSV export, with encrypted configuration and audit logging.

### Features
- **Real-Time Dashboard**: Displays current readings for five meters (Transformer, EssentialLoad, NonEssentialLoad, ColonyLoad, DGSetLoad) with status indicators.
- **Meter-Specific Pages**: Detailed parameter tables for each meter (e.g., `/meter/2` for EssentialLoad).
- **Historical Charts**: Visualizes yesterday’s and today’s data for voltage, current, watts, and power factor using SQLite databases.
- **Secure Access**: Basic authentication (`admin`/`password123`) and encrypted CSV download (`secure123`).
- **Audit Logging**: Tracks system events in `dashboard_audit.log`.
- **Encrypted Configuration**: Uses `cryptography.fernet` to secure `config.json`.

## Repository Structure
```
SmartSubstationMonitoringSystem/
├── app.py              # Dash application for the web dashboard
├── DMF_Reader.py       # Reads meter data and updates CSV/database
├── datalogger.py       # Handles data logging to SQLite
├── encrypt_config.py   # Encrypts configuration file
├── config.json         # Encrypted configuration
├── config_key.key      # Encryption key
├── requirements.txt    # Python dependencies
├── start.sh            # Starts the system
├── stop.sh             # Stops the system
├── meter_data.csv      # Stores real-time meter data
├── daily_data.db       # SQLite database for daily data
├── app.log             # Application logs
├── dashboard_audit.log # Audit logs
├── modbus_reader.log   # Modbus communication logs
├── ngrok.log           # ngrok tunneling logs
```

## Prerequisites
- **Hardware**: Raspberry Pi (e.g., Raspberry Pi 4) with Raspberry Pi OS.
- **Software**:
  - Python 3.8+
  - Virtualenv
  - ngrok (optional, for remote access)
- **Dependencies**: Listed in `requirements.txt`.

## Setup Instructions

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/<your-username>/SmartSubstationMonitoringSystem.git
   cd SmartSubstationMonitoringSystem
   ```

2. **Set Up Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Generate Encryption Key and Config**:
   - Run `encrypt_config.py` to create `config_key.key` and `config.json`:
     ```bash
     python3 encrypt_config.py
     ```
   - Ensure `config.json` contains:
     ```json
     {
       "encrypted_data": "<encrypted_string>",
       "dashboard_auth": {"admin": "password123"},
       "download_password": "secure123",
       "csv_file": "/home/sseevri/SmartSubstationMonitoringSystem/meter_data.csv",
       "db_path": "/home/sseevri/SmartSubstationMonitoringSystem/daily_data.db",
       "db_daily_path": "/home/sseevri/SmartSubstationMonitoringSystem/daily_data.db",
       "audit_log_file": "/home/sseevri/SmartSubstationMonitoringSystem/dashboard_audit.log"
     }
     ```

5. **Set File Permissions**:
   ```bash
   sudo chown sseevri:sseevri /home/sseevri/SmartSubstationMonitoringSystem/*
   chmod 644 /home/sseevri/SmartSubstationMonitoringSystem/*.py
   chmod 644 /home/sseevri/SmartSubstationMonitoringSystem/config.json
   chmod 644 /home/sseevri/SmartSubstationMonitoringSystem/config_key.key
   chmod 664 /home/sseevri/SmartSubstationMonitoringSystem/meter_data.csv
   chmod 664 /home/sseevri/SmartSubstationMonitoringSystem/daily_data.db
   chmod 755 /home/sseevri/SmartSubstationMonitoringSystem/start.sh
   chmod 755 /home/sseevri/SmartSubstationMonitoringSystem/stop.sh
   ```

6. **Initialize Data**:
   - Run `DMF_Reader.py` to generate `meter_data.csv` and `daily_data.db`:
     ```bash
     python3 DMF_Reader.py
     ```

7. **Set Up Systemd Service (Optional)**:
   - Create `/etc/systemd/system/smart-substation.service`:
     ```ini
     [Unit]
     Description=Smart Substation Monitoring System
     After=network.target

     [Service]
     User=sseevri
     WorkingDirectory=/home/sseevri/SmartSubstationMonitoringSystem
     ExecStart=/home/sseevri/SmartSubstationMonitoringSystem/start.sh
     ExecStop=/home/sseevri/SmartSubstationMonitoringSystem/stop.sh
     Restart=always

     [Install]
     WantedBy=multi-user.target
     ```
   - Enable and start:
     ```bash
     sudo systemctl enable smart-substation.service
     sudo systemctl start smart-substation.service
     ```

8. **Set Up ngrok (Optional)**:
   - Install ngrok and run:
     ```bash
     ngrok http 8050
     ```
   - Save the ngrok URL to `ngrok.log`:
     ```bash
     ngrok http 8050 > ngrok.log 2>&1 &
     ```

## Usage
1. **Start the System**:
   - Manually:
     ```bash
     source venv/bin/activate
     python3 app.py
     ```
   - Via script:
     ```bash
     ./start.sh
     ```

2. **Access the Dashboard**:
   - Local: Open `http://127.0.0.1:8050` in a browser (e.g., Firefox).
   - Remote: Use the ngrok URL from `ngrok.log`.
   - Login with username `admin` and password `password123`.

3. **Navigate the Dashboard**:
   - **Home Page**: View status summary, current readings, and historical charts.
   - **Meter Pages**: Access via dropdown (e.g., `/meter/2` for EssentialLoad) for detailed parameters.
   - **Download Data**: Enter `secure123` to download `meter_data_1year.csv`.

4. **Stop the System**:
   ```bash
   ./stop.sh
   ```

## Troubleshooting
- **Callback Failed Errors**:
  - Check logs:
    ```bash
    cat app.log dashboard_audit.log modbus_reader.log ngrok.log
    ```
  - Verify `meter_data.csv` and `daily_data.db`:
    ```bash
    ls -l meter_data.csv daily_data.db
    head -n 5 meter_data.csv
    ```
  - Regenerate data:
    ```bash
    python3 DMF_Reader.py
    ```
- **Session Warnings**:
  - Ensure `app.py` includes `app.server.config['SECRET_KEY']`.
- **Negative Power Factor**:
  - Inspect `DMF_Reader.py` for `PF Average Received` calculation.
  - Check `modbus_reader.log` for raw Modbus data.
- **Resource Issues**:
  - Monitor CPU/memory:
    ```bash
    top
    ```
  - Check disk space:
    ```bash
    df -h
    ```
- **Configuration Issues**:
  - Test decryption:
    ```bash
    python3 -c "from cryptography.fernet import Fernet; import json; with open('config_key.key', 'rb') as f: key = f.read(); cipher = Fernet(key); with open('config.json', 'r') as f: encrypted_config = json.load(f); print(json.loads(cipher.decrypt(encrypted_config['encrypted_data'].encode()).decode()))"
    ```

## Contributing
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/YourFeature`).
3. Commit changes (`git commit -m "Add YourFeature"`).
4. Push to the branch (`git push origin feature/YourFeature`).
5. Open a Pull Request.

## License
This project is licensed under the MIT License.

## Contact
For issues or questions, open an issue on GitHub or contact the repository owner.