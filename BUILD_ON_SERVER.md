# Build trên server

Gói gồm source, .env hiện tại, model ONNX, catalog, background và Dockerfile.
Không chứa Docker image đã build, .venv, cache hoặc output.

Giải nén rồi chạy từ thư mục MWG-VideoRecap:

```bash
chmod 600 .env
sha256sum -c models/SHA256SUMS
docker build -t mwg-videorecap:local .
docker run -d \
  --name mwg-videorecap \
  --restart unless-stopped \
  --env-file .env \
  -p 8000:8000 \
  --mount type=volume,source=mwg-recap-output,target=/app/output \
  mwg-videorecap:local
```

Docker build cần base images ghcr.io/astral-sh/uv:0.13.6 và
python:3.12-slim-bookworm, các package Debian và dependency Python trong uv.lock.
Server phải lấy được chúng qua Internet, mirror nội bộ hoặc cache phù hợp.
Gói source này không phải bộ dependency để build hoàn toàn offline.
Chỉ cho phép gọi gateway MWG là chưa đủ để thực hiện bước build.

Runtime load model ONNX có sẵn, không tải trọng số. Dịch tên và Gen ảnh
sử dụng gateway MWG. Xem README.md để kiểm tra health, log và lấy output.
.env có thông tin xác thực; không commit hoặc chia sẻ gói này công khai.
