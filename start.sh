#!/bin/bash

# Smart Substation Monitoring System start script
# Directory where the project files are located
PROJECT_DIR="/home/sseevri/SmartSubstationMonitoringSystem"

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project directory $PROJECT_DIR does not exist."
    exit 1
fi

cd "$PROJECT_DIR" || exit 1

# Check if config_key.key exists
if [ ! -f "config_key.key" ]; then
    echo "Error: config_key.key not found. Run encrypt_config.py first."
    exit 1
fi

# Check if ngrok is running, start if not
if ! pgrep -x "ngrok" > /dev/null; then
    echo "Starting ngrok..."
    nohup ngrok http 8050 > ngrok.log 2>&1 &
    sleep 2
    echo "ngrok started. Check ngrok.log for details."
else
    echo "ngrok is already running."
fi

# Start DMF_Reader.py
if [ -f "DMF_Reader.py" ]; then
    echo "Starting DMF_Reader.py..."
    nohup python3 DMF_Reader.py > dmf_reader.log 2>&1 &
    echo $! > dmf_reader.pid
else
    echo "Error: DMF_Reader.py not found."
    exit 1
fi

# Start app.py
if [ -f "app.py" ]; then
    echo "Starting app.py..."
    nohup python3 app.py > app.log 2>&1 &
    echo $! > app.pid
else
    echo "Error: app.py not found."
    exit 1
fi

echo "Smart Substation Monitoring System started successfully."
echo "Access the dashboard via the ngrok URL (check ngrok.log)."