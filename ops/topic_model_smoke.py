# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Four real main-model choices from Telegram's fetched catalogue; no topic edits."""
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

if sys.argv[1:]!=['--execute']:raise SystemExit('Requires --execute (four model requests, no Telegram edits)')
os.umask(0o077)
project=Path('/home/operator/workspaces/automation-integrations');root=Path('/home/operator/.local/share/automation-integrations/greif/topics')
assert not (root/'smoke-attempt').exists(),'No implicit paid rerun'
(root/'smoke-attempt').write_text('started')
plugin=root/'smoke-plugin';shutil.copytree(project/'bridges/hermes_topics',plugin,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copyfile(project/'automation_integrations/topic_style.py',plugin/'topic_style.py')
spec=importlib.util.spec_from_file_location('topic_smoke_plugin',plugin/'__init__.py',submodule_search_locations=[str(plugin)])
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
catalog={s['emoji']:s['id'] for s in json.loads((root/'catalog.json').read_text())}
selected=[]
for context in ['Монтаж электрического щита и подбор автоматов.', 'Разводка кабеля и размещение розеток в квартире.', 'Ремонт электрического освещения и выключателей.', 'Диагностика короткого замыкания в электропроводке.']:
 allowed=[e for e in catalog if e not in [x['emoji'] for x in selected[-3:]]]
 result=m.choose_style(context,{'title':'','emoji':''},allowed)
 assert result.get('change') is True and result['emoji'] in allowed and 1<=len(result['title'])<=64,result
 selected.append(result)
assert len({x['emoji'] for x in selected})==4
report={'passed':True,'selections':selected,'telegram_edited':False,'rule':'previous_three_distinct_topics'}
(root/'smoke-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
