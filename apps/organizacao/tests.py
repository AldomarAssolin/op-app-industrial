from django.test import TestCase

from django.apps import apps
from django.test import SimpleTestCase


class OrganizacaoConfigTests(SimpleTestCase):
    """Verifica o registro do aplicativo organizacao."""

    def test_app_esta_registrado(self):
        app_config = apps.get_app_config("organizacao")

        self.assertEqual(
            app_config.name,
            "apps.organizacao",
        )

    def test_app_utiliza_configuracao_correta(self):
        app_config = apps.get_app_config("organizacao")

        self.assertEqual(
            app_config.__class__.__name__,
            "OrganizacaoConfig",
        )
