# Text-to-SQL và JOIN — nghiệm thu độ tin cậy, 20/10/2026

> Mục A–M ghi kết quả lượt baseline `eeaffd4`. Bản sửa offline mới cho JOIN đảo
> thứ tự được ghi ở mục N; chưa gọi provider hoặc triển khai bản sửa đó lên main.

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
