# Nguồn tham khảo kỹ thuật

Tài liệu này ghi lại cơ sở cho các quyết định AI và dữ liệu chính. Các ngưỡng như top 3 retrieval, chunk khoảng 200–400 token và timeout 5 giây là cấu hình khởi đầu cho MVP, chưa phải kết quả tối ưu hóa bằng benchmark riêng của ShopQuery AI.

## Gemini API và structured output

- Nguồn: [Gemini API documentation](https://ai.google.dev/gemini-api/docs) và [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).
- Áp dụng: Google GenAI SDK chính thức, model generation cấu hình qua environment, Pydantic schema cho SQL draft và route label.
- Lý do: structured output giảm phụ thuộc vào việc bóc JSON/SQL từ văn bản tự do. Schema chỉ bảo đảm hình dạng output; SQL vẫn phải qua validator và quyền database.
- Độ tin cậy: dùng `HttpRetryOptions` của SDK với timeout hữu hạn, tối đa 3 attempts và exponential backoff chỉ cho 408, 429 và lỗi 5xx có tính tạm thời, theo [Gemini API troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting).

## Gemini Embedding 2

- Nguồn: [Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings) và [Gemini Embedding 2 model](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2).
- Áp dụng: `gemini-embedding-2`, `output_dimensionality=768`; query dùng `task: question answering | query: ...`, document dùng `title: ... | text: ...`. Mỗi chunk được gửi thành một input độc lập.
- Lý do: tài liệu hiện hành nêu Embedding 2 tổng hợp nhiều phần input thành một vector, không tương đương batch nhiều chuỗi của model cũ. Model tự chuẩn hóa các chiều rút gọn được hỗ trợ.
- Giới hạn: retrieval semantic không chứng minh câu trả lời đúng; chất lượng thật cần live test và corpus thực tế.

## Retrieval-Augmented Generation

- Nguồn: Lewis và cộng sự, 2020, [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401).
- Áp dụng: truy hồi evidence trước, sau đó yêu cầu model chỉ tổng hợp từ evidence và trả chunk IDs đã sử dụng.
- Giới hạn: bài báo là nền tảng phương pháp, không chứng minh cấu hình top 3 là tối ưu cho corpus này.

## Chunking Markdown

- Nguồn: Xiao và cộng sự, 2025, [Is Semantic Chunking Worth the Computational Cost?](https://aclanthology.org/2025.findings-naacl.114/).
- Áp dụng: heading-aware chunking và tách theo paragraph khi section dài, thay vì semantic chunking bằng LLM.
- Lý do: giữ điều kiện chính sách và metadata, đồng thời tránh chi phí/độ phức tạp chưa cần thiết. Khoảng 200–400 token chỉ là cấu hình khởi đầu.

## pgvector và cosine distance

- Nguồn: [pgvector](https://github.com/pgvector/pgvector) và [pgvector-python](https://github.com/pgvector/pgvector-python).
- Áp dụng: cột `vector(768)`, toán tử cosine distance và exact nearest-neighbor search.
- Lý do: corpus nhỏ chưa cần HNSW/IVFFlat; exact search đơn giản và không có sai số approximate retrieval.

## SQLGlot và kiểm tra AST

- Nguồn: [SQLGlot documentation](https://sqlglot.com/sqlglot.html).
- Áp dụng: parse PostgreSQL thành AST, kiểm tra mọi node, allowlist bảng/cột/hàm và từ chối DML, DDL, nhiều statement, subquery/CTE ngoài phạm vi.
- Giới hạn: parse thành công không đồng nghĩa an toàn. Hệ thống còn dùng role read-only, read-only transaction, timeout và row limit; đây không thay thế security audit production.

## FastAPI, SQLAlchemy và Docker Compose

- Nguồn: [FastAPI](https://fastapi.tiangolo.com/), [SQLAlchemy](https://docs.sqlalchemy.org/) và [Docker Compose](https://docs.docker.com/compose/).
- Áp dụng: Pydantic API contracts, SQLAlchemy 2.x connections/transactions, healthcheck và dependency ordering trong Compose.
- Giới hạn: cấu hình hiện tại phục vụ MVP local; chưa bao gồm authentication, production secrets manager, reverse proxy hoặc cloud deployment.
