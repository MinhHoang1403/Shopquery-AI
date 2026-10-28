# Khả năng và giới hạn

Runtime đang sử dụng: Gemini default, Knowledge manual, fallback OFF, provider gate ON,
Guest AI OFF, embedding2/768/vector-only và Langfuse metadata-only ON. Đây là phạm vi
localhost đã nghiệm thu, không phải mọi schema/public deployment. Knowledge có live
passes nhưng đợt đánh giá rộng còn1 UNKNOWN nên chưa chuyển default. Kết quả hiện hành
ở [system acceptance](v2_final_acceptance.md), [telemetry](observability_acceptance.md)
và [deployment](deployment.md). Hệ thống chuyển sang sử dụng/bảo trì có kiểm soát.

## SQL

Production hỗ trợ authorized SELECT, filters, arithmetic, aggregates, GROUP BY,
sorting/top-N, thời gian và NULL/zero/Decimal. Uploaded workspace không có quan hệ
chỉ truy vấn một bảng; runtime bật approved JOIN bằng `SQL_JOIN_V1_ENABLED`.

JOIN hai/ba bảng cần một/hai approved relations và revision/key proof hợp lệ.
Backend kiểm exact ON, fact → dimension, uniqueness/no fanout. Mặc định GROUP BY
entity key; typed grouping=category giữ đúng các category được yêu cầu. Category
JOIN chỉ nhận direct non-identity columns, projection và GROUP BY khớp chính xác;
không thêm entity IDs làm thay đổi mức tổng hợp. KPI classification vẫn dùng entity
coverage, không chuyển sang category. Không mở many-to-many hoặc dimension measures.
Chain/star ba bảng chỉ aggregate fact gốc. Shared-dimension two-fact, many-to-many,
composite/outer/self joins, chu trình và đường mơ hồ bị từ chối.

Automatic discovery dùng header gốc để tách snake_case/camelCase/PascalCase, bỏ dấu
tiếng Việt, tiền tố số và các wrapper danh sách/catalog. Nhận `id`, `code`, `ma`/`mã`,
`ref`, `key` ở đầu/cuối tên; `number`/`no` cần metadata bổ sung xác nhận định danh.
Khóa nguồn phải có tên thực thể; `id` trống nghĩa ở cả hai bảng không đủ bằng chứng.
Không dịch/đoán tên khác ngôn ngữ hoặc dùng trùng giá trị làm bằng chứng nghiệp vụ.
Tên bảng mở rộng cần thêm cột tên thực thể và một vai trò khóa rõ ràng. Chỉ tự kích
hoạt TEXT/BIGINT cùng kiểu sau full-data N:1 verification, không NULL/trùng/orphan,
không ứng viên cạnh tranh hoặc đường nối khác. Score chỉ sắp thứ tự kiểm tra.

Tải bảng mới tự chạy detector. UI liên kết chỉ đọc, không gọi discovery khi mở/render.
Quét lại qua API quản trị không re-ingest, sửa bảng gốc, gọi AI hoặc ghi đè liên kết đã có. API owner-scoped
`POST /api/datasets/{dataset_id}/relationships/discover` giữ CSRF/quota/dataset lock.
Mỗi lượt kiểm tối đa20 cặp, ngừng bắt đầu kiểm tiếp sau2 giây, từng SQL statement
vẫn chịu timeout5 giây. Quét chưa đủ không tự kích hoạt kết quả một phần. Gợi ý cần
kiểm tra lại và explicit confirmation bằng revision hiện tại; 1:1 không tự chọn chiều.

COUNT(*) đếm matched fact rows; COUNT(nullable column) đếm non-NULL values; verified
INNER fact key có thể row-equivalent. SUM/AVG NULL không đổi thành zero. Calendar
executor là `Asia/Ho_Chi_Minh`; boundaries giữ offset và khoảng `>= start AND < end`.
Không writes, CTE/subquery/window/locks hoặc hàm ngoài allowlist.

Evidence UI triển khai28/10 mặc định thu gọn bảng/SQL/citation, không lặp inline table.
Structured rows đi riêng với summary; scalar/count+sum được diễn đạt
deterministic, không thêm generation call hoặc suy đơn vị từ alias. Numeric display
chỉ opt-in theo compiled type/aggregate metadata; identifiers/unknown legacy strings
giữ nguyên. Detail/SQL/sources vẫn mở được; kết quả lớn phân trang20, SQL cap200 giữ.
Conversion diagnostics phân biệt literal/non-literal, QueryPlan bounds và final
contract validation bằng bounded safe codes; original provider payload không log.

Production dùng typed QueryPlan: +/−/×/÷ numeric, SUM/AVG/MIN/MAX một bảng,
AND/OR, IN/NULL, GROUP BY, SUM HAVING, sort/limit và typed temporal ranges.
Day/month/year grouping và YYYY-MM/YYYY-MM-DD formatting dùng business timezone.
Mẫu SUM(x)/COUNT(x) compile thành AVG(x), giữ NULL và exact numeric semantics;
dynamic denominator zero trả NULL, literal zero bị từ chối. Không đổi NULL thành zero.
Uploaded JOIN vẫn chỉ direct root-fact SUM/AVG và COUNT; aggregate arithmetic,
MIN/MAX/dimension metrics, COUNT HAVING và nested aggregates vẫn bị từ chối.
Default demo dùng đúng bốn models/FKs đã khai báo và revenue quantity×unit_price;
quy tắc này không áp dụng cho uploaded workspaces.

## RAG và Hybrid

Auto Router dùng một structured classifier call với evidence_requirement và intent/scope
bắt buộc; backend suy SQL/RAG/HYBRID từ loại bằng chứng, không dùng keyword ngành nghề.
Thiếu metadata bị từ chối trước dispatch, không gọi classifier/model lần hai. Current question
tách khỏi bounded history; history chỉ giải tham chiếu, không bắt buộc dùng route trước.
Đây vẫn là model semantic classification, không chứng minh mọi paraphrase sẽ đúng.
Typed intent/scope không tự cấp quyền hoặc chứng minh chính sách; guards hiện có vẫn kiểm.
Explicit /sql,/rag,/hybrid giữ nguyên và không phát classifier call. Các metadata/enum chỉ
ghi diagnostics an toàn; user-facing badges và provider errors dùng ngôn ngữ dễ hiểu,
technical codes giữ trong details thu gọn. Thiếu result metadata dùng summary trung tính,
không tự dùng alias làm nhãn nghiệp vụ. Hybrid summaries đếm cùng các decisions đã kiểm.

CSV/XLSX tạo bảng; PDF text-layer, DOCX, TXT/MD tạo tài liệu. Không OCR, DOC cũ,
macro, URL ingestion hoặc vector database mới. Original binaries không lưu để tải
lại. Không tự re-embed corpus main hoặc đổi embedding dimensions.

Runtime hiện vector-only, top_n3. Local `BAAI/bge-reranker-v2-m3` là tùy chọn theo
cấu hình/extra riêng, chưa bật production hoặc được chứng nhận tăng retrieval quality.
Candidate K12 chỉ áp dụng khi reranker hoạt động; chỉ xếp original retrieved chunks.
Guest giữ vector-only với isolation limits. Không chạy benchmark GPU để chốt bàn giao.

Hybrid retrieval trước SQL. Verified scope gồm một numeric rule SUM/AVG/row count/
non-NULL count, exact threshold/operator/source units/entity key, all rows và whole
document. Một grammar đóng cho SUM có kỳ/trạng thái chỉ được dùng khi đủ toàn bộ
registered chunks/section titles/hash/owner proof (tối đa20 chunks/60.000 ký tự) và
COUNT/non-NULL/MIN/MAX toàn cột chứng minh mọi dòng nằm đúng phạm vi. Dữ liệu ngoài kỳ,
status hỗn hợp, NULL, tên/heading ngoài grammar hoặc cột mơ hồ không được suy all-rows.
Chưa hỗ trợ arbitrary filtered-policy plans. Closed bilingual prose grammar không phải general rules
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
