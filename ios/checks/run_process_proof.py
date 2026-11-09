"""Normal simulator process restart + bounded, payload-free network observation.
Run after the accessory-required DAT suite installs its simulator app. Never installs,
changes permissions, starts a receiver, or operates a physical device.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

def summarize_network(out, phases):
    report = {}
    for phase in ['baseline', 'capture', 'restore']:
        rows = list(csv.reader((out / f'{phase}-app-nettop.csv').open()))
        app_rows = [row for row in rows if row and row[0]]
        counters = {}
        for row in csv.reader((out / f'{phase}-system-nettop.csv').open()):
            if row and re.fullmatch(r'.+\.\d+', row[0]):
                counters.setdefault(row[0], []).append((int(row[1]), int(row[2])))
        deltas = {}
        for name, values in counters.items():
            pid = name.rsplit('.', 1)[1]
            path = subprocess.run(['ps', '-p', pid, '-o', 'comm='], capture_output=True, text=True).stdout.strip()
            role = 'unknown' if not path else ('simulator' if 'SimulatorRuntime' in path or 'CoreSimulator' in path else 'host')
            key = name.rsplit('.', 1)[0] + ' (' + role + ')'
            delta = deltas.setdefault(key, {'in': 0, 'out': 0})
            delta['in'] += values[-1][0] - values[0][0]
            delta['out'] += values[-1][1] - values[0][1]
        report[phase] = {'appFlowRows': len(app_rows), 'samples': sum(bool(r) and not r[0] for r in rows),
                         'systemCounterDeltas': deltas, **phases[phase]}
    (out / 'network-summary.json').write_text(json.dumps(report, indent=2))
    return report

parser = argparse.ArgumentParser()
parser.add_argument('simulator')
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--summarize-existing', action='store_true', help='Read existing counters only; do not launch the app')
args = parser.parse_args()
app_id = 'app.heysophie.capture.photodev'
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True, mode=0o700)
if args.summarize_existing:
    prior = json.loads((out / 'summary.json').read_text())
    print(json.dumps(summarize_network(out, prior['phases']), indent=2))
    raise SystemExit(0)

def sim(*parts, env=None, check=True):
    return subprocess.run(['xcrun', 'simctl', *parts], env=env, capture_output=True, text=True, check=check)

inventory = json.loads(sim('list', 'devices', 'available', '--json').stdout)
assert any(d['udid'] == args.simulator and d['state'] == 'Booted'
           for devices in inventory['devices'].values() for d in devices), 'Existing booted simulator required'
container = Path(sim('get_app_container', args.simulator, app_id, 'data').stdout.strip())
support = container / 'Library/Application Support'

# Only stop the named test app. Preserve its entire data container.
sim('terminate', args.simulator, app_id, check=False)

def observe(phase, seconds, launch=None):
    files = []
    monitors = []
    for scope, names, summary in [('app', ['HeySophie'], False),
                                   ('system', ['nsurlsessiond', 'mDNSResponder', 'apsd', 'networkd'], True)]:
        handle = (out / f'{phase}-{scope}-nettop.csv').open('w')
        files.append(handle)
        command = ['nettop', '-n', '-x', '-L', str(seconds), '-s', '1', '-J', 'bytes_in,bytes_out']
        if summary:
            command.append('-P')
        for name in names:
            command += ['-p', name]
        monitors.append(subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT))
    try:
        pid = launch() if launch else None
    except BaseException:
        for process in monitors:
            process.terminate(); process.wait(timeout=5)
        for handle in files:
            handle.close()
        raise
    started = time.monotonic()
    samples = 0
    socket_samples = 0
    with (out / f'{phase}-sockets.txt').open('w') as log:
        while time.monotonic() - started < seconds:
            if pid:
                sockets = subprocess.run(['lsof', '-nP', '-a', '-p', str(pid), '-i', '-FpcnT'],
                                         capture_output=True, text=True)
                if sockets.returncode not in (0, 1):
                    raise RuntimeError('lsof observation failed: ' + sockets.stderr)
                log.write(f'elapsed={time.monotonic()-started:.3f}\n{sockets.stdout}')
                samples += 1
                socket_samples += bool(sockets.stdout.strip())
            time.sleep(0.5)
    for process in monitors:
        process.wait(timeout=5)
        assert process.returncode == 0, 'nettop failed; inspect private log'
    for handle in files:
        handle.close()
    return {'pid': pid, 'seconds': seconds, 'socketSamples': samples, 'samplesWithSockets': socket_samples}

pids = {}
def launch(mode):
    env = dict(os.environ, SIMCTL_CHILD_HS_META_PROOF_MODE=mode)
    result = sim('launch', args.simulator, app_id, env=env)
    pid = int(re.search(r': (\d+)\s*$', result.stdout).group(1))
    pids[mode] = pid
    print(f'{mode}: launched normal app process', flush=True)
    return pid

def snapshot(mode):
    path = support / 'HSPhotoProof' / (mode + '.json')
    value = json.loads(path.read_text())
    assert value.get('failed') != 'true', 'App reported proof failure: ' + value.get('reason', '')
    assert value['mode'] == mode and value['processID'] == pids[mode], 'Stale or wrong-process proof'
    assert value['sdkConnectionRequested'] == (mode == 'capture')
    receipt = value['receipt']
    root = (support / 'HeySophieCaptures').resolve()
    original = (root / value['relativeFile']).resolve()
    assert original.is_relative_to(root), 'Invalid proof file path'
    data = original.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    manifest_bytes = original.with_name('capture.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest['photoReceipt'] == receipt
    assert manifest['id'].lower() == receipt['request']['id'].lower()
    assert receipt['request']['source'] == 'datMock'
    assert digest == receipt['sha256'] and len(data) == receipt['bytes']
    stat = original.stat()
    return {'receipt': receipt, 'relativeFile': value['relativeFile'], 'data': data,
            'manifest': manifest_bytes, 'inode': stat.st_ino, 'mtime': stat.st_mtime_ns}

print('baseline: app stopped; observing existing OS processes', flush=True)
phases = {'baseline': observe('baseline', 15)}
print('capture: observing normal DAT capture and idle window', flush=True)
phases['capture'] = observe('capture', 30, lambda: launch('capture'))
before = snapshot('capture')
sim('terminate', args.simulator, app_id)
assert subprocess.run(['ps', '-p', str(pids['capture']), '-o', 'comm='], capture_output=True).returncode != 0
print('termination: original process no longer exists; original file retained', flush=True)
phases['restore'] = observe('restore', 20, lambda: launch('restore'))
after = snapshot('restore')
sim('io', args.simulator, 'screenshot', str(out / 'restore-screen.png'))
assert pids['capture'] != pids['restore']
assert before == after, 'Original bytes, receipt, identity, source or file metadata changed after relaunch'
(out / 'verified-photo.jpeg').write_bytes(after['data'])
(out / 'verified-manifest.json').write_bytes(after['manifest'])
(out / 'verified-receipt.json').write_text(json.dumps(after['receipt'], indent=2))
summary = {'restartPassed': True, 'newProcess': True, 'originalFileUnchanged': True,
           'captureIdentityUnchanged': True, 'receiptUnchanged': True, 'source': 'datMock',
           'bytes': after['receipt']['bytes'], 'sha256': after['receipt']['sha256'],
           'dimensions': [after['receipt']['width'], after['receipt']['height']],
           'phases': phases,
           'limits': 'nettop process counters + sampled sockets; no packet capture or zero-egress claim'}
(out / 'summary.json').write_text(json.dumps(summary, indent=2))
summarize_network(out, phases)
sim('terminate', args.simulator, app_id)
print(json.dumps({k:v for k,v in summary.items() if k != 'phases'}, indent=2), flush=True)
