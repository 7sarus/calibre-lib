#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Independent Mirror Health & Speed Rating Tool.
Tests all known and discovered LibGen mirrors for latency, throughput, and operational status.
"""

import os
import sys
import time
import concurrent.futures
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import LibgenScraper
from config import get_mirrors


def rate_mirror(is_ok, latency_ms, speed_kb_s, status_msg):
    if not is_ok:
        return "F (Offline)", 0

    score = 100
    # Latency penalty: <300ms: 0, 300-800ms: -15, 800-1500ms: -30, >1500ms: -50
    if latency_ms < 400:
        score -= 0
    elif latency_ms < 800:
        score -= 15
    elif latency_ms < 1500:
        score -= 30
    elif latency_ms < 3000:
        score -= 50
    else:
        score -= 65

    # Bandwidth bonus / penalty:
    if speed_kb_s > 2048:
        score += 15
    elif speed_kb_s > 512:
        score += 5
    elif speed_kb_s < 100:
        score -= 20

    score = max(10, min(100, score))

    if score >= 90:
        grade = "A+ (Excellent)"
    elif score >= 80:
        grade = "A (Very Good)"
    elif score >= 70:
        grade = "B (Good)"
    elif score >= 55:
        grade = "C (Fair)"
    else:
        grade = "D (Slow)"

    return grade, score


def main():
    print("====================================================================")
    print("  LibGen Mirrors Independent Diagnostic & Speed Benchmark")
    print("====================================================================\n")

    scraper = LibgenScraper(timeout=8)

    # 1. Gather all candidates
    mirrors = list(dict.fromkeys(get_mirrors() + scraper.DEFAULT_MIRRORS))

    print(f"[*] Discovering live mirrors from open-slum.org tracker...")
    live_mirrors = scraper.fetch_live_mirrors()
    if live_mirrors:
        print(f"    Discovered: {', '.join(live_mirrors)}")
        for m in live_mirrors:
            if m not in mirrors:
                mirrors.append(m)
    else:
        print("    Tracker offline or unreachable; testing cached mirrors.")

    print(f"\n[*] Testing {len(mirrors)} mirrors concurrently (timeout: 8s)...\n")

    results = []

    def _test(m):
        t0 = time.perf_counter()
        try:
            is_ok, lat_ms, kb_s, speed_str, status_msg = scraper.ping_mirror(m, timeout=8)
            grade, score = rate_mirror(is_ok, lat_ms, kb_s, status_msg)
            return {
                "mirror": m,
                "is_ok": is_ok,
                "latency": lat_ms,
                "kb_s": kb_s,
                "speed_str": speed_str,
                "status": status_msg,
                "grade": grade,
                "score": score,
            }
        except Exception as e:
            return {
                "mirror": m,
                "is_ok": False,
                "latency": int((time.perf_counter() - t0) * 1000),
                "kb_s": 0.0,
                "speed_str": "0 KB/s",
                "status": f"Err: {str(e)[:25]}",
                "grade": "F (Offline)",
                "score": 0,
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(mirrors)) as pool:
        future_map = {pool.submit(_test, m): m for m in mirrors}
        for fut in concurrent.futures.as_completed(future_map):
            res = fut.result()
            results.append(res)
            icon = "✓" if res["is_ok"] else "✗"
            print(f"  [{icon}] {res['mirror']:<25} -> {res['grade']:<15} (Ping: {res['latency']}ms, Speed: {res['speed_str']}, Status: {res['status']})")

    # Sort results: online first, then by score desc, latency asc
    results.sort(key=lambda x: (not x["is_ok"], -x["score"], x["latency"]))

    print("\n" + "=" * 80)
    print(f"{'Rank':<5} {'Mirror':<25} {'Rating':<16} {'Latency':<10} {'Speed':<12} {'Status'}")
    print("-" * 80)
    for idx, r in enumerate(results, 1):
        lat_str = f"{r['latency']} ms"
        print(f"{idx:<5} {r['mirror']:<25} {r['grade']:<16} {lat_str:<10} {r['speed_str']:<12} {r['status']}")
    print("=" * 80)

    # Save to diagnostic log
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mirrors_rating.log")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"LibGen Mirror Rating Report ({time.strftime('%Y-%m-%d %H:%M:%S')})\n")
        f.write("=" * 80 + "\n")
        f.write(f"{'Rank':<5} {'Mirror':<25} {'Rating':<16} {'Latency':<10} {'Speed':<12} {'Status'}\n")
        f.write("-" * 80 + "\n")
        for idx, r in enumerate(results, 1):
            lat_str = f"{r['latency']} ms"
            f.write(f"{idx:<5} {r['mirror']:<25} {r['grade']:<16} {lat_str:<10} {r['speed_str']:<12} {r['status']}\n")


if __name__ == "__main__":
    main()

