# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Guarded topic-style activation/rollback, preserving all speech settings. No restart."""
import hashlib,json,os,re,shutil,sys
from pathlib import Path
import yaml
ROOT=Path('/home/operator/.local/share/automation-integrations/greif/topics')
HOME=Path('/home/operator/.hermes')
PROJECT=Path('/home/operator/workspaces/automation-integrations')
PLUGIN=HOME/'plugins/automation-topic-style'

def sha(data):return hashlib.sha256(data).hexdigest()
def atomic(path,data):
 tmp=path.with_suffix(path.suffix+'.topics-new')
 with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)

def main():
 os.umask(0o077);config=HOME/'config.yaml';backup=ROOT/'backup'
 if sys.argv[1:]==['apply']:
  assert json.loads((ROOT/'smoke-report.json').read_text())['passed']
  assert not backup.exists() and not PLUGIN.exists(),'Inspect existing deployment first'
  before=config.read_bytes();cfg=yaml.safe_load(before)
  plugins=cfg.setdefault('plugins',{});plugins.setdefault('enabled',[]).append('automation-topic-style')
  telegram=cfg.setdefault('platforms',{}).setdefault('telegram',{});extra=telegram.setdefault('extra',{})
  fixed=['1']
  for item in extra.get('dm_topics',[]):
   if str(item.get('chat_id'))=='100001':fixed.extend(str(t['thread_id']) for t in item.get('topics',[]) if t.get('thread_id'))
  extra['disable_topic_auto_rename']=True
  plugins.setdefault('entries',{})['automation-topic-style']={'settings':{
   'enabled':True,'dry_run':False,'state_dir':str(ROOT/'state'),'owner_id':'100001','chat_id':'100001',
   'bot_id':100002,'env_file':str(HOME/'.env'),'excluded_threads':fixed}}
  text=before.decode()
  for section in ['plugins','platforms']:
   block=yaml.safe_dump({section:cfg[section]},allow_unicode=True,sort_keys=False)
   pattern=rf'(?ms)^{section}:.*?(?=^[A-Za-z_][A-Za-z_0-9-]*:|\Z)'
   if re.search(pattern,text):
    text,count=re.subn(pattern,lambda _:block+'\n',text);assert count==1
   else:text+='\n'+block
  assert yaml.safe_load(text)==cfg
  backup.mkdir(mode=0o700);(backup/'config.yaml').write_bytes(before)
  (backup/'manifest.json').write_text(json.dumps({'before':sha(before),'after':sha(text.encode())},indent=2))
  shutil.copytree(PROJECT/'bridges/hermes_topics',PLUGIN,ignore=shutil.ignore_patterns('__pycache__'))
  shutil.copyfile(PROJECT/'automation_integrations/topic_style.py',PLUGIN/'topic_style.py')
  assert config.read_bytes()==before,'Concurrent config edit'
  atomic(config,text.encode())
 elif sys.argv[1:]==['rollback']:
  manifest=json.loads((backup/'manifest.json').read_text());assert sha(config.read_bytes())==manifest['after'],'Config changed; reconcile manually'
  atomic(config,(backup/'config.yaml').read_bytes())
 else:raise SystemExit('Use apply or rollback')
 print('Topic configuration updated; restart gateway separately')
if __name__=='__main__':main()
