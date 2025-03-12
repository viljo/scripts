#!/usr/bin/env python3
import argparse
import json
import math
import socket
import threading
import time
import numpy as np

# Global dictionaries for aircraft filters and TCP clients.
filters = {}  # Key: icaoAddress, Value: KalmanFilterLocal instance
filters_lock = threading.Lock()

clients = []
clients_lock = threading.Lock()

# ---------------------------
# Coordinate conversion functions
# ---------------------------
def latlon_to_xy(lat, lon, ref_lat, ref_lon):
    """Convert lat,lon (in degrees) to local x,y in meters using an equirectangular approximation."""
    # Approximate meters per degree at the reference latitude.
    rad = math.radians(ref_lat)
    m_per_deg_lon = 111320 * math.cos(rad)
    m_per_deg_lat = 110574
    x = (lon - ref_lon) * m_per_deg_lon
    y = (lat - ref_lat) * m_per_deg_lat
    return x, y

def xy_to_latlon(x, y, ref_lat, ref_lon):
    """Convert local x,y in meters back to lat,lon using the same approximation."""
    rad = math.radians(ref_lat)
    m_per_deg_lon = 111320 * math.cos(rad)
    m_per_deg_lat = 110574
    lat = y / m_per_deg_lat + ref_lat
    lon = x / m_per_deg_lon + ref_lon
    return lat, lon

# ---------------------------
# Kalman Filter Class for Local Coordinates
# ---------------------------
class KalmanFilterLocal:
    def __init__(self, lat, lon, alt_m, vx, vy, v_alt, icao, callsign, squawk):
        # Use the first measurement as the reference for local coordinates.
        self.ref_lat = lat
        self.ref_lon = lon
        self.icao = icao
        self.callsign = callsign
        self.squawk = squawk

        x, y = latlon_to_xy(lat, lon, self.ref_lat, self.ref_lon)
        self.alt = alt_m  # altitude in meters

        # State vector: [x, y, alt, vx, vy, v_alt]
        self.state = np.array([x, y, self.alt, vx, vy, v_alt]).reshape(6, 1)
        # Initial covariance (tuned arbitrarily)
        self.P = np.eye(6) * 100.0
        # Process noise covariance (tune as needed)
        self.Q = np.eye(6) * 0.1
        # Measurement noise covariance for [x, y, alt]
        self.R = np.eye(3) * 10.0
        self.last_time = time.time()

    def predict(self, dt):
        """Perform the prediction step with time increment dt."""
        F = np.array([
            [1, 0, 0, dt, 0,  0],
            [0, 1, 0, 0,  dt, 0],
            [0, 0, 1, 0,  0,  dt],
            [0, 0, 0, 1,  0,  0],
            [0, 0, 0, 0,  1,  0],
            [0, 0, 0, 0,  0,  1]
        ])
        self.state = F @ self.state
        self.P = F @ self.P @ F.T + self.Q
        self.last_time += dt
        return self.state

    def update(self, lat, lon, alt_m, current_time):
        """Update the filter with a new measurement (lat, lon in degrees, alt in meters)."""
        # Convert measurement to local x,y coordinates
        z_x, z_y = latlon_to_xy(lat, lon, self.ref_lat, self.ref_lon)
        z_alt = alt_m
        z = np.array([z_x, z_y, z_alt]).reshape(3, 1)

        # Use the elapsed time since the last update for prediction.
        dt = current_time - self.last_time
        if dt > 0:
            self.predict(dt)
        H = np.array([
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0]
        ])
        y = z - (H @ self.state)
        S = H @ self.P @ H.T + self.R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.state = self.state + K @ y
        self.P = (np.eye(6) - K @ H) @ self.P
        self.last_time = current_time

# ---------------------------
# SBS Message Generation from Filter
# ---------------------------
def generate_sbs_from_filter(kf, current_time):
    """
    Generate an SBS-formatted CSV line from the predicted state of a KalmanFilterLocal.
    Uses the current time for the generated/logged timestamps.
    """
    # Calculate dt since last update and predict forward to now.
    dt = current_time - kf.last_time
    if dt > 0:
        kf.predict(dt)
    state = kf.state.flatten()
    x, y, alt, vx, vy, v_alt = state

    # Convert back to lat, lon using the filter's reference.
    lat, lon = xy_to_latlon(x, y, kf.ref_lat, kf.ref_lon)
    # Convert altitude from meters to feet.
    alt_ft = int(round(alt * 3.28084))
    # Compute ground speed in m/s from vx, vy and convert to knots.
    speed_mps = math.hypot(vx, vy)
    speed_knots = int(round(speed_mps * 1.94384))
    # Compute track in degrees: heading from north.
    # Note: math.atan2 returns angle in radians from the x-axis (east); we adjust.
    track_deg = math.degrees(math.atan2(vx, vy))
    if track_deg < 0:
        track_deg += 360
    track_deg = int(round(track_deg))
    # Vertical rate: convert v_alt from m/s to ft/min.
    vr_ft_min = int(round(v_alt * 196.850394))
    
    # Generate date and time strings.
    now_struct = time.localtime(current_time)
    date_str = time.strftime("%Y/%m/%d", now_struct)
    time_str = time.strftime("%H:%M:%S", now_struct)
    
    # SBS fields (22 fields, many left empty or default):
    fields = [
        "MSG",                 # Message type
        "3",                   # Transmission type (3 for airborne position)
        "",                    # Session ID
        "",                    # Aircraft ID
        kf.icao.upper(),       # HexIdent
        "",                    # Flight ID
        date_str,              # Date Generated
        time_str,              # Time Generated
        date_str,              # Date Logged
        time_str,              # Time Logged
        kf.callsign.strip(),   # Callsign
        str(alt_ft),           # Altitude (ft)
        str(speed_knots),      # Ground Speed (knots)
        str(track_deg),        # Track (deg)
        f"{lat:.5f}",          # Latitude
        f"{lon:.5f}",          # Longitude
        str(vr_ft_min),        # Vertical Rate (ft/min)
        str(kf.squawk),        # Squawk
        "0",                   # Alert
        "0",                   # Emergency
        "0",                   # SPI
        "0"                    # OnGround
    ]
    return ",".join(fields)

# ---------------------------
# UDP Listener Thread
# ---------------------------
def udp_listener(udp_port, quiet):
    """
    Listen for incoming UDP JSON messages on the specified port.
    For each aircraft record, update or create a Kalman filter.
    """
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(("", udp_port))
    if not quiet:
        print(f"UDP listener started on port {udp_port}")
    while True:
        try:
            data, addr = udp_sock.recvfrom(65535)
            if not quiet:
                print(f"Received UDP packet from {addr}")
            json_str = data.decode("utf-8")
            json_data = json.loads(json_str)
            current_time = time.time()
            if "aircraft" not in json_data:
                if not quiet:
                    print("UDP JSON has no 'aircraft' field.")
                continue
            with filters_lock:
                for ac in json_data["aircraft"]:
                    icao = ac.get("icaoAddress", "").upper()
                    if not icao:
                        continue
                    lat = ac.get("latDD")
                    lon = ac.get("lonDD")
                    altitudeMM = ac.get("altitudeMM")
                    if lat is None or lon is None or altitudeMM is None:
                        continue
                    # Convert altitude from mm to meters.
                    alt_m = float(altitudeMM) / 1000.0
                    # Determine initial velocity using horVelocityCMS and headingDE2 if available.
                    v_cm_s = ac.get("horVelocityCMS", 0)
                    speed_mps = float(v_cm_s) / 100.0  # convert cm/s to m/s
                    heading_centi = ac.get("headingDE2", 0)
                    heading_deg = float(heading_centi) / 100.0
                    heading_rad = math.radians(heading_deg)
                    # In our coordinate system: x = east, y = north.
                    vx = speed_mps * math.sin(heading_rad)
                    vy = speed_mps * math.cos(heading_rad)
                    # Vertical velocity in m/s (from verVelocityCMS, cm/s to m/s)
                    v_alt = float(ac.get("verVelocityCMS", 0)) / 100.0
                    callsign = ac.get("callsign", "").strip()
                    squawk = ac.get("squawk", "")
                    # Update or create the filter.
                    if icao in filters:
                        # Update existing filter.
                        filters[icao].callsign = callsign  # update if changed
                        filters[icao].squawk = squawk
                        filters[icao].update(lat, lon, alt_m, current_time)
                    else:
                        # Create a new filter with the current measurement as reference.
                        filters[icao] = KalmanFilterLocal(lat, lon, alt_m, vx, vy, v_alt, icao, callsign, squawk)
                        if not quiet:
                            print(f"Created filter for aircraft {icao}")
        except Exception as e:
            if not quiet:
                print(f"Error in UDP listener: {e}")

# ---------------------------
# Prediction Thread (10 Hz)
# ---------------------------
def prediction_thread(quiet):
    """
    At 10 Hz, iterate over all aircraft filters, predict the state,
    generate an SBS message, and broadcast it to all connected TCP clients.
    """
    while True:
        current_time = time.time()
        messages = []
        with filters_lock:
            for icao, kf in list(filters.items()):
                try:
                    sbs_msg = generate_sbs_from_filter(kf, current_time)
                    messages.append(sbs_msg + "\n")
                except Exception as e:
                    if not quiet:
                        print(f"Error generating SBS for {icao}: {e}")
        # Broadcast all messages (if any)
        if messages:
            broadcast("".join(messages), quiet)
        time.sleep(0.1)

# ---------------------------
# TCP Server for SBS Output
# ---------------------------
def broadcast(message, quiet):
    """
    Send the given message (string) to all connected TCP clients.
    Remove clients that are disconnected.
    """
    global clients
    with clients_lock:
        for client in clients[:]:
            try:
                client.sendall(message.encode("utf-8"))
            except Exception as e:
                if not quiet:
                    print(f"Removing client due to error: {e}")
                clients.remove(client)
                try:
                    client.close()
                except:
                    pass

def tcp_server(listen_host, listen_port, quiet):
    """
    Start a TCP server that listens on the specified host and port.
    Accept incoming client connections and add them to the global client list.
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((listen_host, listen_port))
    server_sock.listen(5)
    if not quiet:
        print(f"TCP server listening on {listen_host or '0.0.0.0'}:{listen_port}")
    while True:
        try:
            client_sock, client_addr = server_sock.accept()
            with clients_lock:
                clients.append(client_sock)
            if not quiet:
                print(f"New client connected from {client_addr}")
        except Exception as e:
            if not quiet:
                print(f"Error accepting client connection: {e}")
            time.sleep(1)

# ---------------------------
# Main
# ---------------------------
def main():
    parser = argparse.ArgumentParser(
        description="UDP-to-TCP SBS server with Kalman filter prediction (10 Hz updates)."
    )
    parser.add_argument("--udp-port", "-u", type=int, default=6666,
                        help="UDP port for incoming JSON data (default: 6666)")
    parser.add_argument("--tcp-port", "-p", type=int, default=30103,
                        help="TCP port for SBS output to clients (default: 30103)")
    parser.add_argument("--listen-host", "-l", default="",
                        help="TCP listen address (default: all interfaces)")
    parser.add_argument("--quiet", action="store_true",
                        help="Run in quiet mode with no console output")
    args = parser.parse_args()
    quiet = args.quiet

    # Start UDP listener thread.
    udp_thread = threading.Thread(target=udp_listener, args=(args.udp_port, quiet), daemon=True)
    udp_thread.start()

    # Start prediction thread.
    pred_thread = threading.Thread(target=prediction_thread, args=(quiet,), daemon=True)
    pred_thread.start()

    # Start TCP server (runs in main thread).
    tcp_server(args.listen_host, args.tcp_port, quiet)

if __name__ == "__main__":
    main()
