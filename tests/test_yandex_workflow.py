import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from automation_integrations.api_read import Failure, validate, HTTP
from automation_integrations.api_write import process
from tests.test_api_catalog import FakeVault, FakeHTTP

ROUTE=[{'geopoint':[37.5,55.7],'fullname':'Public point A'},{'geopoint':[37.6,55.8],'fullname':'Public point B'}]
PARAMS={'user_id':'user-test','class':'econom','route':ROUTE}
QUOTE={'offer':'fake-offer','service_levels':[{'class':'econom','price':'100 RUB','is_fixed_price':True}]}
RULES={'can_cancel':True,'state':'free','title':'Free','message':'No fee'}
ORDER={'id':'order-test','status':'pending','cancel_rules':RULES}

class YandexWorkflow(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.config={'state_dir':self.tmp.name,'yandex_client_id':'test-company'}
  self.context={'scope':['owner','owner','private-thread','thread-1'],'message_id':'1'}
  self.vault=FakeVault()
 def run_req(self,request,http=None,context=None,now=100):
  return process(request,context or self.context,self.config,http=http,vault=self.vault,clock=lambda:now)
 def prepare(self,op='order_create',http=None):
  return self.run_req({'action':'prepare','operation':op,'params':PARAMS if op=='order_create' else {'order_id':'order-test'}},http or FakeHTTP(QUOTE if op=='order_create' else ORDER))
 def confirm(self,draft,msg='2',now=100):
  return self.run_req({'action':'confirm','confirmation_text':'ПОДТВЕРЖДАЮ '+draft['draft_id']},context={**self.context,'message_id':msg},now=now)
 def test_create_requires_separate_exact_owner_confirmation_and_verifies(self):
  d=self.prepare();network=FakeHTTP({'order_id':'order-test'},ORDER)
  with self.assertRaises(Failure) as denied:self.run_req({'action':'execute','draft_id':d['draft_id']},network)
  self.assertEqual(denied.exception.code,'owner_confirmation_required');self.assertEqual(network.calls,[])
  with self.assertRaises(Failure):self.confirm(d,msg='1')
  self.confirm(d)
  result=self.run_req({'action':'execute','draft_id':d['draft_id']},network)
  self.assertEqual(result['status'],'verified');self.assertEqual(network.calls[0][0],('POST','/orders/create'))
  self.assertEqual(network.calls[0][1]['headers']['X-Idempotency-Token'],d['draft_id'])
  self.assertEqual(network.calls[1][1]['query'],{'order_id':'order-test'})
  self.run_req({'action':'execute','draft_id':d['draft_id']},network);self.assertEqual(len(network.calls),2)
 def test_no_model_boolean_or_wrong_scope_can_confirm(self):
  d=self.prepare()
  for req in [{'action':'execute','draft_id':d['draft_id'],'confirmed':True},{'action':'confirm','confirmation_text':'yes'},{'action':'confirm','confirmation_text':'Quote: ПОДТВЕРЖДАЮ '+d['draft_id']}]:
   with self.assertRaises(Failure):self.run_req(req)
  context={'scope':['owner','owner','different-thread','thread-1'],'message_id':'2'}
  with self.assertRaises(Failure):self.run_req({'action':'confirm','confirmation_text':'ПОДТВЕРЖДАЮ '+d['draft_id']},context=context)
  with self.assertRaises(Failure):self.confirm(d,now=701)
 def test_timeout_no_blind_replay_manual_recovery_reuses_same_token(self):
  d=self.prepare();self.confirm(d);network=FakeHTTP(Failure('request_timeout'))
  result=self.run_req({'action':'execute','draft_id':d['draft_id']},network);self.assertEqual(result['status'],'outcome_unknown')
  with self.assertRaises(Failure):self.run_req({'action':'execute','draft_id':d['draft_id']},network)
  self.assertEqual(len(network.calls),1)
  self.confirm(d,msg='3');again=FakeHTTP({'order_id':'order-test'},ORDER)
  self.run_req({'action':'execute','draft_id':d['draft_id']},again)
  self.assertEqual(network.calls[0][1]['headers']['X-Idempotency-Token'],again.calls[0][1]['headers']['X-Idempotency-Token'])
 def test_verification_failure_retains_exact_id_and_only_reads_on_status(self):
  d=self.prepare();self.confirm(d);network=FakeHTTP({'order_id':'order-test'},Failure('request_timeout'))
  result=self.run_req({'action':'execute','draft_id':d['draft_id']},network);self.assertEqual(result['status'],'accepted_unverified')
  recovery=FakeHTTP(ORDER);result=self.run_req({'action':'status','draft_id':d['draft_id']},recovery)
  self.assertEqual(result['status'],'verified');self.assertEqual(recovery.calls[0][0][0],'GET')
 def test_cancel_checks_conditions_before_and_exact_object_after(self):
  d=self.prepare('order_cancel');self.confirm(d)
  network=FakeHTTP(ORDER,{'status':'cancelled'},{'id':'order-test','status':'cancelled'})
  result=self.run_req({'action':'execute','draft_id':d['draft_id']},network)
  self.assertEqual(result['status'],'verified');self.assertEqual([a[0][0] for a in network.calls],['GET','POST','GET'])
  self.assertEqual(network.calls[1][1]['body'],{'state':'free'})
 def test_changed_cancel_fee_and_wrong_returned_object_block(self):
  d=self.prepare('order_cancel');self.confirm(d)
  network=FakeHTTP({**ORDER,'cancel_rules':{**RULES,'state':'paid'}})
  with self.assertRaises(Failure):self.run_req({'action':'execute','draft_id':d['draft_id']},network)
  self.assertEqual(len(network.calls),1)
  with self.assertRaises(Failure):self.prepare('order_cancel',FakeHTTP({**ORDER,'id':'other'}))
 def test_crash_marker_does_not_repeat_mutation_and_payload_is_immutable(self):
  d=self.prepare();p=Path(self.tmp.name)/'yandex-writes'/(d['draft_id']+'.json');row=json.loads(p.read_text());row['status']='submitting';p.write_text(json.dumps(row))
  result=self.run_req({'action':'status','draft_id':d['draft_id']});self.assertEqual(result['status'],'outcome_unknown')
  row['payload']['class']='vip';p.write_text(json.dumps(row))
  with self.assertRaises(Failure):self.confirm(d)
 def test_strict_read_schema_and_unsupported_flights(self):
  for p in [{'route':[[0,0],[0,91]]},{'route':[[True,0],[1,1]]},{'route':[[0,0],[0,0]]},{'route':[[0,0],[1,1]],'unknown':1},{'route':[[float('nan'),0],[1,1]]}]:
   with self.assertRaises(Failure):validate({'service':'yandex_go','operation':'routestats','params':p})
  for o,err in [('flight_search','unsupported_operation'),('order_create','write_tool_required'),('food_list','missing_parameter')]:
   with self.assertRaises(Failure) as e:validate({'service':'yandex_go','operation':o})
   self.assertEqual(e.exception.code,err)
 def test_rate_limit_cooldown_is_persistent_and_no_network_retry(self):
  h=HTTP('yandex_go',self.config);h.rate_gate(cooldown=30)
  with patch('urllib.request.build_opener') as opener,self.assertRaises(Failure) as e:h.call('GET','/users')
  self.assertEqual(e.exception.code,'rate_limited');opener.return_value.open.assert_not_called()
 def test_nonfixed_offer_cannot_be_booked(self):
  with self.assertRaises(Failure):self.prepare(http=FakeHTTP({'offer':'fake','service_levels':[{'class':'econom','price':'100 RUB','is_fixed_price':False}]}))
 def test_changed_offer_is_rejected_without_retry(self):
  d=self.prepare();self.confirm(d);network=FakeHTTP(Failure('offer_expired_or_price_changed',406,provider_code='PRICE_CHANGED'))
  result=self.run_req({'action':'execute','draft_id':d['draft_id']},network)
  self.assertEqual(result['status'],'rejected');self.assertEqual(result['provider_code'],'PRICE_CHANGED')
  self.run_req({'action':'execute','draft_id':d['draft_id']},network);self.assertEqual(len(network.calls),1)
 def test_uncertain_cancel_reconciles_without_second_post(self):
  d=self.prepare('order_cancel');self.confirm(d);network=FakeHTTP(ORDER,Failure('request_timeout'))
  self.assertEqual(self.run_req({'action':'execute','draft_id':d['draft_id']},network)['status'],'outcome_unknown')
  with self.assertRaises(Failure):self.confirm(d,msg='3')
  recovery=FakeHTTP({'id':'order-test','status':'cancelled'})
  self.assertEqual(self.run_req({'action':'status','draft_id':d['draft_id']},recovery)['status'],'verified')
  self.assertEqual(recovery.calls[0][0][0],'GET')
 def test_concurrent_execute_serializes_one_mutation(self):
  from concurrent.futures import ThreadPoolExecutor
  d=self.prepare();self.confirm(d);network=FakeHTTP({'order_id':'order-test'},ORDER)
  with ThreadPoolExecutor(2) as pool:
   results=list(pool.map(lambda _:self.run_req({'action':'execute','draft_id':d['draft_id']},network),range(2)))
  self.assertTrue(all(r['status']=='verified' for r in results));self.assertEqual(len(network.calls),2)
 def test_new_draft_cannot_bypass_uncertain_submit_even_after_expiry(self):
  d=self.prepare();self.confirm(d)
  self.run_req({'action':'execute','draft_id':d['draft_id']},FakeHTTP(Failure('request_timeout')))
  network=FakeHTTP()
  result=self.run_req({'action':'prepare','operation':'order_create','params':PARAMS},network,now=99999)
  self.assertFalse(result['ok']);self.assertEqual(result['error'],'existing_unresolved_draft')
  self.assertEqual(result['draft_id'],d['draft_id']);self.assertEqual(network.calls,[])
