from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBLEM_STATEMENT_DIR = REPO_ROOT / "problem statment"
DATA_DIR = PROBLEM_STATEMENT_DIR / "data"
SPECS_DIR = PROBLEM_STATEMENT_DIR / "specs"
BASE_CONTEXT_MD = PROBLEM_STATEMENT_DIR / "base_context.md"
DDL_SQL = DATA_DIR / "ddl.sql"
LOAD_SH = DATA_DIR / "load.sh"

ATLYS_AGENTIC_DIR = Path(__file__).resolve().parent
CHDB_PATH = ATLYS_AGENTIC_DIR / "chdb_data"
OUTPUTS_DIR = ATLYS_AGENTIC_DIR / "outputs"
SCHEMAS_DIR = OUTPUTS_DIR / "schemas"
INSIGHTS_DIR = OUTPUTS_DIR / "insights"
TRACES_DIR = OUTPUTS_DIR / "traces"
SUBMISSION_DIR = ATLYS_AGENTIC_DIR / "submission"
UNSEEN_SPECS_DIR = ATLYS_AGENTIC_DIR / "specs" / "06_unseen"

for _d in (OUTPUTS_DIR, SCHEMAS_DIR, INSIGHTS_DIR, TRACES_DIR, SUBMISSION_DIR, UNSEEN_SPECS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def spec_dir(spec_id: str) -> Path:
    if spec_id == "06_unseen":
        return UNSEEN_SPECS_DIR
    return SPECS_DIR / spec_id


def spec_md(spec_id: str) -> Path:
    return spec_dir(spec_id) / "spec.md"


def events_ndjson(spec_id: str) -> Path:
    return spec_dir(spec_id) / "events.ndjson"
