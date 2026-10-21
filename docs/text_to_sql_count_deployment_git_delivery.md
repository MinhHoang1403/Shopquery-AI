# Semantic COUNT — local deployment and Git delivery

Ngày 21/10/2026, Asia/Ho_Chi_Minh. Workspace ShopQuery AI.

**DEPLOYED TO 8080 — GIT DELIVERY IN PROGRESS — LIVE HYBRID NOT VERIFIED.**

Báo cáo này là trạng thái deployment mới; các reports/handoff trước là checkpoints
lịch sử, không ghi đè kết quả cũ thành PASS. Không có production source patch thêm
trong lượt này. Phạm vi: API-only deployment đúng source đã kiểm thử và public Git
delivery. Không provider/embedding/live chat, business-data audit, migration/restore.

## A. Preflight và Docker before/after

Preflight khớp baseline được duyệt. Recreate API lúc khoảng **16:07:10 +07:00**;
API mới StartedAt **2026-10-21T09:07:13.83927839Z**.

| Service | Old ID | New ID | Image sau | Health |
|---|---|---|---|---|
| Web | 2af67d527f2e | 2af67d527f2e | sha256:5ca6e17125f12574cf8cdf4d030b6a0a209007e9469b264e94e6d98056090146 | healthy |
| API | fd62fc397a91 | 8a39b1cb69a0 | sha256:4bbf907c554099a7d542a53b10b5850b6bfc56d7ba1e9ebb499c696cc2c0151b | healthy |
| DB | 511c4f5aaccc | 511c4f5aaccc | sha256:137f044b0efe3d57f39b972b9b53641b1f2045b99d879e298bbf514a25787dcf | healthy |

API full ID mới:
`8a39b1cb69a0f89c49d6976996f89b29019abdc289bc805f58a25b7aa7b19f72`.
Image API cũ:
`sha256:1a96e048886281ff5d7742e21cb1374e2e88571556c769bcdad3b29990b36417`.

Web/DB full IDs, image IDs, health, StartedAt, RestartCount, mounts, ports,
networks và Compose labels được so exact trước/sau trong private operational
snapshot: không đổi. Chỉ API được recreate. Network vẫn shopquery-ai_backend;
API8001→8000, web8080→80, PG15432→5432 trên loopback.

Dùng đầy đủ ba files:
`compose.yaml + .env.compose-ui.yaml + .env.join-v1.yaml`.
DB label giữ hai files từ lúc tạo, JOIN override chỉ tác động API; không recreate
DB để sửa label. Merged Compose chỉ có db/api/web, không service test.

Active volume `shopquery-ai_postgres_auth_20261019` vẫn mount đúng data path;
archived `shopquery-ai_postgres_data` còn nguyên. Volume metadata trước/sau
khớp. Compose có warning archived volume không khớp active mapping và **left
untouched**; không làm theo gợi ý remove. Không prune/xóa tài nguyên khác.

## B. Source freeze, candidate và runtime integrity

Source app **không đổi** so snapshot 770 unit +682 PostgreSQL đã PASS. Manifest
tính đúng phương pháp của semantic redesign report: sorted relative POSIX paths,
mỗi dòng `path SPACE sha256(LF-normalized UTF8 text) LF`, hash toàn listing UTF8.
Empty module hash là SHA-256 empty bytes.

- Local tested/frozen manifest: `47b9d4083e13bf32d79c441681d344dcf3f88ea1e5c679604a8f0db1d7f59586`.
- Candidate manifest: cùng hash, **72/72** module khớp.
- Runtime sau deploy: cùng hash, **72/72**, không thiếu/import mismatch.
- Runtime trước deploy: 71 modules; theo chính phương pháp mới là
  `47aa7355c88cb96996209037998ff1cc6c497400f33e0c11c374e302a7ae3d50`.
  Không so với historical manifest dùng cách serialization khác.
- `text_to_sql/count_contract.py` tồn tại, hash
  `8a8b46f77862da95334f84afd93cbe95b953321dd22d89704eb38eaaa89f5c9c`.

Build dùng Dockerfile hiện hữu, `uv sync --frozen --no-dev`, dependency layer
cached; không đổi lockfile. Candidate chạy Python AST parse/compile tất cả modules,
import CountKind/CountMetric, SqlValidator, HybridPipeline và app.main thành công.
Hai ephemeral candidate-check containers dùng `--network none`, không env main/
mounts/server/lifespan startup, tự remove; không kết nối DB/provider.
**70 package versions** candidate/runtime khớp API cũ, không dependency drift.

## C. Configuration, quiescence và health

So toàn bộ API environment trong memory trước/sau; không xuất/lưu full environment
hoặc credentials. Digest cho sorted `key=value` joined bằng LF (không trailing LF)
trước/sau:
`5593c011af92e092eb2d7d4fdb59a01d4ad4b37137e63a452159e782090e236f`.
Khác method với historical JSON digest không là config drift.
Merged Compose/runtime **0 mismatch**, cả trước/sau.

Allowlisted checks: JOIN=true, default inetcloud-knowledge; Knowledge=knowledge;
Gemini=gemini-3.5-flash-lite; embedding=gemini-embedding-2/768; fallback=false;
provider-data gate/Guest AI/enabled=true. Gemini timeout30000ms/attempts3,
Knowledge timeout60s/attempts1 giữ nguyên. Quotas, OAuth và settings khác được
bảo vệ bằng full environment equality; không sửa .env/overrides hoặc secrets.
Hai database URLs chỉ kiểm host/port/database: **db:5432/shopquery**, không test DB.

Đã cảnh báo Guest RAM state mất qua API recreate. Hai lần operational quiescence
snapshot, gồm ngay trước recreate: **authenticated_active=0, guest_active=0**.
Chỉ đọc count resource_leases chưa hết hạn và resource_limits prefix Guest lease,
current_database; transaction READ ONLY, timeout3s, rollback. Không đọc key/user/
session/customer/history rows; không reset quota/lease. Đây không phải maintenance
lock chống mọi request mới hoặc bằng chứng Guest idle files không tồn tại;
graceful shutdown và cửa sổ quiescent được dùng như procedure đã duyệt.
Không hứa Guest RAM files/history tồn tại sau recreate.

Sau deploy: GET /api/health trực tiếp8001 và Nginx8080 đều HTTP200/status ok,
ba services healthy. Startup log chỉ có server/application startup complete,
không startup/import errors. Web DNS api resolve đúng IP API mới; nginx -t PASS.
Không quan sát502, **không reload/recreate/rebuild web**.

Không gọi /chat, upload, generation, embedding hoặc probes KH/GH.
**0 live chats /0 generation /0 embedding calls do agent trong task này.**
Không thay model/retry/fallback hoặc thêm raw SQL/prompt logging.

Không migration/seed/restore/re-ingest, không main business SELECT/fingerprints.
Operational health/volume identity không chứng minh toàn DB byte-for-byte bất biến
trước concurrent user writes. Không reset persistent Google sessions/datasets/
documents/vectors/history.

## D. Rollback protection và recovery procedure

Tag mới được tạo sau khi xác minh chưa tồn tại:
`shopquery-ai-api:rollback-pre-count-semantic-20261021`, trỏ đúng immutable API cũ
`sha256:1a96e048886281ff5d7742e21cb1374e2e88571556c769bcdad3b29990b36417`.
Đã kiểm lại sau deploy. Không ghi đè/xóa rollback tags hoặc images cũ.

Nếu cần recovery: trước hết xác minh lỗi và quyền rollback/quiescence; không tự
restore DB. Tạo approved private override (ngoài public repo):

```yaml
services:
  api:
    image: sha256:1a96e048886281ff5d7742e21cb1374e2e88571556c769bcdad3b29990b36417
```

Sau phê duyệt recovery, dùng đúng ba Compose files rồi override pinned image cuối:

```powershell
docker compose -p shopquery-ai -f compose.yaml -f .env.compose-ui.yaml -f .env.join-v1.yaml -f '<approved-rollback-override.yaml>' up -d --no-deps --no-build api
```

Kiểm old source manifest/health8001+8080/config/unchanged web+DB, chỉ reload Nginx
nếu chứng minh stale DNS. Không down -v, migration, restore, xóa metadata hoặc
reset data. Tắt JOIN flag không phải rollback database.
Procedure chuẩn bị, **KHÔNG rollback trong lượt này**.

## E. Regression baseline và Git/security delivery

Source freeze khớp nên không chạy lại full DB/frontend suites chỉ để deploy.

| Suite đã PASS trên đúng source này | Distinct tests / result |
|---|---:|
| Backend unit | 770 PASS |
| Isolated PostgreSQL integration | 682 PASS |
| Frontend unit | 67 PASS |
| Frontend mock UI | 105 PASS |
| Supported COUNT scenarios trong tests PG | 540/540 oracle match |
| Unsafe COUNT validator scenarios trong tests PG | 480/480 rejected |
| Ruff/lint/typecheck/build/diff | PASS |

Scenarios không cộng lại thành distinct pytest totals. Xem
[text_to_sql_count_semantic_contract_redesign.md](text_to_sql_count_semantic_contract_redesign.md)
cho fail-before/pass-after, reasons, six-domain oracle và security review.
Đã review production diff gồm cả generator/context/Hybrid dirty từ trước, new
analyzer/imports, new tests/fixtures và public Markdown/handoff. Không bỏ chúng
khỏi commit chỉ vì không thuộc delta cuối cùng.

Public delivery scan dùng công cụ local: so exact current Gemini/OAuth/private
endpoint/allowlist values trong memory và high-confidence Google/GitHub/private-key
patterns; kiểm candidate files và toàn reachable Git patch history. Không in
matching values. Scan đầu:37 reviewed files,0 blocking findings,0 email/credential-
URL review locations,0 reachable-history secret matches. Sẽ kiểm lại staged blobs
trước commit. Đây không phải chứng nhận mọi secret không thể phát hiện.

Baseline HEAD/main `e2151a3d6b37f3a11e83f68553e5985bbe087deb`; repo GitHub xác minh
**PUBLIC**, default main; remote đúng MinhHoang1403/Shopquery-AI.
Fetch origin: local HEAD và origin/main không divergence (0/0).
Không git add . / -A, không reset/clean/rebase/force push.
Stage explicit reviewed paths; không .env/private backups/raw responses/screenshots/
logs/JUnit/cache/venv hoặc credentials.

Commit/push/remote SHA và CI: **PENDING**, chỉ ghi PASS sau kết quả thật.
Không lấy CI cũ hoặc test local làm CI SHA mới. Báo cáo sẽ được bổ sung kết quả
delivery; không đổi app source để xử lý CI pending.

## F. Limits và next acceptance — KHÔNG THỰC HIỆN

Semantic COUNT verified offline và source đã phục vụ8080; **KH/GH Hybrid live
chưa test lại trên runtime mới**. Historical KH raw draft shape vẫn UNKNOWN.
Typed COUNT không chứng minh mọi business intent hoặc mọi model answer đúng.
Giữ SELECT-only, exact approved keys/graph/root/grain, owner/revision guards,
NULL/zero/Decimal/BIGINT và read-only execution.

Chỉ đề xuất riêng: KH Knowledge Hybrid một synthetic chat; chỉ KH PASS mới GH
Gemini cùng fixture. Trần **2 chats /8 logical generation stages /2 query embeddings /
0 document embeddings** nếu persisted policy còn hợp lệ. SDK retries có thể tăng
HTTP requests/cost. Fresh independent SQL/document oracle và protected fingerprints,
Google session/user approval cần riêng; không reuse budget cũ, không tự retry.

## G. Exact app module hash appendix

Mỗi hash dưới đây đồng thời là tested local = candidate = deployed runtime.
Đường dẫn tương đối backend/app;72 entries. Không phải Git object hashes.

```text
__init__.py 39faa09f530748ba8348a453df0ab89a1d1340a76b7f50dfaf5d3ae89f89df01
ai/__init__.py 3f91b9aee56d7404621978462edd733407a7a9388361d42c73f3335ba5037459
ai/chat.py 16f042d670891562c566d62efc81703389d570de88cd651524a91fa062f6fc76
ai/gemini.py ebdd95fe027a66bcad679451e00b1440bb6098b9349c2ffa0e33fb9ae9b2e4a8
ai/inetcloud.py 22b845f8e17d6944d2f496b3ad19281e9d965e5b6d5805e0e47591429a04d24b
ai/providers.py 641df715808dc9fddd16501376921f82099310fd9e086e2a7626ed76ba1d79d4
api/__init__.py fca301e8a6575a964358c81dc728ee04dabf136ac837e5a6f139816e30dcef92
api/models.py 5ad08db4a362292146e9637e78e5d6448e717db386d228479dbcdc979249d8a1
api/relationship_routes.py 3e61686545382da8d8bc9ea8782aa2e06e584523b389a7c6048aeb0a2ded85d6
api/routes.py 2ecfc79fb3f6a6c9122eec9d92d37bc33455d0cc8634ae1e57efe572dce562db
auth/__init__.py e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
auth/dependencies.py e2c1881f84d70b23a56c39441c503eb26fbb01628132fba0ec728b80d49ddc85
auth/limits.py f4ff57b080cbf7735f4c957c5ca5c880768c654513f3db9769f35f85feba8595
auth/oidc.py 4c1a375d0e5162ee1537c73199ef9dca856d7d8a2b212fb2e35378b30e3c60ee
auth/repository.py 1de321af050547c999c0506ffa91f4d505d5acd2e652dcc1228b3f8c1fd4bf03
auth/routes.py ee22343111a948c434c3b2dff46a1befda3dc38711c4c9440a48a50165be7010
conversations/__init__.py cec4b4726d78b3ad4057996d55b23621efc2fe0cf298b07fb36d35445bb1b0ed
conversations/repository.py 884f33818bb678a2cc8ccd7ab50ac4b77119585d14e0a9c31b36193d8e9e368c
core/__init__.py 9187ab8a2f623c99b6a4c97c973fa16672e2e978f7d41127813f92cf7efb3dce
core/client_ip.py 5ccd6f86e7ef5d1edbf483976e92e1da02a38b7ab34a3a91e48080169b2629f4
core/config.py 539cff48651745ac8be8cd1c3b8aac5780f1d7e57b76b9e5ea8813b8a2f08082
core/diagnostics.py 15f61e95d4ad9d8f7839b0b85a396c639f37ea1c46bda61ee0c71584a25384d1
core/errors.py 6040e6bee501e4760d32cadae40d8802db8b6f75506129e1a59cf77b7eb8caed
core/logging.py 26acc670088da1732479eed0db68aabb2ca50d7108849d1427a24523ceae3658
database/__init__.py 09aa2e704d5ca061318417aa86a52d58a3a830f0c06c9fdc5bdf7b8a2aa7973f
database/fresh.py da05654eeca38938bbc861c7c7002e657b860f577b11bf5615dc0c0ad8a32e2f
database/guest_access.py 6ce2def12a015e573edc409f477eb2441436b8976acdc2c35fee9b3aaebbf3ff
database/integrity.py 328e0b39cc7b9c2330be424c290e2b6943b6e8a497c52f9a13acc10b4cdd83b6
database/join_migration.py 9f8f9aca84f68670b278184ecea6b0dd2d7cf3c86b1d78cbcd3945ecc1457f5a
database/loader.py dee63e9c829be2cede6ba944d0f7b71c06252f74c80e752d1e298aeddaa9a3f8
database/migrations.py 919ac5f43f5e34fcdf4d9f7f858380eca62c0fce9b2a04066fa65d19ec40887f
database/models.py 607f486e77a27586144543d5cb43f0498b9dafd89b5f98ca6f4614060ac8a0e0
database/quotas.py 51765d9b7e530e9d6ea4c572bc0d8125c5e105e83b0bc9bfa71834a0c416bd56
database/seed_data.py 42ee04afafc47fd43813ddb5795fb0c202d2b0e0a309097c7aca042402aff55c
database/session.py d137065917820b433c6d0e06af0a19a481a7c8fb6bc3eacc1127d6fbe9c7b887
database/setup.py c2c45ec2c87c52ecb0ec24d304091be084cdc53430a7057fbc94556b16e5cee6
database/test_safety.py 64456f67cb4a059f06c4ed89610cc75e43595cf7c74c2d747c8398d2eede3e40
datasets/__init__.py 88ad67dc8cede332976f35e3e211baa29a2009c001fad86541fd90b6b66ade0c
datasets/context.py 0ec6cb0d29e2f217cb43f7cff7df6adbda6303d262817c70660fe9286633fea5
datasets/parser.py 7c14f5d6890fff5ea6ec36100f4f5398fac96962e8aa4b781c5cec9aa4416324
datasets/relationship_detection.py a665a3cd28ec0bd6f360e4c93314c6b37665ecae5936341a636565377231e2aa
datasets/relationship_repository.py 1b28c96851870e1091eddbca44ffc09e1c6ebb0746ef4a0510faea929190e1ca
datasets/relationships.py 884ca43b0b852765a5c7b5a6722420b2d1677d487b6eda3a65983950f00962c2
datasets/repository.py 8b5ff307f7df29660fc037524ab1704660f2c20e2e1d36e153af81abc8033c26
dependencies.py 6ef14ea67d9a18eaa7badad41c5e6bdecf3970fe592922a3e2e6d88e6cd06d4c
guest/__init__.py 05ab59172464aeb8ab6544ac2bd405f79cf3a8618482b7e83813411dfbd704e7
guest/limits.py dd8da93a584e8920197e0d9e53701b7150406adcafbdf99b5ae8010d925b3fb9
guest/middleware.py 8eb1bc66b7aab67aa130c3b07e6d0cd2d15f68c1b99241a67f04805fb12d9553
guest/pipeline.py 694197194796601a15bb6caea6d23101d5460f30c6132a4665ec5372ddcc7ad2
guest/relationship_routes.py ee22b7656a398d584944a07698cd884bd7fde828c385ba6b3b0c76326adbce61
guest/routes.py 8b2e6c5bb7df62dc30125c179ea714e01e004b85e7608d4ba583c719d0a26cbe
guest/store.py b5dfd846de03235b3d7251dda2c6850a7d8edebf12cd08b6b339a12f4eb86a97
guest/worker.py f581b70f9848f00c8427d4eb9d3cab9d8ebc64ef499137d50d6594f7bdaf5c7e
main.py 1107d4198224cb02fafef3a590bd833f5ea9203cd2ceb44c6ce447821324e54b
rag/__init__.py c5cbde6768079766683bf6d5183000c0d5d92aa4c997bc7959ec20a73ed55806
rag/chunking.py 4d0484f385137118d5aec329630a04e7e2fbdacf10934edb0a87d64180fce8fc
rag/documents.py deb1d07f2916ca1dede512336c8eaf0573e63127059e9502fdb776bfb1fb74a6
rag/pipeline.py 320538b3bf5f654322fa6eddb16efb391f8f644e1d8d05961d85d0d74d48c7fc
rag/repository.py f7f49642ba10084d167e429536d6e4ac5a35a7631055c39308c0bab079d41eda
rag/upload_parser.py 5961acb1eb80f942571da54705ab082ec678b42aaa3ecb01e15a17770874d69e
routing/__init__.py 20d9b4c0a466845f90b1b7c66550fd32ce35837fa51de9dbd7c4f523ca7b83a1
routing/hybrid.py 4e8a74ba599f86a2539c79c7e8710f7e76fa8a784a7fc8fabda0a063f6adfcb8
routing/router.py 60a17bb53fcec40e0da5b2f6fe7a1c56f438d8f991d59a0b157932973fb67b1c
routing/service.py 0995b6162cde7457f6a5eab1144ce9b220370918c0416d90b1473cc1f0ff7d5d
text_to_sql/__init__.py 6dbfc2a2e93a38309a37ce4d4ad9917c9fab72dd3dfc1d8c14ab995504aff2e9
text_to_sql/count_contract.py 8a8b46f77862da95334f84afd93cbe95b953321dd22d89704eb38eaaa89f5c9c
text_to_sql/executor.py e99de53dc5aac5bb890c5cca457b1f95f67ca239952b7ecf4ecc36e23c80aed6
text_to_sql/generator.py 3b50d43ae2ac1010624d1f5ee325aea431c9a8301db95d45fa7ef20ae306b78d
text_to_sql/join_policy.py a3fbbdf0f34840eb9247e06ae3a5f34f111d8d299668c416a9c71a09876471cd
text_to_sql/pipeline.py 057d6a5adada9383bfb083129043424d1b247a00effb40057e32506fdcb30818
text_to_sql/schema_context.py 800c26da1ef69abaa9bf30c9ab6c797a3449acc9b978631e738813b71bb6f575
text_to_sql/validator.py b83b28e856ae430f35d04f8ac74c51d636002e511d7238cd39a022149e753e12
```
