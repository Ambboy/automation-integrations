from pathlib import Path
from bs4 import BeautifulSoup,Tag
import re,csv,collections,json
base=Path(__file__).resolve().parent
files={'abcp-client':'api__abcp1__api-abcp-client','abcp1-admin':'api__abcp1__api-abcp-admin','ts-client':'api__abcp2__api-ts-client','ts-admin':'api__abcp2__api-ts-admin','vinqu':'vinqu__apivinqu','carcare':'carcare__carcaremodule__api'}
sections=[]
for family,name in files.items():
 a=BeautifulSoup((base/'snapshots'/f'{name}.html').read_bytes(),'html.parser').select_one('.theme-doc-markdown')
 for h in a.find_all(['h3'] if family in ('carcare','vinqu') else ['h3','h4']):
  level=int(h.name[1]); nodes=[]
  for node in h.next_siblings:
   if isinstance(node,Tag) and node.name in ['h2','h3','h4'] and (family not in ('carcare','vinqu') or int(node.name[1])<=level):break
   nodes.append(node)
  s=BeautifulSoup(''.join(str(x) for x in nodes),'html.parser');tx=s.get_text(' ',strip=True).replace('\u200b','')
  declaration=next((p.get_text() for p in s.find_all('p') if 'Операция:' in p.get_text()),None)
  if family=='carcare':
   declaration=next((p.get_text() for p in s.find_all('pre') if re.match(r'^(GET|POST) /',p.get_text())),None)
  if not declaration:continue
  m=re.search(r'(?:Операция:\s*)?(?:(GET|POST)\s+)?([/a-zA-Z][\w/:{}.\-]*)',declaration.replace('Операция:',''))
  if not m:print('FAIL',family,declaration);continue
  method=m.group(1)
  if not method:
   mm=re.search(r'Метод:[\s*]*(GET|POST)',tx);method=mm.group(1) if mm else None
  path=m.group(2).rstrip('/').replace(':id','{id}')
  if not method:print('NO METHOD',family,repr(tx[:100]));continue
  section={'family':family,'method':method,'path':'/'+path.lstrip('/'),'anchor':h['id'],'title':h.get_text(' ',strip=True).replace('\u200b','').strip(),'text':tx,'html':str(s)}
  sections.append(section)
(base/'sections.json').write_text(json.dumps(sections,ensure_ascii=False,indent=2))
print('COUNTS',collections.Counter(x['family'] for x in sections))
old=list(csv.DictReader((base/'baseline-endpoints.csv').read_text().splitlines()))
f=lambda x:(x['family'],x['method'],x['path'].rstrip('/').replace(':id','{id}'))
print('Missing:',[(f(x),x['title']) for x in old if f(x) not in {f(y) for y in sections}]);print('Extra:',[(f(x),x['title']) for x in sections if f(x) not in {f(y) for y in old}]);
for x in sections:print(x['family'],x['method'],x['path'],x['title'])
