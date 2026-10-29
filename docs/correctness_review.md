# Sửa correctness và trình bày kết quả sau bàn giao

## Kết luận hiện hành — 28/10/2026

**APPLICATION_ACCEPTED_WITH_UPSTREAM_LIMITATIONS**, chỉ trong phạm vi hỗ trợ và mẫu
nghiệm thu dưới đây. API application `4ab2c5a1cc115b95cbc9854d6dc65f75a95ae473`, image
`sha256:2d27fba187bb8703ebefbb214931933576767a52d7a32855b05d4a25c3bf5d98`;
Web application `de0572ebf7e946c3396c5693a9c5a3f27ab6a4ef`, image
`sha256:b2188879d84d6069f66dd73a13210bb810d269a23366aa77d6d4fd6eb307a7b3`.
Các commit bàn giao chỉ sửa tài liệu sau hai application revisions này không đòi rebuild.
Không release tag/full Stage2, không tuyên bố mọi câu hỏi/schema đều đúng.

| Lỗi | Root cause và mức chắc chắn | Sửa ở đâu | Regression | Live / trạng thái |
| --- | --- | --- | --- | --- |
| Policy-only bị chọn HYBRID | CONFIRMED: Router contract chỉ biểu diễn route, không biểu diễn loại bằng chứng cần dùng; history/current request chưa tách rõ trách nhiệm. Lý do suy luận nội bộ của model lịch sử UNKNOWN. | `routing/router.py::RouteDecision`, `QueryRouter.route`; `routing/service.py`; dataset/chat services truyền current question riêng | Evidence/route contradiction, capability unavailable, ambiguity, explicit route, current/history switch; cả hai SDK wire | Auto RAG citation23 và policy-only follow-up citation50 PASS; FIXED trong mẫu đã kiểm |
| COUNT+SUM gặp 504 | CONFIRMED failure boundary trước đây là provider deadline/transport, không có bằng chứng compiler lỗi ở trace504 | Không tăng timeout/retry, không sửa SQL để che transport; scalar guards đã sửa ở đợt trước giữ nguyên | Independent PostgreSQL COUNT/SUM/AVG, NULL, Decimal, scalar và grouping | Exact question trả192 và24360000 đúng oracle,3.328s; NOT_REPRODUCED ở lượt mới, không tuyên bố hết504 vĩnh viễn |
| Hybrid mới scope incomplete | CONFIRMED contract gap: evidence/intent/scope có defaults, schema/SDK cho bỏ fields; service chỉ dùng full classification khi intent khácnone và scopeall_entities. Raw intent/scope của trace lỗi UNKNOWN, chưa chứng minh là nguyên nhân duy nhất | `routing/router.py::RouteDecision` yêu cầu cả ba fields; local dispatch validation; descriptions chung; safe enum metadata ở diagnostics/observability | 3 tests FAIL trước sửa;45 SDK/routing checks PASS;240 related targeted PASS có overlap, không cộng. Complete intent qua real Hybrid verification6cases/2SDK/3selections | PR4 Hybrid8entities/5đạt/3chưa và follow-up3entities PASS đúng oracle; FIXED trong mẫu, giới hạn paraphrase còn công bố |
| Alias/thuật ngữ/error summary khó hiểu | CONFIRMED fallback thiếu metadata dùng alias làm nhãn; UI error chung không phân biệt boundary | `text_to_sql/answer.py::compose_sql_answer`, `routing/hybrid_evidence.py::compose_answer`, `ErrorDetails.tsx`, `ChatMessage.tsx` | Neutral metadata fallback, Decimal/NULL/DATE/ID, category-specific safe errors, collapsed evidence/accessibility | Summary và evidence live đúng số/citation; friendly provider errors chỉ kiểm offline, không cố tạo paid failure |
| Knowledge403/timeout | CONFIRMED các lượt lịch sử dừng ở upstream trước plan/SQL; quyền gateway/model inference hiện tại UNKNOWN | Không đổi auth/key/model/endpoint; giữ manual và fallbackOFF | Hai SDK contract/mapping offline PASS không thay provider acceptance | GET/models200,334ms,cóknowledge; không đủ chứng minh generation/structured support; UPSTREAM_BLOCKED/chưa nghiệm thu lại |

PR[#4](https://github.com/MinhHoang1403/Shopquery-AI/pull/4) đã squash merge.
[Exact application-main CI40631282398](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/40631282398)
**4/4 jobs PASS:1523 backend,878 PostgreSQL,88 frontend,125 mock E2E,10 maintenance,
10 Compose**. Local targeted và full CI được phân biệt; không cộng overlap thành test count.
Giữ QueryPlan/Pydantic/binder/compiler, approvedN:1/fact/grouping/COUNT provenance,
WHERE/HAVING/LIMIT coverage trước execution, AST/read-only/timeout/rowcap, Decimal/NULL,
owner/workspace scope, citation identity và verified conversation guards. Không đổi dependency.

### Cửa sổ live cuối và đối chiếu độc lập

Sau failure của cửa sổ đầu, operator cho phép tiếp tục tự kiểm an toàn trong hạn mức;
cửa sổ mới giữ trần3câu/6generation/3query/0document, không reuse cửa sổ đã đóng.
Chỉ Gemini, attempts1, không retry/fallback hoặc Knowledge generation. Cả ba dùng cùng
hội thoại dataset17, tài liệu synthetic đã xác minh; follow-up chỉ gửi sau Hybrid PASS thật.

| Câu | Correlation | Kết quả được đối chiếu | Usage / thời gian |
| --- | --- | --- | --- |
| Theo chính sách KPI đã lưu, những kho nào đạt và những kho nào chưa đạt? |c3dcc160229e4e788b05b27acadbb2c2|HYBRID,verified_classification;8kho,5đạt/3chưa; mọi tổng/sốđơn đúng independent fact oracle,citations50/51;intentall/scopeall_entities|1generation/1query;2.932s |
| Vậy còn những kho chưa đạt KPI? |5585fe2882df491ab3b147e62f6c8081|Cùng hội thoại/context;K01,K02,K03 đúng oracle,fullSQL evidence vẫn8kho;verified,citations50/51|1generation/1query;2.669s |
| Vậy quy định đó yêu cầu tính những trạng thái đơn nào? |03cb3b972bd54bc08ae44cf56c646fca|RAG/evidence=documents;contexttrue,citation50 khớp nội dung;chỉHoàn tất trong kỳ,khôngSQL|2generation/1query;3.829s |

Lưu ý nhánh follow-up: classifier trả intentnot_qualified nhưng **scopefiltered_entities**.
Kết quả đúng nhờ resolver `classification_selection` hiện có nhận câu tham chiếu trong
grammar hỗ trợ, dựng full coverage rồi chọn subset. Không dùng PASS này để tuyên bố mọi
paraphrase đi qua typed-intent branch, hoặc contract bắt buộc sẽ bảo đảm semantic accuracy.
Không thêm regex ngành/dataset hoặc nới guard để ép câu này PASS.

Oracle:192facts/8kho,24dòng mỗi kho; tổng24360000. K01/K02/K03 lần lượt2400000/
2640000/2880000;K04/K053000000;K063240000;K073480000;K083720000.
Ngưỡng tài liệu>=3000000 nênK04–K08đạt. Chính sách/kỳ/trạng thái/citation50/51 kiểm riêng
với tài liệu, không lấy câu trả lời hoặc SQL do model tạo làm oracle.

Toàn nhiệm vụ có **7UI requests:6PASS/1FAIL trước correction**. Loại câu:2policy-onlyRAG,
2SQL,2Hybrid (1FAIL,1PASS),1follow-up classification;2câu cuối có context. Route đúng7/7
trong mẫu nhỏ, business false refusal1/7 trước correction,0/3 sau correction; không có
unsupported/ambiguous live samples nên không báo accuracy cho hai nhóm đó. Provider
transport failures0/7 không suy SLA. SQLCOUNT+SUM/hotel PASS trên de0572e; sau PR4 chỉ đổi
classifier contract, SQL offline/PG regressions PASS, không gọi lại hai câu để tăng score.

**Usage cộng dồn13/16generation,5/5query,0document,7/8UI; cả hai cửa sổ đã đóng.**
Langfuse có7roots/258observations,13generation/5query observations, IDs không trùng;
SDK usage đủ13generation:30162input+2105output=32267tokens. Embedding tokens/cost
UNKNOWN; cost estimate trên dashboard không phải hóa đơn. Raw input/output null và
metadata privacy checks PASS trên cả258observations; không ghi câu hỏi/SQL/rows/email/
owner/conversation IDs thô/keys/private Knowledge URL. Dashboard trace mới hiển thị2.93s
và pipeline thực. Không generation/embedding call nào chỉ để tạo telemetry.

### Trình bày, tổng quát hóa và vận hành cuối

Ví dụ có căn cứ, không tạo thêm lời trả lời trả phí để minh họa:

| Trường hợp | Trước / sau và phạm vi bằng chứng |
| --- | --- |
| COUNT/SUM | Raw alias fallback → nhãn từ result provenance đã kiểm; live192bản ghi/tổng24360000 đúng oracle, không tự thêm đơn vị tiền |
| Numeric filter/GROUP BY | Chi tiết16rows ở giao diện → summary16nhóm, mở bảng khi cần; live IDs/names đúng16khách sạn có>100phòng |
| Ranking | Ranking chỉ diễn đạt từ sort/limit metadata được xác minh; ordinal/date/ID không suy từ alias; regression/PG/E2E, không có lượt ranking trả phí mới |
| RAG policy | False refusal doHYBRID → câu trả lời tài liệu và citation23; follow-up tài liệu citation50,khôngSQL |
| Hybrid verified | Summary chung →5đạt/3chưa từ chính vector decisions đã Decimal-verify; subset3 có thể mở toàn8SQL rows |
| Insufficient evidence | Chi tiết validation/đề nghị đổi câu hỏi dù yêu cầu rõ → thông báo không đủ căn cứ xác nhận; guard/error details giữ thu gọn, negative tests |
| Provider unavailable | Thông báo chung hoặc lẫn thiếu dữ liệu → summary timeout/quyền truy cập/quota theo safe category; technical details thu gọn, offline regression |

Frontend không đổi số liệu, không tính KPI ở client, một bảng evidence mặc định thu gọn;
pagination/mobile/keyboard/citation/SQL detail còn nguyên. Live reload giữ Google existing
session, ba câu/history và citation; không gọi đó là fresh OAuth acceptance.

Phạm vi tổng quát:4domains trong routing fixtures (logistics/energy/hotel/library),
library held-out không dùng làm prompt examples;16phrases script metadata như bảng bên
dưới. Metamorphic3schema variants/12executions+3threshold checks bằng oracle độc lập,
không đo model accuracy. Negative tests gồm unavailable/unclear/contradiction/missing
metadata, unverified/cross-owner context, metric/coverage/grain/refusal;45 và240targeted
checks có overlap nên không bịa tổng số negative độc lập. Không hardcode giá trị nghiệp vụ.

Strict verifier88modules/source manifest/config/image/health PASS; manifest
`3054d4cad4f1d1a3e03746f67fa4fde1f88895f468ace4f923106b2d9e4bc123`.
MainPG giữ container511c4f5a và volume`shopquery-ai_postgres_auth_20261019`;36data objects
và316messages cũ≤390 có fingerprint không đổi. Chỉ thêm14messages nghiệm thu, tổng330,
maxID404. Sáu Langfuse containers/datastores giữ nguyên. Không migrate/re-embed/BGE.
Gemini default/gateON/GuestOFF/fallbackOFF/embedding2-768/Knowledge manual giữ nguyên.

Cleanup sau promote: xóa exacttags của3API images07045862/d7f2d822/6a632447 đã xác minh
không container tham chiếu và không cần rollback. Giữ active2d27/b218,rollback4a80/9b,
các model/PG/Langfuse images và toàn34volumes. Images64→61; Docker báo57.44→57.42GB
(làm tròn/shared layers). Hostfree138423947264→138423463936bytes trong hoạt động đồng thời;
**dung lượng vật lý thu hồi UNKNOWN/chưa chứng minh**, không nhân virtual image sizes.
Buildcache401/47.24GB giữ nguyên, không prune/force hoặc tác động project khác.

Evidence riêng ngoài Git:`C:/Users/admin/.codex/backups/shopquery-ai/evidence-routing-20261028/`,
gồm oracle/fingerprints, strict reports, usage, sanitized trace checks và screenshots;
không commit raw logs/history/config secrets. Runbook ghi đầy đủ active/rollback digests.

## Lịch sử và closeout

Đây là bằng chứng nghiệm thu28/10, không phải lượt kiểm thử mới. Trạng thái đóng dự án
và caveat byte CRLF/LF hiện tại ở [PROJECT_CLOSEOUT](PROJECT_CLOSEOUT.md).
Nhật ký trước correction, failures và scorecards đầy đủ được bảo toàn trong
[Git stable baseline](https://github.com/MinhHoang1403/Shopquery-AI/blob/b09ec4ebb21d63e2e11841243210bf23f6d54f26/docs/correctness_review.md). Không xóa hoặc đổi gold/tests.
