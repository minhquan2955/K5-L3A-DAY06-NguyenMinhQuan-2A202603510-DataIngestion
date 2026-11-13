# Kiểm tra bài nộp — 13/11/2026

- [x] 58 trang nội dung hợp lệ, PDF snapshot và manifest khớp hash.
- [x] 20 câu đã freeze trước retrieval, 15 dev/5 test, 7 câu filter (3 test), evidence đối chiếu local PDF.
- [x] Model API thật, pgvector bền vững, cosine exact và filter chapter; đã lưu version/config.
- [x] A/B/C cùng corpus/model, B–C chỉ thay filter, C tái dùng vector B.
- [x] 60 trace câu×strategy, mỗi dòng 3 hits; summary dev/test và selection B có trên đĩa.
- [x] REPORT, báo cáo cá nhân, STUDENT, README và experiment log đã điền số liệu thực.
- [x] Audit hỗ trợ AI: 30 coherence samples, 15 test cases, 45 hit metadata và lý do từng nhãn.
- [x] Codex đã đối chiếu lại 20 gold/21 evidence với PDF và điền 30 coherence, 15 test grounding, 45 metadata vào file audit gốc; giữ nguyên frozen inputs. Xem gold_review.json và audit_review.json.
- [ ] Học viên review độc lập nhãn/gold đã điền nếu giảng viên yêu cầu chấm thủ công; chưa có xác nhận của người học.
- [ ] Hoàn tất kiểm tra thủ công cả 5 tiêu chí và ghi rõ người chấm; không dùng điểm AI như chấm tay của học viên.
- [x] Đồng bộ cost CSV: A 0,0240/B 0,0216/C 0 USD; C 0 document token theo log và 0 USD document embedding tăng thêm.
- [ ] Đối soát cost A/B, ghi nguồn/đơn giá/công thức và bổ sung chi phí query nếu có; tổng CSV 0,0456 USD chưa phải hóa đơn đầy đủ ingest/eval.
- [ ] Chốt commit chứa code/artifacts/báo cáo; điền hash vào STUDENT, push và kiểm tra quyền truy cập repo cho người chấm.
- [ ] Nộp link repo theo kênh/thời hạn giảng viên; chưa có bằng chứng đã nộp.

Không cần chạy lại eval chỉ để tăng điểm. Nếu thay đổi sau khi xem test, ghi rõ và tạo test mới khi có thể. Kiểm tra secret trước khi commit; .env và .venv đã được .gitignore loại trừ. Không tạo commit/push trong tác vụ báo cáo này.
