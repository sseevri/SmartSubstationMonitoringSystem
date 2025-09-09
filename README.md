# Smart Substation Monitoring System

## Overview

The **Smart Substation Monitoring System** is a web-based dashboard for real-time monitoring of electrical substations. Built using [Plotly Dash](https://dash.plotly.com/), it runs on a Raspberry Pi and displays meter data (e.g., voltage, current, power factor) from multiple meters, sourced from `meter_data.csv` and `daily_data.db`. The system supports secure access, data visualization, CSV export, Telegram alerts, and audit logging.

### Features
- **Real-Time Dashboard**: Displays current readings for five meters (Transformer, EssentialLoad, NonEssentialLoad, ColonyLoad, DGSetLoad) with status indicators.  
- **Meter-Specific Pages**: Detailed parameter tables for each meter (e.g., `/meter/2` for EssentialLoad).  
- **Historical Charts**: Visualizes yesterday’s and today’s data for voltage, current, watts, and power factor using SQLite databases.  
- **Secure Access**: Basic authentication and encrypted CSV download.  
- **Audit Logging**: Tracks system events in `dashboard_audit.log`.  
- **Telegram Bot Integration**: Sends real-time alerts and periodic meter readings to a Telegram group or private chat.  
- **Encrypted Configuration (local only)**: Sensitive configs are excluded from GitHub and must be maintained securely on the Raspberry Pi.  

---

## Repository Structure
```
SmartSubstationMonitoringSystem/
├── app.py                 # Dash application for the web dashboard
├── DMF_Reader.py          # Reads meter data and updates CSV/database
├── datalogger.py          # Handles data logging to SQLite
├── requirements.txt       # Python dependencies
├── telegram_meter_bot.py  # Telegram bot for sending alerts
├── send_test_message.py   # Script to test Telegram bot messages
├── a7670c.py              # GSM module integration (A7670C)
├── anomaly_detector.py    # Detects anomalies in meter readings
├── docs/                  # Documentation folder
│   ├── equipment_specs.txt
│   └── maintenance_procedures.txt
├── meter_data.csv         # Stores real-time meter data
├── daily_data.db          # SQLite database for daily data
├── app.log                # Application logs
├── dashboard_audit.log    # Audit logs
├── modbus_reader.log      # Modbus communication logs
└── ngrok.log              # ngrok tunneling logs
```

⚠️ Note: Sensitive files like `config.json` and `encrypt_config.py` are **no longer tracked** in GitHub for security reasons.  

---

## Prerequisites
- **Hardware**: Raspberry Pi (e.g., Raspberry Pi 4) with Raspberry Pi OS.  
- **Software**:  
  - Python 3.8+  
  - Virtualenv  
  - ngrok (optional, for remote access)  
- **Dependencies**: Listed in `requirements.txt`.  

---

## Setup Instructions

1. **Clone the Repository**:
   ```bash
   git clone git@github.com:<your-username>/SmartSubstationMonitoringSystem.git
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

4. **Configure Telegram Bot**:
   - Create a bot via [BotFather](https://t.me/botfather) on Telegram.  
   - Get the **bot token** and your **chat ID** (use [@userinfobot](https://t.me/userinfobot) for user chat ID or add bot to a group and check logs).  
   - Create a **local config file** `config.json` (not stored in GitHub) with:
     ```json
     {
       "telegram_token": "YOUR_BOT_TOKEN",
       "chat_id": "YOUR_GROUP_OR_USER_CHAT_ID"
     }
     ```
   - Test it:
     ```bash
     python3 send_test_message.py
     ```

5. **Initialize Data**:
   ```bash
   python3 DMF_Reader.py
   ```

6. **Set File Permissions (recommended)**:
   ```bash
   chmod 600 config.json
   chmod 644 *.py
   chmod 664 meter_data.csv daily_data.db
   ```

7. **(Optional) Set Up Systemd Service**:
   ```ini
   [Unit]
   Description=Smart Substation Monitoring System
   After=network.target

   [Service]
   User=sseevri
   WorkingDirectory=/home/sseevri/SmartSubstationMonitoringSystem
   ExecStart=/usr/bin/python3 app.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   Enable and start:
   ```bash
   sudo systemctl enable smart-substation.service
   sudo systemctl start smart-substation.service
   ```

8. **(Optional) Set Up ngrok**:
   ```bash
   ngrok http 8050 > ngrok.log 2>&1 &
   ```

---

## Usage

1. **Start the System**:
   ```bash
   source venv/bin/activate
   python3 app.py
   ```

2. **Access the Dashboard**:
   - Local: [http://127.0.0.1:8050](http://127.0.0.1:8050)  
   - Remote: Use the ngrok URL from `ngrok.log`  

3. **Telegram Alerts**:
   - System will automatically send hourly readings and anomaly alerts.  

4. **Stop the System**:
   ```bash
   pkill -f app.py
   ```

---

## Versioning
- **v1.0 (Current)**:  
  - Added Telegram bot integration.  
  - Added anomaly detection module.  
  - Cleaned repository to exclude sensitive files.  

---

## Troubleshooting
- **Telegram Bot Not Sending**:  
  - Verify `telegram_token` and `chat_id` in `config.json`.  
  - Run `python3 send_test_message.py` for debugging.  

- **Dashboard Issues**:  
  - Check `app.log`, `dashboard_audit.log`, and `modbus_reader.log`.  

- **Database Issues**:  
  - Verify `meter_data.csv` and `daily_data.db` exist.  
  - Regenerate with `python3 DMF_Reader.py`.  

---

## Contributing
1. Fork the repository.  
2. Create a feature branch (`git checkout -b feature/YourFeature`).  
3. Commit changes (`git commit -m "Add YourFeature"`).  
4. Push to the branch (`git push origin feature/YourFeature`).  
5. Open a Pull Request.  

---

## License
This project is licensed under the MIT License.  

---

## Contact
For issues or questions, open an issue on GitHub or contact the repository owner.  
