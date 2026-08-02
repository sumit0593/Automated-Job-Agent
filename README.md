# Automated Job Agent 🤖🚀

> An autonomous, open-source AI agent system designed for automated job discovery, intelligent resume matching, background scheduling, and automated application filling across job boards (LinkedIn, Naukri, Greenhouse, Lever, Workday, etc.).

---

## 🌟 Key Features

- 🧠 **Multi-LLM Task Router**:
  - Automatically routes tasks based on complexity across **Google Gemini (`3.5 Flash`, `3.1 Flash-Lite`)**, **xAI Grok**, **OpenAI (`gpt-4o`)**, **Hugging Face**, and **Local Ollama**.
  - Includes cost tracking and automatic fallback chains.

- ⏰ **Persistent Scheduler & Task Queue**:
  - SQLite-backed queue with priority levels, payload hash deduplication, and exponential backoff retries.
  - Recurring cron schedules (e.g. run job discovery every weekday at 9 AM & 6 PM) that **persist across server reloads and system restarts**.
  - Built-in **Token-Bucket Rate Limiter** to prevent platform bans (LinkedIn: 25/day, Naukri: 50/day).

- ⚡ **Agentic RAG Job Matching**:
  - Multi-stage retrieval: HyDE query expansion → Qdrant Vector Store hybrid search → BGE Cross-Encoder reranking.

- 🌐 **Browser Session Pool & Stealth Automation**:
  - Pre-warmed Playwright browser context pool with active session cookie persistence.
  - Advanced anti-detection stealth measures (hides `navigator.webdriver`, rotates user-agents and viewports).

- 👁️ **Vision-Based Page Navigator**:
  - Iterative screenshot → LLM Vision → Action loop for unknown external application forms when traditional DOM selectors fail.

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
[ Multi-LLM Task Router ]     [ Scheduler & Queue System ]        [ Browser Session Pool ]
 ├─ Gemini 3.5 Flash           ├─ APScheduler Cron Engine         ├─ Warm Playwright Contexts
 ├─ Gemini 3.1 Flash-Lite      ├─ SQLite Task Queue (Persisted)   ├─ Anti-Detection Stealth JS
 ├─ Grok 3 / Grok Mini         ├─ Per-Platform Rate Limiter       └─ Vision Navigator Loop
 ├─ OpenAI GPT-4o              └─ Staggered Batch Execution
 └─ Ollama / HF Free
          │                                │                                │
          └────────────────────────────────┼────────────────────────────────┘
                                           ▼
                            [ Storage & Vector Layer ]
                              ├─ SQLite (job_agent.db)
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
   git clone https://github.com/your-username/Automated-Job-Agent.git
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
   *(Edit `.env` to add your optional API keys for Gemini, Grok, OpenAI, or Hugging Face)*.

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

## 📡 API Reference & Scheduler Commands

The API provides endpoints for scheduler management, task queuing, and LLM router status:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/llm/status` | View router strategy, active providers, and real-time cost tracking |
| `GET` | `/api/schedule/status` | View scheduler status, queue stats, and active rate limits |
| `GET` | `/api/schedule/schedules` | List all active recurring schedules |
| `POST` | `/api/schedule/discovery` | Add recurring job discovery scan |
| `POST` | `/api/schedule/tasks/enqueue` | Manually enqueue a high-priority task |
| `POST` | `/api/schedule/stop` | Stop background scheduler engine |
| `POST` | `/api/schedule/start` | Restart background scheduler engine |

---

## 🔒 Security & Privacy Notice

- **Public Repository Safety**: Sensitive files (such as `.env`, `job_agent.db`, `qdrant_db/`, session cookies, and uploaded resumes) are excluded via `.gitignore`.
- **Session Encryption**: Browser session cookies stored in SQLite are encrypted using Fernet symmetric encryption (`cryptography` library).

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.