############################################################
# SCENARIO 1: Pure DB query — only db_analyst needed
# The coordinator should NOT invoke code_reviewer or api_designer
############################################################

============================================================
COORDINATOR AGENT
============================================================
User: This query is slow: SELECT * FROM users WHERE age > 25 ORDER BY name. The users table has 2M rows. How can I optimize it?

  [Coordinator iteration 1 | stop_reason: tool_use]

  Coordinator delegating to [db_analyst]:
  Task: Analyze and optimize the following slow SQL query on a table with 2 million rows:

SELECT * FROM use...

    --- Subagent [db_analyst] started ---
    [db_analyst] iteration 1 | stop_reason: tool_use
    [db_analyst] tool: explain_query({"query": "SELECT * FROM users WHERE age > 25 ORDER BY name"}...)
    [db_analyst] tool: suggest_indexes({"table": "users", "query_patterns": ["WHERE age > 25", "ORDER BY name", "WHERE ...)
    [db_analyst] iteration 2 | stop_reason: end_turn
    --- Subagent [db_analyst] finished (2 iterations) ---

  [Coordinator iteration 2 | stop_reason: end_turn]
  Coordinator thinking: ## Query Optimization Report: `SELECT * FROM users WHERE age > 25 ORDER BY name`

The root cause is a **full table scan ...

============================================================
FINAL ANSWER:
============================================================
## Query Optimization Report: `SELECT * FROM users WHERE age > 25 ORDER BY name`

The root cause is a **full table scan + in-memory sort** on 2M rows — an expensive combo. Here's everything you need to fix it:

---

### 🔎 What's Going Wrong

| Step | Problem |
|---|---|
| `WHERE age > 25` | No index → reads all 2M rows before filtering |
| `ORDER BY name` | No pre-sorted data → expensive in-memory/disk sort |
| `SELECT *` | Fetches all columns, prevents index-only scans |

---

### ✅ Fix 1 — Add a Composite Index ⭐ *Biggest Impact*

```sql
CREATE INDEX idx_users_age_name ON users (age, name);
```

- Handles **both** the filter and the sort in a single index scan
- `age` comes first because range predicates (`age > 25`) must lead in composite indexes
- Eliminates the separate sort step entirely

---

### ✅ Fix 2 — Rewrite the Query

```sql
-- ❌ Before
SELECT * FROM users WHERE age > 25 ORDER BY name;

-- ✅ After
SELECT id, name, age, email
FROM users
WHERE age > 25
ORDER BY name
LIMIT 100;
```

- **Avoid `SELECT *`**: fetches unnecessary columns (including large TEXT/BLOB fields) and blocks index-only scans
- **Add `LIMIT`**: with 2M rows, this query could return millions of records — always paginate

---

### ✅ Fix 3 — Refresh Query Planner Statistics

```sql
ANALYZE users;          -- PostgreSQL / standard SQL
-- or
VACUUM ANALYZE users;   -- PostgreSQL (also reclaims dead tuples)
```

This ensures the query planner has accurate row estimates and picks the optimal execution plan.

---

### 💡 Bonus: Consider a Partial Index

If your app *always* queries above a fixed threshold (e.g., always `age > 18`), a partial index is smaller and faster:

```sql
CREATE INDEX idx_users_adults ON users (name) WHERE age > 18;
```

---

### 📋 Full Action Plan (in order)

```sql
-- 1. Add the composite index
CREATE INDEX idx_users_age_name ON users (age, name);

-- 2. Rewrite the query
SELECT id, name, age, email
FROM users
WHERE age > 25
ORDER BY name
LIMIT 100;

-- 3. Update statistics
ANALYZE users;
```

**Expected result:** Query cost drops from ~1245 → <50, switching from a full sequential scan to a fast index range scan with pre-sorted results. 🚀

############################################################
# SCENARIO 2: Code + API — needs code_reviewer AND api_designer
# The coordinator should NOT invoke db_analyst (no DB aspect)
############################################################

============================================================
COORDINATOR AGENT
============================================================
User: I'm building a user registration endpoint. Here's my handler code:
def register(request):
    query = f"INSERT INTO users VALUES ('{request.name}', '{request.email}')"
    db.execute(query)
    return {'status': 'ok'}

Review this code for security issues and also generate a proper OpenAPI spec for a POST /users endpoint.

  [Coordinator iteration 1 | stop_reason: tool_use]

  Coordinator delegating to [code_reviewer]:
  Task: Review the following Python web handler for security vulnerabilities and best practices. Focus on in...

    --- Subagent [code_reviewer] started ---
    [code_reviewer] iteration 1 | stop_reason: tool_use
    [code_reviewer] tool: check_security_patterns({"code": "def register(request):\n    query = f\"INSERT INTO users VALUES ('{req...)
    [code_reviewer] tool: analyze_complexity({"code": "def register(request):\n    query = f\"INSERT INTO users VALUES ('{req...)
    [code_reviewer] iteration 2 | stop_reason: end_turn
    --- Subagent [code_reviewer] finished (2 iterations) ---

  Coordinator delegating to [api_designer]:
  Task: Generate a complete OpenAPI 3.0 specification for a POST /users endpoint for user registration. The ...

    --- Subagent [api_designer] started ---
    [api_designer] iteration 1 | stop_reason: tool_use
    [api_designer] tool: validate_openapi_spec({"spec": "\nopenapi: 3.0.0\ninfo:\n  title: User Registration API\n  version: 1....)
    [api_designer] tool: generate_endpoint_stub({"method": "POST", "path": "/users", "description": "Register a new user by acce...)
    [api_designer] iteration 2 | stop_reason: end_turn
    --- Subagent [api_designer] finished (2 iterations) ---

  [Coordinator iteration 2 | stop_reason: end_turn]
  Coordinator thinking: Here's a complete technical breakdown covering both the security review and the API spec:

---

## 🚨 Code Security Revie...

============================================================
FINAL ANSWER:
============================================================
Here's a complete technical breakdown covering both the security review and the API spec:

---

## 🚨 Code Security Review

Your current code has **critical and moderate issues** that must be addressed before going to production.

### Critical: SQL Injection
The f-string interpolation is the most dangerous problem. A malicious user submitting:
```
name = "'; DROP TABLE users; --"
```
...would produce destructive SQL. **Always use parameterized queries:**
```python
# ❌ Vulnerable
query = f"INSERT INTO users VALUES ('{request.name}', '{request.email}')"

# ✅ Safe
query = "INSERT INTO users (name, email) VALUES (%s, %s)"
db.execute(query, (request.name, request.email))
```

### Additional Issues

| Issue | Severity | Fix |
|---|---|---|
| No input validation | 🔴 High | Validate/sanitize `name` and `email` before use |
| No error handling | 🔴 High | Wrap in `try/except`, return proper HTTP errors |
| Implicit column names in `INSERT` | 🟡 Medium | Always specify column names explicitly |
| No duplicate email handling | 🟡 Medium | Catch unique constraint violations → return `409` |
| Opaque success response | 🟢 Low | Return `201 Created` with the created user object |

### ✅ Recommended Rewrite
```python
import re

def register(request):
    name = getattr(request, 'name', '').strip()
    email = getattr(request, 'email', '').strip()

    if not name or not email:
        return {'status': 'error', 'message': 'Name and email are required'}, 400

    if not re.match(r'^[\w\s\-]{1,100}$', name):
        return {'status': 'error', 'message': 'Invalid name format'}, 400

    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return {'status': 'error', 'message': 'Invalid email format'}, 400

    query = "INSERT INTO users (name, email) VALUES (%s, %s)"
    try:
        db.execute(query, (name, email))
        return {'status': 'created'}, 201
    except DuplicateEntryError:
        return {'status': 'error', 'message': 'Email already registered'}, 409
    except DatabaseError as e:
        logger.error("DB error during registration: %s", e)
        return {'status': 'error', 'message': 'Internal server error'}, 500
```

---

## 📄 OpenAPI 3.0 Specification — `POST /users`

```yaml
openapi: 3.0.0
info:
  title: User Registration API
  version: 1.0.0

paths:
  /users:
    post:
      summary: Register a new user
      operationId: registerUser
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name, email]
              properties:
                name:
                  type: string
                  minLength: 1
                  maxLength: 100
                  example: Jane Doe
                email:
                  type: string
                  format: email
                  example: jane.doe@example.com
      responses:
        '201':
          description: User successfully created
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                    format: uuid
                    example: 123e4567-e89b-12d3-a456-426614174000
                  name:
                    type: string
                  email:
                    type: string
                    format: email
                  createdAt:
                    type: string
                    format: date-time
        '400':
          description: Validation error
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
                  message:
                    type: string
                  details:
                    type: array
                    items:
                      type: object
                      properties:
                        field:
                          type: string
                        issue:
                          type: string
        '409':
          description: Email already registered
        '500':
          description: Internal server error
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| **`201 Created`** | Semantically correct for resource creation |
| **UUID for `id`** | Prevents user enumeration attacks vs. sequential integers |
| **`409 Conflict`** | Correct status for duplicate email, not a generic `400` |
| **`400` with `details` array** | Allows surfacing multiple field errors in one response |
| **`format: email` on schema** | Enables tooling and client-side validation automatically |
| **`minLength: 1` on `name`** | Prevents empty-string bypass of the `required` constraint |

---

## 🔑 Top Priorities

1. **Fix the SQL injection immediately** — this is a critical vulnerability
2. **Add input validation** before any DB interaction
3. **Handle all error paths explicitly** (missing fields, duplicates, DB failures)
4. **Return `201` with a user object** (including a UUID `id`) instead of a bare `{'status': 'ok'}`

############################################################
# SCENARIO 3: Full stack review — all subagents relevant
############################################################

============================================================
COORDINATOR AGENT
============================================================
User: We're launching a new /search endpoint. Review this handler:
def search(q):
    return db.execute(f"SELECT * FROM products WHERE name LIKE '%{q}%'")

Also optimize the underlying SQL query (products table has 500K rows) and generate an OpenAPI spec for GET /search?q=term.

  [Coordinator iteration 1 | stop_reason: tool_use]
  Coordinator thinking: Great — this touches all three domains: code quality/security, database performance, and API design. I'll dispatch all t...

  Coordinator delegating to [code_reviewer]:
  Task: Review this Python database handler function for security vulnerabilities, complexity issues, and be...

    --- Subagent [code_reviewer] started ---
    [code_reviewer] iteration 1 | stop_reason: tool_use
    [code_reviewer] tool: check_security_patterns({"code": "def search(q):\n    return db.execute(f\"SELECT * FROM products WHERE ...)
    [code_reviewer] tool: analyze_complexity({"code": "def search(q):\n    return db.execute(f\"SELECT * FROM products WHERE ...)
    [code_reviewer] iteration 2 | stop_reason: end_turn
    --- Subagent [code_reviewer] finished (2 iterations) ---

  Coordinator delegating to [db_analyst]:
  Task: Analyze and optimize this SQL query running against a products table with 500,000 rows:

SELECT * FR...

    --- Subagent [db_analyst] started ---
    [db_analyst] iteration 1 | stop_reason: tool_use
    [db_analyst] tool: explain_query({"query": "SELECT * FROM products WHERE name LIKE '%{q}%'"}...)
    [db_analyst] tool: suggest_indexes({"table": "products", "query_patterns": ["SELECT * FROM products WHERE name LIKE...)
    [db_analyst] iteration 2 | stop_reason: end_turn
    --- Subagent [db_analyst] finished (2 iterations) ---

  Coordinator delegating to [api_designer]:
  Task: Generate an OpenAPI 3.0 specification for the following endpoint:

- Method: GET
- Path: /search
- Q...

    --- Subagent [api_designer] started ---
    [api_designer] iteration 1 | stop_reason: tool_use
    [api_designer] tool: validate_openapi_spec({"spec": "\nopenapi: 3.0.0\ninfo:\n  title: Product Search API\n  version: 1.0.0...)
    [api_designer] tool: generate_endpoint_stub({"method": "GET", "path": "/search", "description": "Search products by name usi...)
    [api_designer] iteration 2 | stop_reason: end_turn
    --- Subagent [api_designer] finished (2 iterations) ---

  [Coordinator iteration 2 | stop_reason: end_turn]
  Coordinator thinking: Here's the complete, synthesized picture across all three dimensions:

---

# 🔍 `/search` Endpoint — Full Technical Revi...

============================================================
FINAL ANSWER:
============================================================
Here's the complete, synthesized picture across all three dimensions:

---

# 🔍 `/search` Endpoint — Full Technical Review

---

## 🔴 1. Code Review — Critical Issues Found

Your handler has a **critical SQL injection vulnerability** and several other issues:

| Issue | Severity |
|---|---|
| SQL Injection via f-string interpolation | 🔴 Critical |
| No input validation (length, type, empty) | 🔴 High |
| No error handling — exceptions bubble up | 🟡 Medium |
| `db` is an implicit global — untestable | 🟡 Medium |
| `SELECT *` — fragile and inefficient | 🟢 Low |

**Here's the corrected handler:**
```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)
MAX_QUERY_LENGTH = 100

def search(db, q: str) -> Optional[list]:
    if not isinstance(q, str) or not q.strip():
        raise ValueError("Search query must be a non-empty string.")
    if len(q) > MAX_QUERY_LENGTH:
        raise ValueError(f"Search query exceeds maximum length of {MAX_QUERY_LENGTH}.")

    # ✅ Parameterized query — user input NEVER touches the SQL string
    sql = "SELECT id, name, price FROM products WHERE name LIKE ?"
    param = (f"%{q.strip()}%",)

    try:
        results = db.execute(sql, param)
        return results.fetchall()
    except Exception as e:
        logger.error("Database error during product search: %s", e)
        return None
```

---

## ⚡ 2. Database Optimization — Big Performance Problem

The leading wildcard (`'%term%'`) causes a **full sequential scan** across all 500K rows (~800ms–2s+ per query). B-Tree indexes are useless here.

**Performance comparison:**

| Approach | Scan Type | Est. Query Time | Scales? |
|---|---|---|---|
| `LIKE '%q%'` — current | Full sequential | ~800ms–2s+ | ❌ |
| B-Tree + prefix `LIKE 'q%'` | Index seek | ~2–10ms | ⚠️ Prefix only |
| **Trigram GIN index** | Index scan | ~5–20ms | ✅ |
| Full-text `MATCH/@@` | Index scan | ~1–5ms | ✅ |
| Elasticsearch | Inverted index | ~1–3ms | ✅ |

**Recommended fixes by priority:**

**🚑 Immediate (no schema change):**
```sql
-- Always paginate + select only needed columns
SELECT id, name, price, description
FROM products
WHERE name LIKE '%q%'
LIMIT 20 OFFSET 0;
```

**🏆 Short-term (best fix — PostgreSQL):**
```sql
-- Enable trigram indexing — preserves exact LIKE '%q%' semantics
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_products_name_trgm ON products USING GIN(name gin_trgm_ops);
-- Your query now uses the index with zero rewrites needed!
```

**For MySQL**, switch to a FULLTEXT index:
```sql
ALTER TABLE products ADD FULLTEXT INDEX ft_products_name (name);
SELECT *, MATCH(name) AGAINST('q' IN BOOLEAN MODE) AS relevance
FROM products WHERE MATCH(name) AGAINST('q' IN BOOLEAN MODE);
```

**🔭 Long-term:** Migrate search to Elasticsearch/Typesense/Meilisearch when catalog exceeds 1M rows or you need fuzzy matching/faceting.

---

## 📄 3. OpenAPI 3.0 Specification

```yaml
openapi: 3.0.0
info:
  title: Product Search API
  version: 1.0.0

paths:
  /search:
    get:
      summary: Search products by name
      operationId: searchProducts
      parameters:
        - name: q
          in: query
          required: true
          description: Search term to filter products by name
          schema:
            type: string
            minLength: 1
      responses:
        '200':
          description: Matching products returned successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items:
                      $ref: '#/components/schemas/Product'
                  count:
                    type: integer
        '400':
          description: Missing or invalid query parameter
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '500':
          description: Internal server error
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

components:
  schemas:
    Product:
      type: object
      required: [id, name, price]
      properties:
        id:
          type: integer
          example: 42
        name:
          type: string
          example: "Wireless Headphones"
        price:
          type: number
          format: float
          example: 49.99
        description:
          type: string
          example: "Over-ear noise-cancelling headphones."
    ErrorResponse:
      type: object
      required: [error, message, status]
      properties:
        error:
          type: string
        message:
          type: string
        status:
          type: integer
```

---

## ✅ Prioritized Action Plan

| Priority | Action |
|---|---|
| 🔴 **Do now** | Switch to parameterized queries — eliminate SQL injection |
| 🔴 **Do now** | Add input validation (non-empty, max length) |
| 🟡 **This sprint** | Add `LIMIT`/pagination to cap result size |
| 🟡 **This sprint** | Replace `SELECT *` with explicit columns |
| 🟢 **Short-term** | Add trigram GIN index (PostgreSQL) or FULLTEXT index (MySQL) |
| 🟢 **Short-term** | Add error handling and logging to the handler |
| 🔵 **Long-term** | Evaluate a dedicated search engine (Elasticsearch, Typesense) |
