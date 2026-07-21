import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]

ENV_FILES = {
    "local": ".local.env",
    "docker": ".docker.env",
    "server": ".server.env",
}

raw_runtime = os.getenv("APP_RUNTIME")

runtime = (raw_runtime or "local").lower()

if runtime not in ENV_FILES:
    raise RuntimeError(
        f"Invalid APP_RUNTIME '{runtime}'. "
        f"Expected one of: {', '.join(ENV_FILES.keys())}"
    )

env_path = ROOT_DIR / ENV_FILES[runtime]

if not env_path.exists():
    raise FileNotFoundError(
        f"Configuration file not found: {env_path}"
    )

load_dotenv(env_path, override=True)

print("=" * 60)
print(f"APP_RUNTIME (raw): {raw_runtime}")
print(f"Runtime selected : {runtime}")
print(f"Configuration    : {env_path}")
print(f"DB_HOST          : {os.getenv('DB_HOST')}")
print("=" * 60)