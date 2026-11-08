"""Run the trusted local demo tests and save a machine-readable report."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent


def run_analysis(timeout=60, run_id=None, reports_dir=None):
    """Run a fixed local test suite. Shared by the CLI and local API."""
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    started = datetime.now(timezone.utc)
    run_id = run_id or started.strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    folder = (reports_dir or ROOT / 'reports') / run_id
    folder.mkdir(parents=True)
    junit = folder / 'results.xml'
    command = [sys.executable, '-m', 'pytest', 'tests', '-v',
               f'--junitxml={junit}']
    summary = {'run_id': run_id, 'started_at': started.isoformat(),
               'status': 'runner_error', 'exit_code': None,
               'counts': {'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0},
               'tests': []}
    try:
        with (folder / 'pytest.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        summary['exit_code'] = result.returncode
        if junit.exists():
            for case in ET.parse(junit).getroot().iter('testcase'):
                state, detail = 'passed', ''
                for tag, label in [('error', 'errors'), ('failure', 'failed'), ('skipped', 'skipped')]:
                    node = case.find(tag)
                    if node is not None:
                        state = label
                        detail = node.text or node.get('message', '')
                        break
                summary['counts'][state] += 1
                summary['tests'].append({'name': case.get('name'),
                                         'classname': case.get('classname'),
                                         'status': state, 'detail': detail})
        if result.returncode == 0:
            summary['status'] = 'passed'
        elif result.returncode == 1:
            summary['status'] = 'tests_failed'
        else:
            summary['message'] = 'pytest could not complete normally; inspect pytest.log.'
    except subprocess.TimeoutExpired:
        summary['status'] = 'timeout'
        summary['message'] = f'pytest exceeded {timeout} seconds.'
    except (OSError, ET.ParseError) as exc:
        summary['message'] = str(exc)

    summary['duration_seconds'] = round((datetime.now(timezone.utc) - started).total_seconds(), 3)
    path = folder / 'summary.json'
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=int, default=60, help='Maximum pytest runtime in seconds')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    summary = run_analysis(timeout=args.timeout)
    print(f"Status: {summary['status']}")
    print(' / '.join(f'{key}: {value}' for key, value in summary['counts'].items()))
    print(f"Report: {ROOT / 'reports' / summary['run_id'] / 'summary.json'}")
    return {'passed': 0, 'tests_failed': 1, 'timeout': 124}.get(summary['status'], 2)


if __name__ == '__main__':
    raise SystemExit(main())
