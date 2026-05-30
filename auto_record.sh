#!/bin/bash
OUTDIR=/home/pip/pip
KEEPDIR=/home/pip/pip/keep
LOGFILE=$KEEPDIR/coherence_log.txt
FIGDIR=/home/pip/pip/figures
DASHBOARD=http://10.15.117.111:5000
ICARUS_USER=icarus
ICARUS_HOST=10.15.117.111
ICARUS_FIGDIR=/home/icarus/solar/figures
DISK_LIMIT=80
BURST_THRESHOLD=0.2

mkdir -p "$KEEPDIR" "$FIGDIR"
touch "$LOGFILE"

post() { curl -sf -X POST "$DASHBOARD$1" -H "Content-Type: application/json" -d "$2" > /dev/null 2>&1; }

cleanup_disk() {
    USAGE=$(df "$OUTDIR" | tail -1 | awk '{print $5}' | tr -d '%')
    while [ "$USAGE" -gt "$DISK_LIMIT" ]; do
        LOWEST=$(sort -k2 -n "$LOGFILE" | head -1)
        TS=$(echo "$LOWEST" | awk '{print $1}')
        [ -z "$TS" ] && break
        rm -f "$KEEPDIR/ant1_${TS}.bin" "$KEEPDIR/ant2_${TS}.bin"
        grep -v "^${TS} " "$LOGFILE" > "${LOGFILE}.tmp" && mv "${LOGFILE}.tmp" "$LOGFILE"
        USAGE=$(df "$OUTDIR" | tail -1 | awk '{print $5}' | tr -d '%')
    done
}

while true; do
    TS=$(date +%Y%m%d_%H%M%S)

    SDR_COUNT=$(lsusb 2>/dev/null | grep -ci 'RTL2838\|0bda:2838\|realtek' || echo 0)
    SDR1=$([ "$SDR_COUNT" -ge 1 ] && echo true || echo false)
    SDR2=$([ "$SDR_COUNT" -ge 2 ] && echo true || echo false)
    post /api/status "{\"recording\":true,\"analyzing\":false,\"timestamp\":\"$TS\",\"sdr1\":$SDR1,\"sdr2\":$SDR2}"
    echo "[$TS] 녹화 시작..."

    rtl_sdr -d 0 -D -f 20100000 -s 2400000 -g 40 "$OUTDIR/ant1.bin" > /dev/null 2>&1 &
    PID1=$!
    rtl_sdr -d 1 -D -f 20100000 -s 2400000 -g 40 "$OUTDIR/ant2.bin" > /dev/null 2>&1 &
    PID2=$!

    # 녹화 중 상주 데몬으로 FFT → 스펙트럼 전송 (2초 주기)
    sleep 2 && /usr/bin/python3 "$OUTDIR/spectrum_daemon.py" "$OUTDIR/ant1.bin" &
    SPEC_PID=$!

    sleep 120
    kill $PID1 $PID2 2>/dev/null
    wait $PID1 $PID2 2>/dev/null
    kill $SPEC_PID 2>/dev/null
    wait $SPEC_PID 2>/dev/null

    # 녹음 실패 감지 (최소 200MB 미만이면 RTL-SDR 오류)
    SIZE1=$(stat -c%s "$OUTDIR/ant1.bin" 2>/dev/null || echo 0)
    SIZE2=$(stat -c%s "$OUTDIR/ant2.bin" 2>/dev/null || echo 0)
    if [ "$SIZE1" -lt 200000000 ] || [ "$SIZE2" -lt 200000000 ]; then
        echo "[$TS] 녹음 실패 (ant1=${SIZE1}B, ant2=${SIZE2}B) → 건너뜀"
        post /api/status "{\"recording\":false,\"analyzing\":false,\"timestamp\":\"$TS\",\"sdr1\":$SDR1,\"sdr2\":$SDR2}"
        rm -f "$OUTDIR/ant1.bin" "$OUTDIR/ant2.bin"
        continue
    fi

    post /api/status "{\"recording\":false,\"analyzing\":true,\"timestamp\":\"$TS\"}"
    echo "[$TS] 분석 중..."

    MAX_COH=$(/usr/bin/python3 "$OUTDIR/check_burst.py" 2>/dev/null)
    if [ -z "$MAX_COH" ]; then
        echo "[$TS] 분석 실패 → 건너뜀"
        post /api/status "{\"recording\":false,\"analyzing\":false,\"timestamp\":\"$TS\"}"
        rm -f "$OUTDIR/ant1.bin" "$OUTDIR/ant2.bin"
        continue
    fi
    echo "[$TS] 코히어런스: $MAX_COH"

    post /api/coherence "{\"timestamp\":\"$TS\",\"coherence\":$MAX_COH}"

    if (( $(echo "$MAX_COH > $BURST_THRESHOLD" | bc -l) )); then
        echo "[$TS] ⚡ 버스트 감지! 보존 중..."
        /usr/bin/python3 "$OUTDIR/analyze_all.py" \
            "$OUTDIR/ant1.bin" "$OUTDIR/ant2.bin" "$TS" > /dev/null 2>&1
        mv "$OUTDIR/ant1.bin" "$KEEPDIR/ant1_${TS}.bin"
        mv "$OUTDIR/ant2.bin" "$KEEPDIR/ant2_${TS}.bin"
        echo "$TS $MAX_COH" >> "$LOGFILE"
        post /api/burst "{\"timestamp\":\"$TS\",\"coherence\":$MAX_COH}"
        # PNG를 icarus로 전송
        sshpass -p 'dkzkfntm1234' rsync -az -e 'ssh -o StrictHostKeyChecking=no' \
            "$FIGDIR/analysis_${TS}.png" \
            "${ICARUS_USER}@${ICARUS_HOST}:${ICARUS_FIGDIR}/" 2>/dev/null || true
    else
        echo "[$TS] 잡음 → 삭제"
        rm -f "$OUTDIR/ant1.bin" "$OUTDIR/ant2.bin"
    fi

    post /api/status "{\"recording\":false,\"analyzing\":false,\"timestamp\":\"$TS\"}"
    cleanup_disk
done
