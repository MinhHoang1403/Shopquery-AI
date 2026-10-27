# Quy tắc phát triển ShopQuery AI

## Phạm vi và nguồn chính

- Một source chính tại `C:\Work\ShopQuery AI`, repository
  `MinhHoang1403/Shopquery-AI`, branch chính `main`.
- Một deployment ShopQuery AI chính tại `http://127.0.0.1:8080`, Compose project
  `shopquery-ai`. Không tạo bản sao source hoặc application stack để thử nghiệm.
- Trước khi sửa: đọc AGENTS.md áp dụng, README và tài liệu liên quan; kiểm tra HEAD,
  working tree, origin/main, source/image/config đang chạy. Đối chiếu trạng thái
  hiện hành trong `docs/deployment.md`, `docs/architecture_audit.md` và
  `docs/v2_final_acceptance.md`; không dùng kết luận lịch sử thay kết quả hiện tại.
- Không xóa, ghi đè, reset hoặc đưa thay đổi chưa commit của người khác vào commit.
  Thay đổi source được quản lý bằng Git; không tạo các thư mục source copy, backup
  hoặc nhiều phiên bản. GitHub không thay thế bản sao lưu dữ liệu, volumes/secrets.
- Quy tắc này là hướng dẫn phát triển lâu dài duy nhất ở gốc; không tạo bộ quy tắc
  trùng lặp. Yêu cầu hiện hành của operator quyết định phạm vi công việc.

## Chất lượng và đặt tên

- Code sạch, rõ ràng, dễ đọc/bảo trì; mỗi module có trách nhiệm cụ thể. Tên file,
  module, class, hàm và biến phản ánh chức năng; tách hàm lớn khi hợp lý.
- Python tuân thủ PEP 8, type hints phù hợp; TypeScript có types rõ ràng.
- Không lặp business logic, hardcode dữ liệu nghiệp vụ hoặc dùng magic numbers
  không có giải thích. Không tạo abstraction/framework nội bộ không cần thiết.
- Comment giải thích logic khó, điều kiện bảo mật/nghiệp vụ quan trọng và lý do
  xử lý không hiển nhiên. Docstring mô tả interface/thuật toán hoặc điều kiện
  đầu vào/đầu ra khi cần. Không comment máy móc từng dòng hoặc trái hành vi thực tế.
- Không dùng nhãn kế hoạch/trạng thái trong tên production code hay service/project
  mới: `v1`, `v2`, `v3`, `s1`, `s2`, `e3`, `freeze`, `frozen`, `final`, `temp`,
  `old`, `new`, `backup` hoặc nhãn giai đoạn/thử nghiệm tương tự. Dùng tên theo
  chức năng, chẳng hạn `observability.py`, `provider_usage.py`, `trace_context.py`.
- Không đổi tên file lịch sử ngoài phạm vi hoặc có thể phá deployment. Không đổi
  environment keys, schema names, protocol/API identifiers đã có hợp đồng tương
  thích chỉ để bỏ nhãn. Nhãn kế hoạch được dùng trong tài liệu/báo cáo khi cần.

## Nghiên cứu và bằng chứng

- Quyết định AI, thuật toán, công thức, dữ liệu, bảo mật và công nghệ quan trọng
  phải có căn cứ kiểm chứng. Ưu tiên tài liệu chính thức đúng phiên bản dependency,
  chuẩn kỹ thuật, nghiên cứu uy tín khi phù hợp, source/repository chính thức và
  thực nghiệm có thể tái hiện. Việc lập trình thường ngày không cần bài báo.
- Kiểm tra API/SDK và serialization thực tế; không suy từ tài liệu phiên bản khác.
  Không bịa công thức, benchmark, giá hoặc khả năng thư viện. Ghi rõ giả thuyết và
  UNKNOWN; không tuyên bố công nghệ hoạt động khi chưa có kiểm chứng phù hợp.
- Ưu tiên phương pháp đã được chứng minh, đơn giản, phù hợp quy mô và dễ bảo trì.

## Thực hiện nhiệm vụ và kiểm soát độ phức tạp

- Quy trình: yêu cầu → đọc source → nghiên cứu → chọn giải pháp → thực hiện →
  kiểm thử → commit/push → triển khai khi cần và được phép → kiểm chứng/báo cáo.
- Hiểu yêu cầu và source trước khi sửa; chỉ thực hiện đúng phạm vi. Không tự đổi
  mục tiêu, kiến trúc, model bắt buộc, provider hoặc mở rộng sang project khác.
- Không sửa module không liên quan, tạo nhiều giải pháp song song để thử, vá theo
  suy đoán, bỏ qua test thất bại hoặc chạy vòng sửa/retry LLM không có điểm dừng.
- Vấn đề ngoài phạm vi phải ghi nhận/báo cáo. Chỉ sửa ngay khi có rủi ro trực tiếp
  về correctness, bảo mật hoặc dữ liệu của chính nhiệm vụ đang làm.
- Ưu tiên ít thành phần/dependency/abstraction, cấu hình rõ, dễ test/rollback/nâng
  cấp, chi phí thấp. Không thêm database, queue, worker, cache, service hoặc logging
  system trùng lặp khi chưa có nhu cầu được chứng minh.
- Ngoại lệ rõ ràng: thành phần bắt buộc của công nghệ operator đã yêu cầu được
  phép, ví dụ Langfuse Web/Worker, PostgreSQL riêng, ClickHouse, Redis, MinIO.
  Không bỏ thành phần bắt buộc của kiến trúc chính thức để giảm số container.
- Không mở lại audit/cải tiến ngoài yêu cầu. Trạng thái đóng băng trước đó không
  cấm nhiệm vụ mới được operator phê duyệt; không dùng nhiệm vụ mới để đổi chatbot
  SQL/RAG/Hybrid logic đã nghiệm thu khi không có bằng chứng hoặc yêu cầu riêng.

## Source, kiểm thử và lời gọi provider

- Ưu tiên unit/integration tests hiện có, provider mocks, static analysis, CI và
  runtime health checks. Kiểm thử trực tiếp hạ tầng hiện có khi an toàn.
- Không tự tạo thêm PostgreSQL/API/Web test containers hoặc Compose sandbox nếu
  công cụ hiện tại/CI đủ kiểm chứng. Không đưa fixture vào production nếu không cần.
- Sau chỉnh sửa luôn chạy tests liên quan và negative/security regression phù hợp;
  kiểm source/image/config/runtime khi triển khai. Không chạy rộng hoặc lặp suite
  đã PASS khi source liên quan không đổi và không có failure/uncertainty mới.
- Không dùng provider thật nếu offline test đủ. Paid calls phải nằm trong dữ liệu,
  provider, quota/ngân sách và số attempts được duyệt cho nhiệm vụ hiện hành.
  Không dùng dư cửa sổ audit đã đóng, tự retry/repair/fallback hoặc gửi dữ liệu khác.
- Theo dõi usage cộng dồn trước dispatch; không reset theo batch. Giữ nguyên normal
  operation gate theo yêu cầu operator, phân biệt ngân sách agent với sử dụng thường.
- Không đánh đồng HTTP200, mocks, schema parsing hay compile với correctness live.
  Không biến UNKNOWN thành PASS, không chọn riêng các ca thành công hoặc che failure.

## Docker: vận hành và kiểm thử

- Được tạo containers/images phục vụ chức năng vận hành operator yêu cầu. Langfuse
  đủ sáu service chính thức là hệ thống vận hành hợp lệ, không phải test stack dư.
- Langfuse quản lý cùng repository, ưu tiên `ops/langfuse/`, Compose project riêng
  `shopquery-observability`, volumes và PostgreSQL riêng; không dùng main DB lưu trace.
  Không nhân bản ShopQuery AI hoặc kết nối main DB vào mạng Langfuse không cần thiết.
- Chỉ build service có source/build inputs thay đổi; không build cho docs/config-only.
  Dùng image ổn định pin version/digest có nguồn kiểm chứng, giữ rollback phù hợp.
- Trước pull/start công nghệ mới, kiểm RAM khả dụng, CPU, Docker/WSL memory, paging,
  disk/storage, ports và tải hiện hành so với yêu cầu chính thức. Không tự đổi cấu
  hình Windows/WSL/security policy, không ép tải khi làm mất ổn định ShopQuery AI.
  Không đủ tài nguyên thì dừng deployment với bằng chứng và phương án máy/VM riêng.
- Không tạo nhiều Compose projects/images thử nghiệm rồi để lại. Không chạm tài
  nguyên project khác, xóa image đang được containers tham chiếu hoặc dùng force.
- Sau triển khai kiểm kê exact containers/images/references; chỉ dọn image thừa
  thuộc phạm vi nhiệm vụ đã xác minh không dùng. Giữ images hiện hành, rollback và
  tất cả volumes dữ liệu. Không dọn cache khi chưa có nhu cầu.
- Không dùng `docker system prune -a`, `docker volume prune`, `docker compose down -v`
  trong dọn dẹp thông thường. Không coi các service phụ trợ Langfuse là rác.
- Chuyển runtime phải có immutable image/config, rollback, kiểm công việc đang chạy
  và thời điểm gián đoạn được operator duyệt theo deployment runbook. Không recreate
  main PostgreSQL để triển khai API/Web hoặc monitoring.

## GitHub và branches

- Thay đổi nhỏ, ít rủi ro, không có người sửa cùng vùng, có tests phù hợp được làm
  trên main. Tích hợp công nghệ mới, nhiều file hoặc rủi ro runtime dùng một branch
  ngắn hạn từ main sạch; ưu tiên prefix `codex/` trừ khi operator chỉ định tên khác.
- Với nhiệm vụ Langfuse: cập nhật/commit/push AGENTS.md lên origin/main và xác minh
  local/remote khớp trước khi bắt đầu tích hợp. Không tạo branch riêng cho mỗi service.
- Commit đúng nội dung, không gộp thay đổi ngoài phạm vi; push, CI, merge main sau
  khi đạt điều kiện, xác minh origin/main, xóa branch ngắn hạn khi không còn cần.
  Không force push main, reset hoặc xóa thay đổi người khác.
- Không commit secrets, `.env`, credentials, dữ liệu người dùng, raw logs, DB dumps,
  Docker volumes/data, cache, virtual environments, weights hoặc build artifacts
  không cần thiết. Dùng private config và template không có secret.
- Hoàn tất phải báo Git SHA, CI, push/merge status và working tree; phân biệt file
  untracked của operator được bảo toàn với thay đổi còn sót của nhiệm vụ.

## Bảo vệ dữ liệu và ứng dụng chính

- Không tự xóa/reset PostgreSQL, đổi main schema, xóa accounts/sessions/history/
  documents/vectors/relationships hoặc bulk rewrite attribution đã lưu.
- Không tự thay embedding/default model, bật fallback chưa nghiệm thu, vô hiệu hóa
  SQL guards hoặc nới security/resource limits. Giữ typed QueryPlan, approved N:1,
  fact/grouping grain, COUNT provenance, Decimal/NULL, owner/workspace scope,
  AST validation, read-only/timeout/row cap và evidence/conversation verification.
- Không giả login, trích session token hoặc gửi nội dung riêng tư sang provider/
  telemetry khi chưa được duyệt. Thay đổi có khả năng phá dữ liệu cần rollback và
  kiểm chứng riêng; GitHub không phải backup thay cho main data/private secrets.

## Quan sát hệ thống và Langfuse

- Tận dụng `backend/app/core/diagnostics.py`; không thay diagnostics hoặc tạo pipeline
  SQL/RAG/Hybrid mới. Instrumentation tối thiểu, tùy chọn, không đổi câu trả lời.
- Một correlation ID/root trace mỗi request, spans phản ánh đúng bước thực sự chạy.
  Mỗi generation/embedding call có observation riêng; không tạo span bước không chạy,
  duplicate spans/tokens hoặc gọi model chỉ để đo telemetry.
- Ghi provider/model/route, duration, usage SDK, safe error/reason, fallback,
  verification status và correlation conversation bằng định danh giả danh khi cần.
  Không log raw prompts/questions/documents/rows/SQL/parameters/vectors, email,
  keys, Google/session credentials hoặc private Knowledge URL. Masking phải có test;
  không bật auto-instrumentation ghi raw contents khi chưa xác minh privacy.
- Phân biệt measured/estimated/missing/cached tokens, failed-call consumption và
  fallback overhead. Thiếu usage là UNKNOWN, không phải0. Giá model dùng nguồn chính
  thức đúng model; không bịa giá Knowledge hoặc coi chi phí UNKNOWN là miễn phí.
- Langfuse phải fail-open: OFF/timeout/restart/SDK error/queue đầy không làm chatbot
  thất bại hoặc thay output; queue/resource bounded, export bất đồng bộ, không flush
  mỗi request hoặc gọi đồng bộ Langfuse trong critical path. Kiểm chứng các trạng thái.
- Dùng credentials ngẫu nhiên riêng, không in secret/log, không dùng default passwords.
  UI/endpoint cần thiết bind loopback; không public DB/Redis/ClickHouse. Chỉ nối API
  tới Langfuse Web qua network cần thiết, không dùng localhost container sai nghĩa.
- READY đòi hỏi services/worker/storage/readiness, login/dashboard, trace ingestion,
  usage/error/privacy/fail-open,8080/strict verifier/data integrity và GitHub đồng bộ.
  UI truy cập được hoặc mocks PASS chưa đủ. Live smoke chỉ trong phạm vi/quota mới.

## Ngôn ngữ và bàn giao

- Giải thích/báo cáo ưu tiên tiếng Việt, Việt hóa thuật ngữ dễ hiểu, giải nghĩa thuật
  ngữ chuyên ngành lần đầu khi cần; giữ nguyên tên API/class/package để đúng kỹ thuật.
- Nêu rõ nguyên nhân, bằng chứng, đã/chưa kiểm chứng; phân biệt offline, CI, live,
  production và giới hạn. Không báo PASS chỉ dựa kiểm thử mô phỏng.
- Bàn giao: thay đổi/files/lý do, số tests thực tế, CI, live/runtime/strict verifier,
  source/image/config, Git SHA/push/merge/working tree, containers/images/volumes/
  rollback/cleanup ảnh hưởng, lỗi/rủi ro và blocker còn lại. Không mở rộng scope để
  tăng số tests, không tuyên bố hoàn tất khi các điều kiện bắt buộc chưa đạt.
