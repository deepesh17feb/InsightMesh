"""FastAPI OpenAI-compatible backend for LibreChat / UI integrations (CUJ 2).

Exposes POST /v1/chat/completions wired to AnalysisFlow.
"""
from datetime import datetime, timezone
import time
import uuid

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    class HTMLResponse:  # type: ignore
        def __init__(self, content: str = "", status_code: int = 200):
            self.content = content

    class FastAPI:  # type: ignore
        def __init__(self, title: str = ""):
            self.title = title

        def post(self, path: str):
            def decorator(fn):
                return fn
            return decorator

        def get(self, path: str, response_class=None):
            def decorator(fn):
                return fn
            return decorator

    from pydantic import BaseModel, Field

from atlys_agentic import chdb_client, paths, tools
from atlys_agentic.flows import analysis_flow, ingestion_flow

app = FastAPI(title="Atlys Analytics Platform — CUJ 1 Ingestion UI & CUJ 2 Analyst Chat")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "atlys-analyst"
    messages: list[ChatMessage] = Field(min_length=1)


class IngestionRequest(BaseModel):
    spec_id: str
    table_name: str = ""


_DEFAULT_BASE_SQL = "SELECT * FROM purchase_completed"


@app.get("/api/specs")
def list_specs():
    specs = []
    if paths.SPECS_DIR.exists():
        for p in sorted(paths.SPECS_DIR.glob("*")):
            if p.is_dir():
                spec_name = p.name.replace("_", " ").title()
                specs.append({
                    "id": p.name,
                    "name": spec_name,
                    "table_default": p.name.split("_", 1)[-1] if "_" in p.name else p.name,
                })
    return {"specs": specs}


@app.post("/api/ingest/propose")
def propose_ingestion(req: IngestionRequest):
    chdb_client.init_schema()
    chdb_client.init_base_context()
    result = ingestion_flow.run(spec_id=req.spec_id, table_name=req.table_name, dry_run=True)
    return {
        "status": "success",
        "spec_id": req.spec_id,
        "table_name": result.get("table_name") or req.table_name,
        "dry_run": True,
        "ddl": result.get("ddl", ""),
        "mv_ddl": result.get("mv_ddl", ""),
        "diff_result": result.get("diff_result", {}),
        "trace_id": result.get("trace_id", ""),
    }


@app.post("/api/ingest/approve")
def approve_ingestion(req: IngestionRequest):
    chdb_client.init_schema()
    chdb_client.init_base_context()
    result = ingestion_flow.run(
        spec_id=req.spec_id,
        table_name=req.table_name,
        input_fn=lambda _: "APPROVE",
        dry_run=False,
    )
    return {
        "status": "success" if result.get("approved") else "failed",
        "spec_id": req.spec_id,
        "table_name": result.get("table_name") or req.table_name,
        "approved": result.get("approved", False),
        "ddl_result": result.get("ddl_result", {}),
        "diff_result": result.get("diff_result", {}),
        "trace_id": result.get("trace_id", ""),
    }


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    question = req.messages[-1].content
    result = analysis_flow.run(question=question, spec_id="chat", base_sql=_DEFAULT_BASE_SQL)

    content = (
        f"{result['answer_md']}\n\n"
        f"_confidence: {result['confidence'].get('score')} · trace: {result['trace_id']}_"
    )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


@app.get("/api/viz")
def get_viz_snapshot():
    chdb_client.init_schema()
    chdb_client.init_base_context()
    snapshot = tools.Tool_Emit_Viz()
    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshot": snapshot,
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Atlys — Agentic Analytics & Ingestion Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0B0F19;
      --card-bg: rgba(22, 30, 49, 0.85);
      --border: #2D3748;
      --accent: #3B82F6;
      --accent-hover: #2563EB;
      --accent-green: #10B981;
      --accent-green-hover: #059669;
      --accent-amber: #F59E0B;
      --accent-purple: #8B5CF6;
      --text: #F3F4F6;
      --text-muted: #9CA3AF;
      --code-bg: #0F172A;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, sans-serif; }
    body { background-color: var(--bg); color: var(--text); min-height: 100vh; padding: 2rem 1.5rem; }
    .container { max-width: 1200px; margin: 0 auto; }
    header { margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1.25rem; display: flex; justify-content: space-between; align-items: center; }
    h1 { font-size: 1.75rem; font-weight: 700; background: linear-gradient(135deg, #60A5FA, #A78BFA); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .nav-tabs { display: flex; gap: 0.75rem; margin-bottom: 1.5rem; }
    .nav-tab { background: #1E293B; border: 1px solid var(--border); padding: 0.6rem 1.25rem; border-radius: 8px; font-size: 0.9rem; font-weight: 600; color: var(--text-muted); cursor: pointer; transition: all 0.2s; }
    .nav-tab:hover { background: #334155; color: #fff; }
    .nav-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
    .grid { display: grid; grid-template-columns: 340px 1fr; gap: 1.5rem; }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; backdrop-filter: blur(12px); box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
    .card-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; color: #E2E8F0; }
    .kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
    .kpi-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; text-align: center; }
    .kpi-val { font-size: 1.8rem; font-weight: 700; color: #60A5FA; font-family: 'JetBrains Mono', monospace; }
    .kpi-label { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem; }
    .form-group { margin-bottom: 1.25rem; }
    label { display: block; font-size: 0.85rem; font-weight: 500; color: var(--text-muted); margin-bottom: 0.4rem; }
    select, input { width: 100%; background: var(--code-bg); border: 1px solid var(--border); color: #fff; padding: 0.65rem 0.85rem; border-radius: 8px; font-size: 0.9rem; outline: none; }
    select:focus, input:focus { border-color: var(--accent); }
    .btn { display: inline-flex; align-items: center; justify-content: center; width: 100%; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 600; cursor: pointer; border: none; transition: all 0.2s; margin-bottom: 0.75rem; }
    .btn-primary { background: var(--accent); color: white; }
    .btn-primary:hover { background: var(--accent-hover); }
    .btn-success { background: var(--accent-green); color: white; }
    .btn-success:hover { background: var(--accent-green-hover); }
    .btn-secondary { background: #374151; color: white; }
    .btn-secondary:hover { background: #4B5563; }
    pre { background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; overflow-x: auto; color: #38BDF8; line-height: 1.5; }
    .section-box { margin-bottom: 1.25rem; }
    .tag-list { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.4rem; }
    .tag { background: #1E293B; border: 1px solid #334155; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; color: #F87171; }
    .tag.green { color: #34D399; }
    .tag.blue { color: #60A5FA; }
    .badge { background: #1E293B; border: 1px solid var(--border); padding: 0.35rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; color: #93C5FD; font-weight: 500; }
    .alert { padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem; font-size: 0.85rem; }
    .alert-info { background: rgba(59, 130, 246, 0.15); border: 1px solid #3B82F6; color: #93C5FD; }
    .alert-success { background: rgba(16, 185, 129, 0.15); border: 1px solid #10B981; color: #6EE7B7; }
    .table-view { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 0.5rem; }
    .table-view th { background: #1E293B; color: #94A3B8; text-align: left; padding: 0.65rem 0.85rem; border: 1px solid var(--border); font-weight: 600; }
    .table-view td { padding: 0.65rem 0.85rem; border: 1px solid var(--border); color: #E2E8F0; }
    .table-view tr:nth-child(even) { background: rgba(15, 23, 42, 0.4); }
    .insight-card { background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; margin-bottom: 1rem; }
    .confidence-meter { height: 8px; border-radius: 4px; background: #334155; margin-top: 0.5rem; overflow: hidden; }
    .confidence-fill { height: 100%; border-radius: 4px; }
    .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #ffffff; border-radius: 50%; border-top-color: transparent; animation: spin 0.8s linear infinite; margin-right: 6px; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Atlys Agentic Analytics Platform</h1>
        <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.25rem;">Autonomous Ingestion (CUJ 1) & Real-Time Visualization Snapshot (CUJ 2)</p>
      </div>
      <span class="badge">ClickHouse Cloud & chDB Engine Active</span>
    </header>

    <div class="nav-tabs">
      <button class="nav-tab active" id="tabIngest" onclick="showTab('ingest')">⚡ CUJ 1: Feature Ingestion Portal</button>
      <button class="nav-tab" id="tabViz" onclick="showTab('viz')">📊 3-View Real-Time Snapshot Dashboard</button>
    </div>

    <!-- TAB 1: INGESTION -->
    <div id="viewIngest">
      <div class="grid">
        <div class="card">
          <div class="form-group">
            <label for="specSelect">Select Feature Specification</label>
            <select id="specSelect" onchange="onSpecChange()">
              <option value="01_express_checkout">01_express_checkout</option>
              <option value="02_group_family">02_group_family</option>
              <option value="03_status_sharing">03_status_sharing</option>
              <option value="04_abandoned_checkout_recovery">04_abandoned_checkout_recovery</option>
              <option value="05_instant_forex">05_instant_forex</option>
            </select>
          </div>

          <div class="form-group" style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); padding: 0.75rem; border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 0.8rem; color: var(--text-muted);">Inferred Table:</span>
              <span id="inferredBadge" class="badge" style="background:#1E3A8A; color:#93C5FD;">express_checkout</span>
            </div>
            <div style="margin-top: 0.6rem; font-size: 0.8rem;">
              <label style="display: inline-flex; align-items: center; cursor: pointer; color: #94A3B8;">
                <input type="checkbox" id="overrideCheck" onchange="toggleOverride()" style="width: auto; margin-right: 6px;" />
                Override inferred table name
              </label>
            </div>
            <div id="overrideBox" style="display: none; margin-top: 0.5rem;">
              <input type="text" id="tableName" value="" placeholder="Custom table name" />
            </div>
          </div>

          <button class="btn btn-primary" id="dryRunBtn" onclick="runDryRun()">
            🛡️ Run Dry Run (Generate Proposal)
          </button>

          <button class="btn btn-success" id="deployBtn" onclick="runApproveDeploy()" style="display:none;">
            🚀 Approve & Deploy to Cloud
          </button>

          <div style="margin-top: 1.5rem; font-size: 0.8rem; color: var(--text-muted); line-height: 1.4;">
            <strong>Safety Guarantee:</strong> "Run Dry Run" generates proposed DDL & MV without mutating ClickHouse Cloud or chDB. "Deploy" requires human confirmation.
          </div>
        </div>

        <div class="card">
          <div id="statusAlert" class="alert alert-info">Select a spec and click <strong>Run Dry Run</strong> to inspect schema proposal.</div>

          <div id="resultsContainer" style="display: none;">
            <div class="section-box">
              <h3 style="font-size: 0.95rem; margin-bottom: 0.4rem; color: #94A3B8;">Proposed ClickHouse Table DDL</h3>
              <pre id="ddlOutput"></pre>
            </div>

            <div class="section-box" id="mvBox" style="display: none;">
              <h3 style="font-size: 0.95rem; margin-bottom: 0.4rem; color: #94A3B8;">Proposed Materialized View (SummingMergeTree)</h3>
              <pre id="mvOutput"></pre>
            </div>

            <div class="section-box">
              <h3 style="font-size: 0.95rem; margin-bottom: 0.4rem; color: #94A3B8;">Context Diff Audit (Context Librarian)</h3>
              <div id="diffSummary" style="font-size: 0.85rem; margin-bottom: 0.5rem;"></div>
              <div class="tag-list" id="diffTags"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 2: VIZ DASHBOARD -->
    <div id="viewViz" style="display: none;">
      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-val" id="kpiSchemas">0</div>
          <div class="kpi-label">Registered Schemas</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" id="kpiInsights">0</div>
          <div class="kpi-label">Product Insights</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" id="kpiChangelogs">0</div>
          <div class="kpi-label">Context Mutations</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" id="kpiConfidence">0%</div>
          <div class="kpi-label">Avg Insight Confidence</div>
        </div>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem;">
        <h2 style="font-size: 1.2rem; color: #E2E8F0;">Three-View Real-Time Snapshot</h2>
        <button class="btn btn-secondary" style="width: auto; padding: 0.45rem 1rem; margin-bottom: 0;" onclick="loadVizSnapshot()">
          🔄 Refresh Snapshot
        </button>
      </div>

      <!-- View 1: Schema Registry -->
      <div class="card" style="margin-bottom: 1.5rem;">
        <h3 class="card-title">1. Schema Registry (Versioned ClickHouse Cloud DDLs)</h3>
        <div id="schemaRegistryContainer">
          <p style="color: var(--text-muted); font-size: 0.85rem;">Loading schema history...</p>
        </div>
      </div>

      <!-- View 2: Insights Feed -->
      <div class="card" style="margin-bottom: 1.5rem;">
        <h3 class="card-title">2. Product Insights & Confidence Feed</h3>
        <div id="insightsContainer">
          <p style="color: var(--text-muted); font-size: 0.85rem;">Loading insights...</p>
        </div>
      </div>

      <!-- View 3: Context Changelog -->
      <div class="card">
        <h3 class="card-title">3. Business Context Changelog Audit Trail</h3>
        <div id="changelogContainer">
          <p style="color: var(--text-muted); font-size: 0.85rem;">Loading context changelog...</p>
        </div>
      </div>
    </div>
  </div>

  <script>
    function showTab(tab) {
      document.getElementById('viewIngest').style.display = (tab === 'ingest') ? 'block' : 'none';
      document.getElementById('viewViz').style.display = (tab === 'viz') ? 'block' : 'none';
      document.getElementById('tabIngest').className = 'nav-tab' + (tab === 'ingest' ? ' active' : '');
      document.getElementById('tabViz').className = 'nav-tab' + (tab === 'viz' ? ' active' : '');
      if (tab === 'viz') {
        loadVizSnapshot();
      }
    }

    async function loadSpecs() {
      try {
        const res = await fetch('/api/specs');
        const data = await res.json();
        if (data.specs && data.specs.length > 0) {
          const select = document.getElementById('specSelect');
          select.innerHTML = '';
          data.specs.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.id;
            opt.textContent = `${s.id} (${s.name})`;
            select.appendChild(opt);
          });
          onSpecChange();
        }
      } catch (e) { console.error(e); }
    }

    function toggleOverride() {
      const checked = document.getElementById('overrideCheck').checked;
      const box = document.getElementById('overrideBox');
      box.style.display = checked ? 'block' : 'none';
      if (!checked) {
        document.getElementById('tableName').value = '';
      }
    }

    function onSpecChange() {
      const select = document.getElementById('specSelect');
      const val = select.value;
      const clean = val.includes('_') ? val.split('_').slice(1).join('_') : val;
      document.getElementById('inferredBadge').textContent = clean;
      if (!document.getElementById('overrideCheck').checked) {
        document.getElementById('tableName').value = clean;
      }
    }

    async function runDryRun() {
      const spec_id = document.getElementById('specSelect').value;
      const custom_table = document.getElementById('tableName').value.trim();
      const table_name = custom_table || document.getElementById('inferredBadge').textContent;
      const btn = document.getElementById('dryRunBtn');
      const alertBox = document.getElementById('statusAlert');
      const deployBtn = document.getElementById('deployBtn');

      btn.innerHTML = '<span class="spinner"></span> Generating Proposal...';
      btn.disabled = true;

      try {
        const res = await fetch('/api/ingest/propose', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({spec_id, table_name})
        });
        const data = await res.json();
        
        document.getElementById('resultsContainer').style.display = 'block';
        document.getElementById('ddlOutput').textContent = data.ddl || '(None)';
        
        if (data.mv_ddl) {
          document.getElementById('mvBox').style.display = 'block';
          document.getElementById('mvOutput').textContent = data.mv_ddl;
        } else {
          document.getElementById('mvBox').style.display = 'none';
        }

        const diffTags = document.getElementById('diffTags');
        diffTags.innerHTML = '';
        const additions = (data.diff_result && data.diff_result.additions) || [];
        document.getElementById('diffSummary').textContent = `Inferred ${additions.length} columns to synchronize with business_context:`;
        additions.forEach(col => {
          const span = document.createElement('span');
          span.className = 'tag green';
          span.textContent = '+ ' + col;
          diffTags.appendChild(span);
        });

        alertBox.className = 'alert alert-info';
        alertBox.innerHTML = `<strong>Proposal Ready for Review:</strong> Proposed DDL and Materialized View generated in Dry-Run mode. Review above and click <strong>Approve & Deploy</strong> when ready.`;
        deployBtn.style.display = 'block';
      } catch (err) {
        alertBox.className = 'alert alert-info';
        alertBox.textContent = 'Error: ' + err.message;
      } finally {
        btn.innerHTML = '🛡️ Run Dry Run (Generate Proposal)';
        btn.disabled = false;
      }
    }

    async function runApproveDeploy() {
      if (!confirm('Deploy this schema and materialized view to ClickHouse Cloud?')) return;

      const spec_id = document.getElementById('specSelect').value;
      const custom_table = document.getElementById('tableName').value.trim();
      const table_name = custom_table || document.getElementById('inferredBadge').textContent;
      const deployBtn = document.getElementById('deployBtn');
      const alertBox = document.getElementById('statusAlert');

      deployBtn.innerHTML = '<span class="spinner"></span> Deploying to ClickHouse Cloud...';
      deployBtn.disabled = true;

      try {
        const res = await fetch('/api/ingest/approve', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({spec_id, table_name})
        });
        const data = await res.json();

        if (data.approved) {
          alertBox.className = 'alert alert-success';
          alertBox.innerHTML = `🎉 <strong>Deployment Successful!</strong> Applied to ClickHouse Cloud table <code>${data.table_name || table_name}</code>, registered in <code>chDB.schema_registry</code>, and synchronized with <code>chDB.business_context</code>.`;
        } else {
          alertBox.className = 'alert alert-info';
          alertBox.innerHTML = `Deployment completed with status: ${JSON.stringify(data.ddl_result)}`;
        }
      } catch (err) {
        alertBox.className = 'alert alert-info';
        alertBox.textContent = 'Deployment error: ' + err.message;
      } finally {
        deployBtn.innerHTML = '🚀 Approve & Deploy to Cloud';
        deployBtn.disabled = false;
      }
    }

    async function loadVizSnapshot() {
      try {
        const res = await fetch('/api/viz');
        const data = await res.json();
        const snap = data.snapshot || {};

        const schemas = snap.schema_history || [];
        const insights = snap.insights || [];
        const changelogs = snap.context_changelog || [];

        // KPI Counts
        document.getElementById('kpiSchemas').textContent = schemas.length;
        document.getElementById('kpiInsights').textContent = insights.length;
        document.getElementById('kpiChangelogs').textContent = changelogs.length;
        
        let avgConf = 0;
        if (insights.length > 0) {
          const sum = insights.reduce((acc, cur) => acc + (parseFloat(cur.confidence) || 0), 0);
          avgConf = Math.round((sum / insights.length) * 100);
        }
        document.getElementById('kpiConfidence').textContent = `${avgConf}%`;

        // Render Schema Registry
        const schemaDiv = document.getElementById('schemaRegistryContainer');
        if (schemas.length === 0) {
          schemaDiv.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">No tables registered in schema_registry yet. Run Ingestion on a feature spec to register tables.</p>';
        } else {
          let html = '<table class="table-view"><thead><tr><th>Table</th><th>Version</th><th>Spec ID</th><th>Created At</th><th>DDL</th></tr></thead><tbody>';
          schemas.forEach(s => {
            const tableName = s.table || s.table_name || 'unknown';
            html += `<tr>
              <td><strong><code>${tableName}</code></strong></td>
              <td><span class="badge">v${s.version || 1}</span></td>
              <td><code>${s.spec_id || 'N/A'}</code></td>
              <td style="color: var(--text-muted); font-size: 0.8rem;">${s.created_at || 'N/A'}</td>
              <td><details><summary style="cursor:pointer; color:#60A5FA;">Show DDL</summary><pre style="margin-top:0.4rem;">${s.ddl || '(DDL recorded in chDB)'}</pre></details></td>
            </tr>`;
          });
          html += '</tbody></table>';
          schemaDiv.innerHTML = html;
        }

        // Render Insights Feed
        const insightsDiv = document.getElementById('insightsContainer');
        if (insights.length === 0) {
          insightsDiv.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">No product insights generated yet. Query the Product Analyst via <code>/v1/chat/completions</code> or test suite.</p>';
        } else {
          let html = '';
          insights.forEach(ins => {
            const conf = Math.round((parseFloat(ins.confidence) || 0) * 100);
            const confColor = conf >= 70 ? '#10B981' : (conf >= 40 ? '#F59E0B' : '#EF4444');
            html += `<div class="insight-card">
              <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                  <strong style="color: #F3F4F6; font-size: 0.95rem;">${ins.question || 'Product Question'}</strong>
                  <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.2rem;">Spec: <code>${ins.spec_id || 'general'}</code> | Created: ${ins.created_at || 'recent'}</div>
                </div>
                <div style="text-align: right;">
                  <span class="badge" style="border-color: ${confColor}; color: ${confColor}; font-weight:700;">Confidence ${conf}%</span>
                  <div class="confidence-meter" style="width: 100px;">
                    <div class="confidence-fill" style="width: ${conf}%; background: ${confColor};"></div>
                  </div>
                </div>
              </div>
              <div style="margin-top: 0.75rem; font-size: 0.85rem; color: #CBD5E1; line-height: 1.5; white-space: pre-wrap; background: rgba(0,0,0,0.3); padding: 0.75rem; border-radius: 6px;">${ins.answer_md || 'Insight recorded.'}</div>
            </div>`;
          });
          insightsDiv.innerHTML = html;
        }

        // Render Context Changelog
        const changelogDiv = document.getElementById('changelogContainer');
        if (changelogs.length === 0) {
          changelogDiv.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">No context modifications logged yet.</p>';
        } else {
          let html = '<table class="table-view"><thead><tr><th>Timestamp</th><th>Change Type</th><th>Agent</th><th>Before -> After</th><th>Trace ID</th></tr></thead><tbody>';
          changelogs.forEach(c => {
            html += `<tr>
              <td style="color: var(--text-muted); font-size: 0.8rem;">${c.ts || 'recent'}</td>
              <td><span class="tag blue">${c.change_type || 'upsert'}</span></td>
              <td><code>${c.agent || 'agent'}</code></td>
              <td style="font-size: 0.8rem;"><span style="color:#F87171;">${c.before || '(None)'}</span> &rarr; <span style="color:#34D399;">${c.after || '(Updated)'}</span></td>
              <td style="font-family: monospace; font-size: 0.75rem; color: var(--text-muted);">${(c.trace_id || '').substring(0, 8)}...</td>
            </tr>`;
          });
          html += '</tbody></table>';
          changelogDiv.innerHTML = html;
        }

      } catch (err) {
        console.error('Error loading viz snapshot:', err);
      }
    }

    window.onload = function() {
      loadSpecs();
      if (window.location.pathname.includes('/ui/viz')) {
        showTab('viz');
      }
    };
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
@app.get("/ui/ingestion", response_class=HTMLResponse)
@app.get("/ui/viz", response_class=HTMLResponse)
def dashboard_ui():
    return HTMLResponse(content=_DASHBOARD_HTML, status_code=200)


def main():
    import uvicorn
    uvicorn.run("atlys_agentic.run_chat:app", host="0.0.0.0", port=8008, reload=True)


if __name__ == "__main__":
    main()

