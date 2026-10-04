# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Installed plugin: fresh/cached owner turns and denied routes, no API calls."""
import hermes_bootstrap
import hermes_yaml as yaml
import json,os,shutil,tempfile
from pathlib import Path
from hermes_constants import set_hermes_home_override,reset_hermes_home_override
from hermes_cli.plugins import get_plugin_manager
from gateway.session_context import set_session_vars,clear_session_vars
from tools.registry import registry

def main():
 os.umask(0o077);live=Path('/home/operator/.hermes');root=Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
 entry=yaml.safe_load((live/'config.yaml').read_text())['plugins']['entries']['automation-api-catalog']
 with tempfile.TemporaryDirectory(prefix='catalog-route-') as tmp:
  home=Path(tmp);shutil.copytree(live/'plugins/automation-api-catalog',home/'plugins/automation-api-catalog')
  (home/'config.yaml').write_text(json.dumps({'plugins':{'enabled':['automation-api-catalog'],'entries':{'automation-api-catalog':entry}}}))
  override=set_hermes_home_override(home);manager=get_plugin_manager();manager.discover_and_load();rows=[]
  try:
   for label,sid,user,chat,typ in [('fresh','route-smoke','100001','100001','dm'),('cached','','100001','100001','dm'),('foreign_user','','999','100001','dm'),('group','','100001','-999','group')]:
    tokens=set_session_vars(platform='telegram',chat_type=typ,chat_id=chat,user_id=user,session_key='route-smoke-key',message_id=label,session_id=sid)
    try:
     manager.invoke_hook('pre_llm_call',session_id='route-smoke',turn_id=label,platform='telegram',sender_id=user,parent_session_id='',user_message='catalog smoke',conversation_history=[])
     result=json.loads(registry.dispatch('integration_catalog',{'service':'yandex_go','view':'service'},scope=str(home)))
     rows.append({'scenario':label,'ok':result['ok'],'error':result.get('error'),'reason':result.get('reason')})
    finally:clear_session_vars(tokens)
  finally:manager.unload();reset_hermes_home_override(override)
 report={'scenarios':rows,'provider_calls':0,'passed':[r['ok'] for r in rows]==[True,True,False,False]}
 (root/('route-smoke-after.json' if report['passed'] else 'route-smoke-before.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
