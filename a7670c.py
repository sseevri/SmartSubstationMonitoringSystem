import serial
import time
import subprocess
import os
import serial.tools.list_ports
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class A7670C:
    """
    Python library for Simcom A7670C 4G LTE GSM module via USB.
    Handles AT commands for setup and PPP for internet connectivity.
    Assumes Linux host; PPP requires sudo privileges.
    """

    def __init__(self, port=None, baudrate=115200, timeout=5):
        """
        Initialize the module.
        :param port: Serial port (e.g., '/dev/ttyUSB0'). If None, auto-detects USB serial ports.
        :param baudrate: Default 115200; module supports autobauding.
        :param timeout: Serial timeout in seconds.
        """
        if port is None:
            port = self._auto_detect_port()
            if not port:
                raise ValueError("No USB serial port detected for A7670C.")
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        logging.info(f"Connected to A7670C on {port} at {baudrate} baud.")
        self._enable_autobaud_if_needed()

    def _auto_detect_port(self):
        """Auto-detect USB serial ports (looks for common VID:PID or descriptions)."""
        ports = serial.tools.list_ports.comports()
        for p in ports:
            if 'USB' in p.description or 'ACM' in p.description or 'Serial' in p.description:
                logging.info(f"Detected potential A7670C port: {p.device}")
                return p.device
        return None

    def _enable_autobaud_if_needed(self):
        """Set autobauding if initial AT fails."""
        ok, _ = self.send_at('AT')
        if not ok:
            self.send_at('AT+IPR=0')  # Enable autobauding
            time.sleep(1)
            self.ser.baudrate = 115200  # Reset to default

    def send_at(self, cmd, expected='OK', max_attempts=3, delay=1):
        """
        Send AT command and check response.
        :return: (success: bool, response: str)
        """
        for attempt in range(max_attempts):
            try:
                self.ser.write((cmd + '\r\n').encode())
                time.sleep(delay)
                response = self.ser.read(1024).decode().strip()
                if expected in response:
                    return True, response
                logging.warning(f"Attempt {attempt+1}: Unexpected response for '{cmd}': {response}")
            except Exception as e:
                logging.error(f"Error sending '{cmd}': {e}")
            time.sleep(1)
        return False, ''

    def check_module(self):
        """Check if module responds."""
        return self.send_at('AT')

    def check_sim(self):
        """Check SIM status."""
        return self.send_at('AT+CPIN?', expected='+CPIN: READY')

    def signal_strength(self):
        """Get signal strength (RSSI)."""
        ok, resp = self.send_at('AT+CSQ')
        if ok and '+CSQ:' in resp:
            rssi = resp.split('+CSQ:')[1].split(',')[0].strip()
            return int(rssi)
        return None

    def network_status(self):
        """Check network registration status."""
        ok, resp = self.send_at('AT+CREG?')
        if ok and '+CREG:' in resp:
            stat = resp.split('+CREG:')[1].split(',')[1].strip()
            return 'Registered' if stat in ['1', '5'] else 'Not Registered'
        return 'Unknown'

    def attach_network(self):
        """Attach to packet domain."""
        return self.send_at('AT+CGATT=1')

    def set_apn(self, apn, cid=1, pdp_type='IP'):
        """Set APN for PDP context."""
        return self.send_at(f'AT+CGDCONT={cid},"{pdp_type}","{apn}"')

    def activate_pdp(self, cid=1):
        """Activate PDP context."""
        return self.send_at(f'AT+CGACT=1,{cid}')

    def get_ip(self, cid=1):
        """Get assigned IP address."""
        ok, resp = self.send_at(f'AT+CGPADDR={cid}')
        if ok and '+CGPADDR:' in resp:
            ip = resp.split('+CGPADDR:')[1].split(',')[1].strip().strip('"')
            return ip
        return None

    def start_ppp(self, apn='internet', username='', password='', interface='ppp0'):
        """
        Start PPP connection for internet (Linux only; requires sudo).
        Generates a chat script and calls pppd.
        :return: (success: bool, output: str)
        """
        chat_script = f"""
ABORT BUSY
ABORT 'NO CARRIER'
ABORT VOICE
ABORT 'NO DIALTONE'
ABORT 'NO DIAL TONE'
ABORT 'NO ANSWER'
ABORT DELAYED
TIMEOUT 120
'' ATZ
OK AT+CGDCONT=1,"IP","{apn}"
OK ATD*99#
CONNECT ''
"""
        script_path = '/tmp/a7670c_chat'
        with open(script_path, 'w') as f:
            f.write(chat_script)

        ppp_cmd = [
            'sudo', 'pppd', self.ser.port, '115200', 'defaultroute', 'usepeerdns',
            'noauth', 'persist', 'nodetach', 'connect', f'/usr/sbin/chat -v -f {script_path}'
        ]
        if username and password:
            ppp_cmd.extend([f'user {username}', f'password {password}'])

        try:
            process = subprocess.Popen(ppp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = process.communicate(timeout=30)
            if process.returncode == 0:
                logging.info(f"PPP started on {interface}")
                return True, output.decode()
            else:
                logging.error(f"PPP failed: {error.decode()}")
                return False, error.decode()
        except Exception as e:
            logging.error(f"Error starting PPP: {e}")
            return False, str(e)
        finally:
            os.remove(script_path)

    def stop_ppp(self, interface='ppp0'):
        """Stop PPP connection."""
        try:
            subprocess.run(['sudo', 'poff', interface], check=True)
            logging.info(f"PPP stopped on {interface}")
            return True
        except Exception as e:
            logging.error(f"Error stopping PPP: {e}")
            return False

    def close(self):
        """Close serial connection."""
        if self.ser.is_open:
            self.ser.close()
            logging.info("Serial connection closed.")

# Usage Example (add to your script):
# modem = A7670C(port='/dev/ttyUSB0')  # Or auto-detect with None
# if modem.check_module()[0]:
#     modem.set_apn('your_apn')
#     modem.activate_pdp()
#     modem.start_ppp(apn='your_apn')
# modem.close()