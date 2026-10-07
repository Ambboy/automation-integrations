import requests,json,hashlib,concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup
base=Path(__file__).resolve().parent
paths=['api/public-api','api/docs','api/abcp1/api-abcp-client','api/abcp1/api-abcp-admin','api/abcp2/api-ts-client','api/abcp2/api-ts-admin','vinqu/apivinqu','carcare/carcaremodule/api']
def run(path):
 url='https://www.abcp.ru/d/docs/'+path
 r=requests.get(url,timeout=45);r.raise_for_status()
 name=path.replace('/','__');(base/'snapshots'/f'{name}.html').write_bytes(r.content)
 soup=BeautifulSoup(r.content,'html.parser');a=soup.find('article')
 (base/'snapshots'/f'{name}.txt').write_text(a.get_text('\n',strip=True))
 return {'url':url,'html':f'snapshots/{name}.html','text':f'snapshots/{name}.txt','sha256':hashlib.sha256(r.content).hexdigest(),'size':len(r.content)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: rows=list(ex.map(run,paths))
(base/'sources.json').write_text(json.dumps({'fetched_at':datetime.now(timezone.utc).isoformat(),'sources':rows},ensure_ascii=False,indent=2)+'\n')
for r in rows: print(r['url'],r['size'])
