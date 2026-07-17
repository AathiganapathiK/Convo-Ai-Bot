import core.config
import os
import sys
import socket
import time
import core.config

def wait_for_db():
    host = os.getenv("DB_HOST", "localhost")
    try:
        port = int(os.getenv("DB_PORT", "1433"))
    except ValueError:
        port = 1433
        
    timeout = int(os.getenv("DB_WAIT_TIMEOUT", "60"))
    start_time = time.time()
    
    print(f"Waiting for database at {host}:{port} (timeout: {timeout}s)...")
    while True:
        try:
            with socket.create_connection((host, port), timeout=3):
                print(f"Database port {port} is open and accessible!")
                break
        except (OSError, ConnectionRefusedError):
            if time.time() - start_time > timeout:
                print(f"Error: Timed out waiting for database at {host}:{port} after {timeout} seconds.")
                sys.exit(1)
            print("Database port is not yet available, retrying in 3 seconds...")
            time.sleep(3)

if __name__ == "__main__":
    wait_for_db()
