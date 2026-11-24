# MWG Video Recap

Tra tên sản phẩm từ `data/api_crawl_infor_new.json`, gom nhóm theo
`data/category_labels.yaml`, dịch mô tả bằng Qwen, gen ảnh và ghép lên
background tương ứng từ `background/mwg-background-recap-1.png` đến
`background/mwg-background-recap-8.png`.

## Chạy API

```bash
uv sync
uv run python app.py
```

Giữ `.env` hiện có. Nếu chưa có, tạo từ `.env.example` và điền `MWG_API_KEY`,
thêm `MWG_COOKIE` nếu gateway yêu cầu. Không đưa khóa vào payload hoặc source.
Ứng dụng kiểm tra cấu hình, catalog, taxonomy, background, font và load model
lúc khởi động.
Các thay đổi catalog hoặc `.env` cần khởi động lại API.

- Swagger: <http://localhost:8000/api/docs>
- ReDoc: <http://localhost:8000/api/redoc>
- OpenAPI: <http://localhost:8000/api/openapi.json>
- Health: `GET /api/v1/health`

`POST /api/v1/recap` nhận trực tiếp một JSON array gồm **1–50 mã dạng chuỗi**:

```json
["0164779000163", "0164779000164"]
```

```bash
curl --fail-with-body --request POST \
  'http://localhost:8000/api/v1/recap' \
  --header 'Content-Type: application/json' \
  --data '["0164779000163", "0164779000164"]' \
  --output recap_final.png
```

HTTP `200` trả trực tiếp bytes PNG với `Content-Type: image/png` và
`Content-Disposition: inline; filename="recap_final.png"` để hiển thị ảnh.
Trong Postman, chọn **Send** rồi xem ảnh trong response body. Response lỗi là JSON;
không đổi đuôi file lỗi thành PNG.

Mã dạng chuỗi giữ được số `0` ở đầu. Mã trùng hoặc cùng biến thể sản phẩm
được loại trùng theo pipeline hiện có. Nếu bất kỳ mã nào không tồn tại, thiếu
tên hoặc thuộc nhóm không hỗ trợ, API trả `422` trước khi gọi Qwen/Gen ảnh.

API và CLI mặc định gọi Gen ảnh tối đa 2 request đồng thời.
Điều chỉnh trong `.env`: `IMAGE_WORKERS=2` (1–8; đặt 1 để chạy tuần tự). CLI dùng transport
`requests` vẫn Gen ảnh tuần tự vì dùng chung HTTP session; `curl` hỗ trợ
chạy đồng thời. Thứ tự nhóm/nhãn được giữ nguyên, xóa nền chạy tuần tự.
Khi lỗi, không tự retry; những request đã chạy được chờ kết thúc trong timeout,
ảnh gốc đã trả về vẫn được lưu. Log ghi từng request ảnh,
xóa nền cùng generation và ghép ảnh để đo tốc độ thực tế của gateway.

Mỗi trang chứa tối đa 8 nhóm. Nếu có nhiều trang, API xếp toàn bộ trang theo
chiều dọc thành **một ảnh PNG**, giữ đủ nhóm và sản phẩm. File gốc, plan và
ảnh cuối được giữ trong `output/recap_<id>/`; thư mục này không được public
qua API. Dọn các kết quả cũ khi không cần nữa.

Background được chọn theo **số nhóm trên từng trang**, không theo số mã sản
phẩm: 10 sản phẩm cùng một nhóm dùng ảnh 1 bục; 9 nhóm chia thành trang 8 bục
và trang 1 bục. Tọa độ ảnh sản phẩm và nhãn của từng mẫu được cấu hình trong
`src/imaging/background_templates.py`, theo thứ tự trái sang phải, hàng sau
đến hàng trước. Các mẫu dùng bố cục 1, 2, 3, 2–2, 3–2, 3–3, 3–2–2 và 3–2–3.
API kiểm tra đủ 8 file lúc khởi động; pipeline kiểm tra các mẫu cần dùng trước
khi gọi Gen ảnh. Khi thay đổi vị trí bục trong PNG, cần chỉnh tọa độ tương ứng.

Request chờ đến khi gen và ghép ảnh hoàn tất. `MWG_REQUEST_TIMEOUT_SECONDS`
(mặc định 120 giây) áp dụng cho **từng lần gọi MWG**, không phải toàn bộ lượt
recap. Tổng thời gian tăng theo số sản phẩm; client/proxy cần cho phép chờ
đủ lâu. Không tự retry khi upstream lỗi hoặc timeout. Nếu client ngắt kết nối,
lượt gen đang chạy có thể tiếp tục và lưu kết quả trong `output`.

Server mặc định chạy một worker, xử lý một lượt gen tại một thời điểm;
request gen đồng thời nhận `503` cùng `Retry-After`, health vẫn hoạt động.
Giới hạn này thuộc từng process, không phải giới hạn chung giữa nhiều worker.

| HTTP | Ý nghĩa |
| --- | --- |
| 422 | Input không hợp lệ hoặc mã không dùng được; xem `detail` |
| 502 | MWG lỗi hoặc trả dữ liệu không dùng được |
| 503 | Đang xử lý một lượt gen khác |
| 504 | Một lần gọi MWG bị timeout |
| 500 | Lỗi xử lý cục bộ |

Mã được tổ chức theo trách nhiệm; import nội bộ dùng `from src...`:

```text
app.py                         # Khởi tạo và chạy FastAPI
src/
  api/
    dependencies.py            # Cấp service cho endpoint
    v1/router.py               # Khai báo /api/v1
    v1/endpoints/              # Endpoint health và recap
  catalog/                     # Tra productcode, ranking và phân nhóm
  clients/                     # HTTP MWG, Gen ảnh và dịch Qwen
  cli/shopping_recap.py        # Parse tham số và chạy CLI
  core/
    config.py                  # Settings của API
    recap_config.py            # Cấu hình client dùng chung API/CLI
    paths.py                   # Đường dẫn tài nguyên theo root project
  imaging/                     # Decode, tách nền, gom cụm, bố cục và nhãn
  prompts/products.py          # Prompt Gen ảnh và dịch sản phẩm
  schemas/recap.py             # Kiểu input và response lỗi của API
  services/
    recap_pipeline.py          # Gen asset và ghép các trang recap
    recap_service.py           # Điều phối API, preflight, giới hạn đồng thời
  shopping_recap.py            # Entry point tương thích lệnh module cũ
tests/
```

`api` phụ thuộc `services`; service dùng `catalog`, `clients` và `imaging`.
API và CLI gọi chung pipeline; pipeline không phụ thuộc endpoint hay CLI.

## Chạy bằng Docker

Chạy các lệnh bên dưới tại thư mục gốc project. Máy cần Docker Engine hoặc
Docker Desktop đang hoạt động; kiểm tra bằng `docker info`. Không cần cài
Python hoặc uv trên máy host. Container khởi động API qua `app.py`, không
chạy `gen_images.sh`.

### 1. Chuẩn bị cấu hình và model

Giữ nguyên `.env` nếu đã có. Nếu chưa có, tạo từ file mẫu:

```bash
if [ ! -f .env ]; then
  cp .env.example .env
fi
```

Điền các giá trị trong `.env` trước khi chạy container:

| Biến | Cách dùng |
| --- | --- |
| `MWG_API_KEY` | Bắt buộc, API key của gateway MWG |
| `MWG_COOKIE` | Tùy chọn, điền nếu gateway yêu cầu |
| `MWG_REQUEST_TIMEOUT_SECONDS` | Timeout mỗi request MWG; mặc định `120` |
| `IMAGE_WORKERS` | Số request Gen ảnh đồng thời; mặc định `2`, từ 1–8 |

Với `docker run --env-file`, viết dạng `KEY=value`, không dùng `export`
và không bọc giá trị trong dấu nháy: Docker có thể giữ dấu nháy trong giá trị.
Ví dụ đặt `APP_NAME=MWG Video Recap`. File `.env` được truyền lúc chạy,
không được đóng gói vào image.

Build cần các tài nguyên sau:

- `models/isnet-general-use.onnx` và `models/SHA256SUMS`.
- `data/api_crawl_infor_new.json` và `data/category_labels.yaml`.
- Đủ 8 background `background/mwg-background-recap-1.png` đến `-8.png`.

Model ONNX không nằm trong Git. Trên máy mới, chuẩn bị theo
[hướng dẫn model](models/README.md). Dockerfile kiểm tra checksum lúc build.
Model được đóng gói sẵn và load trực tiếp khi API khởi động; không tự tải
trọng số hoặc ghi model vào cache ở runtime. Thiếu/hỏng model sẽ làm startup
thất bại; cần kiểm tra log thay vì chờ request Gen ảnh.

### 2. Build image

```bash
docker build -t mwg-videorecap:local .
```

Bước build cần mạng để lấy base image, package hệ điều hành và dependency
Python từ `uv.lock`. Runtime dùng CPU để xóa nền, có sẵn curl và font tiếng Việt,
chạy bằng user UID/GID `10001`. `.env`, `.venv`, cache và output của máy host
được loại khỏi build context.

### 3. Chạy container

```bash
docker run -d \
  --name mwg-videorecap \
  --restart unless-stopped \
  --env-file .env \
  -p 8000:8000 \
  --mount type=volume,source=mwg-recap-output,target=/app/output \
  mwg-videorecap:local
```

Container chạy nền. Docker tự tạo named volume `mwg-recap-output` nếu chưa có;
plan, ảnh gốc và ảnh final được giữ trong volume khi container bị xóa/tạo lại.
Đây không phải thư mục `./output` trên host. Nếu cổng 8000 đang bận, đổi thành
`-p 8001:8000` và dùng cổng 8001 trong các URL bên dưới.

### 4. Kiểm tra và gọi API

```bash
docker logs --tail 100 -f mwg-videorecap
```

Nhấn `Ctrl+C` để ngừng theo dõi log; container vẫn chạy. Sau khi model load
xong, kiểm tra:

```bash
docker inspect --format '{{.State.Health.Status}}' mwg-videorecap
curl --fail http://localhost:8000/api/v1/health
```

Healthcheck có trạng thái `starting` trong lúc khởi động và chuyển sang
`healthy` khi kiểm tra thành công. Health xác nhận ứng dụng đã sẵn sàng,
không kiểm tra kết nối tới gateway MWG.

Mở Swagger tại <http://localhost:8000/api/docs>, hoặc trong Postman:

- Method: `POST`.
- URL: `http://localhost:8000/api/v1/recap`.
- Header: `Content-Type: application/json`.
- Body → raw → JSON:

```json
["0164779000163", "0164779000164"]
```

Chọn **Send** để xem ảnh PNG trong response body. Request chờ đến khi hoàn tất;
đặt timeout của Postman đủ dài. API key MWG được lấy từ môi trường container,
không cần gửi trong body. Payload và mã lỗi dùng chung với phần
[Chạy API](#chạy-api) ở trên.

### 5. Lấy output về máy

Xem các thư mục kết quả rồi copy toàn bộ output từ container:

```bash
docker exec mwg-videorecap ls /app/output
mkdir -p output-docker
docker cp mwg-videorecap:/app/output/. ./output-docker/
```

Ảnh final nằm trong từng thư mục `recap_<id>/`. Giữ volume
`mwg-recap-output` khi thay container để bảo toàn các kết quả này.

### 6. Dừng, khởi động lại và cập nhật

Dừng hoặc chạy lại chính container hiện tại:

```bash
docker stop -t 180 mwg-videorecap
docker start mwg-videorecap
```

Nên chờ lượt Gen đang chạy hoàn tất trước khi dừng. Đổi `.env` cần **tạo lại
container** để nhận giá trị mới; `docker restart` không đọc lại `--env-file`.
Đổi code, catalog, background hoặc model đóng gói cần build lại image:

```bash
docker build -t mwg-videorecap:local .
docker stop -t 180 mwg-videorecap
docker rm mwg-videorecap
```

Sau đó chạy lại lệnh ở bước 3 với cùng volume. Nếu chỉ đổi `.env`, bỏ qua bước
build. Xóa container bằng lệnh trên không xóa named volume output.

### Xử lý lỗi thường gặp

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| Không kết nối được Docker daemon | Mở Docker Desktop hoặc khởi động Docker Engine rồi chạy `docker info` |
| Build báo thiếu ONNX hoặc sai checksum | Chuẩn bị đúng model theo `models/README.md`; không bỏ kiểm tra checksum |
| ONNX báo `system error number 13` hoặc catalog báo `PermissionError` | Tài nguyên không có quyền đọc. Dockerfile cấp quyền đọc file và truy cập thư mục cho `data`, `background`, `models`; rebuild image và tạo lại container. Nếu bind mount model ngoài, kiểm tra quyền đọc của UID 10001 trên file và quyền đi qua thư mục cha |
| Container thoát ngay hoặc `unhealthy` | Xem `docker logs --tail 100 mwg-videorecap`; kiểm tra key, model, catalog và background |
| Tên container đã tồn tại | Dùng `docker start` cho container cũ, hoặc dừng/xóa rồi tạo lại theo bước 6 |
| Gen trả `502`/`504` | Kiểm tra key/cookie, kết nối gateway từ môi trường Docker, timeout và log từng request |
| Gen trả `503` | Container đang xử lý một lượt recap khác; chờ rồi gửi lại |

Nếu cần model ngoài image, mount file ONNX ở chế độ read-only và đặt
`REMBG_MODEL_PATH` trỏ tới **đường dẫn trong container**. Bảo đảm user UID 10001
đọc được file. Giữ named volume cho output để tránh lỗi quyền ghi của bind mount.

## Chạy CLI

```bash
bash gen_images.sh --productcodes 0164779000163 0164779000164
```

Có thể chạy trực tiếp bằng `uv run python -m src.cli.shopping_recap` với cùng
tham số. Lệnh module cũ `uv run python -m src.shopping_recap` vẫn hoạt động.

## Kiểm tra

```bash
uv run python -m unittest discover -s tests -q
uv run flake8 app.py src tests
```

Tests API giả lập MWG và mô hình tách nền để kiểm tra contract, lỗi, giới hạn
đồng thời và ảnh nhiều trang mà không phát sinh lượt gen thật.
