# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Bùi Hoàng Việt |
| MSSV | 2A202601391 |
| Khóa/Lớp | K4 |
| Tên nhóm | SilverFlag |
| Vai trò chính | Vai trò 1 — Trưởng nhóm / Pipeline integrator |
| Repository | https://github.com/thevietofficial-coder/K4_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Baseline orchestration | `src/pipelines/phase1.py: main()` | `Settings`, module do 4 thành viên còn lại xây | `data/clean/`, `data/embeddings/`, `data/eval/test_set.json`, `data/results/baseline_*.json`, `data/quality/*`, `data/reports/phase1_report.md` | Hoàn thành |
| Corruption flow orchestration | `src/pipelines/corruption_flow.py: main()` | Baseline artifacts, raw records | `data/clean/papers_clean_{corrupted,repaired}.*`, `data/results/{corrupted,repaired}_*.json`, `data/reports/corruption_report.md` | Hoàn thành |
| Rà soát chất lượng + sửa lỗi tích hợp toàn hệ thống | `src/ingestion/cleaning.py`, `src/evaluation/testset.py`, `src/ingestion/corruption.py`, `src/ingestion/crossref.py` | Toàn bộ artifact sinh ra sau mỗi lần chạy | 3 bug/giới hạn được sửa và xác minh lại bằng cách chạy thật (chi tiết mục 3, 6) | Hoàn thành |

Phần code chính của tôi là orchestration (`phase1.py`, `corruption_flow.py`). Ngoài ra, với vai trò trưởng nhóm, tôi chủ động rà soát kỹ toàn bộ output thay vì chỉ tin "pipeline chạy không lỗi", và sửa trực tiếp 3 vấn đề phát hiện được trong file của đồng đội khi chúng ảnh hưởng đến độ tin cậy của kết luận cuối cùng.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Sửa bug tz-aware/tz-naive chặn pipeline | `src/ingestion/cleaning.py` (Vai trò 3) | Baseline chạy được 8/8 bước thay vì crash |
| Sửa evaluation set sinh câu hỏi vô nghĩa | `src/evaluation/testset.py` (Vai trò 5) | Bỏ câu hỏi `categories` khi ground-truth là `"Unknown"` cho mọi document |
| Thêm seed cố định cho corruption | `src/ingestion/corruption.py` (Vai trò 3) | Corruption tái lập được y hệt giữa các lần chạy, xác minh bằng diff |
| Dọn code | `src/ingestion/crossref.py` (Vai trò 2) | Xóa 1 import thừa, không đổi hành vi |
| Điều phối git | Toàn nhóm | Nhánh `develop` làm nhánh tích hợp, `stash` an toàn trước khi pull, review commit trước khi tin artifact |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Ghép baseline pipeline | `src/pipelines/phase1.py` | `baseline_metrics.json`: `retrieval_hit_rate=1.0`, `judge_accuracy=1.0` (12/12 câu) | `uv run python script/run_phase1.py` |
| Ghép corruption/repair/comparison flow | `src/pipelines/corruption_flow.py` | `corrupted_metrics.json` (`retrieval_hit_rate=0.5`), `repaired_metrics.json` (`retrieval_hit_rate=1.0`) | `uv run python script/run_corruption_flow.py` |
| Sửa bug timezone | `src/ingestion/cleaning.py` | Pipeline hết crash | Chạy lại, so log trước/sau |
| Sửa evaluation set: bỏ câu hỏi `categories` không có ground-truth thật | `src/evaluation/testset.py` | Test set 16→12 câu; `mean_token_f1` corrupted giảm từ 0.625 xuống 0.435 (chính xác hơn) | Xóa `test_set.json` cũ, chạy lại `run_phase1.py`, kiểm tra `question types present` trong answers không còn `categories` |
| Thêm seed cho corruption | `src/ingestion/corruption.py` | `corruption_log.json` tái lập được | Chạy `run_corruption_flow.py` 2 lần liên tiếp, `diff` cho kết quả rỗng |

Output cụ thể minh chứng rõ nhất cho phần việc của tôi: bảng so sánh `mean_token_f1` corrupted **trước sửa (0.625) → sau sửa (0.435)** — một con số tự nó không "đẹp hơn" nhưng **đúng hơn**, vì nó không còn bị 2 câu hỏi `categories="Unknown"` che giấu một phần thất bại retrieval thật. Đây là ví dụ cụ thể cho việc "báo cáo phải khớp artifact thật" chứ không phải chọn số liệu đẹp nhất.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Ngoài việc ghép đúng thứ tự phụ thuộc giữa 5 module, phần quan trọng không kém là **không mặc định tin artifact "trông đúng"**. Baseline chạy `retrieval_hit_rate=1.000` ngay từ đầu khiến dễ dừng lại ở đó; nhưng khi soi từng câu trả lời trong `corrupted_answers.json` thay vì chỉ nhìn số tổng, tôi phát hiện một số câu "đúng" theo `token_f1`/`judge` dù `retrieval_hit=false` — dấu hiệu cho thấy metric phụ đang sai lệch so với thực tế retrieval.

### Cách triển khai fix chính (evaluation set)

Trong `src/evaluation/testset.py`, hàm `build_test_set` trước đây luôn sinh đủ 4 loại câu hỏi (`summary/authors/date/categories`) cho mỗi paper được chọn. Vì toàn bộ 24 paper trong lần fetch này đều không có field `subject` từ Crossref, `categories_joined` (do `cleaning.py` tạo) luôn là chuỗi fallback `"Unknown"` — không phải giá trị thật. Tôi sửa để hàm chỉ thêm câu hỏi `categories` vào danh sách khi `row["categories"]` (list gốc, chưa join) không rỗng:

```python
raw_categories = row.get("categories")
if isinstance(raw_categories, list) and raw_categories:
    questions.append(("categories", ..., categories, "categories_joined"))
```

Dùng list gốc thay vì so sánh chuỗi `"Unknown"` để không phụ thuộc cứng vào chuỗi fallback cụ thể mà `cleaning.py` chọn — nếu Vai trò 3 đổi fallback text sau này, logic vẫn đúng.

### Cách triển khai fix phụ (seed corruption)

Trong `src/ingestion/corruption.py`, `corrupt_clean_dataframe` thêm tham số `seed: int = 42` (có giá trị mặc định nên không phá chữ ký hàm hiện có), tạo `rng = np.random.default_rng(seed)` và thay toàn bộ 4 lời gọi `np.random.choice(...)` thành `rng.choice(...)` — dùng generator cục bộ thay vì global state của `numpy.random`, tránh ảnh hưởng ngoài ý muốn tới code khác có thể cũng dùng `np.random`.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `Settings`/`Paths`, `PaperRecord`, clean `DataFrame`, `LocalEmbeddingIndex`, các hàm evaluation/observability |
| Output | `data/clean/*`, `data/embeddings/*`, `data/results/*`, `data/quality/*`, `data/reports/*.md` |
| Module phụ thuộc | Toàn bộ `src/ingestion/`, `src/retrieval/`, `src/evaluation/`, `src/observability/` |
| Module sử dụng output | `script/run_phase1.py`, `script/run_corruption_flow.py`, `report/group_report.md` |
| Điều kiện lỗi cần xử lý | Thiếu baseline artifact khi chạy corruption flow → `RuntimeError` rõ ràng; thiếu raw snapshot khi `REFRESH_SOURCE` tắt → `RuntimeError` từ `fetch_source_records` (thiết kế của Vai trò 2, đã xác nhận không ảnh hưởng vì `data/raw/` đã commit) |

### Cách xác minh

```bash
rm data/eval/test_set.json
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run python script/run_corruption_flow.py   # chạy lần 2 để kiểm tra reproducibility
diff <(cat data/results/corruption_log.json)  # so với bản lưu từ lần 1
```

- **Kết quả mong đợi:** test set còn 12 câu (không còn `categories`), corruption log giống hệt giữa 2 lần chạy.
- **Kết quả thực tế:** đúng như mong đợi — `diff` rỗng, `mean_token_f1`/`judge_accuracy` corrupted giảm xuống mức thấp hơn (chính xác hơn) so với trước khi sửa.
- **Artifact/log:** `data/eval/test_set.json`, `data/results/corruption_log.json`, `data/results/corrupted_metrics.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Phát hiện `mean_token_f1`/`judge_accuracy` ở trạng thái corrupted có thể bị sai lệch do 2/16 câu hỏi `categories` "đúng" một cách ngẫu nhiên (ground-truth `"Unknown"` trùng với câu trả lời sai). Cần quyết định cách xử lý.
- **Các phương án đã cân nhắc:** (1) Giữ nguyên, chỉ ghi chú giới hạn trong báo cáo; (2) Sửa `build_test_set` để không sinh câu hỏi `categories` khi không có dữ liệu thật; (3) Sửa `_extract_answer`/scoring để coi `"Unknown"` là câu trả lời "không hợp lệ", luôn tính sai.
- **Phương án đã chọn:** (2) — sửa tận gốc ở bước sinh test set.
- **Lý do:** Phương án (1) không giải quyết vấn đề, chỉ ghi nhận. Phương án (3) sửa ở tầng scoring sẽ ảnh hưởng logic dùng chung cho mọi loại câu hỏi (rủi ro cao hơn, phạm vi thay đổi rộng hơn cần thiết). Phương án (2) sửa đúng nguyên nhân gốc (câu hỏi không nên được hỏi nếu không có ground-truth thật), phạm vi thay đổi nhỏ, không ảnh hưởng 3 loại câu hỏi còn lại.
- **Bằng chứng quyết định phù hợp:** Sau khi sửa, `mean_token_f1` corrupted giảm từ 0.625 xuống 0.435, `judge_accuracy` từ 0.625 xuống 0.583 — cả hai đều **thấp hơn**, tức phản ánh đúng hơn mức độ hư hại thật của corruption thay vì bị làm đẹp giả tạo.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `TypeError: Cannot subtract tz-naive and tz-aware datetime-like objects` khi chạy `uv run python script/run_phase1.py`.
- **Lệnh hoặc bước tái hiện:** `uv run python script/run_phase1.py` (trước khi sửa).
- **Nguyên nhân gốc:** `cleaning.py` tính `df['published_dt']` tz-naive nhưng `run_date` (từ `now_utc()`) là tz-aware — phép trừ không hợp lệ trong pandas.
- **Cách xử lý:** Chuẩn hóa `run_date` về tz-naive trước khi dùng, giữ nguyên chữ ký hàm.
- **Cách xác minh sau khi sửa:** Pipeline chạy hết 8/8 bước.
- **Điều học được:** Một contract chung (chữ ký hàm) chưa đủ để tránh lỗi tích hợp — cần thống nhất cả quy ước ngầm, và phải chạy thử thật để lộ ra.

**Một phát hiện thứ hai đã xử lý xong (không phải lỗi runtime nhưng là sai lệch âm thầm về chất lượng đánh giá):**

- **Triệu chứng:** `data/results/corrupted_answers.json` có các câu hỏi với `retrieval_hit: false` nhưng `token_f1: 1.0` và `judge.correct: true` — mâu thuẫn logic (retrieval sai mà câu trả lời vẫn "đúng").
- **Nguyên nhân gốc:** Toàn bộ 24 paper không có field `subject` từ Crossref → `categories_joined = "Unknown"` cho mọi document → khi retrieval trả về document sai, document đó cũng có `categories_joined = "Unknown"`, trùng khớp ngẫu nhiên với ground-truth.
- **Cách xử lý:** Sửa `build_test_set` (mục 4) để không sinh câu hỏi `categories` khi không có dữ liệu thật.
- **Cách xác minh sau khi sửa:** Không còn câu hỏi loại `categories` nào trong test set mới; `mean_token_f1`/`judge_accuracy` corrupted giảm xuống mức thấp hơn, chính xác hơn.
- **Điều học được:** Một metric tổng hợp có thể "trông ổn" trong khi từng điểm dữ liệu bên trong mâu thuẫn nhau — luôn cần đối chiếu chéo giữa metric độc lập (`retrieval_hit` dựa trên ID) và metric phụ thuộc nội dung (`token_f1`) trước khi kết luận.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?** `fetch_source_records` gọi Crossref, lưu response gốc rồi parse thành `PaperRecord` (DOI làm `paper_id`). `build_clean_dataframe` chuẩn hóa thành DataFrame có `text_for_embedding`. `LocalEmbeddingIndex.build()` dùng MiniLM encode rồi nạp vào Chroma collection kèm metadata.
2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?** `build_test_set` chọn 4 paper đại diện, sinh câu hỏi từ các field có dữ liệu thật (bỏ field rỗng như `categories="Unknown"`), `ground_truth_doc_ids=[paper_id]`. `retrieval_hit_rate` kiểm tra `paper_id` trả về có khớp ground-truth không — đây là tín hiệu đáng tin nhất vì độc lập với nội dung câu trả lời.
3. **Quality checks khác freshness monitoring ở điểm nào?** Quality checks đo tính toàn vẹn cấu trúc tức thời (null, trùng lặp, độ dài). Freshness chỉ đo một chiều: dữ liệu có còn mới so với ngưỡng thời gian hay không.
4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?** Để đo tác động của thay đổi dữ liệu chứ không phải thay đổi câu hỏi. Test set chỉ được sửa **một lần trước khi chạy chính thức cả 3 trạng thái**, sau đó khóa lại.
5. **Repair được xem là thành công dựa trên artifact và metric nào?** `data/quality/repaired.json` (10/10 pass), `freshness_report_repaired.json` (`is_fresh: true`), và `repaired_metrics.json` (4 metric quay về đúng baseline).

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.000 | 0.500 | 1.000 | Không đổi trước/sau khi tôi sửa test set — vì đây là metric dựa trên ID, không phụ thuộc nội dung câu trả lời, luôn đáng tin |
| `mean_token_f1` | 1.000 | 0.435 | 1.000 | Sau khi sửa, giảm mạnh hơn trước (0.625→0.435) — con số "xấu hơn" nhưng đúng hơn |
| `judge_accuracy` | 1.000 | 0.583 | 1.000 | Cùng lý do như trên |
| `mean_judge_score` | 5.000 | 3.500 | 5.000 | Giảm rõ rệt hơn, phản ánh đúng 6/12 câu bị miss |
| Quality checks | 10/10 pass | 5/10 pass | 10/10 pass | Không đổi qua các lần sửa — 5 check fail đúng khớp 6 loại corruption |
| Freshness status | Fresh | Stale (7 dòng) | Fresh | `stale_date` corruption phản ánh chính xác |

### Kết luận từ số liệu

1. **`drop_latest` xóa `10.1111/exsy.70341` và `10.2118/234689-pa`** (2/4 paper của test set) → toàn bộ câu hỏi liên quan có `retrieval_hit: false` → `retrieval_hit_rate` giảm chính xác 0.500, không đổi dù test set có 12 hay 16 câu vì tỉ lệ paper bị ảnh hưởng (2/4) không đổi.
2. **Repair chạy lại `build_clean_dataframe` trên raw records gốc** → mọi quality/freshness/metric phục hồi 100% về đúng baseline.

Corruption ảnh hưởng rõ nhất: **`drop_latest`** — vì là loại duy nhất làm mất hẳn tài liệu khỏi index, không thể bị "cứu" bởi trùng hợp ngẫu nhiên trong nội dung câu trả lời (như từng xảy ra với câu hỏi `categories` trước khi sửa).

Kết quả khác với kỳ vọng ban đầu: ở vòng phân tích đầu tiên, tôi từng báo cáo `mean_token_f1 corrupted = 0.625` và coi đó là số liệu cuối cùng. Sau khi chủ động soi từng câu trả lời thay vì chỉ tin con số tổng, tôi phát hiện con số đó bị lệch do lỗi thiết kế câu hỏi `categories`, và con số đúng sau khi sửa là **0.435** — thấp hơn đáng kể. Đây là bài học trực tiếp về việc không dừng lại ở "số liệu trông hợp lý" mà phải verify từng điểm dữ liệu.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Data pipeline:** Contract chung (chữ ký hàm) không đủ để tránh lỗi tích hợp — cần cả quy ước ngầm (tz-aware/tz-naive) và phải chạy lại toàn bộ pipeline mỗi khi có code mới từ đồng đội.
2. **Data quality/observability:** Một metric tổng hợp có thể che giấu lỗi nếu ground-truth ở nhiều document trùng nhau (như `"Unknown"`) — luôn cần đối chiếu nhiều metric độc lập, không chỉ tin con số cuối cùng đẹp hay xấu.
3. **Ảnh hưởng của data đến RAG agent:** Corruption làm **mất tài liệu khỏi index** có tác động trực tiếp, đo được rõ ràng và không thể bị nhiễu bởi trùng hợp ngẫu nhiên — trong khi metric dựa trên so khớp nội dung (`token_f1`) có thể bị "đánh lừa" nếu evaluation set thiết kế chưa chặt.

### Nếu có thêm thời gian

Sẽ thêm assertion tự động trong `evaluate_pipeline` để cảnh báo khi phát hiện cặp `retrieval_hit=false` nhưng `token_f1=1.0` (dấu hiệu ground-truth không đủ phân biệt) — đo cải thiện bằng cách chạy trên toàn bộ answers hiện có, kỳ vọng 0 cảnh báo sau các bản sửa đã áp dụng.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Bùi Hoàng Việt
**Ngày xác nhận:** 2026-08-06
