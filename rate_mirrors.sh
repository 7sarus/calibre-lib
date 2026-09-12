#!/usr/bin/env bash
# ==============================================================================
# rate_mirrors.sh - Independent LibGen Mirror Latency & Bandwidth Rating Tool
# Concurrently probes LibGen mirrors, benchmarks speed, and ranks them in a table.
# ==============================================================================

set -uo pipefail

TIMEOUT=8
USER_AGENT="Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"

# ANSI Colors
if [ -t 1 ]; then
    BOLD="\033[1m"
    GREEN="\033[32m"
    CYAN="\033[36m"
    YELLOW="\033[33m"
    RED="\033[31m"
    MAGENTA="\033[35m"
    RESET="\033[0m"
else
    BOLD=""
    GREEN=""
    CYAN=""
    YELLOW=""
    RED=""
    MAGENTA=""
    RESET=""
fi

echo -e "${BOLD}======================================================================${RESET}"
echo -e "  ${BOLD}LibGen Mirrors Latency & Bandwidth Benchmark${RESET}"
echo -e "${BOLD}======================================================================${RESET}"

# 1. Base list of mirrors or user-supplied arguments
if [ "$#" -gt 0 ]; then
    MIRRORS=("$@")
    echo -e "[*] Using ${BOLD}${#MIRRORS[@]}${RESET} custom mirror(s) from arguments."
else
    MIRRORS=(
        "https://libgen.li"
        "https://libgen.la"
        "https://libgen.gl"
        "https://libgen.bz"
        "https://libgen.vg"
        "https://libgen.is"
    )

    # 2. Fetch live discovered mirrors from open-slum tracker
    echo -n "[*] Querying open-slum.org tracker for live mirrors... "
    DISCOVERED=$(curl -sL -m 5 https://open-slum.org/libgen.html 2>/dev/null | grep -oP 'href="(https://libgen\.[a-z]+)"' | cut -d'"' -f2 | sort -u || true)
    if [ -n "$DISCOVERED" ]; then
        echo -e "${GREEN}Found active mirrors.${RESET}"
        while IFS= read -r m; do
            [ -n "$m" ] && MIRRORS+=("$m")
        done <<< "$DISCOVERED"
    else
        echo -e "${YELLOW}Tracker unreachable; using default set.${RESET}"
    fi
fi

# De-duplicate list
mapfile -t UNIQUE_MIRRORS < <(printf "%s\n" "${MIRRORS[@]}" | sort -u)
TOTAL=${#UNIQUE_MIRRORS[@]}
echo -e "[*] Testing ${BOLD}${TOTAL}${RESET} mirrors concurrently (timeout: ${TIMEOUT}s)...\n"

TMP_DIR=$(mktemp -d /tmp/libgen_rate_XXXXXX)
trap 'rm -rf "$TMP_DIR"' EXIT

# 3. Probe function
test_mirror() {
    local mirror="$1"
    local idx="$2"
    local out_file="$TMP_DIR/res_${idx}.txt"

    # curl: write http_code, ttfb, total_time, speed_bytes_sec, size_bytes
    local curl_stats
    curl_stats=$(curl -sL --compressed -m "$TIMEOUT" -A "$USER_AGENT" -o /dev/null \
        -w "%{http_code} %{time_starttransfer} %{time_total} %{speed_download} %{size_download}\n" \
        "$mirror" 2>/dev/null) || true

    curl_stats=$(echo "$curl_stats" | head -n1)
    if [ -z "$curl_stats" ]; then
        curl_stats="000 0 0 0 0"
    fi

    read -r code ttfb total speed_bytes size_bytes <<< "$curl_stats"
    code=${code:-000}
    ttfb=${ttfb:-0}
    total=${total:-0}
    speed_bytes=${speed_bytes:-0}
    size_bytes=${size_bytes:-0}

    local latency_ms=0
    local speed_kbs=0
    local speed_str="0 KB/s"
    local size_str="0 B"
    local status="Offline"
    local grade="F"
    local score=0

    # Calculate latency in ms
    if awk "BEGIN {exit !($ttfb > 0)}" 2>/dev/null; then
        latency_ms=$(awk "BEGIN {printf \"%d\", $ttfb * 1000}")
    elif awk "BEGIN {exit !($total > 0)}" 2>/dev/null; then
        latency_ms=$(awk "BEGIN {printf \"%d\", $total * 1000}")
    fi

    # Calculate download speed
    if awk "BEGIN {exit !($speed_bytes > 0)}" 2>/dev/null; then
        speed_kbs=$(awk "BEGIN {printf \"%.1f\", $speed_bytes / 1024.0}")
        if awk "BEGIN {exit !($speed_kbs >= 1024.0)}" 2>/dev/null; then
            speed_str=$(awk "BEGIN {printf \"%.2f MB/s\", $speed_kbs / 1024.0}")
        else
            speed_str="${speed_kbs} KB/s"
        fi
    fi

    # Format payload size
    if [[ "$size_bytes" =~ ^[0-9]+$ ]] && [ "$size_bytes" -ge 1048576 ]; then
        size_str=$(awk "BEGIN {printf \"%.1f MB\", $size_bytes / 1048576.0}")
    elif [[ "$size_bytes" =~ ^[0-9]+$ ]] && [ "$size_bytes" -ge 1024 ]; then
        size_str=$(awk "BEGIN {printf \"%.1f KB\", $size_bytes / 1024.0}")
    elif [[ "$size_bytes" =~ ^[0-9]+$ ]] && [ "$size_bytes" -gt 0 ]; then
        size_str="${size_bytes} B"
    else
        size_str="0 B"
    fi

    # Determine status & rating
    if [ "$code" = "200" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
        status="Online"
        score=100

        # Latency scoring
        if [ "$latency_ms" -lt 400 ]; then
            score=$((score - 0))
        elif [ "$latency_ms" -lt 800 ]; then
            score=$((score - 15))
        elif [ "$latency_ms" -lt 1500 ]; then
            score=$((score - 30))
        elif [ "$latency_ms" -lt 3000 ]; then
            score=$((score - 50))
        else
            score=$((score - 65))
        fi

        # Bandwidth adjustments
        if awk "BEGIN {exit !($speed_kbs >= 500.0)}" 2>/dev/null; then
            score=$((score + 15))
        elif awk "BEGIN {exit !($speed_kbs >= 100.0)}" 2>/dev/null; then
            score=$((score + 5))
        else
            score=$((score - 15))
        fi

        [ "$score" -gt 100 ] && score=100
        [ "$score" -lt 10 ] && score=10

        if [ "$score" -ge 88 ]; then
            grade="A+ (Excellent)"
        elif [ "$score" -ge 78 ]; then
            grade="A (Very Good)"
        elif [ "$score" -ge 65 ]; then
            grade="B (Good)"
        elif [ "$score" -ge 50 ]; then
            grade="C (Fair)"
        else
            grade="D (Slow)"
        fi
    elif [ "$code" = "000" ]; then
        status="Timed out"
        grade="F (Offline)"
        score=0
    else
        status="HTTP $code"
        grade="F (Error)"
        score=0
    fi

    # Write tab-separated result: score, is_ok, latency, speed_kbs, mirror, grade, speed_str, size_str, status
    printf "%d\t%s\t%d\t%s\t%s\t%s\t%s\t%s\t%s\n" \
        "$score" "$([ "$status" = "Online" ] && echo 1 || echo 0)" "$latency_ms" "$speed_kbs" \
        "$mirror" "$grade" "$speed_str" "$size_str" "$status" > "$out_file"
}

# 4. Run tests concurrently in background
i=0
for m in "${UNIQUE_MIRRORS[@]}"; do
    test_mirror "$m" "$i" &
    i=$((i + 1))
done
wait

# 5. Collate and Sort results (online first, score desc, latency asc)
RESULTS=$(cat "$TMP_DIR"/res_*.txt | sort -t$'\t' -k2,2rn -k1,1rn -k3,3n)

# 6. Render Formatted Table
echo -e "${BOLD}==============================================================================================${RESET}"
printf "${BOLD}%-5s %-25s %-16s %-12s %-14s %-11s %s${RESET}\n" "Rank" "Mirror" "Rating" "Latency" "Bandwidth" "Payload" "Status"
echo -e "${BOLD}----------------------------------------------------------------------------------------------${RESET}"

rank=1
while IFS=$'\t' read -r score is_ok latency speed_kbs mirror grade speed_str size_str status; do
    color="$RESET"
    if [[ "$grade" =~ ^A ]]; then
        color="$GREEN"
    elif [[ "$grade" =~ ^B ]]; then
        color="$CYAN"
    elif [[ "$grade" =~ ^C ]]; then
        color="$YELLOW"
    elif [[ "$grade" =~ ^D ]]; then
        color="$YELLOW"
    else
        color="$RED"
    fi

    lat_display="${latency} ms"
    [ "$latency" -eq 0 ] && lat_display="-"

    printf "%-5s %-25s ${color}%-16s${RESET} %-12s ${BOLD}%-14s${RESET} %-11s ${color}%s${RESET}\n" \
        "$rank" "$mirror" "$grade" "$lat_display" "$speed_str" "$size_str" "$status"
    rank=$((rank + 1))
done <<< "$RESULTS"

echo -e "${BOLD}==============================================================================================${RESET}\n"
