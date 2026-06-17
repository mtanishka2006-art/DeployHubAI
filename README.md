# DeployHub AI

**AI-Powered Infrastructure Observability, Incident Intelligence, and Disaster
Recovery Platform.**

DeployHub AI ingests infrastructure and deployment telemetry from 13 enterprise
sources, normalizes it through a connector framework, and runs a pipeline of
specialized AI agents — orchestrated by a LangGraph **Mission Control Center** —
to monitor health, detect incidents, perform root-cause analysis, score disaster
recovery readiness, retrieve historical incident knowledge (RAG), and recommend
recovery actions. Its differentiator is an **AI Disaster Simulation Engine** that
answers *"what happens if AWS us-east-1 fails?"* before it ever does.

> **Runs immediately, anywhere.** Every external dependency degrades gracefully:
> no Kafka → in-process event bus; no ChromaDB → in-memory cosine store; no
> Sentence-Transformers → deterministic hashing embedder; no LangGraph →
> sequential orchestrator; no `ANTHROPIC_API_KEY` → deterministic heuristic
> agents. So `docker compose up` (or even a bare `uvicorn`) gives you a fully
> populated, working dashboard with zero configuration.

---

## Architecture

```
Data Sources (13)
      │   Jenkins · GitHub Actions · AWS CloudWatch/CloudTrail ·
      │   Azure Monitor/Activity · Kubernetes · App/Infra Logs ·
      │   DR · Backup · Replication · Failover
      ▼
Data Ingestion Layer        BaseConnector + 7 connectors → Unified Event Schema → Kafka
      ▼
Data Storage Layer          PostgreSQL (SQLAlchemy + Alembic)
      ▼
Data Processing Layer       Metric / Log / Deployment / DR processors
      ▼                       (clean → feature-extract → enrich → embed → persist)
Agent Layer                 Monitoring · RCA · DR · Recovery
      ▼
Infrastructure Memory       ChromaDB + Sentence-Transformers (enterprise RAG)
      ▼
Mission Control Center      LangGraph StateGraph orchestrating all agents
      ▼
Dashboard                   Next.js + React + TypeScript + Tailwind
```

### Repository layout

```
DeployHub AI/
├── backend/                       FastAPI service
│   ├── app/
│   │   ├── config.py              env-driven settings (+ feature flags)
│   │   ├── main.py                app wiring, lifespan, table create + seed
│   │   ├── core/                  logging, security (JWT + RBAC)
│   │   ├── db/                    Base, session, 12 ORM models
│   │   ├── schemas/               Unified Event Schema + API Pydantic models
│   │   ├── messaging/             Kafka event bus (+ in-memory fallback), topics
│   │   ├── ingestion/             BaseConnector + 7 connectors + registry
│   │   ├── processing/            4 processors over the unified events
│   │   ├── memory/                embeddings, vector store, Infrastructure Memory (RAG)
│   │   ├── agents/                Monitoring / RCA / DR / Recovery (+ optional LLM)
│   │   ├── mission_control/       context builder, state, LangGraph orchestrator
│   │   ├── simulation/            topology graph, scenario catalog, blast-radius engine
│   │   ├── api/                   deps (RBAC) + routers
│   │   └── seed/                  realistic demo data
│   ├── alembic/                   migrations (baseline 0001_initial)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                      Next.js 14 App Router dashboard (6 pages)
│   ├── app/                       overview, incidents, disaster-recovery,
│   │                              memory, mission-control, simulation
│   ├── components/                shadcn-style UI primitives + widgets
│   ├── lib/                       typed API client + shared types
│   └── Dockerfile
├── docker-compose.yml             frontend · backend · postgres · chromadb · kafka · zookeeper
└── .env.example
```

---

## Quick start

### Option A — Docker Compose (full stack)

```bash
cp .env.example .env          # optional: set ADMIN_PASSWORD / ANTHROPIC_API_KEY
docker compose up -d --build
```

| Service   | URL                                |
|-----------|------------------------------------|
| Dashboard | http://localhost:3000              |
| API docs  | http://localhost:8000/docs         |
| Health    | http://localhost:8000/health       |

The backend auto-creates tables and seeds realistic data on first boot, so the
dashboard is populated immediately.

### Option B — Local dev (no infra required)

```bash
# Backend (SQLite + in-memory fallbacks; zero config)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000/docs

# Frontend
cd ../frontend
npm install
npm run dev                            # http://localhost:3000
```

### Default logins (seeded)

| Username | Password | Role            |
|----------|----------|-----------------|
| `admin`  | `admin`  | Admin           |
| `sre`    | `sre`    | SRE             |
| `devops` | `devops` | DevOps Engineer |
| `viewer` | `viewer` | Viewer          |

---

## API

All endpoints are under `/api` and documented at `/docs` (OpenAPI). Auth is JWT
bearer; RBAC is hierarchical (Admin ⊇ SRE ⊇ DevOps ⊇ Viewer).

| Method | Endpoint                      | Min role | Purpose                                  |
|--------|-------------------------------|----------|------------------------------------------|
| POST   | `/api/auth/login`             | —        | Obtain JWT                               |
| GET    | `/api/overview`               | Viewer   | Dashboard aggregate                      |
| GET    | `/api/metrics`                | Viewer   | Infrastructure metrics                   |
| GET/POST | `/api/incidents`            | Viewer/DevOps | List / declare incidents            |
| GET    | `/api/deployments`            | Viewer   | Deployment history                       |
| GET    | `/api/dr/status`              | Viewer   | DR readiness + backups/replication/failover |
| POST   | `/api/memory/search`          | Viewer   | Semantic RAG over incident knowledge     |
| POST   | `/api/mission-control/run`    | SRE      | Run the full agent orchestration         |
| POST   | `/api/simulation/run`         | DevOps   | Run a disaster simulation                |

---

## The AI agents

| Agent          | Inputs                                   | Output                                  |
|----------------|------------------------------------------|-----------------------------------------|
| **Monitoring** | metrics, logs                            | `health_status`, score, anomalies, alerts |
| **RCA**        | logs, metrics, deploy history, memory    | `root_cause`, confidence, ranked hypotheses |
| **DR**         | backups, replication, failover           | `dr_score`, `readiness`, risks          |
| **Recovery**   | RCA, DR assessment, similar incidents    | ranked `recommendations`, rollback/failover guidance |

Agents are deterministic by default (correlation, thresholds, z-score spikes,
weighted scoring). Setting `ANTHROPIC_API_KEY` lets Mission Control upgrade the
executive summary and rationales with **Claude (`claude-opus-4-8`)**, always
falling back to the heuristic output if the call fails.

## Mission Control (LangGraph)

`receive incident → Monitoring → RCA → DR → query Memory → Recovery → aggregate
→ Unified Incident Report`. Each node persists an `AgentOutput`; the final report
is stored as a `MissionControlReport` and its recommendations are materialized as
`RecoveryAction` rows on the incident.

## Disaster Simulation Engine

A directed dependency topology (services → clusters → regions → clouds, plus DB,
CI, replication edges) is walked to: **trace dependencies → identify affected
services → predict blast radius → estimate downtime → suggest recovery strategy
→ produce a tier-ordered failover sequence.** Supported scenarios:
`aws_region_outage`, `azure_outage`, `kubernetes_cluster_failure`,
`database_failure`, `jenkins_failure`, `deployment_rollback`,
`cross_cloud_migration`.

---

## Configuration

| Variable                  | Default                          | Effect                                    |
|---------------------------|----------------------------------|-------------------------------------------|
| `DATABASE_URL`            | `sqlite:///./deployhub.db`       | Postgres in Docker; SQLite locally        |
| `KAFKA_BOOTSTRAP_SERVERS` | *(empty)*                        | Empty → in-memory event bus               |
| `CHROMA_HOST` / `CHROMA_PERSIST_DIR` | local persist dir     | Remote Chroma server vs local persistence |
| `ANTHROPIC_API_KEY`       | *(empty)*                        | Empty → heuristic agents                  |
| `JWT_SECRET`              | dev default                      | **Set in production**                     |
| `SEED_ON_STARTUP`         | `true`                           | Seed demo data on boot                    |

## Database migrations

```bash
cd backend
alembic upgrade head                          # apply baseline schema
alembic revision --autogenerate -m "change"   # after editing models
```

## Tech stack

FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL · Kafka · ChromaDB ·
Sentence-Transformers · LangGraph · Anthropic Claude (optional) · Next.js 14 ·
React · TypeScript · TailwindCSS · Docker Compose.
