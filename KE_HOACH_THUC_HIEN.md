# Kế hoạch thực hiện — Day 10: Data Pipeline & Data Observability

> File gồm 2 phần: **Phần A** là phân tích yêu cầu đầy đủ (bài tập đang giải quyết gì, yêu cầu bắt buộc, module, task, kiến trúc, rủi ro...). **Phần B** là kế hoạch thực hiện theo từng bước kèm câu lệnh cụ thể để code và kiểm tra. Chạy trên Windows PowerShell (đã cài `uv`). Nếu dùng `pip` thay vì `uv`, bỏ tiền tố `uv run` và đảm bảo đã kích hoạt `.venv`.

---

# PHẦN A — PHÂN TÍCH YÊU CẦU

## A1. Bài tập này đang làm gì?

Đây là bài lab mô phỏng công việc của một Data/ML Engineer xây dựng và vận hành một **data pipeline phục vụ hệ thống RAG (Retrieval-Augmented Generation)**, dùng dữ liệu bài báo học thuật thật lấy từ **Crossref API**.

Vấn đề cốt lõi cần chứng minh: chất lượng dữ liệu đầu vào ảnh hưởng trực tiếp đến chất lượng câu trả lời của agent ("garbage in, garbage out"). Học viên phải: lấy dữ liệu → làm sạch → build vector index → cho agent trả lời câu hỏi → đo điểm → **cố ý làm hỏng dữ liệu** → đo điểm lại (phải tệ hơn) → **phục hồi dữ liệu từ nguồn raw** → đo điểm lại (phải khá hơn) → viết báo cáo so sánh ba trạng thái bằng **số liệu thật**.

Đây là **bài tập bắt buộc làm nhóm 3–5 người**, có phân công vai trò theo file, có mẫu báo cáo nhóm + cá nhân đi kèm, khung thời gian gợi ý 4 giờ (checkpoint timer trong `phan-cong-day-10-data-pipeline-4h(2).html`).

## A2. Mục tiêu cuối cùng

Một repository hoàn chỉnh gồm:
1. 12 hàm còn `NotImplementedError` trong `src/` được implement đúng contract có sẵn (không đổi chữ ký hàm).
2. Hai lệnh chạy end-to-end không lỗi: `script/run_phase1.py` và `script/run_corruption_flow.py`.
3. Đầy đủ artifact thật (JSON/CSV/Markdown) trong `data/` chứng minh pipeline chạy đúng.
4. Hai báo cáo Markdown tự sinh (`data/reports/phase1_report.md`, `data/reports/corruption_report.md`) khớp số liệu thật.
5. `report/group_report.md` và mỗi thành viên một `report/individual_report.md` (hoặc `<MSSV>_HoTen.md`) đã điền đầy đủ, không sao chép nhau.

## A3. Đầu vào và đầu ra

**Đầu vào:**
- Crossref REST API (`https://api.crossref.org/works`) — công khai, không cần key.
- Query/filter đã định sẵn trong `src/core/config.py`: `source_query="agentic retrieval augmented generation large language model"`, `source_filter="from-pub-date:<180 ngày trước>,has-abstract:true"`, `max_results=24`.
- API key của 1 LLM provider tự chọn, điền vào `.env` (Gemini là mặc định).
- Code starter với contract (dataclass, chữ ký hàm) đã cố định trong `src/`.

**Đầu ra bắt buộc** (path đã cố định trong `Paths` — không tự đặt path khác):

| Nhóm | File/thư mục |
|---|---|
| Raw | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` |
| Clean | `data/clean/papers_clean.{csv,json}` (+ `_corrupted`, `_repaired`) |
| Embedding | `data/embeddings/papers_embeddings.json` (+ `_corrupted`, `_repaired`) + Chroma tại `data/chroma/` |
| Eval | `data/eval/test_set.json` |
| Kết quả | `data/results/baseline_metrics.json`, `baseline_answers.json`, `corruption_log.json`, `corrupted_metrics.json`, `corrupted_answers.json`, `repaired_metrics.json`, `repaired_answers.json` |
| Quality | `data/quality/freshness_report.json` + quality check khác |
| Report | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` |
| Báo cáo nhóm | `report/group_report.md`, `report/individual_report.md` |

## A4. Các yêu cầu bắt buộc

**Chức năng/dữ liệu:**
- Lưu raw response gốc trước khi parse + raw records đã parse riêng biệt; retry/backoff cho `429/503`.
- `PaperRecord.paper_id` phải ổn định (dùng DOI), tái sử dụng được ở raw → clean → index → repair.
- Cleaning: chuẩn hóa title/summary/authors/categories, tính `age_days`, tạo `text_for_embedding`, dedupe theo ID, loại record hỏng — **phải log/đếm** số record bị loại.
- Test set sinh từ cleaned dataset thật, mỗi sample có `id, question_type, question, ground_truth, ground_truth_doc_ids`; **giữ nguyên, dùng chung** cho baseline/corrupted/repaired.
- Quality checks tối thiểu: row count, `paper_id` not-null & unique, `title` not-null, độ dài `summary`, freshness qua `age_days`.
- Corruption phải có chủ đích, có tham số, có log (6 loại: xoá bản ghi mới nhất, blank summary, noise text, truncate title, làm cũ ngày publish, thêm duplicate).
- Corrupted/repaired dùng path và Chroma collection riêng (`papers-corrupted`, `papers-repaired`) — **không ghi đè** baseline.
- Repair chạy lại từ raw source đáng tin — không sửa tay JSON kết quả.

**Backend/xử lý dữ liệu (đã có code tham khảo, không cần code lại):** Embedding MiniLM, ChromaDB, LangChain agent với tool `semantic_search_papers`/`lookup_paper`, multi-provider LLM (OpenAI/Gemini/Anthropic/OpenRouter/Ollama/custom).

**Bảo mật:** không commit `.env`/API key/secret; không hard-code path tuyệt đối hoặc key.

**Kiểm thử:** không có test/grader tự động — xác minh bằng chạy lệnh thật + đối chiếu artifact + `Rubric.md`. Report không được mô tả khác artifact thực tế.

**Tài liệu:** `report/group_report.md` (13 mục có sẵn) + mỗi thành viên một `individual_report.md` riêng, không sao chép.

**Ngoài phạm vi:** không cần frontend/UI, không cần API HTTP expose ra ngoài, không cần database quan hệ (chỉ file JSON/CSV + Chroma), không cần deploy, không cần slide/video (demo là trình bày trực tiếp buổi học).

## A5. Sản phẩm cần bàn giao

| # | Sản phẩm | Định dạng | Ưu tiên |
|---|---|---|---|
| 1 | Source code hoàn thiện (12 hàm) | `.py` | Bắt buộc, cao nhất |
| 2 | Raw artifacts | JSON | Bắt buộc |
| 3 | Cleaned dataset (baseline/corrupted/repaired) | CSV + JSON | Bắt buộc |
| 4 | Embedding + Chroma index (x3) | JSON + Chroma dir | Bắt buộc |
| 5 | Evaluation test set | JSON | Bắt buộc |
| 6 | Metrics + answers (x3) | JSON | Bắt buộc |
| 7 | Corruption log | JSON | Bắt buộc |
| 8 | Data quality + freshness report | JSON | Bắt buộc |
| 9 | Baseline report | `.md` | Bắt buộc |
| 10 | Comparison report | `.md` | Bắt buộc |
| 11 | Group report | `.md` | Bắt buộc |
| 12 | Individual reports | `.md` | Bắt buộc |
| 13 | Demo trực tiếp | — | Bắt buộc (theo lịch nhóm) |

Tiêu chí chung: artifact phải là kết quả chạy thật, path đúng `Paths`, report khớp 100% với `data/`.

## A6. Các module chính (theo thứ tự phụ thuộc)

| # | Module | Trạng thái | Mục tiêu | File |
|---|---|---|---|---|
| M0 | Core & Reference code | ✅ Có sẵn — chỉ đọc hiểu | Settings/Paths, IO utils, embedding, Chroma index, multi-LLM, agent, QA, evaluation runner | `core/*`, `retrieval/*`, `evaluation/metrics.py` |
| M1 | Raw Ingestion | ❌ Cần code (3 hàm) | Lấy Crossref, lưu raw, parse `PaperRecord` | `ingestion/crossref.py` |
| M2 | Cleaning & Data Modeling | ❌ Cần code (1 hàm) | Chuẩn hóa, `text_for_embedding`, `age_days` | `ingestion/cleaning.py` |
| M3 | Evaluation Test Set | ❌ Cần code (1 hàm) | Sinh câu hỏi + ground truth | `evaluation/testset.py` |
| M4 | Data Observability | ❌ Cần code (2 hàm) | Quality checks + freshness | `observability/quality.py` |
| M5 | Reporting | ❌ Cần code (2 hàm) | Markdown report tự sinh | `observability/reporting.py` |
| M6 | Baseline Orchestration | ❌ Cần code (`main`) | Ghép M1→M2→M0(index)→M3→M0(eval)→M4→M5 | `pipelines/phase1.py` |
| M7 | Corruption Simulation | ❌ Cần code (1 hàm) | Sinh 6 loại lỗi có log | `ingestion/corruption.py` |
| M8 | Corruption Flow Orchestration | ❌ Cần code (`main`) | corrupt→rebuild→evaluate→quality→repair→evaluate→compare | `pipelines/corruption_flow.py` |

Thứ tự bắt buộc: M0 (đọc) → M1 → M2 → M3 (song song được với build index) → M6 → **chỉ sau khi M6 thành công** → M7 → M8.

## A7. Danh sách task chi tiết (Input/Output/Phụ thuộc/Kiểm tra)

**T-ING-01 — `parse_crossref_payload(payload: dict) -> list[PaperRecord]`**
Input: dict JSON Crossref (`payload["message"]["items"]`). Output: list `PaperRecord` (11 field: `paper_id, title, summary, authors, categories, primary_category, published, updated, abs_url, pdf_url, comment`). Việc làm: lấy DOI làm `paper_id`, `title[0]`, strip tag JATS khỏi abstract, `author` → tên đầy đủ, `subject` → categories, ưu tiên `published-print`/`published-online`/`created` cho ngày, `URL`/`link` cho PDF. Bỏ item thiếu title/DOI. Phụ thuộc: không. Kiểm tra: chạy trên payload mẫu, in vài record.

**T-ING-02 — `fetch_source_records(settings) -> list[PaperRecord]`**
Input: `Settings`. Output: list `PaperRecord`; ghi `raw_api_response` + `raw_records_json`. Việc làm: build params từ `source_query/source_filter/max_results`, gọi Crossref với retry/backoff cho `429/503`, lưu response thô trước khi parse. Phụ thuộc: T-ING-01. Kiểm tra: `data/raw/` có 2 file JSON không rỗng.

**T-ING-03 — `load_raw_records(path) -> list[PaperRecord]`**
Input: path tới `crossref_records.json`. Output: list `PaperRecord` (dùng cho repair, không fetch lại). Phụ thuộc: T-ING-02. Kiểm tra: độ dài khớp với lúc fetch.

**T-CLN-01 — `build_clean_dataframe(records, run_date) -> pd.DataFrame`**
Output: DataFrame có `paper_id, title, summary, authors_joined, categories_joined, published, age_days, summary_chars, text_for_embedding`. Việc làm: normalize whitespace, parse `published`, `age_days = (run_date - published).days`, `text_for_embedding = title + summary` (+authors/categories tuỳ chọn), dedupe theo `paper_id`, drop row hỏng, sort theo `published`. Phụ thuộc: T-ING-01/02/03. Kiểm tra: `paper_id` unique, `text_for_embedding` không rỗng.

**T-EVAL-01 — `build_test_set(df, output_path) -> list[dict]`**
Output: list dict ghi ra `test_set.json`. Việc làm: kiểm tra đủ record tối thiểu, chọn N paper đại diện, sinh câu hỏi 4 loại (summary/authors/date/categories) khớp cách `qa.py._extract_answer` nhận diện (`who authored`, `when was`, `what categories`), `ground_truth_doc_ids=[paper_id]`. Phụ thuộc: T-CLN-01. Kiểm tra: mọi `ground_truth_doc_ids` tồn tại trong clean data.

**T-OBS-01 — `run_data_quality_checks(df, settings, report_name) -> dict`**
Việc làm: row count > 0, `paper_id` not-null & unique, `title` not-null, `summary` đủ dài, tỉ lệ `age_days` vượt ngưỡng. Phụ thuộc: T-CLN-01 (và tương đương cho corrupted/repaired). Kiểm tra: baseline pass hết, corrupted có fail có evidence.

**T-OBS-02 — `build_freshness_report(df, settings, report_path) -> dict`**
Output: `latest_published, oldest_published, stale_rows, total_rows, is_fresh`. Phụ thuộc: T-CLN-01. Kiểm tra: baseline `is_fresh=true`, corrupted (sau khi làm cũ ngày) `is_fresh=false`/`stale_rows` tăng.

**T-REPORT-01 — `generate_phase1_report(...)`**
Ghi `phase1_report.md` từ source_summary + metrics + quality + freshness (chỉ format, không tính lại). Phụ thuộc: M1, M0(eval), M4. Kiểm tra: số liệu khớp `baseline_metrics.json`.

**T-REPORT-02 — `generate_corruption_report(...)`**
Ghi `corruption_report.md` so sánh 3 trạng thái. Phụ thuộc: M8 chạy xong cả 2 vòng evaluate. Kiểm tra: bảng so sánh khớp 3 file JSON.

**T-PIPE-01 — `phase1.main()`**
Ghép: load settings → fetch/load raw → clean → lưu clean → build index baseline → tạo/đọc test set → evaluate → quality → freshness → report. Phụ thuộc: tất cả M1–M5. Kiểm tra: `run_phase1.py` chạy hết, đủ file theo README mục 6.

**T-CORR-01 — `corrupt_clean_dataframe(df, output_log_path) -> pd.DataFrame`**
6 kỹ thuật corruption, mỗi kỹ thuật log `{type, affected_ids, params, before, after}`. **Phải rebuild `text_for_embedding`** cho record bị sửa summary/title (lỗi hay gặp nhất là quên bước này). Phụ thuộc: T-CLN-01. Kiểm tra: log liệt kê đủ loại, số record ảnh hưởng > 0.

**T-PIPE-02 — `corruption_flow.main()`**
Ghép: đọc baseline_metrics + clean → corrupt → lưu → build index `papers-corrupted` → evaluate (cùng test set) → quality/freshness → repair (load_raw_records → build_clean_dataframe lại → index `papers-repaired`) → evaluate lại → quality/freshness → comparison report. Phụ thuộc: M6 phải xong trước, M7, M3, M4, M5. Kiểm tra: `repaired_metrics.json` tồn tại; `papers-baseline` không bị mutate.

## A8. Thứ tự thực hiện

```
Bước 0  Đọc & hiểu code tham khảo (core, retrieval, evaluation/metrics)
Bước 1  T-ING-01 → T-ING-02 → T-ING-03                                    (M1)
Bước 2  T-CLN-01                                                          (M2, cần M1)
Bước 3  T-EVAL-01  ‖  build index baseline                               (M3, cần M2 — song song được)
Bước 4  T-OBS-01 → T-OBS-02                                               (M4, cần M2)
Bước 5  T-REPORT-01 (bản baseline)                                        (M5, cần M3+M4+eval runner)
Bước 6  T-PIPE-01: ghép phase1.py, chạy script/run_phase1.py             (M6)
        ⇒ ĐIỂM DỪNG BẮT BUỘC: chỉ tiếp tục khi baseline_metrics.json hợp lý
Bước 7  T-CORR-01                                                         (M7, cần M2)
Bước 8  T-REPORT-02 (bản so sánh)                                         (M5 phần 2)
Bước 9  T-PIPE-02: ghép corruption_flow.py, chạy script/run_corruption_flow.py (M8)
Bước 10 Điền group_report.md + individual_report.md, đối chiếu Rubric.md
```

## A9. Kiến trúc và công nghệ (đã cố định sẵn trong starter — không tự đổi)

| Thành phần | Công nghệ | Vì sao phù hợp |
|---|---|---|
| Nguồn dữ liệu | Crossref REST API | Miễn phí, không cần key, đủ mô phỏng ETL thật |
| Ngôn ngữ | Python 3.11–3.13 | Hệ sinh thái data/LLM mạnh nhất |
| Package manager | `uv` (khuyến nghị) hoặc pip+venv | Tái lập chính xác từ `uv.lock` |
| Xử lý dữ liệu | pandas | Chuẩn cho bảng dữ liệu cỡ vừa (24 record) |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` | Nhỏ, chạy CPU nhanh |
| Vector store | ChromaDB (persistent local) | Nhẹ, dễ tạo nhiều collection tách biệt |
| Agent | LangChain `create_agent` | Chuẩn hoá tool-calling, đã có sẵn |
| LLM | Đa provider qua LangChain (Gemini mặc định) | Mỗi nhóm dùng provider có sẵn key |
| Đánh giá | Token-F1 tự viết + LLM-judge + Ragas (optional) | Kết hợp metric rẻ và metric ngữ nghĩa |
| Data quality | pandas thuần (Great Expectations optional, dùng cho bonus) | Đủ cho yêu cầu tối thiểu |
| Cấu hình | `.env` + `python-dotenv` | Tách secret khỏi code |

## A10. Luồng hoạt động

```
uv run python script/run_phase1.py
  → load Settings (.env)
  → fetch/load raw Crossref records (data/raw/)
  → clean thành dataframe (data/clean/)
  → build embedding + Chroma "papers-baseline" (data/embeddings/, data/chroma/)
  → tạo/đọc test set (data/eval/test_set.json)
  → mỗi câu hỏi: search Chroma → top-k context → trả lời → LLM-judge chấm
  → tổng hợp metrics (data/results/baseline_metrics.json)
  → quality checks + freshness (data/quality/)
  → sinh phase1_report.md

uv run python script/run_corruption_flow.py   (SAU khi trên chạy xong)
  → đọc baseline_metrics.json + papers_clean.csv
  → corrupt_clean_dataframe() → log (data/results/corruption_log.json)
  → build index "papers-corrupted" (KHÔNG đụng "papers-baseline")
  → evaluate với CÙNG test_set.json → corrupted_metrics.json (phải tệ hơn)
  → quality/freshness trên corrupted (phải có fail)
  → repair: load_raw_records() (raw gốc) → build_clean_dataframe() lại
  → build index "papers-repaired" → evaluate lại → repaired_metrics.json (gần baseline hơn)
  → generate_corruption_report() so sánh 3 trạng thái
```

**Error flow:** Crossref `429/503` → retry/backoff, không tạo dữ liệu giả. Thiếu API key → `require_llm_credentials` raise rõ ràng. LLM-judge lỗi → đã có fallback heuristic sẵn trong `metrics.py`. Ragas lỗi → trả `{"error": ...}`, không crash. Chạy `corruption_flow.py` trước `phase1.py` → phải fail rõ ràng, không tự tạo baseline giả.

## A11. Rủi ro và phương án xử lý

| Rủi ro | Phương án xử lý |
|---|---|
| Parse Crossref không ổn định (abstract có tag JATS, ngày nằm ở nhiều field khác nhau) | Strip tag bằng regex; dùng `.get()` với fallback qua nhiều field ngày theo thứ tự ưu tiên; log record bị bỏ thay vì crash |
| `paper_id` không ổn định nếu dùng index thay vì DOI | Luôn dùng DOI chuẩn hoá; test bằng cách fetch 2 lần, so sánh ID |
| Corruption không đủ mạnh để thấy khác biệt | Chọn tỉ lệ đủ lớn (30–50% record); **bắt buộc rebuild `text_for_embedding`** sau khi sửa summary/title |
| Quên giữ test set cố định | Dùng cờ `settings.refresh_test_set` có sẵn, chỉ tạo mới khi chưa tồn tại |
| Vô tình ghi đè `papers-baseline` khi build corrupted/repaired | Luôn truyền đúng `embeddings_output_path` tương ứng — `_derive_collection_name` đã map sẵn |
| LLM-judge phụ thuộc API ngoài (rate limit, timeout) | Đã có fallback heuristic trong `metrics.py`; ghi rõ trong báo cáo nếu dùng fallback |
| Great Expectations/Ragas nặng, có thể lỗi cài | Cả 2 optional — GX chỉ cho bonus, Ragas mặc định tắt (`RUN_RAGAS`) |
| Phối hợp nhóm 3–5 người, module phụ thuộc chặt schema chung | Thống nhất contract (raw/clean schema, `paper_id`, test set format) trước khi code song song |

## A12. Tiêu chí kiểm thử

- Unit-thủ công từng hàm: xem lệnh cụ thể ở Phần B.
- Tích hợp: `run_phase1.py` và `run_corruption_flow.py` chạy exit code 0, đủ file theo README mục 6.
- Toàn hệ thống: `corrupted_metrics` thấp hơn `baseline_metrics` (cùng test set); `repaired_metrics` phục hồi gần `baseline_metrics`; corrupted có ít nhất 1 quality/freshness check fail mà baseline pass; `corruption_report.md` khớp 100% với JSON.

## A13. Checklist hoàn thành (đối chiếu trước khi nộp)

- [ ] `rg -n "TODO(student)|NotImplementedError" src` rỗng.
- [ ] `uv sync` sạch trên máy mới.
- [ ] `.env` không commit; không secret trong log/report.
- [ ] `run_phase1.py` chạy sạch.
- [ ] `run_corruption_flow.py` chạy sạch, sau baseline.
- [ ] Đủ artifact `data/raw`, `data/clean`, `data/embeddings`, `data/eval`, `data/results`, `data/quality`, `data/reports`.
- [ ] `papers-baseline` không bị mutate sau corruption flow.
- [ ] Metrics chứng minh corrupted < baseline và repaired ≈ baseline bằng số liệu thật.
- [ ] `group_report.md` + mỗi `individual_report.md` khớp `data/` thật, không sao chép nhau.
- [ ] Đối chiếu từng mục `Rubric.md` — không mục nào ở mức thấp nhất.

## A14. Thông tin còn thiếu / giả định / cần xác nhận

- Số lượng thành viên nhóm và vai trò cụ thể của bạn — quyết định module nào ưu tiên trước.
- Deadline chính xác — không có trong repo.
- Tên nhóm, danh sách MSSV — cần điền `group_report.md`.
- Provider LLM sẽ dùng — `.env.example` mặc định Gemini nhưng key đang rỗng.
- Ngưỡng cụ thể "fresh/stale" trong `build_freshness_report` — Guide không cho công thức cứng, nhóm tự quyết định và giải thích trong báo cáo.
- Tỉ lệ/tham số corruption cụ thể — nhóm tự chọn, miễn đủ mạnh để thấy tác động.

---

# PHẦN B — KẾ HOẠCH THỰC HIỆN THEO BƯỚC, KÈM CÂU LỆNH

## Bước 0 — Chuẩn bị môi trường

```powershell
cd "c:\CODE\AITHUCCHIEN\1. LABS\K4_Day10_Data-Pipeline-Data-Observability"
python --version                      # phải là 3.11, 3.12 hoặc 3.13
uv sync                               # cài project + dependency theo uv.lock
Copy-Item .env.example .env           # tạo file .env cục bộ
notepad .env                          # điền LLM_PROVIDER, LLM_MODEL và API key tương ứng
```

Kiểm tra còn bao nhiêu phần chưa code (phải giảm dần về 0 khi làm xong):

```powershell
Get-ChildItem src -Recurse -Filter *.py | Select-String -Pattern 'TODO\(student\)|NotImplementedError'
```

Nếu có `rg` (ripgrep):

```bash
rg -n "TODO\(student\)|NotImplementedError" src
```

**Tiêu chí qua bước:** `uv sync` chạy sạch, `.env` tồn tại (không commit), lệnh trên liệt kê đủ 24 dòng ban đầu.

---

## Bước 1 — Raw ingestion (`src/ingestion/crossref.py`)

Code 3 hàm: `parse_crossref_payload`, `fetch_source_records`, `load_raw_records`.

**Test nhanh sau khi code xong** (gọi trực tiếp không qua pipeline):

```powershell
uv run python -c "from core.config import load_settings; from ingestion.crossref import fetch_source_records; s = load_settings(); recs = fetch_source_records(s); print(len(recs)); print(recs[0])"
```

**Kiểm tra artifact:**

```powershell
Get-ChildItem data\raw
Get-Content data\raw\crossref_records.json -TotalCount 40
```

**Test `load_raw_records` (dùng lại raw đã lưu, không gọi API):**

```powershell
uv run python -c "from core.config import load_settings; from ingestion.crossref import load_raw_records; s = load_settings(); recs = load_raw_records(s.paths.raw_records_json); print(len(recs))"
```

**Tiêu chí qua bước:** `data/raw/crossref_response.json` và `crossref_records.json` không rỗng; mỗi record có `paper_id` khác rỗng và không trùng.

---

## Bước 2 — Cleaning (`src/ingestion/cleaning.py`)

Code hàm `build_clean_dataframe`.

**Test nhanh:**

```powershell
uv run python -c "from core.utils import now_utc; from core.config import load_settings; from ingestion.crossref import load_raw_records; from ingestion.cleaning import build_clean_dataframe; s = load_settings(); recs = load_raw_records(s.paths.raw_records_json); df = build_clean_dataframe(recs, now_utc()); print(df.shape); print(df[['paper_id', 'title', 'age_days']].head()); df.to_csv(s.paths.clean_csv, index=False); import json; s.paths.clean_json.parent.mkdir(parents=True, exist_ok=True); s.paths.clean_json.write_text(df.to_json(orient='records', indent=2))"
```

**Kiểm tra artifact:**

```powershell
Get-ChildItem data\clean
```

**Tiêu chí qua bước:** `paper_id` không trùng (`df['paper_id'].is_unique == True`), không có `text_for_embedding` rỗng, `age_days` là số hợp lệ.

---

## Bước 3 — Test set + Embedding/Index (`src/evaluation/testset.py`)

Code hàm `build_test_set`. (Phần embedding/index trong `src/retrieval/` đã có sẵn — chỉ cần gọi, không cần code lại.)

**Build test set:**

```powershell
uv run python -c "import pandas as pd; from core.config import load_settings; from evaluation.testset import build_test_set; s = load_settings(); df = pd.read_csv(s.paths.clean_csv); ts = build_test_set(df, s.paths.eval_testset); print(len(ts)); print(ts[0])"
```

**Build Chroma index baseline (dùng code có sẵn):**

```powershell
uv run python -c "import pandas as pd; from core.config import load_settings; from retrieval.index import LocalEmbeddingIndex; s = load_settings(); df = pd.read_csv(s.paths.clean_csv); idx = LocalEmbeddingIndex.build(df, s); print(idx.collection_name, len(idx.documents))"
```

**Smoke test search + lookup:**

```powershell
uv run python -c "from core.config import load_settings; from retrieval.index import LocalEmbeddingIndex; s = load_settings(); idx = LocalEmbeddingIndex.load(s); results = idx.search('retrieval augmented generation'); [print(r.paper_id, r.title, round(r.score,3)) for r in results]"
```

**Tiêu chí qua bước:** `data/eval/test_set.json` tồn tại, mọi `ground_truth_doc_ids` trùng khớp `paper_id` trong clean data; search trả về document có nội dung hợp lý.

---

## Bước 4 — Data quality & freshness (`src/observability/quality.py`)

Code 2 hàm: `run_data_quality_checks`, `build_freshness_report`.

**Test nhanh:**

```powershell
uv run python -c "import pandas as pd; from core.config import load_settings; from observability.quality import run_data_quality_checks, build_freshness_report; s = load_settings(); df = pd.read_csv(s.paths.clean_csv); print(run_data_quality_checks(df, s, 'baseline')); print(build_freshness_report(df, s, s.paths.freshness_report))"
```

**Kiểm tra artifact:**

```powershell
Get-ChildItem data\quality
Get-Content data\quality\freshness_report.json
```

**Tiêu chí qua bước:** mọi check pass trên baseline; `is_fresh = true`.

---

## Bước 5 — Ghép baseline pipeline (`src/pipelines/phase1.py`)

Code hàm `main()`, gọi lại toàn bộ Bước 1–4 theo đúng thứ tự + `evaluate_pipeline` (đã có sẵn ở `src/evaluation/metrics.py`) + `generate_phase1_report` (`src/observability/reporting.py`, cần code song song).

**Chạy toàn bộ baseline:**

```powershell
uv run python script/run_phase1.py
```

**Kiểm tra toàn bộ output:**

```powershell
Get-ChildItem data\raw, data\clean, data\embeddings, data\eval, data\results, data\quality, data\reports
Get-Content data\results\baseline_metrics.json
Get-Content data\reports\phase1_report.md
```

**Tiêu chí qua bước — CHỈ được sang Bước 6 khi đạt hết:**
- Lệnh chạy xong không lỗi (exit code 0).
- `data/results/baseline_metrics.json` tồn tại và có `retrieval_hit_rate`, `mean_token_f1`, `judge_accuracy`, `mean_judge_score`.
- `data/reports/phase1_report.md` đọc được, số liệu khớp file JSON trên.

---

## Bước 6 — Corruption (`src/ingestion/corruption.py`)

Code hàm `corrupt_clean_dataframe`.

**Test nhanh:**

```powershell
uv run python -c "import pandas as pd; from core.config import load_settings; from ingestion.corruption import corrupt_clean_dataframe; s = load_settings(); df = pd.read_csv(s.paths.clean_csv); cdf = corrupt_clean_dataframe(df, s.paths.corruption_log); print(cdf.shape)"
```

**Kiểm tra log:**

```powershell
Get-Content data\results\corruption_log.json
```

**Tiêu chí qua bước:** log liệt kê đủ các loại corruption đã áp dụng, kèm số record bị ảnh hưởng > 0; `text_for_embedding` của record bị sửa summary/title đã được rebuild lại (không còn giữ text cũ).

---

## Bước 7 — Ghép corruption flow (`src/pipelines/corruption_flow.py`)

Code hàm `main()` + hàm `generate_corruption_report` trong `src/observability/reporting.py`.

**Bắt buộc chạy sau khi Bước 5 đã thành công** (cần `baseline_metrics.json` làm mốc so sánh).

```powershell
uv run python script/run_corruption_flow.py
```

**Kiểm tra toàn bộ output:**

```powershell
Get-Content data\results\corruption_log.json
Get-Content data\results\corrupted_metrics.json
Get-Content data\results\repaired_metrics.json
Get-Content data\reports\corruption_report.md
```

**Đối chiếu baseline không bị ảnh hưởng:**

```powershell
uv run python -c "from core.config import load_settings; from retrieval.index import LocalEmbeddingIndex; s = load_settings(); idx = LocalEmbeddingIndex.load(s, s.paths.embeddings_json); print(idx.collection_name, len(idx.documents))"
```

**Tiêu chí qua bước:**
- `corrupted_metrics.json` có `retrieval_hit_rate`/`mean_token_f1`/`judge_accuracy` **thấp hơn** `baseline_metrics.json`.
- `repaired_metrics.json` **phục hồi gần bằng** baseline.
- Collection `papers-baseline` vẫn nguyên vẹn (không bị lệnh trên ghi đè).
- `corruption_report.md` khớp với 3 file JSON metrics.

---

## Bước 8 — Báo cáo nhóm và cá nhân

```powershell
notepad report\group_report.md
notepad report\individual_report.md
```

Nếu lưu nhiều bản cá nhân trong cùng repo, đặt tên theo quy ước `<MSSV>_HoTen.md` trong thư mục `report/`.

**Tiêu chí qua bước:** số liệu trong 2 báo cáo khớp 100% với file trong `data/results/` và `data/quality/`; mỗi thành viên có bản riêng, không sao chép.

---

## Kiểm tra cuối cùng trước khi nộp

```powershell
Get-ChildItem src -Recurse -Filter *.py | Select-String -Pattern 'TODO\(student\)|NotImplementedError'   # phải rỗng
git status
```

- [ ] Lệnh trên trả về rỗng (không còn TODO/NotImplementedError).
- [ ] `uv run python script/run_phase1.py` chạy sạch trên bản mới nhất.
- [ ] `uv run python script/run_corruption_flow.py` chạy sạch, sau baseline.
- [ ] Đủ artifact trong `data/raw`, `data/clean`, `data/embeddings`, `data/eval`, `data/results`, `data/quality`, `data/reports`.
- [ ] `report/group_report.md` và mọi `individual_report.md` đã điền, khớp artifact thật.
- [ ] `git status` không lộ `.env` hoặc secret nào (`.gitignore` đã chặn `.env` sẵn, chỉ cần xác nhận).
- [ ] Đối chiếu `Rubric.md` — không mục nào ở mức thấp nhất.
