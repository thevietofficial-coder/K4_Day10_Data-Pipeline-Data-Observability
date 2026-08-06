from __future__ import annotations

import pandas as pd


import json
import numpy as np

def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Simulate nhieu dang data corruption."""
    if df.empty:
        return df
        
    corrupted_df = df.copy()
    corruption_log = []
    
    # 1. Drop mot so latest records (e.g. 10%)
    drop_count = max(1, int(len(corrupted_df) * 0.1))
    if len(corrupted_df) > drop_count:
        dropped_indices = corrupted_df.index[:drop_count]
        dropped_ids = corrupted_df.loc[dropped_indices, 'paper_id'].tolist()
        corrupted_df = corrupted_df.drop(dropped_indices).reset_index(drop=True)
        corruption_log.append({
            "type": "drop_latest",
            "params": {"count": drop_count},
            "affected_ids": dropped_ids
        })
        
    n = len(corrupted_df)
    
    if n > 0:
        # 2. Blank summary o mot so dong (30%)
        num_blank = max(1, int(n * 0.3))
        blank_idx = np.random.choice(corrupted_df.index, size=num_blank, replace=False)
        for idx in blank_idx:
            paper_id = corrupted_df.loc[idx, 'paper_id']
            before_val = corrupted_df.loc[idx, 'summary']
            corrupted_df.loc[idx, 'summary'] = ""
            corruption_log.append({"type": "blank_summary", "record_id": paper_id, "before": before_val, "after": ""})
        
        # 3. Inject noise vao text (30%)
        num_noise = max(1, int(n * 0.3))
        noise_idx = np.random.choice(corrupted_df.index, size=num_noise, replace=False)
        for idx in noise_idx:
            paper_id = corrupted_df.loc[idx, 'paper_id']
            before_val = corrupted_df.loc[idx, 'summary']
            after_val = str(before_val) + "\n\n[NOISE] Lorem ipsum dolor sit amet, " * 3
            corrupted_df.loc[idx, 'summary'] = after_val
            corruption_log.append({"type": "inject_noise", "record_id": paper_id, "before_length": len(str(before_val)), "after_length": len(after_val)})
        
        # 4. Lam title bi truncate (30%)
        num_trunc = max(1, int(n * 0.3))
        trunc_idx = np.random.choice(corrupted_df.index, size=num_trunc, replace=False)
        for idx in trunc_idx:
            paper_id = corrupted_df.loc[idx, 'paper_id']
            before_val = corrupted_df.loc[idx, 'title']
            after_val = before_val[:10] + "..." if isinstance(before_val, str) and len(before_val) > 10 else before_val
            corrupted_df.loc[idx, 'title'] = after_val
            corruption_log.append({"type": "truncate_title", "record_id": paper_id, "before": before_val, "after": after_val})
        
        # 5. Lam published date cu di (30%) -> tang age_days len 1000 ngay
        num_stale = max(1, int(n * 0.3))
        stale_idx = np.random.choice(corrupted_df.index, size=num_stale, replace=False)
        for idx in stale_idx:
            paper_id = corrupted_df.loc[idx, 'paper_id']
            before_val = int(corrupted_df.loc[idx, 'age_days'])
            after_val = before_val + 1000
            corrupted_df.loc[idx, 'age_days'] = after_val
            corruption_log.append({"type": "stale_date", "record_id": paper_id, "before": before_val, "after": after_val})

        # 6. Add duplicate rows (duplicate top 2 rows)
        if len(corrupted_df) >= 2:
            dup_rows = corrupted_df.head(2).copy()
            dup_ids = dup_rows['paper_id'].tolist()
            corrupted_df = pd.concat([corrupted_df, dup_rows], ignore_index=True)
            corruption_log.append({"type": "add_duplicates", "params": {"count": 2}, "affected_ids": dup_ids})
            
    # 7. Rebuild text_for_embedding
    corrupted_df['text_for_embedding'] = (
        "Title: " + corrupted_df['title'].astype(str) + "\n" +
        "Authors: " + corrupted_df['authors_joined'].astype(str) + "\n" +
        "Categories: " + corrupted_df['categories_joined'].astype(str) + "\n" +
        "Summary: " + corrupted_df['summary'].astype(str)
    )
    
    # 8. Ghi corruption log
    import os
    os.makedirs(os.path.dirname(output_log_path), exist_ok=True)
    with open(output_log_path, 'w', encoding='utf-8') as f:
        json.dump(corruption_log, f, indent=2, ensure_ascii=False)
        
    return corrupted_df
