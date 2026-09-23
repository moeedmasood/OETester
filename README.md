# OE Testing Assistant

Flask web app for Internal Audit Operating Effectiveness (OE) testing, using UnifiedAPI's
Extraction and Inference services.

## Workflow implemented

1. User fills in audit metadata, an optional list-of-samples file, and defines the
   **Extraction Structure** and **Compute Structure** field builders in the browser.
2. On submit, the server validates required fields and (if a sample size / list of
   samples was provided) checks it against the files found in the **Sample Source**
   folder, warning (but allowing override via "ignore mismatch") on any difference.
3. For each sample file, UnifiedAPI **Extraction** pulls out the Extraction Structure
   fields (schema built dynamically from a runtime Pydantic model).
4. UnifiedAPI **Inference** computes the Compute Structure fields plus a per-sample
   pass/fail outcome, then a final call summarises an overall conclusion.
5. Results are written to an Excel working paper (metadata header + per-sample table)
   and offered as a download. Progress is polled live in the browser during processing.

## Setup

```powershell
cd oe-testing-app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
#to install the local unified api client
# pip install ai-unified-api-client  --extra-index-url https://nexus.itt.aws.oprd.com.au/repository/pypi-group/simple
copy .env.example .env
# edit .env with real CLIENT_ID / CLIENT_SECRET
python run.py
```

Open http://127.0.0.1:5050

## Notes / known simplifications (v1)

- `Sample Source` must be a folder path accessible from the machine running the Flask
  server (same constraint as the original prototype app).
- The "Compute Structure" step and overall conclusion rely on free-form JSON returned by
  an LLM (`api.inference`); if the model returns malformed JSON the job will fail with the
  raw response included in the error for debugging.
- Job state is stored in-memory (a Python dict) — restarting the server loses in-flight
  job status. Fine for local/single-worker use; swap for Redis/DB before multi-worker deployment.
- Credentials come from `.env` (`CLIENT_ID` / `CLIENT_SECRET` / `UNIFIED_API_ENV`) — never commit
  the real `.env` file.
