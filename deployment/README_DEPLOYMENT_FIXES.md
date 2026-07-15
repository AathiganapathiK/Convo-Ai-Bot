# What was fixed, and one thing YOU still need to do

## Bugs fixed in these scripts

1. **Filename typo** — every script previously did `source .../deployment.conf`
   while the actual file was named `deployement.conf` (extra "e"). Every
   script would have failed immediately. Fixed: config file is now named
   `deployment.conf` everywhere, consistently.

2. **`04_run_migrations.sh` was completely empty (0 bytes)** but `deploy.sh`
   called it as a required step. It now actually applies
   `001_security_framework.sql` and `002_semantic_audit_types.sql` against
   `RR_platform`, tracking what's applied in a `__schema_migrations` table
   so it's safe to re-run without erroring on already-applied migrations.

3. **Frontend build ordering bug** — the original `06_install_frontend.sh`
   ran `npm run build` before any `.env` was ever created for the frontend
   (no script created one at all). Create React App bakes `REACT_APP_*`
   variables into the build **at build time**, not at runtime. `06` now
   creates `frontend/.env` from the template and stops so you can point
   `REACT_APP_API_BASE_URL` at the real server address *before* building.

4. **SQL Server engine install now respects your mentor's existing server**
   — `02_install_sqlserver.sh` no longer blindly installs `mssql-server`.
   Since SQL Server is already installed there, it only installs the ODBC
   driver + `sqlcmd` (which your Python backend needs locally regardless of
   where the DB physically runs), and it verifies connectivity to whatever
   `SQL_HOST` you configure.

5. **Everything is now driven by `SQL_IS_LOCAL` in `deployment.conf`** —
   flip this one flag once you know whether the database is on the same box
   as the app or a separate machine. Scripts 02, 03, 09, 10 all check it.

## The one thing that still needs a code change: `database.py`

Your current platform DB connection string is:

```python
DATABASE_URL = f"mssql+pyodbc://@{_host}/{_name}?driver={_driver}&trusted_connection=yes"
```

`trusted_connection=yes` is **Windows Integrated Authentication**. It only
works when the app and SQL Server both trust the same Windows/AD identity —
this is why it works on your local Windows machine right now. **It has no
equivalent on Linux** (short of a full Kerberos/AD join, which is not worth
doing here).

### Fix: switch to SQL Server Authentication using your existing `DB_USER`/`DB_PASSWORD`

Give this exact instruction to Antigravity (or edit `backend/database.py`
yourself):

```
In backend/database.py, replace the DATABASE_URL construction so it uses
SQL Server Authentication (username + password) instead of
trusted_connection, using the existing DB_USER and DB_PASSWORD environment
variables. Example:

import os
from urllib.parse import quote_plus

_host = os.getenv("DB_HOST")
_port = os.getenv("DB_PORT", "1433")
_name = os.getenv("DB_NAME")
_user = os.getenv("DB_USER")
_password = os.getenv("DB_PASSWORD")
_driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")

DATABASE_URL = (
    f"mssql+pyodbc://{quote_plus(_user)}:{quote_plus(_password)}"
    f"@{_host}:{_port}/{_name}"
    f"?driver={quote_plus(_driver)}&TrustServerCertificate=yes"
)

Keep the rest of the file (engine creation, etc.) unchanged. Do not remove
support for the ODBC driver name coming from an environment variable.
Apply the same pattern to backend/services/database_connection_factory.py
for the Windows Auth branch, OR simply always use the username/password
branch there going forward since the server is Linux.
```

You'll then need a SQL Server login (not just Windows Auth) for the app to
use — ask your mentor to create one, e.g.:

```sql
CREATE LOGIN retail_ai_app WITH PASSWORD = 'a-strong-password-here';
USE RR_platform;
CREATE USER retail_ai_app FOR LOGIN retail_ai_app;
ALTER ROLE db_owner ADD MEMBER retail_ai_app;  -- or a tighter role
```

Put those same values into `backend/.env` as `DB_USER` / `DB_PASSWORD`.

## Confirmed setup (as of latest update)

- **OS**: Ubuntu 24.04 — already handled by the scripts.
- **SQL Server**: fresh install, same machine as the app (`SQL_IS_LOCAL=true`
  in `deployment.conf`, already set). `02_install_sqlserver.sh` now installs
  `mssql-server` directly and runs `mssql-conf setup` interactively so you
  set the SA password and edition (choose "Developer" — free, full-featured,
  fine for this use case, but not licensed for production use).
- **SSMS**: cannot run on Linux. If your mentor wants a GUI to browse the
  database, he should install SSMS on his own Windows machine and connect
  remotely to this server's IP on port 1433 (make sure the firewall — `ufw`
  or cloud provider security group — allows inbound 1433 from his IP if
  he'll connect from outside the server itself). Alternatively, Azure Data
  Studio or the VS Code "SQL Server (mssql)" extension work directly on
  Linux with no extra install step here.

## Still worth double-checking before the final run

- **SQL Server version compatibility**: your local backup was taken from
  SQL Server 2025. You generally **cannot restore a newer-version backup
  onto an older SQL Server instance.** The apt repo `02_install_sqlserver.sh`
  adds installs whatever the current `mssql-server` package is — check its
  version after install (`sqlservr -v` or `SELECT @@VERSION` once running)
  and confirm it's 2025 or newer. If it installs an older version (e.g. 2022)
  and the restore fails with a version error, use SSMS's "Generate Scripts"
  (schema + data as plain `.sql`) instead of the `.bak` file — that route
  isn't version-locked.
- **Minimum system requirements**: `mssql-server` on Linux requires at least
  2 GB RAM (Microsoft recommends 4 GB+) and enough disk for your data. GPU
  servers usually have plenty of RAM, but worth a quick check with `free -h`
  before installing.

## What to send your mentor / push to GitHub

- Push all code + this `deployment/` folder to GitHub. Add a `.gitignore`
  entry for `backend/.env` and `frontend/.env` if not already ignored
  (your existing root `.gitignore` already covers `.env`, good).
- Send `backend.env.example` and `frontend.env.example` via GitHub (safe,
  no secrets) — your mentor fills in real values on the server.
- Send the real `GROQ_API_KEY`, `ENCRYPTION_KEY`, and DB credentials
  **separately**, never through GitHub.
- Send the `.bak` file(s) via direct transfer (cloud storage / SCP), not
  through GitHub — they're usually too large and contain your data.