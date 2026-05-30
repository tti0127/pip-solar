import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import spectrogram
import sys, os

SAMPLE_RATE = 2.4e6
CENTER_FREQ = 20.1e6
FIGDIR = '/home/pip/pip/figures'

def analyze(file1, file2, timestamp):
    try:
        s1 = np.fromfile(file1, dtype=np.uint8).astype(np.float32)
        s2 = np.fromfile(file2, dtype=np.uint8).astype(np.float32)
        min_len = min(len(s1), len(s2))
        min_len -= min_len % 2
        s1 = (s1[:min_len] - 127.5) / 127.5
        s2 = (s2[:min_len] - 127.5) / 127.5
        c1 = s1[0::2] + 1j * s1[1::2]
        c2 = s2[0::2] + 1j * s2[1::2]
        N = min(len(c1), len(c2))

        window = 1000
        coh_list, phase_list, time_list = [], [], []
        for i in range(0, N - window, window * 10):
            seg1 = c1[i:i+window]
            seg2 = c2[i:i+window]
            cross = np.mean(seg1 * np.conj(seg2))
            norm = np.sqrt(np.mean(np.abs(seg1)**2) * np.mean(np.abs(seg2)**2))
            if norm > 0:
                coh_list.append(float(np.abs(cross) / norm))
                phase_list.append(float(np.degrees(np.angle(cross))))
                time_list.append(i / SAMPLE_RATE)

        max_coh = max(coh_list) if coh_list else 0
        mean_coh = float(np.mean(coh_list)) if coh_list else 0

        # Spectrogram
        N_spec = min(N, int(SAMPLE_RATE * 30))
        f, t_s, Sxx = spectrogram(c1[:N_spec], fs=SAMPLE_RATE, nperseg=1024,
                                   noverlap=512, return_onesided=False)
        f_shifted = np.fft.fftshift(f) + CENTER_FREQ
        Sxx_shifted = np.fft.fftshift(Sxx, axes=0)
        mask = (f_shifted >= 18.9e6) & (f_shifted <= 21.3e6)

        BG = '#1c1c1e'
        fig, axes = plt.subplots(3, 1, figsize=(11, 7.5), facecolor=BG)
        fig.subplots_adjust(hspace=0.38, left=0.08, right=0.97, top=0.93, bottom=0.08)

        # Panel 1: Spectrogram
        ax1 = axes[0]
        ax1.set_facecolor(BG)
        if mask.any():
            im = ax1.pcolormesh(t_s, f_shifted[mask]/1e6,
                                10*np.log10(Sxx_shifted[mask]+1e-12),
                                cmap='jet', shading='auto')
            cb = plt.colorbar(im, ax=ax1, pad=0.01)
            cb.ax.tick_params(colors='white', labelsize=8)
            cb.set_label('Power (dB)', color='white', fontsize=9)
        ax1.set_ylabel('Frequency (MHz)', color='white', fontsize=9)
        ax1.set_title(f'Spectrogram — {timestamp}', color='white', fontsize=10, pad=4)
        ax1.tick_params(colors='white', labelsize=8)
        for s in ax1.spines.values(): s.set_color('#444')

        # Panel 2: Coherence
        ax2 = axes[1]
        ax2.set_facecolor(BG)
        ax2.plot(time_list, coh_list, color='#007AFF', linewidth=0.9)
        ax2.axhline(0.2, color='#FF453A', linestyle='--', linewidth=1,
                    label='Burst threshold (0.2)')
        ax2.set_ylabel('Coherence', color='white', fontsize=9)
        ax2.set_title(f'Coherence  (max={max_coh:.3f}, mean={mean_coh:.3f})',
                      color='white', fontsize=10, pad=4)
        ax2.set_ylim(0, 1)
        ax2.legend(facecolor='#2c2c2e', labelcolor='white', fontsize=8,
                   framealpha=0.7, loc='upper right')
        ax2.tick_params(colors='white', labelsize=8)
        for s in ax2.spines.values(): s.set_color('#444')

        # Panel 3: Phase
        ax3 = axes[2]
        ax3.set_facecolor(BG)
        ax3.plot(time_list, phase_list, color='#30D158', linewidth=0.6)
        ax3.set_ylabel('Phase Diff (°)', color='white', fontsize=9)
        ax3.set_xlabel('Time (s)', color='white', fontsize=9)
        ax3.set_title('Phase Difference', color='white', fontsize=10, pad=4)
        ax3.tick_params(colors='white', labelsize=8)
        for s in ax3.spines.values(): s.set_color('#444')

        os.makedirs(FIGDIR, exist_ok=True)
        figpath = os.path.join(FIGDIR, f'analysis_{timestamp}.png')
        plt.savefig(figpath, dpi=130, bbox_inches='tight', facecolor=BG)
        plt.close()
        print(figpath)
        return figpath
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return None

if __name__ == '__main__':
    f1 = sys.argv[1] if len(sys.argv) > 1 else '/home/pip/pip/ant1.bin'
    f2 = sys.argv[2] if len(sys.argv) > 2 else '/home/pip/pip/ant2.bin'
    ts = sys.argv[3] if len(sys.argv) > 3 else 'unknown'
    analyze(f1, f2, ts)
