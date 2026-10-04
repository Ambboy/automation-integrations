"""Regenerate pinned inference.sh contracts from reviewed definitions and snapshots.

Run from repository root: python3 ops/build_inference_contract.py
This does not fetch network data or read credentials. Request fields are reviewed
from docs/media-api-snapshots/inference; the OpenAPI document is a route catalog
without request schemas, so it is used only to inventory and verify routes.
"""
from pathlib import Path
from copy import deepcopy
import datetime,hashlib,json,re
ROOT=Path('.');SNAP=ROOT/'docs/media-api-snapshots/inference';DOC=json.loads((SNAP/'openapi.json').read_text())
S={'type':'string','maxLength':8192};O={'type':'object','additionalProperties':True};A={'type':'array','items':{},'maxItems':1000};B={'type':'boolean'};N={'type':'number'};I={'type':'integer'}
ID={'type':'string','minLength':1,'maxLength':256,'pattern':r'^[A-Za-z0-9_@.+-]+$'}
REF={'type':'string','minLength':1,'maxLength':512,'pattern':r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:@[A-Za-z0-9_.-]+)?$'}
PAGE={'limit':{'type':'integer','minimum':1,'maximum':100},'cursor':S,'direction':{'type':'string','enum':['next','prev','forward','backward']},'filters':A,'sort':A,'search':O,'include_others':B,'include_private':B}
ops={}
def add(name,method,path,fields=None,required=(),*,scope=None,effect=None,category=None,query=(),public=False,source=None,raw=False):
 fields=deepcopy(fields or {}); path_names=re.findall(r'{([^{}]+)}',path)
 for key in path_names:fields[key]=deepcopy(ID)
 params={'type':'object','properties':fields,'required':list(dict.fromkeys(list(path_names)+list(required))),'additionalProperties':False}
 cat=category or path.strip('/').split('/')[0]
 ops[name]={'method':method,'path':path,'category':cat,'effect':effect or ('read' if method=='GET' else 'write'),'parameters':params,'path_parameters':path_names,'query_parameters':list(fields) if method=='GET' else list(query),'required_scopes':scope or [],'public':public,'source':source or 'https://inference.sh/docs/api/rest/'+cat,'raw_response':raw}

def read(name,path,fields=None,**kw):add(name,'GET',path,fields,**kw)
def write(name,path,fields=None,required=(),**kw):add(name,'POST',path,fields,required,**kw)
def paged(name,path,scope,source=None):
 read(name,path,PAGE,scope=[scope],source=source)
 if path+'/list' in DOC['paths']:add(name+'_post','POST',path+'/list',PAGE,effect='read',scope=[scope],source=source)

read('identity','/me',scope=['user:read'],source='https://inference.sh/docs/api/rest/teams')
read('scopes','/scopes',source='https://inference.sh/docs/api/rest/api-keys')
paged('app_list','/apps','apps:read');read('app_get','/apps/{id}',scope=['apps:read']);read('app_get_by_ref','/apps/{namespace}/{name}',scope=['apps:read'])
paged('app_versions','/apps/{id}/versions','apps:read',source='https://inference.sh/docs/api/rest/apps');read('app_version','/apps/{id}/versions/{versionId}',scope=['apps:read'])
add('app_set_current_version','PUT','/apps/{id}/versions/{versionId}/current',scope=['apps:write'])
write('app_set_status','/apps/{id}/status',{'status':{'type':'string','enum':['active','maintenance','deprecated','retired']},'message':S},['status'],scope=['apps:write'])
for kind in ['apps','skills']:
 paged('store_'+kind,'/store/'+kind,'',source='https://inference.sh/docs/api/rest/store')
 for op in ['store_'+kind,'store_'+kind+'_post']:
  if op in ops:ops[op].update(public=True,required_scopes=[])
 read('store_'+kind+'_get','/store/'+kind+'/{'+('appId' if kind=='apps' else 'skillId')+'}',public=True,source='https://inference.sh/docs/api/rest/store')
read('app_pricing','/store/apps/{appId}/pricing',public=True,source='https://inference.sh/docs/api/rest/store')
write('estimate','/store/apps/{appId}/estimate',{'input':O,'function':S},effect='read',public=True,source='https://inference.sh/docs/api/rest/store')
run_fields={'app':REF,'input':O,'setup':O,'function':S,'infra':{'type':'string','enum':['cloud','private','private_first']},'workers':{'type':'array','items':ID},'webhook':S,'session':S,'session_timeout':{'type':'integer','minimum':1,'maximum':3600},'wait':{'type':'boolean','enum':[False]}}
write('app_run','/run',run_fields,['app','input'],scope=['apps:execute'],effect='generation',query=['wait'],source='https://inference.sh/docs/api/rest/tasks')
write('app_run_alias','/apps/run',run_fields,['app','input'],scope=['apps:execute'],effect='generation',query=['wait'],source='https://inference.sh/docs/api/rest/tasks')
paged('task_list','/tasks','apps:read');read('task_get','/tasks/{id}',scope=['apps:read'])
for tail in ['status','logs','timings','telemetry']:read('task_'+tail,'/tasks/{id}/'+tail,scope=['apps:read'])
read('task_queue_stats','/tasks/queue-stats',scope=['apps:read'],source='https://inference.sh/docs/api/rest/tasks')
write('task_cancel','/tasks/{id}/cancel',{'force':B,'timeout':{'type':'integer','minimum':0,'maximum':60000}},scope=['apps:execute'])
read('task_cost','/usage/tasks/{taskID}/cost',scope=['apps:read|billing:read'],source='https://inference.sh/docs/api/rest/usage')
for op,path in [('billing_account','/billing'),('balance','/billing/balance'),('service_fee','/billing/service-fee'),('billing_settings','/billing/settings'),('billing_payments','/billing/payments'),('usage_summary','/usage/summary'),('entitlements','/entitlements'),('entitlement_usage','/entitlements/usage'),('subscription','/subscription'),('subscription_addons','/subscription/addons')]:
 read(op,path,PAGE if op=='billing_payments' else {},scope=['billing:read'])
read('plans','/plans',{'type':{'type':'string','enum':['base','addon','all']}},public=True,source='https://inference.sh/docs/api/rest/subscription')
read('usage_breakdown','/usage/breakdown',{'range':{'type':'string','enum':['1h','1d','7d','30d','90d']},'team_id':ID},scope=['billing:read'],source='https://inference.sh/docs/api/rest/usage')
write('pricing_evaluate','/usage/cel/evaluate',{'pricing':O,'output_meta':O,'resources':A,'usage_seconds':I,'task_inputs':O},effect='read',scope=['billing:read'],source='https://inference.sh/docs/api/rest/usage')
read('suggest','/suggest',{'q':S},required=['q'],source='https://inference.sh/docs/api/rest/search')
write('suggest_search','/suggest',{'query':S,'context':S,'scope':{'type':'array','items':S},'limit':{'type':'integer','minimum':1,'maximum':100},'category':{'type':'string','enum':['app','skill','knowledge','agent','mcp','doc']},'agent':B},['query'],effect='read',source='https://inference.sh/docs/api/rest/search')
read('search','/search',{'q':S,'collection':{'type':'string','enum':['apps','skills','knowledge','agents','flows','mcp_servers','pages']}},required=['q'],source='https://inference.sh/docs/api/rest/search')
write('search_collections','/search',{'query':S,'collections':{'type':'array','items':{'type':'string','enum':['apps','skills','knowledge','agents','flows','mcp_servers','pages']}},'limit':{'type':'integer','minimum':1,'maximum':100}},['query'],effect='read',source='https://inference.sh/docs/api/rest/search')
file_row={'type':'object','properties':{'uri':{'type':'string','enum':['']},'filename':S,'content_type':S,'size':{'type':'integer','minimum':0},'path':S},'required':['uri'],'additionalProperties':False}
write('file_create','/files',{'files':{'type':'array','items':file_row,'minItems':1,'maxItems':100},'category':S},['files'],scope=['files:write'])
paged('file_list','/files','files:read');add('file_delete','DELETE','/files/{id}',scope=['files:write'])
read('session_list','/sessions',scope=['apps:read']);read('session_get','/sessions/{id}',scope=['apps:read']);write('session_keepalive','/sessions/{id}/keepalive',scope=['apps:execute']);add('session_end','DELETE','/sessions/{id}',scope=['apps:execute'])
# Definition and version read APIs; schemas remain provider-owned and evolve per resource.
for resource,scope,cat in [('flows','flows','flows'),('agents','agents','agents'),('knowledge','knowledge','knowledge'),('skills','knowledge','skills'),('artifacts','artifacts','artifacts')]:
 singular={'knowledge':'knowledge'}.get(resource,resource[:-1]);source='https://inference.sh/docs/api/rest/'+cat
 paged(singular+'_list','/'+resource,scope+':read',source)
 read(singular+'_get','/'+resource+'/{id}',scope=[scope+':read'],source=source)
 read(singular+'_get_by_ref','/'+resource+'/{namespace}/{name}',scope=[scope+':read'],source=source)
 paged(singular+'_versions','/'+resource+'/{id}/versions',scope+':read',source)
 if '/'+resource+'/{id}/versions/{versionId}' in DOC['paths']:read(singular+'_version','/'+resource+'/{id}/versions/{versionId}',scope=[scope+':read'],source=source)
 add(singular+'_delete','DELETE','/'+resource+'/{id}',scope=[scope+':write'],source=source)
 write(singular+'_visibility','/'+resource+'/{id}/visibility',{'visibility':{'type':'string','enum':['private','team','org','public','unlisted']}},['visibility'],scope=[scope+':write'],source=source)
for resource in ['knowledge','skills']:
 singular='knowledge' if resource=='knowledge' else 'skill'
 for tail in ['references','lineage']:read(singular+'_'+tail,'/'+resource+'/{id}/'+tail,scope=['knowledge:read'],source='https://inference.sh/docs/api/rest/'+resource)
read('knowledge_version_by_ref','/knowledge/{namespace}/{name}/versions/{versionId}',scope=['knowledge:read'])
read('skill_content','/skills/{namespace}/{name}/content',scope=['knowledge:read'])
read('skill_resolve','/skills/resolve',{'ref':S,'skill':S},required=['ref'],scope=['knowledge:read'])
write('skill_import_discover','/skills/import/github/discover',{'url':S},['url'],effect='read',scope=['knowledge:read'],source='https://inference.sh/docs/api/rest/skills')
write('skill_import','/skills/import/github',{'url':S,'paths':{'type':'array','items':S}},['url'],scope=['knowledge:write'],source='https://inference.sh/docs/api/rest/skills')
write('flow_create','/flows',{'name':S},scope=['flows:write'])
add('flow_update','PATCH','/flows/{id}',{x:S for x in ['name','description','card_image','thumbnail','banner_image']},scope=['flows:write'])
write('flow_actions','/flows/{id}/actions',{'actions':{'type':'array','items':{'type':'object','properties':{'type':{'type':'string','enum':['node.add','node.remove','node.move','node.move_many','node.duplicate','node.rename','node.set_app','node.update','node.set_input','node.clear_input','edge.add','edge.remove','flow.set_input_schema','flow.set_output_schema','flow.set_output_mapping','flow.remove_output_mapping','flow.rename_output_field','undo','redo']},'payload':O},'required':['type'],'additionalProperties':False},'minItems':1,'maxItems':100}},['actions'],scope=['flows:write'])
write('flow_duplicate','/flows/{id}/duplicate',scope=['flows:write']);write('flow_deploy_app','/flows/{id}/app',{'name':S},scope=['flows:write'])
write('flow_run','/flowruns',{'flow':ID,'input':O},['flow','input'],effect='generation',scope=['flows:execute'],source='https://inference.sh/docs/api/rest/flow-runs')
paged('flow_run_list','/flowruns','flows:read','https://inference.sh/docs/api/rest/flow-runs');read('flow_run_get','/flowruns/{id}',scope=['flows:read'],source='https://inference.sh/docs/api/rest/flow-runs');write('flow_run_cancel','/flowruns/{id}/cancel',scope=['flows:execute'],source='https://inference.sh/docs/api/rest/flow-runs');write('flow_run_clone','/flowruns/{id}/clone',scope=['flows:write'],source='https://inference.sh/docs/api/rest/flow-runs')
agent_fields={'agent':REF,'chat_id':ID,'agent_config':O,'agent_name':S,'context':O,'channel_context':O,'input':O,'stream':{'type':'boolean','enum':[False]}}
write('agent_run','/agents/run',agent_fields,['input'],effect='generation',scope=['agents:execute'])
write('agent_message','/agents/message',{**{k:v for k,v in agent_fields.items() if k!='agent'},'agent_id':ID,'agent_version_id':ID},['input'],effect='generation',scope=['agents:execute'])
write('agent_create','/agents',{'name':S,'namespace':S,'id':ID,'version':O,'visibility':S},['name'],scope=['agents:write'])
write('agent_update','/agents/{id}',{'name':S,'version':O,'description':S,'card_image':S,'thumbnail':S,'banner_image':S},scope=['agents:write'])
read('agent_internal_tools','/agents/internal-tools',scope=['agents:read']);read('agent_hook_events','/agents/hook-events',scope=['agents:read']);read('agent_card','/agents/{id}/card',scope=['agents:read'],raw=True);read('agent_card_by_ref','/agents/{namespace}/{name}/card',scope=['agents:read'],raw=True)
write('chat_create','/chats',{'agent':REF,'name':S},scope=['conversations:write'],source='https://inference.sh/docs/api/rest/agents')
paged('chat_list','/chats','conversations:read','https://inference.sh/docs/api/rest/agents')
for tail in ['','/status','/trace']:read('chat_'+(tail.strip('/') or 'get'),'/chats/{id}'+tail,scope=['conversations:read'],source='https://inference.sh/docs/api/rest/agents')
paged('chat_messages','/chats/{id}/messages','conversations:read','https://inference.sh/docs/api/rest/agents')
write('chat_stop','/chats/{id}/stop',scope=['conversations:write'],source='https://inference.sh/docs/api/rest/agents')
write('chat_message','/chats/{id}/messages',{'message':S},['message'],effect='generation',scope=['conversations:write'],source='https://inference.sh/docs/api/rest/agents')
write('chat_message_cancel','/chats/messages/{messageId}/cancel',scope=['conversations:write'],source='https://inference.sh/docs/api/rest/agents')
write('tool_result','/tools/{toolInvocationId}',{'result':S},['result'],scope=['conversations:write'],source='https://inference.sh/docs/api/rest/agents')
write('tool_approve','/tools/{toolInvocationId}/invoke',scope=['conversations:write'],effect='generation',source='https://inference.sh/docs/api/rest/agents')
write('tool_reject','/tools/{toolInvocationId}/reject',{'reason':S},scope=['conversations:write'],source='https://inference.sh/docs/api/rest/agents')
read('agent_run_interrupts','/agent-runs/{runId}/interrupts',scope=['conversations:read'],source='https://inference.sh/docs/api/rest/agents')
write('interrupt_resolve','/interrupts/{id}/resolve',{'decision':{'type':'string','enum':['allow','deny']},'data':O},['decision'],scope=['conversations:write'],effect='generation',source='https://inference.sh/docs/api/rest/agents')
for path,name in [('/models/openai/models','chat_models')]:read(name,path,scope=['apps:read'],raw=True,source='https://inference.sh/docs/api/rest/openai')
chat_fields={'model':REF,'messages':{'type':'array','minItems':1,'items':O},'stream':{'type':'boolean','enum':[False]},'tools':A,'tool_choice':{},'response_format':O,'temperature':N,'top_p':N,'frequency_penalty':N,'presence_penalty':N,'seed':I,'stop':{},'max_completion_tokens':{'type':'integer','minimum':1},'max_tokens':{'type':'integer','minimum':1},'reasoning_effort':{'type':'string','enum':['none','minimal','low','medium','high','xhigh']},'functions':A,'function_call':{},'user':S,'metadata':O,'store':B,'parallel_tool_calls':B}
write('chat_completion','/models/openai/chat/completions',chat_fields,['model','messages'],scope=['apps:execute'],effect='generation',raw=True,source='https://inference.sh/docs/api/rest/openai')
write('app_chat_completion','/apps/{namespace}/{name}/openai/chat/completions',{k:v for k,v in chat_fields.items() if k!='model'},['messages'],scope=['apps:execute'],effect='generation',raw=True,source='https://inference.sh/docs/api/rest/openai')
write('agent_chat_completion','/agents/{namespace}/{name}/openai/chat/completions',{**{k:v for k,v in chat_fields.items() if k!='model'},'channel':S,'continue':S,'wait':S,'max_chars':I},['messages'],scope=['agents:execute'],effect='generation',query=['channel','continue','wait','max_chars'],raw=True,source='https://inference.sh/docs/api/rest/openai')
# Artifacts JSON content and storage, no multipart renderer/assets transport here.
for path,name in [('/artifacts/{id}/content','artifact_content'),('/artifacts/{id}/versions/{versionId}/content','artifact_version_content'),('/artifacts/{id}/comments','artifact_comments'),('/artifacts/{id}/viewer','artifact_viewer'),('/artifacts/{id}/assets','artifact_assets')]:read(name,path,scope=['artifacts:read'])
read('artifact_guidance','/artifacts/guidance',{'topics':S},scope=['artifacts:read'])
write('artifact_comment','/artifacts/{id}/comments',{'content':S,'parent_comment_id':ID,'send_to_agent':B},['content'],scope=['artifacts:read'])
write('artifact_comment_activate','/artifacts/{id}/comments/{commentId}/activate',scope=['artifacts:write'])
write('artifact_comment_resolve','/artifacts/{id}/comments/{commentId}/resolve',{'resolved':B},scope=['artifacts:write'])
for tail in ['get','list','set','update','delete']:
 fields={'collection':S}
 if tail!='list':fields['doc_id']=S
 if tail in ['set','update']:fields['data']=O
 if tail=='list':fields['limit']={'type':'integer','minimum':1,'maximum':200}
 write('artifact_data_'+tail,'/artifacts/{id}/data/'+tail,fields,list(k for k in fields if k!='limit'),effect='read' if tail in ['get','list'] else 'write',scope=['artifacts:read' if tail in ['get','list'] else 'artifacts:write'])
add('artifact_asset_delete','DELETE','/artifacts/{id}/assets/{assetId}',scope=['artifacts:write'])
# Trigger scheduling is a write; dispatch is charged execution. No webhook signature emulation.
for path,name in [('/triggers','trigger_list'),('/trigger-fires','trigger_fire_list')]:paged(name,path,'agents:read','https://inference.sh/docs/api/rest/triggers')
for path,name in [('/triggers/{id}','trigger_get'),('/trigger-fires/{id}','trigger_fire_get')]:read(name,path,scope=['agents:read'],source='https://inference.sh/docs/api/rest/triggers')
read('trigger_sources','/trigger-sources',public=True,source='https://inference.sh/docs/api/rest/triggers')
trig={'name':S,'type':{'type':'string','enum':['cron','webhook','scheduled','manual']},'action':{'type':'string','enum':['run_agent','run_app','run_flow','resolve_interrupt']},'agent_id':ID,'app_id':ID,'flow_id':ID,'interrupt_id':ID,'config':O,'scheduled_at':S,'source_id':ID,'enabled':B,'input':O,'input_mapping':O,'filters':A}
write('trigger_create','/triggers',trig,['name','type','action'],scope=['agents:write']);write('trigger_update','/triggers/{id}',{k:trig[k] for k in ['name','enabled','config','scheduled_at','input','input_mapping','filters']},scope=['agents:write']);add('trigger_delete','DELETE','/triggers/{id}',scope=['agents:write'])
# JSON fire payload is arbitrary input for the previously configured trigger.
write('trigger_fire','/triggers/{id}/fire',{'input':O},scope=['agents:execute'],effect='generation');ops['trigger_fire']['body_parameter']='input'
# MCP and inventory for connected tools. MCP credentials stay behind provider boundary.
for path,name in [('/mcps','mcp_catalog'),('/mcp-servers','mcp_server_list')]:paged(name,path,'credentials:read','https://inference.sh/docs/api/rest/mcp-servers')
read('mcp_catalog_get','/mcps/{slug}',scope=['credentials:read'],source='https://inference.sh/docs/api/rest/mcp-servers');read('mcp_server_get','/mcp-servers/{id}',scope=['credentials:read'],source='https://inference.sh/docs/api/rest/mcp-servers');read('mcp_discover','/mcps/discover',{'url':S},required=['url'],scope=['credentials:read'],source='https://inference.sh/docs/api/rest/mcp-servers');read('mcp_tools','/mcps/{slug}/tools',scope=['credentials:read'],source='https://inference.sh/docs/api/rest/mcp-servers')
write('mcp_tool_call','/mcps/{slug}/tools/{tool}',{'arguments':O},['arguments'],scope=['credentials:write'],effect='generation',source='https://inference.sh/docs/api/rest/mcp-servers');ops['mcp_tool_call']['body_parameter']='arguments'
for path,name in [('/credentials/capabilities','credential_capabilities'),('/credentials/available','credential_providers')]:read(name,path,scope=['credentials:read'],source='https://inference.sh/docs/api/rest/credentials')
# Read operational metadata; remote command dispatch remains explicitly unimplemented.
for path,name,scope in [('/engines','engine_list','engines:read'),('/remotes','remote_list','remotes:read'),('/execs','exec_list','remotes:read'),('/teams','workspace_list','teams:read'),('/pages','page_list',''),('/apikeys','api_key_metadata','apikeys:read')]:paged(name,path,scope)
for path,name,scope in [('/engines/{id}','engine_get','engines:read'),('/remotes/{id}','remote_get','remotes:read'),('/remotes/{id}/sessions','remote_sessions','remotes:read'),('/execs/{id}','exec_get','remotes:read'),('/teams/{id}','workspace_get','teams:read'),('/teams/{id}/members','workspace_members','teams:read'),('/pages/{id}','page_get',''),('/pages/slug/{slug}','page_get_by_slug',''),('/instances/types','instance_types',''),('/harnesses','harnesses','remotes:read')]:read(name,path,scope=[scope] if scope else [])
read('exec_output','/execs/{id}/output',{'after_seq':{'type':'integer','minimum':0}},scope=['remotes:read'],source='https://inference.sh/docs/api/rest/exec-runs')
write('engine_resources','/engines/resources',{'resources':O},['resources'],scope=['engines:read'],effect='read',source='https://inference.sh/docs/api/rest/engines')
# Remaining documented JSON authoring and sharing operations.
for op in ['artifact_guidance','skill_content']:
 ops[op]['response_kind']='text';ops[op]['public']=op=='artifact_guidance'
read('skill_file','/skills/{namespace}/{name}/files/{path}',scope=['knowledge:read'])
ops['skill_file']['response_kind']='text';ops['skill_file']['parameters']['properties']['path']={'type':'string','minLength':1,'maxLength':1024}
read('artifact_frame','/artifacts/{id}/frame',{'version':S,'theme':{'type':'string','enum':['dark','light']}},scope=['artifacts:read'])
read('artifact_render','/artifacts/{id}/render',{'version':S,'theme':{'type':'string','enum':['dark','light']}},scope=['artifacts:read']);ops['artifact_render']['response_kind']='text'
write('artifact_update','/artifacts/{id}',{k:S for k in ['title','description','favicon','shared_version_id','card_image','thumbnail','banner_image']},scope=['artifacts:write'])
write('artifact_share','/artifacts/{id}/share',{'user_id':ID,'permission':{'type':'string','enum':['read','write']}},['user_id','permission'],scope=['artifacts:write']);read('artifact_shares','/artifacts/{id}/shares',scope=['artifacts:read']);add('artifact_unshare','DELETE','/artifacts/{id}/share/{userId}',scope=['artifacts:write'])
for resource in ['artifacts','knowledge']:
 write(('artifact' if resource=='artifacts' else 'knowledge')+'_transfer','/'+resource+'/{id}/transfer',{'team_id':ID},['team_id'],scope=[resource+':write'])
skill_fields={'namespace':S,'name':S,'description':S,'instructions':{'type':'string','maxLength':524288},'files':A,'license':S,'allowed_tools':S,'compatibility':S,'repo_url':S}
write('skill_create','/skills',skill_fields,['name','description','instructions'],scope=['knowledge:write']);write('skill_update','/skills/{id}',skill_fields,scope=['knowledge:write']);write('skill_supersede','/skills/{id}/supersede',{'superseded_id':ID},['superseded_id'],scope=['knowledge:write'])
knowledge_fields={'name':S,'description':S,'type':S,'lifecycle':{'type':'string','enum':['permanent','decay']},'version':O}
write('knowledge_create','/knowledge',knowledge_fields,['name','description','version'],scope=['knowledge:write']);write('knowledge_update','/knowledge/{id}',knowledge_fields,scope=['knowledge:write'])
server_fields={'server_url':S,'name':S,'slug':S,'description':S,'auth_type':{'type':'string','enum':['oauth','api_key','none']},'oauth_client_id':S,'default_scopes':{'type':'array','items':S},'documentation_url':S,'visibility':{'type':'string','enum':['private','public']}}
write('mcp_server_create','/mcp-servers',server_fields,['server_url'],scope=['credentials:write'],source='https://inference.sh/docs/api/rest/mcp-servers');add('mcp_server_update','PUT','/mcp-servers/{id}',server_fields,scope=['credentials:write'],source='https://inference.sh/docs/api/rest/mcp-servers');write('mcp_server_refresh','/mcp-servers/{id}/refresh',scope=['credentials:write'],source='https://inference.sh/docs/api/rest/mcp-servers');add('mcp_server_delete','DELETE','/mcp-servers/{id}',scope=['credentials:write'],source='https://inference.sh/docs/api/rest/mcp-servers')
paged('mcp_tool_history','/mcp-tool-calls','credentials:read','https://inference.sh/docs/api/rest/mcp-servers')
read('publication_list','/publications',{'resource_type':{'type':'string','enum':['agent']},'resource_id':ID},required=['resource_type','resource_id'],scope=['agents:read']);read('publication_get','/publications/{id}',scope=['agents:read'])
publication_fields={'resource_type':{'type':'string','enum':['agent']},'resource_id':ID,'allowed_origins':{'type':'array','items':S},'theme':O,'label':S,'rate_limit_rpm':I}
write('publication_create','/publications',publication_fields,['resource_type','resource_id'],scope=['agents:write']);add('publication_update','PUT','/publications/{id}',{k:v for k,v in publication_fields.items() if k not in ['resource_type','resource_id']},scope=['agents:write']);add('publication_delete','DELETE','/publications/{id}',scope=['agents:write'])
# Metadata endpoints and scope names in OpenAPI tags do not always equal docs page slugs.
source_map={'run':'tasks','chats':'agents','tools':'agents','interrupts':'agents','agent-runs':'agents','apikeys':'api-keys','scopes':'api-keys','execs':'exec-runs','harnesses':'remotes','teams':'teams','plans':'subscription','models':'openai','instance-types':'instances','trigger-fires':'triggers','trigger-sources':'triggers'}
for op in ops.values():
 family=op['path'].split('/')[1]
 if family in source_map:op['source']='https://inference.sh/docs/api/rest/'+source_map[family]
 opscope=op['required_scopes']
 op['required_scopes']=[x for x in opscope if x]

ops['skill_resolve']['effect']='write'
ops['skill_resolve']['required_scopes']=['knowledge:write']
# Only methods actually in the official route catalog are executable. Record omissions for review.
def normalize(path):return re.sub(r'{[^}]+}','{}',path)
route_map={(m.upper(),normalize(p)):(p,v) for p,methods in DOC['paths'].items() for m,v in methods.items() if m in ['get','post','put','patch','delete','options','head']}
missing=[]
for name,op in list(ops.items()):
 key=(op['method'],normalize(op['path']))
 if key not in route_map:missing.append((name,op['method'],op['path']));del ops[name]
print('Missing from official catalog:',missing)
# Explicit unavailable inventory. Unsupported means method is NOT callable by a passthrough escape hatch.
supported={(r['method'],normalize(r['path'])):(n,r) for n,r in ops.items()}
def reason(method,path):
 if path.startswith('/admin/') or path.startswith('/_') or path.startswith('/internal/'):return 'platform_internal_or_admin_route'
 if path.startswith(('/auth/','/oauth/','/device/','/apikeys','/secrets','/credentials','/vaults')):return 'credential_or_identity_workflow_requires_secret_safe_executor'
 if path.startswith(('/billing','/subscription')) and method!='GET':return 'payment_or_subscription_mutation_requires_billing_executor'
 if '/stream' in path or path.endswith('/events') or '/ws' in path or 'socket' in path:return 'streaming_or_websocket_transport_not_implemented_use_polling'
 if '/a2a' in path:return 'a2a_protocol_transport_not_implemented_use_agent_json_api'
 if path.startswith('/embed/'):return 'anonymous_embed_origin_and_guest_session_flow_not_implemented'
 if '/skills/' in path and '/files/' in path:return 'cdn_redirect_file_download_not_implemented'
 if '/render' in path or '/assets' in path or (path.startswith('/artifacts') and method in ('POST','PUT')):return 'multipart_or_binary_artifact_transport_or_unreviewed_schema'
 if path.startswith(('/remotes','/execs','/engines')) and method!='GET':return 'remote_or_engine_control_requires_separate_executor'
 if '/hook' in path or '/channel' in path or path.endswith('/slack'):return 'inbound_provider_webhook_not_an_outbound_connector_operation'
 return 'request_schema_not_published_or_not_reviewed'
sources=json.loads((SNAP/'sources.json').read_text())
assert any(row['url']=='https://api.inference.sh/openapi.json' and row['sha256']==hashlib.sha256((SNAP/'openapi.json').read_bytes()).hexdigest() for row in sources), 'Update source provenance when replacing the OpenAPI snapshot'
cap=[]
for (method,np),(path,doc) in sorted(route_map.items()):
 item={'id':method+' '+path,'method':method,'path':path,'category':doc.get('tags',[]),'effect':'read' if method=='GET' else 'business_write','source':'https://api.inference.sh/openapi.json'}
 if (method,np) in supported:
  name,row=supported[(method,np)]; item.update(operation=name,summary=name.replace('_',' '),effect='read' if row['effect']=='read' else 'business_write',execution_effect=row['effect'],required_scopes=row['required_scopes'],params_schema=row['parameters'],source=row['source'],availability='implemented')
 else:item.update(availability='not_implemented',unsupported_reason=reason(method,path))
 cap.append(item)
contract={'schema_version':1,'service':'inference','retrieved_at':'2026-10-04','base_url':'https://api.inference.sh','operations':ops}
(ROOT/'registry/contracts').mkdir(exist_ok=True)
(ROOT/'registry/contracts/inference.json').write_text(json.dumps(contract,indent=2)+'\n')
summary={'schema_version':1,'service':'inference','retrieved_at':'2026-10-04','scope':'All methods in official route catalog inventoried; reviewed JSON contracts callable. Public app discovery and execution are dynamic; no hardcoded model allowlist. Documented availability is distinct from account grants.','sources':sources,'total':len(cap),'implemented':len(ops),'capabilities':cap}
(ROOT/'registry/capabilities/inference.json').write_text(json.dumps(summary,indent=2)+'\n')
print('operations',len(ops),'inventory',len(cap),'generation',[n for n,r in ops.items() if r['effect']=='generation'])
