---
title: "Session Management & Lifecycle Orchestration"
phase: "Phase-02-Authentication"
version: "1.0.0"
status: "Approved"
author: "Automated Job Agent Architecture Team"
last_updated: "2026-07-29"
related:
  - "OAuth.md"
  - "Cookie-Authentication.md"
  - "Token-Encryption.md"
---

# 1. Overview
This document specifies the **Session Management Subsystem**, covering candidate JWT user session tokens, stateful session tracking, session revocation, and multi-tenant user session isolation ([session_manager.py](file:///d:/Personal%20Imp/Projects/Automated-job-Agent/backend/app/services/session_manager.py)).

---

# 2. Why This Exists
Managing candidate interactions across REST APIs, WebSockets, background Playwright workers, and external job portals requires an overarching session manager. The session subsystem ensures secure user authentication, prevents cross-tenant data leakage, and manages session expiration timeouts.

---

# 3. Responsibilities
- Issue and validate JWT authentication tokens for frontend dashboard users.
- Manage session state stored in Redis.
- Enforce strict candidate user context isolation across multi-agent background workflows.

---

# 4. Inputs
- Candidate authentication credentials, HTTP Bearer tokens, WebSocket headers.

---

# 5. Outputs
- Verified `UserSession` objects, refreshed JWT tokens, session termination events.

---

# 6. Components
- **SessionManager**: Central service managing candidate session lifecycles ([session_manager.py](file:///d:/Personal%20Imp/Projects/Automated-job-Agent/backend/app/services/session_manager.py)).
- **RedisSessionStore**: High-performance session state cache storing active session metadata.
- **JWTTokenHandler**: Signs and decodes HS256 / RS256 JWT tokens.

---

# 7. Folder Structure
```text
docs/Phase-02-Authentication/
└── Session-Management.md
```

---

# 8. Data Models
```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class UserSession(BaseModel):
    session_id: str
    user_id: str
    email: str
    roles: List[str] = Field(default_factory=lambda: ["candidate"])
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True
```

---

# 9. API Contracts
Session Validation Middleware Contract:
```json
{
  "request_header": "Authorization: Bearer eyJhbGciOiJIUzI1Ni...",
  "decoded_session": {
    "session_id": "sess_98412",
    "user_id": "usr_98412",
    "email": "candidate@example.com",
    "status": "Valid"
  }
}
```

---

# 10. Sequence Diagram
```mermaid
sequenceDiagram
    autonumber
    actor Candidate as Candidate Frontend
    participant Middleware as FastAPI Auth Middleware
    participant Manager as SessionManager
    participant Redis as Redis Session Cache

    Candidate->>Middleware: Request API Endpoint + Bearer JWT
    Middleware->>Manager: validate_session(jwt_token)
    Manager->>Redis: GET session:sess_98412
    Redis-->>Manager: Return active UserSession JSON
    Manager-->>Middleware: Session Validated
    Middleware-->>Candidate: Proceed to Route Handler
```

---

# 11. Flow Diagram
```mermaid
flowchart TD
    Req[Incoming HTTP / WS Request] --> Extract[Extract Bearer JWT Token]
    Extract --> VerifyJWT{Verify JWT Signature & Exp}
    VerifyJWT -->|Invalid / Expired| Deny[Return HTTP 401 Unauthorized]
    VerifyJWT -->|Valid| RedisCheck{Active in Redis Cache?}
    RedisCheck -->|Revoked / Missing| Deny
    RedisCheck -->|Active| Grant[Grant Request Context]
```

---

# 12. Internal Working
JWT tokens contain short lifespans (15 minutes access token, 7 days refresh token). Active session IDs are cached in Redis under key pattern `session:<session_id>` with matching TTL expirations.

---

# 13. Configuration
- Specified in [backend/app/config.py](file:///d:/Personal%20Imp/Projects/Automated-job-Agent/backend/app/config.py).
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: `15`
- `JWT_REFRESH_TOKEN_EXPIRE_DAYS`: `7`
- `JWT_ALGORITHM`: `HS256`

---

# 14. Error Handling
Invalid, tampered, or expired tokens raise `HTTPException(status_code=401, detail="Could not validate credentials")`.

---

# 15. Retry Strategy
- Frontend HTTP clients automatically invoke `/api/v1/auth/refresh` upon receiving HTTP 401 responses.

---

# 16. Security
- Tokens are signed with a high-entropy secret (`SECRET_KEY`).
- Refresh tokens are bound to candidate fingerprint hashes to prevent token hijacking.

---

# 17. Logging
- Session events log `session_id`, `user_id`, `action` (login, refresh, logout, revoke), and `client_ip`.

---

# 18. Metrics
- Active User Sessions Count.
- Session Validation Latency (<2ms via Redis).

---

# 19. Testing Strategy
- Unit test JWT decoding, expiration enforcement, and session revocation logic.

---

# 20. Performance Considerations
- Caching session states in Redis avoids database lookup queries on every API request.

---

# 21. Best Practices
- Always check session revocation status in Redis for critical financial or profile modification routes.

---

# 22. Production Improvements
- Upgrade JWT signing algorithm from HS256 to RS256 asymmetric keypairs for microservice validation.

---

# 23. Common Failure Scenarios
- **Scenario**: Candidate logs out from device.
  - **Resolution**: `SessionManager` deletes session key from Redis, instantly revoking access across all background workers.

---

# 24. Future Enhancements
- Add multi-device concurrent session management dashboard.

---

# 25. References
- RFC 7519: JSON Web Token (JWT) Specification.
