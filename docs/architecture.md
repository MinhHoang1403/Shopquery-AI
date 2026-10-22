# Kiến trúc hiện hành

Modular monolith: React → web proxy → FastAPI → PostgreSQL 17/pgvector.
Knowledge/Gemini generation adapters, Gemini Embedding 768 dimensions, authentication,
persistence và frontend layout được giữ nguyên.

```text
Question + authorized workspace → structured QueryRouter
  SQL: authorized catalog → PlanDecision → QueryCompiler → SQLGlot/JOIN/COUNT guards
       → reader with bound parameters → answer
  RAG: embedding → scoped pgvector → optional local BGE → cited answer
  HYBRID: retrieval/rerank → policy requirements → SQL → verified decisions → answer
  UNSUPPORTED: clarification/insufficient evidence using the existing API contract
```

Default, authenticated, Guest và Hybrid SQL dùng cùng QueryPlanner/QueryCompiler.
Generator SQL tự do đã được gỡ; không có fallback sang SQL do model sinh.

| Module | Trách nhiệm |
| --- | --- |
| `api`, `auth`, `conversations` | HTTP contracts, sessions/CSRF, owner-bound persistence |
| `datasets/context.py` | Schema registry, headers/types, categories, approved relations |
| `text_to_sql/planner.py` | PlanDecision từ authorized catalog IDs và retrieved evidence |
| `query_plan.py`, `expressions.py`, `compiler.py` | Bounded typed DAG, type/grain checks và SQLAlchemy compilation |
| `validator.py`, `join_policy.py`, `count_contract.py` | AST authorization, exact keys, grain, COUNT provenance |
| `executor.py` | Read-only transaction, timeout, row cap, lossless values |
| `rag/repository.py`, `reranker.py` | Owner/workspace retrieval, original sources, offline ranking |
| `routing/hybrid*.py`, `natural_policy.py` | Binding, complete evidence, exact Decimal, authoritative decisions |
| `ai` | Adapters, structured response/error handling, existing retry/fallback policy |
| `guest` | TTL/quota, RAM chunks, disposable workers, PostgreSQL TEMP |
| `dependencies.py` | Request object graph; không DDL lúc chat |

Hybrid lấy candidate policy trước SQL; rule chỉ verified sau SQL/registry/source
hash binding. Document/cell text là untrusted data. Bỏ lượt SQL answer generation
trung gian; composer cuối dùng một decision set cho summary/detail và citations.

Public API giữ `answer`, `route`, `sql`, `rows`, `sources`, error và model attribution.
NUMERIC là decimal strings; NULL khác zero; COUNT provenance từ AST, không từ alias.
Router chưa có CLARIFY riêng; dùng phản hồi `UNSUPPORTED` hiện hữu.

QueryPlan giới hạn 80 expression nodes, depth8, 30 selected fields. Không pruning
mất columns/relationships: catalog chỉ gồm workspace đã được authorize. Arithmetic,
AND/OR, SUM HAVING, date grouping/formatting và typed ranges compile thành bound SQL.
Literal evidence SQL được render an toàn và validate riêng cho Hybrid/public response;
executor chỉ chạy statement có bind parameters. Hai AST phải giữ cùng provenance.
