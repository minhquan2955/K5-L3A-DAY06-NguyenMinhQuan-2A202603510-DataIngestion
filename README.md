# Day 06 — Data Ingestion · Nguyễn Minh Quân

MSSV **2A202603510**, lớp **L3A**. Pipeline Python/PDF → chunks → OpenAI embeddings → PostgreSQL/pgvector → benchmark 20 câu. Báo cáo: [REPORT.md](REPORT.md), [bản cá nhân](report/individual/2A202603510_NguyenMinhQuan.md); [nhật ký](artifacts/experiment_log.csv).

## Kết quả đã chạy

Run [run-02](starter/src/results/run-02/) ngày 13/11/2026, text-embedding-3-small/1536 chiều, cosine exact top-3. 58 trang nội dung; A449/B505/C505 chunk. Dev Hit@3: A8/15, B11/15, C11/15. Test Hit@3: cả ba 1/5. Chọn B theo dev; không tinh chỉnh theo test. Audit hỗ trợ AI có lý do trong [audit.assistant.json](starter/src/results/run-02/audit.assistant.json), đã được đối chiếu nguồn và điền vào file audit; biên bản tại `audit_review.json` và `gold_review.json`. Chưa có review độc lập của học viên.

## Setup trên Windows PowerShell

Từ thư mục gốc repo, cần Python 3.11–3.14 và Docker Desktop đang chạy:

```powershell
cd starter
python -m venv src/.venv
.\src\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -p day6_student_starter up -d --wait
.\src\.venv\Scripts\python.exe scripts/check_setup.py
```

Điền `OPENAI_API_KEY`, `EMBEDDING_MODEL=text-embedding-3-small` và DATABASE_URL theo `.env.example`; giữ key trong `.env`. Database local port55433, volume Docker lưu bền vững; không xóa volume khi muốn giữ index. Thư viện/model/database đo thực tế ở [environment.json](starter/src/results/run-02/environment.json).

## Dữ liệu và chạy lại

[chapter1-2.pdf](chapter1-2.pdf) là snapshot PDF 83 trang; [manifest](data/manifest.json) ghi nguồn, quyền, page IDs, 58 trang được tính và SHA256. Nguồn gốc: https://openstax.org/books/foundations-information-systems/pages/1-introduction . Giữ attribution và CC BY-NC-SA 4.0. Nếu thiếu PDF, lấy đúng snapshot theo manifest; bản sách mới có thể khác hash, không sửa hash/gold để giả làm cùng thí nghiệm. Căn cứ giáo dục phi thương mại cho API embedding được ghi trong manifest; xem phạm vi và giới hạn tại REPORT.md.

[questions.json](benchmark/questions.json) có 15 dev/5 test, 7 câu filter. [freeze.json](benchmark/freeze.json) khóa hash và split; run xác minh trước mỗi lần chạy. Không đưa gold vào query/filter. Từ `starter/` dùng một thư mục output mới cho mỗi cấu hình:

```powershell
.\src\.venv\Scripts\python.exe -m src.run --mode prepare --output src/results/reproduce-01
.\src\.venv\Scripts\python.exe -m src.run --mode ingest --output src/results/reproduce-01
.\src\.venv\Scripts\python.exe -m src.run --mode eval --split dev --output src/results/reproduce-01
.\src\.venv\Scripts\python.exe -m src.run --mode eval --split test --output src/results/reproduce-01
```

Ingest/eval gọi API có tính phí. Dùng thư mục output mới để giữ kết quả cũ. Cost CSV: A 0,0240/B 0,0216/C 0 USD; tổng ghi nhận 0,0456 USD, A/B cần đối soát nguồn và đơn giá. C tái dùng vector B nên có 0 document token mới và 0 USD document embedding tăng thêm; chi phí query embedding chưa đo riêng. Tổng document token run-02 là 75.979. Xem REPORT.md về phạm vi chi phí và README pipeline về cách chạy/kiểm tra code.

## Bằng chứng và phần cần hoàn tất

- [summary dev](starter/src/results/run-02/summary.dev.json), [summary test](starter/src/results/run-02/summary.test.json), [selection](starter/src/results/run-02/selection.dev.json).
- [trace dev](starter/src/results/run-02/traces.dev.jsonl), [trace test](starter/src/results/run-02/traces.test.jsonl), [ingest](starter/src/results/run-02/ingest.json).
- [checklist bài nộp](artifacts/submission_check.md): audit/gold đã được Codex kiểm tra và điền; còn review độc lập của học viên, đối soát chi phí API, commit/push và nộp link. Không ghi audit Codex thành nhãn chấm tay của học viên.
- Code đã hiện thực tại [starter/src](starter/src/); hướng dẫn chi tiết [README pipeline](starter/src/README.md). Quy tắc: [GUIDE](GUIDE.md), [BENCHMARK](BENCHMARK.md), [RUBRIC](RUBRIC.md), [SUBMISSION](SUBMISSION.md), [RULES](RULES.md).
