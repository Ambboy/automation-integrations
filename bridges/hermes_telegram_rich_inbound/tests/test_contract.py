"""Version-scoped executable compatibility gate. Re-review before changing pins."""
import inspect
from pathlib import Path
import subprocess
import unittest

import telegram
from telegram.ext import BaseHandler, Application
from hermes_cli.plugins import PluginContext
from hermes_cli.version_info import get_version_info
from plugins.platforms.telegram import adapter

CORE_SHA = 'bf0203a794a07aac3ff764972ab9087baa4e4f4e'

class ContractTests(unittest.TestCase):
    def test_reviewed_versions_and_checkout(self):
        self.assertEqual(telegram.__version__, '22.8')
        self.assertEqual(get_version_info().base_version, '0.22.5')
        core = Path(adapter.__file__).resolve().parents[3]
        actual = subprocess.check_output(['git', '-C', str(core), 'rev-parse', 'HEAD'], text=True).strip()
        self.assertEqual(actual, CORE_SHA, 'Unreviewed core SHA: rerun/review all behavior tests before updating pin')

    def test_public_contract(self):
        for name in ('register_platform_handler', 'register_telegram_handler', 'on_unload'):
            self.assertTrue(callable(getattr(PluginContext, name)))
        self.assertEqual(list(inspect.signature(BaseHandler.handle_update).parameters),
                         ['self', 'update', 'application', 'check_result', 'context'])
        for name in ('add_handler', 'remove_handler'):
            self.assertTrue(callable(getattr(Application, name)))
        self.assertTrue(callable(telegram.Update.de_json))
        self.assertTrue(callable(telegram.Update.to_dict))
