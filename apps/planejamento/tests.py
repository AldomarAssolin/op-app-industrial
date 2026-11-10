from django.test import TestCase

from django.apps import apps
from django.test import SimpleTestCase, TestCase
from django.db import connection
from django.contrib.auth import get_user_model
from django.urls import reverse


class PlanejamentoConfigTests(SimpleTestCase):
    """Verifica o registro do aplicativo planejamento."""

    def test_app_esta_registrado(self):
        app_config = apps.get_app_config("planejamento")

        self.assertEqual(
            app_config.name,
            "apps.planejamento",
        )

    def test_app_utiliza_configuracao_correta(self):
        app_config = apps.get_app_config("planejamento")

        self.assertEqual(
            app_config.__class__.__name__,
            "PlanejamentoConfig",
        )


class DatabaseTests(TestCase):
    """Valida a integração do Django com PostgreSQL."""

    def test_backend_postgresql_configurado(self):
        self.assertEqual(
            connection.vendor,
            "postgresql",
        )

    def test_banco_aceita_consulta_sql(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            resultado = cursor.fetchone()

        self.assertEqual(resultado[0], 1)

    def test_persistencia_de_usuario(self):
        User = get_user_model()

        User.objects.create_user(
            username="teste_op_app",
            password="senha_teste_local_123",
        )

        usuario = User.objects.get(
            username="teste_op_app",
        )

        self.assertTrue(
            usuario.check_password("senha_teste_local_123")
        )


class AuthenticationTests(TestCase):
    """Valida o mecanismo nativo de autenticação."""

    def test_login_com_credenciais_validas(self):
        User = get_user_model()

        User.objects.create_user(
            username="coordenador_teste",
            password="senha_teste_local_123",
        )

        autenticado = self.client.login(
            username="coordenador_teste",
            password="senha_teste_local_123",
        )

        self.assertTrue(autenticado)

    def test_admin_exige_autenticacao(self):
        resposta = self.client.get(
            reverse("admin:index")
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(
            reverse("admin:login"),
            resposta["Location"],
        )
