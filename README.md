# Fritz!Box DOCSIS Monitor for InfluxDB

This Python script fetches detailed DOCSIS (Cable Modem) channel statistics from an AVM Fritz!Box router using its web interface and writes the data into an InfluxDB v2 database. This allows for monitoring and visualization of cable connection quality over time using tools like Grafana.

## Requirements

* Python 3.x
* Python packages: `requests`, `influxdb-client`
    ```bash
    pip install requests influxdb-client
    ```
* AVM Fritz!Box **Cable** model (that provides DOCSIS stats via `data.lua?page=docInfo`). DSL models are not supported by this method.
* A Fritz!Box user account with permissions to access status information (Web interface login).
* An InfluxDB v2 instance (accessible from where the script runs).
* An InfluxDB API Token with **write permissions** for the target bucket.

## Configuration

Before running the script, you **must** edit the configuration section at the top of the Python file (`your_script_name.py`) and enter your specific details:

```python
# ==============================================================================
# --- SCRIPT CONFIGURATION ---
# --- PLEASE FILL IN YOUR DETAILS HERE ---
# ==============================================================================

# Fritz!Box Configuration
ROUTER_URL = "http://fritz.box"  # Or "[http://192.168.178.1](http://192.168.178.1)" etc.
# --- Replace with your actual Fritz!Box credentials ---
FRITZ_USERNAME = "YOUR_FRITZBOX_USERNAME"
FRITZ_PASSWORD = "YOUR_FRITZBOX_PASSWORD"

# InfluxDB v2 Configuration
# --- Replace with your actual InfluxDB details ---
INFLUX_URL = "http://YOUR_INFLUXDB_IP_OR_HOSTNAME:8086" # E.g., "[http://192.168.1.10:8086](http://192.168.1.10:8086)"
INFLUX_TOKEN = "YOUR_INFLUXDB_API_TOKEN"    # Your InfluxDB API Token (with write permissions)
INFLUX_ORG = "YOUR_INFLUXDB_ORGANIZATION" # Your InfluxDB Organization
INFLUX_BUCKET = "fritzbox_docsis"      # The InfluxDB bucket name (create if needed)

# ==============================================================================
# --- End of Configuration ---
# ==============================================================================
