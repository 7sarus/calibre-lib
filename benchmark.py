#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
LibGen Benchmark Runner:
Standard benchmark query: Series="Foundation", max_results=5.
Measures and logs exact timing breakdowns, data transfer, bandwidth, and fastest CDNs.
Completely offline and untracked (local manual test run only).
"""

import os
import sys
import time
import tempfile
import shutil
from urllib.parse import urlparse

# Ensure local repository root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import LibgenScraper
from config import get_mirrors, get_fastest_cdns, record_cdn_speed


class BenchmarkLogger:
    def __init__(self, log_file=None):
        self.log_file = log_file
        self.events = []
        self.start_time = None
        self.end_time = None

    def log(self, stage, message, elapsed_stage=None):
        now_str = time.strftime("%H:%M:%S")
        if elapsed_stage is not None:
            line = f"[{now_str}] [{stage:<12}] {message} ({elapsed_stage:.2f}s)"
        else:
            line = f"[{now_str}] [{stage:<12}] {message}"
        print(line, flush=True)
        self.events.append((time.time(), stage, message, elapsed_stage))
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()


def run_benchmark():
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark.log")
    logger = BenchmarkLogger(log_file=log_path)

    # Initialize log
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"=== LibGen Benchmark Run: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

    logger.log("START", "=== Starting Benchmark: Series 'Foundation' (5 books) ===")
    total_start = time.perf_counter()

    fast_mode = "--fast" in sys.argv
    unique_mode = "--no-unique" not in sys.argv

    # Step 1: Initialize Scraper & Mirrors
    t0 = time.perf_counter()
    mirrors = get_mirrors()
    scraper = LibgenScraper(mirrors=mirrors, timeout=15)
    t_init = time.perf_counter() - t0
    mode_desc = " [FAST MODE]" if fast_mode else " [STANDARD MODE]"
    logger.log("INIT", f"Loaded {len(mirrors)} mirrors: {', '.join(mirrors[:3])}...{mode_desc}", t_init)

    # Step 2: Search for Series "Foundation" (max_results=5)
    logger.log("SEARCH", f"Searching for series 'Foundation' (max_results=5, unique={unique_mode})...")
    t0 = time.perf_counter()
    books = scraper.search(
        query="Foundation",
        search_field="s",
        max_results=5,
        unique_results=unique_mode,
    )
    t_search = time.perf_counter() - t0
    logger.log("SEARCH", f"Found {len(books)} books from mirror search", t_search)

    if not books:
        logger.log("ERROR", "No books returned from search! Benchmark aborted.")
        return 1

    temp_dir = tempfile.mkdtemp(prefix="libgen_bench_")
    book_timings = []
    total_bytes_downloaded = 0

    try:
        # Step 3: Sequential Downloads with Timing Breakdown
        for idx, book in enumerate(books, 1):
            short_title = (book.title or "Unknown")[:45]
            ext = (book.extension or "epub").lower()
            logger.log("BOOK_START", f"[{idx}/5] \"{short_title}\" ({book.size}, {ext.upper()})")

            dest_file = os.path.join(temp_dir, f"bench_{idx}.{ext}")
            t_book_start = time.perf_counter()
            resolve_start = time.perf_counter()
            resolve_duration = [0.0]
            stream_duration = [0.0]
            used_cdn = ["unknown"]

            def on_log(msg):
                if "Piece-together active:" in msg:
                    parts = msg.split("across")
                    if len(parts) > 1:
                        used_cdn[0] = "multi-segment (" + parts[1].strip() + ")"
                    else:
                        used_cdn[0] = "multi-segment"
                elif "Streaming directly via" in msg or "Streaming via" in msg:
                    resolve_duration[0] = time.perf_counter() - resolve_start
                    logger.log("RESOLVE", f"[{idx}/5] Mirror link resolved", resolve_duration[0])
                logger.log("DETAIL", f"[{idx}/5] {msg}")

            def on_link(url, stage):
                if stage == "streaming":
                    used_cdn[0] = urlparse(url).netloc
                    logger.log("STREAM_URL", f"[{idx}/5] Stream target: {urlparse(url).netloc}")

            t_stream_start = time.perf_counter()
            try:
                dest_path, cover = scraper.resolve_and_download(
                    book.detail_url,
                    dest_file,
                    book_title=book.title,
                    book_author=book.author,
                    book_ext=book.extension,
                    log_callback=on_log,
                    link_callback=on_link,
                    fast_mode=fast_mode,
                )
                t_book_end = time.perf_counter()
                t_book_total = t_book_end - t_book_start

                file_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
                total_bytes_downloaded += file_size
                speed_kb = (file_size / 1024.0) / t_book_total if t_book_total > 0 else 0.0

                book_timings.append({
                    "idx": idx,
                    "title": short_title,
                    "ext": ext.upper(),
                    "size_bytes": file_size,
                    "time_sec": t_book_total,
                    "speed_kb": speed_kb,
                    "cdn": used_cdn[0],
                    "status": "Success",
                })

                logger.log(
                    "BOOK_DONE",
                    f"[{idx}/5] Completed: {file_size / (1024*1024):.2f} MB in {t_book_total:.2f}s "
                    f"({speed_kb:.1f} KB/s) via {used_cdn[0]}",
                    t_book_total,
                )
            except Exception as dl_err:
                t_book_end = time.perf_counter()
                t_book_total = t_book_end - t_book_start
                book_timings.append({
                    "idx": idx,
                    "title": short_title,
                    "ext": ext.upper(),
                    "size_bytes": 0,
                    "time_sec": t_book_total,
                    "speed_kb": 0.0,
                    "cdn": "failed",
                    "status": f"Failed ({dl_err})",
                })
                logger.log(
                    "BOOK_FAIL",
                    f"[{idx}/5] ✗ Failed: \"{short_title}\" after {t_book_total:.2f}s ({dl_err})",
                    t_book_total,
                )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    total_duration = time.perf_counter() - total_start

    # Step 4: Aggregate and Print "What Took How Much" Breakdown
    total_mb = total_bytes_downloaded / (1024.0 * 1024.0)
    avg_speed_kb = (total_bytes_downloaded / 1024.0) / total_duration if total_duration > 0 else 0.0
    avg_speed_mb = avg_speed_kb / 1024.0

    summary_lines = [
        "",
        "=" * 68,
        "  📊 BENCHMARK TIMING BREAKDOWN (WHAT TOOK HOW MUCH)",
        "=" * 68,
        f"  Total Elapsed Time:   {total_duration:.2f}s ({int(total_duration // 60)}m {total_duration % 60:.1f}s)",
        f"  Total Data Download:  {total_mb:.2f} MB ({total_bytes_downloaded:,} bytes)",
        f"  Overall Bandwidth:    {avg_speed_mb:.2f} MB/s ({avg_speed_kb:.1f} KB/s)",
        "-" * 68,
        f"  Phase / Item                     Time (s)     Ratio     Bandwidth / CDN",
        "-" * 68,
        f"  Search & Mirror Scrape          {t_search:7.2f}s    {(t_search / total_duration) * 100:5.1f}%    LibGen Query API",
    ]

    for b in book_timings:
        pct = (b["time_sec"] / total_duration) * 100
        size_str = f"{b['size_bytes'] / (1024*1024):.2f}MB" if b["size_bytes"] > 0 else "FAILED"
        status_icon = "✓" if b["status"] == "Success" else "✗"
        summary_lines.append(
            f"  {status_icon} Book {b['idx']} ({size_str:<6} {b['ext']:<4})       {b['time_sec']:7.2f}s    {pct:5.1f}%    "
            f"{b['speed_kb']:6.1f} KB/s ({b['cdn']})"
        )

    summary_lines.append("-" * 68)

    # Fastest CDNs logged
    fastest = get_fastest_cdns()
    if fastest:
        summary_lines.append("  ⚡ Fastest CDNs Recorded:")
        for host, spd in fastest[:5]:
            summary_lines.append(f"     • {host:<28} : {spd:7.1f} KB/s ({spd / 1024:.2f} MB/s)")
    summary_lines.append("=" * 68)

    summary_text = "\n".join(summary_lines)
    print(summary_text)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n" + summary_text + "\n")

    logger.log("FINISH", f"Benchmark completed in {total_duration:.2f}s. Log saved to benchmark.log.")
    return 0


if __name__ == "__main__":
    sys.exit(run_benchmark())

