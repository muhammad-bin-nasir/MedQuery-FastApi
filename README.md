# MedQuery RAG API

FastAPI-only backend for a multi-tenant, medical RAG platform using PostgreSQL + pgvector.

## Features
- Multi-tenant isolation by `business_client_id` + `workspace_id`.
- Admin JWT authentication (optional super admin).
- Workspace configuration for chunking, retrieval, and chat defaults.
- Document ingestion (PDF/TXT), chunking, embeddings, pgvector storage.
- Retrieval-only and chat endpoints.
- Full Swagger/OpenAPI docs at `/docs`.

## Setup

### 1) Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure environment
Create a `.env` file:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/medquery
JWT_SECRET_KEY=change-me
OPENAI_API_KEY=sk-...
VECTOR_DIMENSION=384
```

### 3) Database and migrations
```bash
alembic upgrade head
```

### 4) Run the API
```bash
uvicorn app.main:app --reload
```

### 5) Open the test UI
Visit `http://localhost:8000/ui` for a ChatGPT-style console that targets the existing
`/api/chat/generate` and `/api/rag/retrieve` endpoints. Provide a bearer token if your
workspace requires authentication.

## Docker setup

### 1) Configure environment
Create a `.env` file in the repo root (same variables as above):
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/medquery
JWT_SECRET_KEY=change-me
OPENAI_API_KEY=sk-...
VECTOR_DIMENSION=384
```

### 2) Start services
```bash
docker compose up --build
```

### 3) Run migrations
```bash
docker compose exec api alembic upgrade head
```

### 4) Open the UI
Visit `http://localhost:8000/ui` to use the testing console (same endpoints consumed by third parties).

### 5) Docker memory (document ingestion)
The API container is limited to **4GB** memory; PDFs are processed **page-by-page** with small embedding batches so usage stays under the limit. PDF extraction uses **PyMuPDF** by default (pypdf can spike to several GB on small files that contain inline images or large content streams). On **Linux (Docker)**, each page is extracted in a **subprocess with a 768MB memory limit** so one bad page cannot OOM the API; if a page hits the limit it is skipped and ingestion continues. If you still see crashes:
- In Docker Desktop: **Settings → Resources** and increase **Memory** (e.g. 8GB) so the 4GB container limit can be used.
- **Exit code 137** = out-of-memory (OOM) kill; the process is killed before Python can write a crash file, so **no `crash_*.log` is created**. The **last line** of **`./logs/crashes/ingest_progress.log`** shows the last step and memory before the kill. The same progress lines are also in **`docker compose logs api`**.
- Full crash reports (for caught exceptions, not OOM) are in **`./logs/crashes/crash_*.log`**. **`./logs/ingestion.log`** contains a step-by-step log of every document upload (file size, extracted text preview, chunk counts, embedding batches, commits, memory at each step). See **`logs/README.md`** for the full log layout. The repo includes **`logs/crashes/`**; the API writes via volume **`./logs:/app/logs`** and **`CRASH_LOG_DIR`** / **`INGESTION_LOG_DIR`**. If no log files appear, ensure the API container is starting (e.g. `docker compose logs api`) and that the volume mount is correct.

## API Walkthrough

### Bootstrap a super admin
If no admins exist, `POST /api/admin/auth/create-admin` can be called without a token:
```json
{
  "business_client_id": "acme",
  "email": "admin@acme.com",
  "password": "secret",
  "role": "super_admin"
}
```

### Login
```json
POST /api/admin/auth/login
{
  "business_client_id": "acme",
  "email": "admin@acme.com",
  "password": "secret"
}
```

### Create business
```json
POST /api/admin/businesses
{
  "business_client_id": "acme",
  "name": "Acme Health"
}
```

### Create workspace
```json
POST /api/admin/businesses/acme/workspaces
{
  "workspace_id": "main",
  "name": "Main Workspace"
}
```

### Update workspace config
```json
PUT /api/admin/businesses/acme/workspaces/main/config
{
  "chunk_words": 300,
  "overlap_words": 50,
  "top_k": 5,
  "similarity_threshold": 0.2,
  "max_context_chars": 12000,
  "embedding_model": "text-embedding-3-small",
  "chat_model_default": "gpt-4.1-mini",
  "chat_temperature_default": 0.2,
  "chat_max_tokens_default": 600
}
```

### Upload and index documents
```bash
curl -X POST \
  -H "Authorization: Bearer <TOKEN>" \
  -F "file=@guide.pdf" \
  "http://localhost:8000/api/admin/businesses/acme/workspaces/main/documents/upload"
```

### Retrieve chunks
```json
POST /api/rag/retrieve
{
  "business_client_id": "acme",
  "workspace_id": "main",
  "user_id": "u123",
  "query": "What are symptoms of ...?",
  "top_k": 5
}
```

### Generate chat response
```json
POST /api/chat/generate
{
  "business_client_id": "acme",
  "workspace_id": "main",
  "user_id": "u123",
  "query": "User question here",
  "prompt_engineering": "You are a medical assistant. Provide concise answers.",
  "chat_config_override": {
    "model": "gpt-4.1-mini",
    "temperature": 0.2,
    "max_tokens": 600
  }
}
```

## Notes
- `pgvector` extension is created via Alembic migration.
- Document deletion cascades to chunks.
- All retrieval operations are filtered by `business_id` and `workspace_id`.
- `VECTOR_DIMENSION` must match the embedding model dimension used in workspace configs.

### Local embeddings (no OpenAI API)

You can create embeddings **locally** so no API key or network call is needed:

1. Install the optional dependency: `pip install -r requirements-local-embeddings.txt`. The default Docker image does **not** include `sentence-transformers` (it pulls PyTorch and can cause long/failing builds); use this file only when you need local embeddings.
2. In `.env` set:
   - `USE_LOCAL_EMBEDDINGS=true`
   - `LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` (default; 384 dimensions)
   - `VECTOR_DIMENSION=384` (must match the local model)
3. If your database was created with 384-dim vectors (OpenAI default), you must add a migration to alter `document_chunks.embedding` to 384 dimensions and re-ingest documents, or use a fresh database.

Local embeddings avoid API cost and work offline; the model is loaded in memory (~100–400 MB depending on the model).


============================================================
🚀 Quick Start Commands

Start everything (build if needed)
docker compose up -d

▶️ Build fresh + start (use ONLY when requirements.txt changes)
docker compose up -d --build

⚡ For code changes (NO rebuild needed - code is mounted as volume)
docker compose restart api
# OR just restart the container - code changes reflect immediately!

💡 Development Tip: Code is mounted as volume, so:
   - Code changes → Just restart: docker compose restart api
   - Requirements change → Rebuild: docker compose up -d --build api

⏹ Stop all services (keep data)
docker compose down


💥 Stop + delete volumes (DANGEROUS – deletes DB data)
docker compose down -v

🔄 Restart all services
docker compose restart

🔄 Restart one service only
docker compose restart api

🔹 Check Status / Health
👀 See running containers
docker compose ps

👀 See ALL containers (running + crashed)
docker compose ps -a

🔎 See only Docker-level containers
docker ps
docker ps -a



🔹 Logs (THIS IS HOW YOU DEBUG)
📜 View logs of a service
docker compose logs api

📜 Last 100 lines
docker compose logs --tail 100 api

📡 Live logs (watch crashes in real time)
docker compose logs -f api

📜 Logs of DB
docker compose logs postgres

🔹 Enter Inside Containers (Very Important)
🧠 Enter API container shell
docker compose exec api bash

🧠 Enter Postgres container
docker compose exec postgres bash

🔹 Run Commands Inside Containers
▶️ Run Alembic migration
docker compose exec api alembic upgrade head

▶️ Run Python command inside API
docker compose exec api python -c "print('hello')"

▶️ Check env variable inside container
docker compose exec api printenv DATABASE_URL

🔹 Database (Postgres)
🔐 Open psql shell
docker compose exec postgres psql -U postgres -d medquery

🔎 List tables
\dt

🔎 View table data
SELECT * FROM businesses;

❌ Exit psql
\q

🔹 Cleanup Commands (Use Carefully)
🧹 Remove stopped containers
docker container prune

🧹 Remove unused images
docker image prune

💣 Remove EVERYTHING (last resort)
docker system prune -a

🔹 Very Common Fixes
❌ Container crashes instantly
docker compose logs api

❌ Port not opening
docker compose ps

❌ Code change not reflected
docker compose up -d --build

❌ DB messed up (DEV ONLY)
docker compose down -v
docker compose up -d --build

🔹 Mental Model (IMPORTANT)

Image = blueprint (built once)

Container = running process (dies, restarts)

up → builds image → starts container

restart → restarts container (NO rebuild)

.env → loaded ONLY into container

Logs ALWAYS tell the truth

✅ Minimum Daily Workflow (MEMORIZE)
docker compose up -d --build
docker compose ps   //logs
docker compose logs -f api //logs
docker compose restart api
