from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizacao.models import Setor, UsuarioSetor


class EntradaOperacionalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('configurar_perfis', stdout=StringIO())
        cls.setor = Setor.objects.create(nome='Soldagem autorizada')
        cls.oculto = Setor.objects.create(nome='Montagem reservada')
        cls.usuarios = {}
        for grupo in ('Consulta', 'Líder', 'Coordenador', 'Administrador'):
            user = get_user_model().objects.create_user(username=grupo, password='senha-descartavel-24', is_staff=True)
            user.groups.add(Group.objects.get(name=grupo))
            UsuarioSetor.objects.create(usuario=user, setor=cls.setor)
            cls.usuarios[grupo] = user

    def test_anonimo_precisa_entrar(self):
        self.assertRedirects(self.client.get(reverse('entrada_operacional')),
                             reverse('login_operacional') + '?next=/app/')

    def test_login_padrao_e_next_interno(self):
        for next_url, esperado in (('', '/app/'), ('/planejamento/semanal/?semana=2026-11-23', '/planejamento/semanal/?semana=2026-11-23'), ('/admin/planejamento/tarefa/', '/admin/planejamento/tarefa/')):
            with self.subTest(next=next_url):
                self.client.logout()
                resposta = self.client.post(reverse('login_operacional'), {'username':'Líder', 'password':'senha-descartavel-24', 'next':next_url})
                self.assertEqual(resposta.status_code, 302)
                self.assertEqual(resposta['Location'], esperado)

    def test_next_externo_ou_downgrade_nao_e_usado(self):
        for destino in ('https://externo.example/app/', '//externo.example/', 'http://testserver/app/', 'javascript:alert(1)', '///externo.example/'):
            with self.subTest(next=destino):
                self.client.logout()
                r = self.client.post(reverse('login_operacional'), {'username':'Líder','password':'senha-descartavel-24','next':destino}, secure=True)
                self.assertEqual(r['Location'], '/app/')

    def test_login_invalido_e_inativo(self):
        for desativar in (False, True):
            user = self.usuarios['Líder']
            user.is_active = not desativar
            user.save()
            r = self.client.post(reverse('login_operacional'), {'username':'Líder','password':'senha-descartavel-24' if desativar else 'incorreta'})
            self.assertEqual(r.status_code, 200)
            self.assertNotIn('_auth_user_id', self.client.session)

    def test_acoes_e_setores_por_perfil(self):
        for grupo, user in self.usuarios.items():
            with self.subTest(grupo=grupo):
                self.client.force_login(user)
                r = self.client.get('/app/')
                self.assertContains(r, 'Soldagem autorizada')
                self.assertContains(r, 'Conectado como')
                if grupo == 'Administrador':
                    self.assertContains(r, 'Montagem reservada')
                else:
                    self.assertNotContains(r, 'Montagem reservada')
                self.assertContains(r, reverse('planejamento:quadro_semanal'))
                if grupo == 'Consulta':
                    self.assertNotContains(r, reverse('admin:planejamento_alocacao_changelist'))
                    self.assertNotContains(r, 'Planejar')
                else:
                    self.assertContains(r, reverse('admin:planejamento_alocacao_changelist'))
                if grupo in ('Coordenador', 'Administrador'):
                    self.assertContains(r, reverse('admin:organizacao_trabalhador_add'))
                else:
                    self.assertNotContains(r, reverse('admin:organizacao_trabalhador_add'))
                self.assertNotContains(r, reverse('admin:organizacao_setor_add'))
                self.assertNotContains(r, reverse('admin:organizacao_funcao_add'))

    def test_consulta_com_permissao_isolada_nao_recebe_acao_de_gravacao(self):
        user = self.usuarios['Consulta']
        user.user_permissions.add(Permission.objects.get(codename='add_alocacao'))
        self.client.force_login(user)
        self.assertNotContains(self.client.get('/app/'), 'Planejar')
        self.assertEqual(self.client.get(reverse('admin:planejamento_alocacao_add')).status_code, 403)

    def test_sem_setor_orienta_responsavel_sem_expor_dados(self):
        user = self.usuarios['Líder']
        UsuarioSetor.objects.filter(usuario=user).delete()
        self.client.force_login(user)
        r = self.client.get('/app/')
        self.assertContains(r, 'Nenhum setor autorizado')
        self.assertContains(r, 'responsável pelo OP-APP')
        for texto in ('Soldagem autorizada', 'Montagem reservada', 'Planejar', 'superusuário'):
            self.assertNotContains(r, texto)

    def test_sem_staff_pode_consultar_sem_receber_links_do_admin(self):
        user = self.usuarios['Consulta']
        user.is_staff = False
        user.save()
        self.client.force_login(user)
        r = self.client.get('/app/')
        self.assertContains(r, reverse('planejamento:quadro_semanal'))
        self.assertNotContains(r, 'href="/admin/')
        self.assertEqual(self.client.get(reverse('planejamento:quadro_semanal')).status_code, 200)

    def test_sem_permissoes_nao_recebe_acoes(self):
        user = self.usuarios['Líder']
        user.groups.clear()
        self.client.force_login(user)
        r = self.client.get('/app/')
        self.assertContains(r, 'Sua conta ainda não tem ações disponíveis')
        self.assertNotContains(r, 'href="/planejamento/semanal/')
        self.assertEqual(self.client.get(reverse('planejamento:quadro_semanal')).status_code, 403)

    def test_logout_exige_post_e_csrf_e_encerra_sessao(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuarios['Líder'])
        self.assertEqual(client.get(reverse('logout_operacional')).status_code, 405)
        self.assertEqual(client.post(reverse('logout_operacional')).status_code, 403)
        client.get('/app/')
        r = client.post(reverse('logout_operacional'), {'csrfmiddlewaretoken':client.cookies['csrftoken'].value})
        self.assertEqual(r['Location'], reverse('login_operacional'))
        self.assertNotIn('_auth_user_id', client.session)
        self.assertEqual(client.get('/app/').status_code, 302)

    def test_login_exige_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('login_operacional'), {'username':'Líder','password':'senha-descartavel-24'}).status_code, 403)

    def test_quadro_compartilha_navegacao_sem_ampliar_acoes(self):
        self.client.force_login(self.usuarios['Consulta'])
        r = self.client.get(reverse('planejamento:quadro_semanal'))
        self.assertContains(r, 'Navegação operacional')
        self.assertContains(r, reverse('entrada_operacional'))
        self.assertNotContains(r, 'Abrir alocações no Admin')
