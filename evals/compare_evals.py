"""Compare two eval reports that use the same cases and judge."""
import argparse
import json
from pathlib import Path


def load_report(path):
    try:
        report = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'Không đọc được report {path}: {exc}') from exc
    if not isinstance(report, dict) or not isinstance(report.get('config'), dict):
        raise ValueError(f'Report không hợp lệ: {path}')
    cases = report.get('cases')
    if not isinstance(cases, list):
        raise ValueError(f'Report thiếu danh sách cases: {path}')
    by_id = {}
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str):
            raise ValueError(f'Report có case không hợp lệ: {path}')
        if case['id'] in by_id:
            raise ValueError(f'Report có case ID trùng: {case["id"]}')
        by_id[case['id']] = case
    return report, by_id


def compare_reports(baseline, candidate):
    baseline_report, baseline_cases = load_report(baseline)
    candidate_report, candidate_cases = load_report(candidate)
    baseline_config = baseline_report['config']
    candidate_config = candidate_report['config']
    for key in ('dataset', 'judge_provider', 'judge_model'):
        if baseline_config.get(key) != candidate_config.get(key):
            raise ValueError(f'Hai report phải dùng cùng {key}.')
    if baseline_cases.keys() != candidate_cases.keys():
        raise ValueError('Hai report phải có cùng danh sách case.')

    rows = []
    for case_id in sorted(baseline_cases):
        before = baseline_cases[case_id].get('grade', {}).get('score')
        after = candidate_cases[case_id].get('grade', {}).get('score')
        delta = after - before if isinstance(before, (int, float)) and isinstance(after, (int, float)) else None
        rows.append((case_id, before, after, delta))
    return baseline_config, candidate_config, rows


def main():
    parser = argparse.ArgumentParser(description='So sánh hai kết quả eval')
    parser.add_argument('baseline', help='Report gốc, ví dụ eval_local.json')
    parser.add_argument('candidate', help='Report so sánh, ví dụ eval_api.json')
    args = parser.parse_args()
    try:
        baseline, candidate, rows = compare_reports(args.baseline, args.candidate)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"Gốc: {baseline.get('provider')} / {baseline.get('model')}")
    print(f"So sánh: {candidate.get('provider')} / {candidate.get('model')}")
    print('Case  Gốc  So sánh  Chênh lệch')
    for case_id, before, after, delta in rows:
        delta_text = f'{delta:+g}' if delta is not None else 'n/a'
        print(f'{case_id:<5} {str(before):>4} {str(after):>8} {delta_text:>10}')

    before_total = baseline.get('summary', {}).get('score_0_100')
    after_total = candidate.get('summary', {}).get('score_0_100')
    if isinstance(before_total, (int, float)) and isinstance(after_total, (int, float)):
        print(f'Tổng điểm: {before_total} -> {after_total} ({after_total - before_total:+g})')
    else:
        print('Chưa thể so sánh điểm tổng: có report chưa chấm đủ case.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
