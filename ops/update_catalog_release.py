# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Update only catalog-owned snapshots; CAS guarded rollback. Gateway restart separate."""
import hashlib,json,os,sys
from pathlib import Path
from ops.greif_catalog_config import atomic
P=Path('/home/operator/workspaces/automation-integrations')
H=Path('/home/operator/.hermes')
R=Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
B=R/'update-20261004-full-api'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 global B
 os.umask(0o077)
 if len(sys.argv)==4 and sys.argv[2]=='--release' and sys.argv[3] in ('20261003-capabilities','20261004-yandex','20261004-full-api','20261004-etm-checkout'):
  B=R/('update-'+sys.argv[3]);sys.argv=sys.argv[:2]
 if sys.argv[1:]==['apply']:
  assert not B.exists(),'Update already recorded; inspect before retry'
  state=json.loads((H/'gateway_state.json').read_text());assert state['active_agents']==0
  sources={P/'automation_integrations/api_read.py':R/'release/api_read.py',P/'registry/catalog.json':R/'release/catalog.json',P/'automation_integrations/catalog.py':H/'plugins/automation-api-catalog/catalog.py'}
  sources.update({P/'automation_integrations'/n:R/'release'/n for n in ('api_write.py','yandex_contract.py','extended_api.py','confirmed_write.py','openapi_contract.py','documented_contract.py','wirenboard.py','wirenboard_http.py','wirenboard_control_contract.py','wirenboard_shell.py','wirenboard_control.py')})
  sources.update({P/'automation_integrations'/n:R/'release'/n for n in ('etm_authorization.py','etm_document.py','etm_order.py','etm_workflow.py')})
  sources.update({P/'automation_integrations'/n:R/'release'/n for n in ('media_api.py','media_runtime.py','media_files.py','fal_media.py','inference_media.py')})
  sources.update({P/'bridges/hermes_catalog'/n:H/'plugins/automation-api-catalog'/n for n in ['__init__.py','plugin.yaml']})
  sources.update({p:R/'release/capabilities'/p.name for p in (P/'registry/capabilities').glob('*.json')})
  sources.update({p:R/'release/contracts'/p.name for p in (P/'registry/contracts').glob('*.json')})
  # Dependencies first, runner next, discovery last. Pin source bytes once.
  priority=lambda pair: 3 if pair[1].name in ('catalog.json','__init__.py','plugin.yaml') else 2 if pair[1].name in ('api_read.py','api_write.py') else 1
  sources=dict(sorted(sources.items(), key=priority))
  pinned={source:source.read_bytes() for source in sources}
  B.mkdir(mode=0o700);entries=[]
  for i,(source,target) in enumerate(sources.items()):
   old=target.read_bytes() if target.exists() else None;new=pinned[source]
   if old is not None:(B/str(i)).write_bytes(old)
   entries.append({'target':str(target),'backup':str(i) if old is not None else None,'before':sha(old) if old is not None else None,'after':sha(new)})
  config_sha=sha((H/'config.yaml').read_bytes())
  (B/'manifest.json').write_text(json.dumps({'entries':entries,'config_sha':config_sha,'gateway_before':state},indent=2))
  for (source,target),entry in zip(sources.items(),entries):
   assert (sha(target.read_bytes()) if target.exists() else None)==entry['before'],'Concurrent file edit'
  for source,target in sources.items():
   target.parent.mkdir(mode=0o700,exist_ok=True);atomic(target,pinned[source])
  for entry in entries:assert sha(Path(entry['target']).read_bytes())==entry['after'],'Installed hash mismatch'
  assert sha((H/'config.yaml').read_bytes())==config_sha,'Config changed concurrently'
 elif sys.argv[1:]==['rollback']:
  manifest=json.loads((B/'manifest.json').read_text())
  for e in manifest['entries']:assert sha(Path(e['target']).read_bytes())==e['after'],'Later file changes; reconcile manually'
  for e in manifest['entries']:
   target=Path(e['target'])
   if e['backup'] is None:target.unlink()
   else:atomic(target,(B/e['backup']).read_bytes())
 else:raise SystemExit('Use apply or rollback')
 print('Catalog snapshots updated; config preserved. Idle gateway restart separately.')
if __name__=='__main__':main()
