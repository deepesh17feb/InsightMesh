from pathlib import Path

ATLYS_AGENTIC_DIR = Path(__file__).resolve().parent
REPO_ROOT = ATLYS_AGENTIC_DIR.parent.parent if ATLYS_AGENTIC_DIR.parent.name == "src" else ATLYS_AGENTIC_DIR.parent
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
AGENTS_CONFIG_YAML = ATLYS_AGENTIC_DIR / "config" / "agents.yaml"

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


def available_spec_ids() -> list[str]:
    specs = []
    if SPECS_DIR.exists():
        for item in sorted(SPECS_DIR.iterdir()):
            if item.is_dir() and (item / "spec.md").exists():
                specs.append(item.name)
    if UNSEEN_SPECS_DIR.exists() and (UNSEEN_SPECS_DIR / "spec.md").exists():
        if "06_unseen" not in specs:
            specs.append("06_unseen")
    return specs or ["01_express_checkout", "02_group_family", "03_coupons", "04_visas_for_digital_nomads", "05_price_drop"]


def normalize_spec_id(spec_id: str) -> str:
    if not spec_id:
        return "01_express_checkout"
    for sid in available_spec_ids():
        if spec_id == sid:
            return sid
        clean_spec = spec_id.replace("spec_", "").replace("0", "").strip("_")
        clean_sid = sid.replace("0", "").strip("_")
        if spec_id in sid or clean_spec in clean_sid:
            return sid
    return spec_id

