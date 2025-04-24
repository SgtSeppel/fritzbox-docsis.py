import requests
import urllib3
import xml.etree.ElementTree as ET
import hashlib
import sys
import json
import datetime # Needed for timestamps
from influxdb_client import InfluxDBClient, Point, WritePrecision # InfluxDB v2 Client
from influxdb_client.client.write_api import SYNCHRONOUS # Synchronous writing (simpler)
# Install InfluxDB client if needed: pip install influxdb-client

# ==============================================================================
# --- SCRIPT CONFIGURATION ---
# --- PLEASE FILL IN YOUR DETAILS HERE ---
# ==============================================================================

# Fritz!Box Configuration
ROUTER_URL = "http://fritz.box"  # Or "http://192.168.178.1" etc.
# --- Replace with your actual Fritz!Box credentials ---
FRITZ_USERNAME = "YOUR_FRITZBOX_USERNAME"
FRITZ_PASSWORD = "YOUR_FRITZBOX_PASSWORD"

# InfluxDB v2 Configuration
# --- Replace with your actual InfluxDB details ---
INFLUX_URL = "http://YOUR_INFLUXDB_IP_OR_HOSTNAME:8086" # E.g., "http://192.168.1.10:8086"
INFLUX_TOKEN = "YOUR_INFLUXDB_API_TOKEN"    # Your InfluxDB API Token (with write permissions)
INFLUX_ORG = "YOUR_INFLUXDB_ORGANIZATION" # Your InfluxDB Organization
INFLUX_BUCKET = "fritzbox_docsis"      # The InfluxDB bucket name (create if needed)

# ==============================================================================
# --- End of Configuration ---
# ==============================================================================

# --- Suppress the InsecureRequestWarning from urllib3 ---
# --- Use verify=False with caution, especially on untrusted networks ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fb_get_sid():
    """
    Logs into the Fritz!Box using global config (ROUTER_URL, FRITZ_USERNAME,
    FRITZ_PASSWORD) and returns a Session ID (SID).
    Exits the script on failure.
    """
    # Use global configuration variables
    fritzbox = ROUTER_URL
    fritz_user = FRITZ_USERNAME
    fritz_pw = FRITZ_PASSWORD

    sid = "0000000000000000" # Initial invalid SID

    if not fritz_user or not fritz_pw:
         print("Error: FRITZ_USERNAME or FRITZ_PASSWORD not set in configuration.", file=sys.stderr)
         sys.exit(1)

    try:
        session = requests.Session()
        session.verify = False # Disables SSL certificate verification
        login_url = fritzbox + "/login_sid.lua"

        initial_response = session.get(login_url, timeout=10)
        initial_response.raise_for_status()
        tree = ET.fromstring(initial_response.content)
        sid = tree.findtext("SID")

        if sid == "0000000000000000":
            challenge = tree.findtext("Challenge")
            if not challenge:
                print("Error: Could not find Challenge in Fritz!Box response.", file=sys.stderr)
                sys.exit(1)

            hash_me = (challenge + "-" + fritz_pw).encode("UTF-16LE")
            hashed = hashlib.md5(hash_me).hexdigest()
            response_value = challenge + "-" + hashed
            auth_params = {"username": fritz_user, "response": response_value}

            auth_response = session.get(login_url, params=auth_params, timeout=10)
            auth_response.raise_for_status()
            tree = ET.fromstring(auth_response.content)
            sid = tree.findtext("SID")

            if sid == "0000000000000000":
                block_time = tree.findtext("BlockTime")
                error_msg = "fb_get_sid: Login failed. Check username/password."
                if block_time and int(block_time) > 0:
                    error_msg += f" Login blocked for {block_time} seconds."
                print(error_msg, file=sys.stderr)
                sys.exit(1)

    except requests.exceptions.Timeout:
        print(f"fb_get_sid: Timeout connecting to {fritzbox}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
         print(f"fb_get_sid: HTTP error during login: {e.response.status_code} {e.response.reason}", file=sys.stderr)
         sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"fb_get_sid: Network error during login: {e}", file=sys.stderr)
        sys.exit(1)
    except ET.ParseError as e:
        print(f"fb_get_sid: Error parsing XML response from Fritz!Box: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"fb_get_sid: An unexpected error occurred during login: {e}", file=sys.stderr)
        sys.exit(1)

    return sid

# --- Helper functions for safe type conversion ---
def safe_float(value, default=None):
    """Safely converts value to Float, returns default on error."""
    if value is None:
        return default
    try:
        return float(str(value).replace(',', '.'))
    except (ValueError, TypeError):
        return default

def safe_int(value, default=None):
    """Safely converts value to Integer, returns default on error."""
    if value is None:
        return default
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default

# --- Main execution logic ---
def main():
    # Get Session ID using global configuration
    session_id = fb_get_sid()
    # Session ID is no longer printed here

    if not (session_id and session_id != "0000000000000000"):
        # fb_get_sid should exit on failure, but double-check
        print(f"Error: Could not get a valid Session ID after login attempt.", file=sys.stderr)
        sys.exit(1)

    print(f"\nFetching DOCSIS channel information from data.lua (page=docInfo)...")
    data_page_url = f"{ROUTER_URL}/data.lua" # Use global config
    payload = {'sid': session_id, 'page': 'docInfo'}
    docsis_info = None # Initialize for error case

    try:
        response_data = requests.post(data_page_url, data=payload, verify=False, timeout=15)
        response_data.raise_for_status()
        docsis_info = response_data.json()

    except requests.exceptions.Timeout:
        print(f"Error: Timeout during request to {data_page_url} (POST, page=docInfo).", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Error: HTTP error accessing {data_page_url} (POST, page=docInfo): {e.response.status_code} {e.response.reason}", file=sys.stderr)
        if e.response.status_code == 403:
             print("Hint: Received 403 Forbidden. The Session ID might be invalid/expired or access to 'page=docInfo' is not allowed.", file=sys.stderr)
        print(f"Received text on error:\n{e.response.text}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Error: Could not connect to {data_page_url} (POST, page=docInfo): {e}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.JSONDecodeError as e:
        print(f"Error: The response from {data_page_url} (POST, page=docInfo) was not valid JSON: {e}", file=sys.stderr)
        if 'response_data' in locals() and hasattr(response_data, 'text'):
             print("Received text:", response_data.text, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while fetching data.lua (page=docInfo): {e}", file=sys.stderr)
        sys.exit(1)

    # --- Prepare data for InfluxDB ---
    print("\nPreparing data points for InfluxDB...")
    points = []
    current_time = datetime.datetime.utcnow()

    channel_sources = [
        (docsis_info.get('data', {}).get('channelDs', {}).get('docsis30', []), "downstream", "3.0"),
        (docsis_info.get('data', {}).get('channelDs', {}).get('docsis31', []), "downstream", "3.1"),
        (docsis_info.get('data', {}).get('channelUs', {}).get('docsis30', []), "upstream",   "3.0"),
        (docsis_info.get('data', {}).get('channelUs', {}).get('docsis31', []), "upstream",   "3.1"),
    ]

    for channel_list, direction, docsis_version in channel_sources:
        if not channel_list:
            continue
        for channel in channel_list:
            channel_id_for_msg = channel.get('channelID', 'Unknown')
            try:
                p = Point("docsis_channel_metrics")
                p.time(current_time, WritePrecision.S)

                # Tags
                channel_id = channel.get('channelID')
                if channel_id is not None: p.tag("channel_id", str(channel_id))
                p.tag("direction", direction)
                p.tag("docsis_version", docsis_version)
                frequency_str = channel.get('frequency', '')
                if frequency_str: p.tag("frequency_str", frequency_str)
                modulation = channel.get('modulation') or channel.get('type')
                if modulation: p.tag("modulation", modulation)

                # Fields
                power = safe_float(channel.get('powerLevel'))
                if power is not None: p.field("power_level", power)
                corr = safe_int(channel.get('corrErrors'))
                if corr is not None: p.field("corr_errors", corr)
                non_corr = safe_int(channel.get('nonCorrErrors'))
                if non_corr is not None: p.field("non_corr_errors", non_corr)

                if direction == "downstream":
                    mse = safe_float(channel.get('mse'))
                    if mse is not None: p.field("mse", mse)
                    if docsis_version == "3.0":
                        latency = safe_float(channel.get('latency'))
                        if latency is not None: p.field("latency", latency)
                    elif docsis_version == "3.1":
                        mer = safe_float(channel.get('mer'))
                        if mer is not None: p.field("mer", mer)
                        plc = safe_int(channel.get('plc'))
                        if plc is not None: p.field("plc", plc)
                if docsis_version == "3.1":
                     fft = channel.get('fft')
                     if fft: p.field("fft", fft)
                if direction == "upstream":
                     if docsis_version == "3.0":
                          multiplex = channel.get('multiplex')
                          if multiplex: p.field("multiplex", multiplex)
                     elif docsis_version == "3.1":
                          activesub = safe_int(channel.get('activesub'))
                          if activesub is not None: p.field("activesub", activesub)

                # Check if any fields were actually added
                if p._fields:
                    points.append(p)
                else:
                     print(f"Warning: Could not extract valid fields for channel ID {channel_id_for_msg} ({direction}/{docsis_version}). Point will not be added.", file=sys.stderr)

            except Exception as e:
                print(f"Error processing channel ({direction}/{docsis_version}, ID {channel_id_for_msg}): {e}", file=sys.stderr)
                print(f"Channel data: {channel}", file=sys.stderr)


    if not points:
        print("No valid channel data points found to write to InfluxDB.")
        sys.exit(0)

    # --- Write data to InfluxDB ---
    print(f"\nAttempting to write {len(points)} data points to InfluxDB...")
    # Use global configuration variables for InfluxDB
    print(f"  URL: {INFLUX_URL}, Org: {INFLUX_ORG}, Bucket: {INFLUX_BUCKET}")
    display_token = INFLUX_TOKEN[:4] + "..." + INFLUX_TOKEN[-4:] if len(INFLUX_TOKEN) > 8 else "TOKEN_NOT_SHOWN"

    # Check if InfluxDB config is set
    if not INFLUX_URL or not INFLUX_TOKEN or not INFLUX_ORG or not INFLUX_BUCKET:
        print("Error: InfluxDB configuration (URL, Token, Org, Bucket) is not fully set in the script.", file=sys.stderr)
        sys.exit(1)

    try:
        # Use 'with' statement for automatic client closing, use global config
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=20_000) as client:
            if not client.ping():
                 raise Exception("InfluxDB ping failed. Connection problem or incorrect URL/Token/Org?")

            write_api = client.write_api(write_options=SYNCHRONOUS)
            # Use global config for bucket and org
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
            print("Data successfully written to InfluxDB.")

    except Exception as e:
        print(f"Error writing to InfluxDB (URL: {INFLUX_URL}, Org: {INFLUX_ORG}, Bucket: {INFLUX_BUCKET}, Token: {display_token}): {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
