# Khả năng và giới hạn

## SQL

Production hỗ trợ authorized SELECT, filters, arithmetic, aggregates, GROUP BY,
sorting/top-N, thời gian và NULL/zero/Decimal. Uploaded workspace mặc định một
bảng; JOIN opt-in giữ tên `SQL_JOIN_V1_ENABLED`.

JOIN hai/ba bảng cần một/hai approved relations và revision/key proof hợp lệ.
Backend kiểm exact ON, fact → dimension, uniqueness/no fanout, GROUP BY entity key.
Chain/star ba bảng chỉ aggregate fact gốc. Shared-dimension two-fact, many-to-many,
composite/outer/self joins, chu trình và đường mơ hồ bị từ chối.

COUNT(*) đếm matched fact rows; COUNT(nullable column) đếm non-NULL values; verified
INNER fact key có thể row-equivalent. SUM/AVG NULL không đổi thành zero. Calendar
executor là `Asia/Ho_Chi_Minh`; boundaries giữ offset và khoảng `>= start AND < end`.
Không writes, CTE/subquery/window/locks hoặc hàm ngoài allowlist.

Typed compiler candidate hỗ trợ một bảng, approved JOIN hai/ba bảng, SUM/AVG/MIN/MAX/
COUNT, comparisons/IN/NULL, grouping/sort/limit và date/timestamp filter values.
Chưa biểu diễn derived arithmetic, date grouping/formatting, OR/HAVING hoặc full
default-store formulas. Không thay production để tránh mất capability.

## RAG và Hybrid

CSV/XLSX tạo bảng; PDF text-layer, DOCX, TXT/MD tạo tài liệu. Không OCR, DOC cũ,
macro, URL ingestion hoặc vector database mới. Original binaries không lưu để tải
lại. Giai đoạn 1 không re-embed corpus main hoặc đổi embedding dimensions.

Authenticated/default RAG có local `BAAI/bge-reranker-v2-m3` theo cấu hình. Default
K=12/N=3; chỉ xếp original chunks. Chưa benchmark Recall/MRR/nDCG/latency hoặc chứng
minh tăng accuracy. Missing/error model dùng vector fallback với sanitized log;
load thử một lần mỗi process/config, cần restart sau khi sửa artifact/device.
Guest giữ vector retrieval vì worker 768 MiB không chứa được weights BGE 2,27 GB;
không nới resource isolation.

Hybrid retrieval trước SQL. Verified scope gồm một numeric rule SUM/AVG/row count/
non-NULL count, exact threshold/operator/source units/entity key, all rows và whole
single-chunk document. Closed bilingual prose grammar không phải general rules
engine. Multiple/conflicting rules, unverified exceptions, thiếu metric hoặc mơ hồ
identity/unit phải refusal/insufficient. Summary/detail dùng cùng decision set.

## Tài khoản và Guest

Google OIDC invite-only, PostgreSQL sessions, CSRF, owner isolation và management/
history/model selection giữ nguyên. Xóa nguồn cần UI confirmation; xóa dataset có
history cần explicit delete flag; không tự chuyển conversation sang corpus khác.

Guest namespace riêng, uploads/chunks/history RAM theo TTL/quota; SQL TEMP có thể
dùng disk nội bộ PostgreSQL. Không hứa forensic zero-copy. Refresh không khôi phục
Guest chat. Một API worker; không thay authentication để phục vụ refactor.

Knowledge model `knowledge`; Gemini generation theo cấu hình hiện hữu, embedding
`gemini-embedding-2`/768. Không đổi model/key/fallback ngầm. Schema mock PASS không
tương đương provider live PASS.
