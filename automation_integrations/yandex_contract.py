"""Strict subset of the official Go Business taxi API; no flight endpoints."""
import datetime as dt
import math
import re
import uuid

DOC='https://taxi__business-api.docs-viewer.yandex.ru/ru/concepts/api20/'
SOURCES={o:DOC+n for o,n in {'routestats':'routestats','zone_info':'zone-info','order_create':'order-create','order_cancel':'order-cancel'}.items()}
NUMBER={'type':'number'}
POINT={'type':'array','minItems':2,'maxItems':2,'items':NUMBER,'description':'[longitude -180..180, latitude -90..90]'}
ROUTE={'type':'array','minItems':2,'maxItems':10,'items':POINT}
ID={'type':'string','minLength':1,'maxLength':128,'pattern':r'^[A-Za-z0-9_-]+$'}
TEXT={'type':'string','minLength':1,'maxLength':512}
def obj(properties,required):return {'type':'object','properties':properties,'required':required,'additionalProperties':False}
SCHEMAS={
 'routestats':obj({'route':ROUTE,'user_id':ID,'use_toll_roads':{'type':'boolean'}},['route']),
 'zone_info':obj({'lon':{'type':'number','minimum':-180,'maximum':180},'lat':{'type':'number','minimum':-90,'maximum':90}},['lon','lat']),
 'order_create':obj({'user_id':ID,'class':ID,'route':{'type':'array','minItems':2,'maxItems':10,'items':obj({'geopoint':POINT,'fullname':TEXT},['geopoint','fullname'])},
                     'comment':TEXT,'cost_center_values':{'type':'array','maxItems':10,'items':obj({'id':ID,'title':TEXT,'value':TEXT},['id','title','value'])}},['user_id','class','route']),
 'order_cancel':obj({'order_id':ID},['order_id'])}
# Intentional subset: immediate rides, no arbitrary city-specific requirements,
# no user-supplied offers or cancellation state. Those come from provider reads.
def check(value,schema):
 t=schema['type']
 if t=='object':
  if not isinstance(value,dict) or set(value)-set(schema['properties']) or not set(schema['required'])<=set(value):raise ValueError('invalid_parameters')
  for k,v in value.items():check(v,schema['properties'][k])
 elif t=='array':
  if not isinstance(value,list) or not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',100):raise ValueError('invalid_array')
  for v in value:check(v,schema['items'])
 elif t=='string':
  if not isinstance(value,str) or not value.strip() or not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',512) or any(ord(c)<32 for c in value):raise ValueError('invalid_string')
  if schema.get('pattern') and not re.fullmatch(schema['pattern'],value):raise ValueError('invalid_identifier')
 elif t=='number':
  if type(value) not in (int,float) or not math.isfinite(value) or not schema.get('minimum',-math.inf)<=value<=schema.get('maximum',math.inf):raise ValueError('invalid_coordinate')
 elif t=='boolean' and type(value) is not bool:raise ValueError('invalid_boolean')
def validate(operation,params):
 if operation not in SCHEMAS:raise ValueError('unsupported_operation')
 check(params,SCHEMAS[operation])
 points=params.get('route',[])
 for p in points:
  p=p.get('geopoint') if isinstance(p,dict) else p
  if not -180<=p[0]<=180 or not -90<=p[1]<=90:raise ValueError('invalid_coordinate')
 if points and len({tuple(p['geopoint'] if isinstance(p,dict) else p) for p in points})<2:raise ValueError('route_points_identical')
 return params
