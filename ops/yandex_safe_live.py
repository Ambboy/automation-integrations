# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Explicit read-only production probes. No writes/booking/cancellation."""
import datetime as dt
import json
from pathlib import Path
from automation_integrations.api_read import execute,Failure,atomic
R=Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
def main():
 c=json.loads((R/'private.json').read_text());rows=[]
 def run(o,p=None):
  row={'service':'yandex_go','operation':o,'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'business_write':False}
  try:
   data=execute({'service':'yandex_go','operation':o,'params':p or {}},c)['data']
   row.update(ok=True,keys=list(data)[:20])
   if o=='routestats':row.update(tariff_count=len(data.get('service_levels',[])),offer_present=bool(data.get('offer')))
  except Failure as e:row.update(ok=False,error=e.code,http_status=e.status);data=None
  rows.append(row);atomic(R/'state'/('yandex_go.'+o+'.json'),row);atomic(R/'yandex-safe-live-20261004.json',rows);print(json.dumps(row),flush=True);return data
 users=run('users',{'limit':1});run('auth_list');orders=run('orders',{'limit':1})
 for op in ('travels','departments','cost_centers','roles'):run(op,{'limit':1} if op=='travels' else {})
 if users and users.get('items'):run('active_orders',{'user_id':users['items'][0]['id']})
 if orders and orders.get('items'):run('order_info',{'order_id':orders['items'][0]['id']})
 # Public documentation sample coordinates, not the user's unspecified flight origin.
 route=[[37.593983,55.738759],[37.609479,55.746943]]
 run('zone_info',{'lon':route[0][0],'lat':route[0][1]})
 p={'route':route}
 if users and users.get('items'):p['user_id']=users['items'][0]['id']
 run('routestats',p)
if __name__=='__main__':main()
