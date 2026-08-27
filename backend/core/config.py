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

# Snapshot the environment before loading, so any variable the file overrides
# can be reported.
#
# override=True is deliberate: each runtime takes its settings from its own env
# file, which is what keeps local, docker and server configurations separate.
# That is not being changed. What is being fixed is the silence - a variable set
# on the command line is discarded without a word, so a command a person
# believes is pointed at a local database can run against the server instead.
_env_before = dict(os.environ)

load_dotenv(env_path, override=True)

_overridden = [
    (key, _env_before[key], os.environ[key])
    for key in os.environ
    if key in _env_before and _env_before[key] != os.environ[key]
]

print("=" * 60)
print(f"APP_RUNTIME (raw): {raw_runtime}")
print(f"Runtime selected : {runtime}")
print(f"Configuration    : {env_path}")
print(f"DB_HOST          : {os.getenv('DB_HOST')}")

if _overridden:
    print("-" * 60)
    plural = "s were" if len(_overridden) > 1 else " was"
    print(f"WARNING: {len(_overridden)} environment variable{plural} IGNORED,")
    print(f"         overridden by {ENV_FILES[runtime]}:")
    for key, from_env, from_file in _overridden:
        # Never echo a value that may be a secret; report only that it changed.
        sensitive = any(m in key.upper() for m in ("PASSWORD", "PWD", "SECRET", "TOKEN", "KEY"))
        if sensitive:
            print(f"         {key}: set in environment, replaced by the file")
        else:
            print(f"         {key}: {from_env!r} (environment) -> {from_file!r} (file)")
    print("         Set APP_RUNTIME to choose a different env file.")

print("=" * 60)