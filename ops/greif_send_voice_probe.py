# Public example: replace synthetic identities and deployment paths before explicit execution.
"""One outbound owner-approved Telegram probe; no polling or automatic retry.

Run with Hermes dependencies bootstrapped. Tokens never enter argv or reports.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values
from telegram import Bot

ROOT = Path('/home/operator/.local/share/automation-integrations/greif')


async def main():
    os.umask(0o077)
    if sys.argv[1:] != ['--execute']:
        raise SystemExit('Requires --execute: sends one voice to the operator via Greif')
    report = json.loads((ROOT / 'native-smoke/report.json').read_text())
    assert report['passed']
    receipt = ROOT / 'telegram-probe.json'
    assert not receipt.exists(), 'Probe already attempted; inspect receipt, do not retry blindly'
    token = dotenv_values('/home/operator/.hermes/.env')['TELEGRAM_BOT_TOKEN']
    async with Bot(token) as bot:
        me = await bot.get_me()
        assert me.id == 100002 and me.username.lower() == 'example_integration_bot'
        with receipt.open('x') as output:
            json.dump({'state': 'attempting', 'chat_id': 100001, 'thread_id': 100003}, output)
        try:
            with open(report['audio'], 'rb') as voice:
                message = await bot.send_voice(
                    chat_id=100001, message_thread_id=100003, voice=voice,
                    caption='Проверка подключения речи к Грейфу: внешний синтез и распознавание работают. '
                            'Теперь отправьте мне короткое голосовое — проверим ответ в обычном диалоге.')
        except Exception as exc:
            # Keep transport diagnostics without recording Telegram error bodies/URLs.
            receipt.write_text(json.dumps({'state': 'outcome_unknown',
                                          'exception_type': type(exc).__name__,
                                          'chat_id': 100001, 'thread_id': 100003}, indent=2))
            raise SystemExit('Delivery failed or outcome unknown; inspect receipt before any retry') from None
        result = {'state': 'sent', 'chat_id': message.chat_id, 'message_id': message.message_id,
                  'thread_id': message.message_thread_id, 'voice': bool(message.voice)}
        receipt.write_text(json.dumps(result, indent=2))
        print(json.dumps(result))


if __name__ == '__main__':
    asyncio.run(main())
