import os
import sys

def debug_print(*args, **kwargs):
    if os.getenv("DEBUG_LOGGING", "True").lower() == "true":
        print(*args, **kwargs)
