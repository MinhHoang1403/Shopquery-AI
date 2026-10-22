# Kiến trúc hiện hành

Modular monolith: React → web proxy → FastAPI → PostgreSQL 17/pgvector.
Knowledge/Gemini generation adapters, Gemini Embedding 768 dimensions, authentication,
persistence và frontend layout được giữ nguyên.

```text
Question + authorized workspace → structured QueryRouter
  SQL: schema context → SqlDraft → SQLGlot/JOIN/COUNT guards → reader → answer
  RAG: embedding → scoped pgvector → optional local BGE → cited answer
  HYBRID: retrieval/rerank → policy requirements → SQL → verified decisions → answer
  UNSUPPORTED: clarification/insufficient evidence using the existing API contract
```

SQL production vẫn dùng `SqlGenerator`. **QueryPlan compiler chưa nối vào factories**:
còn thiếu biểu diễn công thức/nhóm ngày đã được hỗ trợ. Không có runtime switch
giữa hai engines. Gate thay thế cụ thể nằm trong báo cáo Giai đoạn 1.

| Module | Trách nhiệm |
| --- | --- |
| `api`, `auth`, `conversations` | HTTP contracts, sessions/CSRF, owner-bound persistence |
| `datasets/context.py` | Schema registry, headers/types, categories, approved relations |
| `text_to_sql/generator.py` | Structured draft theo schema và retrieved evidence |
| `query_plan.py`, `compiler.py` | Backend-issued IDs, SQLAlchemy subset compiler; chưa production |
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

QueryPlan candidate resolve backend table/column/relation IDs, fields/metrics,
AND filters, grouping, sorting, limit; bind values và kiểm cả preview/bound AST qua
validator hiện hữu. Chưa có LLM plan generation/schema pruning trong production.
