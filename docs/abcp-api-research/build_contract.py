"""Compile the pinned official prose snapshots into the connector's contract.

Build-time dependency: beautifulsoup4. Runtime consumes only JSON. Unknown types
and conditional requirements stay explicit prose, rather than guessed constraints.
"""
from pathlib import Path
from bs4 import BeautifulSoup, Tag
import re, json, csv, collections, copy
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
AUTH_FIELDS = {'userlogin','userpsw','siteHash','accessHash','sitelogin','sitepsw'}
FAMILY_PATHS = {'abcp-client':'api/abcp1/api-abcp-client','abcp1-admin':'api/abcp1/api-abcp-admin','ts-client':'api/abcp2/api-ts-client','ts-admin':'api/abcp2/api-ts-admin','vinqu':'vinqu/apivinqu','carcare':'carcare/carcaremodule/api'}
SOURCES={f:'https://www.abcp.ru/d/docs/'+p for f,p in FAMILY_PATHS.items()}

def norm(x):return re.sub(r'\s+', ' ', x.replace('\u200b','')).strip()
def text(x):return norm(x.get_text(' ',strip=True))

def split_archive(rows):
 out=[]
 for r in rows:
  if r['path']!='/cp/orders/statusHistory':out.append(r);continue
  soup=BeautifulSoup(r['html'],'html.parser');nodes=list(soup.children)
  starts=[i for i,n in enumerate(nodes) if isinstance(n,Tag) and n.name=='p' and 'Операция:' in text(n)]
  for j,start in enumerate(starts):
   end=starts[j+1]-2 if j+1<len(starts) else len(nodes)
   sub=BeautifulSoup(''.join(str(n) for n in nodes[start:end]),'html.parser')
   rr=copy.deepcopy(r);rr['html']=str(sub);rr['text']=text(sub)
   if j:
    rr['method']='POST';rr['path']='/cp/orders/'+('fromArchive' if j==1 else 'toArchive');rr['title']='Достать заказ из архива' if j==1 else 'Вернуть заказ в архив'
   out.append(rr)
 return out

def table_rows(tab):
 rows=tab.find_all('tr'); cells=[text(x) for x in rows[0].find_all(['td','th'])]
 header=cells if cells and (cells[0].lower() in ('параметр','параметры запроса','поле','название','значение','объект','код','код ошибки')) else []
 if header and header[0]=='Параметры запроса':header=['Параметр','Описание','Комментарий']
 result=[]
 for tr in rows[1:] if header else rows:
  cells=[text(x) for x in tr.find_all(['td','th'],recursive=False)]
  if len(cells)<2:continue
  raw=cells[0]; typ=cells[header.index('Тип')] if 'Тип' in header else ''
  desc=cells[header.index('Описание')] if 'Описание' in header else cells[-1]
  obligatory=cells[header.index('Обязательность')] if 'Обязательность' in header else ''
  result.append({'name':raw,'type':typ,'description':desc,'required_text':obligatory,'cells':cells})
 return {'headers':header,'rows':result}

def req(row):
 d=(row['description']+' '+row['required_text']).lower()
 conditional=any(s in d for s in ('если','необязательн','не обязательн','этап','при включ','при смене','в случае','для способ','для самовывоз','для доставки'))
 # "Признак обязательности" describes a boolean field; it is not a required marker.
 mandatory=re.search(r'\bобязательн(?:ый|ая|ое|ые|о)\b',d)
 return not conditional and ('*' in row['name'] or bool(mandatory) or row['required_text'].lower() in ('да','yes','true','+'))

def names(row):
 raw=row['name'].replace('*','').strip()
 if raw=='с1':return ['c1']  # Cyrillic typo in table; request examples use ASCII c1.
 raw=re.sub(r'\s+\[устарел.*','',raw)
 if '[1...7]' in raw:return [raw.replace('[1...7]',str(i)) for i in range(1,8)]
 return [x.strip() for x in raw.split(',')]

def type_schema(row, name):
 t=row['type'].lower().strip(); d=row['description'].lower()
 result={'description':row['description']}
 if t:result['x-provider-type']=row['type']
 scalar={}
 if t in ('uint','uint8','uint16','uint32','uint64','int','int32','int64','integer'):scalar={'type':'integer'}
 elif t in ('float','float64','float32','decimal','number'):scalar={'type':'number'}
 elif t in ('string','datetime','rfc3339'):scalar={'type':'string'}
 elif t in ('bool','boolean'):scalar={'anyOf':[{'type':'boolean'},{'type':'integer','enum':[0,1]}]}
 elif t=='object':scalar={'type':'object','additionalProperties':True}
 elif t.startswith('[]') or t.endswith('[]'):scalar={'type':'array','items':{}}
 elif 'массив' in d or d.startswith('список '):scalar={'type':'array','items':{}}
 elif d.startswith('объект') or d.startswith('данные для создания'):scalar={'type':'object','additionalProperties':True}
 # PHP uses the term "массив" for associative maps too; examples determine maps below.
 if 'через запятую' in d:
  scalar={'anyOf':[{'type':'string'},{'type':'array','items':{}}]}
 if re.search(r'(^|[\s(])один или|одного.*или|либо.*массив|массив.*или.*строк',d):scalar={}
 if not t and 'булев' in d:scalar={}
 result.update(scalar)
 return result

def add_property(schema,name,child,required=False):
 # Bracket paths are represented as nested objects/arrays in the tool's flat
 # params dict. The transport emits PHP brackets; names themselves stay trusted.
 parts=[p for p in re.split(r'\[([^]]*)\]',name) if p!='' and p is not None]
 # re.split loses [] indexes; tokenize explicitly instead.
 m=re.match(r'^([^[]+)',name)
 if not m:return
 root=m.group(1); brackets=re.findall(r'\[([^]]*)\]',name)
 tokens=[root]+brackets
 current=schema
 for i,token in enumerate(tokens):
  if token=='':
   current['type']='array';current.pop('properties',None);current.pop('additionalProperties',None)
   if i==len(tokens)-1:current['items']=child;return
   current=current.setdefault('items',{'type':'object','properties':{},'additionalProperties':True});continue
  if token=='1...7':
   current['type']='object';current['additionalProperties']=child;return
  current['type']='object';current.setdefault('properties',{});current.setdefault('additionalProperties',True)
  if i==len(tokens)-1:
   old=current['properties'].get(token,{})
   if old.get('properties') and not child.get('properties'):old.update({k:v for k,v in child.items() if k!='type'})
   else:current['properties'][token]=child
   if required and len(tokens)==1:current.setdefault('required',[]).append(token)
  else:
   existing=current['properties'].setdefault(token,{'type':'object','properties':{},'additionalProperties':True})
   existing.pop('anyOf',None);current=existing


def endpoint_id(r):
 p=re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',r['path']).lower()
 return re.sub(r'[^a-z0-9]+','_',r['family']+'_'+r['method'].lower()+'_'+p).strip('_')


def apply_reviewed_bounds(operation):
 """Reviewed limits and requirements; no guessed default page sizes."""
 schema=operation['parameters']; path=operation['path']; method=operation['method']
 # Repair older generated contracts as well as applying numeric limits. These
 # phrases describe business flags or conditional TS1 requirements, not fields
 # every request must supply; req() applies the same rule to fresh builds.
 optional={('/cp/ts/legalPersons/list','GET'):'agreementWithIndividualsRequired',
           ('/cp/ts/delivery/update','POST'):'isWeightRequired',
           ('/cp/ts/orderPickings/changeStatus','POST'):'positionsStatusId'}.get((path,method))
 if optional in schema.get('required',[]):
  schema['required'].remove(optional)
  if not schema['required']:schema.pop('required')
  operation['required_fields']=schema.get('required',[])
 def update(tokens, **bounds):
  node=schema
  for token in tokens.split('.'):
   node=node['items'] if token=='items' else node['properties'][token]
  node.update(bounds)
 def unsigned(node):
  if isinstance(node,dict):
   provider_type=node.get('x-provider-type','').lower()
   if node.get('type')=='integer' and provider_type.startswith('uint'):
    node['minimum']=0
   if provider_type in ('[]uint','uint[]','[]string','string[]'):
    candidates=[node]+node.get('anyOf',[])
    for candidate in candidates:
     if candidate.get('type')=='array':
      candidate.setdefault('items',{}).update({'type':'integer','minimum':0} if 'uint' in provider_type else {'type':'string'})
   for value in node.values():unsigned(value)
  elif isinstance(node,list):
   for value in node:unsigned(value)
 unsigned(schema)
 if method=='GET' and path in (
     '/ts/goodReceipts/get','/ts/goodReceipts/getPositions',
     '/ts/orderPickings/get','/ts/orderPickings/getGoods',
     '/ts/customerComplaints/get','/ts/customerComplaints/getPositions',
     '/cp/ts/orderPickings/get','/cp/ts/orderPickings/getGoods',
     '/cp/ts/orderPickings/markCodes/list','/cp/ts/goodReceipts/get',
     '/cp/ts/goodReceipts/getPositions','/cp/ts/stockRemoval/list',
     '/cp/ts/stockRemoval/getPositions','/cp/ts/logs/read','/cp/productCards/search'):
  update('limit',type='integer',maximum=1000)
 if method=='GET' and path=='/orders':update('limit',type='integer',minimum=1,maximum=1000)
 if method=='GET' and path=='/cp/users/profiles':update('limit',type='integer',minimum=1,maximum=100)
 if method=='GET' and path=='/cp/ts/legalPersons/list':update('limit',maximum=50)
 if method=='POST' and path=='/search/batch':update('search',type='array',items={},maxItems=100)
 if method=='POST' and path=='/cp/articles/info/batch':update('articles',maxItems=100)
 if method=='POST' and path=='/cp/distributors/notes':update('note',maxItems=2000)
 if method=='GET' and path=='/cp/onlinePayments':
  for key in ('customerIds','orderIds'):update('filter.'+key,maxItems=100)
 if method=='POST' and path=='/cp/user':update('office',minItems=1)
 if method=='POST' and path=='/cp/finance/payments':update('payments.items.paymentNumber',type='string',maxLength=64)
 if method=='GET' and path=='/cp/users':update('organizationName',type='string',minLength=4)
 if method=='GET' and path=='/cp/users':update('marketType',type='integer',minimum=1,maximum=2)
 if method=='POST' and path=='/user/new':update('business',type='integer',minimum=1,maximum=3)
 if method=='GET' and path=='/ts/goodReceipts/getPositions':update('auto',type='string',minLength=3)
 if method=='POST' and path=='/cp/route':update('descriptionOfDeliveryProbability',type='string',maxLength=3000)
 if method=='POST' and path=='/cp/ts/orderPickings/fastGetOut':update('positions.items.externalId',type='string',maxLength=15)

rows=split_archive(json.loads((HERE/'sections.json').read_text()))
operations={}; details={}; notes=[]
for r in rows:
 soup=BeautifulSoup(r['html'],'html.parser');tables=soup.find_all('table')
 parsed=[table_rows(t) for t in tables]
 main=parsed[0]['rows'] if parsed else []
 schema={'type':'object','properties':{},'additionalProperties':False}
 auth='vinqu' if r['family']=='vinqu' else 'carcare' if r['family']=='carcare' else 'abcp'
 auth_fields=[x for x in AUTH_FIELDS if any(x in names(z) for z in main)]
 serialization={}; parameter_rows=[]
 for row in main:
  for name in names(row):
   if name in AUTH_FIELDS:continue
   if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_\[\].]*$',name):
    notes.append({'operation':endpoint_id(r),'issue':'unparsed_parameter_name','parameter':name});continue
   child=type_schema(row,name)
   if 'через запятую' in row['description'].lower():serialization[name.replace('[]','')]='csv'
   add_property(schema,name,child,req(row))
   parameter_rows.append(row)
 # Reviewed continuation tables: VINQU has additional top-level parameters;
 # TS log filters use additional flat parameters for each event type.
 continuation=[]
 if r['path']=='/vinquery/add':continuation=[parsed[2]['rows']]
 if r['path']=='/cp/ts/logs/read':continuation=[x['rows'] for x in parsed[1:16]]
 for extra in continuation:
  for row in extra:
   for name in names(row):
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name):
     add_property(schema,name,type_schema(row,name),False);parameter_rows.append(row)
 # Examples document parameters sometimes omitted from tables. Only form/query
 # assignments are considered; response JSON does not invent request fields.
 examples=[p.get_text() for p in soup.find_all('pre')]
 for example in examples:
  if '=' not in example:continue
  for m in re.finditer(r'(?:^|[?&\s])([a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]\s]*\])*)=',example):
   name=m.group(1);root=name.split('[')[0]
   if root in AUTH_FIELDS:continue
   if root not in schema['properties']:
    schema['properties'][root]={'description':'Параметр приведён в официальном примере запроса; тип и обязательность не уточнены.','x-source':'request_example'}
   if '[' in name and not name[len(root)+1:].startswith(']'):
    bracket=re.findall(r'\[([^]]*)\]',name)
    if bracket and bracket[0] and not bracket[0].isdigit():
     sc=schema['properties'][root]
     if sc.get('type')=='array':sc.pop('items',None);sc['type']='object';sc['additionalProperties']=True
 # Every path placeholder is an explicit trusted path parameter.
 path_parameters=re.findall(r'\{([^}]+)\}',r['path'])
 for name in path_parameters:
  schema['properties'].setdefault(name,{'anyOf':[{'type':'integer'},{'type':'string'}],'description':'Идентификатор из пути операции.'})
  schema.setdefault('required',[]).append(name)
 # Attach nested table schemas when the preceding caption names an existing
 # request field and clearly says this is a request node rather than a response.
 for index,(tab,part) in enumerate(zip(tables[1:],parsed[1:]),1):
  preceding=[]
  for n in tab.previous_siblings:
   if isinstance(n,Tag) and n.name=='table':break
   if isinstance(n,Tag):preceding.insert(0,text(n))
  caption=' '.join(preceding)
  request_key=None
  for key in schema['properties']:
   if re.search(r'(?:Узел|Объект|Массив)\s+[\"`]?'+re.escape(key)+r'(?!\w)',caption):request_key=key;break
  if r['path'] in ('/cp/onlinePayments','/reservation') and index==1:request_key='filter'
  if r['path']=='/cp/finance/payments' and r['method']=='POST' and index==1:request_key='payments'
  if r['path']=='/cp/ts/supplierReturns/positions/attr/create' and index==1:request_key='attr'
  if r['path']=='/vinquery/add' and index in (1,3):request_key='carInfo' if index==1 else 'guestInfo'
  if request_key and part['headers'] and part['headers'][0] in ('Параметр','Поле') and 'ответ' not in caption.lower() and 'Пример запроса' not in caption:
   child={'type':'object','properties':{},'additionalProperties':True}
   for row in part['rows']:
    for name in names(row):
     if re.match(r'^[a-zA-Z_][a-zA-Z0-9_\[\].]*$',name):add_property(child,name,type_schema(row,name),False)
   old=schema['properties'][request_key]
   if old.get('type')=='array':old['items']=child
   else:
    old.update(child)
   if request_key=='filter':old.update(child)
 # RFC3339 fields and table scalars must never receive response objects.
 if r['path']=='/cp/ts/delivery/createByPos' and len(parsed)>2:
  meet={'type':'object','properties':{},'additionalProperties':True}
  for row in parsed[2]['rows']:
   for name in names(row):add_property(meet,name,type_schema(row,name),False)
  schema['properties']['delivery'].setdefault('properties',{})['meetData']=meet
 # Account-role requirements are sometimes stated outside parameter tables.
 if 'API-администратора' in r['text'] and re.search(r'передавать параметр userId',r['text']):
  schema['properties']['userId']={'description':'Идентификатор клиента; обязателен при вызове от API-администратора.','x-source':'request_prose'}
 # Conditional alternatives must not become unconditional requirements.
 if r['path']=='/user/garage/add':
  schema['required']=[k for k in schema.get('required',[]) if k not in ('name','vin','frame')]
  schema['anyOf']=[{'required':['name']},{'required':['vin']},{'required':['frame']}]
 if r['path']=='/user/restore':
  schema.pop('required',None);schema['anyOf']=[{'required':['emailOrMobile']},{'required':['passwordNew','code']}]
 if '/cart/' in r['path'] and 'guestId' in schema['properties'] and 'clientId' in schema.get('required',[]):
  schema['required'].remove('clientId');schema['anyOf']=[{'required':['clientId']},{'required':['guestId']}]
 if r['path']=='/cp/catalog/search':schema['properties']['properties']={'type':'object','additionalProperties':True,'description':'Ключи criterias из cp/catalog/info; значения — массивы выбранных фильтров.'}
 for key in ('orderPickingResellerData','resellerData'):
  if key in schema['properties']:schema['properties'][key]={'type':'string','description':schema['properties'][key].get('description',''),'contentMediaType':'application/json'}
 if 'required' in schema:
  schema['required']=sorted(set(schema['required']))
  if not schema['required']:schema.pop('required')
 method=r['method'];path=r['path']
 read_posts={'/search/batch','/advices/batch','/cp/catalog/search','/cp/articles/info/batch','/ts/supplierOrders/orders/list','/ts/supplierOrders/positions/list','/cp/ts/supplierOrders/orders/list','/cp/ts/supplierOrders/positions/list'}
 effect='read' if method=='GET' or path in read_posts else 'business_write'
 if path in ('/cp/payment/token','/cp/payment/top-balance-link'):effect='business_write'
 encoding='json' if path=='/advices/batch' else 'multipart' if 'multipart/form-data' in r['text'] or path=='/vinquery/add' else 'form'
 auth_location='query' if method=='GET' or path in ('/cp/usercatalogs/{catalogId}/upload','/cp/productCards/import') else 'body'
 if path in ('/user/new','/user/restore'):auth_location='none'
 file_fields=[name for name in schema['properties'] if name in ('uploadFile','file','imagesArchive') and encoding=='multipart']
 for name in file_fields:schema['properties'][name]={'type':'object','properties':{'filename':{'type':'string','minLength':1},'content_base64':{'type':'string','contentEncoding':'base64'},'content_type':{'type':'string'}},'required':['filename','content_base64'],'additionalProperties':False,'description':schema['properties'][name].get('description',''),'x-file-upload':True}
 risk=[]
 if effect=='business_write':
  risk.append('changes_remote_state')
  if re.search('finance|payment|fastGetOut',path,re.I):risk.append('financial')
  if re.search('delete|clear|cancel|refuse|stockRemoval|toArchive',path,re.I) or path=='/cp/user/shipmentAddressZones':risk.append('destructive_or_cancel')
  if re.search('goodReceipts|orderPickings|stockRemoval|complaint|supplierReturns',path,re.I):risk.append('inventory_or_returns')
  if re.search('vinquery/(add|addComment|on)|user/restore|orders/online',path):risk.append('external_side_effect')
  if method=='GET':risk.append('get_with_side_effect')
 doc_url=SOURCES[r['family']]+'#'+r['anchor']
 ident=endpoint_id(r)
 if ident in operations:raise ValueError('duplicate '+ident)
 operation={'id':f"{r['family']} {method} {path}",'family':r['family'],'method':method,'path':path,'effect':effect,'encoding':encoding,'auth':auth,'auth_location':auth_location,'auth_fields':sorted(auth_fields),'auth_required':bool(auth_fields),'account_role':'api_administrator' if r['family'] in ('abcp1-admin','ts-admin') else 'site' if auth=='carcare' else 'vinqu_integration' if auth=='vinqu' else 'customer_or_supplier','summary':r['title'],'parameters':schema,'source':doc_url,'documentation':r['text'],'required_fields':schema.get('required',[]),'path_parameters':path_parameters,'parameter_serialization':serialization,'file_fields':file_fields,'risk':risk,'response_kind':'binary_or_json' if path=='/cp/productCards/export/file' else 'empty_or_json' if any(z in r['text'].lower() for z in ('не содержит данн','пустой ответ','не возвращает данн','ничего не возвращает','без содержимого')) else 'json','live_verified':False,'validation':'official_prose_reviewed_offline','unsupported_reason':None}
 if auth=='abcp' and not auth_fields and path not in ('/user/new','/user/restore'):
  operation['auth_fields']=['userlogin','userpsw'];operation['auth_required']=True
 if path=='/brands/get' and auth=='vinqu':
  operation['auth_field_map']={'siteHash':'hash'};operation['auth_fields']=['hash','accessHash'];schema['properties'].pop('hash',None)
  if 'hash' in schema.get('required',[]):schema['required'].remove('hash')
 if path=='/vinquery/add':operation['encoding_options']=['form','multipart']
 if path in ('/cp/orders/fromArchive','/cp/orders/toArchive'):operation['response_kind']='empty_or_json'
 if path=='/cp/orders/online' and method=='POST':operation['response_semantics']={'orders_path':'$[]','item_success_path':'$[].positions[].confirmSend','false_may_have_committed':True,'retry_after_error':'Never automatically; reconcile with supplier first.','success_value':True}
 if path in ('/basket/order','/orders/instant'):operation['response_semantics']={'success_path':'$.status','success_value':1,'created_objects_path':'$.orders','partial_commit_on_failure':True,'retry_after_error':'Inspect orders and reconcile before retry.'}
 if path=='/basket/add':operation['response_semantics']={'success_path':'$.status','success_value':1,'item_success_path':'$.positions[].status','partial_commit_on_failure':True}
 if path=='/cp/distributors/notes' and method=='POST':operation['response_semantics']={'atomic_on_error':True,'max_notes':2000}
 if path=='/vinquery/chatList':operation['response_semantics']={'empty_response':{'http_status':404,'message':'messages not found'},'history_window_minutes':15}
 if auth=='vinqu':operation.setdefault('response_semantics',{})['error_field']='Error'
 if path in ('/user/new','/user/activation','/user/restore'):
  operation['sensitive_fields']=[x for x in ('password','passwordNew','activationCode','code') if x in schema['properties']]
 operation['schema_notes']='Only explicit types and unconditional requirements are enforced. Nested shapes remain permissive where the provider supplies prose only. Review documentation before a write.'
 apply_reviewed_bounds(operation)
 operations[ident]=operation
 details[ident]={'request_parameter_rows':parameter_rows,'tables':parsed,'source':doc_url,'request_examples':examples}

sources=json.loads((HERE/'sources.json').read_text())
contract={'schema_version':1,'service':'abcp','fetched_at':sources['fetched_at'],'scope':'All 287 operations in the official ABCP, TS, VINQU and CarCare public API documentation. Documentation coverage does not establish account permission or live verification.','sources':sources['sources'],'auth_profiles':{'abcp':{'host':'Configured tenant HTTPS host; obtain from ABCP API access settings.','fields':['userlogin','userpsw'],'password':'userpsw is the MD5 digest; do not hash an existing digest again.','administrator_role':'A special API-administrator account is required for cp methods; account rights may further restrict TS operations.'},'vinqu':{'base_url':'https://publicapi.vinqu.com','fields':['siteHash','accessHash'],'credentials':'Separate VINQU integration settings; ABCP credentials are not interchangeable.'},'carcare':{'base_url':'https://car-care.abcp.ru','fields':['sitelogin','sitepsw'],'password':'sitepsw is MD5; issued separately by ABCP support.'}},'runtime_semantics':{'default_post_content_type':'application/x-www-form-urlencoded','accept':'application/json','text_encoding':'utf-8','arrays':'PHP bracket encoding except explicitly comma-separated parameters.','writes':'Never infer safety from HTTP method. Business writes require a reviewed plan; do not retry ambiguous failures automatically.','partial_success':'Inspect row-level errors and counts; an HTTP 200 response does not establish success of every item.','pagination':'Provider-specific skip/offset/limit, no automatic full-data scan.','global_rate_limit':'No universal numeric requests-per-second quota is specified in the reviewed pages.'},'operations':operations}
(ROOT/'registry/contracts/abcp.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')
capabilities=[]
for ident,op in operations.items():
 capabilities.append({'id':ident,'method':op['method'],'path':op['path'],'summary':op['summary'],'category':[op['family']], 'effect':op['effect'],'source':op['source'],'adapter':ident,'execution':'integration_read' if op['effect']=='read' else 'integration_write','access':'unknown_not_tested','implementation_status':'documented_contract','live_check':{'status':'not_tested','reason':'Official documentation and offline contract validation only.'},'parameters':op['parameters'],'executable_contracts':{ident:{'params_schema':op['parameters'],'source':op['source'],'response_kind':op['response_kind'],'encoding':op['encoding'],'auth':op['auth'],'auth_location':op['auth_location'],'parameter_serialization':op['parameter_serialization'],'documentation':op['documentation'],'risk':op['risk'],'schema_notes':op['schema_notes'],'response_semantics':op.get('response_semantics',{})}}})
capability_doc={'schema_version':1,'service':'abcp','retrieved_at':sources['fetched_at'],'scope':contract['scope'],'sources':sources['sources'],'total':len(capabilities),'capabilities':capabilities}
(ROOT/'registry/capabilities/abcp.json').write_text(json.dumps(capability_doc,ensure_ascii=False,indent=2)+'\n')
(HERE/'contract-details.json').write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n')
(HERE/'extraction-notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2)+'\n')
print('Total',len(operations),'families',dict(collections.Counter(x['family'] for x in operations.values())))
print('Effects',dict(collections.Counter(x['effect'] for x in operations.values())))
print('Encodings',dict(collections.Counter(x['encoding'] for x in operations.values())))
print('Extraction notes',notes)
assert len(operations)==287
assert all(re.fullmatch('[a-z][a-z0-9_]{0,99}',k) for k in operations)
