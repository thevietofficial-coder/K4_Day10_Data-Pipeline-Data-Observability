import json
import pandas as pd
from datetime import datetime

from ingestion.crossref import PaperRecord
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe

def test_cleaning():
    # 1. Prepare raw sample data
    raw_samples = [
        PaperRecord(
            paper_id="10.1234/sample1",
            title="A great paper on Data Pipeline",
            summary="This is a summary about data observability.",
            authors=["Alice", "Bob"],
            categories=["Computer Science", "Data"],
            primary_category="Computer Science",
            published="2023-10-01",
            updated="2023-10-05",
            abs_url="http://example.com/1",
            pdf_url="http://example.com/1.pdf",
            comment=""
        ),
        PaperRecord(
            paper_id="10.1234/sample2",
            title="   Another Paper with bad formatting   ",
            summary="  ", # Empty summary -> Should be dropped
            authors=[],
            categories=[],
            primary_category="",
            published="2024-01-15",
            updated="2024-01-20",
            abs_url="http://example.com/2",
            pdf_url="http://example.com/2.pdf",
            comment=""
        ),
        PaperRecord(
            paper_id="10.1234/sample3",
            title="Duplicate Paper",
            summary="This is a valid summary.",
            authors=["Charlie"],
            categories=["AI"],
            primary_category="AI",
            published="2024-02-01",
            updated="2024-02-01",
            abs_url="http://example.com/3",
            pdf_url="",
            comment=""
        ),
        PaperRecord(
            paper_id="10.1234/sample3", # Duplicate ID
            title="Duplicate Paper (Updated)",
            summary="This is a valid summary. With more text.",
            authors=["Charlie"],
            categories=["AI"],
            primary_category="AI",
            published="2024-02-01",
            updated="2024-02-15",
            abs_url="http://example.com/3",
            pdf_url="",
            comment=""
        )
    ]
    
    run_date = datetime.now()
    print("--- RAW RECORDS ---")
    for r in raw_samples:
        print(f"ID: {r.paper_id} | Title: '{r.title}' | Summary len: {len(r.summary)}")
        
    print("\n--- RUNNING CLEANING ---")
    clean_df = build_clean_dataframe(raw_samples, run_date)
    
    print("\n--- CLEANED DATAFRAME ---")
    print(clean_df[['paper_id', 'title', 'authors_joined', 'age_days', 'summary_chars']])
    print("\nSample text_for_embedding:\n", clean_df['text_for_embedding'].iloc[0])

    print("\n--- RUNNING CORRUPTION ---")
    corrupted_df = corrupt_clean_dataframe(clean_df, "data/results/test_corruption_log.json")
    print(corrupted_df[['paper_id', 'title', 'summary']])
    print("\nCheck data/results/test_corruption_log.json for corruption details.")

if __name__ == "__main__":
    test_cleaning()
