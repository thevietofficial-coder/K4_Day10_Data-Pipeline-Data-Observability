# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Nguyễn Đình Duy            |
| MSSV               | 2A202601046                |
| Khóa/Lớp         | K4                         |
| Tên nhóm         | SilverFlag                 |
| Vai trò chính    | Vai trò 3 — Cleaning & Corruption (Clean Schema, Corruption, Repair) |
| Repository         | https://github.com/thevietofficial-coder/K4_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Data Cleaning & Normalization | `src/ingestion/cleaning.py`<br>`build_clean_dataframe` | List `PaperRecord` từ Crossref API, `run_date` (datetime) | Cleaned DataFrame (`papers_clean.csv`, `papers_clean.json`) gồm 16 cột chuẩn | Hoàn thành |
| Data Corruption Simulation | `src/ingestion/corruption.py`<br>`corrupt_clean_dataframe` | Cleaned DataFrame, `output_log_path` | Corrupted DataFrame (`papers_clean_corrupted.json`), Corruption Log (`corruption_log.json`) | Hoàn thành |
| Sample Validation & Repair Logic | `script/test_cleaning.py`<br>`src/ingestion/cleaning.py` | Raw JSON records | Script test nghiệm thu CP1-CP6 & Repaired DataFrame (`papers_clean_repaired.json`) | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Thống nhất Schema Contract | Role 4 (`src/retrieval/index.py`) | Đảm bảo đủ 9 cột bắt buộc (`paper_id`, `title`, `text_for_embedding`, `published`, `authors_joined`, `categories_joined`, `summary`, `abs_url`, `pdf_url`), không bị crash khi build Index. |
| Cấu hình Corruption Log cho Observability | Role 5 (`src/observability/quality.py`) | Thêm thông tin `before`/`after`, `record_id`, `type` và `params` chi tiết vào `corruption_log.json` giúp Quality Checks phát hiện chính xác lỗi. |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Làm sạch và chuẩn hóa dữ liệu | `src/ingestion/cleaning.py` | `data/clean/papers_clean.json` (24 bản ghi sạch, 0 duplicate, 0 empty text_for_embedding) | `python -c "import pandas as pd; df=pd.read_json('data/clean/papers_clean.json'); print(len(df))"` |
| Giả lập 6 dạng hỏng dữ liệu có chủ đích | `src/ingestion/corruption.py` | `data/clean/papers_clean_corrupted.json`, `data/results/corruption_log.json` (26 log entries) | `uv run python script/test_cleaning.py` |
| Phục hồi dữ liệu từ nguồn Raw (Repair) | `src/pipelines/corruption_flow.py` | `data/clean/papers_clean_repaired.json` (24 bản ghi khôi phục khớp 100% với Baseline) | `uv run python script/run_corruption_flow.py` |

**Nêu một output cụ thể mà phần việc của bạn tạo ra hoặc giúp xác minh:**
Hàm `corrupt_clean_dataframe` đã tạo ra mớ dữ liệu lỗi với 6 dạng corruption (tỉ lệ 30%), kéo tụt chỉ số `retrieval_hit_rate` của RAG Agent từ **100% (1.0)** xuống **50% (0.5)** và `judge_accuracy` từ **100% (1.0)** xuống **68.75% (0.6875)**, làm bằng chứng thực nghiệm rõ ràng cho báo cáo so sánh 3 trạng thái Baseline - Corrupted - Repaired.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Dữ liệu học thuật thô (Raw Data) lấy từ Crossref API thường chứa mã HTML rác, thiếu thông tin (rỗng summary/title), chuỗi ngày tháng không đồng nhất, hoặc dính các bài báo bị trùng lặp DOI. Nếu đưa trực tiếp vào RAG Pipeline, Vector DB sẽ lưu trữ các đoạn text chất lượng kém, làm sai lệch kết quả tìm kiếm ngữ nghĩa (Retrieval). Ngoài ra, cần một module chủ động phá hoại dữ liệu (Corruption) và khôi phục (Repair) để kiểm thử năng lực quan sát (Data Observability) của hệ thống.

### Cách triển khai
1. **`build_clean_dataframe(records, run_date)`**:
   - Lọc bỏ triệt để (filter) các bản ghi thiếu `paper_id`, `title` hoặc `summary`. Log ra số lượng bản ghi bị dọn dẹp.
   - Chuẩn hóa ngày `published` về định dạng `datetime` chuẩn (timezone-naive). Tính `age_days = (run_date_naive - published_dt).days` (dùng `.clip(lower=0)` để tránh giá trị âm).
   - Nối mảng `authors` và `categories` thành các chuỗi `authors_joined` và `categories_joined` phân cách bằng dấu phẩy.
   - Ghép 4 trường thông tin chính (`title`, `authors_joined`, `categories_joined`, `summary`) thành `text_for_embedding`.
   - Thực hiện loại bỏ trùng lặp `drop_duplicates(subset=['paper_id'], keep='last')` và log số lượng trùng lặp bị loại bỏ.
2. **`corrupt_clean_dataframe(df, output_log_path)`**:
   - Đặt cố định `np.random.seed(42)` để đảm bảo tính tái lập (reproducible).
   - Áp dụng 6 kịch bản lỗi có chủ đích (với tỉ lệ 30% số lượng bản ghi): Xóa bài mới nhất (`drop_latest`), Xóa rỗng summary (`blank_summary`), Bơm văn bản rác (`inject_noise`), Cắt xén tiêu đề (`truncate_title`), Lùi ngày xuất bản và tăng tuổi bài báo (`stale_date`), Nhân bản dòng trùng lặp (`add_duplicates`).
   - **QUAN TRỌNG:** Tái tạo lại (rebuild) cột `text_for_embedding` sau khi biến đổi nội dung để Vector DB tạo ra vector embeddings bị hỏng thật sự.
   - Ghi chi tiết lịch sử biến đổi (`record_id`, `type`, `params`, `before`, `after`) vào file `corruption_log.json`.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ------ |
| Input | `records: list[PaperRecord]`, `run_date: datetime` (cho cleaning); `df: pd.DataFrame`, `output_log_path` (cho corruption) |
| Output | `pd.DataFrame` gồm 16 cột chuẩn hóa; file log `corruption_log.json` |
| Module phụ thuộc | `src/ingestion/crossref.py` (`PaperRecord`) |
| Module sử dụng output | `src/retrieval/index.py` (build ChromaDB index), `src/observability/quality.py` (run Quality checks), `src/evaluation/testset.py` |
| Điều kiện lỗi cần xử lý | Bản ghi rỗng, ngày tháng sai định dạng, `run_date` chứa timezone (tz-aware vs tz-naive), danh sách tác giả/thể loại rỗng |

### Cách xác minh

```bash
uv run python script/test_cleaning.py
```

- **Kết quả mong đợi:** In ra log dọn dẹp (filter & dedupe), hiển thị mẫu `text_for_embedding`, thực thi corruption và xuất log JSON chứa before/after.
- **Kết quả thực tế:** Code chạy thành công 100%, lọc đúng 1 bài rỗng, 1 bài trùng lặp, tạo 26 log entries corruption.
- **Artifact/log:** `data/results/test_corruption_log.json`, `data/clean/papers_clean.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn phương án triển khai lỗi hỏng ngày tháng (`stale_date`) trong module Corruption.
- **Các phương án đã cân nhắc:**
  - *Phương án 1:* Chỉ tăng giá trị số của cột `age_days` lên 1000 ngày, giữ nguyên chuỗi `published`.
  - *Phương án 2 (Được chọn):* Tăng `age_days` lên 1000 ngày, đồng thời lùi chuỗi ngày `published` gốc về quá khứ 1000 ngày (ví dụ `2023-10-01` -> `2021-01-05`) và rebuild lại `text_for_embedding`.
- **Lý do:** Ở Phương án 1, RAG Agent khi đọc `text_for_embedding` vẫn thấy năm xuất bản gốc nên trả lời đúng các câu hỏi về mốc thời gian (không làm giảm metric `judge_accuracy`). Phương án 2 đảm bảo tính đồng bộ dữ liệu: vừa làm kích hoạt cảnh báo Stale Data ở Freshness Observability Report (Role 5), vừa làm giảm điểm tìm kiếm và đánh giá của LLM Agent (Role 4).
- **Bằng chứng quyết định phù hợp:** Metric `judge_accuracy` giảm mạnh từ **1.0** xuống **0.6875** và Freshness report báo trạng thái `FAIL (stale)` rõ ràng.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Kết quả đánh giá chỉ số ở Phase 2 (Corrupted metrics) bị biến động ngẫu nhiên qua mỗi lần chạy script, không thể tái lập (reproducible) để viết báo cáo CP5-CP6.
- **Lệnh hoặc bước tái hiện:** Chạy `uv run python script/run_corruption_flow.py` nhiều lần liên tiếp và đối chiếu `data/results/corrupted_metrics.json`.
- **Nguyên nhân gốc:** Hàm `corrupt_clean_dataframe` sử dụng `np.random.choice` để chọn ngẫu nhiên các chỉ số dòng bị phá hoại mà không thiết lập Random Seed cố định.
- **Cách xử lý:** Thêm lệnh `np.random.seed(42)` vào ngay đầu hàm `corrupt_clean_dataframe`.
- **Cách xác minh sau khi sửa:** Chạy lại `script/run_corruption_flow.py` 5 lần liên tiếp, file `corrupted_metrics.json` luôn trả về kết quả cố định (`retrieval_hit_rate = 0.5`, `judge_accuracy = 0.6875`).
- **Điều học được:** Mọi thao tác giả lập lỗi dữ liệu (Data Corruption) trong Data Engineering / ML Pipeline bắt buộc phải kiểm soát được tính ngẫu nhiên (reproducibility) bằng Random Seed để phục vụ cho việc kiểm thử và báo cáo.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Luồng dữ liệu từ Crossref đến Vector Index:** Raw JSON thu thập từ Crossref API được parse thành `PaperRecord` -> Đi qua hàm `build_clean_dataframe` để lọc rác, chuẩn hóa ngày tháng, ghép trường thành `text_for_embedding` và xóa trùng lặp -> Chuyển thành `papers_clean.json` -> Module `LocalEmbeddingIndex` mã hóa `text_for_embedding` thành các vector d-chiều (bằng mô hình `all-MiniLM-L6-v2`) và nạp vào ChromaDB Vector Collection.
2. **Vai trò của Evaluation set & Ground-truth document IDs:** Evaluation set chứa các cặp câu hỏi và câu trả lời chuẩn kèm `ground_truth_doc_ids` (ID của bài báo chứa đáp án). Khi Agent nhận câu hỏi, nó tìm kiếm Top-K bài báo liên quan trong ChromaDB. Nếu `ground_truth_doc_ids` nằm trong Top-K tìm được, `retrieval_hit_rate` được tính là 1 (ngược lại là 0). Đồng thời, câu trả lời do LLM sinh ra được so sánh với Ground Truth để tính `mean_token_f1` và `judge_accuracy`.
3. **Phân biệt Quality checks và Freshness monitoring:** 
   - *Quality checks:* Kiểm tra tính toàn vẹn tĩnh và cấu trúc dữ liệu tại thời điểm chạy (chống rỗng, đúng kiểu dữ liệu, ID duy nhất, độ dài chuỗi hợp lệ).
   - *Freshness monitoring:* Đánh giá tính mới/thời sự của dữ liệu động theo thời gian (so sánh `age_days` với ngưỡng `freshness_threshold_days = 180` ngày) để cảnh báo dữ liệu bị lỗi thời.
4. **Lý do dùng chung 1 Test set:** Việc dùng cố định bộ 16 câu hỏi test set cho cả 3 trạng thái Baseline, Corrupted và Repaired tạo ra một "thước đo chuẩn" (controlled environment). Giúp nhóm đo lường chính xác mức độ sụt giảm chất lượng do dữ liệu lỗi gây ra và mức độ phục hồi sau khi sửa chữa.
5. **Dấu hiệu chứng minh Repair thành công:** Repair thành công khi:
   - Dữ liệu `repaired_df` khôi phục khớp 100% với `clean_df` ban đầu (`Repaired equals Clean: True`).
   - Báo cáo Data Quality chuyển trạng thái từ `FAIL` về `PASS` (9/9 bài test đạt).
   - Các chỉ số của RAG Agent phục hồi hoàn toàn về mức tối đa: `retrieval_hit_rate` từ 0.5 -> **1.0**, `mean_token_f1` từ 0.634 -> **1.0**, `judge_accuracy` từ 0.6875 -> **1.0**.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate`   |    `1.0` |     `0.5` |    `1.0` | Dữ liệu bị hỏng làm Agent mất khả năng tìm thấy 50% tài liệu liên quan. |
| `mean_token_f1`        |    `1.0` |   `0.634` |    `1.0` | Độ trùng khớp từ vựng giữa câu trả lời và đáp án mẫu giảm mạnh do thông tin bị nhiễu/xóa. |
| `judge_accuracy`       |    `1.0` |  `0.6875` |    `1.0` | Tỉ lệ LLM Judge đánh giá câu trả lời đúng giảm xuống chỉ còn ~68.7%. |
| `mean_judge_score`     |    `5.0` |   `3.875` |    `5.0` | Điểm chất lượng trung bình của câu trả lời (thang điểm 5) bị sụt giảm rõ rệt. |
| Quality checks         |   `PASS` |    `FAIL` |   `PASS` | Hệ thống Quality bắt được 4 lỗi (duplicate, null summary, min length, stale date). |
| Freshness status       |   `PASS` |    `FAIL` |   `PASS` | Phát hiện chính xác dữ liệu bị biến đổi làm ngày xuất bản bị cũ quá 180 ngày. |

### Kết luận từ số liệu

1. **[Data corruption]** (Xóa summary, bơm noise, truncate title, lùi ngày) → **[quality/freshness signal báo FAIL]** (hỏng 4/9 checks) → **[agent metric sụt giảm mạnh]** (`hit_rate` giảm từ 1.0 -> 0.5).
2. **[Repair action]** (Tải lại Raw data từ Crossref và re-run cleaning) → **[quality/freshness signal phục hồi về PASS]** (9/9 checks đạt) → **[agent metric phục hồi hoàn toàn]** (`hit_rate`, `token_f1`, `judge_acc` trở lại mức 1.0 tuyệt đối).

- **Corruption ảnh hưởng rõ nhất:** Lỗi `blank_summary` và `inject_noise` ảnh hưởng mạnh nhất đến `retrieval_hit_rate` và `judge_accuracy`. Khi tóm tắt bị rỗng hoặc chứa văn bản rác, mô hình Vector Embedding không thể tạo ra representation chuẩn xác, dẫn đến tìm kiếm sai tài liệu và LLM sinh câu trả lời bị hallucinate hoặc thiếu thông tin.
- **Kết quả khác với kỳ vọng ban đầu:** Ban đầu dự đoán lùi ngày xuất bản (`stale_date`) sẽ làm hỏng câu trả lời, nhưng nếu không rebuild lại `text_for_embedding` thì RAG Agent vẫn đọc được ngày cũ. Sau khi chủ động rebuild `text_for_embedding`, metric `judge_accuracy` đã sụt giảm đúng như kỳ vọng ban đầu.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về Data Pipeline:** Quy trình làm sạch dữ liệu (Cleaning & Normalization) không đơn thuần là xóa khoảng trắng, mà là việc thiết lập một Data Contract chặt chẽ giữa các tầng (Ingestion -> Storage -> Embedding -> RAG).
2. **Về Data Observability:** Data Quality Checks và Freshness Monitoring là "hàng rào phòng thủ" không thể thiếu. Chúng giúp phát hiện lỗi dữ liệu ngay tại nguồn trước khi dữ liệu độc hại làm hỏng các mô hình AI/LLM ở hạ nguồn.
3. **Về ảnh hưởng của Data đến RAG Agent:** "Garbage in, garbage out" — Chất lượng tìm kiếm và câu trả lời của RAG Agent phụ thuộc trực tiếp 100% vào độ sạch và tính toàn vẹn của dữ liệu đầu vào.

### Nếu có thêm thời gian

Nếu có thêm thời gian, em sẽ phát triển thêm tính năng **Automated Anomaly Detection** cho chiều dài văn bản (dùng Z-Score / IQR) trong module `cleaning.py` để tự động phát hiện và loại bỏ các đoạn abstract bị cắt dở hoặc chứa rác mà không cần phải viết quy tắc cứng (hardcoded rules).

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Đình Duy  
**Ngày xác nhận:** 2026-08-06
