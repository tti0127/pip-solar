from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO
import subprocess, os, threading, time, json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'solar_rpi_2026'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

FIGDIR = '/home/icarus/solar/figures'
KEEPDIR = '/home/icarus/solar/keep'
LOGFILE = '/home/icarus/solar/keep/coherence_log.txt'
HISTORY_FILE = '/home/icarus/solar/keep/dashboard_history.jsonl'
MAX_HISTORY = 200

spectrum_state = {'freqs': [], 'power': []}

state = {
    'history': [],
    'logs': [],
    'latest_figure': None,
    'status': {
        'sdr1': False, 'sdr2': False,
        'recording': False, 'analyzing': False,
        'disk_percent': 0, 'disk_used': '—', 'disk_total': '—',
        'burst_active': False,
        'service_active': False,
    }
}

def fmt_bytes(b):
    if b >= 1e9: return f'{b/1e9:.1f} GB'
    if b >= 1e6: return f'{b/1e6:.1f} MB'
    return f'{b/1e3:.1f} KB'

def get_disk():
    try:
        parts = subprocess.run(['df', '/home/icarus/solar'],
            capture_output=True, text=True).stdout.strip().split('\n')[1].split()
        pct = int(parts[4].replace('%',''))
        return pct, fmt_bytes(int(parts[2])*1024), fmt_bytes(int(parts[1])*1024)
    except:
        return 0, '—', '—'

def load_history():
    try:
        with open(HISTORY_FILE, 'r') as f:
            entries = [json.loads(l) for l in f if l.strip()]
        entries = entries[-MAX_HISTORY:]
        state['history'] = entries
        state['logs'] = list(reversed(entries))
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f'history load error: {e}')

def save_history_entry(entry):
    try:
        os.makedirs(KEEPDIR, exist_ok=True)
        with open(HISTORY_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        with open(HISTORY_FILE, 'r') as f:
            lines = f.readlines()
        if len(lines) > MAX_HISTORY * 2:
            with open(HISTORY_FILE, 'w') as f:
                f.writelines(lines[-MAX_HISTORY:])
    except Exception as e:
        print(f'history save error: {e}')

def ts_display(ts):
    try:
        return datetime.strptime(ts, '%Y%m%d_%H%M%S').strftime('%m/%d %H:%M')
    except:
        return ts

def monitor_loop():
    prev_figs = set()
    while True:
        pct, used, total = get_disk()
        state['status'].update(
            disk_percent=pct, disk_used=used, disk_total=total,
        )
        socketio.emit('status_update', {**state['status']})

        try:
            figs = set(f for f in os.listdir(FIGDIR) if f.endswith('.png'))
            new = figs - prev_figs
            for f in sorted(new):
                state['latest_figure'] = f
                socketio.emit('figure_update', {'filename': f})
            prev_figs = figs
        except:
            pass

        time.sleep(8)

load_history()
threading.Thread(target=monitor_loop, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/coherence', methods=['POST'])
def api_coherence():
    d = request.json
    ts = d.get('timestamp', datetime.now().strftime('%Y%m%d_%H%M%S'))
    coh = round(float(d.get('coherence', 0)), 4)
    burst = coh > 0.2
    entry = {'timestamp': ts, 'coherence': coh, 'burst': burst, 'display': ts_display(ts)}
    state['history'].append(entry)
    if len(state['history']) > MAX_HISTORY:
        state['history'] = state['history'][-MAX_HISTORY:]
    state['logs'].insert(0, entry)
    state['status']['burst_active'] = burst
    save_history_entry(entry)
    socketio.emit('coherence_update', entry)
    socketio.emit('log_update', entry)
    return jsonify(ok=True)

@app.route('/api/burst', methods=['POST'])
def api_burst():
    d = request.json
    state['status']['burst_active'] = True
    socketio.emit('burst_alert', d)
    return jsonify(ok=True)

@app.route('/api/status', methods=['POST'])
def api_status():
    d = request.json
    if 'recording' in d: state['status']['recording'] = d['recording']
    if 'analyzing' in d: state['status']['analyzing'] = d['analyzing']
    if 'sdr1' in d: state['status']['sdr1'] = d['sdr1']
    if 'sdr2' in d: state['status']['sdr2'] = d['sdr2']
    if 'service_active' in d: state['status']['service_active'] = d['service_active']
    elif 'recording' in d or 'analyzing' in d:
        state['status']['service_active'] = True
    socketio.emit('status_update', {**state['status']})
    return jsonify(ok=True)

RPI_HOST = 'pip@172.28.1.201'
RPI_PASS = 'pip1234'
CTRL_PASSWORD = 'pip1234'

@app.route('/api/control', methods=['POST'])
def api_control():
    d = request.json
    if d.get('password') != CTRL_PASSWORD:
        return jsonify(ok=False, error='비밀번호가 올바르지 않습니다'), 403
    action = d.get('action')
    if action not in ('start', 'stop'):
        return jsonify(ok=False, error='잘못된 명령'), 400
    result = subprocess.run(
        ['sshpass', '-p', RPI_PASS, 'ssh', '-o', 'StrictHostKeyChecking=no',
         RPI_HOST,
         f"echo {RPI_PASS} | sudo -S systemctl {action} solar_record.service"],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        state['status']['service_active'] = (action == 'start')
        state['status']['recording'] = (action == 'start')
        socketio.emit('status_update', {**state['status']})
    return jsonify(ok=result.returncode == 0)

@app.route('/api/spectrum')
def api_spectrum():
    return jsonify({'freqs': spectrum_state['freqs'], 'power': spectrum_state['power']})

@app.route('/api/spectrum_update', methods=['POST'])
def api_spectrum_update():
    d = request.json
    if d.get('freqs') and d.get('power'):
        spectrum_state['freqs'] = d['freqs']
        spectrum_state['power'] = d['power']
        socketio.emit('spectrum_update', {'freqs': d['freqs'], 'power': d['power']})
    return jsonify(ok=True)

@app.route('/api/history')
def api_history():
    return jsonify(state['history'])

@app.route('/api/logs')
def api_logs():
    return jsonify(state['logs'])

@app.route('/api/figure/<path:filename>')
def api_figure(filename):
    return send_from_directory(FIGDIR, filename)

@app.route('/api/latest_figure')
def api_latest_figure():
    try:
        files = sorted(f for f in os.listdir(FIGDIR) if f.endswith('.png'))
        return jsonify(filename=files[-1] if files else None)
    except:
        return jsonify(filename=None)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
