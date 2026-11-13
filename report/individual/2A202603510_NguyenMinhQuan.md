# Báo cáo Day 06 — Nguyễn Minh Quân

- MSSV: 2A202603510; lớp L3A. Ngày thí nghiệm: 13/11/2026.
- Run được báo cáo: `starter/src/results/run-02`; model `text-embedding-3-small`, 1536 chiều.
- Trạng thái: retrieval, audit và kiểm tra gold đã hoàn tất bởi Codex theo yêu cầu học viên. Người thực hiện: Nguyễn Minh Quân; Codex hỗ trợ điền nhãn và kiểm tra nguồn. Chưa ghi nhận chấm độc lập của học viên.

## Dữ liệu và pipeline

Corpus: *Foundations of Information Systems*, Dr. Mahesh S. Raisinghani, OpenStax/Rice University; trích chương 1–2 trong `chapter1-2.pdf`. Giấy phép CC BY-NC-SA 4.0, ghi công và ShareAlike theo manifest. Truy cập miễn phí: https://openstax.org/books/foundations-information-systems/pages/1-introduction . Manifest ghi căn cứ giáo dục phi thương mại do học viên cung cấp; không có thư cho phép riêng của OpenStax. Ghi chú riêng về LLM/generative AI trong trang sách vẫn được lưu; cờ API trong manifest áp dụng cho lần thực hành embeddings. Không kết luận đây là quyền sử dụng AI không giới hạn. Chính sách API: https://developers.openai.com/api/docs/guides/your-data (không training mặc định; có thể giữ abuse logs 30 ngày).

PDF 83 trang vật lý; tính 58 trang nội dung: 11–36 và 45–76, tổng 191.045 ký tự chuẩn hóa. Loại 25 trang bìa/mục lục/preface/terms/summary/câu hỏi hoặc không có body; p44 chỉ có footer. Số trang trong gold là trang vật lý 1-based; printed page được lưu riêng, thường bằng physical−4.

Pipeline dùng pypdf đọc từng trang, thay ligature theo font, NFC, bỏ footer xác định và chuẩn hóa whitespace; giữ truy vết document/source/page, offset ký tự và trạng thái extraction. Không OCR, không dehyphenation. Các bảng, caption và ngắt dòng PDF vẫn có thể làm giảm coherence. A chia cửa sổ 500 ký tự, overlap 50; B nhóm block/heading/bullet tối đa 500 ký tự, không overlap; C dùng đúng chunk/vector B và thêm filter được câu hỏi cung cấp. B là heuristic vì PDF này không có dòng trống phân đoạn; vẫn có chunk bắt đầu hoặc kết thúc giữa ý.

PostgreSQL 16.16 (Debian 16.16-1.pgdg12+1), pgvector 0.8.7; bảng `public.day6_chunks` trong database `day6_lab`, Docker Compose, cổng local 55433, lưu trên volume Docker. Cosine exact (`<=>`), top-3. Metadata: `document_id`, `source`, `page`, `chapter`, `language`, `printed_page`, offset/char_count/chunking. Chapter lấy từ ranh giới chương trong PDF và manifest, có giá trị 1/2 để lọc; không suy chapter từ gold lúc truy vấn. Ngôn ngữ corpus en; câu hỏi vi nên đây là truy xuất xuyên ngôn ngữ.

Python 3.14.2; thư viện: openai 3.50.0, psycopg 3.3.8, pypdf 6.21.4, python-dotenv 1.2.4. Provider không công bố revision bất biến của model alias trong lần gọi này; không tự suy phiên bản weights. Trích phiên bản và số đo ingest từ `environment.json` và `ingest.json`; cost bổ sung từ `artifacts/experiment_log.csv`. Nạp lại thay snapshot mỗi document/strategy trong transaction, khóa `(strategy, chunk_id)` ngăn nhân đôi; kiểm tra DB hiện tại có A449/B505/C505 ID không trùng. Suite 21 test trước đó đã kiểm tra idempotence bằng dữ liệu tổng hợp; chưa ingest corpus lần hai để đo lại.

## Benchmark và cấu hình

20 câu q01–q20 đã freeze trước retrieval; dev q01–q15 (mục 1.1/1.2/2.1/2.2), test q16–q20 (1.3/1.4/2.3/2.4/2.5). Có 7 filter chương: q02/q06/q09/q12 dev, q16/q18/q20 test. 20 evidence chính và 1 evidence thay thế đã được Codex đối chiếu lại local PDF; đáp án kỳ vọng phù hợp evidence. Biên bản tại `starter/src/results/run-02/gold_review.json`; giữ nguyên gold và freeze. Corpus cùng sách nên vẫn có rò rỉ thuật ngữ giữa chủ đề. Chỉ question và filter đầu vào đi vào truy xuất; gold dùng sau retrieval.

Hit yêu cầu một chunk đúng nguồn/trang và chứa đủ evidence chuẩn hóa hoặc alternative gold; evidence bị cắt qua nhiều chunk không được cộng thành hit chính. Chính sách chọn: Hit@3 dev, rồi Hit@1, rồi ít chunk hơn; hòa cuối chọn theo A/B/C. Quy tắc tie cuối được ghi trong code và selection. B được chọn lúc 2026-11-13T11:56:22.419263+00:00 trước test, giữ nguyên cấu hình sau khi xem test.

## Kết quả retrieval

| Strategy | Split | Hit@1 n/N | Evidence Hit@3 n/N | Chunk | Ingest giây | Chi phí ước tính USD (CSV) |
|---|---|---|---|---|---|---|
| A | dev | 3/15 | 8/15 | 449 | 11.323 | 0.0240 |
| B | dev | 3/15 | 11/15 | 505 | 10.506 | 0.0216 |
| C | dev | 3/15 | 11/15 | 505 | 0.972 | 0.0000 |
| A | test | 1/5 | 1/5 | 449 | 11.323 | 0.0240 |
| B | test | 0/5 | 1/5 | 505 | 10.506 | 0.0216 |
| C | test | 0/5 | 1/5 | 505 | 0.972 | 0.0000 |

Thời gian và cost theo chiến lược lặp lại ở dev/test để tham chiếu, không cộng hai lần. CSV ghi A = 0.0240 USD, B = 0.0216 USD và C = 0 USD; tổng ghi nhận 0.0456 USD. A/B là ước tính học viên nhập bổ sung, cần đối soát đơn giá/công thức. C = 0 USD chỉ là chi phí document embedding tăng thêm khi tái dùng vector B; query embedding vẫn gọi API và chưa đo chi phí riêng. Tổng này chưa đại diện hóa đơn toàn bộ ingest/eval.

Log ingest ghi A 40.086 document token, B 35.893 và C 0 token mới; tổng document token đo được là 75.979. CSV đã sửa C về 0 token theo log. Log gốc giữ estimated_cost_usd=null vì lúc chạy không truyền đơn giá. Thời điểm ingest: 2026-11-13T11:55:36.122362+00:00.

Trace: `starter/src/results/run-02/traces.dev.jsonl` (45 dòng) và `traces.test.jsonl` (15 dòng), mỗi dòng 3 hit; summary và selection cùng thư mục. Lệnh setup/run tại README gốc và `starter/src/README.md`.

## Audit năm khía cạnh

**Người thực hiện và phụ trách audit: Nguyễn Minh Quân. Công cụ hỗ trợ điền nhãn và kiểm tra nguồn: Codex.** Codex hỗ trợ code, soạn gold, chạy eval và báo cáo; học viên cần kiểm tra nguồn/nhãn và giải thích được pipeline. Cùng trợ lý soạn câu hỏi và đánh giá nên có nguy cơ thiên lệch, chưa có chấm độc lập. Bản ghi đọc từng mẫu có lý do tại `starter/src/results/run-02/audit.assistant.json`. Đã điền `coherence_samples.json` và `manual_audit.test.json` với điểm, lý do, tên học viên Nguyễn Minh Quân và thông tin Codex hỗ trợ tạo nhãn. Biên bản xác minh `audit_review.json` ghi 30 mẫu coherence, 15 bộ test top-3 và 45 hit metadata. Các chỉ số trong bảng được tính lại từ nhãn đã điền; đây là audit hỗ trợ AI, chưa phải xác nhận độc lập của học viên. Audit dev là phần tùy chọn, chưa chấm grounding dev. Thang coherence/grounding 0=không đủ ý/bằng chứng, 1=một phần, 2=đủ. Nhãn grounding dựa trên đọc top-3, không suy ra trực tiếp từ Hit@3.

| Strategy | Coherence /2 (n) | Metadata đủ đúng | Filter đúng top-3 | Grounding số câu 0/1/2 | Grounding TB /2 |
|---|---|---|---|---|---|
| A | 1.0 (10) | 15/15 | 3/3 | 2/2/1 | 0.8 |
| B | 1.4 (10) | 15/15 | 2/3 | 3/1/1 | 0.6 |
| C | 1.4 (10) | 15/15 | 3/3 | 3/1/1 | 0.6 |

Coherence dùng cùng 10 vị trí midpoint trên 10 trang nội dung đầu (p11–20), chọn trước retrieval; C giống B. Mẫu chỉ thuộc chương 1 nên không đại diện toàn corpus. Metadata kiểm tra đủ 45 hit của 5 test × 3 strategy × top-3 so với manifest và text trang PDF; 15 hit/strategy. Filter dùng 3 câu test q16/q18/q20; A vẫn có thể tuân thủ tình cờ; B sai chương ở q20, C loại p25 chương 1. Chapter giúp giới hạn phạm vi nhưng không đảm bảo tìm đúng evidence trong cùng chương.

## Phân tích và lựa chọn

A–B: B tăng Hit@3 dev từ 8/15 lên 11/15 (+20 điểm phần trăm), Hit@1 giữ 3/15. Coherence sơ bộ tăng 1,0 lên 1,4/2; B có thêm 56 chunk (+12,5%) nhưng không lặp overlap nên document embedding token giảm 4.193 (10,5%). Runtime chỉ một lần đo, không đủ kết luận tốc độ ổn định. B–C: cùng chunk/vector, chỉ thay filter; dev Hit@3 cùng 11/15, test cùng 1/5. C tăng tuân thủ filter 2/3 lên 3/3 so với B, nhưng chưa tăng hit. C ingest ngắn vì dùng lại vector B, không chứng minh một lần chạy độc lập của C rẻ hơn toàn bộ B.

Chọn B theo dev. Test cho A Hit@1 1/5, B/C 0/5 và cả ba Hit@3 1/5; không đổi lựa chọn sau test. Test chỉ 5 câu, một câu tương đương 20 điểm phần trăm; không suy B tốt nhất nói chung. Kết quả thấp cần được giữ và giải thích.

- **q18**, gold p62, freemium: A top-1 p62 có đủ định nghĩa nên hit; B/C trả về p45/p75/p63 (caption vận hành, Gojek, digital product). C đúng chương 2 nhưng không sửa được lệch ngữ nghĩa trong chương.
- **q19**, gold p70, BPI: B/C top-1 đúng p70 và có tên BPI nhưng dừng ở “existing business”, mất “processes to identify areas for improvement”. Không đủ quote nên Hit@3=0; audit grounding=1 do có thông tin liên quan. A cũng không giữ định nghĩa đầy đủ.
- **q17**, gold p35, edge computing: B/C top-2 có định nghĩa đầy đủ (hit); A top-1 bị cắt phần đầu, chỉ được grounding=1 dù có tên thuật ngữ. Điều này minh họa khác biệt giữa đánh giá exact evidence và đủ ngữ cảnh.

Nếu mở rộng, thử điều chỉnh chunk theo câu/đoạn trên dev, xử lý bảng/caption và kiểm tra truy xuất xuyên ngôn ngữ; không tối ưu thêm trên 5 test đã xem. Cần tập test mới lớn hơn và đa tài liệu. Không thay gold/metric để làm tăng số liệu hiện tại.
