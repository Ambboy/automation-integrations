"""The ETM exception must not weaken other providers or forge message consent."""
from copy import deepcopy
import hashlib
import unittest

from automation_integrations.etm_authorization import owner_command


class EtmAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.config = {'etm_order_authorization': 'owner_command'}
        self.scope = ['owner', 'owner', 'session', 'topic']
        self.text_hash = hashlib.sha256('Доделай заказ'.encode()).hexdigest()
        self.context = {'scope': list(self.scope), 'message_id': 'inbound-42',
                        'owner_message': {'source': 'native_owner_telegram',
                                          'message_id': 'inbound-42',
                                          'scope': list(self.scope),
                                          'text_sha256': self.text_hash}}

    def authorize(self, operation='order_checkout', params=None, service='etm'):
        return owner_command(self.context, self.config, service, operation,
                             {} if params is None else params)

    def test_current_native_message_authorizes_procurement_and_has_no_plaintext(self):
        for operation in ('order_checkout', 'invoice_order', 'invoice_delivery',
                          'delivery_point_create', 'invoice_print'):
            with self.subTest(operation=operation):
                evidence = self.authorize(operation)
                self.assertEqual(evidence, {'policy': 'owner_command',
                                           'message_id': 'inbound-42',
                                           'text_sha256': self.text_hash})
                self.assertNotIn('scope', evidence)
                self.assertNotIn('text', evidence)

    def test_policy_requires_explicit_exact_setting(self):
        for value in (None, False, True, '', 'confirmed', 'OWNER_COMMAND', ['owner_command']):
            with self.subTest(value=value):
                self.config['etm_order_authorization'] = value
                self.assertIsNone(self.authorize())
        self.config = {}
        self.assertIsNone(self.authorize())

    def test_missing_or_model_claimed_provenance_cannot_authorize(self):
        for provenance in (None, True, 'native_owner_telegram', {},
                           {'source': 'model', 'confirmed': True}):
            with self.subTest(provenance=provenance):
                self.context['owner_message'] = provenance
                self.context['confirmed'] = True
                self.assertIsNone(self.authorize())
        self.context.pop('owner_message')
        self.assertIsNone(self.authorize())

    def test_evidence_cannot_move_to_a_different_message_or_scope(self):
        original = deepcopy(self.context)
        for field, value in (
                ('source', 'quoted_history'), ('message_id', 'inbound-41'),
                ('scope', ['owner', 'owner', 'session', 'other-topic']),
                ('scope', ['owner', 'owner', 'another-session', 'topic']),
                ('scope', ['other', 'other', 'session', 'topic']),
                ('scope', tuple(self.scope))):
            with self.subTest(field=field, value=value):
                self.context = deepcopy(original)
                self.context['owner_message'][field] = value
                self.assertIsNone(self.authorize())
        self.context = original
        self.context['message_id'] = 'inbound-43'
        self.assertIsNone(self.authorize())

    def test_malformed_hash_empty_text_and_unexpected_provenance_are_rejected(self):
        original = deepcopy(self.context)
        for value in (None, True, '', 'a' * 63, 'g' * 64, 'a' * 65,
                      'A' * 64, 'a' * 64 + '\n', hashlib.sha256(b'').hexdigest()):
            with self.subTest(value=value):
                self.context = deepcopy(original)
                self.context['owner_message']['text_sha256'] = value
                self.assertIsNone(self.authorize())
        self.context = original
        self.context['owner_message']['confirmed'] = True
        self.assertIsNone(self.authorize())

    def test_invalid_owner_context_cannot_be_repaired_by_matching_provenance(self):
        original = deepcopy(self.context)
        for scope in ([], ['owner'] * 3, [''] * 4,
                      ['owner', 'group', 'session', 'topic'],
                      ['owner', 'owner', '', 'topic'],
                      ['owner', 'owner', 'session', 0], tuple(self.scope)):
            with self.subTest(scope=scope):
                self.context = deepcopy(original)
                self.context['scope'] = scope
                self.context['owner_message']['scope'] = scope
                self.assertIsNone(self.authorize())
        for message in ('', ' ', None, True, 42):
            with self.subTest(message=message):
                self.context = deepcopy(original)
                self.context['message_id'] = message
                self.context['owner_message']['message_id'] = message
                self.assertIsNone(self.authorize())

    def test_order_creation_and_confirmation_allowed_but_replacement_refusal_not(self):
        for action in ('P', 'A'):
            with self.subTest(action=action):
                self.assertIsNotNone(self.authorize('invoice_create',
                    {'body': {'DocumentFunctionCode': action}}))
        for action in ('C', 'D', None, '', 'p', True, ['P']):
            with self.subTest(action=action):
                self.assertIsNone(self.authorize('invoice_create',
                    {'body': {'DocumentFunctionCode': action}}))
        for params in ({}, {'body': None}, {'body': 'P'}):
            self.assertIsNone(self.authorize('invoice_create', params))

    def test_other_providers_and_other_etm_actions_keep_explicit_confirmation(self):
        for service in ('tochka', 'saby', 'wirenboard', 'yandex_go', '', None, ['etm']):
            with self.subTest(service=service):
                self.assertIsNone(self.authorize(service=service))
        for operation in ('catalog_job_create', 'invoice_approval_update', 'goods_get',
                          'order_cancel', 'sample_write', None, ['order_checkout']):
            with self.subTest(operation=operation):
                self.assertIsNone(self.authorize(operation))

    def test_helper_does_not_modify_its_inputs_and_handles_nonobjects(self):
        expected = deepcopy((self.context, self.config))
        self.authorize()
        self.assertEqual((self.context, self.config), expected)
        self.assertIsNone(owner_command(None, self.config, 'etm', 'order_checkout', {}))
        self.assertIsNone(owner_command(self.context, None, 'etm', 'order_checkout', {}))
        self.assertIsNone(owner_command(self.context, self.config, 'etm', 'order_checkout', []))


if __name__ == '__main__':
    unittest.main()
