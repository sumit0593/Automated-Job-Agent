# Automated Job Agent 🤖🚀

> An enterprise-grade, open-source AI agent system designed for automated job discovery, agentic RAG matching, background scheduling, multi-agent state graph orchestration, and automated application filling across job boards (LinkedIn, Naukri, Greenhouse, Lever, Workday, Ashby, SmartRecruiters, etc.).

---

## 🌟 Key Features

- ⚡ **10/10 Enterprise Hybrid Match Cache Engine**:
  - **Tiered Hot/Cold Caching**: Redis Hot Cache (< 1ms) with SQLite/PostgreSQL Cold Cache (< 5ms) fallback.
  - **Circuit Breaker PING Monitor**: Instant zero-delay fallback to DB cold cache if Redis is offline or unreachable.
  - **Decoupled Resume Hashing**: `resume_embedding_hash` (skills + experience + raw text) is decoupled from metadata (CTC/Location). Updating CTC/location reuses precomputed embeddings without calling LLMs!
  - **Distributed `SETNX` Locks**: 30s auto-expiry locks prevent thundering-herd RAG calls across worker processes.
  - **Separate Vector & Reranker Caches**: Caches precomputed vectors (`emb:resume:{hash}`, `emb:job:{hash}`) and Cross-Encoder probabilities (`rerank:{resume_emb_hash}:{job_hash}`).
  - **Financial Savings Telemetry**: Real-time tracking of hit rates, LLM calls saved, and dollar savings.

- 📊 **Dual Observability & Tracing (Langfuse + LangSmith)**:
  - Full trace observability across LangGraph state machines and LangChain RAG pipelines.
  - Integrated with **Langfuse US Cloud** (`https://us.cloud.langfuse.com`) and **LangSmith** (`LANGSMITH_PROJECT="Automated-Job-Agent"`).

- 🌐 **Multi-Board Public ATS Scraper & Job Discovery**:
  - **Public ATS Engine**: Discovers job listings across 17+ top tech company boards (`Stripe`, `Figma`, `Airbnb`, `Reddit`, `Lyft`, `GitHub`, `Cloudflare`, `Coinbase`, `Datadog`, `Instacart`, `Scale AI`, `Cohere`, `Discord`, `Canva`, `Roblox`, `Robinhood`) for keyword role discovery (`GenAI`, `Python`, `Full Stack`).
  - **Portal Auto-Detection**: Distinguishes between authenticated portals (`Naukri`, `LinkedIn`, `Wellfound`, `Workday`) requiring stored credentials and public ATS forms (`Greenhouse`, `Lever`, `Ashby`, `SmartRecruiters`, `Indeed`, `Glassdoor`) that submit directly without login.

- 🤖 **LangGraph Multi-Agent State Graph Orchestrator**:
  - State machine routing across `PlannerAgent`, `RetrieverAgent`, `MatcherAgent`, `TailorAgent`, `ApplicationAgent`, and `ReflectionAgent`.

- ⏰ **Persistent Scheduler & Task Queue**:
  - SQLite-backed queue with priority levels, payload hash deduplication, and exponential backoff retries.
  - Recurring cron schedules (e.g. run job discovery every weekday at 9 AM & 6 PM) that **persist across server reloads and system restarts**.
  - Built-in **Token-Bucket Rate Limiter** to prevent platform bans (LinkedIn: 25/day, Naukri: 50/day).

- 🌐 **Browser Session Pool & Stealth Automation**:
  - Pre-warmed Playwright browser context pool with active session cookie persistence.
  - Advanced anti-detection stealth measures (hides `navigator.webdriver`, rotates user-agents and viewports).

- 💻 **Modern Web Interface**:
  - React 19 + Vite dashboard for managing candidate profile data, uploading resumes, viewing job matches, and monitoring application status.

---

## 🏗️ System Architecture

```
                             [ React Frontend (Vite) ]
                                  http://localhost:5173
                                           │
                                           ▼
                            [ FastAPI Backend Engine ]
                                  http://localhost:8000
                                           │
          ┌────────────────────────────────┼────────────────────────────────┐
          ▼                                ▼                                ▼
[ LangGraph Multi-Agent ]     [ Enterprise Cache Engine ]         [ Observability Tracing ]
 ├─ StateGraph Pipeline        ├─ Redis Hot Cache (< 1ms)          ├─ Langfuse US Cloud
 ├─ Planner & Matcher Agents   ├─ DB Cold Cache (< 5ms)           ├─ LangSmith Project Tracing
 ├─ Application Agent          ├─ Circuit Breaker Monitor          └─ Real-Time Cost Telemetry
 └─ Reflection Loop            └─ SETNX Stampede Locks
          │                                │                                │
          └────────────────────────────────┼────────────────────────────────┘
                                           ▼
                            [ Storage & Vector Layer ]
                              ├─ SQLite (job_agent.db) / PostgreSQL
                              ├─ Qdrant Vector Store (qdrant_db/)
                              └─ Encrypted Session Cookies & Profiles
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** & `npm`
- **Playwright** (`playwright install chromium`)

---

### Step 1: Environment Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/sumit0593/Automated-Job-Agent.git
   cd Automated-Job-Agent
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. Install backend dependencies:
   ```bash
   pip install -r backend/requirements.txt
   playwright install chromium
   ```

4. Create your environment configuration file from the template:
   ```bash
   cp .env.example .env
   ```
   *(Edit `.env` to add your optional API keys for Gemini, Langfuse, LangSmith, Grok, OpenAI, or Hugging Face)*.

---

### Step 2: Start the Application

#### Option A: Running Locally (Development Mode)

1. **Start Backend Server**:
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```

2. **Start Frontend Dashboard**:
   Open a second terminal window:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. Access the interfaces:
   - **React Dashboard UI**: [http://localhost:5173](http://localhost:5173)
   - **Interactive API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

#### Option B: Background Service via PM2 (24/7 Service)

To run both backend and frontend as persistent background processes on Windows or Linux:

```bash
# Install PM2 globally
npm install -g pm2

# Start all services using ecosystem configuration
pm2 start ecosystem.config.js

# View live background status
pm2 status

# View logs
pm2 logs
```

---

## 📡 API Reference & Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | System health check and database status |
| `GET` | `/api/llm/status` | View router strategy, active providers, and real-time cost tracking |
| `GET` | `/api/matching/match` | Agentic RAG candidate-to-job matching & vector rankings |
| `POST` | `/api/jobs/scrape` | Trigger multi-board public ATS & portal job discovery |
| `GET` | `/api/schedule/status` | View scheduler status, queue stats, and active rate limits |
| `GET` | `/api/schedule/schedules` | List all active recurring schedules |
| `POST` | `/api/schedule/discovery` | Add recurring job discovery scan |
| `POST` | `/api/schedule/batch-apply` | Queue staggered auto-application task batch |

---

## 🔒 Security & Privacy Notice

- **Public Repository Safety**: Sensitive files (such as `.env`, `job_agent.db`, `qdrant_db/`, session cookies, and uploaded resumes) are excluded via `.gitignore`.
- **Session Encryption**: Browser session cookies stored in SQLite are encrypted using Fernet symmetric encryption (`cryptography` library).

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.