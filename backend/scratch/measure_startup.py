import time
import sys
import os

sys.path.insert(0, os.path.abspath("."))

t0 = time.time()
print(f"[0.000s] Measurement script started...")

import app

t_end = time.time()
print(f"[{round(t_end - t0, 3)}s] Full 'import app' completed successfully!")
