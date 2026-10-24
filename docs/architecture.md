# Kiến trúc hiện hành

Modular monolith: React → web proxy → FastAPI → PostgreSQL 17/pgvector.
Knowledge/Gemini generation adapters, Gemini Embedding 768 dimensions, authentication,
persistence và frontend layout được giữ nguyên.

```text
Question + authorized workspace → explicit source choice / structured QueryRouter
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

## Reliability boundaries

`ChatRequest.route_hint` (SQL/RAG/HYBRID) là lựa chọn nguồn rõ ràng của người dùng,
không phải kết luận suy ra từ từ khóa. UI có “Nguồn trả lời”; mặc định tự chọn vẫn
dùng semantic router. Backend luôn kiểm lựa chọn với capabilities của workspace;
không hạ Hybrid thành SQL khi thiếu documents. Prefix /sql, /rag, /hybrid là lựa
chọn tương đương. Không suy route từ tiền đề hội thoại hoặc tên bảng không tin cậy.
Lựa chọn này bỏ một generation stage; không bỏ planner/grounding/security guards.

SQL rows sau compiler/reader được presenter trung tính dựng thành bảng, giữ exact
digits, NULL/zero và COUNT provenance, không đoán đơn vị từ column name. Không gọi
LLM để diễn đạt lại rows. Hybrid giữ evidence-first và verified_classification /
compose_answer hiện có: chỉ một rule đủ source-bound evidence mới có verdict Decimal
deterministic; rule phức tạp/thiếu citation/scope không được tự kết luận.

Provider errors có ErrorContext dùng chung: provider/operation/phase/status/category,
attempt nếu biết, origin_stage, attempted_route và correlation_id. API vẫn persist
turn lỗi theo HTTP200 contract; route thành công không bị dùng thay attempted_route.
Validation paths được allowlist và giới hạn, không lưu input/msg/provider body.
Gemini tách schema preparation, SDK request, JSON decode, wire validation và domain
conversion. SDK ValueError tại request phase không tự chứng minh HTTP đã được gửi.
GenerationDecision wire validator không dựng QueryPlan; conversion chạy một lần riêng.
Knowledge giữ status từ APIStatusError, phân biệt refusal/parsing/validation.

Retry vẫn do SDK quản lý, không thêm tầng retry. Default attempts1/fallback OFF.
HTTP429 giữ category quota_or_rate_limit khi chưa có bằng chứng phân biệt; không
suy đoán hết tiền. SDK behavior được kiểm bằng mock HTTP serializers, không paid calls.

Nguồn interface: [Google GenAI retry implementation](https://github.com/googleapis/python-genai/blob/main/google/genai/_api_client.py),
[LangChain include_raw contract](https://reference.langchain.com/python/langchain-openai/chat_models/base/BaseChatOpenAI/with_structured_output).
Pinned dependencies trong uv.lock và HTTP-mock tests là bằng chứng cho SDK đang dùng.

QueryPlan giới hạn 80 expression nodes, depth8, 512 expanded nodes/expression và
30 selected fields. Bound expansion chặn DAG reuse làm SQL tăng theo cấp số nhân. Không pruning
mất columns/relationships: catalog chỉ gồm workspace đã được authorize. Arithmetic,
AND/OR, SUM HAVING, date grouping/formatting và typed ranges compile thành bound SQL.
Literal evidence SQL được render an toàn và validate riêng cho Hybrid/public response;
executor chỉ chạy statement có bind parameters. Hai AST phải giữ cùng provenance.
