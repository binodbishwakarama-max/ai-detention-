import socket
import sys

def check_port(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except:
            return False

ports = {
    "Vite (Frontend Internal)": 3000,
    "Frontend (Host Map)": 3001,
    "API (Host Map)": 8000,
    "Redis": 6379,
    "Postgres": 5432
}

print("Checking connectivity...")
for name, port in ports.items():
    status = "ALIVE" if check_port("localhost", port) else "DEAD"
    print(f"{name} (port {port}): {status}")
