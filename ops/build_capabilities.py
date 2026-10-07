"""Build secret-free inventories from downloaded official provider documents.

Input is a private research directory; output only descriptions/schema metadata.
No API calls and no credentials. Saby scope is its published EDO command index
(including linked employee directory), not every separately licensed Saby product.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import yaml
from html.parser import HTMLParser

class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ('script','style'):self.skip+=1
 def handle_endtag(self,t):
  if t in ('script','style'):self.skip-=1
 def handle_data(self,s):
  if not self.skip:self.parts.append(s)

MAPS={
'yandex_go':{'auth-list':'auth_list','user-list':'users','order-active':'active_orders','order-info':'order_info','travels-list':'travels','order-list':'orders','department-list':'departments','cost-center-list':'cost_centers','role-list':'roles'},
'etm':{'POST /user/login':'login_check','GET /catalog':'search','GET /goods/{id}':'goods','GET /goods/{id}/price':'price','GET /goods/{id}/remains':'remains'},
'tochka':{'GET /open-banking/v1.0/accounts':'accounts','GET /open-banking/v1.0/balances':'balances','GET /open-banking/v1.0/statements':'statements','GET /open-banking/v1.0/accounts/{accountId}/statements/{statementId}':'statement'},
'saby':{'СБИС.СписокДокументов':'documents','СБИС.ПрочитатьДокумент':'document','СБИС.ИнформацияОВерсии':'version','СБИС.СписокНашихОрганизаций':'organizations'}}
MAPS['etm'].update({'GET /invoice':'invoices','GET /invoice/{id}/body':'invoice','GET /info/search/{type}/':'manufacturers'})
MAPS['yandex_go'].update({'routestats':'routestats','zone-info':'zone_info','order-create':'order_create','order-cancel':'order_cancel'})
MAPS['tochka'].update({'GET '+p:o for p,o in {
 '/open-banking/v1.0/customers':'customers', '/consent/v1.0/consents':'consents',
 '/open-banking/v1.0/accounts/{accountId}':'account', '/open-banking/v1.0/accounts/{accountId}/balances':'account_balances',
 '/open-banking/v1.0/accounts/{accountId}/authorized-card-transactions':'card_holds',
 '/acquiring/v1.0/retailers':'acquiring_retailers','/acquiring/v1.0/payments':'acquiring_payments',
 '/acquiring/v1.0/subscriptions':'subscriptions','/payment/v1.0/for-sign':'payments_for_sign','/sbp/v1.0/get-sbp-payments':'sbp_payments'}.items()})

def main():
 ap=argparse.ArgumentParser();ap.add_argument('research',type=Path);ap.add_argument('--output',type=Path,default=Path('registry/capabilities'));a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 def save(service,items,sources,scope):
  for row in items:
   adapter=MAPS[service].get(row['id']);row['adapter']=adapter
   row['execution']=('integration_write' if service=='yandex_go' and adapter in ('order_create','order_cancel')
                     else 'integration_read' if adapter else 'not_implemented')
   row['access']='unverified';row['live_check']={'status':'not_tested','reason':'Business effects are not tested' if row['effect'] not in ('read','authentication') else 'No live adapter probe yet'}
  doc={'schema_version':1,'service':service,'retrieved_at':'2026-10-03','scope':scope,'sources':sources,'total':len(items),'capabilities':items}
  (a.output/(service+'.json')).write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n');print(service,len(items))
 def source(file,url):return {'url':url,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
 for service,file,url in [('etm','etm.yaml','https://ipro.etm.ru/ns2000/yaml/cli.yaml'),('tochka','tochka-openapi.json','https://enter.tochka.com/doc/openapi/swagger.json')]:
  f=a.research/file;spec=yaml.safe_load(f.read_text());items=[]
  def resolve(value,seen=()):
   if isinstance(value,list):return [resolve(x,seen) for x in value]
   if not isinstance(value,dict):return value
   ref=value.get('$ref')
   if ref and ref not in seen:
    fn,ptr=ref.split('#',1);doc=yaml.safe_load((a.research/fn).read_text()) if fn else spec
    for key in ptr.strip('/').split('/'):doc=doc[key.replace('~1','/').replace('~0','~')]
    return resolve(doc,seen+(ref,))
   if ref:return {'$ref':ref}
   return {k:resolve(v,seen) for k,v in value.items()}
  for route,entries in spec['paths'].items():
   for method,op in entries.items():
    if method not in ('get','post','put','patch','delete'):continue
    ident=method.upper()+' '+route
    effect='read' if method=='get' else 'business_write'
    if service=='etm' and route=='/user/login':effect='authentication'
    if '/print/' in route or service=='tochka' and route.endswith('/statements') and method=='post':effect='report_generation'
    items.append({'id':ident,'method':method.upper(),'path':route,'summary':op.get('summary',op.get('operationId',ident)),
     'category':op.get('tags',[]),'effect':effect,'parameters':resolve(entries.get('parameters',[])+op.get('parameters',[])),
     'request_body':resolve(op.get('requestBody',{})), 'security':op.get('security',spec.get('security',[])),
     'response_codes':list(op.get('responses',{})), 'source':url,'provider_version':spec['info']['version']})
  sources=[source(f,url)]
  if service=='etm':sources += [source(a.research/n,'https://ipro.etm.ru/ns2000/yaml/'+n) for n in ['components.yaml','goods.yaml','invoice.yaml']]
  save(service,items,sources,'All operations in the official published OpenAPI snapshot; documented availability does not establish account permissions.')
 items=[];sources=[]
 for f in sorted((a.research/'yandex').glob('*.md')):
  s=f.read_text();m=re.search(r'(GET|POST|PUT|PATCH|DELETE) https?://b2b-api.go.yandex.ru([^\s?]+)',s)
  if not m:continue # roles is an explanatory table, not an endpoint
  method,path=m.groups();src='https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/'+f.stem
  effect='read' if method=='GET' or f.stem in ('travels-list','food-list','user-phone','users-spending-details','routestats') else 'business_write'
  if f.stem=='taxi-report':effect='report_generation'
  title=re.search(r'^# (.+)',s,re.M).group(1)
  # Parameters are metadata names, not wholesale copies of documentation.
  req=s.split('## Описание полей ответа')[0].split('## Описание ответа')[0]
  names=sorted(set(re.findall(r'(?:^|\n)- `([^`]+)`',req)))
  items.append({'id':f.stem,'method':method,'path':path,'summary':title,'effect':effect,'parameters':[{'name':n,'details':'See official source for requiredness/type'} for n in names], 'source':src})
  sources.append(source(f,src+'.md'))
 save('yandex_go',items,sources,'All endpoint pages linked from API 2.0 request index; roles explanatory page excluded. TLS verified through taxi-business-api.docs-viewer.yandex.ru with canonical Host header. Always use HTTPS for API calls.')
 methods=json.loads((a.research/'saby-methods.json').read_text());items=[];sources=[]
 for ident,info in sorted(methods.items()):
  f=a.research/'saby-methods'/(ident+'.html')
  effect='read' if re.match(r'СБИС\.(Список|Прочитать|Информация)|sabyMchd.Get',ident) else 'business_write'
  if any(x in ident for x in ['Аутентифицировать','Выход','ПодтвердитьВход','ОтправитьКод','ПереключитьАккаунт']):effect='authentication'
  names=[];endpoint=None
  if f.exists():
   parser=Text();parser.feed(f.read_text());text=' '.join(parser.parts)
   section=text.split('Параметры запроса',1)[-1].split('Результат',1)[0] if 'Параметры запроса' in text else ''
   names=sorted(set(re.findall(r'"\s*([^"\n]{1,65}?)\s*"\s*:',section)))
   found=re.search(r'Адрес запроса\s*:\s*(https://[^\s]+)',text)
   if found:endpoint=found.group(1)
  items.append({'id':ident,'method':'JSON-RPC','path':endpoint,'summary':ident.split('.',1)[1],'category':info['category'],'effect':effect,'source':info['source'],'documentation_downloaded':f.exists(),'parameters':[{'name':n,'details':'Field at any nesting level; consult official contract'} for n in names],'parameter_note':'Consult linked method contract for types/nesting/requiredness before implementing; generic JSON-RPC execution is intentionally unavailable.'})
  if f.exists():sources.append(source(f,info['source']))
 save('saby',items,sources,'Published Saby EDO command index and linked employee directory, including authentication, documents, counterparties, organizations and powers of attorney. Separate product APIs/licenses are not implied by EDO credentials.')
if __name__=='__main__':main()
