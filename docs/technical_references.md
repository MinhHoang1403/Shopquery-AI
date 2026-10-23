# Nguồn kỹ thuật hiện hành

Các nguồn dưới đây giải thích library semantics; không chứng nhận application accuracy.
K/N/batch/length là giới hạn khởi đầu, chưa phải benchmark tối ưu.

- [BAAI model card](https://huggingface.co/BAAI/bge-reranker-v2-m3): multilingual cross-encoder, Apache-2.0; dùng đúng pinned snapshot.
- [CrossEncoder API](https://sbert.net/docs/package_reference/cross_encoder/model.html): local path, local_files_only, revision, device, max_length và bounded predict batch.
- [SQLAlchemy Core](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html) và [bound parameters](https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.bindparam): typed expressions và parameterized values, identifiers từ registry.
- [SQLGlot AST](https://sqlglot.com/sqlglot.html): PostgreSQL parse/inspection, không phải authorization tự động.
- [PostgreSQL aggregates](https://www.postgresql.org/docs/17/functions-aggregate.html): COUNT rows vs values, SUM/AVG NULL; [transactions](https://www.postgresql.org/docs/17/sql-set-transaction.html): read-only transaction.
- [Python Decimal](https://docs.python.org/3.11/library/decimal.html): exact numeric decisions, không qua float.
- [pgvector](https://github.com/pgvector/pgvector): cosine distance và exact vector retrieval; scope dùng SQL predicates.
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/): typed contracts; schema validation không chứng minh business semantics.
- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output): structured response handling; bằng chứng live của compact generation contract nằm trong [nghiệm thu V2](v2_final_acceptance.md).
- [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect): issuer/audience/nonce/PKCE và callback handling.
- [Compose merge](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/): explicit file order/override; [volumes](https://docs.docker.com/reference/compose-file/volumes/): external protected persistence.
- [Uvicorn reload](https://www.uvicorn.org/settings/#development) và [Vite server](https://vite.dev/config/server-options): development reload/HMR, không coi là production deployment.
- [RAG paper](https://arxiv.org/abs/2005.11401): retrieval-grounded generation; không chứng minh candidate answers luôn đúng.

Capabilities/security hiện hành được ghi riêng ở canonical docs. Các báo cáo cũ
có trong Git tại `87cdf40`; không dùng test count lịch sử để mô tả source hiện tại.
