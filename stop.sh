#!/bin/bash

# Smart Substation Monitoring System stop script
PROJECT_DIR="/home/sseevri/SmartSubstationMonitoringSystem"

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project directory $PROJECT_DIR does not exist."
    exit 1
fi

cd "$PROJECT_DIR" || exit 1

# Stop DMF_Reader.py
if [ -f "dmf_reader.pid" ]; then
    PID=$(cat dmf_reader.pid)
    if ps -p "$PID" > /dev/null; then
        echo "Stopping DMF_Reader.py (PID: $PID)..."
        kill "$PID"
        rm dmf_reader.pid
    else
        echo "DMF_Reader.py is not running."
    fi
else
    echo "No PID file for DMF_Reader.py found."
fi

# Stop app.py
if [ -f "app.pid" ]; then
    PID=$(cat app.pid)
    if ps -p "$PID" > /dev/null; then
        echo "Stopping app.py (PID: $PID)..."
        kill "$PID"
        rm app.pid
    else
        echo "app.py is not running."
    fi
else
    echo "No PID file for app.py found."
fi

# Stop ngrok
if pgrep -x "ngrok" > /dev/null; then
    echo "Stopping ngrok..."
    pkill -x ngrok
else
    echo "ngrok is not running."
fi

echo "Smart Substation Monitoring System stopped."