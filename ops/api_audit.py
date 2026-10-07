# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Read-only audit; raw business data/IDs remain in memory, receipts contain only shapes."""
import datetime as dt
import json
from pathlib import Path
from automation_integrations.api_read import execute, Failure, atomic
ROOT=Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')

def main():
 config=json.loads((ROOT/'private.json').read_text());report=[]; results={}
 def run(s,o,p=None):
  row={'service':s,'operation':o,'checked_at':dt.datetime.now(dt.timezone.utc).isoformat()}
  try:
   value=execute({'service':s,'operation':o,'params':p or {}},config)['data'];results[s,o]=value
   row.update(ok=True,keys=list(value)[:20] if isinstance(value,dict) else [],count=len(value) if isinstance(value,list) else None)
  except Failure as e:row.update(ok=False,error=e.code,http_status=e.status)
  except Exception as e:row.update(ok=False,error=type(e).__name__)
  report.append(row);atomic(ROOT/'state'/f'{s}.{o}.json',row);atomic(ROOT/'audit.json',report);print(json.dumps(row,ensure_ascii=False),flush=True)
  return results.get((s,o))
 for s,ops in {'yandex_go':['auth_list','users','orders','departments','cost_centers','roles','travels'],
               'etm':['login_check','search','goods','price','remains','manufacturers','invoices'],
               'saby':['version','organizations','documents'],
               'tochka':['accounts','balances','statements','customers','consents']}.items():
  for o in ops:
   p={'limit':1} if o in ['users','orders','travels','statements'] else {'page_size':1} if o=='documents' else {'query':'5301409'} if o=='search' else {'id':'5301409'} if s=='etm' and o in ['goods','price','remains'] else {}
   if o=='manufacturers':p={'query':'IEK','limit':1}
   if o=='invoices':
    today=dt.date.today();p={'date_from':(today-dt.timedelta(days=30)).isoformat(),'date_to':today.isoformat(),'limit':1}
   run(s,o,p)
 users=results.get(('yandex_go','users'),{}).get('items',[])
 if users:run('yandex_go','active_orders',{'user_id':users[0]['id']})
 orders=results.get(('yandex_go','orders'),{}).get('items',[])
 if orders:run('yandex_go','order_info',{'order_id':orders[0]['id']})
 docs=results.get(('saby','documents'),{}).get('Документ',[])
 if docs:run('saby','document',{'id':docs[0]['Идентификатор']})
 statements=results.get(('tochka','statements'),{}).get('Data',{}).get('Statement',[])
 if statements:
  st=statements[0]
  if 'accountId' in st and 'statementId' in st:run('tochka','statement',{'account_id':st['accountId'],'statement_id':st['statementId']})
  else:print('statement fixture keys:',list(st))
 invoices=results.get(('etm','invoices'),{}).get('data',{}).get('rows',[])
 if invoices:run('etm','invoice',{'id':str(invoices[0]['id'])})
 accounts=results.get(('tochka','accounts'),{}).get('Data',{}).get('Account',[])
 if accounts:
  for o in ['account','account_balances','card_holds']:run('tochka',o,{'account_id':accounts[0]['accountId']})
 customers=results.get(('tochka','customers'),{}).get('Data',{}).get('Customer',[])
 if customers:
  for o in ['acquiring_retailers','acquiring_payments','subscriptions','payments_for_sign','sbp_payments']:
   run('tochka',o,{'customer_code':customers[0]['customerCode']})
 # Missing fixtures are recorded explicitly, never replaced by invented IDs.
 from automation_integrations.api_read import OPERATIONS
 attempted={(r['service'],r['operation']) for r in report}
 for s,ops in OPERATIONS.items():
  for o in ops:
   if (s,o) not in attempted:report.append({'service':s,'operation':o,'status':'not_tested','reason':'Required fixture unavailable'})
 atomic(ROOT/'audit.json',report)
if __name__=='__main__':main()
