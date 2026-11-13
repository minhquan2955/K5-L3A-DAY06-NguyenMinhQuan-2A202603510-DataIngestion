# Pipeline Day 06

Chạy các lệnh dưới đây từ `starter/`, dùng venv tại `src/.venv`. Đầu vào mặc định: `../data/manifest.json`, `../benchmark/questions.json`, `../benchmark/freeze.json`. Cấu hình môi trường được đọc từ `starter/.env`.

## Kiểm tra và chuẩn bị

```powershell
.\src\.venv\Scripts\python.exe scripts\check_setup.py
.\src\.venv\Scripts\python.exe -m unittest discover -s src -v
.\src\.venv\Scripts\python.exe -m src.run --help
.\src\.venv\Scripts\python.exe -m src.run --mode prepare --output results/run-01
```

`prepare` là chế độ mặc định. Lệnh kiểm tra hash, trang, evidence và split rồi xuất chunk; không dùng API, database hay tính retrieval metrics. Test storage dùng bảng riêng `test_day6_<uuid>` và tự dọn bảng; test điều phối dùng câu hỏi/vector giả lập riêng, không chạy bộ 20 câu của lab.

A dùng cửa sổ 500 ký tự, overlap 50. B nhóm các block tối đa 500 ký tự; C dùng chính chunk B. Đổi tham số qua `--size`, `--overlap`, `--paragraph-size`. B nhận biết dòng trống, dòng giống tiêu đề, bullet/số thứ tự và kết thúc đoạn ngắn. Đây là heuristic vì PDF này không trích xuất được dòng trống giữa các đoạn; cần chấm coherence để đánh giá chất lượng. Chỉ cắt giữa từ khi một token dài hơn giới hạn.

Đầu ra chuẩn bị: `prepared.json` chứa thống kê/config, `chunks.A/B/C.jsonl` chứa chunk và metadata, `coherence_samples.json` chứa cùng 10 vị trí nguồn cho mỗi chiến lược với nhãn để trống. Nhãn đã điền được giữ khi chuẩn bị/ingest lại cùng cấu hình. Mỗi thư mục output dành cho một cấu hình; thay model/đầu vào/chunk thì dùng output mới. Dấu vân tay của toàn bộ chunk gắn nội dung và metadata vào index/selection, kể cả khi thay thuật toán mà số chunk không đổi.

## Ingest

Manifest hiện ghi căn cứ học tập phi thương mại do học viên cung cấp cho lần gọi embeddings API; cờ `external_ai_upload_ready` đã được cập nhật và hash manifest được ghi trong freeze. Xem REPORT.md để biết phạm vi và giới hạn. Dùng output mới khi thay cấu hình; không chỉnh câu hỏi/test sau khi xem kết quả.

```powershell
.\src\.venv\Scripts\python.exe -m src.run --mode ingest --output results/run-01
```

Model lấy từ `EMBEDDING_MODEL`, mặc định `text-embedding-3-small`, số chiều mặc định 1536. API chạy theo batch 64 (`--batch-size`), C dùng lại vector B. `ingest.json` ghi số chunk, token và thời gian. Chi phí chỉ là ước tính khi truyền `--price-per-million` theo giá provider tại thời điểm chạy; nếu không, giá trị là null. API/backend lỗi sẽ báo lỗi, không fallback sang vector giả.

PostgreSQL lưu bền vững và tìm cosine exact. Nạp lại không nhân đôi: `upsert` nhận **toàn bộ snapshot của từng document**, thay snapshot trong transaction và giữ các document khác. Để xử lý document không còn chunk, truyền `document_ids=[...]` cùng hai danh sách chunk/vector rỗng. Không gọi upsert theo từng batch API riêng lẻ. Lab chạy một tiến trình ghi tại một thời điểm.

## Dev rồi test

Sau khi ingest thành công:

```powershell
.\src\.venv\Scripts\python.exe -m src.run --mode eval --split dev --output results/run-01
.\src\.venv\Scripts\python.exe -m src.run --mode eval --split test --output results/run-01
```

Dev tạo `selection.dev.json`, chọn theo Hit@3, rồi Hit@1, rồi ít chunk hơn; nếu vẫn hòa, theo thứ tự A/B/C. Test yêu cầu selection và index khớp cấu hình hiện tại. Chỉ câu hỏi được đưa vào query embedding; gold/đáp án dùng sau retrieval. A/B không áp dụng filter người dùng; C chỉ áp dụng khi câu hỏi có filter. Cả ba cùng giới hạn corpus và dấu vân tay ingest.

Mỗi split xuất `traces.<split>.jsonl`, `summary.<split>.json`, `manual_audit.<split>.json`. Một hit tự động cần đúng document/trang và đủ evidence chuẩn hóa; chấp nhận `alternative_gold`. Bằng chứng tương đương khác cần người chấm xác nhận. Chỉ đúng trang hoặc ghép evidence bị cắt qua nhiều chunk không tự được tính là hit chính.

Grounding, metadata correctness và filter compliance để trống cho người chấm. Câu yêu cầu filter cần chấm compliance cho cả A/B/C; chỉ ghi N/A khi câu không yêu cầu filter. Không suy ra nhãn thủ công từ exact match. Lệnh từ chối ghi đè output eval đã tồn tại, giữ trace và nhãn đã chấm. Dùng thư mục mới cho thí nghiệm mới và không chỉnh cấu hình theo test.

Xem quy tắc lab và attribution trong `../../GUIDE.md`, `../../BENCHMARK.md`, `../../benchmark/README.md`. Tài liệu kỹ thuật: [pgvector](https://github.com/pgvector/pgvector), [tham số SQL psycopg](https://www.psycopg.org/psycopg3/docs/basic/params.html).
