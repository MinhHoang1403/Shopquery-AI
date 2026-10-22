# Bảo mật và quyền dữ liệu

Giữ OIDC invite-only, PostgreSQL session lifecycle/revocation, CSRF, Origin checks
và owner-bound repositories. Đọc [authentication](authentication.md) trước migration.
Không gán dữ liệu cũ cho người đăng nhập đầu hoặc fake user trên main. Guest có
namespace/TTL/quota riêng, không truy cập private history.

SQL SELECT-only, table/column allowlists và approved graph; execution guard khóa
relationship revisions/key proof. Reader role, read-only transaction, timeout và
row cap giữ nguyên. Không nới validator để model trả lời được. Runtime setup role
cho metadata trong kiến trúc cũ chưa được coi là least-privilege production-audited.

Model chỉ sinh PlanDecision với catalog IDs và bounded expression operations; không
nhận SQL fragments, physical identifiers hoặc JOIN ON từ model. Compiler kiểm types,
grouping, depth/node bounds và COUNT aliases trước SQLGlot. Giá trị luôn bind vào
executor; rendered literal SQL chỉ dùng làm evidence sau validation. NULLIF được
thêm vào allowlist cho numeric division với mẫu số động bằng zero; COUNT/JOIN
policies và các assertions từ chối cũ được giữ.

Retrieval lọc owner/workspace trước nearest-neighbor. Reranker chỉ trả original
objects, không đổi source content/scope/IDs. Hybrid kiểm whole-document hash,
source identity, exact metric/Decimal và coverage; model verdict không override
evidence. Document/header/cell text là untrusted data, không phải instructions.

Gate bật không tự cấp consent gửi mọi dữ liệu cho provider. Generation/embedding
là hai cost/data paths. Không đổi model/key/quota/fallback ngầm. Dev Giai đoạn 1
tắt paid gates và không mang provider credentials vào API.

Local model pinned revision/hashes, local_files_only, remote code tắt, read-only
mount; không sửa cache phục vụ project khác. Guest memory limit giữ nguyên, không
load weights nhiều GB vào disposable worker hoặc nới tài nguyên ngầm.

Không log OAuth callback URL, key/cookie/token, raw prompt/private rows. Release
Nginx/Uvicorn access logs giữ tắt. Vite chỉ localhost dev. Config drift chỉ xuất
tên biến. Secrets, private evidence, weights, backups và logs ngoài commits.

Main/archived volumes và private backups không thuộc cleanup. Fixtures chỉ chạy
trong DB được guard xác nhận; không reset/migrate/re-ingest main. Public production,
load/abuse và comprehensive security audit chưa được nghiệm thu.
