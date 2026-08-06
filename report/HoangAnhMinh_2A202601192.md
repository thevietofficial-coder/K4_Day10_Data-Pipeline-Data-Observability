# Báo cáo cá nhân — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Hoàng Anh Minh |
| MSSV | 2A202601192 |
| Khóa/Lớp | K4 |
| Tên nhóm | SilverFlag |
| Vai trò chính | Thành viên 5 — Pipeline Integration & Evidence Owner; phụ trách các checkpoint evaluation/observability |
| Repository | https://github.com/thevietofficial-coder/K4_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Evaluation set | `src/evaluation/testset.py` | Cleaned dataframe có `paper_id` ổn định | `data/eval/test_set.json` gồm 16 câu hỏi và 4 loại câu hỏi | Hoàn thành |
| Evaluation audit | `src/evaluation/metrics.py`, `src/observability/audit.py` | Test set, answers, metrics, embedding manifest và Chroma catalog | Kiểm tra SHA-256, ID coverage, document count và tính lại metric từ answers | Hoàn thành |
| Quality và freshness evidence | `src/observability/quality.py` | Cleaned/corrupted/repaired dataframe; `published`, `age_days` | Các JSON quality/freshness cho ba trạng thái | Hoàn thành |
| Reporting | `src/observability/reporting.py` | Metrics, answers, quality, freshness và index audit thật | Baseline, corrupted-evidence và three-state comparison report | Hoàn thành |
| Recovery integration | `src/pipelines/corruption_flow.py` | Artifact baseline, corrupted và repaired | `recovery_checkpoint.json` và `corruption_report.md` | Hoàn thành |

Triển khai và kiểm chứng phần evaluation/observability ở các checkpoint 1, 2, 3, 5 và 6. Phạm vi của tôi không bao gồm việc sở hữu logic fetch Crossref, cleaning gốc, embedding model hay thuật toán tạo corruption; tôi nhận artifact từ các module đó để đánh giá, audit và tạo bằng chứng tích hợp.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Tích hợp recovery checkpoint vào corruption flow | `src/pipelines/corruption_flow.py` | Flow CP6 tự audit repaired manifest/index, đối chiếu ba bộ answers/metrics và sinh report từ một checkpoint đã xác thực |
| Kiểm tra artifact sau rebase | Nhánh `develop` | Commit CP6 được rebase không conflict, compile và kiểm tra checkpoint lại trước khi push |
| Loại bỏ side effect audit lên Chroma | Observability/index audit | Đọc Chroma catalog bằng SQLite read-only; các file index không bị đưa vào commit chỉ vì thao tác audit |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Tạo test set từ cleaned data | `build_test_set`, `load_frozen_test_set`, `data/eval/test_set.json` | 16 câu hỏi thuộc `summary`, `authors`, `date`, `categories`; 4 `ground_truth_doc_ids` đều lấy từ `paper_id` thật | Đọc test set và so ID với embedding manifest |
| Audit baseline index và test set | `audit_embedding_manifest`, `build_baseline_artifact_audit` | Collection `papers-baseline`, 24 documents; SHA test set cố định | `data/quality/baseline_audit.json` |
| Ghi mốc baseline | `write_baseline_checkpoint` | Hit rate, token F1, judge accuracy đều 1.0; judge score 5.0 | `data/quality/baseline_checkpoint.json` |
| Gắn corruption với tín hiệu và metric | `write_corrupted_checkpoint` | Ghi rõ signal thay đổi, case xấu đi và loại corruption chưa đủ bằng chứng attribution | `data/quality/corrupted_checkpoint.json` |
| Audit phục hồi ba trạng thái | `write_recovery_checkpoint` | Tự kiểm tra sample IDs, test SHA, metrics khớp answers, quality khớp freshness và residual so với baseline | `data/quality/recovery_checkpoint.json` |
| Sinh báo cáo comparison | `generate_recovery_comparison_report` | Bảng baseline/corrupted/repaired, hit/miss thật, kết luận và giới hạn | `data/reports/corruption_report.md` |

Output tiêu biểu là `data/quality/recovery_checkpoint.json`. Artifact này chứng minh cả ba evaluation dùng test set SHA-256 `88846fd8575b8fe78cd02cc8e3647a06833666568a430c04d030acac8d13ba00`; 8 case giảm dưới corruption đều trở lại baseline; không còn metric, signal hoặc answer case chưa phục hồi trong phạm vi đo.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Nếu chỉ nhìn một file metric tổng hợp, nhóm có thể kết luận sai vì test set đã đổi, ground-truth ID không còn trong index, judge dùng fallback, hoặc quality/freshness đến từ lần chạy khác nhau. Phần của tôi tạo chuỗi bằng chứng có thể audit từ cleaned `paper_id` đến test set, index, per-question answers, metrics và report ba trạng thái.

### Cách triển khai

Test set chỉ được tạo từ cleaned dataframe sau khi `paper_id` đã ổn định. Mỗi paper đại diện tạo bốn câu hỏi có đáp án kiểm chứng được trực tiếp từ `summary`, `authors`, `published` và `categories`. `ground_truth_doc_ids` luôn chứa chính `paper_id` của record, không sinh ID giả. Khi đọc test set cố định, loader chuẩn hóa schema, kiểm tra ID trùng/blank, tính SHA-256 và xác minh ID có trong index.

Evaluator ghi cả answer, retrieved document IDs, contexts, retrieval hit, token F1 và structured judge verdict. `retrieval_hit_rate` là tỷ lệ câu có ít nhất một retrieved ID thuộc ground-truth IDs. Token F1 hiện tại đo lexical overlap trên tập token đã lower-case/chuẩn hóa khoảng trắng; nó không thay thế semantic evaluation. Judge metric là đánh giá của LLM theo thang 1–5 và cờ `correct`, nên phải được đọc cùng retrieval hit và token F1.

Quality checks đo row count, null `paper_id`/title/summary, duplicate ID/record, summary ngắn, `age_days` thiếu hoặc không hợp lệ và stale rows. Freshness dùng `published` có nguồn Crossref để lấy biên ngày, còn `age_days` đã materialize trong bước cleaning để so với ngưỡng 180 ngày. Nó không tự gán ngày xuất bản bằng ngày hiện tại.

Recovery checkpoint chỉ được ghi khi ba bộ answers có cùng sample IDs, metrics tính lại từ answers khớp JSON, SHA test set giống nhau, và các giá trị `row_count`, `stale_rows`, `max_age_days` giữa quality/freshness đồng nhất. Report chỉ format checkpoint này, không tự bịa hoặc tính từ số hard-code.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Clean JSON; frozen test set; embedding manifest/Chroma catalog; ba cặp answers/metrics; quality/freshness JSON; corruption log |
| Output | Audit/checkpoint JSON và Markdown report có bảng delta, case evidence, trạng thái recovery và limitations |
| Module phụ thuộc | `core.config`, `core.utils`, `evaluation.metrics`, `evaluation.testset`, `retrieval.index` |
| Module sử dụng output | `pipelines.phase1`, `pipelines.corruption_flow`, báo cáo nhóm và phần demo |
| Điều kiện lỗi cần xử lý | Test SHA khác nhau; sample IDs lệch; metric không khớp answers; manifest sai collection/count; ground-truth ID thiếu; quality/freshness không cùng tín hiệu; judge fallback |

### Cách xác minh

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe script\run_phase1.py
.\.venv\Scripts\python.exe script\run_corruption_flow.py
Get-Content data\quality\recovery_checkpoint.json
Get-Content data\reports\corruption_report.md
```

- **Kết quả mong đợi:** ba trạng thái dùng cùng test set; artifact đủ; report khớp JSON; corrupted xấu hơn baseline và repaired được đánh giá trung thực.
- **Kết quả thực tế:** compile PASS; test SHA giống nhau; baseline/corrupted/repaired lần lượt có retrieval hit rate `1.0/0.5/1.0`; repaired quality/freshness/index audit đều PASS.
- **Artifact/log:** `data/quality/recovery_checkpoint.json`, `data/reports/corruption_report.md`; không ghi API key hoặc secret.
- **Kiểm thử:** `python -m pytest tests -q --basetemp=.pytest-tmp-final-2` đạt `29 passed`; `script/test_retrieval.py` là integration script cần model/network nên không thuộc unit suite này.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần so sánh ảnh hưởng của corruption và repair mà không để thay đổi câu hỏi hoặc ground-truth làm sai lệch metric.
- **Các phương án đã cân nhắc:** (1) sinh lại test set ở từng trạng thái; (2) đóng băng một test set từ cleaned baseline và tái sử dụng cho corrupted/repaired; (3) viết ID thủ công.
- **Phương án đã chọn:** đóng băng test set được sinh từ cleaned baseline, lưu SHA-256 và bắt buộc dùng lại cho cả ba trạng thái.
- **Lý do:** sinh lại test set có thể bỏ mất chính paper bị drop và tạo kết quả đẹp giả; ID thủ công dễ sai hoặc không tồn tại. Test set cố định bảo toàn biến kiểm soát và cho phép quy thay đổi metric về trạng thái dữ liệu/index trong phạm vi thí nghiệm.
- **Bằng chứng:** cả ba metrics JSON có cùng SHA-256; corrupted index thiếu hai ground-truth IDs và hit rate giảm từ `1.0` xuống `0.5`; repaired index có lại đủ 24 documents và hit rate trở về `1.0`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** phiên bản comparison report cũ có thể hiển thị quality signal corrupted `stale_rows=6` nhưng freshness table lại lấy giá trị `stale_rows=0` từ artifact/lần chạy khác.
- **Bước tái hiện:** so sánh `data/quality/corrupted.json`, `data/quality/freshness_report_corrupted.json` và bảng freshness trong report cũ.
- **Nguyên nhân gốc:** generator nhận nhiều dictionary rời mà không có contract xác nhận chúng thuộc cùng trạng thái/lần đo; report chỉ format đầu vào nên không phát hiện inconsistency.
- **Cách xử lý:** bổ sung `write_recovery_checkpoint` để kiểm tra lại metric từ answers, test SHA, sample IDs và equality của `row_count`, `stale_rows`, `max_age_days` giữa quality/freshness trước khi sinh report.
- **Cách xác minh sau khi sửa:** checkpoint hiện ghi corrupted `stale_rows=6`, `max_age_days=1161`, `is_fresh=false`; report hiển thị đúng các giá trị này và repaired lần lượt là `0`, `175`, `true`.
- **Điều học được:** report là sản phẩm dữ liệu và cũng cần validation contract; “đọc được JSON” chưa đủ để đảm bảo các artifact nhất quán.

## 7. Hiểu biết về luồng end-to-end

1. Crossref trả raw response; ingestion parse thành raw records. Cleaning chuẩn hóa DOI thành `paper_id`, xử lý title/summary/authors/categories/published, tính `age_days` và tạo `text_for_embedding`. Cleaned dataframe được embed bằng `sentence-transformers/all-MiniLM-L6-v2` và ghi vào các Chroma collection tách biệt.
2. Evaluation set được tạo từ cleaned baseline. Mỗi câu có `ground_truth` và `ground_truth_doc_ids`. Retrieval hit kiểm tra retrieved IDs có giao với ground-truth IDs; answer quality được đo thêm bằng token F1 và LLM judge.
3. Quality checks đo volume, completeness, uniqueness, validity và stale count trên dataframe. Freshness monitoring tập trung vào nguồn timestamp, biên ngày, tuổi dữ liệu, ngưỡng 180 ngày và trạng thái fresh/stale.
4. Dùng cùng test set giữ cố định câu hỏi và ground truth. Nếu sinh test set mới sau corruption, những paper bị drop có thể biến mất khỏi bài kiểm tra, làm metric tăng giả.
5. Repair được xem là thành công trong phạm vi đo khi repaired index đủ ID/count, quality và freshness PASS, metrics/answers trở về baseline và residual bằng 0. Kết luận phải dựa vào `recovery_checkpoint.json` cùng per-question answers, không chỉ một con số tổng hợp.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.5000 | 1.0000 | Hai ground-truth papers bị drop làm 8/16 câu miss; repair phục hồi đủ ID |
| `mean_token_f1` | 1.0000 | 0.6337 | 1.0000 | Answer lexical overlap giảm rõ khi retrieval miss và trở lại baseline sau repair |
| `judge_accuracy` | 1.0000 | 0.6875 | 1.0000 | Có phục hồi, nhưng judge có một false positive nên không thể dùng đơn độc |
| `mean_judge_score` | 5.0000 | 3.8750 | 5.0000 | Xu hướng phù hợp tổng thể nhưng che khuất case answer rỗng được chấm 5 |
| Quality checks | PASS 10/10 | FAIL 5/10 | PASS 10/10 | Corrupted fail uniqueness, summary completeness/length và freshness |
| Freshness status | PASS | FAIL | PASS | Stale rows `0 → 6 → 0`; max age `175 → 1161 → 175` ngày |

### Kết luận từ số liệu

1. `drop_latest` làm hai ground-truth IDs biến mất khỏi corrupted index → retrieval hit giảm `1.0 → 0.5` → token F1 giảm `1.0 → 0.6337`, judge accuracy giảm `1.0 → 0.6875`.
2. Repair xây lại cleaned data và `papers-repaired` từ raw source → null summary, duplicate và stale rows trở về 0; index trở lại 24 documents → bốn RAG metrics trở lại đúng baseline, residual bằng 0.

Corruption ảnh hưởng rõ nhất đến RAG metric là `drop_latest`, vì hai ID bị drop trùng chính xác hai ground-truth IDs bị thiếu và bao phủ cả 8 sample xấu đi. `blank_summary`, `add_duplicates` và `stale_date` có liên hệ trực tiếp với quality signals, nhưng thí nghiệm áp dụng nhiều corruption cùng lúc nên chưa đủ bằng chứng tách riêng tác động của từng loại lên answer metric.

Kết quả khác kỳ vọng là `q01-summary`: corrupted answer là chuỗi rỗng, retrieval miss và token F1 bằng 0, nhưng structured judge vẫn chấm đúng với score 5. Kiểm tra trực tiếp `corrupted_answers.json` xác nhận đây là false positive thật, không phải evaluator fallback. Vì vậy report trình bày đồng thời retrieval hit, token F1 và judge metric.

Case demo trung thực là `q01-authors`, document `10.1111/exsy.70341`: baseline và repaired trả lời đúng “Wei Tian, Yuhao Zhou”, hit=true, F1=1, judge=5; corrupted retrieval miss, trả lời sai nhóm tác giả, F1=0, judge=1. Không có repaired miss trong lần chạy này, nên report dùng corrupted miss và ghi rõ trạng thái thay vì dựng một repaired miss giả.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Identity ổn định và lineage quan trọng hơn số lượng câu hỏi: `paper_id` phải được clean trước khi test set/index dùng chung contract.
2. Observability phải kiểm tra cả tính nhất quán giữa artifact, không chỉ từng file riêng lẻ; report cần fail sớm khi sample IDs, SHA, metric hoặc freshness signal lệch nhau.
3. Dữ liệu xấu có thể làm retrieval và answer suy giảm rõ, nhưng LLM judge vẫn có thể chấm sai. Kết luận RAG cần nhiều tín hiệu độc lập và per-question evidence.

### Nếu có thêm thời gian

Tôi sẽ mở rộng test set sang nhiều paper và câu hỏi không chứa DOI/title chính xác, chạy lặp nhiều seed, bật Ragas và bổ sung deterministic checks cho answer rỗng. Cải thiện sẽ được đo bằng coverage số paper/type, confidence interval của metrics, tỷ lệ judge disagreement và số false positive/false negative khi đối chiếu thủ công một sample chuẩn.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phạm vi công việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Hoàng Anh Minh

**Ngày xác nhận:** 2026-08-06
