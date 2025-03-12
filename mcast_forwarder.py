import socket
import struct

# Multicast group and port to listen on.
MCAST_GRP = '224.1.1.1'
MCAST_PORT = 6666

# Destination address to forward packets.
DEST_HOST = 'home.viljo.se'
DEST_PORT = 6666

def main():
    # Create a UDP socket for receiving multicast messages.
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Bind to all interfaces on the specified multicast port.
    recv_sock.bind(('', MCAST_PORT))
    
    # Tell the operating system to add the socket to the multicast group
    # on all interfaces.
    mreq = struct.pack("4sL", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
    recv_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    # Create a UDP socket for sending packets.
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"Listening for multicast packets on {MCAST_GRP}:{MCAST_PORT}")
    while True:
        try:
            # Receive packet data.
            data, addr = recv_sock.recvfrom(65535)
            print(f"Received {len(data)} bytes from {addr}. Forwarding to {DEST_HOST}:{DEST_PORT}")
            
            # Forward the received packet to the destination.
            send_sock.sendto(data, (DEST_HOST, DEST_PORT))
        except KeyboardInterrupt:
            print("Interrupted by user, exiting.")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
