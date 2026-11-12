import argparse
import datetime
import json
import os
from pathlib import Path
import sys
from agent import run_agent
from providers import Provider
from status_tools import StatusTools
from bonus.tools import BonusTools


def run(question, mode, provider_name, model, max_steps, fail=False, bonus=False):
    provider = Provider(provider_name, model)
    tools = BonusTools(mode) if bonus else StatusTools(mode, fail=fail)
    return run_agent(question, provider, tools, max_steps=max_steps)


def main():
    p = argparse.ArgumentParser(description='Chạy status agent')
    p.add_argument('question', help='Câu hỏi cho agent')
    p.add_argument('--bonus', action='store_true', help='Dùng bộ tools bonus')
    p.add_argument('--mode', choices=['snapshot', 'live'], default='snapshot')
    p.add_argument('--provider', choices=['openai', 'gemini', 'anthropic', 'openrouter', 'ollama', 'openai-compatible'], default=os.getenv('PROVIDER', 'openai'))
    p.add_argument('--model', default=os.getenv('MODEL'))
    p.add_argument('--max-steps', type=int, default=6)
    p.add_argument('--output', help='Lưu kết quả JSON cùng cấu hình để xem lại')
    args = p.parse_args()
    if args.max_steps < 1:
        p.error('--max-steps phải >= 1')
    try:
        result = run(args.question, args.mode, args.provider, args.model, args.max_steps, bonus=args.bonus)
    except (ValueError, RuntimeError, NotImplementedError) as exc:
        print(f'Lỗi: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        report = {
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'config': {
                'provider': args.provider,
                'model': args.model,
                'mode': args.mode,
                'max_steps': args.max_steps,
                'bonus': args.bonus,
                'question': args.question,
            },
            'result': result,
        }
        try:
            Path(args.output).write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8',
            )
        except OSError as exc:
            print(f'Không ghi được log vào {args.output}: {exc}', file=sys.stderr)
            return 1
        print(f'Đã lưu log: {args.output}', file=sys.stderr)
    return 0 if result['status'] == 'completed' else 1

if __name__ == '__main__':
    sys.exit(main())
