"""Synthetic operating instructions shared by the two maintenance demo documents."""

PROCEDURE = [
    (
        "Tiếp nhận và xác định trung tâm",
        [
            (
                "Mục đích và phạm vi",
                (
                    "Quy trình hướng dẫn bộ phận tiếp nhận, điều phối, kỹ thuật và kiểm soát chất"
                    " lượng xử lý một phiếu bảo trì từ lúc ghi nhận đến khi đóng hồ sơ. Các mã, "
                    "địa điểm và tình huống trong bộ dữ liệu bảo trì thiết bị đều là giả lập. "
                    "Người vận hành dùng mã phiếu để tra cứu lịch sử; không dùng tên trung tâm để"
                    " thay thế khóa định danh. Tài liệu này mô tả công việc vận hành, không đặt "
                    "thêm ngưỡng KPI."
                ),
            ),
            (
                "Ghi nhận yêu cầu",
                (
                    "Nhân viên tiếp nhận xác định loại thiết bị, mô tả triệu chứng, kênh tiếp "
                    "nhận và mức độ ưu tiên trước khi lập phiếu. ma_phieu là mã duy nhất; "
                    "ma_trung_tam và ma_dich_vu phải có trong danh mục tương ứng. ngay_tiep_nhan "
                    "phản ánh ngày tiếp nhận thực tế. Ghi chú ghi lại hiện tượng quan sát được và"
                    " thông tin còn thiếu, không chứa mật khẩu thiết bị hoặc thông tin cá nhân "
                    "của người sử dụng."
                ),
            ),
            (
                "Xác nhận nơi thực hiện",
                (
                    "Điều phối đối chiếu ma_trung_tam với 01_trung_tam, kiểm tra thành phố, khu "
                    "vực, loại trung tâm và trạng thái hoạt động. Trung tâm Tạm ngưng không nhận "
                    "phân công mới; phiếu lịch sử của trung tâm vẫn được giữ để đối soát. Nếu cần"
                    " chuyển nơi thực hiện, điều phối xác minh mã đích và lưu lý do trước khi cập"
                    " nhật hồ sơ theo quy trình quản trị. Không ghép trung tâm chỉ vì tên gần "
                    "giống."
                ),
            ),
            (
                "Phân loại và chuyển giao",
                (
                    "Đối chiếu ma_dich_vu với 02_dich_vu để biết nhóm dịch vụ, loại thiết bị và "
                    "mức độ kỹ thuật. Phiếu mới ở trạng thái Mới tiếp nhận cho đến khi đủ thông "
                    "tin và có người nhận việc. Các kênh gồm Cổng dịch vụ, Điện thoại, Trực tiếp "
                    "và Đối tác. Mức ưu tiên Thấp, Bình thường, Cao hoặc Khẩn mô tả thứ tự xử lý,"
                    " không làm thay đổi công thức tổng phí. Ví dụ, PT000001 chỉ được giao cho "
                    "trung tâm có đúng mã được ghi trên phiếu, sau khi đối chiếu danh mục."
                ),
            ),
        ],
    ),
    (
        "Thực hiện và chuyển trạng thái",
        [
            (
                "Bắt đầu xử lý",
                (
                    "Kỹ thuật viên kiểm tra hồ sơ bàn giao, xác nhận phạm vi dịch vụ và lập nội "
                    "dung kiểm tra ban đầu. Khi công việc thực sự bắt đầu, chuyển trạng thái từ "
                    "Mới tiếp nhận sang Đang xử lý. Ghi nhận so_gio_xu_ly là thời gian đã dùng, "
                    "không tự suy từ khoảng cách hai ngày. Phiếu đang xử lý có thể chưa có "
                    "ngay_hoan_thanh; ô trống này là dữ liệu chưa có, không phải ngày tiếp nhận "
                    "hoặc ngày hiện tại."
                ),
            ),
            (
                "Điều kiện hoàn thành",
                (
                    "Chỉ chuyển sang Hoàn thành sau khi công việc đã thực hiện, kiểm tra an toàn "
                    "đạt yêu cầu, kết quả được kiểm soát chất lượng xác nhận và hồ sơ có nội dung"
                    " bàn giao. ngay_hoan_thanh phải không sớm hơn ngay_tiep_nhan và không muộn "
                    "hơn ngày ghi nhận hồ sơ. Kỹ thuật viên báo số giờ thực tế; bộ phận đối soát "
                    "xác nhận phi_bao_tri_vnd. Không điền ngày hoàn thành cho phiếu chỉ mới tiếp "
                    "nhận hoặc còn đang xử lý."
                ),
            ),
            (
                "Hủy và giữ lịch sử",
                (
                    "Chỉ chuyển sang Hủy khi yêu cầu không tiếp tục thực hiện và điều phối đã lưu"
                    " lý do. Không xóa phiếu hủy để làm đẹp thống kê. Phiếu hủy trước khi phát "
                    "sinh công việc có thể có phí bằng 0; phiếu hủy sau kiểm tra hoặc xử lý ban "
                    "đầu có thể giữ khoản phí đã được ghi nhận. Trường ngày hoàn thành để trống ở"
                    " phiếu Hủy. Chính sách KPI tại tài liệu MD xác định phạm vi tổng hợp; trạng "
                    "thái Hủy không tự động tạo một điều kiện lọc."
                ),
            ),
            (
                "Ví dụ kiểm tra ngày và phí",
                (
                    "Một phiếu tiếp nhận ngày 2026-03-12 và hoàn thành ngày 2026-03-15 có thứ tự "
                    "ngày hợp lệ. Phiếu đang xử lý ngày 2026-03-15 chưa có ngày hoàn thành vẫn "
                    "hợp lệ. Phí 0.00 là khoản đã ghi nhận bằng không; ô ghi chú trống chỉ cho "
                    "biết không có ghi chú bổ sung. Các ví dụ này giải thích dữ liệu, không thay "
                    "thế đối soát từng phiếu và không cho phép tự kết luận chất lượng dịch vụ từ "
                    "mức phí."
                ),
            ),
        ],
    ),
    (
        "Trách nhiệm và xử lý thiếu thông tin",
        [
            (
                "Trách nhiệm theo vai trò",
                (
                    "Bộ phận tiếp nhận chịu trách nhiệm mô tả yêu cầu và kênh gửi. Điều phối chịu"
                    " trách nhiệm kiểm tra mã trung tâm, mã dịch vụ, mức ưu tiên và phân công. Kỹ"
                    " thuật viên chịu trách nhiệm ghi triệu chứng, thao tác đã làm và số giờ thực"
                    " tế. Kiểm soát chất lượng đối chiếu kết quả với yêu cầu ban đầu và kiểm tra "
                    "an toàn trước bàn giao. Bộ phận đối soát xác nhận phí thực tế và xử lý chênh"
                    " lệch; không thay số giờ kỹ thuật bằng thời gian dự kiến trong danh mục."
                ),
            ),
            (
                "Phiếu thiếu thông tin",
                (
                    "Nếu thiếu mô tả thiết bị hoặc triệu chứng, giữ trạng thái Mới tiếp nhận và "
                    "yêu cầu bổ sung qua kênh đã ghi. Ghi rõ mục đang thiếu trong ghi_chu. Nếu "
                    "không xác định được ma_trung_tam hoặc ma_dich_vu hợp lệ, không import phiếu "
                    "vào bộ dữ liệu chuẩn cho đến khi điều phối xác minh. Không tạo mã giả để lấp"
                    " ô trống và không chọn ngẫu nhiên một dịch vụ có tên gần giống."
                ),
            ),
            (
                "Bàn giao giữa bộ phận",
                (
                    "Nội dung bàn giao cần cho biết ma_phieu, ma_trung_tam, ma_dich_vu, trạng "
                    "thái hiện tại, công việc đã thực hiện và phần còn chờ. Người nhận kiểm tra "
                    "khóa danh mục trước khi xác nhận tiếp nhận công việc. Nếu sai mã dịch vụ, "
                    "tạm dừng thao tác chuyên môn cho đến khi điều phối xác nhận phạm vi. Một "
                    "thông báo đã được gửi không đồng nghĩa công việc hoàn thành; trạng thái vẫn "
                    "phản ánh tiến độ thực tế."
                ),
            ),
            (
                "Thông tin không được suy đoán",
                (
                    "Ghi chú NULL không đồng nghĩa thiết bị không có lỗi. so_gio_xu_ly NULL ở "
                    "phiếu mới không được thay bằng 0 khi tính trung bình thời gian đã ghi nhận. "
                    "Không suy tình trạng hiện tại của trung tâm từ ngày tạo phiếu lịch sử. Khi "
                    "truy vấn phân tích, COUNT(*) đếm dòng phiếu, còn COUNT(ghi_chu) chỉ đếm "
                    "phiếu có ghi chú. Câu hỏi thiếu phạm vi hoặc thiếu bằng chứng cần được làm "
                    "rõ thay vì tự bổ sung điều kiện."
                ),
            ),
        ],
    ),
    (
        "Khiếu nại và kiểm tra kết quả",
        [
            (
                "Tiếp nhận khiếu nại",
                (
                    "Nhân viên ghi nhận ma_phieu, nội dung phản ánh và kênh tiếp nhận, rồi chuyển"
                    " người phụ trách kiểm soát chất lượng. Kiểm tra đúng trung tâm và dịch vụ "
                    "trên hồ sơ trước khi phản hồi. Không ghi nội dung tố cáo hoặc kết luận "
                    "nguyên nhân vào trạng thái phiếu. Tài liệu này không quy định thời hạn bồi "
                    "thường hay mức hoàn tiền; khi không có căn cứ, cần chuyển bộ phận có thẩm "
                    "quyền thay vì tự đưa ra con số."
                ),
            ),
            (
                "Đối chiếu kết quả",
                (
                    "Kiểm soát chất lượng đọc yêu cầu ban đầu, ghi chú thao tác, ngày tiếp nhận, "
                    "ngày hoàn thành và số giờ xử lý. Đối soát kiểm tra phi_bao_tri_vnd thực tế, "
                    "phân biệt với phi_tham_khao_vnd của danh mục dịch vụ. Nếu hai nguồn khác "
                    "nhau, phải tìm căn cứ nghiệp vụ thay vì tự sửa phí thực tế bằng phí tham "
                    "khảo. Hồ sơ kiểm tra phải chỉ ra trường dữ liệu và bằng chứng đã dùng."
                ),
            ),
            (
                "Kiểm tra tổng hợp",
                (
                    "Báo cáo theo trung tâm phải dùng ma_trung_tam để phân biệt các thực thể; tên"
                    " chỉ là thông tin mô tả. JOIN từ phiếu sang danh mục phải là nhiều phiếu đến"
                    " một dòng danh mục, không được nhân số dòng. Khi cần kết luận KPI, đọc "
                    "04_KPI_trung_tam.md và tổng hợp dữ liệu theo đúng phạm vi của chính sách đó."
                    " Quy trình này không có một ngưỡng KPI hoặc ngoại lệ KPI khác."
                ),
            ),
            (
                "Kết thúc và lưu hồ sơ",
                (
                    "Người phụ trách ghi kết quả kiểm tra, mục đã xác minh và việc cần theo dõi "
                    "trong ghi_chu; lưu lịch sử thay đổi qua chức năng quản trị được cho phép. "
                    "Không xóa dữ liệu cũ chỉ vì một báo cáo có sai lệch. Nếu phát hiện lỗi "
                    "import, khóa danh mục không hợp lệ hoặc kết quả bị nhân dòng, dừng sử dụng "
                    "kết quả phân tích đó và kiểm tra nguồn trước. Chỉ bàn giao kết luận sau khi "
                    "các bên thống nhất bằng chứng và phạm vi giải thích."
                ),
            ),
        ],
    ),
]

SERVICE_GROUPS = ["Kiểm tra", "Vệ sinh", "Hiệu chuẩn", "Thay thế", "Sửa chữa", "Kiểm định"]
DEVICE_TYPES = ["Máy bơm", "Máy nén khí", "Tủ điện", "Bộ lưu điện", "Hệ thống lạnh"]

HANDBOOK = [
    (
        "Nhóm dịch vụ và thiết bị",
        [
            (
                "Phạm vi sử dụng",
                (
                    "Sổ tay giúp tiếp nhận và kỹ thuật thống nhất cách chọn dịch vụ trong "
                    "02_dich_vu và tham chiếu dịch vụ từ 03_phieu_bao_tri. Đây là danh mục bảo "
                    "trì thiết bị giả lập dùng để phân tích và kiểm thử. Sổ tay giải thích nghiệp"
                    " vụ; không đặt ngưỡng KPI, không thay thế kiểm tra hiện trường và không cho "
                    "phép thực hiện thao tác điện hoặc áp lực khi chưa có người đủ chuyên môn."
                ),
            ),
            (
                "Sáu nhóm dịch vụ",
                (
                    "Kiểm tra dùng để quan sát, đo và xác định hiện tượng trước khi quyết định "
                    "công việc. Vệ sinh loại bỏ bụi, cặn hoặc tác nhân làm giảm hiệu quả. Hiệu "
                    "chuẩn đối chiếu thông số đo với chuẩn được chấp nhận. Thay thế áp dụng khi "
                    "bộ phận cần được đổi theo phạm vi đã xác nhận. Sửa chữa khắc phục hư hỏng "
                    "xác định. Kiểm định là bước đánh giá kết quả, an toàn và điều kiện đưa thiết"
                    " bị vào vận hành."
                ),
            ),
            (
                "Năm loại thiết bị",
                (
                    "Danh mục hỗ trợ Máy bơm, Máy nén khí, Tủ điện, Bộ lưu điện và Hệ thống lạnh."
                    " Mỗi dịch vụ có loai_thiet_bi riêng, không dùng một mã cho mọi thiết bị chỉ "
                    "vì cùng nhóm công việc. Ví dụ, dịch vụ vệ sinh máy bơm có bước kiểm tra "
                    "đường hút và bề mặt khác với vệ sinh tủ điện. Tra ma_dich_vu trước khi giao "
                    "việc; tên dễ đọc giúp mô tả, còn mã là khóa liên kết."
                ),
            ),
            (
                "Chọn dịch vụ đúng phạm vi",
                (
                    "Đọc triệu chứng trong hồ sơ, xác định loại thiết bị và chọn nhóm công việc "
                    "phù hợp. Nếu chưa biết nguyên nhân, chọn công việc kiểm tra tương ứng thay "
                    "vì mặc định thay thế. Nếu yêu cầu có nhiều hạng mục, điều phối ghi rõ công "
                    "việc đang được phân tích trong từng phiếu. Tài liệu không định nghĩa một "
                    "bảng chi tiết nhiều dịch vụ trong cùng phiếu; mỗi dòng phiếu hiện tham chiếu"
                    " một ma_dich_vu."
                ),
            ),
        ],
    ),
    (
        "Mức kỹ thuật và phân công",
        [
            (
                "Cơ bản",
                (
                    "Mức Cơ bản gồm công việc quan sát, vệ sinh bên ngoài hoặc kiểm tra theo "
                    "hướng dẫn đã được duyệt. Người thực hiện kiểm tra tình trạng an toàn trước "
                    "khi chạm vào thiết bị và dừng nếu phát hiện nguy cơ điện, áp lực hoặc rò rỉ."
                    " Mức này không tự cho phép mở một cụm cần chứng nhận chuyên môn. Loại thiết "
                    "bị và phạm vi dịch vụ vẫn quyết định người được phân công."
                ),
            ),
            (
                "Nâng cao",
                (
                    "Mức Nâng cao cần người có năng lực kiểm tra sâu, đọc thông số và giải thích "
                    "kết quả đo. Điều phối đối chiếu công việc với khả năng của trung tâm. Kỹ "
                    "thuật viên ghi phương pháp kiểm tra và kết quả vào ghi_chu theo biểu mẫu "
                    "quản trị. thoi_gian_du_kien_gio trong danh mục chỉ là thông tin lập lịch, "
                    "không thay cho so_gio_xu_ly đã thực tế ghi trên phiếu."
                ),
            ),
            (
                "Chuyên sâu",
                (
                    "Mức Chuyên sâu yêu cầu điều phối chuyển cho kỹ thuật chuyên trách; người "
                    "tiếp nhận không tự chẩn đoán hoặc đưa thiết bị vào vận hành thử. Kiểm soát "
                    "chất lượng xem xét bằng chứng kiểm tra và xác nhận điều kiện bàn giao. Nếu "
                    "trung tâm không đủ năng lực hoặc đang Tạm ngưng, dừng phân công mới và xác "
                    "minh nơi tiếp nhận phù hợp. Không chọn mã dịch vụ Cơ bản chỉ để bỏ qua yêu "
                    "cầu chuyên môn."
                ),
            ),
            (
                "Tài liệu và bằng chứng",
                (
                    "Khi trả lời câu hỏi phân công, cần dẫn đúng phần mô tả mức kỹ thuật và phần "
                    "xác nhận trung tâm trong quy trình DOCX. Sổ tay không quy định danh sách "
                    "nhân viên hay chứng chỉ cá nhân. Nếu người hỏi yêu cầu tên người có thẩm "
                    "quyền mà workspace không có nguồn đó, phải nêu thiếu thông tin. Không suy "
                    "danh tính người chịu trách nhiệm từ tên thành phố hoặc mức phí."
                ),
            ),
        ],
    ),
    (
        "Mã dịch vụ và phí thực tế",
        [
            (
                "Tham chiếu mã",
                (
                    "ma_dich_vu là khóa duy nhất của danh mục; phiếu tham chiếu đúng mã này để "
                    "lấy ten_dich_vu, nhom_dich_vu, loai_thiet_bi và muc_do_ky_thuat. Không JOIN "
                    "bằng phí hoặc tên nhóm vì nhiều dịch vụ có thể cùng nhóm hay cùng mức giá. "
                    "Khi mã không tồn tại, dừng import hoặc phân công và yêu cầu điều phối xác "
                    "nhận. Không tạo một dịch vụ mặc định để che mã orphan."
                ),
            ),
            (
                "Phí danh mục",
                (
                    "phi_tham_khao_vnd là mức tham khảo phục vụ tư vấn và lập kế hoạch. Giá này "
                    "không phải chi phí đã ghi nhận trên từng phiếu và không được cộng lại theo "
                    "số dòng JOIN để thay thế số liệu thực tế. Danh mục có thể có phần thập phân,"
                    " vì vậy không làm tròn một giá trị chỉ vì đơn vị là VND. Khi hiển thị, giữ "
                    "nguyên chữ số đã được nguồn dữ liệu ghi nhận."
                ),
            ),
            (
                "Phí của phiếu",
                (
                    "phi_bao_tri_vnd nằm trong 03_phieu_bao_tri là giá trị thực tế dùng khi hỏi "
                    "tổng phí bảo trì. Ví dụ minh họa: phí danh mục 125000.50 VND và phí phiếu "
                    "123456.78 VND là hai giá trị khác nhau, mỗi giá trị có nguồn riêng. Hỏi tổng"
                    " phí thực tế phải SUM phi_bao_tri_vnd ở phiếu; không SUM phi_tham_khao_vnd ở"
                    " danh mục, không coi chênh lệch là lỗi khi chưa có căn cứ đối soát."
                ),
            ),
            (
                "Không và chưa có",
                (
                    "Phí 0.00 là một giá trị hợp lệ, có thể xuất hiện khi công việc không thu phí"
                    " hoặc phiếu hủy chưa phát sinh công việc. NULL ở ghi chú hay ngày hoàn thành"
                    " thể hiện dữ liệu chưa có, không đồng nghĩa số không. Phiếu hủy sau kiểm tra"
                    " có thể có khoản phí đã ghi nhận. Khi hỏi KPI, phải dùng chính sách MD và "
                    "phạm vi mọi trạng thái; sổ tay không tự thêm một ngoại lệ cho phiếu Hủy."
                ),
            ),
        ],
    ),
    (
        "Tình huống đặc biệt",
        [
            (
                "Thiết bị chưa xác định",
                (
                    "Nếu không xác định được loai_thiet_bi, yêu cầu bổ sung nhãn thiết bị và mô "
                    "tả hiện tượng theo kênh tiếp nhận đã lưu. Không suy loại thiết bị từ một từ "
                    "đơn lẻ trong ghi chú. Hồ sơ tiếp tục Mới tiếp nhận cho đến khi có thông tin "
                    "đủ để phân loại; ma_dich_vu chỉ được chọn sau đối chiếu danh mục. Không gán "
                    "mức Chuyên sâu hoặc Cơ bản theo cảm tính."
                ),
            ),
            (
                "Nguy cơ an toàn",
                (
                    "Khi có dấu hiệu mất an toàn điện, áp lực, nhiệt hoặc rò rỉ, dừng công việc "
                    "và chuyển điều phối cùng kỹ thuật chuyên trách. Không dùng yêu cầu phân tích"
                    " dữ liệu để thực hiện hoặc hướng dẫn một thao tác nguy hiểm chưa có quy "
                    "trình. Ghi hiện tượng quan sát được vào hồ sơ; không kết luận nguyên nhân "
                    "hoặc hứa thời gian khôi phục khi chưa có bằng chứng kiểm tra."
                ),
            ),
            (
                "Sai mã hoặc sai nơi thực hiện",
                (
                    "Nếu ma_trung_tam hoặc ma_dich_vu không khớp hồ sơ bàn giao, tạm dừng phân "
                    "công và đối chiếu lại nguồn. Sai tên viết tắt không cho phép tự thay đổi "
                    "khóa đã lưu. Nếu trung tâm Tạm ngưng, phiếu lịch sử vẫn được phân tích đúng "
                    "theo mã; điều phối xác minh việc phân công mới. Không xóa các dòng lịch sử "
                    "để làm cho JOIN hoặc báo cáo trông hợp lệ."
                ),
            ),
            (
                "Khiếu nại về phí",
                (
                    "Đối soát đọc phí thực tế của phiếu, ghi chú công việc và căn cứ đã bàn giao."
                    " Danh mục chỉ cung cấp mức tham khảo; không chứng minh khách hàng được hoàn "
                    "chênh lệch. Workspace này không có biểu phí bồi thường, thời hạn hoàn tiền "
                    "hoặc điều khoản bảo hiểm. Nếu tài liệu không nói, câu trả lời phải thừa nhận"
                    " thiếu căn cứ và chuyển đúng bộ phận, không tự nêu điều khoản hoặc số tiền."
                ),
            ),
        ],
    ),
    (
        "Kiểm tra báo cáo và dẫn chứng",
        [
            (
                "Báo cáo sử dụng dịch vụ",
                (
                    "Số phiếu theo dịch vụ được đếm từ từng dòng 03_phieu_bao_tri sau khi liên "
                    "kết N:1 tới 02_dich_vu. Trung bình phí phải dùng phi_bao_tri_vnd thực tế. "
                    "Nếu một phiếu bị nhân thành nhiều dòng sau JOIN, kết quả tổng hợp không hợp "
                    "lệ; kiểm tra uniqueness của mã dịch vụ và điều kiện ON trước khi kết luận. "
                    "Không dùng tên hiển thị làm định danh duy nhất của một nhóm thực thể."
                ),
            ),
            (
                "Đối chiếu ba nguồn",
                (
                    "Quy trình DOCX giải thích trạng thái và trách nhiệm; sổ tay PDF giải thích "
                    "dịch vụ và phí; 04_KPI_trung_tam.md là nguồn duy nhất cho quy tắc phân loại "
                    "KPI. Câu hỏi cần số liệu và chính sách phải có cả kết quả SQL đúng phạm vi "
                    "lẫn dẫn chứng tài liệu. Một đoạn mô tả dịch vụ không đủ để kết luận một "
                    "trung tâm đạt hoặc chưa đạt KPI."
                ),
            ),
            (
                "Đọc ngày và phạm vi",
                (
                    "Lọc theo ngay_tiep_nhan khi người hỏi yêu cầu thời điểm tiếp nhận; lọc theo "
                    "ngay_hoan_thanh khi người hỏi nêu thời điểm hoàn thành. Không thay một "
                    "trường ngày bằng trường còn lại. Một phiếu chưa hoàn thành có ngày hoàn "
                    "thành trống và không thuộc tập lọc ngày hoàn thành. Khoảng tháng dùng mốc "
                    "bắt đầu bao gồm và mốc đầu tháng kế tiếp loại trừ để tránh đếm trùng biên."
                ),
            ),
            (
                "Giới hạn của tài liệu",
                (
                    "Không có thông tin về doanh thu kế toán, nhân viên cụ thể, hợp đồng khách "
                    "hàng, thời hạn bồi thường hoặc vị trí kho linh kiện. Không trả lời các thông"
                    " tin này bằng suy đoán. Khi trích dẫn, nêu đúng nguồn và trang chứa quy tắc "
                    "đã dùng. Khi một câu hỏi cần nhiều đoạn, dẫn cả phần giải thích phí danh mục"
                    " và phí của phiếu, thay vì gán một đoạn trích cho hai kết luận khác nhau."
                ),
            ),
        ],
    ),
]
