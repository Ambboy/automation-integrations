"""Confirmed Yandex taxi writes. Durable drafts; no automatic mutation retries.

Only the native owner-private plugin supplies context/confirmation messages.
The local OS user already has vaultctl access; files are not an OS sandbox.
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
try:
 from .api_read import HTTP, Vault, Failure, atomic, sanitize
 from .yandex_contract import validate, SOURCES
except ImportError:
 from api_read import HTTP, Vault, Failure, atomic, sanitize
 from yandex_contract import validate, SOURCES

TERMINAL={'verified','rejected'}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def save(path,row):
 atomic(path,row)
 fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def identity(value):
 if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise Failure('invalid_draft_id')
 return value

def yandex_process(request,context,config,*,http=None,vault=None,clock=time.time):
 if not isinstance(request,dict) or not isinstance(context,dict):raise Failure('invalid_write_request')
 scope=context.get('scope');message=context.get('message_id')
 if (not isinstance(scope,list) or len(scope)!=4 or not all(isinstance(s,str) for s in scope)
     or not scope[0] or scope[0]!=scope[1] or not scope[2] or not isinstance(message,str) or not message):raise Failure('invalid_write_context')
 root=Path(config['state_dir'])/'yandex-writes';root.mkdir(mode=0o700,parents=True,exist_ok=True)
 action=request.get('action');allowed={'prepare':{'action','operation','params'},'execute':{'action','draft_id'},'status':{'action','draft_id'},'confirm':{'action','confirmation_text'}}
 if action not in allowed or set(request)-allowed[action]:raise Failure('invalid_write_request')
 if action=='confirm':
  text=request.get('confirmation_text','')
  if not isinstance(text,str) or not re.fullmatch(r'ПОДТВЕРЖДАЮ [a-f0-9-]{36}',text):raise Failure('exact_confirmation_required')
  ident=identity(text.split(' ')[1])
 elif action=='prepare':ident=str(uuid.uuid4())
 else:ident=identity(request.get('draft_id'))
 path=root/(ident+'.json')
 def auth():
  nonlocal http,vault
  vault=vault or Vault(config);secret=vault.get('yandex_go');http=http or HTTP('yandex_go',config)
  return {'Authorization':'Bearer '+secret['YANDEX_GO_BUSINESS_OAUTH_TOKEN'],'X-YaTaxi-Selected-Corp-Client-Id':config['yandex_client_id']}
 def read_order(order_id,headers):
  obj=http.call('GET','/orders/info',query={'order_id':order_id},headers=headers)
  if obj.get('id')!=order_id or not isinstance(obj.get('status'),str):raise Failure('object_verification_failed')
  return obj
 def view(row):
  out={k:row.get(k) for k in ('draft_id','operation','status','expires_at','preview','order_id','last_error','provider_code','verification','retry_after_seconds')}
  out.update(ok=True,mutation_verified=row['status']=='verified',source=SOURCES[row['operation']],production_write_verification='not_tested_by_deployment')
  if row['status'] in ('prepared','outcome_unknown'):
   out['confirmation_command']='ПОДТВЕРЖДАЮ '+ident
   out['instruction']='Show the complete preview, then ask the owner to send this exact command in a new private Telegram message. No boolean/model claim is approval.'
  return out
 # Serialize all workflow transitions of the exact draft. No credentials are fetched
 # for prepare validation, confirmation, denied execution, or cached final results.
 with (root/('prepare.lock' if action=='prepare' else ident+'.lock')).open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  if action=='prepare':
   operation=request.get('operation');params=request.get('params',{})
   if operation not in ('order_create','order_cancel'):raise Failure('unsupported_write_operation')
   try:validate(operation,params)
   except ValueError as e:raise Failure(str(e)) from None
   intent = digest({'operation':operation,'params':params})
   # A model retry must not escape an uncertain submit by inventing a NEW draft
   # (and hence a new provider idempotency token). Serialize prepare and reject
   # the same unresolved intent before any credential lookup or provider call.
   for candidate in root.glob('*.json'):
    with (root/(candidate.stem+'.lock')).open('a') as candidate_lock:
     fcntl.flock(candidate_lock,fcntl.LOCK_EX)
     old=json.loads(candidate.read_text())
     old_intent=old.get('intent_hash') or digest({'operation':old['operation'],
         'params':{k:v for k,v in old['payload'].items() if k not in ('offer','state')}})
     if old.get('scope')!=scope or old_intent!=intent or old.get('status') in TERMINAL:
      continue
     if old.get('expires_at',0)<clock() and 'submitted_at' not in old:
      continue
     return {'ok':False,'error':'existing_unresolved_draft','draft_id':old['draft_id'],
             'status':old['status'],'instruction':'Use status on this exact draft. Do not replace its idempotency token.'}
   headers=auth();payload=dict(params)
   if operation=='order_create':
    quote=http.call('POST','/orders/routestats',headers=headers,body={'user_id':params['user_id'],'route':[p['geopoint'] for p in params['route']]})
    levels=[x for x in quote.get('service_levels',[]) if x.get('class')==params['class']]
    if len(levels)!=1 or not isinstance(quote.get('offer'),str) or not quote['offer']:raise Failure('offer_unavailable')
    if not levels[0].get('is_fixed_price') or not levels[0].get('price'):raise Failure('fixed_price_offer_required')
    payload['offer']=quote['offer']
    preview={'action':'Создать немедленный заказ такси','user_id':params['user_id'],'route':params['route'],
             'class':params['class'],'price_as_returned':levels[0]['price'],'is_fixed_price':True,
             'tariff_conditions':levels[0].get('details_tariff',[]),'comment':params.get('comment'),
             'cost_center_values':params.get('cost_center_values',[]),'warning':'Дополнительные услуги/ожидание могут влиять на итоговую стоимость согласно условиям перевозчика.'}
   else:
    obj=read_order(params['order_id'],headers);rules=obj.get('cancel_rules',{})
    if rules.get('can_cancel') is not True or rules.get('state') not in ('free','paid','minimal'):raise Failure('order_not_cancellable')
    payload={'order_id':params['order_id'],'state':rules['state']}
    preview={'action':'Отменить точный заказ такси','order_id':params['order_id'],'status':obj['status'],
             'route':{k:obj.get(k) for k in ('source','destination')},'cancellation_rules':rules,
             'warning':'Отмена может быть платной; подтверждаются именно эти правила.'}
   row={'draft_id':ident,'operation':operation,'intent_hash':intent,'payload':payload,'payload_hash':digest(payload),
        'scope':scope,'created_message':message,'created_at':clock(),'expires_at':clock()+600,
        'status':'prepared','preview':sanitize(preview,vault.sensitive),'idempotency_token':ident}
   if operation=='order_cancel':row['rules_hash']=digest(rules);row['order_id']=params['order_id']
   save(path,row);return view(row)
  if not path.exists():raise Failure('draft_not_found')
  row=json.loads(path.read_text())
  if row['scope']!=scope:raise Failure('draft_scope_mismatch')
  if row['payload_hash']!=digest(row['payload']):raise Failure('draft_integrity_failed')
  if action=='confirm':
   # A recovery confirmation authorizes only reuse of the SAME create token.
   if row['status'] not in ('prepared','outcome_unknown') or (row['status']=='outcome_unknown' and row['operation']!='order_create'):raise Failure('draft_not_confirmable')
   if message in (row['created_message'],row.get('confirmed_message')):raise Failure('new_owner_message_required')
   if row['expires_at']<clock():raise Failure('draft_expired_prepare_again' if row['status']=='prepared' else 'uncertain_draft_requires_manual_reconciliation')
   row.update(approved_hash=row['payload_hash'],confirmed_message=message,status='confirmed');save(path,row);return view(row)
  if row['status']=='submitting':
   row['status']='outcome_unknown';row['last_error']='interrupted_submission';save(path,row)
  if action=='execute' and row['status'] in TERMINAL:return view(row)
  if action=='status':
   if row.get('order_id') and row['status'] in ('outcome_unknown','accepted_unverified'):
    headers=auth()
    try:
     obj=read_order(row['order_id'],headers)
     if row['operation']=='order_create' or obj['status']=='cancelled':row.update(status='verified',verification={'id_matches':True,'status':obj['status']},last_error=None)
     else:row['verification']={'id_matches':True,'status':obj['status'],'cancellation_confirmed':False}
    except Failure as e:row['last_error']=e.code
    save(path,row)
   return view(row)
  if row['status']!='confirmed' or row.get('approved_hash')!=row['payload_hash']:raise Failure('owner_confirmation_required')
  if row['expires_at']<clock():raise Failure('confirmation_expired')
  headers=auth();payload=row['payload']
  if row['operation']=='order_cancel':
   obj=read_order(payload['order_id'],headers)
   if digest(obj.get('cancel_rules',{}))!=row['rules_hash']:
    row.update(status='rejected',last_error='cancellation_conditions_changed_prepare_again');save(path,row)
    raise Failure('cancellation_conditions_changed_prepare_again')
  # The durable submitting record MUST reach disk before the mutation starts.
  row.update(status='submitting',submitted_at=clock());save(path,row)
  try:
   if row['operation']=='order_create':
    result=http.call('POST','/orders/create',headers={**headers,'X-Idempotency-Token':row['idempotency_token']},body=payload)
    order_id=result.get('order_id')
    if not isinstance(order_id,str) or not order_id:raise Failure('missing_created_order_id')
    row['order_id']=order_id
   else:
    result=http.call('POST','/orders/cancel',headers=headers,query={'order_id':payload['order_id']},body={'state':payload['state']})
   row['status']='accepted_unverified';save(path,row)
   obj=read_order(row['order_id'],headers)
   if row['operation']=='order_cancel' and obj['status']!='cancelled':raise Failure('cancellation_not_yet_verified')
   row.update(status='verified',verification={'id_matches':True,'status':obj['status']},last_error=None)
  except Failure as e:
   row['last_error']=e.code;row['provider_code']=e.provider_code;row['retry_after_seconds']=e.retry_after
   if row['status']=='submitting':row['status']='rejected' if e.status in (400,401,403,404,406,429) else 'outcome_unknown'
  except Exception:
   row['status']='outcome_unknown' if row['status']=='submitting' else 'accepted_unverified';row['last_error']='unexpected_execution_error'
  save(path,row);return view(row)

def process(request, context, config, *, http=None, vault=None, clock=time.time):
 if not isinstance(request, dict):raise Failure('invalid_write_request')
 action=request.get('action')
 if action=='prepare' and request.get('service') in ('fal','inference'):
  try:from .media_api import process as media_process
  except ImportError:from media_api import process as media_process
  return media_process(request,context,config,transport=http,vault=vault,clock=clock)
 if action in ('execute','status'):
  try:from .media_runtime import job_exists
  except ImportError:from media_runtime import job_exists
  if job_exists(Path(config['state_dir'])/'media',request.get('draft_id','')):
   try:from .media_api import process as media_process
   except ImportError:from media_api import process as media_process
   return media_process(request,context,config,transport=http,vault=vault,clock=clock)
 etm_checkout = action == 'prepare' and request.get('service') == 'etm' and request.get('operation') == 'order_checkout'
 if action != 'prepare':
  etm_ident = request.get('draft_id', '')
  if action == 'confirm':
   etm_text = request.get('confirmation_text', '')
   etm_ident = etm_text.split(' ')[-1] if isinstance(etm_text, str) else ''
  if isinstance(etm_ident, str) and re.fullmatch(r'[a-f0-9-]{36}', etm_ident):
   etm_checkout = (Path(config['state_dir']) / 'etm-writes' / (etm_ident + '.json')).exists()
 if etm_checkout:
  try:from .etm_workflow import process as etm_process
  except ImportError:from etm_workflow import process as etm_process
  return etm_process(request, context, config, clock=clock)
 wb=request.get('service')=='wirenboard' if action=='prepare' else False
 if action in ('confirm','execute','status'):
  wb_id=request.get('draft_id','')
  if action=='confirm':
   wb_text=request.get('confirmation_text','')
   wb_id=wb_text.split(' ')[-1] if isinstance(wb_text,str) else ''
  if isinstance(wb_id,str) and re.fullmatch(r'[a-f0-9-]{36}',wb_id):
   wb=(Path(config['state_dir'])/'wirenboard-writes'/(wb_id+'.json')).exists()
 if wb:
  try:from .wirenboard_control import process as wb_process
  except ImportError:from wirenboard_control import process as wb_process
  return wb_process(request,context,config,http=http,vault=vault,clock=clock)
 extended=False
 if action=='prepare':
  service=request.get('service','yandex_go')
  extended=service!='yandex_go' or request.get('operation') not in ('order_create','order_cancel')
 else:
  ident=request.get('draft_id','')
  if action=='confirm':
   text=request.get('confirmation_text','')
   ident=text.split(' ')[-1] if isinstance(text,str) else ''
  if isinstance(ident,str) and re.fullmatch(r'[a-f0-9-]{36}',ident):
   extended=(Path(config['state_dir'])/'contract-writes'/(ident+'.json')).exists()
 if extended:
  try:from .confirmed_write import process as confirmed
  except ImportError:from confirmed_write import process as confirmed
  return confirmed(request,context,config,http=http,vault=vault,clock=clock)
 request=dict(request)
 if action=='prepare':request.pop('service',None)
 return yandex_process(request,context,config,http=http,vault=vault,clock=clock)

def main():
 os.umask(0o077)
 try:
  raw=sys.stdin.read(32001)
  if len(raw)>32000:raise Failure('request_too_large')
  envelope=json.loads(raw);config=json.loads(Path(sys.argv[1]).read_text())
  result=process(envelope['request'],envelope['context'],config)
 except Failure as e:result={'ok':False,'error':e.code,'http_status':e.status,'provider_code':e.provider_code,'retry_after_seconds':e.retry_after}
 except Exception:result={'ok':False,'error':'invalid_or_failed_write_request'}
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
