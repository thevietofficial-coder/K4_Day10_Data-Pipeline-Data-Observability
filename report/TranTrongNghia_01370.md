# Member Role Report — Day 10: Data Pipeline & Data Observability

> Mỗi thành viên trong nhóm tự hoàn thành mẫu này để báo cáo đúng vai trò, phần việc và mức hiểu của mình. Không sao chép nguyên báo cáo chung hoặc báo cáo của thành viên khác. Thay nội dung trong dấu `[ ]` và xóa các dòng hướng dẫn không cần thiết trước khi nộp.

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Trần Trọng Nghĩa             |
| MSSV               | 2A202601370                     |
| Khóa/Lớp         | K4              |
| Tên nhóm         | SilverFlag     |
| Vai trò chính    | Role 2 (Ingestion Owner)                 |
| Repository         | https://github.com/thevietofficial-coder/K4_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 06/08/2026               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái                                 |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Parse Crossref Payload | `src/ingestion/crossref.py` (hàm `parse_crossref_payload`) | Raw JSON dictionary từ Crossref API | `list[PaperRecord]` đã chuẩn hoá (có paper_id thống nhất, abstract sạch JATS tag) | Hoàn thành |
| Fetch Source Records | `src/ingestion/crossref.py` (hàm `fetch_source_records`) | Tham số cấu hình `Settings` | 2 file log thô (`data/raw/crossref_response.json` và `data/raw/crossref_records.json`) + List `PaperRecord` trả về | Hoàn thành |
| Đảm bảo Freeze Snapshot Pipeline | `src/ingestion/crossref.py` | Cờ `refresh_source` trong Settings | Hard Error `RuntimeError` khi thiếu file cache mà không tự động fetch lại API làm hỏng baseline | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Đảm bảo tính nhất quán (Consistency) của `paper_id` | Role 3 (Cleaning), QA Agent (`retrieval/qa.py`) | Viết test `test_consistency.py` và `test_qa_evidence.py` để chứng minh `paper_id` không bị đột biến, đồng thời QA tự động attach evidence/source vào `AnswerResult`. |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Lấy dữ liệu Crossref | `data/raw/crossref_response.json` | File JSON nguyên gốc Bytes từ API | Mở file kiểm tra schema trả về của Crossref |
| Parse và chuẩn hoá dữ liệu | `data/raw/crossref_records.json` | Danh sách schema dạng JSON chứa metadata paper đã trích xuất | Mở file kiểm tra `paper_id` (đã lowercase, mất prefix url), abstract mất tag JATS |
| Kiểm chứng snapshot guarantee | `tests/test_snapshot_guarantee.py` | 1 file Unit test đảm bảo code văng lỗi chứ không fall-back khi tắt cờ refresh_source | Lệnh: `uv run pytest tests/test_snapshot_guarantee.py` (Trả về PASSED) |

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Role 2 giải quyết vấn đề nhập liệu (Ingestion) từ nguồn ngoài. Dữ liệu từ Crossref trả về là một cục JSON khổng lồ, các DOIs (ID) có lúc viết hoa, viết thường, có chứa HTTPS org hoặc không. Abstract thì lại dính thẻ HTML/XML (`<jats:p>`). Nếu không xử lý và đưa về một chuẩn `PaperRecord` chặt chẽ, các bước Embedding (Role 4) và Agent (Role 5) phía sau sẽ fail do mismatch ID, hoặc sinh ra vector rác (do lẫn thẻ JATS).

### Cách triển khai

1. **Chuẩn hoá ID:** Viết hàm `normalize_doi` dùng regex để lấy chuẩn DOI, strip tiền tố `https://doi.org/` và đưa hết về chuỗi chữ thường `lower()`.
2. **Làm sạch Abstract (ngay tại Ingestion):** Dùng regex `<[^>]+>` để quét và xóa sạch các thẻ XML/HTML trả về từ API Crossref, giữ lại Text thuần cho Role 3 (Cleaning).
3. **Cơ chế Retry / 429:** Thay vì code chay hàm sleep, mình áp dụng thư viện `tenacity` (`@retry`) kết hợp với hàm `_build_retry` để đọc giá trị `Retry-After` header trong HTTP Response. Khi Crossref chặn rate-limit, pipeline tự lùi lại chờ đúng thời gian hệ thống báo thay vì request điên cuồng gây bị ban IP.

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | Endpoint `https://api.crossref.org/works`, filter `has-abstract:true` |
| Output                         | Danh sách `list[PaperRecord]` và 2 file artifact trong `data/raw/` |
| Module phụ thuộc             | `core/config.py` (chứa URL và cấu hình max retries) |
| Module sử dụng output        | `phase1.py` (truyền kết quả cho `cleaning.py` làm bước tiếp) |
| Điều kiện lỗi cần xử lý | Xử lý Rate Limit 429/503 (bằng Tenacity), Lỗi thiếu tác giả (cảnh báo nhưng vẫn parse), Lỗi thiếu file cache khi bắt buộc phải Freeze snapshot (Ném RuntimeError). |

### Cách xác minh

```bash
uv run pytest tests/test_consistency.py
```

- **Kết quả mong đợi:** Hàm `normalize_doi` hoạt động chuẩn. Đầu vào `HTTPS://DOI.ORG/10.1234/aBcD` hay `10.1234/aBcD` đều ra kết quả `10.1234/abcd`. `paper_id` được bảo toàn xuyên suốt từ JSON gốc -> DataFrame -> ChromaDB.
- **Kết quả thực tế:** Test `PASSED` 100%.
- **Artifact/log:** `data/raw/crossref_records.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn phương án xử lý Fallback khi Cache (`crossref_response.json`) vô tình bị xóa và cờ `refresh_source=False` (chạy Baseline/Corruption Flow).
- **Các phương án đã cân nhắc:** 
  1. Im lặng gọi lại API Live để lấy data.
  2. Bắn Exception văng lỗi hệ thống ngay lập tức.
- **Phương án đã chọn:** 2. Ném Exception (`RuntimeError`).
- **Lý do:** Trade-off về Data Correctness và Reproducibility. Khi chạy quá trình Corruption/Repair Flow, tính nhất quán của Baseline (cột mốc so sánh) là tuyệt đối. Nếu gọi API Live ngầm (Silent Fallback), số liệu trả về có thể khác ngày hôm qua, dẫn đến việc so sánh hiệu suất AI ở Baseline vs Repaired bị méo mó.
- **Bằng chứng quyết định phù hợp:** Bài test `test_snapshot_guarantee.py` được viết ra để khóa chặt hành vi này, đảm bảo `RuntimeError` bay ra khi cố tình kích hoạt ngữ cảnh trên.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Lúc đầu code test `test_paper_id_consistency` bị báo lỗi `AttributeError: Mock object has no attribute 'paths'`.
- **Lệnh hoặc bước tái hiện:** `uv run pytest tests/test_consistency.py`
- **Nguyên nhân gốc:** Quá trình khởi tạo giả (mocking) đói tượng `Settings` không tự động giả định (mock) được thuộc tính con `paths`. Ta phải khởi tạo trực tiếp biến `paths = MagicMock()` trước khi gán các thuộc tính `.chroma_dir` hoặc `.embeddings_json`.
- **Cách xử lý:** Bổ sung `settings.paths = MagicMock()` và import `patch` từ `unittest.mock`.
- **Cách xác minh sau khi sửa:** Chạy lại `uv run pytest tests/test_consistency.py` và nhận kết quả PASSED.
- **Điều học được:** Việc Mock các Dataclass/Object lồng nhau (nested attributes) trong unit test cần khai báo tầng tầng lớp lớp tường minh, không thể trông cậy vào autospec hoàn toàn nếu class quá tĩnh.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**
   - Lấy JSON từ HTTP -> Tách xuất vào struct `PaperRecord` -> Chuyển thành `pd.DataFrame` (cleaning.py để ghép chuỗi text embedding, age_days) -> Gọi Model `MiniLM` để tạo ra list các vector -> Lưu Vector + Metadata (trong đó có `paper_id` và `title`) xuống ChromaDB disk.
2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**
   - Ground-truth document ID được dùng làm đáp án cho hệ thống Retrieval: Khi Agent truy xuất vector, tập `retrieved_doc_ids` trả về sẽ được tính độ trùng khớp với `ground_truth_doc_ids` (tính ra Retrieval Hit Rate).
3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**
   - Quality checks là xem xét "tính đúng đắn" của cấu trúc data (có null, có trùng lặp ID, summary có quá ngắn không). Freshness là độ "tươi" (Age days): tính thời điểm, stale (cũ quá ngưỡng) sẽ rớt Freshness nhưng vẫn Pass Quality nếu đầy đủ struct.
4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**
   - Để đảm bảo tính A/B Testing công bằng. Nếu dùng tập câu hỏi khác, sẽ không thể chứng minh sự suy giảm hiệu suất của Agent (giảm Hit rate, giảm F1) là do "data bị Corrupt", mà có thể là do câu hỏi mới quá khó.
5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   - Khi artifact `freshness_report_repaired.json` và `quality_report_repaired.json` 100% Passed trở lại, và file `repaired_metrics.json` có điểm số khôi phục chính xác bằng với điểm của `baseline_metrics.json` lúc đầu.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |      1.0 |       0.5 |      1.0 | Rớt 50% do mất Context (Summary bị làm rỗng hoặc rác)              |
| `mean_token_f1`      |      1.0 |    0.6337 |      1.0 | Giảm mạnh do không còn thông tin để lấy câu trả lời chính xác              |
| `judge_accuracy`     |      1.0 |    0.6875 |      1.0 | Giảm ~31% cho thấy LLM Judge nhận diện câu trả lời bịa đặt              |
| `mean_judge_score`   |        5 |     3.875 |        5 | Điểm tuyệt đối giảm thê thảm do dữ liệu nhiễu              |
| Quality checks         |     Pass |      Fail |     Pass | Corrupted báo lỗi do xuất hiện Summary null, Duplicate ID              |
| Freshness status       |     Pass |      Fail |     Pass | Phát hiện 6 rows bị stale (cũ quá 180 ngày) trong Corrupted set              |

### Kết luận từ số liệu

Hoàn thành hai chuỗi nguyên nhân–bằng chứng sau:

1. Dữ liệu bị làm nhiễu (Summary null/rác, Stale date, ID trùng) → Cảnh báo Quality Status chuyển thành **FAIL**, `stale_rows` tăng đột biến (6) → Điểm Agent tụt hạng không phanh: `retrieval_hit_rate` (-0.5), `mean_token_f1` (-0.3663), `judge_accuracy` (-0.3125).
2. Load lại từ Snapshot gốc (`crossref_records.json`) → Các cột báo lỗi được dọn sạch, Quality phục hồi **PASS** → Mọi Agent metric đều lấy lại điểm tuyệt đối ban đầu (+0.5 hit rate, +0.3663 F1).

Corruption nào ảnh hưởng rõ nhất và vì sao?

Lỗi xóa trống (blank summary) và thay bằng rác (noise) tác động rõ rệt nhất. Lý do là Embedding Model (MiniLM) phụ thuộc vào ngữ nghĩa của Text. Khi Summary mất, Text for Embedding vô dụng dẫn đến ChromaDB không thể tìm được `paper_id` đúng (Hit Rate rớt thẳng 50%). Hit Rate rớt kéo theo F1 rớt.

Kết quả nào khác với kỳ vọng ban đầu?

Bất ngờ nhất là hệ thống LLM Judge (`mean_judge_score`) chưa giảm bằng 0 mà vẫn giữ mức trung bình 3.875 điểm. Giả thuyết là Agent (GPT-4o-mini) vẫn cố gắng bịa ra câu trả lời hợp lý dù context bị nhiễu (Hallucination), hoặc nó lấy câu trả lời từ tàn dư của Title, Author thay vì Summary. Điều này chứng tỏ Observability không chỉ cần chấm kết quả cuối cùng mà phải bắt lỗi ngay từ Data (Quality Check Fail) trước khi feed vào RAG.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Sự mong manh của Data Pipeline: Một hàm API silent fallback có thể phá hủy hoàn toàn quá trình RAG Evaluation phía sau. Observability không chỉ là báo lỗi mà còn là chặn các hành vi im lặng sai trái.
2. Sức mạnh của Exponential Backoff và `tenacity` trong việc giữ pipeline chạy ổn định và tuân thủ nguyên tắc tôn trọng hệ thống của Third-party API (Crossref).
3. Data Consistency (như `paper_id`) là chìa khóa vàng nối toàn bộ Ingestion - Vector Index - Evaluation Test Set. 

### Nếu có thêm thời gian

Mình sẽ cải tiến `fetch_source_records` để không chỉ lưu 1 file cache duy nhất, mà sẽ append thêm timestamp vào file thô, tạo thành một Data Lake mini (vd: `data/raw/crossref_2024-05-01.json`). Lúc này có thể Time-Travel về bất cứ snapshot lịch sử nào mà không sợ bị ghi đè (Overwrite).

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Trọng Nghĩa
**Ngày xác nhận:** 06/08/2026
