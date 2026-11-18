from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class PaginasPublicasTests(SimpleTestCase):
    @override_settings(OP_APP_PUBLIC_PAGES_ENABLED=False)
    def test_publicacao_desativada_por_padrao(self):
        for nome in ("inicio", "privacidade"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 404)

    @override_settings(OP_APP_PUBLIC_PAGES_ENABLED=True, OP_APP_SUPPORT_EMAIL="")
    def test_paginas_nao_publicam_contato_vazio_ou_invalido(self):
        for email in ("", "endereco-invalido"):
            with self.settings(OP_APP_SUPPORT_EMAIL=email):
                for nome in ("inicio", "privacidade"):
                    self.assertEqual(self.client.get(reverse(nome)).status_code, 404)

    @override_settings(OP_APP_PUBLIC_PAGES_ENABLED=True,
                       OP_APP_SUPPORT_EMAIL="suporte@example.com")
    def test_textos_publicos_sem_login_ou_banco_e_com_vinculo_privacidade(self):
        # SimpleTestCase impede consultas ao banco, inclusive indiretas.
        inicio = self.client.get(reverse("inicio"))
        self.assertContains(inicio, "OP-APP Backups")
        self.assertContains(inicio, f'href="{reverse("privacidade")}"')
        privacidade = self.client.get(reverse("privacidade"))
        self.assertContains(privacidade, "drive.file")
        self.assertContains(privacidade, "mailto:suporte@example.com")
        self.assertContains(privacidade, "https://myaccount.google.com/connections")
        self.assertNotIn("sessionid", privacidade.cookies)
        self.assertNotIn("csrftoken", privacidade.cookies)

    @override_settings(OP_APP_PUBLIC_PAGES_ENABLED=True,
                       OP_APP_SUPPORT_EMAIL="suporte@example.com")
    def test_paginas_nao_abrem_consulta_operacional(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)
        resposta = self.client.get(reverse("planejamento:quadro_semanal"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("admin:login"), resposta["Location"])
