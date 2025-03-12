#!/usr/bin/env python3
import argparse
import json
import socket
import threading
import time

# Global list of TCP client sockets and a lock for thread-safe access.
clients = []
clients_lock = threading.Lock()

def convert_aircraft_to_sbs(ac, quiet=False):
    """
    Convert a single aircraft JSON record to an SBS BaseStation formatted CSV line.
    
    SBS format (22 fields) is defined as:
      1. Message type (always "MSG")
      2. Transmission type (we use "3" for airborne position)
      3. Session ID (empty)
      4. Aircraft ID (empty)
      5. HexIdent (from "icaoAddress")
      6. Flight ID (empty)
      7. Date Generated (YYYY/MM/DD)
      8. Time Generated (HH:MM:SS)
      9. Date Logged (same as date generated)
     10. Time Logged (same as time generated)
     11. Callsign (trimmed)
     12. Altitude (ft) – converted from altitudeMM (mm)
     13. Ground Speed (knots) – from horVelocityCMS (cm/s)
     14. Track (deg) – from headingDE2 (centi-deg)
     15. Latitude – from latDD
     16. Longitude – from lonDD
     17. Vertical Rate (ft/min) – from verVelocityCMS (cm/s)
     18. Squawk – from squawk
     19. Alert – default "0"
     20. Emergency – default "0"
     21. SPI – default "0"
     22. OnGround – default "0"
     
    Returns the SBS message line as a string.
    """
    # Helper: get time/date from the "timeStamp" field (ISO8601 format)
    date_generated = ""
    time_generated = ""
    ts = ac.get("timeStamp", "")
    if ts:
        # Expect format like "YYYY-MM-DDTHH:MM:SSZ" or similar.
        try:
            date_part, time_part = ts.split("T")
            # Convert date to "YYYY/MM/DD"
            date_generated = date_part.replace("-", "/")
            # Remove trailing 'Z' if present and take HH:MM:SS
            time_generated = time_part.rstrip("Z")[:8]
        except Exception as e:
            if not quiet:
                print(f"Error parsing timeStamp '{ts}': {e}")

    hex_ident = ac.get("icaoAddress", "").upper()
    callsign = ac.get("callsign", "").strip()
    
    # Convert altitude from millimeters to feet.
    altitude_ft = ""
    if "altitudeMM" in ac:
        try:
            altitude_ft = str(int(round(float(ac["altitudeMM"]) * 0.00328084)))
        except Exception as e:
            if not quiet:
                print(f"Error converting altitudeMM: {e}")
    
    # Convert ground speed: horVelocityCMS (cm/s) to m/s then to knots.
    ground_speed = ""
    if "horVelocityCMS" in ac:
        try:
            # horVelocityCMS in cm/s -> m/s
            mps = float(ac["horVelocityCMS"]) / 100.0
            # 1 m/s ~ 1.94384 knots
            ground_speed = str(int(round(mps * 1.94384)))
        except Exception as e:
            if not quiet:
                print(f"Error converting horVelocityCMS: {e}")

    # Heading: from headingDE2 (centi-deg) to degrees.
    track = ""
    if "headingDE2" in ac:
        try:
            track = str(int(round(float(ac["headingDE2"]) / 100.0)))
        except Exception as e:
            if not quiet:
                print(f"Error converting headingDE2: {e}")

    # Latitude and Longitude as-is.
    latitude = str(ac.get("latDD", ""))
    longitude = str(ac.get("lonDD", ""))
    
    # Vertical rate: from verVelocityCMS (cm/s) to ft/min.
    vertical_rate = ""
    if "verVelocityCMS" in ac:
        try:
            # Convert cm/s to m/s then to ft/min: 1 m/s = 196.850394 ft/min.
            vertical_rate = str(int(round((float(ac["verVelocityCMS"]) / 100.0) * 196.850394)))
        except Exception as e:
            if not quiet:
                print(f"Error converting verVelocityCMS: {e}")
    
    squawk = str(ac.get("squawk", ""))
    
    # Build the SBS CSV line.
    # Fields: MSG,3,,,(hex_ident),,date_generated,time_generated,date_generated,time_generated,callsign,alt_ft,gs,track,lat,lon,vr,squawk,0,0,0,0
    fields = [
        "MSG",
        "3",        # Transmission type: using "3" for airborne position
        "",         # Session ID
        "",         # Aircraft ID
        hex_ident,
        "",         # Flight ID
        date_generated,
        time_generated,
        date_generated,
        time_generated,
        callsign,
        altitude_ft,
        ground_speed,
        track,
        latitude,
        longitude,
        vertical_rate,
        squawk,
        "0",        # Alert
        "0",        # Emergency
        "0",        # SPI
        "0"         # OnGround
    ]
    return ",".join(fields)

def convert_json_to_sbs(json_data, quiet=False):
    """
    Convert the entire JSON data (which is expected to have an "aircraft" array)
    into a list of SBS formatted lines.
    """
    sbs_lines = []
    if "aircraft" not in json_data:
        if not quiet:
            print("Received JSON does not contain an 'aircraft' field.")
        return sbs_lines

    for ac in json_data["aircraft"]:
        sbs_line = convert_aircraft_to_sbs(ac, quiet)
        if sbs_line:
            sbs_lines.append(sbs_line)
    return sbs_lines

def udp_listener(udp_port, quiet):
    """
    Listen for incoming UDP JSON messages on the specified port.
    Convert them to SBS formatted lines and broadcast to all connected TCP clients.
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
            sbs_lines = convert_json_to_sbs(json_data, quiet)
            # For each SBS message line, broadcast (append newline)
            for line in sbs_lines:
                broadcast(line + "\n", quiet)
        except Exception as e:
            if not quiet:
                print(f"Error in UDP listener: {e}")

def broadcast(message, quiet):
    """
    Send the given message (a string) to all connected TCP clients.
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
        print(f"TCP server listening on {listen_host}:{listen_port}")

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

def main():
    parser = argparse.ArgumentParser(
        description="Listen for UDP JSON ADS-B data, convert to SBS (30003) format, and serve it to TCP clients."
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

    # Start TCP server (in main thread or separate thread).
    tcp_server(args.listen_host, args.tcp_port, quiet)

if __name__ == "__main__":
    main()
