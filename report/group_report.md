# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K4 |
| Tên nhóm | SilverFlag |
| Repository | https://github.com/thevietofficial-coder/K4_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Bùi Hoàng Việt | 2A202601391 | Trưởng nhóm / Vai trò 1 — Pipeline integrator | `src/core/`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` |
| 2 | Trần Trọng Nghĩa | 2A202601370 | Vai trò 2 — Ingestion owner | `src/ingestion/crossref.py`, `data/raw/` |
| 3 | Nguyễn Đình Duy | 2A202601046 | Vai trò 3 — Cleaning & corruption owner | `src/ingestion/cleaning.py`, `src/ingestion/corruption.py` |
| 4 | Nguyễn Thừa Tuân | 2A202601330 | Vai trò 4 — RAG & agent owner | `src/retrieval/`, `data/embeddings/` |
| 5 | Hoàng Anh Minh | 2A202601192 | Vai trò 5 — Evaluation & observability owner | `src/evaluation/`, `src/observability/` |

## 2. Tóm tắt kết quả

Nhóm đã hoàn thành toàn bộ 12 hàm `TODO(student)` và chạy thành công cả hai entrypoint `script/run_phase1.py`, `script/run_corruption_flow.py` end-to-end. Sau khi baseline đầu tiên chạy ổn định, nhóm tiếp tục rà soát sâu và phát hiện, rồi sửa, ba vấn đề chất lượng: (1) evaluation set sinh 4 câu hỏi loại `categories` với ground-truth `"Unknown"` cho mọi paper (do Crossref không trả field `subject`), khiến metric dựa trên nội dung bị thổi phồng khi retrieval sai nhưng vẫn "trùng khớp" ngẫu nhiên — đã sửa `build_test_set` để bỏ loại câu hỏi này khi dữ liệu không có thật; (2) `corrupt_clean_dataframe` dùng random không seed, không tái lập được giữa các lần chạy — đã thêm `seed=42` cố định bằng `np.random.default_rng`, xác minh 2 lần chạy liên tiếp cho `corruption_log.json` **giống hệt nhau**; (3) dọn 1 import thừa trong `crossref.py`. Sau khi sửa, baseline vẫn đạt tuyệt đối trên 12 câu hỏi (`retrieval_hit_rate/mean_token_f1/judge_accuracy = 1.000`, `mean_judge_score = 5.000`), corrupted giảm rõ và **chính xác hơn** trước (`retrieval_hit_rate = 0.500`, `mean_token_f1 = 0.435`, `judge_accuracy = 0.583` — thấp hơn hẳn số liệu trước khi sửa vì không còn bị "Unknown" che giấu thất bại retrieval), và repaired phục hồi 100% về đúng mức baseline. Nguyên nhân corruption ảnh hưởng rõ nhất vẫn là `drop_latest` (xóa 2 paper trùng với 2/4 tài liệu ground-truth). Không còn blocker kỹ thuật; phần còn lại là hoàn thiện báo cáo cá nhân của từng thành viên.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API
    -> raw response/raw records (data/raw/)
    -> cleaning và data modeling (data/clean/)
    -> embedding + ChromaDB index (data/embeddings/, data/chroma/)
    -> evaluation baseline (data/eval/, data/results/baseline_*.json)
    -> quality/freshness reports (data/quality/)
    -> corruption (data/results/corruption_log.json)
    -> re-index và re-evaluate (data/results/corrupted_*.json)
    -> repair từ dữ liệu nguồn (data/clean/papers_clean_repaired.*)
    -> comparison report (data/reports/corruption_report.md)
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref REST API | Fetch với retry/backoff (429/503), parse DOI/title/abstract/authors/dates thành `PaperRecord`; chặn live-fetch ngoài ý muốn khi `REFRESH_SOURCE` tắt | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Trần Trọng Nghĩa |
| Cleaning | `list[PaperRecord]` | Normalize text, parse ngày, tính `age_days`, build `text_for_embedding`, dedupe theo `paper_id` | `data/clean/papers_clean.{csv,json}` | Nguyễn Đình Duy |
| Corruption/repair | Clean dataframe + raw records | 6 kỹ thuật corruption có log, **seed cố định (42)** để tái lập được; repair = chạy lại cleaning từ raw | `data/results/corruption_log.json`, `data/clean/papers_clean_{corrupted,repaired}.*` | Nguyễn Đình Duy (+ seed fix: Bùi Hoàng Việt) |
| Embedding/index | Clean dataframe | MiniLM embeddings, Chroma collection riêng cho từng trạng thái | `data/embeddings/papers_embeddings*.json`, `data/chroma/` | Nguyễn Thừa Tuân |
| Evaluation | Clean dataframe, index | Sinh test set cố định (chỉ hỏi `categories` khi paper có dữ liệu thật, không dùng fallback `"Unknown"`), chạy agent/qa, chấm token-F1 + LLM-judge | `data/eval/test_set.json`, `data/results/*_metrics.json`, `*_answers.json` | Hoàng Anh Minh (+ fix categories: Bùi Hoàng Việt) |
| Observability | Clean dataframe, Settings | 10 data-quality check + freshness report | `data/quality/*.json` | Hoàng Anh Minh |
| Orchestration | Toàn bộ module trên | Ghép đúng thứ tự raw→clean→index→eval→quality→report cho cả 2 flow | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Bùi Hoàng Việt |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
| --- | --- |
| `LLM_PROVIDER` | `openai` |
| `LLM_MODEL` | `gpt-4o-mini` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 (`max_results=24`, filter `from-pub-date:<180 ngày>,has-abstract:true`) |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày |
| Random seed, nếu có | `seed=42` cố định trong `corrupt_clean_dataframe` (`np.random.default_rng(42)`) — đã xác minh 2 lần chạy cho `corruption_log.json` giống hệt nhau |

Không dán nội dung API key hoặc file `.env` vào báo cáo.

### Lệnh cài đặt

```bash
uv sync
```

### Lệnh chạy

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| Baseline pipeline | Thành công (chạy lại xác nhận 3 lần trong quá trình tích hợp + sửa lỗi) | 2026-08-06 | `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| Corruption flow | Thành công (chạy lại 2 lần liên tiếp sau khi thêm seed, xác nhận `corruption_log.json` tái lập y hệt) | 2026-08-06 | `data/results/corrupted_metrics.json`, `data/results/repaired_metrics.json`, `data/reports/corruption_report.md` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | Crossref REST API — `https://api.crossref.org/works` |
| Query/filter | `query="agentic retrieval augmented generation large language model"`, `filter="from-pub-date:<180 ngày trước>,has-abstract:true"` |
| Thời điểm lấy dữ liệu | 2026-08-06 |
| Số record nhận được | 24 raw → 24 clean (không record nào bị loại) |
| Cơ chế retry/backoff | `tenacity`, exponential backoff + tôn trọng header `Retry-After`, tối đa 5 lần thử cho status `429`/`503` |

### Raw và clean schema

| Trường | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu/sai |
| --- | --- | --- | --- | --- |
| `paper_id` | str (DOI chuẩn hóa) | Có | Định danh ổn định xuyên suốt raw→clean→index→repair | Record không có DOI bị bỏ qua từ bước parse |
| `title`, `summary` | str | Có | Nội dung chính cho embedding | Record thiếu title/summary bị loại ở bước clean |
| `authors`, `categories` | list[str] | Không | Ngữ cảnh trả lời câu hỏi authors/categories | Rỗng thì `authors_joined`/`categories_joined` = `"Unknown"`; **từ bản sửa, `testset.py` không còn hỏi `categories` khi paper không có dữ liệu thật** |
| `published` | str (ISO date) | Không | Nguồn tính `age_days`/freshness | Không parse được thì dùng `run_date` làm mốc |
| `age_days` (derived) | int | — | Tín hiệu freshness, so với ngưỡng 180 ngày | Tính lại mỗi lần clean, không cache |
| `text_for_embedding` (derived) | str | — | Nội dung đưa vào MiniLM | Ghép `Title/Authors/Categories/Summary`, rebuild lại sau mỗi lần corrupt |

### Quy tắc cleaning

| Quy tắc | Quality dimension liên quan | Số record bị tác động | Cách xác minh |
| --- | --- | ---: | --- |
| Loại record thiếu `paper_id`/`title`/`summary` | Completeness | 0 (lần chạy này) | `data/quality/baseline.json` → `null_*_rows = 0` |
| Dedupe theo `paper_id` (giữ bản ghi cuối) | Uniqueness | 0 | `paper_id_unique`, `records_unique` pass trong `baseline.json` |

Giải thích cách nhóm tạo `text_for_embedding`, document ID và `age_days`: `paper_id` là DOI đã chuẩn hóa để đảm bảo cùng một paper luôn có cùng ID dù fetch lại nhiều lần. `text_for_embedding` ghép 4 dòng `Title/Authors/Categories/Summary`, được rebuild lại sau mỗi thao tác corruption. `age_days` = số ngày giữa `run_date` (chuẩn hóa tz-naive) và `published`.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
| --- | --- |
| Số câu hỏi | 12 (4 paper đại diện × tối đa 3 loại câu hỏi thật) |
| Các `question_type` | `summary`, `authors`, `date`. (`categories` bị loại vì cả 24 paper trong lần fetch này đều không có field `subject` từ Crossref — hỏi câu này sẽ tạo ground-truth `"Unknown"` không phân biệt được đúng/sai document) |
| Ground-truth document ID | Lấy trực tiếp `paper_id` của 4 paper mới nhất trong clean dataset; `build_test_set` kiểm tra `paper_id` không null/không trùng trước khi ghi test set |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection | ChromaDB local (`data/chroma/`) — `papers-baseline` / `papers-corrupted` / `papers-repaired` |
| Retrieval `top_k` | 4 |
| LLM provider/model | `openai` / `gpt-4o-mini` |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (tạo một lần, `REFRESH_TEST_SET` không bật nên tái sử dụng nguyên vẹn cho cả baseline/corrupted/repaired) |

Giải thích vì sao test set được giữ nguyên: nếu câu hỏi/ground-truth thay đổi giữa các lần đánh giá, mọi chênh lệch metric sẽ không thể quy kết chắc chắn là do dữ liệu thay đổi hay do bộ câu hỏi thay đổi. Test set đã được sửa **một lần duy nhất trước khi chạy 3 trạng thái chính thức** (bỏ câu hỏi `categories` vô nghĩa), sau đó giữ cố định cho cả baseline, corrupted và repaired.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn thực tế | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/` | Có | 24 record |
| Cleaned dataset | `data/clean/` | Có | 24 record, 0 bị loại |
| Embedding manifest/index | `data/embeddings/` | Có | `papers-baseline`, 24 document |
| Evaluation set | `data/eval/` | Có | 12 câu hỏi (3 loại × 4 paper) |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | Xem bảng dưới |
| Quality/freshness | `data/quality/` | Có | 10/10 check pass |
| Baseline report | `data/reports/phase1_report.md` | Có | Sinh tự động từ `generate_phase1_report` |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| `retrieval_hit_rate` | 1.000 | Cả 12/12 câu hỏi đều truy hồi đúng document ground-truth |
| `mean_token_f1` | 1.000 | Câu trả lời trùng khớp hoàn toàn với ground truth |
| `judge_accuracy` | 1.000 | LLM-judge (`gpt-4o-mini`) chấm đúng 12/12 câu |
| `mean_judge_score` | 5.000 | Điểm judge tối đa (thang 1–5) |
| Ragas | Bỏ qua | `RUN_RAGAS` không được bật trong lần chạy này |

## 8. Data quality và freshness

### Quality checks (10 check)

| Check | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline | Bằng chứng |
| --- | --- | --- | --- | --- |
| `row_count` | Volume | ≥ 4 | Pass (24) | `data/quality/baseline.json` |
| `paper_id_not_null` / `paper_id_unique` | Completeness / Uniqueness | 0 vi phạm | Pass (0) | `data/quality/baseline.json` |
| `records_unique` | Uniqueness | 0 bản ghi trùng toàn bộ nội dung | Pass (0) | `data/quality/baseline.json` |
| `title_not_null` / `summary_not_null` | Completeness | 0 vi phạm | Pass (0) | `data/quality/baseline.json` |
| `summary_min_length` | Validity | 0 dòng < 80 ký tự | Pass (0) | `data/quality/baseline.json` |
| `age_days_valid` / `age_days_fresh` | Validity / Freshness | 0 âm, 0 dòng > 180 ngày | Pass (0/0) | `data/quality/baseline.json` |

Tổng: **10/10 check pass**.

### Freshness

| Thuộc tính | Giá trị |
| --- | --- |
| Freshness được đo tại | Clean dataframe baseline |
| Timestamp mới nhất | `2026-08-01` |
| Ngưỡng freshness | 180 ngày |
| Trạng thái baseline | Fresh (`is_fresh = true`, `stale_rows = 0`) |
| Lý do | Filter Crossref đã giới hạn `from-pub-date` trong 180 ngày nên toàn bộ 24 record đều nằm trong ngưỡng freshness |

## 9. Corruption scenarios và repair

| Corruption | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair |
| --- | --- | ---: | --- | --- | --- |
| `drop_latest` (xác định) | Xóa 10% record đứng đầu (đã sort theo `published` giảm dần) | 2/24 — `10.2118/234689-pa`, `10.1111/exsy.70341` | `row_count` giảm | Cả 2 paper trùng với 2/4 tài liệu ground-truth trong test set → 6/12 câu hỏi mất khả năng retrieval đúng | Repair build lại từ raw gốc |
| `blank_summary` (seed=42, 30%) | Xóa nội dung `summary` | 6/24 | `summary_not_null`, `summary_min_length` fail | Một phần bị `inject_noise` "lấp" lại (vô nghĩa), phần còn lại rỗng thật | Repair phục hồi `summary` gốc từ raw |
| `inject_noise` (seed=42, 30%) | Thêm `"[NOISE] Lorem ipsum..."` vào `summary` | 6/24 | Không có check riêng — ảnh hưởng gián tiếp qua chất lượng câu trả lời | Nội dung agent nhận được bị nhiễu khi retrieval trúng các record này | Repair phục hồi `summary` sạch từ raw |
| `truncate_title` (seed=42, 30%) | Cắt `title` còn 10 ký tự + `"..."` | 6/24 | Không fail check completeness nhưng mất định danh ngữ nghĩa | Ảnh hưởng semantic search/agent khi cần nhận diện paper qua title | Repair phục hồi `title` đầy đủ từ raw |
| `stale_date` (seed=42, 30%) | Cộng thêm 1000 ngày vào `age_days` | 6/24 | `age_days_fresh` fail | `stale_rows`: 0 → 7; `freshness.is_fresh`: true → false | Repair tính lại `age_days` từ `published` gốc |
| `add_duplicates` (xác định) | Nhân đôi 2 record đầu còn lại sau `drop_latest` | 2 record gốc → 4 dòng trùng `paper_id` — `10.1007/s10278-026-02086-9`, `10.21203/rs.3.rs-10178277/v1` | `paper_id_unique`, `records_unique` fail | `duplicate_paper_id_rows`: 0 → 4 | Repair dedupe lại theo `paper_id` khi build từ raw |

Corruption log: `data/results/corruption_log.json`, đủ 6 loại corruption, kèm `record_id`/`affected_ids`, tham số `before/after` cho từng bản ghi. **Từ bản sửa, toàn bộ corruption dùng `np.random.default_rng(seed=42)`** — đã xác minh chạy 2 lần liên tiếp cho file log giống hệt nhau (byte-for-byte), khắc phục giới hạn "không tái lập được" phát hiện ở vòng review trước.

Giải thích cách repair đảm bảo dữ liệu được phục hồi từ nguồn đáng tin cậy: `corruption_flow.py` không sửa tay bất kỳ file kết quả nào. Repair gọi `load_raw_records()` đọc lại `data/raw/crossref_records.json` (không bao giờ bị corruption chạm vào) rồi chạy lại **đúng hàm `build_clean_dataframe`** đã dùng cho baseline.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.000 | 0.500 | 1.000 | −0.500 | +0.500 | Phục hồi hoàn toàn |
| `mean_token_f1` | 1.000 | 0.435 | 1.000 | −0.565 | +0.565 | Phục hồi hoàn toàn |
| `judge_accuracy` | 1.000 | 0.583 | 1.000 | −0.417 | +0.417 | Phục hồi hoàn toàn |
| `mean_judge_score` | 5.000 | 3.500 | 5.000 | −1.500 | +1.500 | Phục hồi hoàn toàn |
| Quality checks pass/fail | 10/10 pass | 5/10 pass | 10/10 pass | −5 check | +5 check | Phục hồi hoàn toàn |
| Freshness status | Fresh (stale=0) | Stale (stale=7) | Fresh (stale=0) | +7 stale rows | −7 stale rows | Phục hồi hoàn toàn |

Hai kết luận nhân quả có bằng chứng cụ thể:

1. **`drop_latest` xóa mất paper `10.1111/exsy.70341` và `10.2118/234689-pa`** (`data/results/corruption_log.json`) → cả 6 câu hỏi liên quan 2 paper này trong `test_set.json` đều có `retrieval_hit: false` trong `data/results/corrupted_answers.json` (đối chứng `retrieval_hit: true` ở `baseline_answers.json`) → `retrieval_hit_rate` giảm chính xác 0.500. Sau khi bỏ câu hỏi `categories` không có giá trị đánh giá, `mean_token_f1`/`judge_accuracy` giờ phản ánh đúng mức độ suy giảm này thay vì bị che một phần.
2. **Repair chạy lại `build_clean_dataframe` trên raw records gốc** (không bị corruption chạm vào) → `data/quality/repaired.json` trở lại 10/10 check pass, `freshness_report_repaired.json` có `is_fresh: true, stale_rows: 0` → cả 4 metric agent trong `repaired_metrics.json` phục hồi về đúng giá trị baseline.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Khi ghép `phase1.py` gọi `build_clean_dataframe`, pipeline crash ngay ở bước Clean với `TypeError: Cannot subtract tz-naive and tz-aware datetime-like objects`.
- **Nguyên nhân:** `cleaning.py` strip timezone khỏi cột `published_dt` (tz-naive), nhưng `run_date` truyền vào từ `core.utils.now_utc()` lại là tz-aware.
- **Cách xử lý:** Chuẩn hóa `run_date` về tz-naive (`run_date.replace(tzinfo=None)`) ngay đầu `build_clean_dataframe`, giữ nguyên chữ ký hàm public.
- **Cách xác minh:** Chạy lại `uv run python script/run_phase1.py` — pipeline chạy hết 8/8 bước.

## 12. Giới hạn và hướng cải thiện

Ba giới hạn phát hiện ở vòng review kỹ (sau khi toàn bộ pipeline đã chạy được) — cả ba **đã được sửa và xác minh lại bằng cách chạy thật**:

| Giới hạn đã phát hiện | Ảnh hưởng trước khi sửa | Cách đã sửa | Bằng chứng đã sửa đúng |
| --- | --- | --- | --- |
| `categories_joined = "Unknown"` cho mọi paper (Crossref không trả `subject`) | `mean_token_f1`/`judge_accuracy` corrupted bị thổi phồng: 2/16 câu hỏi "đúng" dù retrieval sai document | `build_test_set` chỉ hỏi `categories` khi paper có `categories` thật (list không rỗng) | Test set còn 12 câu (bỏ 4 câu `categories`); `mean_token_f1` corrupted giảm từ 0.625 xuống **0.435**, `judge_accuracy` từ 0.625 xuống **0.583** — phản ánh đúng mức suy giảm thật |
| `corrupt_clean_dataframe` dùng `np.random.choice` không seed | Không tái lập được record cụ thể bị corrupt giữa các lần chạy | Thêm `seed: int = 42`, dùng `np.random.default_rng(seed)` thay cho global RNG | Chạy 2 lần liên tiếp, `diff` trên `corruption_log.json` cho kết quả **rỗng** (giống hệt byte-for-byte) |
| Import thừa `wait_exponential_jitter` trong `crossref.py` | Không ảnh hưởng chức năng, chỉ là code thừa | Xóa khỏi import | `uv run python -c "import pipelines..."` không lỗi |

Giới hạn còn lại, cân nhắc nhưng **chưa sửa** (không phải bug, là quyết định thiết kế hợp lý của Vai trò 2):

| Giới hạn | Lý do không sửa |
| --- | --- |
| `fetch_source_records` raise `RuntimeError` nếu chưa có raw snapshot và `REFRESH_SOURCE` tắt | Thiết kế chủ đích để tránh vô tình đổi dữ liệu gốc giữa các lần chạy — đúng nguyên tắc reproducibility của lab. Không ảnh hưởng bài nộp vì `data/raw/` đã commit sẵn trong repo |
| Ragas đang tắt (`RUN_RAGAS` không set) | Cần thêm ngân sách API/thời gian; không bắt buộc theo Guide, chỉ là bonus optional |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp (3 lần trong quá trình tích hợp + sửa lỗi, kết quả nhất quán).
- [x] Baseline, corrupted và repaired dùng cùng evaluation set (đã khóa lại sau khi sửa test set 1 lần duy nhất).
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
