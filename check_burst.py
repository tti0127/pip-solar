import numpy as np
import sys
import os

# 청크 단위 처리: 100000 IQ쌍 = 200000 bytes = ~0.042초 @ 2.4MSPS
# 메모리 사용: ~4MB/청크 (vs 원본 ~4GB)
CHUNK_IQ   = 100_000
WINDOW     = 1_000

def check_burst(file1="/home/pip/pip/ant1.bin", file2="/home/pip/pip/ant2.bin"):
    try:
        for f in (file1, file2):
            if not os.path.exists(f) or os.path.getsize(f) < CHUNK_IQ * 2:
                print("ERROR: recording too short or missing", file=sys.stderr)
                return

        # memmap — 파일을 RAM에 올리지 않음
        m1 = np.memmap(file1, dtype=np.uint8, mode="r")
        m2 = np.memmap(file2, dtype=np.uint8, mode="r")
        total_bytes = min(len(m1), len(m2))
        chunk_bytes = CHUNK_IQ * 2  # I+Q 각 1바이트

        max_coh = 0.0
        # 파일 전체에서 10개 청크만 균등 샘플링
        n_chunks = max(1, total_bytes // chunk_bytes)
        step = max(1, n_chunks // 10) * chunk_bytes

        for start in range(0, total_bytes - chunk_bytes, step):
            end = start + chunk_bytes
            # 청크만 float32 변환 — 청크 끝나면 GC
            s1 = m1[start:end].astype(np.float32)
            s2 = m2[start:end].astype(np.float32)
            s1 = (s1 - 127.5) / 127.5
            s2 = (s2 - 127.5) / 127.5
            c1 = s1[0::2] + 1j * s1[1::2]
            c2 = s2[0::2] + 1j * s2[1::2]
            N = min(len(c1), len(c2))

            for i in range(0, N - WINDOW, WINDOW * 5):
                seg1 = c1[i : i + WINDOW]
                seg2 = c2[i : i + WINDOW]
                cross = np.mean(seg1 * np.conj(seg2))
                norm = np.sqrt(
                    np.mean(np.abs(seg1) ** 2) * np.mean(np.abs(seg2) ** 2)
                )
                if norm > 0:
                    coh = float(np.abs(cross) / norm)
                    if coh > max_coh:
                        max_coh = coh

        print(f"{max_coh:.4f}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)

if __name__ == "__main__":
    check_burst()
