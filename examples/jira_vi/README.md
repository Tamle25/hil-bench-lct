# Dữ liệu Jira tiếng Việt mẫu

DEMO-101 và toàn bộ dữ liệu giao hàng trong thư mục này được tạo riêng cho ví dụ. Mỗi tình huống đi kèm đề bài, blocker do người duyệt cung cấp, dữ liệu SQLite, truy vấn chuẩn và câu hỏi dùng để kiểm định judge.

```powershell
python -m hil_bench.jira_dataset examples/jira_vi/jira_export.json examples/jira_vi/annotations.json
```

Bản `jira_export.json` sử dụng định dạng Atlassian Document Format cho phần mô tả. Ví dụ dùng `problem_source: jira_description` để lấy mô tả đã được duyệt. Với ticket nội bộ, dùng trường `problem` trong bản chú thích để cung cấp đề đã làm sạch. Mọi đường dẫn đến dữ liệu, test hoặc truy vấn đều tính từ thư mục chứa `annotations.json`.
