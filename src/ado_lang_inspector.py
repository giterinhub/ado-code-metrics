#!/usr/bin/env python3
import os, sys, csv, time, base64, argparse
from collections import Counter
from urllib.parse import quote
import requests
from datetime import datetime, timedelta

API_VER = "7.1-preview.1"

# Extension to language map (edit as you like)
EXT_TO_LANG = {
    "bicep": "Bicep",
    "json": "JSON",
    "yaml": "YAML", "yml": "YAML",
    "tf": "Terraform",
    "ps1": "PowerShell", "psm1": "PowerShell",
    "sh": "Shell",
    "py": "Python",
    "ts": "TypeScript", "tsx": "TypeScript",
    "js": "JavaScript", "jsx": "JavaScript",
    "cs": "C#",
    "java": "Java",
    "go": "Go",
    "rb": "Ruby",
    "php": "PHP",
    "rs": "Rust",
    "cpp": "C++", "cxx": "C++", "cc": "C++",
    "c": "C",
    "h": "C/C++ Header", "hpp": "C++ Header", "hxx": "C++ Header",
    "scala": "Scala",
    "kt": "Kotlin",
    "md": "Markdown",
    "csv": "CSV",
    "xml": "XML",
    "ini": "INI",
    "toml": "TOML",
}

NON_CODE_LANGS = {"Markdown", "CSV"}

def ext_from_path(path:str)->str:
    name = path.rsplit("/", 1)[-1]
    if "." not in name: return ""
    return name.rsplit(".", 1)[-1].lower()

def lang_from_ext(ext:str)->str:
    return EXT_TO_LANG.get(ext, "Other")

class ADO:
    def __init__(self, org_url:str, pat:str, rate_delay:float=0.0):
        self.org_url = org_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": "Basic " + base64.b64encode(f":{pat}".encode()).decode()
        })
        self.rate_delay = rate_delay

    def _get(self, url:str):
        r = self.session.get(url)
        if self.rate_delay: time.sleep(self.rate_delay)
        r.raise_for_status()
        return r

    def paged(self, url:str):
        continuation = None
        while True:
            u = url
            if continuation:
                u = f"{u}{'&' if '?' in u else '?'}continuationToken={quote(continuation)}"
            r = self._get(u)
            data = r.json()
            for item in data.get("value", []):
                yield item
            continuation = r.headers.get("x-ms-continuationtoken")
            if not continuation:
                break

    # --- Projects / Repos ---
    def list_projects(self):
        url = f"{self.org_url}/_apis/projects?api-version={API_VER}"
        return list(self.paged(url))

    def list_repos(self, project_id):
        url = f"{self.org_url}/{project_id}/_apis/git/repositories?api-version={API_VER}"
        return list(self.paged(url))

    # --- Items (tree listing) ---
    def list_files(self, project_id, repo_id, branch_name):
        base = f"{self.org_url}/{project_id}/_apis/git/repositories/{repo_id}/items"
        url = (f"{base}?recursionLevel=Full&includeContentMetadata=true"
               f"&versionDescriptor.version={quote(branch_name)}"
               f"&api-version={API_VER}")
        for item in self.paged(url):
            if not item.get("isFolder", False) and item.get("gitObjectType") == "blob":
                size = int(item.get("size", 0) or 0)
                path = item.get("path")
                if path is not None:
                    yield {"path": path, "size": size}

    # --- Commits / Changes (for recency filters) ---
    def list_commits(self, project_id, repo_id, branch_name, from_date_iso):
        commits = []
        top, skip = 200, 0
        while True:
            url = (f"{self.org_url}/{project_id}/_apis/git/repositories/{repo_id}/commits"
                   f"?searchCriteria.itemVersion.version={quote(branch_name)}"
                   f"&searchCriteria.fromDate={quote(from_date_iso)}"
                   f"&$top={top}&$skip={skip}&api-version={API_VER}")
            r = self._get(url)
            batch = r.json().get("value", [])
            if not batch:
                break
            commits.extend(batch)
            if len(batch) < top:
                break
            skip += top
        return commits

    def list_changed_paths_for_commits(self, project_id, repo_id, commit_ids, created_only=False):
        changed, created = set(), set()
        for cid in commit_ids:
            url = (f"{self.org_url}/{project_id}/_apis/git/repositories/{repo_id}/commits/{cid}/changes"
                   f"?api-version={API_VER}")
            r = self._get(url)
            for ch in r.json().get("changes", []):
                ctype = (ch.get("changeType") or "").lower()
                item = ch.get("item") or {}
                path = item.get("path")
                if not path:
                    continue
                if ctype == "add":
                    created.add(path); changed.add(path)
                elif ctype in ("edit","rename"):
                    changed.add(path)
        return (created if created_only else changed)

def parse_args():
    p = argparse.ArgumentParser(prog="ado_lang_inspector", description="Scan Azure DevOps language stats")
    p.add_argument("--out", default="out/", help="Output directory for CSVs")
    p.add_argument("--org-url", default=os.environ.get("ADO_ORG_URL"), help="Azure DevOps org URL")
    p.add_argument("--pat", default=os.environ.get("ADO_PAT"), help="PAT with Code (Read) scope")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--since-days", type=int, default=int(os.environ.get("FILTER_SINCE_DAYS", "0")),
                   help="Filter to files changed since N days ago")
    g.add_argument("--since-iso", default=os.environ.get("FILTER_SINCE_ISO"),
                   help="Filter to files changed since YYYY-MM-DD")
    p.add_argument("--created-only", action="store_true",
                   default=os.environ.get("FILTER_CREATED_ONLY","false").lower()=="true",
                   help="Only include files CREATED since the window")
    p.add_argument("--exclude-non-code", action="store_true",
                   default=os.environ.get("EXCLUDE_NON_CODE","false").lower()=="true",
                   help="Exclude non-code (Markdown/CSV) from % calculation")
    p.add_argument("--rate-delay", type=float, default=float(os.environ.get("RATE_DELAY","0.0")),
                   help="Seconds to sleep between API calls (e.g., 0.05)")
    return p.parse_args()

def ensure_out(path):
    os.makedirs(path, exist_ok=True)

def write_csv(path, rows, headers):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def main():
    args = parse_args()
    if not args.org_url or not args.pat:
        print("Please set --org-url/--pat or ADO_ORG_URL/ADO_PAT.", file=sys.stderr)
        return 2

    # resolve since date
    since_iso = None
    if args.since_iso:
        since_iso = args.since_iso
    elif args.since_days and args.since_days > 0:
        since_iso = (datetime.utcnow() - timedelta(days=args.since_days)).strftime("%Y-%m-%d")

    ado = ADO(args.org_url, args.pat, rate_delay=args.rate_delay)

    ensure_out(args.out)

    per_repo_rows = []
    tenant_totals = Counter()
    tenant_totals_code_only = Counter()

    projects = ado.list_projects()
    print(f"Found {len(projects)} projects")

    for p in projects:
        proj_id = p["id"]
        proj_name = p["name"]
        repos = ado.list_repos(proj_id)
        print(f"- {proj_name}: {len(repos)} repos")

        for repo in repos:
            repo_name = repo["name"]
            default_branch = repo.get("defaultBranch")
            if not default_branch:
                per_repo_rows.append({
                    "project": proj_name,
                    "repository": repo_name,
                    "default_branch": "",
                    "language": "",
                    "bytes": 0
                })
                continue

            branch_name = default_branch.replace("refs/heads/","")

            # optional recent filter
            recent_paths = None
            if since_iso:
                commits = ado.list_commits(proj_id, repo["id"], branch_name, since_iso)
                commit_ids = [c["commitId"] for c in commits]
                if commit_ids:
                    recent_paths = ado.list_changed_paths_for_commits(
                        proj_id, repo["id"], commit_ids, created_only=args.created_only
                    )
                else:
                    recent_paths = set()

            lang_bytes = Counter()
            total_bytes = 0

            try:
                for item in ado.list_files(proj_id, repo["id"], branch_name):
                    if recent_paths is not None and item["path"] not in recent_paths:
                        continue
                    size = item["size"]
                    total_bytes += size
                    ext = ext_from_path(item["path"])
                    lang = lang_from_ext(ext)
                    lang_bytes[lang] += size
            except requests.HTTPError as e:
                print(f"  ! Error listing files for {proj_name}/{repo_name}: {e}", file=sys.stderr)
                continue

            if total_bytes == 0:
                per_repo_rows.append({
                    "project": proj_name,
                    "repository": repo_name,
                    "default_branch": default_branch,
                    "language": "",
                    "bytes": 0
                })
            else:
                for lang, b in lang_bytes.items():
                    per_repo_rows.append({
                        "project": proj_name,
                        "repository": repo_name,
                        "default_branch": default_branch,
                        "language": lang,
                        "bytes": b
                    })
                    tenant_totals[lang] += b
                    if (not args.exclude_non_code) or (lang not in {{"Markdown","CSV"}}):
                        tenant_totals_code_only[lang] += b

    # Write CSVs
    repo_csv = os.path.join(args.out, "repo_language_stats.csv")
    write_csv(repo_csv, per_repo_rows, ["project","repository","default_branch","language","bytes"])

    total_all = sum(tenant_totals.values()) or 1
    rows = []
    for lang, b in tenant_totals.most_common():
        rows.append({
            "language": lang,
            "bytes": b,
            "percent_all_files": round(100.0 * b / total_all, 2)
        })
    tenant_csv = os.path.join(args.out, "tenant_language_summary.csv")
    write_csv(tenant_csv, rows, ["language","bytes","percent_all_files"])

    # Pretty print code-only summary
    total_code = sum(tenant_totals_code_only.values()) or 1
    print("\n== Tenant summary (code-only %) ==")
    for lang, b in tenant_totals_code_only.most_common():
        pct = 100.0 * b / total_code
        print(f"{lang:15s} {pct:6.2f}%")

    print(f"\nWrote:\n - {repo_csv}\n - {tenant_csv}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
