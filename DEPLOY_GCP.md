# InsightMesh GCP Cloud Run Deployment Guide (`DEPLOY_GCP.md`)

This guide explains how to deploy the entire **InsightMesh** production stack to **Google Cloud Platform (GCP) Cloud Run**:
- **LibreChat Web UI** (Ingress / Frontend)
- **InsightMesh Backend App** (FastAPI, CrewAI, chDB, ClickHouse Cloud, Langfuse)
- **MongoDB** (LibreChat user & session state database)

---

## 1. Architecture Overview

InsightMesh runs on Google Cloud Run utilizing **Multi-Container Pods (Sidecars)**:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Google Cloud Run Service: insightmesh-app                                   │
│                                                                             │
│  ┌───────────────────────┐                                                  │
│  │ Ingress: LibreChat    │ ─── http://127.0.0.1:8008/v1 ──┐                 │
│  │ (Port 8080 - Public)  │                                │                 │
│  └───────────┬───────────┘                                ▼                 │
│              │                                ┌───────────────────────┐     │
│              │ mongodb://127.0.0.1:27017      │ Sidecar 1: Backend    │     │
│              ▼                                │ (Port 8008 - Private) │     │
│  ┌───────────────────────┐                    └───────────────────────┘     │
│  │ Sidecar 2: MongoDB    │                                │                 │
│  │ (Port 27017 - Private)│                                │                 │
│  └───────────────────────┘                                │                 │
└───────────────────────────────────────────────────────────┼─────────────────┘
                                                            │
                            ┌───────────────────────────────┴───────────────┐
                            ▼                                               ▼
                ClickHouse Cloud (Data Warehouse)          Google Gemini (LLM)
```

- **Single Public HTTPS URL**: The user accesses LibreChat directly through Cloud Run's secure managed HTTPS domain.
- **Zero Latency Loopback**: LibreChat, the FastAPI backend, and MongoDB communicate directly over `127.0.0.1` (localhost loopback) within the same container sandbox.
- **Cost Effective & Serverless**: Auto-scales dynamically based on traffic.

---

## 2. Prerequisites

1. **Google Cloud SDK (`gcloud`)**:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_GCP_PROJECT_ID
   gcloud config set compute/region us-east1
   ```

2. **Environment Variables (`.env`)**:
   Ensure `.env` contains your runtime credentials:
   ```ini
   # LLM Provider
   GEMINI_API_KEY=your-gemini-api-key
   LLM_MODEL=gemini/gemini-2.0-flash

   # ClickHouse Cloud
   CLICKHOUSE_HOST=your-clickhouse.clickhouse.cloud
   CLICKHOUSE_PORT=8443
   CLICKHOUSE_USER=default
   CLICKHOUSE_PASSWORD=your-password
   CLICKHOUSE_DATABASE=default
   CLICKHOUSE_SECURE=true

   # Observability (Optional)
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://us.cloud.langfuse.com
   LANGFUSE_TRACING_ENABLED=true
   ```

---

## 3. One-Command 1-Click Deployment

To build the images and deploy to Cloud Run automatically:

```bash
bash scripts/deploy_gcp.sh
```

### What this script does:
1. Enables required GCP APIs (`run.googleapis.com`, `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com`).
2. Creates an Artifact Registry Docker repository (`insightmesh-docker`).
3. Builds the Backend and LibreChat images in Google Cloud Build.
4. Generates the multi-container Cloud Run service spec and deploys `insightmesh-app`.
5. Binds IAM permissions (`roles/run.invoker`) for public web access.
6. Returns the live HTTPS Cloud Run URL.

---

## 4. Local Simulation Before Deploying

You can run and test the identical 3-container Cloud Run environment locally:

```bash
# Build and start all 3 containers locally
docker compose -f docker-compose.cloudrun-sim.yml up --build -d

# Check status
docker compose -f docker-compose.cloudrun-sim.yml ps

# Test backend healthcheck
curl http://localhost:8008/healthz

# Open LibreChat UI
# Open http://localhost:3080 in your browser
```

To stop:
```bash
docker compose -f docker-compose.cloudrun-sim.yml down
```

---

## 5. Deployment Options & Specifications

The repository includes ready-to-use specifications in `deploy/`:

- **`deploy/cloudrun-all-in-one.yaml`**: Recommended unified multi-container deployment (LibreChat + Backend + MongoDB in 1 service).
- **`deploy/cloudrun-backend.yaml`**: Standalone backend Cloud Run service.
- **`deploy/cloudrun-frontend.yaml`**: Decoupled LibreChat + MongoDB frontend service.
- **`Dockerfile.backend`**: Multi-stage Python 3.11 container for the FastAPI app.
- **`Dockerfile.librechat`**: LibreChat image configured for InsightMesh custom agents.
