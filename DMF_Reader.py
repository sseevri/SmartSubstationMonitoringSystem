import serial
import struct
import time
from datetime import datetime, timedelta
import logging
import pandas as pd
import os
import json
from cryptography.fernet import Fernet, InvalidToken
from datalogger import init_db, log_to_db, init_daily_db, log_to_daily_db, copy_daily_to_yearly
from shared_config import REGISTER_MAP, VALIDATION_RANGES

# Load and decrypt configuration
try:
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
    decrypted_config = json.loads(cipher.decrypt(encrypted_config['encrypted_data'].encode()).decode())
except (FileNotFoundError, json.JSONDecodeError, InvalidToken) as e:
    logging.critical(f"Failed to load or decrypt configuration: {e}")
    raise SystemExit(f"Failed to load or decrypt configuration: {e}") from e

SERIAL_PORT = decrypted_config['serial_port']
BAUD_RATE = decrypted_config['baud_rate']
TIMEOUT = decrypted_config['serial_timeout']
PARITY = serial.PARITY_EVEN
STOPBITS = serial.STOPBITS_ONE
BYTESIZE = serial.EIGHTBITS
POLLING_INTERVAL = decrypted_config['polling_interval']
SQLITE_LOG_INTERVAL = decrypted_config['sqlite_log_interval']
METER_IDS = decrypted_config['meter_ids']
CSV_FILE = decrypted_config['csv_file']
DB_PATH = decrypted_config['db_path']
DB_DAILY_PATH = decrypted_config['db_daily_path']
LOG_FILE = decrypted_config['log_file']

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=LOG_FILE
)

MODBUS_READ_HOLDING_REGISTERS = 0x03


def calculate_crc(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, byteorder='little')

def build_read_holding_registers(slave_id, start_address, quantity):
    address = start_address - 40001
    frame = bytes([slave_id, MODBUS_READ_HOLDING_REGISTERS]) + \
            address.to_bytes(2, byteorder='big') + \
            quantity.to_bytes(2, byteorder='big')
    crc = calculate_crc(frame)
    return frame + crc

def parse_float(data, byte_order='big'):
    if len(data) != 4:
        raise ValueError(f"Expected 4 bytes for float, got {len(data)}")
    try:
        if byte_order == 'big':
            # This handles a specific word-swapped big-endian format (CDAB)
            swapped_data = data[2:4] + data[0:2]
            value = struct.unpack('>f', swapped_data)[0]
        elif byte_order == 'little':
            value = struct.unpack('<f', data)[0]
        elif byte_order == 'big_endian':
            value = struct.unpack('>f', data)[0]
        else:
            raise ValueError(f"Unsupported byte order for float: {byte_order}")

        if abs(value) > 1e10:
            raise ValueError("Unreasonable value")
        return value
    except (ValueError, struct.error) as e:
        logging.debug(f"Parse float failed: {e}")
        raise

def parse_integer(data, dtype, byte_order='big'):
    try:
        if dtype == 'int16':
            return struct.unpack('>h' if byte_order == 'big' else '<h', data)[0]
        elif dtype == 'uint16':
            return struct.unpack('>H' if byte_order == 'big' else '<H', data)[0]
        elif dtype == 'int32':
            return struct.unpack('>i' if byte_order == 'big' else '<i', data)[0]
        elif dtype == 'uint32':
            return struct.unpack('>I' if byte_order == 'big' else '<I', data)[0]
        else:
            raise ValueError(f"Unsupported integer dtype: {dtype}")
    except struct.error as e:
        logging.debug(f"Parse integer failed: {e}")
        raise

def validate_data(data):
    """Validate data: enforce non-negative values and defined ranges."""
    validated_data = {}
    for name, value in data.items():
        if value is None:
            validated_data[name] = None
            continue
        if value < 0:
            logging.warning(f"Negative value for {name}: {value}. Setting to 0.")
            validated_data[name] = 0
            continue
        range_min, range_max = VALIDATION_RANGES.get(name, (0, float('inf')))
        if not (range_min <= value <= range_max):
            logging.warning(f"Invalid value for {name}: {value} (Range: {range_min}-{range_max})")
            validated_data[name] = None
        else:
            validated_data[name] = value
    return validated_data

def read_meter(ser, slave_id, registers, max_retries=2):
    data = {}
    comm_status = "OK"
    sorted_registers = sorted(registers, key=lambda x: x[2])
    i = 0
    while i < len(sorted_registers):
        start_name, start_dtype, start_addr = sorted_registers[i]
        
        # Determine quantity of registers to read based on data type
        quantity = 0
        if "Float" in start_dtype or "32" in start_dtype:
            quantity = 2
        else:
            quantity = 1

        j = i + 1
        while j < len(sorted_registers) and sorted_registers[j][2] == start_addr + quantity and quantity < 125:
            next_dtype = sorted_registers[j][1]
            if "Float" in next_dtype or "32" in next_dtype:
                quantity += 2
            else:
                quantity += 1
            j += 1

        for attempt in range(max_retries):
            try:
                if not ser.is_open:
                    ser.open()
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                request = build_read_holding_registers(slave_id, start_addr, quantity)
                ser.write(request)
                logging.debug(f"Meter {slave_id} attempt {attempt + 1} sent request for addr {start_addr}, qty {quantity}: {request.hex()}")
                time.sleep(0.2)
                
                expected_length = 5 + quantity * 2 # Slave ID (1) + Func Code (1) + Byte Count (1) + Data (qty*2) + CRC (2)
                response = ser.read(expected_length)
                logging.debug(f"Meter {slave_id} raw response for addr {start_addr}: {response.hex()}")

                if not response:
                    raise Exception("No response from meter")

                # CRC Validation
                received_crc = response[-2:]
                calculated_crc = calculate_crc(response[:-2])
                if received_crc != calculated_crc:
                    raise Exception(f"CRC mismatch. Received: {received_crc.hex()}, Calculated: {calculated_crc.hex()}")

                if response[0] != slave_id or response[1] != MODBUS_READ_HOLDING_REGISTERS:
                    raise Exception(f"Invalid response header: {response.hex()}")
                
                byte_count = response[2]
                if byte_count != quantity * 2:
                    raise Exception(f"Unexpected data length: {byte_count}")
                
                response_data = response[3:-2]
                
                for k in range(i, j):
                    name, dtype, addr = sorted_registers[k]
                    offset = (addr - start_addr) * 2
                    
                    if dtype == "Float":
                        value = parse_float(response_data[offset:offset+4], byte_order='big')
                        data[name] = value
                    elif dtype in ['int16', 'uint16']:
                        value = parse_integer(response_data[offset:offset+2], dtype)
                        data[name] = value
                    elif dtype in ['int32', 'uint32']:
                        value = parse_integer(response_data[offset:offset+4], dtype)
                        data[name] = value

                break  # Success
            except serial.SerialException as e:
                logging.error(f"Serial error in read_meter for meter {slave_id}: {e}")
                raise
            except Exception as e:
                logging.error(f"Meter {slave_id} attempt {attempt + 1} failed for addr {start_addr}: {e}")
                if attempt + 1 == max_retries:
                    for k in range(i, j):
                        name = sorted_registers[k][0]
                        data[name] = None
                    comm_status = "FAILED"
        i = j
    validated_data = validate_data(data)
    return validated_data, comm_status

def write_to_csv(date, time_str, meter_id, data, comm_status):
    """
    Write meter data to CSV.
    For performance, this function now appends to the CSV file.
    The 1-hour data retention policy should be handled by a separate, periodic cleanup process.
    """
    filename = CSV_FILE
    datetime_str = f"{date} {time_str}"
    status = 'OK'
    power_current_params = ['Watts Total', 'Current Total', 'VA Total', 'VAR Total']
    if comm_status == "OK" and all(data.get(param, 0.0) == 0.0 for param in power_current_params):
        if meter_id == 1:
            status = 'EB supply Off'
        elif meter_id == 5:
            status = 'DG set Off'
        else:
            status = 'POWER_FAIL'
    elif comm_status == "OK":
        if meter_id == 1:
            status = 'EB supply On'
        elif meter_id == 5:
            status = 'DG set On'

    row = {
        'Date': date,
        'Time': time_str,
        'DateTime': datetime_str,
        'Meter_ID': meter_id,
        'comm_status': comm_status,
        'status': status
    }
    row.update({name: "{:.2f}".format(value) if value is not None else "None" for name, value in data.items()})
    
    header = not os.path.exists(filename)
    df = pd.DataFrame([row])
    df.to_csv(filename, mode='a', header=header, index=False, encoding='utf-8')

def open_serial_port(max_retries=3):
    """Attempt to open serial port with retries."""
    for attempt in range(max_retries):
        try:
            ser = serial.Serial(
                port=SERIAL_PORT,
                baudrate=BAUD_RATE,
                parity=PARITY,
                stopbits=STOPBITS,
                bytesize=BYTESIZE,
                timeout=TIMEOUT
            )
            logging.info(f"Serial port opened: {SERIAL_PORT}")
            return ser
        except serial.SerialException as e:
            logging.error(f"Failed to open serial port (attempt {attempt + 1}): {e}")
            time.sleep(2)
    logging.critical("Could not open serial port after max retries")
    raise serial.SerialException("Failed to open serial port")

def main():
    init_db(DB_PATH)
    init_daily_db(DB_DAILY_PATH)
    ser = None
    try:
        ser = open_serial_port()
        last_log_time = time.time()
        last_day = datetime.now().day
        meter_data = {meter_id: {} for meter_id in METER_IDS}
        while True:
            now = datetime.now()
            date = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H:%M:%S')
            logging.info(f"Polling cycle started at {date} {time_str}")
            print(f"\n=== Polling Cycle: {date} {time_str} ===")
            for meter_id in METER_IDS:
                print(f"\nMeter ID: {meter_id}")
                try:
                    data, comm_status = read_meter(ser, meter_id, REGISTER_MAP)
                    if comm_status == "FAILED":
                        print(f"Error: No response from meter")
                        meter_data[meter_id] = data
                    else:
                        power_current_params = [
                            'Watts Total', 'Current Total', 'VA Total', 'VAR Total'
                        ]
                        if all(data.get(param, 0.0) == 0.0 for param in power_current_params):
                            print("Warning: All power and current values are 0. Check load connection or CT wiring.")
                        for name, value in data.items():
                            if value is None:
                                print(f"{name}: Failed to read")
                            else:
                                print(f"{name}: {value:.2f}")
                        meter_data[meter_id] = data
                        write_to_csv(date, time_str, meter_id, data, comm_status)
                    logging.info(f"Meter {meter_id} data: {data}, comm_status: {comm_status}")
                except serial.SerialException as e:
                    logging.error(f"Serial error for meter {meter_id}: {e}")
                    if ser and ser.is_open:
                        ser.close()
                    try:
                        ser = open_serial_port()
                    except serial.SerialException:
                        logging.critical("Could not reopen serial port. Will retry in next cycle.")
                        time.sleep(POLLING_INTERVAL)
            
            current_time = time.time()

            # Check for day change to copy daily data and reset
            if now.day != last_day:
                copy_daily_to_yearly(DB_DAILY_PATH, DB_PATH)
                init_daily_db(DB_DAILY_PATH)
                last_day = now.day
                logging.info("Daily database copied to yearly and reset")

            if current_time - last_log_time >= SQLITE_LOG_INTERVAL:
                for meter_id in METER_IDS:
                    try:
                        log_to_db(DB_PATH, date, time_str, meter_id, meter_data.get(meter_id, {}))
                        log_to_daily_db(DB_DAILY_PATH, date, time_str, meter_id, meter_data.get(meter_id, {}))
                    except Exception as e:
                        logging.error(f"Failed to log data to database for meter {meter_id}: {e}")
                last_log_time = current_time
                logging.info(f"Logged data to SQLite (1-year and daily) for all meters at {date} {time_str}")
            
            print(f"\nWaiting {POLLING_INTERVAL} seconds for next poll...")
            time.sleep(POLLING_INTERVAL)
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
    except Exception as e:
        logging.critical(f"Unhandled program error: {e}", exc_info=True)
    finally:
        if ser and ser.is_open:
            ser.close()
            logging.info("Serial port closed")


if __name__ == "__main__":
    main()
