# Text-to-SQL và JOIN — nghiệm thu độ tin cậy, 20/10/2026

> Mục A–M ghi kết quả lượt baseline `eeaffd4`; mục N ghi bản sửa offline.
> Kết quả live mới nhất ở mục Q: đúng một probe do người dùng gửi qua UI,
> FAIL CLOSED tại join_aggregate. Chưa nghiệm thu Gemini JOIN positive trên UI.
> Mục O giữ lần chẩn đoán trước, mục P ghi hardening/deployment offline đã PASS.
> Mục R bổ sung chẩn đoán từng nhánh offline; không thay kết luận live FAIL ở Q.

## A. Kết luận

**Chưa nghiệm thu đầy đủ Gemini JOIN end-to-end trên 8080.** Bản sửa giúp sáu
probe synthetic sau chẩn đoán đạt trong harness, nhưng probe cuối trên giao diện
tài khoản vẫn bị validator từ chối. Không được lấy CI xanh hoặc harness PASS để
tuyên bố mọi câu hỏi/model/workspace đều hoạt động đúng.

Source đã kiểm thử và triển khai: `071b7f5cfdf2e6a9edbbb4ae4ef24fea8f16e786`,
baseline `0bb9089d03eb73973d2a7db6c8c29e095695bd7a`. Commit tài liệu tiếp theo
không đổi source runtime. Đây là nghiệm thu local, không phải production/VPS.

## B. Nguyên nhân có bằng chứng

1. Probe Gemini đầu tiên giữ raw **synthetic** SqlDraft trước validation:
   JSON đúng contract, bảng/khóa/alias hợp lệ, router chọn SQL, nhưng `FROM`
   bắt đầu từ dimension rồi JOIN fact. V1 yêu cầu fact → dimension. Validator
   từ chối đúng, executor không chạy; không có lỗi 503 trong probe này.
2. Hai câu hỏi lịch sử về AVG giá và COUNT đơn hàng gắn với workspace chỉ có
   `fees.csv` chứa `Fee` và `inventory.xlsx` chứa `Mã`, `Nhà cung cấp`.
   Kiểm tra metadata main bằng transaction read-only; không gửi dữ liệu đó đến
   provider. Schema không có giá/sản phẩm/đơn hàng: không có căn cứ trả số.
   Thông báo cũ gợi lỗi JOIN và nhãn “Ngoài phạm vi” gây hiểu nhầm.
   Không có raw route/draft của những lượt lịch sử nên không khẳng định tầng
   model nào đã từ chối chúng.
3. Router trước đây nhận cả các lệnh cấm SQL trong schema context. So sánh chạy
   module baseline với source mới cho thấy cùng fixture một bảng + tài liệu:
   trước có `Never JOIN tables` trong context đưa vào router; sau router nhận
   facts/capabilities, generator vẫn nhận đầy đủ SQL restrictions.
   Đây là bằng chứng ranh giới prompt, không phải phép đo độ chính xác LLM trước/sau.
4. Tái hiện mất precision khi JSON số nguyên `9007199254740993` qua JavaScript
   thành `9007199254740992`. Thêm test fail trước sửa; sửa serialization chứ
   không đổi kiểu dữ liệu PostgreSQL.
5. Probe số 8 trên UI thật vẫn trả thông báo `calculation` từ kiểm tra JOIN.
   Workspace synthetic có confirmed relation, preview hợp lệ. Không bật log
   raw draft trong production, nên **chưa phân biệt được sai hướng/khóa hay
   aggregate trong lượt UI này**. Không suy đoán, không gọi probe thứ 9.

## C. Thay đổi nhỏ đã giữ

- `datasets/context.py`: fragment FROM fact / INNER JOIN dimension / ON đúng
  physical identifiers lấy từ approved metadata, không hardcode lĩnh vực.
- `dependencies.py`, `guest/pipeline.py`, `routing/router.py`: giữ phần Hybrid
  legacy có ích; tách routing context khỏi SQL-only restrictions. Một bảng +
  tài liệu có thể HYBRID mà không cần JOIN. Generator/validator vẫn giữ V1.
- `core/errors.py`, `routing/service.py`, `generator.py`, `join_policy.py`,
  `validator.py`: phân biệt nhỏ unknown/relationship/calculation; không echo
  unsupported reason của model hoặc đánh đồng mọi từ chối với thiếu quan hệ.
  Không mở thêm SQL được phép, không repair loop, không đổi retry/model.
- `datasets/parser.py`, `text_to_sql/executor.py`: integer vượt ±(2^53−1)
  thành chuỗi chữ số chính xác trong preview/result; integer nhỏ, boolean,
  NUMERIC, NULL/zero giữ contract. Integer vượt PostgreSQL signed BIGINT bị
  từ chối lúc parse thay vì lỗi import. Không chuyển TEXT/ID sang metric.
- API description, SQL/Hybrid grounding prompt và frontend type comment cập
  nhật contract số lớn; không đổi route enum hoặc response shape.

## D. Giao diện và lịch sử

Nhãn `UNSUPPORTED` nay là **Chưa thể trả lời**. Mặc định:

> Mình chưa đủ thông tin để trả lời chính xác câu hỏi này. Bạn hãy kiểm tra dữ liệu hoặc liên kết bảng trong Quản lý dữ liệu nhé.

Có thông báo riêng khi xác minh được thiếu nguồn, thiếu quan hệ hoặc phép tính
chưa hỗ trợ. Không dùng “thiếu dữ liệu” thay cho số zero thật. Đúng một thông
báo generic cũ đã biết được chuyển sang copy mới **chỉ khi render assistant
UNSUPPORTED**, không rewrite database/history, không sửa user/error text.

65 Vitest và 105 Playwright mock PASS tại 1440/1280/768/390/320 px: SQL/RAG/Hybrid,
error/unsupported, upload, model selection, history reload, zero/NULL/Decimal,
Markdown/XSS, quota/gates, auth loading, A/B transition, relationship lifecycle.
Không có streaming implementation để nghiệm thu; response hiện là non-streaming.

UI thật mobile 8080 đã hiển thị copy mới cả lịch sử cũ và probe mới; reload
giữ đúng Gemini/UNSUPPORTED, không xuất hiện SQL/rows/sources giả. Ảnh private:
`ui-gemini-join-fail-closed.png`, `ui-authenticated-relationship.png`.
Ảnh Guest desktop/mobile: `live-guest-join.png` trong Playwright test output.
Không đưa ảnh tài khoản hoặc browser session vào Git.

## E. Correctness và oracle

- PostgreSQL disposable riêng; không chạy destructive pytest fixtures trên main.
- Golden JOIN mở rộng bảy cặp schema, gồm bán hàng/kho, học phí, nhân sự,
  logistics và điện năng. 20 pipeline cases = 5 lĩnh vực × SQL/HYBRID × hai
  model selections, fake gateway, restricted TEMP PostgreSQL thật.
- Expected SUM/AVG/COUNT lấy từ truy vấn fact riêng không JOIN và Decimal oracle,
  không lấy câu trả lời AI làm expected result. Giữ NULL khác zero; kiểm tra
  grouping/filter, các điều kiện biên tháng Việt Nam và độ chính xác NUMERIC.
- Bốn test single-table chạy đúng nguyên văn câu A/B, cả hai model selections,
  JOIN OFF: AVG Book=20.50, Pen=5.125; ba dòng orders = ba đơn. Gateway fake
  kiểm tra contract, không chứng minh mọi lần LLM sẽ chọn đúng route.
- Test schema 5/15/30 cột, Vietnamese/near-duplicate headers, alias/missing
  columns và limit 31 cột; giữ các test CSV/XLSX/multiple sheets, encoding,
  malformed/oversized, timezone, rollback và precision đã có.
- BIGINT DB→preview→API metadata→history và frontend giữ đủ chữ số. Không thể
  khôi phục chữ số đã bị Excel làm tròn trước khi upload, hoặc JSON history
  cũ vốn đã lưu sai từ trước; không tự sửa lịch sử đó.

## F. Security và negative paths

191 PostgreSQL integration PASS, cùng unit negatives: owner/workspace scope,
Guest capabilities, CSRF/Origin, session, deletion permissions, read-only role,
timeout/row limits, function allowlist, transaction rollback, relationship
revision/deletion/race, duplicate/NULL/orphan dimension keys.

Giữ V1 hai bảng/INNER/fact→dimension/một approved key pair. Wrong direction/key,
cross-owner/workspace, Cartesian/ON OR/ON 1=1, CTE/subquery/more tables,
dimension aggregates và COUNT sai grain vẫn bị chặn. Không cấp thêm database
grants hoặc endpoint arbitrary SQL để làm provider pass.

SQL/RAG/Hybrid có positive API+history integration và ba negative cases mới:
SQL đọc bảng cấm, RAG citation giả, Hybrid SQL hợp lệ nhưng citation giả.
Response lỗi không giữ SQL/rows/sources hay câu trả lời bịa thành thành công.

## G. Live providers — đủ tám probe, không vượt ngân sách

| Probe | Môi trường | Kết quả | Route/validator/execution/answer |
| --- | --- | --- | --- |
| 1 Gemini JOIN chẩn đoán | Synthetic harness, PostgreSQL TEMP | FAIL, 2.616s | SQL route đúng, reverse JOIN bị chặn trước executor |
| 2 Gemini SQL JOIN | Synthetic harness, PostgreSQL TEMP | PASS, 4.013s | Fact→dimension; An 50.00/2, Binh 0.00/1 khớp oracle |
| 3 Gemini Hybrid JOIN | Synthetic harness, PostgreSQL TEMP | PASS, 6.004s | SQL đúng; An đạt 40, Binh chưa đạt; dẫn đúng rules.md/chunk 1 |
| 4 Knowledge SQL JOIN | Synthetic harness, PostgreSQL TEMP | PASS, 5.520s | Route/draft/validator/rows/answer đúng oracle |
| 5 Knowledge Hybrid JOIN | Synthetic harness, PostgreSQL TEMP | PASS, 9.150s | Route/rows/grounding/citation đúng, không thêm quy định |
| 6 Gemini single-table AVG | Synthetic harness, PostgreSQL TEMP | PASS, 3.286s | SQL route, AVG Book=20.50/Pen=5.125, không JOIN |
| 7 Knowledge single-table AVG | Synthetic harness, PostgreSQL TEMP | PASS, 4.707s | Cùng expected result, không JOIN |
| 8 Gemini JOIN | Authenticated UI→HTTP→main, workspace synthetic 5 | **FAIL CLOSED** | Trả UNSUPPORTED/calculation, không rows/SQL/sources; reload giữ đúng kết quả |

Sáu probe harness sau sửa đi qua router→SqlDraft→validator→restricted executor→
grounded answer thật, **không phải browser/API acceptance**. Chúng chạy sau fix
JOIN/Hybrid, trước phần hardening số nguyên/legacy rendering bổ sung. Probe 8
dùng đúng source `071b7f5` đã deploy; vì vậy không suy rộng harness PASS thành UI PASS.

Bảy probe harness đo **22 logical generation + 4 logical embedding calls**.
Probe UI không instrument gateway; nhánh SQL bị từ chối trước answer, theo code
là router + SqlDraft, không có document/embedding. Không coi số suy ra này là
bộ đếm HTTP/billing. SDK/schema retries giữ nguyên; không có token/cost chính xác.
Model `knowledge`, `gemini-3.5-flash-lite`, embedding `gemini-embedding-2`/768
không đổi; fallback OFF. Không gửi dữ liệu thật/history đến provider.
Không chạy thêm live RAG hoặc 5/15/30-column provider suite trong lượt này;
16 live tests được deselect trong full regression.

## H. Google và Guest UI thật

Phiên Google cũ hết hạn khi mở quản lý dữ liệu; fail về Guest không bypass.
Sau khi người dùng đăng nhập lại, phiên hợp lệ truy cập được workspace/history,
preview synthetic relation 3/2 dòng, zero duplicate/NULL/orphan và xác nhận
idempotent thành công trên API mới. Một cuộc chat synthetic mới lưu hai messages,
reload khôi phục đúng model/answer. **PASS phạm vi authenticated session,
relationship preview/confirm và history; không có SQL JOIN positive UI pass.**
Không quan sát toàn bộ Google credential/OAuth redirect để tuyên bố kiểm thử
fresh-login flow; không đọc/xuất token, cookie hoặc storage state. Manual
Playwright helper chỉ opt-in chờ account readiness, không export phiên.
Xóa quan hệ authenticated trên main không chạy lại; đã có PostgreSQL/mock tests.

Guest UI thật 8080: **2/2 PASS**, desktop/mobile upload hai CSV, preview/confirm/
delete relation, capability isolation, invalid CSRF/Origin và layout. Không AI
calls trong suite này; chỉ reset RAM sessions do chính test tạo, không dữ liệu main.

## I. Bộ test trên exact source snapshot

| Kiểm tra | Kết quả |
| --- | --- |
| Ruff app/scripts/tests | PASS |
| Full pytest `-m 'not live'` | **602 PASS**, 16 deselected; 98.91s |
| Phân loại thu thập | 411 unit/non-integration + 191 PostgreSQL integration |
| npm ci / ESLint / TypeScript / production build | PASS; npm audit tại lúc cài: 0 vulnerabilities |
| Vitest | **65/65 PASS** |
| Playwright mock năm viewport | **105/105 PASS**, 3 phút |
| Live Guest UI, API mới trên 8080 | **2/2 PASS**, 57.6s, không provider |
| Live provider | 1 diagnostic fail + 6 harness pass + 1 authenticated UI fail |

Snapshot export từ Git index ngoài repository, không `.env`, secrets/private
overrides. Full pytest dùng database disposable `shopquery_test_reliability_snapshot`,
API credentials rỗng. So sánh toàn bộ 31 file staged với snapshot theo nội dung
normalize LF đạt trước commit. Không giảm/bỏ security assertions để xanh.

## J. Git inventory

- Review và commit 31 source/test files trong `071b7f5`; sáu Hybrid legacy được
  kiểm tra ranh giới prompt trước/sau và giữ regression coverage.
- Hai audit test modules và domain pipeline tests là synthetic; helper login
  opt-in không export auth state. Không thêm framework/dependency.
- 13 tracked docs bị xóa được khôi phục đúng HEAD vì không có bằng chứng deletion
  có chủ đích; không commit deletion. Không xóa local data để làm sạch status.
- `safe_join_v1.md`, `safe_join_v1_local_deployment.md`,
  `sql_reliability_observability_review.md` không có trên disk hoặc Git history
  trong lượt kiểm tra. Không dựng lại; dùng báo cáo JOIN final đã tracked và
  deployment evidence private có sẵn. `sql_correctness_hardening.md` được đọc từ
  HEAD/khôi phục. Báo cáo cũ giữ lịch sử, có link chuyển tới tài liệu này.
- Scan index không phát hiện key/token/private-key signatures đã kiểm tra.
  `.env`, overrides, venv, caches, node_modules, dumps, private evidence không stage.
- Source đã push không force. Commit tài liệu này cập nhật README, không thay
  source đã test. Trạng thái exact final HEAD/origin/CI được xác nhận trong
  tin nhắn bàn giao sau khi commit tài liệu, tránh tự tham chiếu SHA của chính file.

## K. CI

Source SHA `071b7f5cfdf2e6a9edbbb4ae4ef24fea8f16e786`:
[CI run 39360092655](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39360092655)
**success**; Backend quality, PostgreSQL integration, Frontend quality đều
success. Live provider không chạy trong CI.

CI của commit tài liệu kế tiếp chưa tồn tại tại thời điểm viết file; không
gắn kết quả source run cho SHA khác. Xác minh đúng final HEAD sau push và báo
URL/từng job trong bàn giao; xem [workflow CI](https://github.com/MinhHoang1403/Shopquery-AI/actions/workflows/ci.yml).

## L. Runtime và dữ liệu

Rebuild/recreate **API/web only**, actual compose + hai private overrides vẫn
giữ nguyên. Không recreate/reset/migrate DB, không chạy lại backup/restore.
API8001/web8080/DB15432 healthy, `/api/health` OK. DB container vẫn bắt đầu bằng
`511c4f5aaccc`, volume main `shopquery-ai_postgres_auth_20261019`; archived
`shopquery-ai_postgres_data` và hai recovery images pre-join vẫn tồn tại.
Compose cảnh báo archived volume label khác mapping hiện tại; đã để nguyên,
không làm theo gợi ý xóa volume cũ.

JOIN=true, provider gate=true, Guest AI=true; OAuth/models/fallback/quotas không
đổi. Hash nội dung 14 production Python modules thay đổi khớp commit. Web JS
`index-ivW5rakR.js` khớp snapshot build, SHA-256:
`18bfaabb7144201cff9f5c3cd90cd3c467f110b36b485ec6a004e2192b764d16`.

26 bảng giữ nguyên schema/columns/constraints/indexes/ACL/roles/sequence definitions,
migration versions và zero owner-reference errors. 19 bảng ngoài auth/quota/chat
giữ nguyên mọi row count/hash, gồm uploads/documents/embeddings/relations.
Fingerprint nhóm protected trước/sau giống nhau:
`4785c16b0a6e4840206d80427887f809ae5796cf954d382fd2d9618bea358d6e`.
4 conversations và 36 messages cũ, gồm toàn bộ timestamps/content/metadata,
khớp hash trước audit khi loại đúng cuộc chat synthetic mới khỏi phép đối chiếu.
Chỉ thêm một conversation + hai messages synthetic; giữ lại cho chủ dự án xem.
Auth user/session/OIDC và resource counters thay đổi trong lúc login/test thật;
không tuyên bố toàn database có fingerprint bất biến. Sequence messages tiến
theo hai message mới; không reset/đổi legacy timestamps.

Backup cũ ngoài repository còn nguyên SHA-256
`a9b458a5ee1c21966f9407e659075d2eadf6e071b4e244b9e07a2c9f18078138`.
Không tạo backup/restore/migration lặp lại. Chỉ dọn container disposable của
lượt audit, xác minh exact ID/label/tmpfs, không có persistent mounts trước xóa.
Dữ liệu test tmpfs đã mất, có thể dựng lại bằng fixtures; không đụng main volumes,
backup, recovery images hoặc Docker project khác. ShopQuery còn ba service chính.

## M. Giới hạn và bước tiếp theo

- **Blocker còn lại: Gemini JOIN positive qua UI 8080 chưa đạt.** Cần phê duyệt
  ngân sách probe mới để chẩn đoán trong harness cô lập mô phỏng physical schema
  main, giữ raw synthetic SqlDraft trước validator và đối chiếu với UI failure.
  Không nới policy hoặc kết luận nguyên nhân lượt 8 khi chưa có draft.
- Chưa live thử mọi domain/schema, mọi cách diễn đạt, tải đồng thời, uptime,
  mọi parser đối kháng hoặc fresh Google OAuth flow. CI không bảo đảm model đúng.
- Không triển khai VPS/Langfuse, không thêm model/agent, không fallback ngầm.
- Tắt JOIN khẩn cấp: đổi **private Compose override đang có hiệu lực** để
  `SQL_JOIN_V1_ENABLED=false`, recreate riêng API `--no-deps`; xác minh runtime
  flag sau đó. Không chỉ sửa `.env` khi YAML override vẫn ghi true. Việc tắt
  flag không rollback database và không cho phép xóa metadata/main volume.

### Cơ sở kỹ thuật

- [JavaScript safe integers](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number/MAX_SAFE_INTEGER): giới hạn 2^53−1 cho serialization.
- [PostgreSQL aggregates](https://www.postgresql.org/docs/17/functions-aggregate.html): COUNT rows/non-NULL và SUM/AVG giữ NULL/zero semantics.
- [PostgreSQL date/time types](https://www.postgresql.org/docs/17/datatype-datetime.html): TIMESTAMP khác TIMESTAMPTZ; không sửa legacy timestamps.

## N. Follow-up: sửa tương đương INNER JOIN, chờ duyệt live

Baseline: `eeaffd4702442024b3d27ed357fdaae4d9cd1f34`. Không audit lại toàn hệ
thống, không migration/backup/restore/main rebuild. Không sửa model, gates,
quotas, OAuth, frontend copy hoặc SQL generation prompt trong lượt này.

### Nguyên nhân đã chứng minh và giới hạn kết luận

Kiểm tra read-only metadata workspace 5: students có `id BIGINT, name TEXT`;
payments có `id BIGINT, student_id BIGINT, amount NUMERIC`, quan hệ
`payments.student_id → students.id`. Fixture riêng dùng đúng kiểu metadata,
tên vật lý ngẫu nhiên `dataset_<uuid>`, `RelationshipRepository.approved()` và
`build_workspace_context()`/`build_dataset_chat_service()` như authenticated API.

PostgreSQL test riêng chứng minh hai thứ tự INNER JOIN cho cùng rows và
SUM/AVG/COUNT, nhưng baseline application từ chối SqlDraft đảo thứ tự trước
executor. Test trước sửa: 8 unit FAIL/16 PASS; integration đầu tiên FAIL sau
khi PostgreSQL oracle đã PASS. Đây là false-negative do phụ thuộc vị trí FROM,
không phải lỗi Google 503. **Không suy ra raw draft của probe UI số 8 đã mất**:
sai key/aggregate vẫn có thể là nguyên nhân riêng của lượt đó.

Synthetic SqlDraft cụ thể trong `tests/test_join_order.py`:

```sql
SELECT s.name, SUM(p.amount) AS total, AVG(p.amount) AS average,
       COUNT(*) AS fact_row_count
FROM uploaded_data.dataset_11111111111111111111111111111111 AS s
INNER JOIN uploaded_data.dataset_22222222222222222222222222222222 AS p
  ON p.student_id = s.id
GROUP BY s.name ORDER BY s.name;
```

AST sau chuẩn hóa chỉ đổi hai Table bindings ở FROM và JOIN: fact `...2222`
với alias `p` vào FROM, dimension `...1111` alias `s` vào INNER JOIN. Không đổi
ON, khóa, alias, projection, filters, grouping hoặc literals. Case An/Binh có
oracle total 50.00/0.00 và fact counts 2/1. Fixture bổ sung NULL, Decimal lớn
và key BIGINT `9007199254740993` cũng khớp oracle fact-only độc lập.

### Logic và files

- `core/errors.py`: giữ `reason` cho UI, thêm internal code:
  `join_direction`, `join_key`, `join_aggregate`, `join_relationship`.
- `text_to_sql/join_policy.py`: yêu cầu đúng một approved relation cho cặp bảng;
  phân biệt thiếu/ambiguous relation, sai ON key, đảo thứ tự, aggregate không
  an toàn. Fact/measure types lấy từ backend relationship metadata, không từ
  alias hoặc vị trí FROM. Từ chối cả JOIN decorations ngoài allowlist.
- `text_to_sql/validator.py`: chỉ bắt đúng `join_direction` đã chứng minh
  một INNER equality giữa đúng hai approved bindings, đổi thứ tự AST một lần,
  chạy lại table/schema/function/column và toàn bộ JOIN policy. Không sửa SQL
  sai key/grain, không thêm generation call, retry hay repair loop.
- `routing/service.py`: log duy nhất mã nội bộ khi từ chối, không exception
  detail/SQL/prompt/rows/credentials. API/frontend không nhận mã nội bộ mới;
  thông báo ngắn gọn và response shape giữ nguyên.
- Tests mới `test_join_order.py`, `test_join_order_integration.py`; mở rộng
  `test_join_policy.py`, `test_sql_reliability.py` và authenticated API tests
  trong `test_relationship_api_integration.py` cho cả hai thứ tự bảng.

### Regression và an toàn

Ruff toàn app/scripts/tests **PASS**. Nhóm targeted ban đầu **90 unit PASS**,
**28 PostgreSQL/API integration PASS**. Sau thêm kiểm tra alias độc lập và
canonicalization idempotent, chạy **324 affected regressions PASS** (34.90s),
gồm single-table SQL, SQL/RAG/Hybrid với hai model selections fake, API/history,
Guest, relationships, golden/domain pipelines, Decimal/BIGINT/timezone.
Không gọi gateway thật; Knowledge regression ở đây là contract/offline,
không phải live provider acceptance mới.

Giữ SELECT-only, hai bảng/một INNER/một verified key pair; cấm wrong key,
ON OR/AND/1=1, CROSS/outer/lateral, aliases sai, unknown schema/table/columns,
dimension SUM/AVG/COUNT, unsafe COUNT alias, SQL injection/multiple statements.
Các assertions security cũ không bị bỏ; case reverse hợp lệ được chuyển sang
positive equivalence và vẫn giữ negative reverse sai khóa. Approved fact và
relationship ID vẫn truyền vào execution guard; test normalized query chặn
foreign owner, foreign workspace và relation đã xóa trước khi executor/answer chạy.

Không chạy lại frontend local vì không sửa frontend. CI chuẩn của commit được
push sẽ kiểm tra checkout đúng SHA; kết quả/URL exact SHA được báo trong bàn giao,
không gán CI baseline cho code mới. Không có test offline thất bại còn treo.

### Trạng thái runtime và đề xuất cần phê duyệt

**0 live calls trong lượt này.** Main 8080 vẫn chạy source trước; chưa rebuild/
recreate API/web để nghiệm thu bản sửa mới. PostgreSQL main/volumes và workspace 5
chỉ được đọc metadata, không ghi, không tạo session giả, không xuất cookies.

Đề xuất tối đa **2 Gemini SQL JOIN probes**, cùng synthetic students/payments:

1. Harness cô lập mô phỏng authenticated metadata/physical identifiers,
   giữ raw synthetic SqlDraft, internal code và canonical SQL trước executor;
   đối chiếu independent PostgreSQL oracle.
2. Sau khi cập nhật riêng API an toàn, dùng phiên Google hợp lệ trên 8080,
   chỉ workspace synthetic 5; kiểm tra rows, SQL canonical và reload history.

Mỗi probe dự kiến 3 logical generation (router + draft + answer), tối đa
**6 logical generation, 0 embedding** cho cả hai; nếu validator từ chối thì
dừng trước answer. SDK retries có thể tăng HTTP requests/quota/cost; không ước
lượng token/billing khi thiếu metadata. Không tự retry probe hoặc bật fallback.
**Chờ chủ dự án phê duyệt; không tuyên bố Gemini UI live PASS.**

Cơ sở: [PostgreSQL INNER JOIN/ON semantics](https://www.postgresql.org/docs/17/queries-table-expressions.html#QUERIES-JOIN)
và [SQLGlot AST API](https://sqlglot.com/sqlglot/expressions.html). Tính tương
đương chỉ áp dụng cho cặp bindings/predicate đã qua các điều kiện hẹp ở trên,
không phải phép rewrite JOIN tổng quát.

## O. Hai probe được phê duyệt — dừng sau probe 1

Source chạy đúng `2a8c113d4dea8c248a81421d82363246204fe5ed`, working tree sạch
trước thử. Chỉ Gemini `gemini-3.5-flash-lite`, không Knowledge/Hybrid/fallback.
Ngân sách được duyệt tối đa hai chat probes, sáu logical generation, zero embedding.

### Probe 1: FAIL CLOSED, đã xác định đúng lỗi

PostgreSQL test cô lập `shopquery_test_join_final` trên localhost15437, không
kết nối main trong pipeline. Dùng đúng physical table identifiers, headers/types,
table IDs 9/10 và dataset ID5 của workspace synthetic 5; owner test riêng,
students 2 dòng, payments 3 dòng, approved relation qua repository thật.
Context và service dùng đường authenticated `build_workspace_context()` /
`build_dataset_chat_service()`; không tạo Google session giả.

| Tầng | Kết quả |
| --- | --- |
| Router | PASS, SQL |
| Gemini structured SqlDraft | PASS về JSON/fields, có đúng hai bảng synthetic |
| FROM/JOIN/ON | Fact → dimension đúng; `f.student_id = d.id` đúng approved key; không cần normalization |
| Validation | **FAIL: `join_aggregate`**, nhánh COUNT(column) alias trong `validate_uploaded_join()` |
| Execution guard / executor | NOT REACHED trong live turn |
| Grounded answer | NOT RUN, không tạo answer số, rows/SQL/sources đều rỗng |
| Response | UNSUPPORTED, used_model=gemini, fallback=false |

Biểu thức gây từ chối chính xác:

```sql
COUNT(f.id) AS fact_row_count
```

V1 chỉ chấp nhận `COUNT(*) AS fact_row_count` cho đếm dòng; COUNT(fact.column)
phải mang nghĩa non-NULL value count và alias `fact_value_count`. Không tự sửa
key/grain hoặc đổi tên kết quả để ép PASS. Backend đã trả thông báo calculation
thân thiện, không trả SQL/dữ liệu giả. Raw SqlDraft chỉ lưu private synthetic evidence.

Mã lỗi trên được xác minh bằng **replay offline đúng raw live draft, context và
source** sau khi service đã chuyển exception thành response UNSUPPORTED. Harness
ban đầu kết thúc ở assertion route phải là SQL; không coi AssertionError của
harness là nguyên nhân ứng dụng. Không bật production raw logging để tìm lỗi.

Đối chiếu offline (zero provider calls thêm): thay đúng COUNT expression thành
COUNT(*) trong bản counterfactual test riêng thì validator, execution guard và
PostgreSQL oracle đều PASS: An 50.00/2; Binh 0.00/1. Không áp dụng thay thế đó
trong source hoặc live pipeline. Test với `[NULL, 1]` cho COUNT(*)=2 nhưng
COUNT(id)=1, chứng minh không được tự coi hai phép đếm luôn tương đương.
[PostgreSQL COUNT semantics](https://www.postgresql.org/docs/17/functions-aggregate.html).
Regression hiện có cho COUNT(column) gắn alias row-count: **1 PASS**, 24 deselected;
không chạy lại bộ test lớn khi không sửa source.

### Call budget và bằng chứng

- **1 logical chat probe**, **2 logical generation calls** (router + draft),
  **0 embedding calls**, 3.656s. Không gọi answer generation vì validation fail.
- Instrument private harness quan sát **2 HTTP requests**, cả hai HTTP200,
  không thấy request thêm do SDK retry; retry settings không đổi.
- Private evidence: `probe1.json` giữ raw synthetic draft; `probe1-analysis.json`
  giữ refusal code/stage, counterfactual và oracle. Không đưa raw evidence,
  credentials, cookies, prompts thật hoặc dữ liệu người dùng lên Git.

### Probe 2 và runtime

**Probe 2 NOT RUN theo điều kiện dừng khi probe 1 fail.** Không dùng lượt còn lại
để thử may rủi. Không gọi provider lần ba, không chủ động rerun probe 1.
Không build/recreate API/web/DB, không migration, restore/reset hoặc thay env,
OAuth/provider gates/model/fallback/quotas. Main API/web/DB vẫn healthy, container
DB main `511c4f5aaccc` và volume `shopquery-ai_postgres_auth_20261019` giữ nguyên.
Workspace/history main không bị ghi trong lượt này. PostgreSQL test riêng còn
giữ để phục vụ replay offline; chưa dọn database hoặc chạy prune.

### Blocker và đề xuất offline tiếp theo

Blocker hiện đã có bằng chứng: generator dùng COUNT(f.id) nhưng gắn alias đếm
dòng. Đề xuất tiếp theo là test nhỏ cho generation contract và làm rõ prompt:
đếm dòng luôn dùng COUNT(*) AS fact_row_count, dù bảng có cột id; COUNT(column)
chỉ dùng khi người dùng hỏi số giá trị non-NULL. Giữ mọi negative tests và
không thêm SQL repair/retry hoặc cho COUNT(nullable_column) giả làm row count.

Chưa sửa prompt/validator thêm trong lượt phê duyệt này. Cần quyết định riêng
cho bước sửa offline tiếp theo; mọi live nghiệm thu sau đó cần phê duyệt mới.
Chỉ cập nhật báo cáo local; chưa commit/push vì điều kiện cả hai probes PASS
để chốt báo cáo chưa đạt. Không gắn CI cũ cho thay đổi tài liệu chưa commit.

## P. Aggregation contract hardening — offline, 20/10/2026

Baseline `2a8c113d4dea8c248a81421d82363246204fe5ed`, origin/main trùng HEAD
trước sửa. Chỉ báo cáo mục O còn uncommitted; giữ nguyên bằng chứng đó.
Đã đọc AGENTS, source liên quan và private synthetic draft. Không audit lại
hệ thống, migration, backup/restore hay gọi provider.

### Contract thống nhất, không mở rộng validator

| Ý nghĩa câu hỏi | JOIN v1 canonical expression |
| --- | --- |
| Số dòng fact sau lọc/group | `COUNT(*) AS fact_row_count` |
| Chẩn đoán scalar SUM/AVG: empty hay all-NULL | `COUNT(*) AS matched_row_count` |
| Số giá trị không NULL của một cột fact, chỉ khi được hỏi | `COUNT(f.column) AS fact_value_count` |
| Tổng/trung bình measure | Direct `SUM(f.numeric_column)` / `AVG(f.numeric_column)`, kiểu NUMERIC/BIGINT |
| Số entity dimension | Single-table khi đủ; không gọi fact count là dimension count |

Không đổi alias để đổi nghĩa metric. COUNT(column) loại NULL; COUNT(*) đếm
dòng; SUM/AVG bỏ qua NULL nhưng empty/all-NULL vẫn NULL, không phải zero.
NUMERIC/BIGINT giữ serialization chính xác hiện có. Không float casts,
DISTINCT, FILTER, aggregate arithmetic hoặc dimension aggregates trong JOIN.
Câu hỏi cần grain/nguồn ngoài subset phải từ chối, không trả SQL một phần.
Quy tắc dựa trên [PostgreSQL aggregates](https://www.postgresql.org/docs/17/functions-aggregate.html).

- `datasets/context.py` là nơi chứa chi tiết JOIN contract, không hardcode
  bảng/lĩnh vực. Nêu rõ không suy đoán id NOT NULL, không hoán đổi COUNT aliases,
  direct fact measures, NULL/zero, entity grain và ưu tiên single-table.
- `generator.py` giữ common rules ngắn, trỏ tới contract của selected schema;
  arithmetic chỉ trong subset được phép, không đổi metric để vừa validator.
  Cùng generator cho Knowledge/Gemini; không thay gateways/models/retry/fallback.
- `text_to_sql/pipeline.py`, `routing/hybrid.py`: grounding phân biệt row-count
  aliases với non-NULL value count; không diễn giải thành dimension entities.
- Validator, execution guard, SQL executor, routing và API/FE contract không đổi.

### Quyết định AST

Không thêm COUNT normalizer. Metadata generator hiện không có trusted NOT NULL
contract; tên id/sample không chứng minh được. Test PostgreSQL cho 5 dòng:
COUNT(*)=5 nhưng COUNT(nullable id)=4. Khi ALTER id NOT NULL **chỉ trong test DB**,
COUNT(id)=5, nhưng validator vẫn yêu cầu dạng canonical cho row-count;
COUNT(id) AS fact_value_count được phép, không tự rewrite.

COUNT(f.join_key) tương đương COUNT(*) trên các matched rows của INNER equality
đã duyệt vì SQL equality không TRUE với NULL. Tương tự cột DB NOT NULL.
Đây là tương đương có điều kiện về schema/SQL semantics, không áp dụng cho cột
tùy ý. Chọn giữ tập cú pháp nhỏ: ngay cả hai dạng tương đương này với alias
fact_row_count vẫn bị từ chối, không bổ sung logic chứng minh/repair mới.
[PostgreSQL INNER JOIN semantics](https://www.postgresql.org/docs/17/queries-table-expressions.html#QUERIES-JOIN).

Giữ nguyên normalization đảo thứ tự INNER JOIN ở mục N: chỉ swap hai bindings
đã chứng minh đúng một approved equality, chạy lại đầy đủ validator, rồi guard
và read-only executor. Không sửa ON/key/aggregate/alias/filter theo phỏng đoán.

### Test matrix và replay

- `test_join_order.py`: 8 câu hỏi nguyên văn yêu cầu, assembled schema + generator
  prompt + structured fake drafts + validation. Hai cách hỏi số lần thanh toán
  dùng fact row count; học phí không thiếu dùng value count; tổng theo entity
  dùng fact SUM; AVG khoản thanh toán dùng fact single-table; số sinh viên dùng
  dimension single-table; số đơn hàng thiếu nguồn → UNSUPPORTED; đếm dòng của
  bảng fact được fixture chọn dùng single-table. Không ép mọi COUNT thành JOIN.
  Intent/draft là expected fixtures, **không đo độ chính xác LLM**.
- `test_join_order_integration.py`: 27 aggregate variants × hai thứ tự JOIN =
  **54 cases: 28 accepted, 26 rejected trước executor**. COUNT bao phủ cả 12 nhóm
  yêu cầu, gồm nullable id, cột units được
  pg_attribute xác nhận NOT NULL, approved join key, swapped aliases, dimension,
  DISTINCT, all-NULL và mixed NULL/zero. Thêm riêng id DB-proven NOT NULL.
- SUM/AVG NUMERIC/BIGINT, nhóm/scalar, zero/all-NULL/empty, matched_row_count,
  Decimal lớn `12345678901234567890.12`, BIGINT `9007199254740993`, nhiều projections,
  dimension fan-out, arithmetic/cast/FILTER negatives. Expected là truy vấn
  fact-only độc lập, không lấy output AI/JOIN SQL làm oracle; so sánh exact
  Decimal text/scale, NULL và chữ số integer browser-unsafe.
- Replay sáu dạng × hai fixture = **12 cases: 4 accepted, 8 rejected**: reverse, captured COUNT(id) alias
  sai, canonical COUNT(*), wrong key, dimension SUM, missing relation. Giữ hình
  dạng SQL synthetic đã quan sát; physical identifiers sinh mới trong DB test,
  không commit private raw evidence. Code từ chối lần lượt join_aggregate,
  join_key, join_aggregate, join_relationship cho bốn negatives; guard/executor/
  answer không được gọi. Hai positives đi qua parse/normalization/validation/
  guard/read-only PG và khớp oracle An/Binh, thêm NULL/Decimal/BIGINT fixture.
- SQL grounding và Hybrid prompt được kiểm tra rõ ý nghĩa aliases. Regressions
  hiện có cho Knowledge/Gemini selections fake, SQL một bảng, SQL/RAG/Hybrid,
  Guest capability, A/B owner/workspace, CSRF/Origin/session, revoked/revision
  relation, sai alias/ON AND/OR/third table, SELECT-only, timeout và row cap
  giữ nguyên assertions. Không giảm hoặc xóa security tests.

Test chạy trên database disposable mới `shopquery_test_aggregation`, localhost
15437 trong container tmpfs test có sẵn; không destructive fixtures trên main.
Process pytest không đọc .env, provider credentials rỗng, không gọi AI/embedding.
8 prompt contract tests FAIL trước sửa, PASS sau sửa; replay COUNT(id) vẫn
REJECT đúng semantics thay vì sửa validator để xanh.

### Kết quả và deployment

Ruff PASS; targeted SQL/JOIN/golden/authenticated/domain/RAG/Hybrid: **261 PASS**.
Full backend offline `pytest -m 'not live'`: **719 PASS, 16 live deselected**,
102.29s; **449 unit + 270 PostgreSQL integration**, không skipped offline tests.
Source commit **`be93d5a0659bdb0f887dfb89ce279d0100181c98`** đã push bình thường.
[CI exact source SHA](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39366369154)
**SUCCESS** cả Backend quality, PostgreSQL integration, Frontend quality:
Ruff, 449 unit, 270 PG, ESLint/typecheck/build, 65 Vitest và 105 Playwright mock
PASS. Không gắn CI baseline cho source mới. Không đổi frontend/API shape nên không
chạy lại full frontend local; CI vẫn phải chạy đủ backend/PG/frontend.

Preflight runtime: actual Compose gồm compose.yaml + hai private overrides
`.env.compose-ui.yaml` và `.env.join-v1.yaml`; toàn bộ planned API environment
trùng runtime. API trước deploy chạy source cũ; DB `511c4f5aaccc`, web `dbc51b8bcb4a`, main
volume `shopquery-ai_postgres_auth_20261019`. Không recreate DB/web hoặc migration.
Fingerprint read-only trước deployment lưu private, 26 bảng; backup cũ còn
SHA-256 `a9b458a5ee1c21966f9407e659075d2eadf6e071b4e244b9e07a2c9f18078138`.

Sau CI xanh, chạy đúng actual Compose `up -d --no-deps --build api`:

- API mới `54ccf295c96d`, image config SHA-256
  `c3bed7ef1e76843144b472ce58c0979535ee85d80b5c8460f66463cb595d43be`.
  Hash nội dung normalize LF của **8/8 modules** thay đổi kể từ runtime cũ khớp
  commit be93d5a (errors/context/Hybrid/service/generator/join_policy/pipeline/validator).
  Generator: `53af1f10913a65a9824d4cac380b63afa5131c67f256242f4ed99d796af411fd`;
  context: `a8759148956320bd3731dbf3dad46c01b881db92e5e8067db128d603a3dfbea5`.
- API/web/DB **3/3 healthy**, `/api/health` qua 8080 OK. JOIN ON; provider gate,
  Guest AI, Google OAuth, model/embedding/768, fallback OFF và toàn bộ API
  environment giữ nguyên (so sánh giá trị trong memory, không xuất secrets).
- DB/web giữ **nguyên exact container IDs**, main volume không đổi. Không
  migration, backup/restore, schema change, DML bằng AI, recreate web/DB hoặc prune.
  Archived volume/recovery images và backup cũ được giữ nguyên.
- Existing opt-in `relationships-live.spec.ts` trên **8080 thật: 2/2 PASS**,
  59.7s, desktop1440/mobile390. Guest upload hai CSV synthetic → preview → confirm
  → delete đúng quan hệ của phiên test; cross-capability 404, invalid CSRF/Origin
  403, anonymous personal API 401; layout không overflow, reset đúng hai phiên
  test của mỗi case. Đã xem ảnh mobile. Không gửi chat hoặc upload tài liệu cần
  embedding; không đọc/export Google session/cookies/token. Google UI positive
  JOIN **NOT RUN**; authenticated API/history được kiểm tra offline trong suite.
- Private manifests: `C:\Work\ShopQuery-Backups\aggregation-contract-20261020`.
  Schema/columns/constraints/indexes/ACL/roles/sequences/migration versions của
  **26 bảng giữ nguyên**; tất cả owner-reference checks = 0. **25 bảng** ngoài
  public.resource_limits giữ exact row counts và hashes, gồm accounts/sessions,
  datasets/uploads/documents/embeddings/relationships/conversations/messages.
  Fingerprint nhóm này trước/sau đều
  `811db474412b821aede331318502ac23d464dbee07a8e4c85c41a093676ac91d`.
- Đối chiếu strict toàn manifest ban đầu **FAIL riêng dữ liệu resource_limits**,
  không che kết quả hoặc khẳng định toàn DB bất biến. Bảng vận hành này từ 6 lên
  9 rows sau smoke (quan sát 10 khi lease test đang chạy); GuestControl vốn ghi
  rate buckets và tạo/xóa concurrency lease qua PostgreSQL. Đã kiểm tra lại mọi
  metadata của chính bảng này và mọi phần khác vẫn exact; lease còn treo = 0.
  Không reset counters/quota để làm sạch hash; không có sai lệch bảng nghiệp vụ.
- Checksum backup sau smoke vẫn bằng giá trị trước. Không có destructive tests
  trên main, không tạo chat synthetic mới hoặc chỉnh dữ liệu workspace 5.
  API restart làm hết phiên Guest RAM cũ theo thiết kế; dữ liệu persistent không đổi.

Offline acceptance **PASS trong phạm vi test đã nêu**; không bảo đảm mọi cách
diễn đạt/model SQL sẽ đúng. Commit tài liệu sau deployment chỉ cập nhật kết quả,
không thay source runtime. CI của final documentation SHA phải được xác minh
riêng sau push và báo trong bàn giao, không dùng run be93d5a thay thế.

**0 live generation, 0 embedding calls trong nhiệm vụ này.** Chưa có bằng chứng
Gemini sẽ tuân thủ prompt mới qua UI; không tuyên bố live PASS. Sau khi offline/
CI/runtime đạt, đề xuất **một synthetic authenticated UI Gemini SQL JOIN probe**
trên workspace 5, oracle An 50.00/2 và Binh 0.00/1; tối đa 1 logical chat,
dự kiến 3 logical generation (router/draft/answer), 0 embedding. SDK retries
giữ nguyên có thể tăng HTTP requests; không retry probe/fallback chủ động.
Phải chờ phê duyệt mới và session Google hợp lệ, không sử dụng lượt cũ còn dư.

## Q. Final Gemini authenticated UI probe — FAIL CLOSED, 20/10/2026

Người dùng đã tự gửi **đúng một lần** câu hỏi được duyệt trên UI 8080,
workspace synthetic 5, Gemini:

> Cho biết tên sinh viên, tổng tiền đã thanh toán và số lần thanh toán của từng sinh viên.

Đây là probe duy nhất của đợt phê duyệt cuối, không phải probe chưa dùng.
Browser automation của trợ lý vẫn bị chặn với thông báo local browser use
disabled; không bypass, không tạo session giả, không đọc cookies/OAuth tokens.
Bằng chứng UI là ảnh người dùng gửi; backend/history/oracle kiểm tra chỉ đọc.
Không gửi thêm chat, harness live, Knowledge, Hybrid/RAG hoặc retry chủ động.

### Kết quả từng tầng và mức độ chứng minh

| Tầng | Kết quả |
| --- | --- |
| UI gửi đúng câu hỏi | Ảnh người dùng khớp đúng một user message ID 39, workspace 5, owner conversation khớp owner dataset |
| Thời gian | User message 04:15:52.369292 UTC; assistant 04:15:56.081797 UTC (11:15 giờ Việt Nam) |
| Router | SQL theo control flow: workspace có hai bảng, zero documents; đi vào SQL validator và bắt SqlUnsupportedError. Không có raw RouteDecision capture |
| Structured SqlDraft | Đã qua structured parsing và SQLGlot parsing để tới JOIN policy; suy ra từ verified runtime code path, không có raw draft của lượt này |
| Tables/relation/ON | Metadata có đúng students/payments và một approved payments.student_id → students.id. Các kiểm tra table pair/approved equality nằm trước nhánh aggregate; không lưu raw SQL để xác định FROM order hoặc canonicalization thực tế |
| Full validator | **FAIL: join_aggregate**, log 04:15:56.074234084 UTC, ngay trước assistant response |
| Execution guard / executor / grounded answer | **NOT REACHED** theo thứ tự pipeline; không có query result hoặc câu trả lời AI số liệu |
| Persisted response | route=UNSUPPORTED; requested_model=gemini; used_model=gemini; fallback_used=false; error=null; SQL null, rows=[], sources=[] |
| UI answer | Copy calculation refusal trong ảnh khớp persisted assistant message 40; không tạo số liệu giả |
| History | DB đã lưu đúng câu hỏi, answer/model và response metadata; reload UI chưa xác minh do browser tool bị chặn |

Log chỉ chứa internal code, không raw SQL/prompt. `join_aggregate` gồm nhiều
nhánh: COUNT alias/argument, dimension measure, aggregate expression, FILTER,
kiểu dữ liệu SUM/AVG. **Không đủ bằng chứng để khẳng định lại lỗi COUNT(id)
của mục O hoặc một SQL expression cụ thể**. Không có raw synthetic SqlDraft
được capture trong lượt UI này; không tự sửa prompt/validator dựa vào suy đoán.
Đây không phải bằng chứng upstream 503 hoặc Google authentication thất bại.

### Oracle, budget và runtime

Read-only PostgreSQL xác minh lại đúng synthetic workspace: students 2 dòng,
payments 3 dòng, quan hệ nguyên vẹn, zero documents. Oracle fact-only độc lập,
map tên từ students: **An 50.00 / 2; Binh 0.00 / 1**. Đây là expected result,
**không phải kết quả của live executor** vì validation đã từ chối.

**Một logical chat probe do người dùng thực hiện**. Theo source code path:
**2 logical generation** (router + SqlDraft), **0 embedding**, không answer call.
Đây là số suy ra từ control flow, không phải gateway instrumentation/billing.
Không quan sát được actual HTTP request count: production HTTP logging tắt;
không coi zero log lines là zero requests hoặc khẳng định SDK không retry.
SDK retry/model/fallback/gates/quotas không thay đổi. Trợ lý không gọi thêm provider.

Runtime 8/8 modules khớp source be93d5a; HEAD
`7e444c231a9162acf789266ea72280f73d4e95cf`. JOIN ON, model
gemini-3.5-flash-lite, fallback OFF. API `54ccf295c96d`, web `dbc51b8bcb4a`,
DB `511c4f5aaccc` giữ nguyên, **3/3 healthy**; health qua 8080 HTTP200/ok.
Không build/recreate/migrate/restore/reset/prune hoặc thay cấu hình bảo mật.

### Data safety và bàn giao

So với manifest sau smoke ở P, schema/constraints/indexes/privileges/roles,
owner references và migration versions giữ nguyên. 23/26 complete table
manifests không đổi; ba bảng đổi dữ liệu là chat_messages, chat_conversations,
resource_limits. Messages từ 38 lên 40 với đúng hai messages synthetic 39/40;
conversations vẫn 5 rows, metadata hash đổi khi lưu lượt chat; rate counters
từ 9 lên 10. Không reset các thay đổi vận hành hợp lệ này để làm sạch hash.

38 messages cũ (loại đúng ID39/40) giữ exact row count và fingerprint
`827313b316d7c3ddaaa4c839d6cebbc7ff1a6817a1f56f195eee7e62eefc09e6`.
Datasets/tables/documents/embeddings/approved relationships nguyên vẹn.
Backup cũ vẫn SHA-256
`a9b458a5ee1c21966f9407e659075d2eadf6e071b4e244b9e07a2c9f18078138`.
Private evidence ngoài Git: `C:\Work\ShopQuery-Backups\gemini-join-ui-final-20261020`,
gồm read-only manifest và bản sao ảnh synthetic người dùng; không chứa raw
production prompts/SQL hoặc auth secrets.

Không sửa code, không chạy lại full regression/CI/migration. CI HEAD 7e444c2
[run 39367052377](https://github.com/MinhHoang1403/Shopquery-AI/actions/runs/39367052377)
đã xác minh success; đó là offline CI, không làm live probe này PASS.
Chỉ cập nhật báo cáo local; **không commit/push**, vì phê duyệt chốt tài liệu
chỉ khi live PASS chưa đạt. Ngân sách một probe đã dùng hết.

Kết luận: **Gemini SQL JOIN live trên synthetic authenticated UI chưa đạt**.
Bước tiếp theo chỉ đề xuất offline: capture có scope/private một synthetic
SqlDraft trước validator (không bật raw production logging), replay đúng draft
và xác định nhánh aggregate trước mọi sửa đổi. Việc capture draft mới cần một
phương án và phê duyệt riêng; không có thêm live call trong lượt này. Giữ
fail-closed và security assertions; chưa có căn cứ nới validator hoặc sửa metric.

## R. Chẩn đoán từng nhánh join_aggregate — offline

Baseline HEAD `7e444c231a9162acf789266ea72280f73d4e95cf`; báo cáo Q đang dirty
được giữ nguyên. Không gọi thêm provider, không đọc/xuất session secrets, không
rebuild/recreate 8080 hay sửa dữ liệu main. Chỉ dùng fake gateways và PostgreSQL
disposable `shopquery_test_aggregation` trên localhost15437 trong container test
tmpfs đã có; process pytest không đọc .env và API credentials rỗng.

### Lỗi có bằng chứng và sửa tối thiểu

Điểm mù đã chứng minh: bảy raise sites cũ đều mang code join_aggregate; hai
predicate gộp nhiều nguyên nhân. Log/history cũ không cho biết nhánh nào gây
từ chối. Thêm 46 tests trước sửa: **46 FAIL** vì chưa có aggregate_reason và
log chi tiết, không phải 46 truy vấn bị validator chặn nhầm.

Giữ `code=join_aggregate`, `reason=calculation` và toàn bộ response shape/copy.
Thêm duy nhất trường nội bộ optional `aggregate_reason` với tập Literal hữu hạn,
do backend gán hằng, không lấy từ SQL values/prompt/model unsupported_reason.
Tách hai predicate gộp thành các raise có cùng điều kiện từ chối nhưng lý do rõ.

| aggregate_reason | Synthetic case chứng minh |
| --- | --- |
| filter | SUM dùng FILTER |
| projection_expression | SUM + 1 hoặc COALESCE(SUM, 0) |
| multiple_arguments | COUNT nhận hơn một argument |
| count_star_alias | COUNT(*) thiếu alias hoặc dùng payment_count/fact_value_count |
| argument_expression | COUNT(1), DISTINCT, CAST, COALESCE argument hoặc SUM arithmetic |
| dimension_column | SUM/AVG/COUNT trên dimension |
| count_column_alias | COUNT(fact.column) gắn fact_row_count/matched_row_count |
| unsupported_function | MIN/MAX trên fact, ngoài subset COUNT/SUM/AVG |
| non_numeric_fact | SUM/AVG trên fact TEXT hoặc kiểu ngoài NUMERIC/BIGINT |

Files production thay đổi:

- `core/errors.py`: optional typed diagnostic, code family cũ không đổi.
- `text_to_sql/join_policy.py`: phân loại đúng chín rule-level causes; không
  sửa AST/draft, alias, key, metric hoặc thêm bất kỳ phép aggregate được phép.
- `routing/service.py`: log dạng `SQL request refused: join_aggregate (count_star_alias)`;
  chỉ mã nội bộ, không raw SQL/exception detail/physical IDs/rows/prompt.
  Không trả aggregate_reason trong API hoặc lưu trường này vào response history.

Không sửa generator/context, model/gateway, retry/fallback, validator parser,
execution guard, SQL executor, database schema, frontend, quotas hay gates.
Không thêm dependencies/framework, repair loop hoặc normalizer.

### Tests và oracle

- `test_join_order.py`: 22 biến thể × hai chiều JOIN = **44 cases**. Mỗi case
  đi từ fake structured SqlDraft qua generator/full validator; kiểm tra family,
  subtype, UI copy, private log và guard/executor/grounded answer NOT REACHED.
  Hai case SQL/HYBRID bổ sung xác nhận không tiếp tục RAG/answer khi SQL bị chặn.
- `test_join_order_integration.py`: **18 cases** = chín causes × hai chiều, dùng
  approved metadata thật qua repository/context; fake draft, real read-only
  executor có spy và guard thật được theo dõi để chứng minh không đi tới chúng.
  Fixture bổ sung duy nhất cột Note TEXT giả lập để test non_numeric_fact trên
  type metadata thật, không giả định chỉ từ tên cột. Không đổi bảng main.
- `test_relationship_api_integration.py`: **4 cases** = SQL/HYBRID × Gemini/
  Knowledge selections fake. Auth/CSRF, API và history dùng PostgreSQL thật;
  internal reason chỉ vào log, không xuất trong JSON/history, không SQL/rows/
  sources giả, không fallback, chỉ hai fake generation và zero embedding query.
- Replay captured synthetic COUNT(id) shape ở O phân loại **count_column_alias**;
  dimension SUM replay phân loại **dimension_column**; missing relation/wrong
  key không bị gán aggregate subtype. Không suy ra raw SQL bị mất ở Q.
- Giữ nguyên 54 aggregate matrix, 12 replay và independent fact-only PostgreSQL
  oracle: valid SUM/AVG/COUNT, zero/NULL/empty, Decimal/BIGINT vẫn chạy đúng;
  invalid key/alias/owner/workspace/ON OR/AND/third table và revoked relation,
  SELECT-only, timeout/row caps tiếp tục bị chặn. Không giảm assertions cũ.

Nhóm SQL/JOIN/authenticated API đầu tiên: **196 PASS**, 73.53s. Ruff toàn
app/scripts/tests **PASS**, git diff --check PASS. Full backend offline cuối trên
DB mới: **791 PASS, 16 live deselected**, 101.05s; 495 unit + 296 PostgreSQL
integration. Bao gồm optional error field và SQL/RAG/Hybrid/Guest/auth; xem S về
lần chạy trước bị stale fixtures khi tái dùng test DB, không che six failures.
Không chạy lại frontend/UI/CI vì không đổi frontend hoặc API contract và chưa push.

### Phạm vi hoàn tất và phần chưa thể kết luận

Đã sửa **mất thông tin chẩn đoán** và có regression tests ở cả chín nhánh.
Không có bằng chứng để đổi tập SQL được chấp nhận: các negatives được kiểm tra
đều nằm ngoài contract hiện tại; canonical positives vẫn khớp PostgreSQL oracle.
Không sửa prompt thêm hoặc nới validator chỉ để làm Gemini PASS.

**Không xác định hồi tố được subtype của live message 40 ở Q**: raw SqlDraft
không được lưu, log cũ chỉ có family. Bản sửa mới không thể tái tạo một response
LLM đã mất. Không tuyên bố lỗi Gemini authenticated UI đã hết; live FAIL ở Q
vẫn giữ nguyên. Không tự dùng thêm ngân sách probe.

Các thay đổi chỉ local, **chưa commit/push/deploy**. Main 8080 vẫn chạy source
be93d5a đã triển khai trước, chưa có log subtype mới. CI 7e444c2 xanh chỉ là CI
của HEAD cũ; chưa có CI cho working tree này. Không đụng Docker main/volume,
backup, OAuth hoặc dữ liệu người dùng. Mọi live/deployment tiếp theo cần yêu cầu
riêng; lượt offline này có **0 live generation, 0 embedding**.

## S. Ảnh workspace Học phí học sinh — xác minh context đúng nguồn

Ảnh bổ sung chọn **workspace 10**, không phải synthetic workspace 5. Kiểm tra
read-only metadata và đúng câu hỏi trong history: message 71 lúc 05:15:30 UTC,
assistant 72 lúc 05:15:31 UTC; Gemini/fallback OFF, route UNSUPPORTED, copy
generic khác calculation refusal của message 40 ở Q. Không có raw RouteDecision
hoặc SqlDraft nên không kết luận chính xác router hay generator đã từ chối;
không thấy SQL-refusal code trong cửa sổ log tương ứng.

### Nguyên nhân có bằng chứng

Workspace 10 có payments 12 dòng (table 20) và students 7 dòng (table 21),
**zero confirmed relationships**, zero documents. Source headers/types gồm:
payments.student_id TEXT, payments.amount_paid NUMERIC; students.student_id TEXT,
students.student_name TEXT. Không thiếu các cột phục vụ câu hỏi JOIN.

Dùng runtime code build_workspace_context → SqlGenerator với fake gateway tại
chỗ (không gọi provider), chỉ xuất booleans/type assertions, không raw prompt/
observed values: context chứa đúng hai bảng/cột, JOIN flag ON, không có default
demo schema, approved_joins rỗng, có explicit no-approved-relationship warning
và Never JOIN tables. Kết quả này **đúng với metadata hiện tại**, không phải
schema context làm mất một quan hệ đã xác nhận. Quan hệ workspace 5 không được
áp dụng sang workspace 10 dù file/bảng cũng tên students/payments.

Preview read-only bằng đúng verify_relationship (không confirm):

- payments.student_id → students.student_id: many-to-one, valid.
- Source/target rows 12/7; source NULL 0, target NULL 0, target duplicates 0,
  orphan rows 0. Không tự cast/normalize khóa.
- Số quan hệ confirmed sau preview vẫn **0**. Không INSERT/UPDATE hoặc tự cấp
  quyền JOIN; chủ dữ liệu cần xác nhận qua UI thông thường.

Các lần trước đã trộn hai trường hợp khác nhau: workspace 5 có trusted relation
nhưng model draft bị aggregate policy từ chối; workspace 10 mới upload chưa có
trusted relation nên không được JOIN. Bản sửa diagnostic ở R **chưa deploy**,
không được kỳ vọng sửa hành vi của source 8080 hiện tại. Prompt/fake tests PASS
cũng không chứng minh model live luôn sinh đúng subset. Không gán cùng một
nguyên nhân COUNT hoặc lỗi Google cho mọi ảnh UNSUPPORTED.

### Kiểm thử context và hướng xử lý

Thêm 4 integration cases trong test_join_order_integration.py: hai model
selections fake × hai chiều INNER JOIN. Tạo hai workspace riêng có cùng filenames
payments/students, kiểu khóa TEXT, measure amount_paid NUMERIC, 12/7 synthetic
rows theo metadata shape (không sao chép dữ liệu thực của người dùng).

Confirm một workspace khác trước, selected workspace chưa confirm phải có
approved_joins rỗng, no-relationship context, không chứa physical IDs workspace
khác. Fake draft cố JOIN vẫn bị chặn trước executor; không có numbers giả.
Sau xác nhận **chỉ trong test DB**, builder lấy đúng approved key/type/physical
IDs, bỏ Never JOIN; SQL pipeline qua canonicalization/validator/guard/readonly
PG đúng 7 nhóm và fact-only oracle, giữ zero, NULL, COUNT(*) chính xác. **4/4 PASS**.

Không sửa prompt/context production khi test và metadata chưa chứng minh lỗi
builder. Không auto-confirm quan hệ dựa trên tên cột hoặc nới aggregate subset.
Để bật JOIN cho chính dataset 10, chủ dữ liệu vào Quản lý dữ liệu → Liên kết bảng,
chọn fact payments / student_id; dimension students / student_id; Kiểm tra quan hệ
rồi Xác nhận liên kết nếu đúng ý nghĩa nghiệp vụ. Chỉ sau xác nhận quan hệ mới
có thể đi tiếp đến generation/aggregate validation; không cam kết model sẽ đúng.
Không tự chạy lại câu hỏi AI vì lượt này vẫn yêu cầu **zero provider live**.

### Tình trạng bộ test và giới hạn

Full offline đầu tiên dùng lại DB test aggregation từ lượt P: **781 PASS, 6 FAIL**
vì six legacy management tests dùng fixed workspace names đã còn từ full run cũ;
trùng uq_datasets_owner_name_ci trước khi chạy logic JOIN. Không đổi assertions,
không xóa records/DB để ép xanh. Dựng database mới shopquery_test_join_diagnosis
trong đúng container tmpfs test, giữ DB cũ; chạy 4 context tests ở trên rồi full
backend offline trên database mới, không cần thay đổi source/tests giữa hai lần.
**Kết quả cuối: 791 PASS, 16 live deselected, 0 FAIL**, 101.05s. Ruff và
git diff --check PASS. Tổng tăng 72 cases so với 719 baseline: 46 unit branch/
pipeline, 18 PG branch, 4 API/history, 4 tuition-context cases. Không giảm test
hoặc security assertions; frontend/API contract không đổi nên không chạy UI
suite riêng hoặc CI mới. Toàn bộ test dùng fake gateways, không API keys.

Main/Google OAuth/volumes/relationships không bị sửa. Không deployment/commit/
push hoặc CI mới trong lượt này; working tree giữ các sửa chẩn đoán/tests/report.
Không tuyên bố Gemini UI JOIN PASS; cần nghiệm thu live riêng sau khi chẩn đoán
đủ và được duyệt ngân sách mới.

## T. Tự kiểm chứng quan hệ upload và JOIN sau xác nhận — 2026-10-20

Phạm vi mới được người dùng duyệt: thử tự nhận diện quan hệ cho upload tiếp theo,
đồng thời kiểm tra phản ánh JOIN vẫn bị từ chối sau khi đã xác nhận. Giữ nguyên
các thay đổi offline R/S chưa commit. Không gọi thêm provider live.

### Bằng chứng trên runtime trước sửa

- Workspace 10 hiện có hai bảng, một record quan hệ valid, một approved join trong
  context thực tế; JOIN flag ON, `Never JOIN tables` không còn trong context.
  Kiểm tra chỉ đọc metadata, không ghi prompts/SQL hoặc dữ liệu người dùng.
- API log có `join_aggregate` lúc 05:55:30, 05:55:42, 05:55:55 và 05:56:06 UTC.
  Đây là từ chối ở aggregate policy sau bước relationship/key/direction, không
  phải thiếu schema context. Runtime cũ chỉ ghi family, chưa có subtype R.
  Không có raw draft ở các lượt này: **chưa chứng minh chính xác aggregate nào**
  của Knowledge/Gemini trong ảnh. Không quy mọi lỗi cho COUNT hay provider 503.

### Thay đổi

- `datasets/relationship_detection.py`: ứng viên chỉ từ tên khóa `_id`/`_code`
  có thực thể khớp tên bảng đích (chuẩn hóa tên, số nhiều đơn giản); TEXT/BIGINT
  cùng kiểu. Chỉ chọn duy nhất một khóa/đích/chiều cho cặp bảng, rồi dùng lại
  full-data verifier. Chỉ tự bật many-to-one, hai bảng không rỗng, không NULL,
  đích unique và orphan=0. Không suy luận chỉ từ tình cờ trùng giá trị; tên khó,
  1:1, kiểu khác hoặc mơ hồ vẫn phải xác nhận thủ công. Đây là heuristic bảo thủ,
  không phải bằng chứng hoàn hảo về ý nghĩa nghiệp vụ của mọi bộ dữ liệu.
- Auth: import bảng mới và quan hệ tự kiểm chứng cùng owner-locked transaction.
  Không tạo quan hệ khác cho cặp đã lưu; chỉ xét cặp có bảng vừa import, không
  quét/bật lại dữ liệu cũ khi GET/chat. Giới hạn 20, timeout SQL 5s/statement,
  transaction rollback nếu lỗi; upload thất bại không để lại bảng nửa chừng.
- Guest: cùng bộ phát hiện, worker không có credentials provider, PostgreSQL TEMP
  dưới role Guest, quota/timeout hiện có. File + quan hệ được thêm atomically vào
  RAM sau kiểm tra memory budget; không ghi vào bảng dữ liệu cá nhân.
- `RelationshipRecord`: thêm origin manual/automatic; automatic có confirmed=false,
  không giả người dùng đã xác nhận. Metadata nằm trong JSON statistics sẵn có;
  **không cần migration**. Record cũ mặc định manual/confirmed=true. Manual
  confirmation có thể nâng provenance nhưng giữ relationship ID.
- Frontend hiển thị nhãn tự kiểm chứng, giữ preview/confirm/delete thủ công và
  tải lại danh sách khi các table IDs thay đổi sau upload. API không nhận SQL,
  physical names hoặc origin do client cung cấp để tự cấp quyền.
- Context có một ví dụ aggregate dùng đúng physical identifiers/khóa/cột numeric
  của quan hệ được duyệt, không hardcode domain. Không chọn các tên ID/code làm
  measure ví dụ. Nhắc GROUP BY identifier khi yêu cầu theo từng entity.
- `join_policy.py`: sau khi kiểm chứng đúng một approved INNER equality và đúng
  fact metadata, `COUNT(f.<approved_join_key>) AS fact_row_count/matched_row_count`
  được canonicalize thành COUNT(*). Không sửa COUNT(f.id) nếu id không phải khóa
  JOIN đã duyệt, không đổi COUNT(nullable measure), DISTINCT, sai key/owner,
  dimension count/SUM/AVG hoặc biểu thức thành một câu SQL khác.
- Chẩn đoán private 9 subtype ở R được giữ nguyên; không hiển thị subtype/SQL ở
  frontend, không log raw draft/prompt/data. Không thêm repair loop/retry/model.

### Chứng minh COUNT hẹp và kiểm thử

[PostgreSQL COUNT](https://www.postgresql.org/docs/17/functions-aggregate.html)
phân biệt số dòng và số giá trị non-NULL. Với
[INNER JOIN equality](https://www.postgresql.org/docs/17/queries-table-expressions.html),
khóa tham gia equality không thể NULL trên dòng đã khớp. Vì vậy đếm chính fact
join key bằng COUNT(*) trên mọi matched row, kể cả nhóm/tập rỗng. PostgreSQL case
độc lập với fact id toàn NULL và một fact key NULL chứng minh: matched rows=3,
COUNT(f.key)=3 nhưng COUNT(f.id)=0. Không suy ra id NOT NULL từ tên hay mẫu dữ liệu.
Một case trước đây từ chối COUNT(f.student_id) nay chuyển sang kiểm tra oracle
COUNT(*), không xóa negative assertions COUNT(f.id)/dimension/wrong key.

- Trước sửa: bốn unit key-count variants FAIL ở count_column_alias; thêm detector
  tests trước implementation FAIL collection vì module chưa có.
- Targeted chính: **209 PASS** (detector, auto-auth, JOIN unit/PG), sau đó Guest
  worker/HTTP detection + JOIN hai model selections **2 PASS**. Lượt Guest đầu
  **2 FAIL** do test đọc sai envelope `response`, không phải production JOIN;
  chỉ sửa đường đọc response trong test rồi chạy lại đạt.
- Full backend offline trên DB mới `shopquery_test_auto_acceptance` trong đúng
  disposable tmpfs container port 15437: **829 PASS, 16 live deselected, 0 FAIL**,
  147.97s. Tăng 38 so với R/S: 16 unit + 22 PostgreSQL. Không API keys; fake
  gateway cho cả Knowledge và Gemini, PostgreSQL thật, không mock kết quả SQL.
- Auto API: upload có CSRF, automatic provenance, owner B bị chặn, SQL router,
  forward/reverse, COUNT key canonicalization, execution guard, NULL/zero Decimal,
  independent fact oracle, answer inputs và conversation history reload đều đạt.
- Security: sai owner/workspace/key/alias, revoked/missing relationship, SELECT-only,
  dimension aggregate, nullable count, precision/grain và SQL/RAG/Hybrid regressions
  giữ assertions và đạt trong full suite. Auto không overwrite manual, không tái
  tạo cặp đã xóa khi upload bảng không liên quan. Rollback upload được kiểm tra.
- Frontend lint/typecheck/build PASS; **66 Vitest PASS**; targeted Playwright
  manual link preview/confirm/delete desktop + mobile **4 PASS**. Full Playwright
  mock suite **105 PASS** trên 5 viewport, 3.2 phút; không gửi chat tới API thật.

Không tuyên bố Knowledge/Gemini UI live PASS. Đến đây **0 live generation,
0 embedding**, không thay model, provider gate, OAuth hoặc quotas. Chưa commit,
push hoặc tạo CI mới; không viện dẫn CI cũ cho working tree mới.

### Runtime 8080 sau deployment và giới hạn còn lại

- Preflight xác minh chính xác project shopquery-ai, ba file Compose đang dùng:
  compose.yaml + .env.compose-ui.yaml + .env.join-v1.yaml. Toàn bộ environment
  API so với cấu hình đang chạy khớp, không in secrets. DB host port 15432,
  API 8001, web 8080; volume main shopquery-ai_postgres_auth_20261019.
- Build/recreate **chỉ API và web**, `up --no-deps`; không migrate/seed/restore,
  không recreate DB. Compose cảnh báo volume cũ postgres_data có label cũ;
  không xóa hoặc sửa volume nào để xử lý cảnh báo đó.
- API mới 5109e082c44a; web d33081dc2211. DB vẫn nguyên full container ID
  `511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8`.
  Cả ba healthy; `/api/health` qua 8080 trả ok. **70/70 Python module hashes**
  trong image khớp working tree đã test, không có mismatch.
- JOIN=true; provider/Guest gates giữ nguyên true; Gemini gemini-3.5-flash-lite,
  fallback=false giữ nguyên. Không thay OAuth/model/quota hoặc đọc Google cookies.
- Main workspace 10: context có đúng một approved relation. Synthetic SQL AST
  dùng schema identifiers/metadata thực, không execute business rows: forward
  canonicalization từ dimension-first và COUNT fact join key đạt; owner execution
  guard đạt. Wrong key trả join_key; dimension SUM trả dimension_column. Không
  gửi SQL/context tới model, không log raw statement hoặc prompt.
- `relationships-live.spec.ts` được tăng assertions cho auto origin/confirmed=false,
  promote manual cùng relationship ID, xóa rõ ràng, Guest isolation/CSRF, giữ hai
  tệp và không gửi `/api/guest/chat`. Chạy thật trên **8080 desktop + mobile:
  2 PASS, 1.1 phút**, dùng CSV synthetic và PostgreSQL TEMP, không mock APIs.
  Không ghi storage state/trace; chỉ reset đúng các phiên Guest tự tạo của test.
- Lượt UI thật đầu **2 FAIL** tại chờ file thứ hai trong danh sách (5s), chưa đủ
  để suy ra backend upload lỗi. Test được sửa để chờ đúng preview file mới và
  response HTTP import, assert 200 rồi kiểm tra danh sách. Lượt cuối đạt cả hai;
  không tăng timeout/quotas production, không bỏ kiểm tra status hoặc UI state.
- Trước/sau deployment + Guest smoke: exact row counts và SHA-256 fingerprints
  của **24 bảng business/upload/relationship/chat metadata** đều khớp, gồm owner
  fields. Fingerprints tính ở PostgreSQL, không xuất nội dung hàng. Không áp dụng
  kết luận này cho operational rate/lease counters (smoke dùng giới hạn thật),
  cũng không đọc/hash bảng chứa session secrets. Không reset dữ liệu người dùng.

**Hoàn tất offline và runtime no-provider smoke trong phạm vi trên.** Chưa có
Google authenticated UI JOIN positive ở lượt này; được thay bằng real session/
CSRF/history API tests trên database cô lập, không giả là Google live acceptance.
Chưa chạy Knowledge/Gemini thật sau sửa; vẫn không biết subtype chính xác của
bốn lần từ chối cũ vì draft không được giữ. Bản runtime mới đã có diagnostic R
để phân biệt lần từ chối tiếp theo mà không lộ SQL/data. Nếu model tiếp tục sinh
COUNT nullable id sai alias, fail-closed vẫn là hành vi đúng; không sửa cột hoặc
thay đổi metric để tạo số liệu giả. Không tuyên bố lỗi live trong ảnh đã được
loại bỏ hoàn toàn chỉ từ fake gateway tests.

Git vẫn HEAD 7e444c231a9162acf789266ea72280f73d4e95cf, source runtime là **working
tree chưa commit**, không gắn nhãn giả là commit mới. README cập nhật hành vi tự
nhận diện/giới hạn. Không commit/push/CI mới; giữ nguyên các diff R/S đã có trước.
0 live generation, 0 embedding trong toàn bộ lượt T. Muốn nghiệm thu AI thật cần
phê duyệt ngân sách mới; đề xuất một SQL JOIN synthetic cho mỗi provider đang dùng,
tối đa hai chat / sáu logical generation, zero embedding, không tự thử lại.

## U. Hai câu hỏi synthetic được duyệt — Knowledge và Gemini live trên 8080

Người dùng duyệt đúng hai câu hỏi synthetic, một Knowledge/một Gemini, tối đa
sáu logical generation và zero embedding. Đã đọc lại AGENTS.md và mục T; không
thay production source/model/gates/quota, không rebuild/restart hoặc migration.

### Fixture, oracle và cách chạy

- Fresh Chromium Guest context trên 8080, không dùng Google session hoặc workspace
  người dùng. Upload qua UI hai CSV: students gồm S1/An, S2/Binh, S3/Chi; payments
  gồm S1=20.00, S1=0.00, S2=0.00, S3=NULL, S3=NULL. Không upload tài liệu.
- PostgreSQL oracle chỉ đọc VALUES trong container tmpfs test đã xác minh ID/
  label, database shopquery_test_auto_acceptance port 15437. Oracle GROUP BY fact
  student_id độc lập với SQL model; expected An=20.00/2, Binh=0.00/1, Chi=NULL/2.
- `join-providers-live.spec.ts`: auto relation valid/many-to-one, source=5/target=3,
  orphan=0, automatic/confirmed=false. Không xác nhận thủ công để test đúng tính
  năng upload xong chat. Cùng câu hỏi tự nhiên, không chèn SQL/alias vào câu hỏi:
  “Cho biết tên sinh viên, tổng tiền đã thanh toán và số lần thanh toán của từng
  sinh viên.” Gửi một lần Knowledge rồi một lần Gemini trong cùng phiên Guest.
- Chạy một project desktop, workers=1, retries=0. Browser request guard chặn model
  ngoài allowlist, câu hỏi khác, duplicate provider hoặc request chat thứ ba.
  Test kết thúc reset đúng capability Guest do test tạo, không reset dữ liệu khác.

### Quan sát thực tế và mức kết luận

**Browser harness 1 PASS, 39.8s**, cả hai response HTTP 200, error=null, route SQL,
SQL chứa INNER JOIN, rows.length=3, sources=[], requested_model/used_model đúng
provider, fallback_used=false. UI hiển thị hai attribution Knowledge/Gemini.
Điều này xác nhận **cả hai JOIN đã chạy qua UI và trả kết quả**, không UNSUPPORTED
trong hai lượt đã duyệt. Không suy rộng sang mọi câu hỏi hoặc Google-authenticated
workspace; đây là Guest + dữ liệu giả.

- Knowledge: ảnh UI giữ đầy đủ ba sinh viên, tổng 20.00 / 0.00 / NULL và số lần
  2 / 1 / 2, khớp PostgreSQL oracle. Giữ zero khác NULL, không bịa tổng cho Chi.
- Gemini: HTTP/route/INNER JOIN/3 rows/attribution/no-fallback được browser asserts
  kiểm tra và PASS. **Đối chiếu từng số liệu và grounded answer với oracle CHƯA
  ĐƯỢC CHỐT** do thiếu bằng chứng giữ lại đầy đủ, mô tả bên dưới. Không gọi đây là
  full numeric-oracle acceptance PASS.
- Không có raw SqlDraft để biết normalization có thực sự được dùng trong lượt
  live hay không. Chỉ biết final SQL đã qua validator/executor từ successful SQL
  response. Không tự gán draft/aggregate subtype cho các lỗi cũ.

### Thiếu sót thu bằng chứng — không tiêu thêm ngân sách để bù

Lần chạy đầu dùng `testInfo.attach({body: JSON})` với reporter=line. Playwright
lưu body trong report event memory, không tự ghi JSON thành file với reporter
này; sau khi test kết thúc chỉ còn hai PNG. Ảnh Knowledge đủ nội dung, ảnh Gemini
bị cắt phần cuối vì message list là scroll container dù screenshot fullPage.
Do đó response rows từng ô và câu trả lời Gemini đầy đủ không còn bằng chứng
để đối chiếu lại. Không giả vờ raw response đã được lưu, không dùng ảnh Knowledge
để thay cho kết quả Gemini, không gửi probe thứ ba.

Private evidence directory:
`C:\Work\ShopQuery-Backups\live-join-providers-20261020-0624\join-providers-live-two-ap-a6cc2-tions-one-per-live-provider-desktop-1440`

Đã sửa riêng collector/test cho **lần được duyệt mới trong tương lai**: bắt buộc
JSON reporter output trong private evidence dir, assert actual numeric rows với
oracle, scroll tới answer/table trước screenshot. Lint/typecheck PASS; chạy test
với approval flag OFF **1 SKIP**, không gửi thêm request provider. Các assertions
mới **chưa chạy live**, không tính hồi tố là bằng chứng cho hai lượt vừa xong.
Khi có approval mới, CLI phải dùng `--reporter=line,json` và
PLAYWRIGHT_JSON_OUTPUT_FILE ở thư mục private mới; không tái sử dụng output dir.

### Ngân sách và trạng thái

- **2/2 logical chat probes** đã dùng; mỗi successful SQL pipeline đi qua router,
  SqlDraft và grounded answer, tương ứng **6 logical gateway generation stages**.
  Không chủ động gửi lại câu hỏi, không thêm application retry/repair/fallback.
- **0 embedding calls**: chỉ hai bảng, zero document/chunks, Guest pipeline không
  dựng embedder/RAG. Không Knowledge/Gemini Hybrid live.
- Gemini SDK attempts=3, Knowledge transport attempts=1 giữ nguyên; Knowledge còn
  structured parsing loop hiện hữu. Không instrument transport trong production
  worker nên **số HTTP requests/thử lại nội bộ chưa đo được**; không khẳng định
  sáu HTTP requests hoặc không có SDK retries.
- API/web/DB giữ nguyên containers 5109e082c44a / d33081dc2211 / 511c4f5aaccc,
  không thay volumes, OAuth, providers hoặc dữ liệu persistent. Không gọi API chat
  khác. Không commit/push/CI mới. Production suite 829/66/105 ở mục T vẫn là kết
  quả trước lượt live, không nói rằng đã chạy lại full suite ở lượt U.

Kết luận: **JOIN thật qua UI đạt cho cả hai provider trong fixture này; Knowledge
answer đối chiếu oracle đạt; Gemini numeric acceptance còn thiếu bằng chứng.**
Đã dừng sau đúng hai lượt được duyệt. Không tuyên bố toàn hệ thống hoặc mọi JOIN
đã chính xác hoàn toàn.

## V. Mở rộng an toàn tối đa ba bảng — offline, 2026-10-20

Người dùng yêu cầu hỗ trợ JOIN nhiều hơn hai bảng. Đã chốt phạm vi triển khai
đầu tiên **tối đa ba bảng, hai approved edges**, không mở JOIN tùy ý. Đọc lại
AGENTS.md, giữ toàn bộ dirty diff từ các lượt R–U, không commit/push tự động.
Tài liệu docs/safe_join_v1.md được kiểm tra nhưng không còn trong working tree;
đối chiếu code, báo cáo hiện hành và PostgreSQL official references thay vì
giả định nội dung file đó. Không gọi provider live trong lượt V.

### Chính sách và lý do không fan-out

Chấp nhận đúng ba bindings khác nhau, hai INNER JOIN, mỗi ON là một equality
đúng approved key pair. Tập approved edges giữa ba bảng phải đúng hai cạnh,
không khóa/chiều/path mơ hồ. Đồ thị có duy nhất một root, đi theo cạnh đã kiểm
chứng source→unique target từ root tới mọi bảng: chain F→D1→D2 hoặc star
F→D1 và F→D2. Intermediate D1 không được dùng làm fact để tính SUM/AVG/COUNT.
Mỗi cạnh N:1/1:1 đã full-data verified nên thêm dimension không nhân bản root
fact rows. Hai fact cùng đi vào một dimension, cycle/disconnected/triangle,
wrong key, ON thêm AND/OR, self/outer/CROSS/USING và >=4 bảng đều fail closed.

Tham khảo:
[PostgreSQL JOIN cardinality](https://www.postgresql.org/docs/17/queries-table-expressions.html),
[unique/foreign keys](https://www.postgresql.org/docs/17/ddl-constraints.html),
[COUNT/SUM/AVG NULL semantics](https://www.postgresql.org/docs/17/functions-aggregate.html).
PostgreSQL counterexample riêng cho hai fact qua shared dimension cho SUM=60
trong khi tổng root thật=30; policy trả join_graph trước execution. Không có
heuristic đổi grain hoặc repair SQL để vượt từ chối.

### Source thay đổi trong lượt V

- `text_to_sql/join_policy.py`: tách dùng chung binding/equality/aggregate checks,
  thêm tree resolver ba bảng; aggregate vẫn dùng root fact do metadata quyết định.
  Chấp nhận các thứ tự INNER JOIN tương đương chỉ sau khi ON kết nối đúng binding
  đã xuất hiện (không sửa forward reference). Canonicalize về root→dimensions,
  giữ aliases, filters, projections và exact keys; validator chạy lại column/
  function/table checks. Two-table direction/key/aggregate behavior giữ regression.
- `validator.py`: ValidatedSql bổ sung relationship_ids tuple cho hai cạnh; giữ
  relationship_id cũ cho single-edge để tương thích. Không serialize dữ liệu này
  ra API hoặc tin vào relationship IDs từ client/model. SELECT-only, readonly,
  timeout và result cap giữ nguyên.
- `datasets/relationship_repository.py`: owner-locked execution guard kiểm tra
  tồn tại/revision/statistics/metadata của **cả hai cạnh trong cùng transaction**;
  FOR SHARE workspace giữ xuyên suốt executor, chặn delete/update qua FOR UPDATE.
  Không chỉ kiểm tra cạnh đầu; duplicate IDs, thiếu expected edge, >2 IDs bị chặn.
- `dependencies.py`, `guest/pipeline.py`: giới hạn 3 nếu có >=2 approved edges,
  nhưng resolver vẫn quyết định thực tế có cây an toàn; không cấp quyền chỉ dựa
  vào số lượng. Guest TEMP được dựng từ immutable snapshot của phiên, revision
  records được kiểm tra trước request, không có dữ liệu tài khoản khác.
- `datasets/context.py`: router/generator nhận thông tin root và physical FROM/JOIN
  fragment cây an toàn (tối đa ba ví dụ cây để tránh context phình), hướng dẫn
  aggregate chỉ root, single-table khi đủ. Không thay framework/model/gate/quota.
- UI Liên kết bảng và README mô tả đúng giới hạn 3 bảng/2 cạnh, không có migration
  mới hoặc metadata schema change. Tự kiểm chứng upload từ T giữ nguyên, có thể
  phát hiện cạnh thứ hai khi thêm bảng thứ ba.

### Kiểm thử offline

- Trước implementation: **10 positive tests FAIL** vì policy cũ chỉ cho hai bảng.
  Sau sửa targeted 3-table + 2-table unit **123 PASS**. Một negative test ban đầu
  thay alias không khớp chuỗi nên không thực sự làm SQL sai; sửa fixture mutation
  để tạo duplicate alias đúng, không nới production assertions.
- Main targeted group (mới + two-table/security/API/history/auto): **315 PASS**,
  82.17s. Full backend fresh DB shopquery_test_three_acceptance trong container
  tmpfs test ID 682e6264b33a, port 15437: **904 PASS, 16 live deselected, 0 FAIL**,
  215.34s. Tăng 75 cases so với 829: 40 unit + 35 PG.
- Ba bảng chain: bốn thứ tự SQL, hai fake model selections, root SUM/AVG/count
  khớp independent fact-only oracle (không JOIN), chính xác Decimal lớn, zero,
  all-NULL, empty matched set, BIGINT ngoài browser-safe integer. Star có hai
  thứ tự với PostgreSQL thật. COUNT fact join key vẫn canonicalize hẹp và an toàn.
- Cả hai edges lần lượt delete/stale đều block guard/executor/answer. Concurrent
  deletion mỗi cạnh chờ FOR SHARE giải phóng. Foreign owner hoặc third table từ
  workspace khác không tới executor. Wrong keys, aliases, ON predicates, SQL
  ghi dữ liệu, dimension measures, COUNT nullable không an toàn vẫn bị chặn.
- Real authenticated test sessions trên database cô lập: upload HTTP/CSRF/owner,
  tự tạo hai automatic relations, SQL/RAG/Hybrid cho hai model selections bằng
  fake gateways, SQL thực thi thật và reload history giữ response. Không giả là
  Google UI live. Guest RAM/TEMP cùng ba pipeline/two model selections đạt, không
  thay đổi persistent fingerprints trong test. Zero live generation/embedding.
- Ruff PASS, diff check PASS; frontend lint/typecheck/build PASS, **66 Vitest PASS**.
  Full Playwright mock suite **105 PASS**, 3.6 phút, năm viewport. Không gọi chat
  tới provider thật trong bất kỳ test nào của lượt V.

Phần V chưa nghiệm thu Knowledge/Gemini **live ba bảng**; kết quả live hai bảng
ở U không dùng làm bằng chứng ba bảng. Không yêu cầu/call live khi chưa có ngân
sách mới. Main schema/volume/OAuth/model/provider gates và dữ liệu hiện có giữ nguyên.

### Triển khai local và smoke sau khi tiếp tục lượt bị ngắt

- Sau khi user yêu cầu tiếp tục, chỉ nhận kết quả các tiến trình còn chạy, không
  chạy lại full suite vào cùng DB fixed-name. Full backend 904 và UI 105 đều exit 0.
  Ruff format loại bỏ newline EOF thừa ở context.py; Ruff và git diff --check PASS.
- Preflight lại đúng ba Compose files compose.yaml + .env.compose-ui.yaml +
  .env.join-v1.yaml. API environment khớp toàn bộ, main volume đúng
  shopquery-ai_postgres_auth_20261019, JOIN flag true. Không in secret hoặc đọc
  cookies/tokens của người dùng. Snapshot fingerprints lấy ngay trước deployment.
- Build/recreate **chỉ api và web**, `up --no-deps --wait`. Không recreate db,
  migrate, backup/restore, seed hoặc chỉnh database. Warning Compose về label volume
  cũ được giữ nguyên; không xóa volume/container hay đổi cấu hình để giấu warning.
- API mới `84a03be15ff502c8ce981f20f08e7ff049d326db9e76c5924bf0a07a84ca29f4`,
  web `a27d03924b652455aecbc3157e62e418f47619d2ad3bcf6b01942ebe66cb80a6`.
  DB vẫn `511c4f5aacccd1ac42261aaa2a7173ae40c5c5e3aa673bb4898d988a8206a3c8`.
  Cả ba healthy; GET /api/health qua 8080 ok. **70/70 Python hashes khớp source**.
  Runtime environment giữ nguyên: JOIN=true, provider gate=true, Guest AI=true,
  Gemini gemini-3.5-flash-lite, fallback=false. Không thay OAuth/quota/models.
- Runtime process smoke dùng source trong container mới, FakeGateway được truyền
  trực tiếp (không monkeypatch service đang phục vụ), chỉ ba CSV synthetic và
  PostgreSQL TEMP thật. Detector cho hai automatic edges; pipeline router→draft→
  validator→executor→grounding trả C1=20.00/count3 và C2=NULL/count1. Dimension-first
  draft canonicalize về root payments; hai INNER JOIN và COUNT key đúng. Không ghi
  tệp/chat vào DB persistent hoặc gọi provider; TEMP đóng khi connection kết thúc.
- UI thật 8080 `relationships-live.spec.ts`, desktop-1440 + mobile-390:
  **4 PASS, 1.9 phút**. Hai lifecycle cases cũ giữ preview/confirm/delete và security;
  hai cases mới upload courses/students/payments bằng giao diện, response import
  200, tự tạo students→courses và payments→students, origin automatic, confirmed
  false, valid/orphan0. UI mô tả tối đa ba bảng/hai cạnh. Không gửi /api/guest/chat,
  không giả là UI đã chạy câu hỏi AI. Chỉ reset các capability Guest test tự tạo.
  Đã xem ảnh desktop của màn hình ba bảng; Google authenticated UI positive vẫn
  NOT RUN, được phủ bởi isolated real session/CSRF/API/history tests đã nêu.
- Exact row counts và SHA-256 của **22 bảng business/upload/relationship/chat**
  trong snapshot trước deployment và sau toàn smoke đều khớp, bao gồm owner fields.
  Đây là số bảng tại cửa sổ V, không so với snapshot cũ ở T/U hoặc giả mọi thay đổi
  người dùng giữa các lượt đều do deployment. Không hash/xuất session secrets;
  không bao gồm operational rate/lease counters có thể thay đổi khi smoke.

**Kết luận V:** hỗ trợ tối đa ba bảng an toàn đã được đưa lên local 8080, đạt
offline + runtime PostgreSQL + UI upload/relationship smoke. Chưa nghiệm thu
live AI ba bảng, không dùng kết quả hai bảng ở U để tuyên bố điều đó. Không thay
đổi framework/model/architecture, không mở JOIN nhiều fact/4+ bảng. Không commit,
push hoặc chạy CI mới; HEAD vẫn 7e444c231a9162acf789266ea72280f73d4e95cf, image
được build từ working tree đã test, giữ nguyên dirty changes trước lượt này.
Tổng live generation **0**, embedding **0** trong toàn bộ V.

## W. Nghiệm thu live JOIN ba bảng và bàn giao Git — 2026-10-20

### Phạm vi và cách chạy

Người dùng phê duyệt chạy JOIN ba bảng trên UI 8080 với cả Knowledge và Gemini,
đối chiếu PostgreSQL rồi commit/push toàn bộ thay đổi liên quan. Chỉ chạy một
câu hỏi mỗi provider, không gọi thêm Hybrid, không dùng dữ liệu người dùng thật.
Playwright dùng context Guest mới (không cookies/storage state có sẵn), upload
CSV và gửi câu hỏi bằng giao diện thật. Không dùng session Google giả hoặc lấy
cookie/token của tài khoản. Sau kiểm thử chỉ reset capability Guest do test tạo.

- `courses`: C1/SQL, C2/RAG, C3/Math.
- `students`: S1/An/C1, S2/Binh/C1, S3/Chi/C2, S4/Dung/C2, S5/Em/C3.
- `payments`: S1 có 20.00 và 0.00; S2 có 0.00; S3 và S4 mỗi người một
  payment NULL; S5 có 12.50 và 0.00. Tổng cộng bảy payment.
- Ba lần import đều HTTP 200. Hai quan hệ tự kiểm chứng `payments.student_id →
  students.student_id` và `students.course_id → courses.course_id`: many-to-one,
  valid, origin automatic, confirmed false, orphan_rows 0. Không cần xác nhận tay.
- Câu hỏi duy nhất, dùng nguyên văn cho cả hai model: “Cho biết tên khóa học,
  tổng tiền đã thanh toán và số lần thanh toán của từng khóa học, kết hợp payments,
  students và courses.”

Oracle chạy PostgreSQL thật trong database test cô lập
`shopquery_test_three_acceptance`, container tmpfs `682e6264b33a`, port 15437.
Dùng VALUES fact-only và mapping khóa synthetic đã biết để GROUP BY khóa học,
không sao chép JOIN của model làm oracle. Kết quả không phụ thuộc thứ tự rows:

| Khóa học | PostgreSQL SUM / COUNT(*) | Knowledge | Gemini |
| --- | --- | --- | --- |
| Math | 12.50 / 2 | 12.50 / 2 | 12.50 / 2 |
| RAG | NULL / 2 | NULL / 2 | NULL / 2 |
| SQL | 20.00 / 3 | 20.00 / 3 | 20.00 / 3 |

### Kết quả live và bằng chứng

`join-providers-live.spec.ts` chạy desktop-1440, workers=1, retries=0:
**1 PASS, 47.2 giây**, bắt đầu 2026-10-20T06:58:23.023Z (13:58:23 giờ Việt Nam).
Đây là một test gồm hai logical chat probes, không phải hai lượt thử mỗi model.

- Cả hai response HTTP 200, route SQL, error null, requested_model = used_model
  đúng model được chọn, fallback_used false, sources rỗng, ba rows chính xác.
- SQL thực thi của cả hai chỉ chứa `pg_temp.table_3` (payments), `table_2`
  (students), `table_1` (courses), đúng hai INNER JOIN và hai equality khóa đã
  kiểm chứng. SUM lấy amount_paid của payments; COUNT(*) đếm payment, không đếm
  học viên. SQL đi qua validator và execution guard của pipeline thật.
- Knowledge: GROUP BY course_title. Gemini: GROUP BY course_id, course_title.
  Tên khóa học trong fixture duy nhất nên cả hai đúng oracle. Chưa kiểm chứng
  live trường hợp các khóa học khác ID nhưng trùng tên; không suy rộng kết quả
  này thành bảo đảm mọi entity grain. Cả hai SQL đã ở thứ tự fact-first; lượt
  này không chứng minh live AST canonicalization cho draft đảo chiều.
- Đã lưu toàn bộ response JSON, SQL/rows, model provenance, visible answer text,
  ảnh nguyên câu trả lời và ảnh bảng kết quả; đã đọc cả hai ảnh trả lời. Knowledge
  và Gemini đều nêu đúng ba tổng, ba số lần và giữ nhóm RAG có tổng NULL, không
  đổi NULL thành 0 hoặc bỏ payment 0. Decimal được truyền dưới dạng chuỗi.
- Evidence private ngoài repository:
  `C:\Work\ShopQuery-Backups\live-join-providers-three-20261020-final\report.json`
  và thư mục `artifacts` cùng cấp. Không commit evidence, credentials, Guest
  capability, raw production prompts hoặc dữ liệu thật. JSON attachment chỉ
  giữ ChatResponse synthetic, không lưu toàn bộ session response.
- Ngân sách đã dùng: **2 logical chat probes, 6 logical generation stages
  (router/draft/answer mỗi model), 0 embedding**. Không có chat retry do harness,
  không probe thứ ba. SDK/structured-output retry hiện hữu không bị đổi;
  transport HTTP count không instrument nên không khẳng định chỉ có sáu HTTP
  requests hoặc SDK không retry.

### Regression, an toàn và giới hạn bàn giao

- Production source không đổi sau kiểm thử V: **904 backend PASS**, 16 live
  deselected; Ruff PASS; frontend lint/typecheck/build PASS, **66 Vitest PASS**,
  **105 mock UI PASS**, **4 real UI upload/relationship smoke PASS**. Các kiểm
  thử owner/workspace, CSRF, stale/revoked từng edge, wrong key, dimension SUM,
  DML, ambiguous/fan-out graph và bốn bảng vẫn được giữ nguyên (chi tiết V).
- Lượt W cập nhật live harness để lưu đủ bằng chứng và hỗ trợ ba bảng; lint và
  typecheck frontend, 66 Vitest, Ruff và diff check chạy lại PASS trước bàn giao.
  Unit backend chạy lại với flag mặc định như CI: **551 PASS, 369 deselected**.
  Lần chạy đầu kế thừa JOIN=true từ cấu hình local có 550 PASS/1 FAIL: mock dataset
  của `test_dataset_list_detail_and_scoped_chat` không có owner/repository quan hệ,
  nên context fail closed khi bật JOIN. Chạy với SQL_JOIN_V1_ENABLED=false trong
  riêng tiến trình pytest đạt; không sửa `.env` hoặc hạ kiểm tra owner ở production.
  Các tests JOIN bật flag rõ ràng vẫn chạy và giữ security assertions như V.
- Không migration, không rebuild/recreate thêm service, không sửa main database,
  volume, OAuth, model, fallback, gates hoặc quota. Ba services main giữ healthy;
  live Guest xử lý synthetic trong RAM/PostgreSQL TEMP, không tạo dataset tài khoản.
- Google authenticated UI ba bảng: **NOT RUN** trong lượt W. Isolated authenticated
  API/session/history coverage ở V không được coi là Google UI live acceptance.
- Commit bàn giao gồm implementation, tests và docs liên quan từ R đến W đã
  review; loại trừ `.env`, secrets, private evidence, caches và dependencies.
  SHA, push và CI đúng SHA sẽ được báo riêng sau thao tác Git, không lấy CI cũ
  của 7e444c2 làm bằng chứng cho working tree mới.

**Kết luận W:** JOIN ba bảng synthetic trên Guest UI 8080 **PASS với cả Knowledge
và Gemini**, kết quả và grounded answer khớp PostgreSQL. Tự kiểm chứng hai quan hệ
khi upload PASS. Chỉ nghiệm thu fixture/câu hỏi này; không cam kết JOIN tùy ý,
mọi câu hỏi hoặc mọi trường hợp dữ liệu đều chính xác.
