from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class DeploymentTests(SimpleTestCase):
    def test_sonda_nao_depende_de_banco_ou_login(self):
        # SimpleTestCase proíbe acesso ao banco, inclusive indireto.
        resposta = self.client.get(reverse("health"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})
        self.assertEqual(self.client.post(reverse("health")).status_code, 405)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_sonda_interna_nao_redireciona_mas_admin_exige_https(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)
        resposta = self.client.get(reverse("admin:login"))
        self.assertEqual(resposta.status_code, 301)
        self.assertTrue(resposta["Location"].startswith("https://"))

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False)
    def test_css_admin_e_servido_sem_runserver_ou_debug(self):
        resposta = self.client.get("/static/admin/css/base.css")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("text/css", resposta["Content-Type"])
        corpo = b"".join(resposta.streaming_content)
        self.assertIn(b"body", corpo)
