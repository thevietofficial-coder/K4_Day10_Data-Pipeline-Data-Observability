# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Nguyễn Thừa Tuân             |
| MSSV               | 2A202601330                     |
| Khóa/Lớp         | K4              |
| Tên nhóm         | Silver Flag     |
| Vai trò chính    | Vai trò 4 — RAG & Agent owner                 |
| Repository         | https://github.com/thevietofficial-coder/K4_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái                                 |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------------------------------------- |
| Xác nhận contract embedding/index | `src/retrieval/index.py` (`LocalEmbeddingIndex.build/load/search/lookup`), `src/retrieval/embeddings.py` | Clean dataframe (`papers_clean.json`), `Settings` | Xác nhận collection `papers-baseline/-corrupted/-repaired` build/load đúng, search/lookup trả kết quả đúng | Hoàn thành |
| Fix bug `persist_path` cross-machine | `src/retrieval/index.py::LocalEmbeddingIndex.load()` | Embedding manifest JSON build trên máy khác | `load()` chạy đúng trên mọi máy, không phụ thuộc đường dẫn tuyệt đối của máy build | Hoàn thành |
| Fix agent không fallback khi lookup thất bại | `src/retrieval/agent.py::build_agent()` | Câu hỏi factual của người dùng | Agent tự gọi `semantic_search_papers` khi `lookup_paper` không tìm thấy exact match, không còn báo sai "không tìm thấy" | Hoàn thành |
| Script smoke test dùng lại cho CP2/CP3/CP5/CP6 | `script/test_retrieval.py` | `Settings`, 3 collection đã build | `test_retrieval()`, `test_corruption_impact()`, `test_repair_impact()`, `explain_hit_rate()` | Hoàn thành |

Toàn bộ code trong `src/retrieval/` được cấp sẵn (không có `NotImplementedError`); phần việc thật của vai trò này là đọc hiểu contract, build/verify bằng data thật, phát hiện và sửa bug khi test, không phải viết hàm mới từ đầu.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Gửi trước schema 9 cột clean dataframe bắt buộc (`paper_id, title, text_for_embedding, published, authors_joined, categories_joined, summary, abs_url, pdf_url`) | Role 3 — `src/ingestion/cleaning.py` | Tránh `KeyError` khi build index; xác nhận đúng khớp sau khi Duy code xong |
| Cảnh báo rủi ro `delete_collection` ghi đè `papers-baseline` nếu build corrupted/repaired quên truyền `embeddings_output_path` | Role 1 — `src/pipelines/phase1.py`, `corruption_flow.py` | Verify thực tế: cả 3 collection tồn tại đúng, baseline không bị ghi đè |
| Đối chiếu `ground_truth_doc_ids` phải dùng `paper_id` (không phải `record_id`) khớp với `SearchResult.paper_id` | Role 5 — `src/evaluation/testset.py` | `retrieval_hit_rate` tính đúng ngay từ đầu |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Verify `papers-baseline` build đúng, search/lookup hoạt động | `data/embeddings/papers_embeddings.json`, Chroma collection `papers-baseline` | 24/24 docs khớp clean dataset, semantic search top-1 đúng chủ đề | `script/test_retrieval.py::test_retrieval()` |
| Fix + verify bug `persist_path` | `src/retrieval/index.py` | `LocalEmbeddingIndex.load()` chạy được trên máy khác máy build | `Loaded OK, collection: papers-baseline \| docs: 24` sau fix, trước đó `chromadb.errors.NotFoundError` |
| Fix + verify agent fallback | `src/retrieval/agent.py` | Agent trả lời đúng câu hỏi "Hi-RAG paper" sau khi `lookup_paper` fail, không còn báo sai | Trace tool call: `lookup_paper` (fail) → `semantic_search_papers` → trả lời đúng nội dung |
| So sánh retrieval baseline vs corrupted | `script/test_retrieval.py::test_corruption_impact()` | Cùng 1 query, top-1 đổi hẳn khi data bị corrupt; xác nhận baseline không bị mutate (vẫn 24 docs) | Chạy script, đối chiếu `data/results/corrupted_metrics.json` |
| Verify repair phục hồi thật (không chỉ tin metric) | `script/test_retrieval.py::test_repair_impact()` | 2 paper bị `drop_latest` xóa (Hi-RAG, SafeRAG) xác nhận quay lại đúng nội dung trong `papers-repaired`; agent trả lời đúng về SafeRAG sau repair | `10.1111/exsy.70341 -> in repaired: True`, `10.2118/234689-pa -> in repaired: True` |

Output cụ thể: `script/test_retrieval.py::explain_hit_rate()` chứng minh bằng code (không chỉ suy đoán) rằng toàn bộ 8/16 miss ở trạng thái corrupted đến từ việc `drop_latest` xóa hẳn 2 paper ground-truth khỏi index — không phải từ `truncate_title`/`blank_summary`/`inject_noise`/`stale_date` như giả thuyết ban đầu (giả thuyết này đã bị bác bỏ sau khi kiểm chứng từng câu hỏi thực tế, xem mục 6).

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Phần RAG/agent là lớp cuối cùng của pipeline (raw → clean → **embedding + Chroma → agent trả lời**). Vấn đề cần đảm bảo: (1) embedding/index build đúng và tái lập được trên máy bất kỳ trong nhóm, không chỉ máy build ra nó; (2) agent trả lời factual phải dựa trên tool result thật, không bịa; (3) khi data bị corrupt, sự suy giảm chất lượng phải đo được và giải thích được bằng nguyên nhân cụ thể, không chỉ nhìn con số tổng.

### Cách triển khai

`LocalEmbeddingIndex` dùng `MiniLMEmbeddings` (sentence-transformers `all-MiniLM-L6-v2`) để encode `text_for_embedding`, lưu vào ChromaDB (`hnsw` cosine space) với 3 collection tên riêng biệt (`papers-baseline`, `papers-corrupted`, `papers-repaired`) được chọn tự động theo `embeddings_output_path` truyền vào `build()`. `build_agent()` tạo agent LangChain với 2 tool (`semantic_search_papers`, `lookup_paper`); sau khi phát hiện agent không fallback khi lookup thất bại, đã sửa system prompt + return message của tool để buộc agent thử `semantic_search_papers` trước khi kết luận "không có trong corpus".

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | Clean dataframe 9 cột bắt buộc từ `cleaning.py`/`corruption.py`; `Settings` (embedding model, collection names, paths) |
| Output                         | Chroma collection + manifest JSON (`data/embeddings/*.json`); `AnswerResult`/agent message trace có nguồn (`paper_id`, `retrieved_contexts`) |
| Module phụ thuộc             | `src/core/config.py` (paths, settings), `src/ingestion/cleaning.py` + `corruption.py` (clean dataframe đầu vào) |
| Module sử dụng output        | `src/pipelines/phase1.py`, `corruption_flow.py` (orchestration), `src/evaluation/metrics.py` (evaluate qua `qa.answer_question`) |
| Điều kiện lỗi cần xử lý | Manifest build trên máy khác (persist_path sai); lookup thất bại vì câu hỏi không quote chính xác; build corrupted/repaired quên truyền path riêng có thể xóa nhầm baseline |

### Cách xác minh

```bash
python script/test_retrieval.py
```

- **Kết quả mong đợi:** load được cả 3 collection, semantic search/lookup trả đúng tài liệu, agent dùng tool trước khi trả lời, baseline không đổi số lượng document sau khi build corrupted/repaired.
- **Kết quả thực tế:** đúng như mong đợi — `papers-baseline: 24 docs` không đổi xuyên suốt CP2/CP5/CP6; agent fallback đúng sang semantic search khi cần; 2 paper bị corruption xóa quay lại đúng nội dung sau repair.
- **Artifact/log:** `data/embeddings/papers_embeddings*.json`, `data/chroma/`, output của `script/test_retrieval.py` (không chứa secret).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `LocalEmbeddingIndex.load()` (code gốc) đọc `persist_path` tuyệt đối lưu cứng trong manifest JSON, nên chỉ chạy đúng trên máy đã build ra nó. Phát hiện khi teammate khác (Việt) build baseline trên máy của họ, mình load lại thì lỗi `chromadb.errors.NotFoundError`.
- **Các phương án đã cân nhắc:**
  1. Mỗi máy tự build lại toàn bộ collection từ đầu khi cần dùng, bỏ qua artifact người khác đã build.
  2. Sửa `load()` để luôn tính `persist_path` từ `settings.paths.chroma_dir` của máy hiện tại, bỏ qua giá trị lưu trong manifest.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:** Phương án 1 tốn thời gian, không tận dụng được artifact nhóm đã commit, và không nhất quán vì mỗi máy build lại có thể cho HNSW graph khác nhau. Phương án 2 nhất quán với cách `build()` đã tính `persist_path` (luôn từ `settings.paths.chroma_dir`, không phải tham số cố định), sửa đúng 1 dòng, không đổi contract của hàm.
- **Bằng chứng quyết định phù hợp:** Sau fix, `load()` chạy đúng trên máy mình (khác máy build) và trả về đúng 24 documents, verify lại bằng `search()`/`lookup()` cho kết quả đúng.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**
  ```
  chromadb.errors.NotFoundError: Collection [papers-baseline] does not exist
  ```
- **Lệnh hoặc bước tái hiện:** `LocalEmbeddingIndex.load(settings)` ngay sau khi pull artifact do teammate khác build và push lên git.
- **Nguyên nhân gốc:** `persist_path` trong manifest là đường dẫn tuyệt đối của máy build (`C:\CODE\AITHUCCHIEN\...`), không khớp đường dẫn máy hiện tại (`D:\Workspace\VinAI_LAB\...`).
- **Cách xử lý:** Sửa `LocalEmbeddingIndex.load()` dùng `settings.paths.chroma_dir` thay vì `Path(payload["persist_path"])`.
- **Cách xác minh sau khi sửa:** Chạy lại, in ra `Loaded OK, collection: papers-baseline | docs: 24`; `search()`/`lookup()` chạy đúng ngay sau đó.
- **Điều học được:** Artifact chia sẻ qua git giữa nhiều máy không nên chứa đường dẫn tuyệt đối của máy tạo ra nó — phải luôn derive lại từ config cục bộ của máy đang chạy.

Một phát hiện thứ hai đáng ghi lại vì suýt dẫn tới kết luận sai: ban đầu tôi giả định `truncate_title` (1 trong 6 loại corruption) là nguyên nhân làm giảm `retrieval_hit_rate` ở trạng thái corrupted, vì nghĩ cơ chế "exact match" trong `qa.answer_question` dựa vào title. Sau khi verify từng câu hỏi thực tế (không chỉ tin số liệu tổng), phát hiện cơ chế đó thực ra dựa vào `paper_id` (không đổi khi corrupt nội dung) — toàn bộ 8/16 miss chỉ đến từ `drop_latest` xóa hẳn 2 paper khỏi index, 4 loại corruption còn lại không hề chạm `retrieval_hit_rate` trong lần chạy này. Đã sửa lại code + comment giải thích cho đúng trước khi commit.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Crossref → vector index:** `crossref.py` gọi Crossref REST API, lưu raw response + parse thành `PaperRecord`, lưu vào `data/raw/`. `cleaning.py` chuẩn hóa thành dataframe có `text_for_embedding` (title + authors + categories + summary ghép lại) và các field freshness (`age_days`). `index.py` dùng `MiniLMEmbeddings` encode `text_for_embedding` thành vector, lưu vào ChromaDB cùng metadata (`paper_id`, `title`, `published`...), đồng thời ghi manifest JSON mô tả collection.
2. **Evaluation set & ground-truth doc IDs:** `testset.py` chọn một số paper đại diện từ clean dataframe, sinh câu hỏi (summary/authors/date/categories) kèm `ground_truth_doc_ids` chính là `paper_id` của paper đó. Khi evaluate, `metrics.py` so `retrieved_doc_ids` (từ `SearchResult.paper_id`) với `ground_truth_doc_ids` để tính `retrieval_hit_rate`, và so nội dung câu trả lời với `ground_truth` để tính `token_f1`/`judge` score.
3. **Quality checks vs freshness monitoring:** Quality checks (`run_data_quality_checks`) đo tính toàn vẹn cấu trúc dữ liệu tại một thời điểm (row count, `paper_id` unique/not-null, độ dài `summary`...). Freshness monitoring (`build_freshness_report`) đo riêng khía cạnh thời gian — dữ liệu có "cũ" so với ngưỡng (`freshness_threshold_days`) hay không, dựa trên `age_days`/`published`. Một dataset có thể PASS quality nhưng vẫn stale (không fresh), hoặc ngược lại.
4. **Vì sao dùng chung 1 test set cho cả 3 trạng thái:** Để mọi thay đổi về metric (baseline → corrupted → repaired) chỉ có thể do trạng thái dữ liệu gây ra, không do câu hỏi/ground-truth khác nhau giữa các lần đánh giá — nếu đổi test set, không thể quy kết chính xác nguyên nhân của sự thay đổi metric.
5. **Repair thành công dựa trên gì:** Không chỉ dựa vào `retrieval_hit_rate`/`token_f1`/`judge_accuracy` quay về bằng baseline (1.0 ở cả 2 phía trong lần chạy này), mà còn phải verify bằng artifact cụ thể — ở đây tôi đã kiểm tra trực tiếp 2 paper từng bị `drop_latest` xóa có thực sự tồn tại lại trong `papers-repaired` với đúng nội dung (title/summary khớp bản gốc), không chỉ tin số liệu tổng hợp.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |      1.0 |       0.5 |      1.0 | Giảm đúng 1/2 vì 2/4 paper trong ground-truth bị `drop_latest` xóa hẳn; phục hồi hoàn toàn sau repair. |
| `mean_token_f1`      |    1.0 |     0.634 |      1.0 | Giảm tương ứng với các câu hỏi miss (trả lời "không biết"); phục hồi 100% sau repair. |
| `judge_accuracy`     |    1.0 |    0.6875 |      1.0 | Giảm nhẹ ít hơn token_f1 vì judge (LLM) đôi khi vẫn chấm đúng một phần dù retrieval miss. |
| `mean_judge_score`   |      5 |     3.875 |        5 | Cùng xu hướng với judge_accuracy. |
| Quality checks         |     PASS |      FAIL |     PASS | Corrupted FAIL do trực tiếp mất bản ghi hợp lệ và `age_days` bất thường sau `stale_date`. |
| Freshness status       |    Fresh (0 stale) |  Not fresh (6 stale) |    Fresh (0 stale) | Đúng như log corruption: 6 dòng bị `stale_date` (+1000 ngày), phục hồi về 0 sau repair. |

### Kết luận từ số liệu

1. `drop_latest` (xóa 2 paper mới nhất) → row count giảm, 2 `paper_id` ground-truth biến mất khỏi index (quality signal) → `retrieval_hit_rate` giảm còn 0.5, kéo theo `token_f1`/`judge_accuracy` giảm.
2. Repair (re-clean lại từ `data/raw/`) → cả 2 paper quay lại đúng nội dung trong index (đã verify trực tiếp, không chỉ tin metric) → `retrieval_hit_rate`/`token_f1`/`judge_accuracy` phục hồi hoàn toàn về bằng baseline.

**Corruption nào ảnh hưởng rõ nhất và vì sao:** `drop_latest` ảnh hưởng rõ nhất đến `retrieval_hit_rate` trong lần chạy này, vì đây là loại corruption duy nhất làm ground-truth document biến mất hoàn toàn khỏi index. 4 loại corruption còn lại (`blank_summary`, `inject_noise`, `truncate_title`, `stale_date`) không đổi `paper_id`, nên cơ chế exact-id lookup trong `qa.answer_question` vẫn tìm đúng tài liệu — chúng chỉ ảnh hưởng tới Quality/Freshness report (và tiềm năng ảnh hưởng `token_f1`/`judge` nếu trúng đúng paper trong test set), không ảnh hưởng `retrieval_hit_rate` trong lần chạy cụ thể này vì không loại nào trong 4 loại đó trúng vào 4 paper thuộc ground-truth của test set.

**Kết quả khác kỳ vọng ban đầu:** Ban đầu tôi giả thuyết `truncate_title` sẽ làm hỏng cơ chế exact-match và gây miss (vì nhầm biến `title_match` trong code là dựa vào title). Sau khi verify từng câu hỏi bằng cách kiểm tra `index.lookup()` và tình trạng tồn tại của từng `ground_truth_doc_id` trong corrupted collection, phát hiện toàn bộ 8 miss đều do `drop_latest`, 0 miss nào do các loại corruption nội dung khác — đã sửa lại kết luận và code giải thích trước khi báo cáo, thay vì giữ nguyên giả thuyết ban đầu chưa kiểm chứng.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Artifact chia sẻ qua git giữa nhiều máy (như manifest embedding chứa `persist_path`) không nên lưu đường dẫn tuyệt đối — phải luôn derive lại từ config cục bộ, nếu không sẽ chỉ chạy đúng trên đúng một máy.
2. **Về data quality/observability:** Một metric "hoàn hảo" (`retrieval_hit_rate = 1.0`) không tự động chứng minh hệ thống tốt — cần đào sâu cơ chế sinh ra con số đó (ở đây là exact-id shortcut) trước khi kết luận, nếu không sẽ báo cáo sai nguyên nhân dù số liệu đúng.
3. **Về ảnh hưởng của data đến RAG agent:** Chất lượng agent phụ thuộc cả vào chiến lược dùng tool, không chỉ chất lượng retrieval — agent không có cơ chế fallback sẽ bỏ cuộc oan ngay cả khi dữ liệu đúng vẫn còn trong corpus.

### Nếu có thêm thời gian

Sẽ mở rộng test set (hoặc thiết kế lại corruption sampling) để đảm bảo ít nhất 1 paper bị mỗi loại corruption nội dung (`blank_summary`/`inject_noise`/`truncate_title`/`stale_date`) rơi đúng vào tập ground-truth của test set — hiện tại `retrieval_hit_rate` chỉ phản ánh được tác động của `drop_latest`, che khuất tác động thật của 4 loại corruption còn lại lên khả năng retrieval (dù chúng vẫn được đo gián tiếp qua Quality/Freshness report). Đo cải thiện bằng cách so sánh `retrieval_hit_rate`/`token_f1` trước và sau khi mở rộng test set, với cùng bộ corruption log để đối chiếu.

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Thừa Tuân
**Ngày xác nhận:** 2026-08-06
