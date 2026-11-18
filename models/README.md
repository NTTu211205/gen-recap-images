# Model xóa nền

Đặt trọng số IS-Net tại `models/isnet-general-use.onnx`.
API load file này trước khi sẵn sàng phục vụ; CLI load khi cần xóa nền.
Runtime không tải model và không dùng `.cache/rembg` hoặc `~/.u2net` để tìm file.
Session được giữ trong RAM để dùng lại, không load ONNX cho từng sản phẩm.

File hiện tại được chuyển từ model đã có trong project. Binary không commit
vào Git; Dockerfile yêu cầu file này trong build context và kiểm tra SHA-256
bằng `models/SHA256SUMS` trước khi tạo image.

Trên máy mới, lấy đúng artifact từ kho model của bạn hoặc nguồn upstream:

```bash
mkdir -p models
curl --fail --location \
  'https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx' \
  --output models/isnet-general-use.onnx
```

Kiểm tra từ root project: `sha256sum -c models/SHA256SUMS` trên Linux;
`shasum -a 256 -c models/SHA256SUMS` trên macOS. Không cập nhật checksum chỉ
để bỏ qua lỗi; xác minh phiên bản model trước khi thay artifact.

Có thể truyền biến môi trường `REMBG_MODEL_PATH` để load trực tiếp một file
IS-Net ONNX tương thích khác. Thiếu hoặc hỏng model sẽ làm startup thất bại;
không có nhánh tự download hay fallback sang cache.
