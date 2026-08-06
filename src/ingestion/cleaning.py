from __future__ import annotations

from datetime import datetime

import pandas as pd

from ingestion.crossref import PaperRecord


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang de embed."""
    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame([vars(r) for r in records])
    
    # 1. Normalize title, summary, authors, categories.
    df['title'] = df['title'].fillna("").str.strip()
    df['summary'] = df['summary'].fillna("").str.strip()
    
    # Drop rows without paper_id, title or summary
    initial_count = len(df)
    df = df[df['paper_id'].notna() & (df['paper_id'] != "")]
    df = df[(df['title'] != "") & (df['summary'] != "")]
    dropped_count = initial_count - len(df)
    if dropped_count > 0:
        print(f"Cleaning: Dropped {dropped_count} records due to missing paper_id, title, or summary.")
        
    if df.empty:
        return df

    # Replace empty authors/categories with empty list
    df['authors'] = df['authors'].apply(lambda x: x if isinstance(x, list) else [])
    df['categories'] = df['categories'].apply(lambda x: x if isinstance(x, list) else [])

    # 2. Parse published/updated date.
    df['published_dt'] = pd.to_datetime(df['published'], errors='coerce', utc=True).dt.tz_localize(None)
    df['published_dt'] = df['published_dt'].fillna(run_date)

    # 3. Tinh age_days.
    df['age_days'] = (run_date - df['published_dt']).dt.days
    df['age_days'] = df['age_days'].clip(lower=0)

    # 4. Tao cot helper:
    df['authors_joined'] = df['authors'].apply(lambda x: ", ".join(str(a) for a in x) if x else "Unknown")
    df['categories_joined'] = df['categories'].apply(lambda x: ", ".join(str(c) for c in x) if x else "Unknown")
    df['summary_chars'] = df['summary'].str.len()
    
    # text_for_embedding
    df['text_for_embedding'] = (
        "Title: " + df['title'] + "\n" +
        "Authors: " + df['authors_joined'] + "\n" +
        "Categories: " + df['categories_joined'] + "\n" +
        "Summary: " + df['summary']
    )

    # 5. Drop duplicates va filter row xau.
    df = df.drop_duplicates(subset=['paper_id'], keep='last')
    
    # Drop intermediate columns
    df = df.drop(columns=['published_dt'])
    
    # 6. Sort dataframe va return.
    df = df.sort_values('published', ascending=False).reset_index(drop=True)
    
    return df
