"""Hồ sơ đề nghị cấp tín dụng MẪU — dùng để tham khảo cách trình bày một bộ hồ sơ đầy đủ.

Số liệu trong file là số liệu minh hoạ của một doanh nghiệp giả định. Phần thẩm định
giá trị doanh nghiệp, chỉ số tài chính, lịch trả nợ và biểu đồ **không viết cứng** mà
được chạy qua đúng engine tính toán của hệ thống, nên bản mẫu luôn nhất quán với
những gì khách hàng thật sẽ nhận được.

Riêng mục "Căn cứ pháp lý" trong bản mẫu được điền sẵn để minh hoạ cách trình bày.
Khi chạy thật, hệ thống chỉ trích dẫn những điều khoản có trong kho văn bản đã nạp.
"""

from __future__ import annotations

from functools import lru_cache

from ..schemas import (
    CollateralItem,
    Dossier,
    FinancialRow,
    LegalBasis,
    LoanRequest,
    Party,
)
from ..services import readiness, valuation

GHI_CHU_MAU = (
    "HỒ SƠ MẪU — số liệu của một doanh nghiệp giả định, dùng để minh hoạ bố cục và "
    "cách trình bày. Phần căn cứ pháp lý trong bản mẫu được điền sẵn; khi lập hồ sơ "
    "thật, hệ thống chỉ trích dẫn điều khoản có trong kho văn bản pháp luật bạn đã nạp."
)

# ------------------------------------------------------- thông tin đầu vào

BEN_VAY = Party(
    ten="CÔNG TY TNHH VẬN TẢI ĐÔNG DƯƠNG",
    loai_hinh="Công ty TNHH hai thành viên trở lên",
    ma_so_thue="0108765432",
    so_giay_to="0108765432 do Sở Kế hoạch và Đầu tư TP Hà Nội cấp lần đầu ngày 12/03/2018",
    nguoi_dai_dien="Nguyễn Văn Thành",
    chuc_vu="Giám đốc",
    dia_chi="Số 128 đường Phạm Văn Đồng, phường Cổ Nhuế 1, quận Bắc Từ Liêm, TP Hà Nội",
    dien_thoai="024 3795 6688",
    email="ketoan@vantaidongduong.com.vn",
    nganh_nghe="Vận tải hàng hoá bằng đường bộ (mã ngành 4933) — vận chuyển container tuyến Bắc - Trung",
    nam_thanh_lap="2018",
    von_dieu_le="15.000.000.000 VND",
)

DE_NGHI_VAY = LoanRequest(
    so_tien="5.000.000.000",
    don_vi="VND",
    muc_dich_vay=(
        "Đầu tư mua 04 xe đầu kéo Howo T7H (đời 2025) phục vụ mở rộng đội xe vận chuyển "
        "container tuyến Hà Nội - Đà Nẵng theo hợp đồng vận chuyển dài hạn đã ký với "
        "03 đối tác, đồng thời bổ sung vốn lưu động cho chi phí vận hành quý đầu."
    ),
    thoi_han="60 tháng",
    phuong_thuc_cho_vay="Cho vay theo dự án đầu tư",
    phuong_thuc_giai_ngan="Chuyển khoản trực tiếp cho bên thụ hưởng",
    phuong_thuc_tra_no="Trả gốc đều hàng tháng, lãi theo dư nợ giảm dần",
    lai_suat_du_kien="9,5%/năm",
    von_tu_co="2.000.000.000",
)

PHUONG_AN_SU_DUNG_VON = [
    "Mua 04 xe đầu kéo Howo T7H đời 2025 (đơn giá 1.600.000.000/xe): 6.400.000.000 VND",
    "Lệ phí trước bạ, đăng ký, đăng kiểm và bảo hiểm vật chất năm đầu: 320.000.000 VND",
    "Bổ sung vốn lưu động quý đầu (nhiên liệu, phí đường bộ, lương lái xe): 280.000.000 VND",
]

TOM_TAT_PHUONG_AN = (
    "Công ty đang khai thác 18 đầu kéo trên tuyến Hà Nội - Đà Nẵng - TP Hồ Chí Minh, hệ số "
    "sử dụng xe bình quân 92%. Trong năm 2025 công ty đã ký 03 hợp đồng vận chuyển dài hạn "
    "thời hạn 36 tháng với sản lượng cam kết 2.400 chuyến/năm, vượt năng lực đội xe hiện có "
    "khoảng 15%. Công ty đề nghị vay 5 tỷ đồng, cùng 2 tỷ đồng vốn tự có, để đầu tư thêm 04 "
    "đầu kéo. Mỗi xe khai thác bình quân 18 chuyến/tháng, doanh thu thuần sau chi phí vận hành "
    "đạt khoảng 46 triệu đồng/xe/tháng, tương ứng 2,2 tỷ đồng/năm cho cả 04 xe — đủ bù đắp "
    "nghĩa vụ trả nợ bình quân 1,3 tỷ đồng/năm của khoản vay này."
)

PHUONG_AN_TRA_NO = (
    "Nguồn trả nợ chính là doanh thu vận tải từ 04 xe đầu tư mới, ước tính 2,2 tỷ đồng lợi "
    "nhuận thuần mỗi năm. Nguồn trả nợ bổ sung là dòng tiền từ 18 đầu kéo đang khai thác, "
    "năm 2025 tạo ra 7,2 tỷ đồng lợi nhuận sau thuế cộng khấu hao. Công ty trả gốc đều "
    "83.333.333 đồng/tháng trong 60 tháng, lãi tính trên dư nợ giảm dần, thu từ tài khoản "
    "thanh toán mở tại ngân hàng cho vay."
)

TAI_SAN_BAO_DAM = [
    CollateralItem(
        ten_tai_san="04 xe đầu kéo Howo T7H hình thành từ vốn vay",
        mo_ta="Xe đầu kéo mới 100%, đời 2025, mua theo hợp đồng số 24/2026/HĐMB-ĐD "
              "ký với Công ty CP Ô tô Trường Hải Auto",
        gia_tri_uoc_tinh="6.400.000.000 VND",
        giay_to_phap_ly="Hợp đồng mua bán, hoá đơn GTGT, giấy đăng ký xe (bổ sung sau khi đăng ký)",
        ghi_chu="Thế chấp tài sản hình thành trong tương lai, mua bảo hiểm vật chất xe "
                "với người thụ hưởng là ngân hàng",
    ),
    CollateralItem(
        ten_tai_san="Quyền sử dụng đất và tài sản gắn liền với đất tại Bắc Từ Liêm",
        mo_ta="Thửa đất số 217, tờ bản đồ số 12, diện tích 240 m², mục đích sử dụng đất ở "
              "đô thị, cùng nhà xưởng kho bãi 180 m² xây năm 2021",
        gia_tri_uoc_tinh="4.200.000.000 VND",
        giay_to_phap_ly="Giấy chứng nhận QSDĐ số CT 084213 do UBND quận Bắc Từ Liêm cấp ngày 08/06/2021",
        ghi_chu="Chủ sở hữu là thành viên góp vốn, đã có văn bản đồng ý thế chấp của "
                "vợ/chồng đồng sở hữu",
    ),
]

TINH_HINH_TAI_CHINH = [
    FinancialRow(chi_tieu="Doanh thu thuần", nam_truoc="42.000.000.000",
                 nam_hien_tai="51.400.000.000", du_kien="61.000.000.000"),
    FinancialRow(chi_tieu="Giá vốn hàng bán", nam_truoc="34.600.000.000",
                 nam_hien_tai="41.900.000.000", du_kien="49.300.000.000"),
    FinancialRow(chi_tieu="Lợi nhuận sau thuế", nam_truoc="2.100.000.000",
                 nam_hien_tai="3.400.000.000", du_kien="4.300.000.000"),
    FinancialRow(chi_tieu="Khấu hao tài sản cố định", nam_truoc="3.200.000.000",
                 nam_hien_tai="3.800.000.000", du_kien="4.600.000.000"),
    FinancialRow(chi_tieu="Chi phí lãi vay", nam_truoc="1.020.000.000",
                 nam_hien_tai="1.150.000.000", du_kien="1.540.000.000"),
    FinancialRow(chi_tieu="Tổng tài sản", nam_truoc="33.500.000.000",
                 nam_hien_tai="38.600.000.000", du_kien="45.200.000.000"),
    FinancialRow(chi_tieu="Tài sản ngắn hạn", nam_truoc="14.100.000.000",
                 nam_hien_tai="16.800.000.000", du_kien=""),
    FinancialRow(chi_tieu="Hàng tồn kho", nam_truoc="2.050.000.000",
                 nam_hien_tai="2.400.000.000", du_kien=""),
    FinancialRow(chi_tieu="Tiền và các khoản tương đương tiền", nam_truoc="1.780.000.000",
                 nam_hien_tai="2.150.000.000", du_kien=""),
    FinancialRow(chi_tieu="Nợ phải trả", nam_truoc="13.200.000.000",
                 nam_hien_tai="14.100.000.000", du_kien="16.400.000.000"),
    FinancialRow(chi_tieu="Nợ ngắn hạn", nam_truoc="8.400.000.000",
                 nam_hien_tai="9.600.000.000", du_kien=""),
    FinancialRow(chi_tieu="Vay và nợ thuê tài chính", nam_truoc="9.100.000.000",
                 nam_hien_tai="9.800.000.000", du_kien=""),
    FinancialRow(chi_tieu="Vốn chủ sở hữu", nam_truoc="20.300.000.000",
                 nam_hien_tai="24.500.000.000", du_kien="28.800.000.000"),
]

CAN_CU_PHAP_LY = [
    LegalBasis(
        van_ban="Luật Các tổ chức tín dụng số 32/2024/QH15",
        dieu_khoan="Điều 102",
        noi_dung="Tổ chức tín dụng phải yêu cầu khách hàng cung cấp tài liệu chứng minh phương án "
                 "sử dụng vốn khả thi, khả năng tài chính, mục đích sử dụng vốn hợp pháp trước khi "
                 "quyết định cấp tín dụng, và phải kiểm tra việc sử dụng tiền vay.",
        ap_dung="Chi phối toàn bộ danh mục hồ sơ khách hàng phải nộp và điều kiện kiểm tra "
                "sử dụng vốn sau giải ngân.",
    ),
    LegalBasis(
        van_ban="Thông tư 39/2016/TT-NHNN (đã được sửa đổi, bổ sung)",
        dieu_khoan="Điều 7",
        noi_dung="Điều kiện vay vốn: khách hàng có năng lực pháp luật dân sự, nhu cầu vay hợp pháp, "
                 "có phương án sử dụng vốn khả thi và có khả năng tài chính để trả nợ.",
        ap_dung="Là căn cứ của mục II (thông tin bên vay), mục IV (phương án sử dụng vốn) và "
                "mục đánh giá khả năng trả nợ.",
    ),
    LegalBasis(
        van_ban="Thông tư 39/2016/TT-NHNN (đã được sửa đổi, bổ sung)",
        dieu_khoan="Điều 8",
        noi_dung="Các nhu cầu vốn tổ chức tín dụng không được cho vay, trong đó có việc cho vay để "
                 "gửi tiền, để trả nợ khoản cấp tín dụng khác, hoặc đầu tư kinh doanh thuộc ngành "
                 "nghề bị cấm.",
        ap_dung="Dùng để đối chiếu tính hợp pháp của mục đích vay vốn nêu tại mục III.",
    ),
    LegalBasis(
        van_ban="Thông tư 39/2016/TT-NHNN (đã được sửa đổi, bổ sung)",
        dieu_khoan="Điều 9",
        noi_dung="Hồ sơ đề nghị vay vốn gồm tài liệu chứng minh đủ điều kiện vay vốn và các tài liệu "
                 "khác do tổ chức tín dụng hướng dẫn.",
        ap_dung="Là căn cứ trực tiếp của mục danh mục hồ sơ phải nộp.",
    ),
    LegalBasis(
        van_ban="Thông tư 39/2016/TT-NHNN (đã được sửa đổi, bổ sung)",
        dieu_khoan="Điều 13",
        noi_dung="Tổ chức tín dụng và khách hàng thoả thuận lãi suất cho vay theo cung cầu vốn, "
                 "trừ các lĩnh vực ưu tiên áp dụng mức trần lãi suất ngắn hạn bằng đồng Việt Nam.",
        ap_dung="Chi phối mức lãi suất dự kiến 9,5%/năm ghi tại mục III.",
    ),
    LegalBasis(
        van_ban="Thông tư 39/2016/TT-NHNN (đã được sửa đổi, bổ sung)",
        dieu_khoan="Điều 23",
        noi_dung="Nội dung tối thiểu của thoả thuận cho vay, gồm số tiền, mục đích, thời hạn, "
                 "lãi suất, phương thức trả nợ, biện pháp bảo đảm và quyền, nghĩa vụ các bên.",
        ap_dung="Là khung nội dung cho hợp đồng tín dụng sẽ ký sau khi hồ sơ được phê duyệt.",
    ),
    LegalBasis(
        van_ban="Thông tư 39/2016/TT-NHNN (đã được sửa đổi, bổ sung)",
        dieu_khoan="Điều 24",
        noi_dung="Tổ chức tín dụng có quyền và nghĩa vụ kiểm tra, giám sát việc sử dụng vốn vay và "
                 "trả nợ của khách hàng.",
        ap_dung="Là căn cứ của điều kiện kèm theo về kiểm tra sử dụng vốn định kỳ.",
    ),
    LegalBasis(
        van_ban="Nghị định 21/2021/NĐ-CP",
        dieu_khoan="Chương II và Chương III",
        noi_dung="Quy định thi hành Bộ luật Dân sự về bảo đảm thực hiện nghĩa vụ, bao gồm tài sản "
                 "bảo đảm, tài sản hình thành trong tương lai và hiệu lực đối kháng với người thứ ba.",
        ap_dung="Chi phối việc nhận thế chấp 04 xe đầu kéo hình thành từ vốn vay tại mục VI.",
    ),
    LegalBasis(
        van_ban="Bộ luật Dân sự số 91/2015/QH13",
        dieu_khoan="Điều 317 đến Điều 327",
        noi_dung="Quy định về thế chấp tài sản: hình thức, hiệu lực, quyền và nghĩa vụ của bên "
                 "thế chấp và bên nhận thế chấp, xử lý tài sản thế chấp.",
        ap_dung="Là căn cứ pháp lý của hợp đồng thế chấp quyền sử dụng đất tại mục VI.",
    ),
    LegalBasis(
        van_ban="Thông tư 11/2021/TT-NHNN",
        dieu_khoan="Điều 10",
        noi_dung="Quy định phân loại nợ và cam kết ngoại bảng theo phương pháp định lượng, làm cơ sở "
                 "trích lập dự phòng rủi ro.",
        ap_dung="Là căn cứ để ngân hàng theo dõi nhóm nợ trong suốt thời gian vay 60 tháng.",
    ),
]

DANH_MUC_HO_SO = [
    # (nhóm, tên tài liệu, bắt buộc, căn cứ, ghi chú)
    ("Hồ sơ pháp lý", "Giấy chứng nhận đăng ký doanh nghiệp (bản sao chứng thực)", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", "Bản cấp đổi gần nhất"),
    ("Hồ sơ pháp lý", "Điều lệ công ty và các phụ lục sửa đổi", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", "Kiểm tra thẩm quyền quyết định vay vốn"),
    ("Hồ sơ pháp lý", "Nghị quyết Hội đồng thành viên về việc vay vốn và thế chấp tài sản", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", "Phải nêu rõ số tiền, thời hạn, tài sản bảo đảm"),
    ("Hồ sơ pháp lý", "Quyết định bổ nhiệm Giám đốc và Kế toán trưởng", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", ""),
    ("Hồ sơ pháp lý", "CCCD của người đại diện theo pháp luật và kế toán trưởng", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", ""),
    ("Hồ sơ pháp lý", "Giấy phép kinh doanh vận tải bằng xe ô tô", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", "Điều kiện kinh doanh của ngành nghề có điều kiện"),
    ("Hồ sơ khoản vay", "Giấy đề nghị vay vốn theo mẫu của tổ chức tín dụng", True,
     "Điều 9 Thông tư 39/2016/TT-NHNN", ""),
    ("Hồ sơ khoản vay", "Phương án sử dụng vốn và kế hoạch trả nợ", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", "Chính là mục IV và V của hồ sơ này"),
    ("Hồ sơ khoản vay", "Hợp đồng mua bán 04 xe đầu kéo và báo giá của nhà cung cấp", True,
     "Điều 9 Thông tư 39/2016/TT-NHNN", "Chứng minh nhu cầu vốn là có thật"),
    ("Hồ sơ khoản vay", "03 hợp đồng vận chuyển dài hạn đã ký với đối tác", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", "Chứng minh đầu ra của phương án"),
    ("Hồ sơ khoản vay", "Bảng kê chi tiết đội xe hiện có và hiệu suất khai thác", False,
     "", "Tài liệu hỗ trợ thẩm định"),
    ("Hồ sơ tài chính", "Báo cáo tài chính 02 năm gần nhất (có xác nhận của cơ quan thuế)", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", "Kèm thuyết minh báo cáo tài chính"),
    ("Hồ sơ tài chính", "Báo cáo tài chính kỳ gần nhất trong năm hiện hành", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", ""),
    ("Hồ sơ tài chính", "Tờ khai thuế GTGT 12 tháng gần nhất và quyết toán thuế TNDN", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", "Đối chiếu doanh thu khai báo"),
    ("Hồ sơ tài chính", "Sao kê tài khoản ngân hàng 12 tháng gần nhất", True,
     "Điều 7 Thông tư 39/2016/TT-NHNN", "Kiểm chứng dòng tiền thực tế"),
    ("Hồ sơ tài chính", "Bảng kê dư nợ tại các tổ chức tín dụng khác", True,
     "Điều 10 Thông tư 11/2021/TT-NHNN", "Đối chiếu với dữ liệu CIC"),
    ("Hồ sơ tài chính", "Bảng kê công nợ phải thu, phải trả tại thời điểm gần nhất", False,
     "", ""),
    ("Hồ sơ tài sản bảo đảm", "Giấy chứng nhận quyền sử dụng đất thửa số 217 (bản gốc)", True,
     "Điều 317 Bộ luật Dân sự 2015", "Bàn giao bản gốc khi ký hợp đồng thế chấp"),
    ("Hồ sơ tài sản bảo đảm", "Văn bản đồng ý thế chấp của vợ/chồng đồng sở hữu", True,
     "Nghị định 21/2021/NĐ-CP", "Có công chứng"),
    ("Hồ sơ tài sản bảo đảm", "Hợp đồng mua bán và hoá đơn 04 xe đầu kéo", True,
     "Nghị định 21/2021/NĐ-CP", "Cơ sở nhận thế chấp tài sản hình thành trong tương lai"),
    ("Hồ sơ tài sản bảo đảm", "Chứng thư thẩm định giá của tổ chức thẩm định giá độc lập", True,
     "", "Bắt buộc với bất động sản bảo đảm"),
    ("Hồ sơ tài sản bảo đảm", "Hợp đồng bảo hiểm vật chất xe, người thụ hưởng là ngân hàng", True,
     "", "Nộp trong vòng 15 ngày kể từ ngày đăng ký xe"),
    ("Hồ sơ tài sản bảo đảm", "Giấy chứng nhận đăng ký biện pháp bảo đảm", True,
     "Nghị định 21/2021/NĐ-CP", "Thực hiện sau khi ký hợp đồng thế chấp"),
]

RUI_RO = [
    ("Rủi ro tập trung khách hàng: 03 hợp đồng vận chuyển dài hạn chiếm khoảng 62% sản lượng "
     "dự kiến của đội xe mở rộng.", "Trung bình",
     "Yêu cầu công ty duy trì tối thiểu 05 đối tác vận chuyển; theo dõi sản lượng thực hiện "
     "hằng quý; đưa điều khoản thông báo ngay khi một hợp đồng lớn bị chấm dứt."),
    ("Rủi ro giá nhiên liệu: chi phí nhiên liệu chiếm khoảng 38% giá vốn, biến động giá dầu "
     "làm giảm biên lợi nhuận.", "Trung bình",
     "Kiểm tra điều khoản điều chỉnh giá cước theo giá nhiên liệu trong hợp đồng vận chuyển; "
     "đặt ngưỡng cảnh báo khi biên lợi nhuận sau thuế giảm dưới 4%."),
    ("Rủi ro giá trị tài sản bảo đảm: xe đầu kéo là động sản, khấu hao nhanh và có thể bị "
     "di dời khỏi địa bàn.", "Trung bình",
     "Mua bảo hiểm vật chất xe với người thụ hưởng là ngân hàng trong suốt thời gian vay; "
     "gắn thiết bị giám sát hành trình; định giá lại tài sản bảo đảm mỗi 12 tháng."),
    ("Rủi ro pháp lý về tài sản hình thành trong tương lai: quyền sở hữu 04 xe chỉ hoàn tất "
     "sau khi đăng ký xe.", "Thấp",
     "Giải ngân chuyển khoản trực tiếp cho bên bán; giữ hoá đơn và hợp đồng mua bán; hoàn tất "
     "đăng ký biện pháp bảo đảm trong vòng 30 ngày kể từ ngày nhận xe."),
    ("Rủi ro sử dụng vốn sai mục đích do một phần vốn vay là vốn lưu động.", "Thấp",
     "Giải ngân theo tiến độ và theo chứng từ; kiểm tra sử dụng vốn trong vòng 30 ngày sau "
     "mỗi lần giải ngân theo Điều 24 Thông tư 39/2016/TT-NHNN."),
    ("Rủi ro cạnh tranh về giá cước trên tuyến Bắc - Trung khi nhiều doanh nghiệp cùng mở rộng "
     "đội xe.", "Trung bình",
     "Theo dõi hệ số sử dụng xe hằng quý; yêu cầu báo cáo sản lượng và giá cước bình quân; "
     "xem xét giảm hạn mức nếu hệ số sử dụng xe xuống dưới 80% trong 02 quý liên tiếp."),
]

KHUYEN_NGHI = [
    "Bổ sung chứng thư thẩm định giá của tổ chức thẩm định giá độc lập cho thửa đất số 217 "
    "trước khi trình phê duyệt.",
    "Cung cấp bảng kê dư nợ tại các tổ chức tín dụng khác và đối chiếu với dữ liệu CIC để "
    "xác định chính xác tổng nghĩa vụ nợ.",
    "Hoàn thiện hợp đồng mua bán 04 xe đầu kéo có xác nhận tiến độ giao xe, làm cơ sở xây "
    "dựng lịch giải ngân theo tiến độ.",
    "Bổ sung phụ lục hợp đồng vận chuyển thể hiện điều khoản điều chỉnh giá cước theo biến "
    "động giá nhiên liệu.",
    "Cam kết chuyển doanh thu từ 03 hợp đồng vận chuyển về tài khoản mở tại ngân hàng cho vay "
    "để kiểm soát nguồn trả nợ.",
    "Mua bảo hiểm vật chất cho 04 xe đầu kéo với người thụ hưởng là ngân hàng, nộp bản gốc "
    "trong vòng 15 ngày kể từ ngày đăng ký xe.",
]


# ------------------------------------------------------------- dựng hồ sơ


def _dossier_goc() -> Dossier:
    from ..schemas import ChecklistItem, RiskItem

    d = Dossier(
        tieu_de="HỒ SƠ ĐỀ NGHỊ CẤP TÍN DỤNG",
        ngay_lap="15/03/2026",
        noi_lap="Hà Nội",
        to_chuc_tin_dung="Ngân hàng TMCP Công Thương Việt Nam — Chi nhánh Bắc Từ Liêm",
        ben_vay=BEN_VAY,
        de_nghi_vay=DE_NGHI_VAY.model_copy(),
        tom_tat_phuong_an=TOM_TAT_PHUONG_AN,
        phuong_an_su_dung_von=list(PHUONG_AN_SU_DUNG_VON),
        phuong_an_tra_no=PHUONG_AN_TRA_NO,
        tai_san_bao_dam=[t.model_copy() for t in TAI_SAN_BAO_DAM],
        tinh_hinh_tai_chinh=[r.model_copy() for r in TINH_HINH_TAI_CHINH],
        danh_muc_ho_so=[
            ChecklistItem(nhom=n, ten_tai_lieu=t, bat_buoc=b, can_cu_phap_ly=c, ghi_chu=g)
            for n, t, b, c, g in DANH_MUC_HO_SO
        ],
        can_cu_phap_ly=[c.model_copy() for c in CAN_CU_PHAP_LY],
        danh_gia_rui_ro=[RiskItem(rui_ro=r, muc_do=m, bien_phap=b) for r, m, b in RUI_RO],
        khuyen_nghi=list(KHUYEN_NGHI),
        ghi_chu=GHI_CHU_MAU,
        la_ho_so_mau=True,
    )

    # Bản mẫu coi như khách hàng đã nộp đủ toàn bộ giấy tờ bắt buộc
    d.ho_so_cung_cap = readiness.danh_muc_giay_to(d.ben_vay.loai_hinh)
    for g in d.ho_so_cung_cap:
        g.da_co = True
    return d


@lru_cache(maxsize=1)
def ho_so_mau() -> Dossier:
    """Hồ sơ mẫu hoàn chỉnh, đã chạy qua đúng engine thẩm định của hệ thống."""
    d = _dossier_goc()

    bao_cao = readiness.kiem_tra(d)
    kq = valuation.tham_dinh(d, diem_ho_so=bao_cao.diem)

    d.chi_so_tai_chinh = kq.chi_so
    d.tham_dinh_gia_tri = kq.dinh_gia
    d.dong_tien_du_kien = kq.dong_tien
    d.ket_luan_tham_dinh = kq.ket_luan

    # Dựng lại biểu đồ sau khi đã có bảng dòng tiền, để biểu đồ DSCR có số liệu
    kq2 = valuation.tham_dinh(d, diem_ho_so=bao_cao.diem)
    d.bieu_do = kq2.bieu_do
    d.ket_luan_tham_dinh = kq2.ket_luan

    # Điền bằng chữ và tỷ lệ vốn vay cho đầy đủ như hồ sơ thật
    from ..services.dossier_pipeline import _tu_dien_hoa

    _tu_dien_hoa(d)
    return d


def thong_tin_mau() -> dict:
    """Phần tóm tắt hiển thị trên thẻ giới thiệu hồ sơ mẫu ở giao diện."""
    d = ho_so_mau()
    so_tien = d.de_nghi_vay.so_tien
    don_vi = d.de_nghi_vay.don_vi or ""
    if don_vi and don_vi.upper() not in so_tien.upper():
        so_tien = f"{so_tien} {don_vi}"
    return {
        "ten": d.ben_vay.ten,
        "loai_hinh": d.ben_vay.loai_hinh,
        "nganh_nghe": d.ben_vay.nganh_nghe,
        "so_tien": so_tien,
        "thoi_han": d.de_nghi_vay.thoi_han,
        "muc_dich": d.de_nghi_vay.muc_dich_vay,
        "gia_tri_doanh_nghiep": d.tham_dinh_gia_tri.gia_tri_ket_luan_hien_thi,
        "diem_tin_dung": d.ket_luan_tham_dinh.diem,
        "xep_hang": d.ket_luan_tham_dinh.xep_hang,
        "so_tai_lieu": len(d.danh_muc_ho_so),
        "so_can_cu": len(d.can_cu_phap_ly),
        "so_bieu_do": len(d.bieu_do),
    }
