# InsightMesh Web Frontend (Next.js + Vercel)

A lightweight, modern web interface for **InsightMesh** — designed for 1-click deployment on **Vercel** with zero configuration.

---

## 🌟 Features

* **Dual AI Agents**:
  * 🛠️ **Atlys Instrumentation Engineer** (CUJ 1: Ingestion, schema inference, ClickHouse DDL generation, Materialized Views)
  * 📊 **Atlys Product Analyst** (CUJ 2: ClickHouse data exploration, conversion funnel queries, retention analysis)
* **Real-Time Streaming**: Low-latency token streaming via Server-Sent Events (SSE).
* **Rich Markdown & SQL Highlighting**: Formatted ClickHouse DDL, SummingMergeTree schema definitions, tables, and context diffs.
* **1-Click Copy**: Easily copy generated SQL queries and DDL to clipboard.
* **Zero Local Dependencies**: 100% serverless, zero database required, open to all internet users.

---

## 🚀 1-Minute Vercel Deployment

### Method A: Via Vercel CLI

```bash
cd frontend
npm install
npx vercel
```

### Method B: Via Vercel Web Dashboard

1. Push your repository to GitHub / GitLab.
2. Open [vercel.com/new](https://vercel.com/new) and import your repo.
3. Set **Root Directory** to `frontend`.
4. In **Environment Variables**, add:
   * `INSIGHTMESH_BACKEND_URL`: `https://insightmesh-backend.onrender.com`
5. Click **Deploy**!

---

## 💻 Local Development

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.
