import subprocess
import time
import os
import sys

def measure_start():
    env = os.environ.copy()
    env["BROWSER"] = "none"
    
    t0 = time.time()
    print("[0.00s] Launching 'npm start'...")
    
    proc = subprocess.Popen(
        ["cmd", "/c", "npm start"],
        cwd=r"d:\RR_Bot\Convo-Ai-Bot\frontend",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    ready_time = None
    for line in iter(proc.stdout.readline, ''):
        now = time.time()
        elapsed = now - t0
        line_str = line.strip()
        if line_str:
            print(f"[{elapsed:6.2f}s] {line_str}")
        if "Compiled successfully" in line_str or "Compiled with" in line_str or "Local:" in line_str or "On Your Network" in line_str:
            ready_time = elapsed
            print(f"\n>>> DEVELOPMENT SERVER READY AT {ready_time:6.2f} SECONDS <<<\n")
            break
            
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
        
    return ready_time

if __name__ == "__main__":
    t = measure_start()
    print(f"RESULT: {t}")
