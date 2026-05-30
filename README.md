# pip-solar — 태양 전파 간섭계 관측 시스템

20.1 MHz 태양 전파 버스트(Type-II/III)를 2안테나 간섭계로 실시간 관측하는 시스템.

## 하드웨어
- Raspberry Pi 5 (8GB)
- RTL-SDR × 2 (직접샘플링, Q-branch)
- 반파장 다이폴 안테나 × 2 (각 3.73m, 남북 7.5m 간격)
- 관측 주파수: 20.1 MHz, 샘플링: 2.4 MSPS, 게인: 40 dB

## 구조

```
RPi (172.28.1.201)
├── auto_record.sh      — 2분 주기 녹음 루프 (systemd: solar_record.service)
├── check_burst.py      — 코히어런스 계산 (memmap 청크 처리, ~20MB RAM)
├── analyze_all.py      — 버스트 감지 시 3패널 PNG 생성
└── spectrum_daemon.py  — 실시간 FFT → 대시보드 스펙트럼 전송

icarus (10.15.117.111)
└── dashboard/          — Flask+SocketIO 대시보드 (포트 5000)
    ├── app.py
    └── templates/index.html
```

## 대시보드
- URL: `http://10.15.117.111:5000`
- 4분할 Apple UI: 코히어런스 그래프 / 실시간 스펙트럼 / 관측 로그 / 시스템 상태
- 버스트 감지 시 Web Notification + 토스트 알림

## 실행
```bash
# RPi — systemd 서비스
sudo systemctl start solar_record.service

# icarus — 대시보드
sudo systemctl start solar_dashboard.service
```
