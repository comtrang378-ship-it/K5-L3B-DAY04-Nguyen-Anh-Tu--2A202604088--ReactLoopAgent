"""Provider adapters dùng chung interface. Không chứa agent loop."""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit

CONFIG = {
    'openai': ('OPENAI_API_KEY', 'https://api.openai.com/v1/chat/completions'),
    'gemini': ('GEMINI_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
    'openrouter': ('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1/chat/completions'),
    'anthropic': ('ANTHROPIC_API_KEY', 'https://api.anthropic.com/v1/messages'),
    'ollama': (None, None),
    'openai-compatible': ('OPENAI_COMPATIBLE_API_KEY', None),
}


def post_json(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', **headers})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        error = body.get('error') if isinstance(body, dict) else None
        details_source = error if isinstance(error, dict) else body
        if not isinstance(details_source, dict):
            details_source = {}

        secrets = []
        for name, value in headers.items():
            if name.lower() in ('authorization', 'x-api-key') and isinstance(value, str):
                secrets.append(value)
                if name.lower() == 'authorization' and ' ' in value:
                    secrets.append(value.split(' ', 1)[1])

        details = []
        for field in ('status', 'type', 'code'):
            value = details_source.get(field)
            if isinstance(value, (str, int, float)) and value != '':
                text = ' '.join(str(value).split())
                for secret in secrets:
                    text = text.replace(secret, '[REDACTED]')
                details.append(f'{field}={text[:40]}')
        message = details_source.get('message')
        if not isinstance(message, str) and isinstance(error, str):
            message = error
        if isinstance(message, str) and message:
            text = ' '.join(message.split())
            for secret in secrets:
                text = text.replace(secret, '[REDACTED]')
            details.append(f'message={text[:100]}')
        retry_after = exc.headers.get('Retry-After') if exc.headers else None
        if retry_after:
            details.append(f'retry_after={str(retry_after)[:20]}')
        if not details:
            fields = ','.join(str(field) for field in body.keys()) if isinstance(body, dict) else type(body).__name__
            details.append(f'response_shape={fields[:60]}')

        diagnostic = f"; {'; '.join(details)[:150]}" if details else ''
        host = urlsplit(url).hostname or 'unknown'
        raise RuntimeError(
            f'Provider {host} trả HTTP {exc.code}{diagnostic}; kiểm tra model, key và quota.'
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'Không kết nối được provider: {exc.reason}') from exc


class Provider:
    """complete(messages, schemas) -> {message, calls, finish, usage}.

    messages: system/user/assistant/tool theo format Chat Completions. message trả về
    cần được append nguyên vẹn; tool result có role, tool_call_id, content (JSON string).
    """
    def __init__(self, name, model):
        if name not in CONFIG:
            raise ValueError(f'Provider không hợp lệ: {name}')
        if not model:
            raise ValueError('Cần đặt MODEL là model có hỗ trợ tool calling.')
        self.name, self.model = name, model
        key_name, endpoint = CONFIG[name]
        if name == 'ollama':
            base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
            self.url = f'{base_url.rstrip("/")}/chat/completions'
            self.key = None
        elif name == 'openai-compatible':
            base_url = os.getenv('OPENAI_COMPATIBLE_BASE_URL')
            if not base_url:
                raise ValueError('Thiếu OPENAI_COMPATIBLE_BASE_URL; xem README.md.')
            self.url = base_url.rstrip('/')
            if not self.url.endswith('/chat/completions'):
                self.url += '/chat/completions'
            self.key = os.getenv(key_name)
        else:
            self.url = endpoint
            self.key = os.getenv(key_name)
            if not self.key:
                raise ValueError(f'Thiếu {key_name}; xem README.md.')

    def complete(self, messages, schemas):
        if self.name == 'anthropic':
            return self._anthropic(messages, schemas)
        payload = {'model': self.model, 'messages': messages}
        if schemas:
            payload['tools'] = schemas
        headers = {'Authorization': f'Bearer {self.key}'} if self.key else {}
        data = post_json(self.url, headers, payload)
        choice = data['choices'][0]
        message = choice['message']
        calls = [{'id': c['id'], 'name': c['function']['name'], 'arguments': c['function']['arguments']} for c in message.get('tool_calls', [])]
        return {'message': message, 'calls': calls, 'finish': choice.get('finish_reason'), 'usage': data.get('usage', {})}

    def _anthropic(self, messages, schemas):
        system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
        native = []
        for m in messages:
            if m['role'] == 'system':
                continue
            if m['role'] == 'assistant':
                blocks = []
                if m.get('content'):
                    blocks.append({'type': 'text', 'text': m['content']})
                for call in m.get('tool_calls', []):
                    blocks.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'], 'input': json.loads(call['function']['arguments'])})
                native.append({'role': 'assistant', 'content': blocks})
            elif m['role'] == 'tool':
                block = {'type': 'tool_result', 'tool_use_id': m['tool_call_id'], 'content': m['content']}
                if native and native[-1]['role'] == 'user' and isinstance(native[-1]['content'], list):
                    native[-1]['content'].append(block)
                else:
                    native.append({'role': 'user', 'content': [block]})
            else:
                native.append({'role': 'user', 'content': m['content']})
        tools = [{'name': x['function']['name'], 'description': x['function']['description'], 'input_schema': x['function']['parameters']} for x in schemas]
        payload = {'model': self.model, 'max_tokens': 1024, 'system': system, 'messages': native}
        if tools:
            payload['tools'] = tools
        data = post_json(self.url, {'x-api-key': self.key, 'anthropic-version': '2023-06-01'}, payload)
        blocks = data['content']
        calls = [{'id': b['id'], 'name': b['name'], 'arguments': json.dumps(b['input'], ensure_ascii=False)} for b in blocks if b['type'] == 'tool_use']
        text = '\n'.join(b['text'] for b in blocks if b['type'] == 'text')
        message = {'role': 'assistant', 'content': text or None}
        if calls:
            message['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': c['arguments']}} for c in calls]
        reason = {'end_turn': 'stop', 'tool_use': 'tool_calls', 'max_tokens': 'length'}.get(data.get('stop_reason'), data.get('stop_reason'))
        return {'message': message, 'calls': calls, 'finish': reason, 'usage': data.get('usage', {})}
