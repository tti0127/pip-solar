"""상주 스펙트럼 데몬 — 종료될 때까지 루프하며 ant1.bin FFT → 대시보드 전송"""
import numpy as np, sys, json, time, os, signal
import urllib.request

SAMPLE_RATE = 2.4e6
CENTER_FREQ = 20.1e6
N_FFT       = 2048
READ_BYTES  = 2 * N_FFT * 256   # 256 FFT 평균치 분량
INTERVAL    = 0.1                  # 초
DASHBOARD   = 'http://10.15.117.111:5000'

filepath = sys.argv[1] if len(sys.argv) > 1 else '/home/pip/pip/ant1.bin'
window   = np.hanning(N_FFT)
running  = True

signal.signal(signal.SIGTERM, lambda *_: globals().update(running=False))
signal.signal(signal.SIGINT,  lambda *_: globals().update(running=False))


def compute():
    fsize = os.path.getsize(filepath)
    if fsize < N_FFT * 2:
        return None
    with open(filepath, 'rb') as f:
        read = min(READ_BYTES, fsize)
        f.seek(-read, 2)
        raw = np.frombuffer(f.read(read), dtype=np.uint8).astype(np.float32)
    raw = (raw - 127.5) / 127.5
    iq  = raw[0::2] + 1j * raw[1::2]
    n_avg = len(iq) // N_FFT
    if n_avg == 0:
        return None
    pw = np.zeros(N_FFT)
    for i in range(n_avg):
        seg = iq[i * N_FFT:(i + 1) * N_FFT] * window
        pw += np.fft.fftshift(np.abs(np.fft.fft(seg)) ** 2)
    pw    = 10 * np.log10(pw / n_avg + 1e-12)
    freqs = (np.fft.fftshift(np.fft.fftfreq(N_FFT, 1 / SAMPLE_RATE)) + CENTER_FREQ) / 1e6
    mask  = (freqs >= 18.9) & (freqs <= 21.3)
    step  = max(1, int(mask.sum()) // 512)
    return {'freqs': freqs[mask][::step].round(4).tolist(),
            'power': pw[mask][::step].round(2).tolist()}


def post(data):
    body = json.dumps(data).encode()
    req  = urllib.request.Request(
        f'{DASHBOARD}/api/spectrum_update', data=body,
        headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=3)


while running:
    try:
        data = compute()
        if data:
            post(data)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f'spectrum_daemon error: {e}', file=sys.stderr)
    time.sleep(INTERVAL)
