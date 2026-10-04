import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from automation_integrations.catalog import Catalog
from automation_integrations.api_read import HTTP, Failure, validate, OPERATIONS
ROOT=Path(__file__).resolve().parents[1]

class CapabilityTests(unittest.TestCase):
 def test_full_inventories_unique_and_paginated(self):
  c=Catalog(ROOT/'registry/catalog.json')
  for s,count in {'etm':19,'tochka':71,'yandex_go':52,'saby':91}.items():
   got=[];offset=0
   while offset is not None:
    page=c.find(service=s,view='capabilities',offset=offset,limit=7)
    got+=page['capabilities'];offset=page['next_offset']
   self.assertEqual(len(got),count);self.assertEqual(len({x['id'] for x in got}),count)
   adapters={name for x in got if x['adapter'] and x['execution']=='integration_read'
             for name in [x['adapter'], *x.get('additional_adapters', [])]}
   adapters.update(name for name, meta in page.get('supplemental_operations', {}).items()
                   if meta['execution']=='integration_read')
   self.assertEqual(adapters,set(OPERATIONS[s]))
   for row in got:
    if row['execution']=='integration_read':self.assertIn(row['effect'],('read','authentication'))
    elif row['execution']=='integration_write':
     self.assertIn(row['effect'],('business_write','report_generation'))
     self.assertEqual(row['access'],'unknown_not_tested')
    else:self.assertEqual(row['execution'],'not_implemented')
   detail=c.find(service=s,view='capabilities',capability_id=got[0]['id'])
   self.assertIn('parameters',detail['capabilities'][0])
 def test_invalid_inventory_inputs_and_search(self):
  c=Catalog(ROOT/'registry/catalog.json')
  for args in [{'service':'../private'},{'service':'etm','offset':-1},{'service':'etm','limit':True}]:
   with self.assertRaises(ValueError):c.find(view='capabilities',**args)
  r=c.find(service='tochka',view='capabilities',query='refund')
  self.assertGreater(r['matched'],0)
  self.assertTrue(all(x['adapter'] for x in r['capabilities']))
  self.assertTrue(any(x['execution']=='integration_write' for x in r['capabilities']))
 def test_proxy_credentials_only_stdin_and_no_direct_fallback(self):
  for code,output in [(0,'{}\n200'),(7,''),(0,'{}\n302')]:
   response=subprocess.CompletedProcess([],code,stdout=output,stderr='SECRET')
   with patch('subprocess.run',return_value=response) as run, patch('urllib.request.build_opener') as direct:
    h=HTTP('etm',{'etm_proxy':'socks5h://127.0.0.1:10929'})
    if code or '302' in output:
     with self.assertRaises(Failure):h.call('POST','/user/login',query={'pwd':'SECRET'})
    else:self.assertEqual(h.call('POST','/user/login',query={'pwd':'SECRET'}),{})
    self.assertNotIn('SECRET',str(run.call_args.args));self.assertIn(b'SECRET',run.call_args.kwargs['input'])
    self.assertNotIn('--location',run.call_args.args[0]);direct.assert_not_called()
 def test_invoice_date_window_and_write_rejection(self):
  for params in [{'date_from':'2026-01-01','date_to':'2026-12-31'}, {'date_from':'03/10/2026','date_to':'2026-10-03'}]:
   with self.assertRaises(Failure):validate({'service':'etm','operation':'invoices','params':params})
  for s,o in [('etm','invoice_create'),('tochka','payment'),('saby','sign'),('yandex_go','order_create')]:
   with self.assertRaises(Failure):validate({'service':s,'operation':o})
