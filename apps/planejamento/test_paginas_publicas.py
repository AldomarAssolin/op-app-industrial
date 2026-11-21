from django.test import SimpleTestCase, override_settings
from django.urls import reverse


@override_settings(OP_APP_PRODUCT_HOME_ENABLED=False)
class PaginasPublicasTests(SimpleTestCase):
    @override_settings(OP_APP_PUBLIC_PAGES_ENABLED=False)
    def test_publicacao_desativada_por_padrao(self):
        for nome in ("inicio", "privacidade", "integracao_backup"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 404)

    @override_settings(OP_APP_PUBLIC_PAGES_ENABLED=True, OP_APP_SUPPORT_EMAIL="")
    def test_paginas_nao_publicam_contato_vazio_ou_invalido(self):
        for email in ("", "endereco-invalido"):
            with self.settings(OP_APP_SUPPORT_EMAIL=email):
                for nome in ("inicio", "privacidade", "integracao_backup"):
                    self.assertEqual(self.client.get(reverse(nome)).status_code, 404)

    @override_settings(OP_APP_PUBLIC_PAGES_ENABLED=True,
                       OP_APP_SUPPORT_EMAIL="suporte@example.com")
    def test_textos_publicos_sem_login_ou_banco_e_com_vinculo_privacidade(self):
        # SimpleTestCase impede consultas ao banco, inclusive indiretas.
        inicio = self.client.get(reverse("inicio"))
        self.assertContains(inicio, "OP-APP Backups")
        self.assertContains(inicio, f'href="{reverse("privacidade")}"')
        integracao = self.client.get(reverse("integracao_backup"))
        self.assertContains(integracao, "OP-APP Backups")
        self.assertContains(integracao, "drive.file")
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
        self.assertIn(reverse("login_operacional"), resposta["Location"])


@override_settings(OP_APP_PRODUCT_HOME_ENABLED=True)
class ApresentacaoProdutoTests(SimpleTestCase):
    def test_produto_independe_da_integracao_e_contato_e_nao_consulta_banco(self):
        # Consultas de sessão/usuário/ORM também falham neste SimpleTestCase.
        with self.settings(OP_APP_PUBLIC_PAGES_ENABLED=False, OP_APP_SUPPORT_EMAIL=""):
            resposta = self.client.get(reverse("inicio"))
            self.assertContains(resposta, "A semana organizada.")
            self.assertContains(resposta, "EXEMPLO FICTÍCIO")
            self.assertContains(resposta, f'href="{reverse("login_operacional")}"')
            self.assertNotContains(resposta, "OP-APP Backups")
            self.assertNotContains(resposta, "mailto:")
            self.assertEqual(self.client.get(reverse("privacidade")).status_code, 404)
            self.assertEqual(self.client.get(reverse("integracao_backup")).status_code, 404)
        self.assertNotIn("sessionid", resposta.cookies)
        self.assertNotIn("csrftoken", resposta.cookies)

    def test_integracao_habilitada_fica_em_pagina_propria_e_rodape(self):
        with self.settings(OP_APP_PUBLIC_PAGES_ENABLED=True, OP_APP_SUPPORT_EMAIL="suporte@example.com"):
            resposta = self.client.get(reverse("inicio"))
            conteudo = resposta.content.decode().split('<main id="conteudo"', 1)[1].split('</main>', 1)[0]
            self.assertNotIn("backup", conteudo.lower())
            self.assertNotIn("OAuth", conteudo)
            self.assertContains(resposta, f'href="{reverse("integracao_backup")}"')
            self.assertContains(resposta, f'href="{reverse("privacidade")}"')
            integracao = self.client.get(reverse("integracao_backup"))
            self.assertContains(integracao, "drive.file")
            self.assertContains(integracao, f'href="{reverse("privacidade")}"')
            self.assertContains(self.client.get(reverse("privacidade")), "mailto:suporte@example.com")

    def test_contato_invalido_nao_quebra_produto_nem_publica_integracao(self):
        with self.settings(OP_APP_PUBLIC_PAGES_ENABLED=True, OP_APP_SUPPORT_EMAIL="invalido"):
            self.assertEqual(self.client.get(reverse("inicio")).status_code, 200)
            self.assertEqual(self.client.get(reverse("integracao_backup")).status_code, 404)
            self.assertEqual(self.client.get(reverse("privacidade")).status_code, 404)

    def test_apresentacao_nao_amplia_acesso_e_paginas_so_aceitam_leitura(self):
        resposta = self.client.get(reverse("planejamento:quadro_semanal"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login_operacional"), resposta["Location"])
        with self.settings(OP_APP_PUBLIC_PAGES_ENABLED=True, OP_APP_SUPPORT_EMAIL="suporte@example.com"):
            for nome in ("inicio", "privacidade", "integracao_backup"):
                self.assertEqual(self.client.head(reverse(nome)).status_code, 200)
                self.assertEqual(self.client.post(reverse(nome)).status_code, 405)
