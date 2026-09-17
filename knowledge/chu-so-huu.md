# Chủ sở hữu và các vai trò quản lý tàu

## Các vai trò
- Chủ sở hữu đăng ký (registered owner): pháp nhân đứng tên tàu trên sổ đăng ký của quốc gia treo cờ. Thường là một công ty "một tàu" (single-ship company) lập ở nơi có chi phí thấp.
- Chủ sở hữu hưởng lợi (beneficial owner): tập đoàn hoặc cá nhân thực sự sở hữu và hưởng lợi từ tàu, đứng sau chủ sở hữu đăng ký.
- Nhà khai thác (operator): công ty khai thác thương mại tàu, ví dụ hãng tàu container đưa tàu vào tuyến dịch vụ. Tàu có thể do hãng khác sở hữu và được thuê (charter).
- Quản lý thương mại (commercial manager): tìm hàng, ký hợp đồng thuê tàu, quản lý doanh thu.
- Quản lý kỹ thuật (technical manager): bảo dưỡng, sửa chữa, cung ứng, thuyền viên.
- Quản lý ISM (ISM manager): công ty chịu trách nhiệm hệ thống quản lý an toàn theo Bộ luật ISM (International Safety Management), nắm giấy chứng nhận DOC.
Một công ty có thể giữ nhiều vai trò trên cùng một tàu.

## Quốc gia treo cờ
Quốc gia treo cờ (flag state) là nơi tàu đăng ký và chịu sự quản lý pháp lý. "Cờ thuận tiện" (flag of convenience) như Panama, Liberia, Quần đảo Marshall được nhiều chủ tàu chọn vì thủ tục và chi phí, nên quốc gia treo cờ thường khác quốc gia của chủ sở hữu hưởng lợi.

## Dữ liệu chủ sở hữu trong hệ thống
- Dữ liệu ở dạng dài: mỗi dòng là một vai trò của một công ty đối với một tàu, kèm quốc gia của công ty và ngày bắt đầu vai trò (có thể rỗng).
- Không phải tàu nào cũng có thông tin chủ sở hữu; khi không có, hệ thống trả lời là không có dữ liệu.
- Tên công ty viết hoa và có biến thể (ví dụ khác nhau ở hậu tố CO, LTD, PTE, CORP). Hệ thống chuẩn hoá bằng cách bỏ dấu câu và hậu tố pháp lý ở cuối tên để gộp các biến thể của cùng một tên. Các pháp nhân khác tên (ví dụ chi nhánh ở quốc gia khác) không bị gộp và được liệt kê riêng để người dùng tự chọn.
- Câu hỏi "tàu do công ty X khai thác" ứng với vai trò operator; "công ty X sở hữu" thường hiểu là registered owner, nếu cần có thể xem thêm beneficial owner.
