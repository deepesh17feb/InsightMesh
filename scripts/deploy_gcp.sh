#!/usr/bin/env bash
# ==============================================================================
# InsightMesh 1-Click GCP Cloud Run Deployment Script
# Deploys: LibreChat UI (Ingress) + InsightMesh Backend (Sidecar) + MongoDB (Sidecar)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Default parameters
PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo "")}"
REGION="${GCP_REGION:-$(gcloud config get-value compute/region 2>/dev/null || echo "us-east1")}"
SERVICE_NAME="${CLOUD_RUN_SERVICE_NAME:-insightmesh-app}"
REPO_NAME="${ARTIFACT_REPO_NAME:-insightmesh-docker}"
ENV_FILE="${ENV_FILE:-.env}"

echo "=============================================================================="
echo "          InsightMesh GCP Cloud Run Deployment"
echo "=============================================================================="
echo "Repository Root: ${REPO_ROOT}"
echo "GCP Project:     ${PROJECT_ID}"
echo "GCP Region:      ${REGION}"
echo "Service Name:    ${SERVICE_NAME}"
echo "Artifact Repo:   ${REPO_NAME}"
echo "Env File:        ${ENV_FILE}"
echo "=============================================================================="

# Pre-flight: Check gcloud CLI
if ! command -v gcloud &> /dev/null; then
    echo "ERROR: 'gcloud' CLI is not installed or not in PATH."
    exit 1
fi

if [ -z "${PROJECT_ID}" ] || [ "${PROJECT_ID}" = "(unset)" ]; then
    echo "ERROR: No active GCP project configured."
    echo "Please run: gcloud config set project YOUR_PROJECT_ID"
    echo "Or set: export GCP_PROJECT_ID=YOUR_PROJECT_ID"
    exit 1
fi

# Load environment variables if .env exists
if [ -f "${ENV_FILE}" ]; then
    echo "Loading environment variables from ${ENV_FILE}..."
    # Export vars while ignoring comments and empty lines
    set -a
    # shellcheck disable=SC1090
    source <(grep -v '^#' "${ENV_FILE}" | grep -v '^$')
    set +a
fi

# 1. Enable Required GCP APIs
echo ""
echo "[Step 1/6] Enabling required GCP APIs (Cloud Run, Artifact Registry, Cloud Build)..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    --project="${PROJECT_ID}"

# 2. Ensure Artifact Registry repository exists
echo ""
echo "[Step 2/6] Verifying Artifact Registry repository '${REPO_NAME}'..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "Creating Artifact Registry repository '${REPO_NAME}' in ${REGION}..."
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="InsightMesh container images" \
        --project="${PROJECT_ID}"
else
    echo "Repository '${REPO_NAME}' already exists."
fi

BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/backend:latest"
LIBRECHAT_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/librechat:latest"

# 3. Build & Push Backend Container Image
echo ""
echo "[Step 3/6] Building and pushing Backend image (${BACKEND_IMAGE})..."
gcloud builds submit \
    --config=- \
    --project="${PROJECT_ID}" \
    "${REPO_ROOT}" <<EOF
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', '${BACKEND_IMAGE}', '-f', 'Dockerfile.backend', '.']
images:
  - '${BACKEND_IMAGE}'
EOF

# 4. Build & Push LibreChat Container Image
echo ""
echo "[Step 4/6] Building and pushing LibreChat image (${LIBRECHAT_IMAGE})..."
gcloud builds submit \
    --config=- \
    --project="${PROJECT_ID}" \
    "${REPO_ROOT}" <<EOF
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', '${LIBRECHAT_IMAGE}', '-f', 'Dockerfile.librechat', '.']
images:
  - '${LIBRECHAT_IMAGE}'
EOF

# 5. Prepare Cloud Run Service YAML with substituted variables
echo ""
echo "[Step 5/6] Generating Cloud Run service definition..."
TEMP_YAML="$(mktemp /tmp/cloudrun-deploy-XXXXXX.yaml)"

# Substitute image paths and runtime credentials
sed \
    -e "s|REGION-docker.pkg.dev/PROJECT_ID/insightmesh-docker/librechat:latest|${LIBRECHAT_IMAGE}|g" \
    -e "s|REGION-docker.pkg.dev/PROJECT_ID/insightmesh-docker/backend:latest|${BACKEND_IMAGE}|g" \
    -e "s|\${GEMINI_API_KEY}|${GEMINI_API_KEY:-}|g" \
    -e "s|\${CLICKHOUSE_HOST}|${CLICKHOUSE_HOST:-}|g" \
    -e "s|\${CLICKHOUSE_PORT:-8443}|${CLICKHOUSE_PORT:-8443}|g" \
    -e "s|\${CLICKHOUSE_USER:-default}|${CLICKHOUSE_USER:-default}|g" \
    -e "s|\${CLICKHOUSE_PASSWORD}|${CLICKHOUSE_PASSWORD:-}|g" \
    -e "s|\${CLICKHOUSE_DATABASE:-default}|${CLICKHOUSE_DATABASE:-default}|g" \
    -e "s|\${CLICKHOUSE_SECURE:-true}|${CLICKHOUSE_SECURE:-true}|g" \
    -e "s|\${LANGFUSE_PUBLIC_KEY}|${LANGFUSE_PUBLIC_KEY:-}|g" \
    -e "s|\${LANGFUSE_SECRET_KEY}|${LANGFUSE_SECRET_KEY:-}|g" \
    -e "s|\${LANGFUSE_HOST:-https://us.cloud.langfuse.com}|${LANGFUSE_HOST:-https://us.cloud.langfuse.com}|g" \
    -e "s|\${LANGFUSE_TRACING_ENABLED:-true}|${LANGFUSE_TRACING_ENABLED:-true}|g" \
    "${REPO_ROOT}/deploy/cloudrun-all-in-one.yaml" > "${TEMP_YAML}"

# Deploy Cloud Run service
echo "Deploying '${SERVICE_NAME}' to Cloud Run in ${REGION}..."
gcloud run services replace "${TEMP_YAML}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}"

rm -f "${TEMP_YAML}"

# Allow public unauthenticated access for web UI
echo "Configuring public access for LibreChat web interface..."
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --member="allUsers" \
    --role="roles/run.invoker" \
    --region="${REGION}" \
    --project="${PROJECT_ID}"

# 6. Retrieve Service URL and Verify
echo ""
echo "[Step 6/6] Verifying deployment..."
SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')"

echo "=============================================================================="
echo "  InsightMesh Successfully Deployed to GCP Cloud Run!"
echo "=============================================================================="
echo "  Public Web UI: ${SERVICE_URL}"
echo ""
echo "  Available Agent Personas:"
echo "    1. Atlys Instrumentation Engineer (CUJ 1 Ingestion)"
echo "    2. Atlys Product Analyst (CUJ 2 Analytics)"
echo "=============================================================================="
