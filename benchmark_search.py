#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
benchmark_search.py - Independent Search & Lookup Benchmark Tool.
Benchmarks lookup latency, field cascading, multi-language filtering,
and match accuracy without downloading payloads.
"""

import os
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import LibgenScraper
from config import get_mirrors


def benchmark_search():
    print("================================================================================")
    print("  LibGen Search & Lookup Benchmark (No Downloads)")
    print("  Test Target: 'Foundation and Empire' (Series: Foundation, Lang: English)")
    print("================================================================================\n")

    scraper = LibgenScraper(timeout=8)

    test_cases = [
        # (Label, Query, Field, Language, Mode)
        ("Series Search [EN]", "Foundation", "s", "English", "Prioritize"),
        ("Title in Series [EN]", "Foundation and Empire", "t", "English", "Prioritize"),
        ("All Fields [EN]", "Foundation and Empire", "", "English", "Prioritize"),
        ("Author Search [EN]", "Isaac Asimov", "a", "English", "Prioritize"),
        ("Series Strict [EN]", "Foundation", "s", "English", "Strict"),
        ("Field Fallback Test", "Foundation and Empire", "s", "English", "Prioritize"),
        ("Multi-Lang [EN+DE]", "Foundation", "s", ["English", "German"], "Prioritize"),
        ("Strict Non-Match [DE]", "Foundation and Empire", "t", "German", "Strict"),
    ]

    results = []

    print(f"{'#':<3} {'Test Case':<24} {'Field':<8} {'Lang':<10} {'Mode':<11} {'Time':<9} {'Count':<7} {'Top Result'}")
    print("-" * 110)

    for idx, (label, query, field, lang, mode) in enumerate(test_cases, 1):
        t0 = time.perf_counter()
        try:
            books = scraper.search(
                query=query,
                search_field=field,
                preferred_language=lang,
                filter_mode=mode,
                max_results=5,
                unique_results=True,
            )
            elapsed = time.perf_counter() - t0
            count = len(books)
            if books:
                top_b = books[0]
                top_str = f"\"{top_b.title[:30]}\" ({top_b.author[:18]}, {top_b.language})"
            else:
                top_str = "No results"

            lang_display = ",".join(lang) if isinstance(lang, list) else str(lang)
            field_display = field if field else "all"

            results.append({
                "idx": idx,
                "label": label,
                "field": field_display,
                "lang": lang_display,
                "mode": mode,
                "time_ms": int(elapsed * 1000),
                "count": count,
                "top": top_str,
            })

            print(f"{idx:<3} {label:<24} {field_display:<8} {lang_display:<10} {mode:<11} {elapsed*1000:6.1f} ms {count:<7} {top_str}")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"{idx:<3} {label:<24} {field:<8} {str(lang):<10} {mode:<11} {elapsed*1000:6.1f} ms 0       Error: {str(e)[:30]}")

    print("-" * 110)
    avg_latency = sum(r["time_ms"] for r in results) / max(len(results), 1)
    print(f"\n[SUMMARY] Completed {len(results)} search benchmarks. Average Lookup Latency: {avg_latency:.1f} ms\n")


if __name__ == "__main__":
    benchmark_search()

