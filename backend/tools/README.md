# Backend Tools

This folder contains local diagnostic and maintenance scripts. These scripts are not imported by the FastAPI application.

Run them from the `backend` directory so imports like `services.*` and `ai.*` resolve correctly.

Examples:

```powershell
python tools/check_provider.py
python tools/check_encryption.py
python tools/inspect_models.py
python tools/hash_password.py
python tools/load_sales_csv.py
python tools/load_all_sales_csv.py
```
