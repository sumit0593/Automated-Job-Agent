---
title: "ADR-003: PostgreSQL Primary Relational Storage with SQLite Fallback"
phase: "Architecture Decision Records"
version: "1.0.0"
status: "Approved"
author: "Automated Job Agent Architecture Team"
last_updated: "2026-07-29"
related:
  - "../Phase-14-Database/ER-Diagram.md"
  - "../Phase-14-Database/Tables-and-Schemas.md"
---

# 1. Overview
This ADR documents the decision to standardize on **PostgreSQL** as the primary enterprise relational storage database for multi-user production deployments, while retaining zero-configuration **SQLite** (`sqlite:///./job_agent.db`) fallback for local developer setups.

---

# 2. Why This Exists
Application tracking, candidate profile management, audit logging, and LangGraph checkpointing require strict ACID compliance, relational integrity, JSONB semi-structured query support, and concurrent write capability across background worker processes. Single-file SQLite databases lock under concurrent multi-process writes in production environments.

---

# 3. Responsibilities
- Define database connection abstractions using SQLAlchemy 2.0 ORM.
- Handle seamless fallback from PostgreSQL to local SQLite when `DATABASE_URL` specifies SQLite.

---

# 4. Inputs
- Environment variable `DATABASE_URL` ([config.py](file:///d:/Personal%20Imp/Projects/Automated-job-Agent/backend/app/config.py#L27)).
- Connection engine setup ([database.py](file:///d:/Personal%20Imp/Projects/Automated-job-Agent/backend/app/database.py#L11)).

---

# 5. Outputs
- Thread-safe, pooled database sessions (`SessionLocal`) bound to ORM models ([models.py](file:///d:/Personal%20Imp/Projects/Automated-job-Agent/backend/app/models.py)).

---

# 6. Components
- **PostgreSQL 16**: Primary production database engine.
- **SQLite 3**: Lightweight local development engine.
- **SQLAlchemy 2.0**: Unified ORM layer.
- **Alembic**: Database schema migration framework.

---

# 7. Folder Structure
```text
docs/
└── Architecture-Decision-Records/
    └── ADR-003-PostgreSQL-Persistence.md
```

---

# 8. Data Models
```python
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class JobPostingModel(Base):
    __tablename__ = "job_postings"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String)
    raw_payload = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

# 9. API Contracts
N/A (ADR).

---

# 10. Sequence Diagram
```mermaid
sequenceDiagram
    autonumber
    participant App as Backend Service
    participant Engine as SQLAlchemy Engine
    participant DB as PostgreSQL / SQLite

    App->>Engine: get_db() session request
    Engine->>DB: Checkout pool connection
    App->>DB: Execute query / commit transaction
    DB-->>App: Result set / success status
    Engine->>DB: Release connection to pool
```

---

# 11. Flow Diagram
```mermaid
flowchart TD
    Config[Check DATABASE_URL] -->|Starts with postgresql://| PG[PostgreSQL Driver - asyncpg/psycopg2]
    Config -->|Starts with sqlite:///| Lite[SQLite Driver - check_same_thread=False]
    PG --> Pool[SQLAlchemy Connection Pool]
    Lite --> Pool
    Pool --> ORM[ORM Models & Repositories]
```

---

# 12. Internal Working
The platform inspects `DATABASE_URL` at runtime. If running PostgreSQL, engine options configure pool size (`pool_size=20`, `max_overflow=10`). If running SQLite, `check_same_thread=False` is applied ([database.py](file:///d:/Personal%20Imp/Projects/Automated-job-Agent/backend/app/database.py#L9)).

---

# 13. Configuration
- `DATABASE_URL`: `postgresql://postgres:password@localhost:5432/job_agent`
- `DB_POOL_SIZE`: `20`
- `DB_MAX_OVERFLOW`: `10`

---

# 14. Error Handling
Database exceptions (`OperationalError`, `IntegrityError`) trigger transaction rollback and raise standard HTTP 400/500 backend responses.

---

# 15. Retry Strategy
- Database pool reconnections execute automatically with exponential backoff on transient network drops.

---

# 16. Security
- Database passwords are stored in `.env` and secret manager vaults. Connections in production require TLS (`sslmode=require`).

---

# 17. Logging
SQLAlchemy logs query execution parameters in `DEBUG` mode and slow queries (>500ms) in `WARNING` mode.

---

# 18. Metrics
- Connection Pool Utilization.
- DB Query Latency (P95 < 15ms).

---

# 19. Testing Strategy
- Run pytest suite against both PostgreSQL container and in-memory SQLite fixtures to guarantee multi-database compatibility.

---

# 20. Performance Considerations
- Indexes are added to foreign keys (`job_id`, `candidate_id`) and status fields (`status`, `created_at`).

---

# 21. Best Practices
- Never execute raw SQL string concatenations; use SQLAlchemy ORM or parameterized queries to prevent SQL injection.

---

# 22. Production Improvements
- Implement PgBouncer connection proxy in Kubernetes deployments for high-throughput concurrency scaling.

---

# 23. Common Failure Scenarios
- **Scenario**: SQLite `database is locked` error in multi-threaded test runner.
  - **Resolution**: Switch test environment setting to PostgreSQL container or WAL mode SQLite.

---

# 24. Future Enhancements
- Implement database read-replicas for heavy analytic job reporting workloads.

---

# 25. References
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [PostgreSQL 16 Documentation](https://www.postgresql.org/docs/16/index.html)
