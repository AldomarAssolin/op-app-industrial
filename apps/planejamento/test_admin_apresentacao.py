from django.contrib.auth import get_user_model
from django.test import TestCase
from django.templatetags.static import static
from django.urls import reverse

from apps.organizacao.models import Setor


class ApresentacaoAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser(username='admin_ui')
        cls.setor = Setor.objects.create(nome='Soldagem de teste')

    def test_extensao_preserva_telas_nativas_e_retorno_na_mesma_sessao(self):
        self.client.force_login(self.usuario)
        for nome, args in (('admin:index', []),
                           ('admin:app_list', ['organizacao']),
                           ('admin:app_list', ['planejamento']),
                           ('admin:organizacao_setor_changelist', []),
                           ('admin:organizacao_setor_change', [self.setor.pk]),
                           ('admin:password_change', [])):
            with self.subTest(tela=nome):
                r = self.client.get(reverse(nome, args=args))
                self.assertContains(r, 'Voltar à área de trabalho')
                self.assertContains(r, 'href="/app/"')
                self.assertContains(r, 'Administração do OP-APP')
                self.assertContains(r, static('planejamento/css/admin.css'))
                self.assertContains(r, static('admin/js/theme.js'))
                self.assertContains(r, static('admin/css/dark_mode.css'))
                self.assertContains(r, reverse('admin:logout'))
                if nome == 'admin:index':
                    self.assertContains(r, 'op-admin-home')
                    self.assertContains(r, 'id="recent-actions-module"')
                else:
                    self.assertNotContains(r, 'op-admin-home')
                if nome == 'admin:app_list':
                    self.assertContains(r, 'op-admin-app-index')
                    self.assertNotContains(r, 'id="recent-actions-module"')
                else:
                    self.assertNotContains(r, 'op-admin-app-index')
        self.assertEqual(self.client.get(reverse('entrada_operacional')).status_code, 200)
        self.assertEqual(self.client.session['_auth_user_id'], str(self.usuario.pk))

    def test_login_e_popup_preservam_fluxo_sem_link_de_sessao(self):
        r = self.client.get(reverse('admin:login'))
        self.assertContains(r, 'Administração do OP-APP')
        self.assertContains(r, 'name="password"')
        self.assertNotContains(r, 'Voltar à área de trabalho')
        self.client.force_login(self.usuario)
        r = self.client.get(reverse('admin:organizacao_setor_add'), {'_popup':'1'})
        self.assertContains(r, 'name="nome"')
        self.assertNotContains(r, 'Voltar à área de trabalho')
