"""Offline regression checks for the pinned ABCP prose contract; stdlib only."""
from pathlib import Path
import collections, csv, hashlib, json, re, unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DOC=json.loads((ROOT/'registry/contracts/abcp.json').read_text())
OPS=DOC['operations']

class CatalogTest(unittest.TestCase):
 def op(self,path,method='GET',family=None):
  found=[x for x in OPS.values() if x['path']==path and x['method']==method and (family is None or x['family']==family)]
  self.assertEqual(len(found),1);return found[0]
 def test_full_baseline(self):
  baseline=list(csv.DictReader((HERE/'baseline-endpoints.csv').read_text().splitlines()))
  expected={(x['family'],x['method'],x['path'].rstrip('/').replace(':id','{id}')) for x in baseline}
  actual={(x['family'],x['method'],x['path']) for x in OPS.values()}
  self.assertEqual(expected,actual);self.assertEqual(len(OPS),287)
 def test_families(self):
  self.assertEqual(collections.Counter(x['family'] for x in OPS.values()),{'abcp-client':45,'abcp1-admin':76,'ts-client':30,'ts-admin':122,'vinqu':8,'carcare':6})
 def test_snapshot_integrity(self):
  for source in DOC['sources']:
   self.assertEqual(hashlib.sha256((HERE/source['html']).read_bytes()).hexdigest(),source['sha256'])
 def test_ids_and_paths(self):
  for key,row in OPS.items():
   self.assertRegex(key,r'^[a-z][a-z0-9_]{0,99}$')
   self.assertRegex(row['path'],r'^/[A-Za-z0-9_{}./-]+$')
   self.assertNotIn('..',row['path']);self.assertNotIn('?',row['path']);self.assertNotIn('://',row['path'])
   self.assertTrue(row['source'].startswith('https://www.abcp.ru/d/docs/'))
   self.assertTrue(row['documentation']);self.assertFalse(row['live_verified'])
 def test_credentials_not_agent_parameters(self):
  reserved={'userlogin','userpsw','siteHash','accessHash','sitelogin','sitepsw'}
  for row in OPS.values():self.assertFalse(reserved.intersection(row['parameters']['properties']))
 def test_scalar_request_fields_not_response_models(self):
  for path,name in [('/articles/info','brand'),('/cp/users','dateUpdatedStart'),('/cp/ts/orders/list','agreementId'),('/cp/finance/payments','userId')]:
   param=self.op(path)['parameters']['properties'][name]
   self.assertNotIn(param.get('type'),('object','array'));self.assertNotIn('properties',param)
  param=self.op('/cp/distributor/status','POST')['parameters']['properties']['status']
  self.assertNotEqual(param.get('type'),'object')
 def test_post_reads(self):
  reads=['/search/batch','/advices/batch','/cp/catalog/search','/cp/articles/info/batch','/ts/supplierOrders/orders/list','/ts/supplierOrders/positions/list','/cp/ts/supplierOrders/orders/list','/cp/ts/supplierOrders/positions/list']
  self.assertEqual({x['path'] for x in OPS.values() if x['method']=='POST' and x['effect']=='read'},set(reads))
 def test_get_payment_links_are_guarded(self):
  for path in ('/cp/payment/token','/cp/payment/top-balance-link'):
   self.assertEqual(self.op(path)['effect'],'business_write');self.assertIn('get_with_side_effect',self.op(path)['risk'])
 def test_json_exception(self):
  self.assertEqual([x['path'] for x in OPS.values() if x['encoding']=='json'],['/advices/batch'])
 def test_upload_credentials_and_file_schema(self):
  for path,location in [('/cp/distributor/pricelistUpdate','body'),('/cp/productCards/import','query'),('/cp/usercatalogs/{catalogId}/upload','query'),('/vinquery/add','body')]:
   row=self.op(path,'POST');self.assertEqual(row['encoding'],'multipart');self.assertEqual(row['auth_location'],location)
   self.assertTrue(row['file_fields'])
   for name in row['file_fields']:
    self.assertEqual(row['parameters']['properties'][name]['required'],['filename','content_base64'])
 def test_vinqu_hash_alias(self):
  row=self.op('/brands/get');self.assertEqual(row['auth_field_map'],{'siteHash':'hash'});self.assertNotIn('hash',row['parameters']['properties'])
  self.assertEqual(self.op('/vinquery/addComment','POST')['auth_location'],'body')
 def test_partial_commit_is_explicit(self):
  for path in ('/basket/order','/orders/instant'):
   row=self.op(path,'POST');self.assertTrue(row['response_semantics']['partial_commit_on_failure']);self.assertEqual(row['response_semantics']['created_objects_path'],'$.orders')
  self.assertTrue(self.op('/cp/orders/online','POST')['response_semantics']['false_may_have_committed'])
 def test_public_credential_recovery_and_archive(self):
  for path in ('/user/new','/user/restore'):self.assertEqual(self.op(path,'POST')['auth_location'],'none')
  restore=self.op('/user/restore','POST')['parameters'];self.assertNotIn('required',restore);self.assertEqual(len(restore['anyOf']),2)
  for path in ('/cp/orders/fromArchive','/cp/orders/toArchive'):self.assertEqual(self.op(path,'POST')['response_kind'],'empty_or_json')
 def test_nested_request_and_additional_filters(self):
  row=self.op('/cp/onlinePayments');self.assertEqual(row['parameters']['properties']['filter']['type'],'object')
  row=self.op('/cp/ts/logs/read');self.assertIn('paymentIds',row['parameters']['properties'])
  row=self.op('/vinquery/add','POST');self.assertIn('guestInfo',row['parameters']['properties'])
  row=self.op('/cp/user/shipmentAddressZones/new','POST');self.assertIn('isOnDay1',row['parameters']['properties']);self.assertNotIn('isOnDay',row['parameters']['properties'])
 def test_capability_parity_and_no_unverified_claim(self):
  caps=json.loads((ROOT/'registry/capabilities/abcp.json').read_text())
  self.assertEqual(caps['total'],287);self.assertEqual({x['id'] for x in caps['capabilities']},set(OPS))
  for row in caps['capabilities']:
   self.assertEqual(row['adapter'],row['id']);self.assertEqual(row['access'],'unknown_not_tested')
 def test_garage_admin_prose_and_json_strings(self):
  for path,method in [('/user/garage','GET'),('/user/garage/car','GET'),('/user/garage/add','POST'),('/user/garage/update','POST'),('/user/garage/delete','POST')]:
   self.assertIn('userId',self.op(path,method)['parameters']['properties'])
  garage=self.op('/user/garage/add','POST')['parameters'];self.assertNotIn('vin',garage.get('required',[]));self.assertEqual(len(garage['anyOf']),3)
  row=self.op('/cp/ts/orderPickings/fastGetOut','POST');self.assertEqual(row['parameters']['properties']['orderPickingResellerData']['type'],'string')
 def test_binary_export_and_empty_chat(self):
  self.assertEqual(self.op('/cp/productCards/export/file')['response_kind'],'binary_or_json')
  self.assertEqual(self.op('/vinquery/chatList')['response_semantics']['empty_response'],{'http_status':404,'message':'messages not found'})

if __name__=='__main__':unittest.main(verbosity=2)
