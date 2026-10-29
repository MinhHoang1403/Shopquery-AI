# ShopQuery AI — Project closeout

**SHOPQUERY_CLOSED_WITH_LIMITATIONS** — ngừng phát triển ngày29/10/2026.
Ứng dụng localhost tiếp tục hoạt động; không triển khai rebuild, không archive repository.
Không còn nhiệm vụ phát triển lõi trong closeout. Không bảo đảm mọi câu hỏi đều đúng.

## A. Stable baseline

- Main trước cleaning: `b09ec4ebb21d63e2e11841243210bf23f6d54f26`.
- Main cuối: commit được annotated tag `shopquery-stable-closeout-2026-10-29` trỏ tới.
  Xác minh SHA bằng `git rev-parse shopquery-stable-closeout-2026-10-29^{commit}` và
  `git rev-parse HEAD origin/main`; không nhúng SHA tự tham chiếu vào chính commit.
- API application `4ab2c5a1cc115b95cbc9854d6dc65f75a95ae473`; Web application
  `de0572ebf7e946c3396c5693a9c5a3f27ab6a4ef`. Digests đầy đủ ở bảngDocker bên dưới.
- API/Web/DB và6Langfuse services healthy; health8080 HTTP200. Không rebuild/redeploy.
- Stable SQL/RAG/Hybrid, approved N:1, COUNT/Decimal/NULL, owner/auth/CSRF, persistence
  và legacy coverage/readers giữ nguyên. [Capabilities](capabilities.md) và
  [deployment/recovery](deployment.md) là tài liệu vận hành.
- Gemini default, Knowledge manual, fallbackOFF, gateON, GuestAIOFF, BGE OFF giữ nguyên.

Giới hạn: upstream Knowledge permissions/timeout và model semantics không có guarantee;
JOIN tối đa3bảng/2edges N:1, không many-to-many/outer joins hoặc rules engine tổng quát.
Langfuse retention/embedding usage/cost có giới hạn và backup restore drill chưa nghiệm thu.
Existing sessions được bảo toàn; không chạy fresh Google login hay paid smoke khi closeout.

## B. Unaccepted rebuild archive

- Candidate `26168c1b3d1eda32670334a41b188523af0e29ac`.
- Annotated tag `shopquery-core-unaccepted-2026-10-29` đã push/peel đúng candidate.
- [PR5](https://github.com/MinhHoang1403/Shopquery-AI/pull/5) CLOSED, không merge.
- Candidate CI40832700750 PASS không thay semantic acceptance: Knowledge p17 TEXT3
  khác goldquận3, không mapping nguồn đã xác minh; các gate live còn thiếu.
- Code/tests/docs/fixtures và f04922a được giữ trong Git history của tag; không cherry-pick
  vào stable main. Ledger/captured synthetic evidence local được giữ private, không reset.
- Xem không đổi checkout: `git show shopquery-core-unaccepted-2026-10-29:docs/core_acceptance.md`.
  Nếu cần phục hồi source sau này, bắt đầu từ tag trên một branch được operator cho phép;
  không dùng tag làm release hoặc cấu hình deploy.

## C. Source/tests cleaning

Đã kiểm kê/đọc tracked tree355files; AST88production Python modules và123test Python files.
Đối chiếu imports, dynamic lookup sites, CLI, CI, Compose, maintenance/recovery và docs refs.
Đây là audit deletion candidates, không phải proof rằng mọi source line không có lỗi.

| Thư mục/đối tượng | Quyết định | Bằng chứng và hành động |
|---|---|---|
| backend/app | KEEP/REQUIRED_COMPATIBILITY |88modules; stable router/planner/coverage vẫn được gọi; không thay core |
| backend/scripts, backend/sql | KEEP | CLI, migrations/setup/seed/recovery/test guards; không tự migrate main |
| backend/tests | KEEP |123Python files,114files có test,596test functions; không có exact AST duplicates kể cả bỏ tên function |
| frontend/src, frontend/e2e/config | KEEP | API/render/security tests và opt-in live entrypoints khác mock E2E; không gộp boundary khác nhau |
| scripts, .github | KEEP | Startup/release/test/verifier/maintenance tools còn tham chiếu |
| data, infrastructure, ops | KEEP | Runtime/build/seed/regression, Nginx và6service Langfuse; không có dữ liệu nào bị xóa |
| root Compose/.env templates/private configs/.vscode | KEEP | Dev/GPU/legacy identifiers còn scripts/tests/recovery consumers; private files không commit |
| docs/architecture_audit.md | OBSOLETE history at HEAD | Rút còn invariants/limitations + Git permalink, giữ tên để không phá AGENTS/runbook |
| docs/correctness_review.md | KEEP current proof | Giữ current acceptance/root causes/oracles; bỏ nhật ký trước correction trùng/lỗi thời, có permalink |
| docs/observability_acceptance.md | KEEP bounded proof | Giữ6trace scorecard/privacy/usage/backup limitations; bỏ nhật ký triển khai trùng |
| docs/operational_handoff.md | OBSOLETE | Xóa handoff27/10 đã bị thay, chuyển links sang báo cáo này; Git giữ lịch sử |
| docs/source_inventory.json, core_rebuild.md, semantic candidate modules/tests | ARCHIVED | Không thuộc stable main; toàn bộ giữ trong unaccepted tag |
| .pytest_cache/.ruff_cache/__pycache__/dist | KEPT_POLICY_BLOCKED | Đã kiểm kê; automatic approval từ chối lệnh cleanup trước thực thi, không thử bypass |

Không xóa production/test/dependency vì không thấy static import. Main ASGI entrypoint và
database migration/seed modules được CLI/tests dùng, dù không có incoming imports trong app.
Các nhóm SQL/COUNT/JOIN, Router, RAG/Hybrid, conversation, API/auth/security, PostgreSQL,
provider mocks, observability và migration fixtures giữ nguyên asserted invariants/discovery.
Không chuyển expected values, xfail hoặc xóa negative/oracle tests để làm xanh kết quả.
Stable test inventory trước/sau:2417collected,123Python files/596functions, không đổi.
Tracked files trước/sau:355/355 (bỏ1handoff, thêm1closeout); production dependencies không đổi.

## D. Verification và known local failure

- Ruff app/scripts/tests PASS; frontend lint/typecheck/88tests/14files/build PASS.
- Local Windows backend:1522PASS,1FAIL,894deselected.
  `tests/test_guest.py::test_disposable_parser_success_timeout_and_crash_cleanup` nhận504
  thay vì502 ở crashed worker; một targeted rerun vẫnFAIL. Không sửa timeout/production,
  không bỏ test. Chưa chứng minh nguyên nhân Windows scheduling/spawn/security cụ thể.
- Full isolated PostgreSQL, backend/security regressions, frontend/mockE2E, Compose và
  maintenance checks được xác minh qua exact-head closeout CI, không dùng mainDB test.
  [CI của closeout branch](https://github.com/MinhHoang1403/Shopquery-AI/actions?query=branch%3Acodex%2Fproject-closeout).
  SHA/runURL cuối còn được ghi ở merged PR và annotation stable tag; không tính mocks là livePASS.
- Python typing: project không cấu hình mypy/pyright; không cài thêm checker khi đóng dự án.
- Không paid generation/embedding trong closeout; ledger rebuild giữ31/120generation,0query/0document.

Strict byte verifier FAIL ở3files: `ai/gemini.py`, `api/routes.py`, `rag/pipeline.py`,
chỉ khácCRLF/LF. Đã so toàn bộ88module sau chuẩn hóa LF:equal; Git build-input diff
so OCI revisions cũng equal, effective env/image/DB config không drift. Không sửa guard
để báoPASS, không sửa source/runtime. Raw manifest image vẫn
`3054d4cad4f1d1a3e03746f67fa4fde1f88895f468ace4f923106b2d9e4bc123`.
Đây là hạn chế portability của byte verifier, không phải code drift chưa giải thích.

## E. GitHub và khôi phục

Cleaning branch từ stable main, không gộp candidate. Closeout PR chỉ docs; merge sau CI.
Annotated stable tag trỏ main cuối; candidate tag trỏ26168c1. Feature branches chỉ xóa
sau khi xác minh remote references; main/origin/main được đối chiếu cuối, working tree sạch.
Không force push, rewrite history, xóa workspace hoặc GitHub archive.
Các tài liệu lịch sử dài vẫn đọc được tại
[stable b09ec4e](https://github.com/MinhHoang1403/Shopquery-AI/tree/b09ec4ebb21d63e2e11841243210bf23f6d54f26/docs).

## F. Docker/data

Kiểm kê61images/28containers toàn máy, chỉ tác động14ShopQuery app images.
Giữ2ACTIVE+2ROLLBACK; xóa10OBSOLETE không container (kể cả stopped) tham chiếu,
không có active Compose reference, revisions còn Git history.47images khác không tác động.

| Image ID/digest (sha256) | Source | Trạng thái | Bytes từ inspect |
|---|---|---|---|
| `2d27fba187bb8703ebefbb214931933576767a52d7a32855b05d4a25c3bf5d98` | `4ab2c5a` | ACTIVE | 118263960 |
| `b2188879d84d6069f66dd73a13210bb810d269a23366aa77d6d4fd6eb307a7b3` | `de0572e` | ACTIVE | 26475992 |
| `4a80e003aeb9ea008afcc5b557084db105ad4507130695a5b7fa1d378bc586e7` | `e2722da` | ROLLBACK | 118263318 |
| `5675513a90921b713413b8dda5391a9c0dfb2b24acbdb60edf4b9f96446f14b0` | `29bb788` | DELETED | 118262051 |
| `9b735b38e62a19f9e1f8426b10c1774bedc30ae07d23cbda6cae75db1237a23f` | `b75a844` | ROLLBACK | 26475598 |
| `d8ad8aa5e3425b803bcec9c61a5e84dd5e950a2e07dc978d70c64d7c33dcbbb2` | `3fe4cc2` | DELETED | 118255221 |
| `52701da8a2d0fb40f5825647ef955936148271cad47c0838dcbaeaca41983285` | `8a2c6aa` | DELETED | 118253870 |
| `069e7f67fb409ac3a587c6327104f509bf3182ca2d410e281f2f3cf90818c599` | `a67242d` | DELETED | 3222963103 |
| `67a891b04fcd0f0a9d6e6e7eea6bf6bccc2b3f0e72bec23be5a8c57f871d9a5a` | `f6f44ae` | DELETED | 3222962184 |
| `ae181335b61aa738f6b0b1c2c1c450fe46a5ba26b4688d5c294d541975696a58` | `02d5cbb` | DELETED | 26475582 |
| `03f83efc5f4b46452f20baa7a82a16c7289662cbdffa701b8396ac4733dd0fb3` | `08d71b9` | DELETED | 26475582 |
| `2be8945280dbb710f287209ecead2731a9b81b96050c5ed65ef5a3b9ecbceb5d` | `08d71b9` | DELETED | 3222929711 |
| `127da3e8b7b1d1885bd3a8457dbf78ae1935d3add141510a2037362ff5fb30d0` | `fd1f510` | DELETED | 26474830 |
| `6994abd7145482c2e83a95ea09e8cb2dd872ecc550a534f5109ad10b204c1b3e` | `0656765` | DELETED | 3222927866 |

Repo/tag của từng hàng là `shopquery-ai-api:main-<full revision>` hoặc
`shopquery-ai-web:main-<full revision>`; RepoDigest cùng sha256 như bảng. ACTIVE dùng
2d27fba1(API)/b2188879(Web), ROLLBACK dùng4a80e003(API)/9b735b38(Web), không dùng candidate.
Rollback là cặp đã ghi trong runbook28/10, kiểm image/config/revision tồn tại; không
restart/deploy thử rollback chỉ để chứng minh khi closeout. Private configs lịch sử giữ
nguyên nhưng không được dùng tự động; runbook bỏ cam kết các images cũ còn tồn tại.

Docker image count61→51; Images accounting57.42GB→38.9GB, trong khi build cache vẫn
443entries/47.28GB và reclaimable cache2.795GB→21.33GB. **Không được gọi18.52GB là
disk vật lý đã giải phóng**: một phần accounting chuyển sang shared/build cache còn giữ.
Không cộng virtual/shared sizes; physical host/VHD reclaimed UNKNOWN. Không prune cache,
volumes/models, không compactWSL, không rmi-force hoặc xóa tài nguyên project khác.

Container count28/active13 và volume count34 không đổi. Main protected volume
`shopquery-ai_postgres_auth_20261019`, container511c4f5a vẫn giữ. Read-only trước/sau:
33table fingerprints (uploaded rows, documents/vectors, datasets/relationships, conversations/
messages) và schema hash bằng nhau;50sessions giữ nguyên số lượng. Không xuất token/
credentials hoặc raw rows. Fresh OAuth/session usability không retest; không có cutover.

## G. Final status

**SHOPQUERY_CLOSED_WITH_LIMITATIONS**: dừng phát triển, stable runtime được giữ; candidate
đã archive, production code/tests không đổi. Giữ local caches do policy block, công bố
Windows Guest-worker test failure và strict byte/EOL caveat; không tuyên bố hết mọi lỗi.
Không mở lại benchmark, không gọi model, không tiếp tục SemanticTask/ChatSAR trong repo này.
