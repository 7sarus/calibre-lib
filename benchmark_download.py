#!/usr/bin/env python3
"""
LibGen Download Speed Benchmark — v1.11b-75
============================================
Tests multiple download strategies against a REAL LibGen CDN file and reports
hard numbers so we know exactly what helps and what doesn't.

Strategies tested:
  1. Single-stream (baseline via mechanize)
  2. Single-stream with anti-throttle headers
  3. Multi-segment (4 segments, same CDN URL)
  4. Multi-segment (8 segments, same CDN URL)
  5. Multi-segment (8 segments, UA rotation)
  6. Multi-segment (8 segments, UA rotation + CDN hostname expansion)
  7. urllib3 single-stream (if available)
  8. pycurl single-stream (if available)
  9. pycurl with range-request segments

Usage:
    python benchmark_download.py [--md5 <MD5>] [--mirror <URL>]

Default test file: Foundation by Isaac Asimov (if no MD5 supplied, searches for it).
"""

import os
import sys
import re
import ssl
import time
import shutil
import socket
import tempfile
import argparse
import threading
import concurrent.futures
from urllib.parse import urlparse, urljoin
from contextlib import contextmanager

# ---------------------------------------------------------------------------
# Stub calibre if running standalone
# ---------------------------------------------------------------------------
import types

if "calibre" not in sys.modules:
    cal = types.ModuleType("calibre")

    def _make_browser():
        import mechanize
        b = mechanize.Browser()
        b.set_handle_robots(False)
        b.set_handle_refresh(False)
        b.set_handle_equiv(False)
        try:
            ctx = ssl._create_unverified_context()
            b.set_ca_data(context=ctx)
        except Exception:
            pass
        b.addheaders = [
            ("User-Agent", "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0")
        ]
        return b

    cal.browser = _make_browser
    sys.modules["calibre"] = cal
    sys.modules["calibre.customize"] = types.ModuleType("calibre.customize")
    sys.modules["calibre_plugins"] = types.ModuleType("calibre_plugins")
    sys.modules["calibre_plugins.libgen_store"] = types.ModuleType("calibre_plugins.libgen_store")

    cfg = types.ModuleType("calibre_plugins.libgen_store.config")
    cfg.prefs = {}
    cfg.record_successful_mirror = lambda *a: None
    cfg.record_cdn_speed = lambda *a, **kw: None
    cfg.get_fastest_cdns = lambda: []
    sys.modules["calibre_plugins.libgen_store.config"] = cfg


# Now import the real scraper
from scraper import LibgenScraper

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
UA_POOL = LibgenScraper._UA_POOL
DEFAULT_UA = LibgenScraper.USER_AGENT
# A known small book for fast benchmarks (Foundation by Asimov)
DEFAULT_SEARCH = "Foundation Asimov"
# Colors for terminal output
C_BOLD = "\033[1m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_CYAN = "\033[36m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"

_thread_local = threading.local()


def _get_browser():
    """Thread-local mechanize browser."""
    b = getattr(_thread_local, "browser", None)
    if b is None:
        from calibre import browser as make_browser
        b = make_browser()
        b.set_handle_robots(False)
        b.set_handle_refresh(False)
        b.set_handle_equiv(False)
        try:
            ctx = ssl._create_unverified_context()
            b.set_ca_data(context=ctx)
        except Exception:
            pass
        b.addheaders = [("User-Agent", DEFAULT_UA)]
        _thread_local.browser = b
    return b


@contextmanager
def _open(browser_inst, url_or_req, timeout=30):
    resp = browser_inst.open(url_or_req, timeout=timeout)
    try:
        yield resp
    finally:
        try:
            resp.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Phase 0: Resolve a test file
# ---------------------------------------------------------------------------
def resolve_test_file(md5=None, mirror=None):
    """
    Returns (stream_url, total_bytes, accepts_ranges, detail_url).
    """
    scraper = LibgenScraper()

    if not md5:
        # Search for a known book
        print(f"{C_CYAN}Searching for test file: '{DEFAULT_SEARCH}'...{C_RESET}")
        results = scraper.search(DEFAULT_SEARCH, max_results=1)
        if not results:
            print(f"{C_RED}No search results. Supply --md5 manually.{C_RESET}")
            sys.exit(1)
        book = results[0]
        detail_url = book.detail_url
        md5_match = re.search(r'(?i)(?:md5=|[/\\])([a-f0-9]{32})\b', detail_url)
        md5 = md5_match.group(1) if md5_match else None
        print(f"  Found: {book.title} by {book.author} ({book.size}) — MD5: {md5}")
    else:
        detail_url = f"https://libgen.li/ads.php?md5={md5}"
        print(f"{C_CYAN}Using supplied MD5: {md5}{C_RESET}")

    if mirror:
        detail_url = f"{mirror.rstrip('/')}/ads.php?md5={md5}"

    print(f"  Detail URL: {detail_url}")

    # Resolve to direct download URL
    download_url, _ = scraper.resolve_details(detail_url, timeout=15)
    if not download_url:
        print(f"{C_RED}Could not resolve download URL from detail page.{C_RESET}")
        sys.exit(1)

    print(f"  Direct URL: {download_url}")

    # Follow redirect to get actual CDN stream URL + headers
    b = _get_browser()
    with _open(b, download_url, timeout=15) as resp:
        stream_url = resp.geturl()
        headers = resp.info()
        total_bytes = int(headers.get("Content-Length", 0))
        accepts_ranges = "bytes" in headers.get("Accept-Ranges", "").lower()
        # Read and discard (we just needed the headers)
        resp.read(1024)

    cdn_host = urlparse(stream_url).netloc
    print(f"  CDN stream: {stream_url}")
    print(f"  CDN host:   {cdn_host}")
    print(f"  File size:  {total_bytes:,} bytes ({total_bytes / 1024:.1f} KB)")
    print(f"  Ranges:     {'✓ Yes' if accepts_ranges else '✗ No'}")

    # DNS resolution
    try:
        ip = socket.gethostbyname(cdn_host)
        print(f"  CDN IP:     {ip}")
    except Exception:
        pass

    return stream_url, total_bytes, accepts_ranges, detail_url, md5


# ---------------------------------------------------------------------------
# Download strategies
# ---------------------------------------------------------------------------
class BenchResult:
    def __init__(self, name, elapsed, bytes_dl, error=None):
        self.name = name
        self.elapsed = elapsed
        self.bytes_dl = bytes_dl
        self.error = error

    @property
    def speed_kbs(self):
        if self.elapsed <= 0 or self.bytes_dl <= 0:
            return 0
        return (self.bytes_dl / 1024.0) / self.elapsed

    def __str__(self):
        if self.error:
            return f"  {self.name}: {C_RED}FAILED — {self.error}{C_RESET}"
        speed = self.speed_kbs
        color = C_GREEN if speed > 100 else C_YELLOW if speed > 30 else C_RED
        return (
            f"  {self.name}: {color}{speed:.1f} KB/s{C_RESET} "
            f"({self.bytes_dl:,} bytes in {self.elapsed:.2f}s)"
        )


def _download_to_devnull(resp, total_bytes, chunk_size=512 * 1024):
    """Read response and discard bytes. Returns bytes actually read."""
    bytes_read = 0
    while True:
        chunk = resp.read(chunk_size)
        if not chunk:
            break
        bytes_read += len(chunk)
    return bytes_read


def bench_single_stream_bare(stream_url, total_bytes, timeout=60):
    """Strategy 1: Plain mechanize, no extra headers."""
    name = "1. Single stream (bare mechanize)"
    try:
        b = _get_browser()
        t0 = time.time()
        with _open(b, stream_url, timeout=timeout) as resp:
            got = _download_to_devnull(resp, total_bytes)
        return BenchResult(name, time.time() - t0, got)
    except Exception as e:
        return BenchResult(name, time.time() - t0, 0, str(e))


def bench_single_stream_headers(stream_url, total_bytes, timeout=60):
    """Strategy 2: Mechanize + Connection: keep-alive, Referer, Accept."""
    import mechanize
    name = "2. Single stream (anti-throttle headers)"
    t0 = time.time()
    try:
        b = _get_browser()
        cdn_origin = f"https://{urlparse(stream_url).netloc}"
        req = mechanize.Request(
            stream_url,
            headers={
                "User-Agent": DEFAULT_UA,
                "Connection": "keep-alive",
                "Referer": cdn_origin + "/",
                "Accept": "*/*",
                "Accept-Encoding": "identity",
            },
        )
        with _open(b, req, timeout=timeout) as resp:
            got = _download_to_devnull(resp, total_bytes)
        return BenchResult(name, time.time() - t0, got)
    except Exception as e:
        return BenchResult(name, time.time() - t0, 0, str(e))


def _segment_worker(stream_url, start_byte, end_byte, ua, timeout=40):
    """Downloads a single byte range via mechanize. Returns bytes read."""
    import mechanize
    b = _get_browser()
    cdn_origin = f"https://{urlparse(stream_url).netloc}"
    req = mechanize.Request(
        stream_url,
        headers={
            "Range": f"bytes={start_byte}-{end_byte}",
            "Accept-Encoding": "identity",
            "User-Agent": ua,
            "Connection": "keep-alive",
            "Referer": cdn_origin + "/",
            "Accept": "*/*",
        },
    )
    with _open(b, req, timeout=timeout) as resp:
        code = getattr(resp, "code", 200)
        if code not in (200, 206):
            raise Exception(f"HTTP {code}")
        got = 0
        while True:
            chunk = resp.read(512 * 1024)
            if not chunk:
                break
            got += len(chunk)
    return got


def bench_multi_segment(stream_url, total_bytes, num_segments, rotate_ua, label, timeout=60):
    """Generic multi-segment benchmark."""
    t0 = time.time()
    try:
        part_size = total_bytes // num_segments
        ranges = []
        for i in range(num_segments):
            start = i * part_size
            end = total_bytes - 1 if i == num_segments - 1 else (i + 1) * part_size - 1
            ranges.append((start, end))

        total_got = [0]
        lock = threading.Lock()

        def worker(idx):
            start, end = ranges[idx]
            ua = UA_POOL[idx % len(UA_POOL)] if rotate_ua else DEFAULT_UA
            got = _segment_worker(stream_url, start, end, ua, timeout=timeout)
            with lock:
                total_got[0] += got
            return got

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_segments) as pool:
            futures = [pool.submit(worker, i) for i in range(num_segments)]
            for f in concurrent.futures.as_completed(futures):
                f.result()  # re-raise any exceptions

        return BenchResult(label, time.time() - t0, total_got[0])
    except Exception as e:
        return BenchResult(label, time.time() - t0, 0, str(e))


def bench_cdn_expansion(stream_url, total_bytes, timeout=60):
    """Strategy 6: 8 segments across cdn1-cdn4 with UA rotation."""
    name = "6. 8-seg + UA rotation + CDN expansion"
    parsed = urlparse(stream_url)
    host = parsed.netloc
    cdn_match = re.match(r'^cdn(\d+)\.(.+)$', host)

    cdn_urls = [stream_url]
    if cdn_match:
        base_domain = cdn_match.group(2)
        for n in range(1, 5):
            alt_host = f"cdn{n}.{base_domain}"
            if alt_host != host:
                alt_url = parsed._replace(netloc=alt_host).geturl()
                cdn_urls.append(alt_url)

    t0 = time.time()
    try:
        num_segments = 8
        part_size = total_bytes // num_segments
        ranges = []
        for i in range(num_segments):
            start = i * part_size
            end = total_bytes - 1 if i == num_segments - 1 else (i + 1) * part_size - 1
            ranges.append((start, end))

        total_got = [0]
        lock = threading.Lock()

        def worker(idx):
            start, end = ranges[idx]
            ua = UA_POOL[idx % len(UA_POOL)]
            # Distribute segments across available CDN URLs
            url = cdn_urls[idx % len(cdn_urls)]
            try:
                got = _segment_worker(url, start, end, ua, timeout=timeout)
            except Exception:
                # Fallback to primary URL if alt CDN fails
                got = _segment_worker(stream_url, start, end, ua, timeout=timeout)
            with lock:
                total_got[0] += got
            return got

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_segments) as pool:
            futures = [pool.submit(worker, i) for i in range(num_segments)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        return BenchResult(name, time.time() - t0, total_got[0])
    except Exception as e:
        return BenchResult(name, time.time() - t0, 0, str(e))


def bench_urllib3_single(stream_url, total_bytes, timeout=60):
    """Strategy 7: urllib3 (if available) single-stream with connection pooling."""
    name = "7. urllib3 single-stream (conn pool)"
    t0 = time.time()
    try:
        import urllib3
        urllib3.disable_warnings()
        http = urllib3.PoolManager(
            num_pools=4,
            maxsize=10,
            cert_reqs="CERT_NONE",
            headers={
                "User-Agent": DEFAULT_UA,
                "Connection": "keep-alive",
                "Accept": "*/*",
                "Accept-Encoding": "identity",
            },
        )
        resp = http.request("GET", stream_url, preload_content=False, timeout=timeout)
        got = 0
        for chunk in resp.stream(512 * 1024):
            got += len(chunk)
        resp.release_conn()
        return BenchResult(name, time.time() - t0, got)
    except ImportError:
        return BenchResult(name, 0, 0, "urllib3 not available")
    except Exception as e:
        return BenchResult(name, time.time() - t0, 0, str(e))


def bench_pycurl_single(stream_url, total_bytes, timeout=60):
    """Strategy 8: pycurl single-stream."""
    name = "8. pycurl single-stream"
    t0 = time.time()
    try:
        import pycurl
        from io import BytesIO
        got = [0]

        def write_cb(data):
            got[0] += len(data)

        c = pycurl.Curl()
        c.setopt(pycurl.URL, stream_url)
        c.setopt(pycurl.WRITEFUNCTION, write_cb)
        c.setopt(pycurl.FOLLOWLOCATION, True)
        c.setopt(pycurl.MAXREDIRS, 5)
        c.setopt(pycurl.TIMEOUT, timeout)
        c.setopt(pycurl.CONNECTTIMEOUT, 10)
        c.setopt(pycurl.USERAGENT, DEFAULT_UA)
        c.setopt(pycurl.SSL_VERIFYPEER, 0)
        c.setopt(pycurl.SSL_VERIFYHOST, 0)
        c.setopt(pycurl.BUFFERSIZE, 512 * 1024)
        cdn_origin = f"https://{urlparse(stream_url).netloc}/"
        c.setopt(pycurl.REFERER, cdn_origin)
        c.setopt(pycurl.HTTPHEADER, [
            "Connection: keep-alive",
            "Accept: */*",
            "Accept-Encoding: identity",
        ])
        c.perform()
        http_code = c.getinfo(pycurl.HTTP_CODE)
        c.close()
        if http_code >= 400:
            return BenchResult(name, time.time() - t0, got[0], f"HTTP {http_code}")
        return BenchResult(name, time.time() - t0, got[0])
    except ImportError:
        return BenchResult(name, 0, 0, "pycurl not available")
    except Exception as e:
        return BenchResult(name, time.time() - t0, 0, str(e))


def bench_pycurl_multi_segment(stream_url, total_bytes, timeout=60):
    """Strategy 9: pycurl with 8 parallel range requests via multi interface."""
    name = "9. pycurl 8-seg multi-range"
    t0 = time.time()
    try:
        import pycurl
        num_segments = 8
        part_size = total_bytes // num_segments
        ranges = []
        for i in range(num_segments):
            start = i * part_size
            end = total_bytes - 1 if i == num_segments - 1 else (i + 1) * part_size - 1
            ranges.append((start, end))

        total_got = [0]
        lock = threading.Lock()
        cdn_origin = f"https://{urlparse(stream_url).netloc}/"

        def curl_worker(idx):
            start, end = ranges[idx]
            ua = UA_POOL[idx % len(UA_POOL)]
            got = [0]

            def write_cb(data):
                got[0] += len(data)

            c = pycurl.Curl()
            c.setopt(pycurl.URL, stream_url)
            c.setopt(pycurl.WRITEFUNCTION, write_cb)
            c.setopt(pycurl.FOLLOWLOCATION, True)
            c.setopt(pycurl.MAXREDIRS, 5)
            c.setopt(pycurl.TIMEOUT, timeout)
            c.setopt(pycurl.CONNECTTIMEOUT, 10)
            c.setopt(pycurl.USERAGENT, ua)
            c.setopt(pycurl.SSL_VERIFYPEER, 0)
            c.setopt(pycurl.SSL_VERIFYHOST, 0)
            c.setopt(pycurl.BUFFERSIZE, 512 * 1024)
            c.setopt(pycurl.RANGE, f"{start}-{end}")
            c.setopt(pycurl.REFERER, cdn_origin)
            c.setopt(pycurl.HTTPHEADER, [
                "Connection: keep-alive",
                "Accept: */*",
                "Accept-Encoding: identity",
            ])
            c.perform()
            http_code = c.getinfo(pycurl.HTTP_CODE)
            c.close()
            if http_code >= 400:
                raise Exception(f"HTTP {http_code} for segment {idx}")
            with lock:
                total_got[0] += got[0]

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_segments) as pool:
            futures = [pool.submit(curl_worker, i) for i in range(num_segments)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        return BenchResult(name, time.time() - t0, total_got[0])
    except ImportError:
        return BenchResult(name, 0, 0, "pycurl not available")
    except Exception as e:
        return BenchResult(name, time.time() - t0, 0, str(e))


def bench_segment_count_sweep(stream_url, total_bytes, timeout=60):
    """Bonus: test 1, 2, 4, 8, 12, 16 segments to find the sweet spot."""
    results = []
    for n in [1, 2, 4, 8, 12, 16]:
        label = f"  Sweep: {n:2d} segments"
        r = bench_multi_segment(stream_url, total_bytes, n, rotate_ua=True, label=label, timeout=timeout)
        results.append(r)
        print(r)
        # Brief pause to avoid CDN rate-limit between tests
        time.sleep(1)
    return results


# ---------------------------------------------------------------------------
# DNS multi-CDN check
# ---------------------------------------------------------------------------
def check_cdn_hostnames(stream_url):
    """Check which cdn1-cdn4 hostnames resolve and respond."""
    parsed = urlparse(stream_url)
    host = parsed.netloc
    cdn_match = re.match(r'^cdn(\d+)\.(.+)$', host)
    if not cdn_match:
        print(f"  {C_DIM}Not a cdn<N>.domain URL — skipping CDN expansion check{C_RESET}")
        return

    base_domain = cdn_match.group(2)
    print(f"\n{C_BOLD}CDN Hostname Availability ({base_domain}):{C_RESET}")
    for n in range(1, 5):
        alt_host = f"cdn{n}.{base_domain}"
        try:
            ip = socket.gethostbyname(alt_host)
            # Quick TCP connect test
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((ip, 443))
            s.close()
            print(f"  cdn{n}: {C_GREEN}✓ {ip} (TCP 443 open){C_RESET}")
        except socket.gaierror:
            print(f"  cdn{n}: {C_RED}✗ DNS failed{C_RESET}")
        except socket.timeout:
            print(f"  cdn{n}: {C_YELLOW}? DNS OK but TCP timeout{C_RESET}")
        except Exception as e:
            print(f"  cdn{n}: {C_YELLOW}? {e}{C_RESET}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="LibGen Download Speed Benchmark")
    parser.add_argument("--md5", help="MD5 hash of book to test")
    parser.add_argument("--mirror", help="Mirror base URL (e.g. https://libgen.li)")
    parser.add_argument("--sweep-only", action="store_true", help="Only run segment count sweep")
    parser.add_argument("--timeout", type=int, default=60, help="Per-download timeout (default: 60s)")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"{C_BOLD}LibGen Download Speed Benchmark — v1.11b-75{C_RESET}")
    print(f"{'='*60}\n")

    # Phase 0: Resolve test file
    stream_url, total_bytes, accepts_ranges, detail_url, md5 = resolve_test_file(
        md5=args.md5, mirror=args.mirror
    )

    if total_bytes == 0:
        print(f"{C_RED}Cannot determine file size. Aborting.{C_RESET}")
        sys.exit(1)

    if not accepts_ranges:
        print(f"{C_YELLOW}⚠ CDN does not advertise Accept-Ranges: bytes{C_RESET}")
        print(f"  Multi-segment tests may fail.\n")

    # Check CDN hostnames
    check_cdn_hostnames(stream_url)

    timeout = args.timeout

    if args.sweep_only:
        print(f"\n{C_BOLD}Segment Count Sweep (UA rotation on):{C_RESET}")
        bench_segment_count_sweep(stream_url, total_bytes, timeout)
        return

    # Phase 1: Run all strategies
    print(f"\n{C_BOLD}Running benchmarks (timeout: {timeout}s each)...{C_RESET}")
    print(f"{C_DIM}Each test downloads the full {total_bytes:,} bytes.{C_RESET}\n")

    results = []

    # 1. Bare single stream
    print(f"{C_DIM}Testing strategy 1/9...{C_RESET}")
    r = bench_single_stream_bare(stream_url, total_bytes, timeout)
    results.append(r)
    print(r)
    time.sleep(2)  # cooldown between tests

    # 2. Single stream + anti-throttle headers
    print(f"{C_DIM}Testing strategy 2/9...{C_RESET}")
    r = bench_single_stream_headers(stream_url, total_bytes, timeout)
    results.append(r)
    print(r)
    time.sleep(2)

    # 3. 4-segment, same UA
    print(f"{C_DIM}Testing strategy 3/9...{C_RESET}")
    r = bench_multi_segment(stream_url, total_bytes, 4, rotate_ua=False,
                            label="3. 4-seg same-UA", timeout=timeout)
    results.append(r)
    print(r)
    time.sleep(2)

    # 4. 8-segment, same UA
    print(f"{C_DIM}Testing strategy 4/9...{C_RESET}")
    r = bench_multi_segment(stream_url, total_bytes, 8, rotate_ua=False,
                            label="4. 8-seg same-UA", timeout=timeout)
    results.append(r)
    print(r)
    time.sleep(2)

    # 5. 8-segment, UA rotation
    print(f"{C_DIM}Testing strategy 5/9...{C_RESET}")
    r = bench_multi_segment(stream_url, total_bytes, 8, rotate_ua=True,
                            label="5. 8-seg UA-rotation", timeout=timeout)
    results.append(r)
    print(r)
    time.sleep(2)

    # 6. 8-seg + UA + CDN expansion
    print(f"{C_DIM}Testing strategy 6/9...{C_RESET}")
    r = bench_cdn_expansion(stream_url, total_bytes, timeout)
    results.append(r)
    print(r)
    time.sleep(2)

    # 7. urllib3
    print(f"{C_DIM}Testing strategy 7/9...{C_RESET}")
    r = bench_urllib3_single(stream_url, total_bytes, timeout)
    results.append(r)
    print(r)
    time.sleep(2)

    # 8. pycurl single
    print(f"{C_DIM}Testing strategy 8/9...{C_RESET}")
    r = bench_pycurl_single(stream_url, total_bytes, timeout)
    results.append(r)
    print(r)
    time.sleep(2)

    # 9. pycurl multi-segment
    print(f"{C_DIM}Testing strategy 9/9...{C_RESET}")
    r = bench_pycurl_multi_segment(stream_url, total_bytes, timeout)
    results.append(r)
    print(r)

    # Phase 2: Summary
    print(f"\n{'='*60}")
    print(f"{C_BOLD}RESULTS RANKED BY SPEED:{C_RESET}")
    print(f"{'='*60}")

    successful = [r for r in results if not r.error]
    failed = [r for r in results if r.error]

    for i, r in enumerate(sorted(successful, key=lambda x: x.speed_kbs, reverse=True), 1):
        bar_len = int(r.speed_kbs / max(s.speed_kbs for s in successful) * 30) if successful else 0
        bar = "█" * bar_len
        color = C_GREEN if i <= 2 else C_YELLOW if i <= 5 else C_RED
        print(f"  {color}#{i} {r.name}: {r.speed_kbs:.1f} KB/s{C_RESET}  {bar}")

    if failed:
        print(f"\n{C_DIM}Failed:{C_RESET}")
        for r in failed:
            print(f"  {C_RED}✗ {r.name}: {r.error}{C_RESET}")

    # Best vs baseline
    if len(successful) >= 2:
        baseline = next((r for r in results if "bare" in r.name.lower() and not r.error), None)
        best = max(successful, key=lambda x: x.speed_kbs)
        if baseline and best != baseline:
            speedup = best.speed_kbs / max(baseline.speed_kbs, 0.01)
            print(f"\n{C_BOLD}Best: {best.name}{C_RESET}")
            print(f"{C_GREEN}  → {speedup:.1f}× faster than bare single-stream{C_RESET}")

    # Segment sweep recommendation
    print(f"\n{C_BOLD}Run segment sweep for optimal count:{C_RESET}")
    print(f"  python benchmark_download.py --md5 {md5} --sweep-only\n")


if __name__ == "__main__":
    main()

