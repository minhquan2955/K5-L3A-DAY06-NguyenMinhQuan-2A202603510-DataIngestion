# Corpus và benchmark cho lab Day 06

Nguồn: *Foundations of Information Systems*, Dr. Mahesh S. Raisinghani, OpenStax, Rice University. Trích đoạn cục bộ: [`chapter1-2.pdf`](../chapter1-2.pdf). Access for free at <https://openstax.org/books/foundations-information-systems/pages/1-introduction>.

Nội dung trích dẫn và bản chuyển thể từ nguồn được ghi nhận theo [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Giữ attribution của bên thứ ba khi tái sử dụng hình ảnh. Trang lời nói đầu của PDF (trang PDF 5) ghi giấy phép này. Trang attribution hiện tại của OpenStax còn nêu điều kiện xin phép bằng văn bản khi đưa nội dung vào generative AI offerings. Repo chưa có tài liệu xác nhận quyền đó; manifest ghi `ai_specific_permission: not_supplied` và `external_ai_upload_ready: false`. Cần làm rõ điều kiện này trước khi gửi corpus lên API.

## Các tệp

- [`../data/manifest.json`](../data/manifest.json): JSON UTF-8 mô tả nguồn, giấy phép, snapshot SHA-256, số ký tự từng trang, phạm vi được tính và metadata.
- [`questions.json`](questions.json): 20 câu hỏi, đáp án và gold evidence; 15 câu dev, 5 câu test.
- [`freeze.json`](freeze.json): thời điểm cố định bộ câu hỏi, danh sách ID dev/test, hash dữ liệu/câu hỏi và kết quả kiểm chứng evidence.

## Phạm vi corpus

| Phần | Trang PDF cục bộ, tính từ 1 | Trang in trên sách | Số trang tính |
|---|---|---|---|
| Chương 1 — Fundamentals of Information Systems | 11–36 | 7–32 | 26 |
| Chương 2 — Data Management and Information Systems Business Strategies | 45–76 | 41–72 | 32 |
| Tổng | | | **58** |

Chỉ các trang có `included: true` trong manifest được ingest. Cả A, B và C phải dùng cùng tập 58 trang này, bao gồm các trang là nguồn của câu test. Không đưa đáp án hoặc bộ câu hỏi vào index.

Loại 25 trang: mục lục (1–4), lời nói đầu/danh sách cộng tác viên (5–10), và phần thuật ngữ, tổng kết, câu hỏi cuối chương (37–44, 77–83). Việc loại tổng kết và thuật ngữ giúp hạn chế các bản lặp của đáp án. Trang 44 chỉ còn footer, không có thân bài sau khi bỏ footer. Không dùng quy tắc 1.500 ký tự để tự động công nhận trang PDF; tiêu chí đó của lab dành cho nguồn không phân trang.

`page` và `gold_page` là số trang vật lý trong **PDF cục bộ 83 trang**, không phải trang trong bản PDF toàn bộ cuốn sách. Từ trang PDF 5 trở đi: `printed_page = page - 4`. Mỗi chunk cần `document_id = openstax-foundations-is-ch1-2`, `source = chapter1-2.pdf`, `page`, và `chapter` kiểu số nguyên 1 hoặc 2.

## Chuẩn hóa và evidence

Trích xuất bằng pypdf 6.21.4. PDF có bảng mã ligature lỗi; cần sửa **theo font**, theo bảng `normalization.font_specific_ligature_replacements` trong manifest. Cùng một mã U+FFFF có nghĩa khác nhau ở font thân bài và font tiêu đề; không thay đồng loạt trên toàn trang. Không OCR, không tự ghép từ bị ngắt bằng dấu gạch nối, không dựng lại bố cục bảng/hình.

Sau khi sửa ligature, chuẩn hóa Unicode NFC và bỏ các dòng footer được mô tả trong manifest. Để đếm ký tự và kiểm chứng evidence, gộp whitespace thành một dấu cách rồi strip. `evidence_normalized_char_start` và `evidence_normalized_char_end` là chỉ số ký tự Python, bắt đầu từ 0, kết thúc không bao gồm ký tự tại chỉ số end, trên chuỗi trang đã chuẩn hóa theo cách này. Đây không phải byte offset hay tọa độ trên PDF. Pipeline có thể giữ xuống dòng để chunk theo đoạn, nhưng phải dùng cùng quy tắc so khớp evidence.

Tổng 191.045 ký tự chuẩn hóa trên 58 trang được tính. Cả 20 evidence chính và 1 evidence thay thế đều đã khớp đúng trang sau chuẩn hóa. Q01 có nguồn bằng chứng hợp lệ ở cả trang 12 và 13; chấp nhận một trong hai. Không có lỗi trích xuất trang. Còn một số khoảng trắng trong từ và ngắt từ theo dòng do PDF gốc; không tự sửa bằng suy đoán.

## Thiết kế dev/test

- **Dev:** q01–q15. Chủ đề thuộc mục 1.1, 1.2, 2.1 và 2.2.
- **Test:** q16–q20. Giữ lại các chủ đề thuộc mục 1.3, 1.4, 2.3, 2.4 và 2.5.
- **Filter:** 7 câu, gồm 4 dev (q02, q06, q09, q12) và 3 test (q16, q18, q20). Mỗi câu nêu rõ chương trong chính yêu cầu. `filter.chapter` là phạm vi người dùng cung cấp trước khi truy xuất, không được suy ra từ gold.
- Câu hỏi và đáp án tiếng Việt; nguồn/evidence tiếng Anh. Đây là benchmark truy xuất xuyên ngôn ngữ, cần ghi rõ khi phân tích lỗi.
- Câu hỏi do trợ lý hỗ trợ soạn từ các đoạn nguồn đã đọc; exact substring được kiểm chứng bằng chương trình. Học viên cần đọc, hiểu và rà soát đáp án trước khi nộp. Chưa có nhãn coherence, metadata hay grounding thủ công.

Chia theo mục để giảm trùng chủ đề giữa dev và test, không chia ngẫu nhiên các câu gần giống nhau. Tuy nhiên, cả hai tập vẫn đến từ cùng cuốn sách; kiến thức và thuật ngữ có thể lặp giữa các mục. Có 5 câu test, nên kết quả chỉ minh họa trên corpus này và không đủ để suy rộng.

## Quy tắc chạy sau khi hoàn thiện pipeline

1. Kiểm tra hash trong `freeze.json` trước mỗi thí nghiệm. Dùng cùng corpus, bộ câu hỏi, model, số chiều và cosine cho cả ba cấu hình.
2. A: chunk cố định, không filter. B: chunk theo cấu trúc, không filter. C: cùng chunk như B; chỉ áp dụng `filter` khi câu hỏi cung cấp. Câu có `filter: {}` chạy không filter. Chỉ truyền `question` và filter được phép vào truy xuất; không truyền `expected_answer`, `gold_*` hoặc `evidence_quote`.
3. Điều chỉnh và chọn cấu hình bằng **dev**. Tiêu chí chốt trước: ưu tiên Evidence Hit@3, sau đó Hit@1; nếu vẫn hòa, chọn cấu hình có ít chunk hơn. Ghi rõ tham số A/B/C và thời điểm chốt trước khi đánh giá test.
4. Sau khi cố định cấu hình, chạy cùng 5 câu test cho A/B/C; không dùng kết quả test để chỉnh tiếp. Nếu thay câu hỏi/gold sau đó, ghi lý do, tăng phiên bản và lưu lại snapshot cũ; không âm thầm sửa hash để coi là test độc lập.
5. Lưu trace top-3 có ID/text/score/metadata. Một hit cần đúng nguồn/trang và đủ evidence, hoặc một nguồn tương đương được người chấm xác nhận. Chấp nhận `alternative_gold`; không coi việc chỉ đúng trang là đủ. Evidence bị chia qua nhiều chunk là một lỗi của chỉ số chính.
6. Chấm thủ công coherence, metadata và grounding theo `GUIDE.md`/`BENCHMARK.md`. So khớp chuỗi tự động không thay thế được các nhãn này.

Đã chạy retrieval ngày 13/11/2026 tại `starter/src/results/run-02`: 15 dev rồi 5 test, ba cấu hình. Xem `REPORT.md` và summary/trace trong thư mục run. Benchmark, gold và split không đổi sau khi xem kết quả. Nhãn gold và audit cần học viên xác nhận.
