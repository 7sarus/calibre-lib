# Changelog

## [v1.0.0 "Godzila"] - 2026-09-11

### Features
- **Concurrent Bulk Downloading:** Re-engineered the queue to process up to 3 downloads concurrently, dramatically speeding up bulk fetching.
- **Dynamic Live Mirrors:** Automatically scrapes `open-slum.org` to fetch and ingest active fallback mirrors (`.bz`, `.gl`, `.li`) when needed.
- **Async Cover Previews:** Clicking any book in search results or the queue now asynchronously fetches and previews its cover in a new side panel.
- **Compact UI Form Factor:** Redesigned the top options bar into a stacked two-row layout to prevent horizontal overflow on smaller screens.
- **ASCII Progress Queues:** Replaced heavy native `QProgressBar` widgets with fast, clean inline ASCII progress bars (`[██████░░░░]`) in the table.
- **Post-Download Stats:** Added automated summary popups (elapsed time, success ratio) and a dedicated live mirror status log panel.

### Bug Fixes & Bypasses
- **SSL Certificate Spoofing:** Completely bypasses `CERTIFICATE_VERIFY_FAILED` errors by injecting raw, unverified SSL contexts for shady mirrors.
- **Headless Scraper Block (Referer Spoofing):** Bypasses strict scraper protections recently added to the `.li` / `.vg` forks by dynamically spoofing the `Referer` header prior to fetching `ads.php` and `get.php`.
- **Mechanize Latency Elimination:** Hard-disabled automatic `robots.txt`, `meta-refresh`, and `meta-equiv` parsing in the internal browser to eliminate massive artificial handshake latency.
- **Default Result Limits:** Reduced default `max_results` query parameters to `5` to heavily accelerate initial resolution and load times.

