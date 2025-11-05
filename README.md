# azure-devops-lang-inspector

Language & file-type analytics for **Azure DevOps** at org scale.  
Scans **all projects** and **all repos**, totals bytes per language (by extension), and outputs CSVs.
Optionally **filter by recent activity** (created/modified since a date or in the last N days).

## Why?
Azure DevOps doesn't natively show a “language breakdown” across hundreds of repos. This tool uses the **REST API**
to walk the default branch file tree (metadata only — no cloning) and tally file sizes by extension, similar in spirit
to GitHub Linguist’s approach. You can also scope stats to **recently touched files** (last 12 months, etc.).

## Features
- 🚀 Scans **all projects** → **all repos** (handles pagination)
- 📁 No clones — uses the **Git Items API** (fast, metadata only)
- 🕒 **Recent activity filters** using **Commits → Changes** (only created/modified files)
- 📊 Outputs:
  - `repo_language_stats.csv` per-repo language totals (bytes)
  - `tenant_language_summary.csv` org-wide totals + percentages
- 🧩 Extensible **extension → language** mapping
- 🧽 Optional “code-only %” (exclude docs/data like Markdown/CSV from percentages)
- 🐳 Docker support + GitHub Actions starter workflow

## Quick start

### 1) Python
```bash
pip install -r requirements.txt

# env
export ADO_ORG_URL="https://dev.azure.com/YourOrg"
export ADO_PAT="your_personal_access_token"

# (optional) filter recent activity
export FILTER_SINCE_DAYS=365            # OR set FILTER_SINCE_ISO=YYYY-MM-DD
export FILTER_CREATED_ONLY=false         # true = only files CREATED in window
export EXCLUDE_NON_CODE=true            # exclude Markdown/CSV from %

# run
python -m src.ado_lang_inspector --out out/
```

### 2) Docker
```bash
docker build -t ado-lang-inspector .
docker run --rm -e ADO_ORG_URL -e ADO_PAT -e FILTER_SINCE_DAYS -e FILTER_SINCE_ISO -e FILTER_CREATED_ONLY -e EXCLUDE_NON_CODE   -v "$PWD/out":/app/out ado-lang-inspector
```

### 3) GitHub Actions (optional)
The included workflow lets you run the scan on push. Store `ADO_ORG_URL` and `ADO_PAT` as repository **secrets**.
Outputs (CSVs) are uploaded as workflow artifacts.

---

## Outputs
- **repo_language_stats.csv**: columns = `project, repository, default_branch, language, bytes`
- **tenant_language_summary.csv**: columns = `language, bytes, percent_all_files`

## CLI
```text
usage: ado_lang_inspector [-h] [--out OUT] [--org-url ORG_URL] [--pat PAT]
                          [--since-days N | --since-iso YYYY-MM-DD]
                          [--created-only] [--exclude-non-code]
                          [--rate-delay SECONDS]

Scan Azure DevOps projects and repositories to compute language stats.
```

### Examples
```bash
# Whole tenant, no time filter
python -m src.ado_lang_inspector --out out/

# Last 12 months (created OR modified)
python -m src.ado_lang_inspector --out out/ --since-days 365

# Only files created in last 12 months
python -m src.ado_lang_inspector --out out/ --since-days 365 --created-only

# Exact since date
python -m src.ado_lang_inspector --out out/ --since-iso 2024-11-05
```

## Security / Permissions
Use a **Personal Access Token** with at least **Code (Read)** scope. The tool only reads metadata
and commit changes to determine which files were touched recently.

## Limitations
- “Language” is inferred from file extension (fast, pragmatic). You can refine the map in code.
- Deletes are ignored for recent filters (file doesn’t exist on tip to measure size).
- Very large orgs: you may want to raise the `--rate-delay` slightly (e.g., `0.05s`).

## License
MIT — see [LICENSE](LICENSE).

---

Made with ❤️ for large ADO tenants.
