from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.organizacao.models import Setor, Funcao, Trabalhador, UsuarioSetor
from .models import Tarefa
from .orientacao import proximo_passo
from .services import alocar_dias


class PrimeiroUsoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('configurar_perfis', stdout=StringIO())
        cls.setor = Setor.objects.create(nome='Soldagem permitida')
        cls.outro = Setor.objects.create(nome='Montagem oculta')
        cls.usuarios = {}
        for perfil in ('Líder', 'Coordenador', 'Consulta', 'Administrador'):
            u = get_user_model().objects.create_user(username=perfil, is_staff=True)
            u.groups.add(Group.objects.get(name=perfil))
            UsuarioSetor.objects.create(usuario=u, setor=cls.setor)
            cls.usuarios[perfil] = u

    def setUp(self):
        self.clock = patch('apps.planejamento.orientacao.timezone.localdate', return_value=date(2026, 11, 18))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.lider = self.usuarios['Líder']

    def equipe(self, setor=None, ativo=True):
        f, _ = Funcao.objects.get_or_create(nome='Soldagem')
        return Trabalhador.objects.create(nome='Pessoa teste', setor_principal=setor or self.setor,
                                         funcao_principal=f, ativo=ativo)

    def tarefa(self, setor=None):
        return Tarefa.objects.create(titulo='Atividade teste', setor=setor or self.setor,
                                    inicio_previsto=date(2026, 11, 1), fim_previsto=date(2026, 11, 30))

    def alocar(self, trabalhador, tarefa, dia=date(2026, 11, 18)):
        return alocar_dias(ator=self.usuarios['Administrador'], trabalhador=trabalhador,
                          tarefa=tarefa, datas=[dia], funcao_desempenhada=trabalhador.funcao_principal)

    def test_progressao_reavaliada_sem_criar_dados_automaticamente(self):
        self.assertEqual(proximo_passo(self.lider)['estado'], 'configuracao')
        Funcao.objects.create(nome='Soldagem')
        self.assertEqual(proximo_passo(self.lider)['estado'], 'equipe')
        trabalhador = self.equipe()
        self.assertEqual(proximo_passo(self.lider)['estado'], 'tarefas')
        tarefa = self.tarefa()
        self.assertEqual(proximo_passo(self.lider)['estado'], 'alocacoes')
        self.alocar(trabalhador, tarefa)
        self.assertEqual(proximo_passo(self.lider)['estado'], 'pronto')
        self.client.force_login(self.lider)
        r = self.client.get('/app/')
        self.assertContains(r, 'Continue pela semana planejada')
        self.assertContains(r, 'Organizar alocações no Admin')
        self.assertEqual(Trabalhador.objects.count(), 1)
        self.assertEqual(Tarefa.objects.count(), 1)

    def test_ctas_respeitam_perfil_e_politica_consulta(self):
        Funcao.objects.create(nome='Soldagem')
        consulta = self.usuarios['Consulta']
        consulta.user_permissions.add(Permission.objects.get(codename='add_trabalhador'))
        for perfil in ('Líder', 'Consulta', 'Coordenador', 'Administrador'):
            with self.subTest(perfil=perfil):
                orientacao = proximo_passo(self.usuarios[perfil])
                if perfil in ('Líder', 'Consulta'):
                    self.assertIsNone(orientacao['url'])
                    self.assertIn('Coordenador ou Administrador', orientacao['ajuda'])
                else:
                    self.assertEqual(orientacao['url'], reverse('admin:organizacao_trabalhador_add'))

    def test_funcao_exige_administrador_e_sem_staff_nao_recebe_admin(self):
        for perfil in ('Líder', 'Coordenador', 'Consulta'):
            self.assertIsNone(proximo_passo(self.usuarios[perfil])['url'])
        self.assertEqual(proximo_passo(self.usuarios['Administrador'])['url'], reverse('admin:organizacao_funcao_add'))
        admin = self.usuarios['Administrador']
        admin.is_staff = False
        admin.save()
        self.assertIsNone(proximo_passo(admin)['url'])

    def test_sem_setor_nao_usa_dados_de_outros_setores(self):
        self.equipe(self.outro)
        self.tarefa(self.outro)
        UsuarioSetor.objects.filter(usuario=self.lider).delete()
        self.client.force_login(self.lider)
        r = self.client.get('/app/')
        self.assertContains(r, 'Confira seu acesso aos setores')
        self.assertNotContains(r, 'Montagem oculta')
        self.assertNotContains(r, 'Prepare a equipe')
        self.assertEqual(proximo_passo(self.lider, setor_id=self.outro.pk)['estado'], 'acesso')

    def test_sem_setores_administrador_recebe_configuracao(self):
        UsuarioSetor.objects.all().delete()
        self.setor.delete()
        self.outro.delete()
        self.assertEqual(proximo_passo(self.usuarios['Administrador'])['url'], reverse('admin:organizacao_setor_add'))
        self.assertEqual(proximo_passo(self.lider)['estado'], 'acesso')

    def test_dados_fora_do_escopo_nao_avancam_etapas(self):
        self.equipe(self.outro)
        self.tarefa(self.outro)
        self.assertEqual(proximo_passo(self.lider)['estado'], 'equipe')
        self.equipe()
        self.assertEqual(proximo_passo(self.lider)['estado'], 'tarefas')

    def test_trabalhador_inativo_e_tarefa_encerrada_nao_indicam_prontidao(self):
        self.equipe(ativo=False)
        self.assertEqual(proximo_passo(self.lider)['estado'], 'equipe')
        self.equipe()
        tarefa = self.tarefa()
        tarefa.status = Tarefa.Status.CANCELADA
        tarefa.save(ator=self.lider)
        self.assertEqual(proximo_passo(self.lider)['estado'], 'tarefas')

    def test_sem_permissao_de_leitura_nao_informa_existencia(self):
        self.equipe()
        self.tarefa()
        self.lider.groups.clear()
        self.assertEqual(proximo_passo(self.lider)['estado'], 'acesso')

    def test_admin_distingue_busca_sem_resultados_de_lista_vazia(self):
        self.client.force_login(self.lider)
        for nome, texto in (('organizacao_trabalhador', 'Ainda não há trabalhadores cadastrados'),
                            ('planejamento_tarefa', 'Ainda não há tarefas cadastradas'),
                            ('planejamento_alocacao', 'Ainda não há alocações')):
            r = self.client.get(reverse(f'admin:{nome}_changelist'))
            self.assertContains(r, texto)
            self.assertContains(r, 'Próximo passo')
        trabalhador = self.equipe()
        tarefa = self.tarefa()
        self.alocar(trabalhador, tarefa)
        for nome in ('organizacao_trabalhador', 'planejamento_tarefa', 'planejamento_alocacao'):
            r = self.client.get(reverse(f'admin:{nome}_changelist'), {'q':'inexistente'})
            self.assertContains(r, 'Nenhum resultado para estes filtros')
            self.assertContains(r, 'Limpar busca e filtros')
            self.assertNotContains(r, 'Faça o primeiro planejamento')

    def test_lista_vazia_nao_considera_registros_ocultos(self):
        self.equipe(self.outro)
        self.client.force_login(self.lider)
        r = self.client.get(reverse('admin:organizacao_trabalhador_changelist'))
        self.assertContains(r, 'Ainda não há trabalhadores cadastrados')
        self.assertNotContains(r, 'Há registros nos seus setores')
        self.assertNotContains(r, 'Montagem oculta')

    def test_quadro_distingue_semana_vazia_e_filtro_de_setor(self):
        trabalhador = self.equipe()
        tarefa = self.tarefa()
        self.alocar(trabalhador, tarefa)
        self.client.force_login(self.lider)
        url = reverse('planejamento:quadro_semanal')
        r = self.client.get(url, {'semana':'2026-11-23'})
        self.assertContains(r, 'Ainda não há alocações nesta semana')
        self.assertNotContains(r, 'O setor selecionado não tem')
        UsuarioSetor.objects.create(usuario=self.lider, setor=self.outro)
        r = self.client.get(url, {'semana':'2026-11-18', 'setor':self.outro.pk})
        self.assertContains(r, 'O setor selecionado não tem alocações nesta semana')
        r = self.client.get(url, {'semana':'2026-11-18', 'setor':999999})
        self.assertEqual(r.status_code, 400)
        self.assertNotContains(r, 'Próximo passo', status_code=400)

    def test_planejamento_vazio_orienta_sem_modificar_formulario(self):
        self.client.force_login(self.lider)
        r = self.client.get(reverse('admin:planejamento_alocacao_varios_dias'))
        self.assertContains(r, 'Prepare as funções')
        self.assertContains(r, 'name="trabalhador"')
        self.assertContains(r, 'Administrador')
        self.assertNotContains(r, 'Cadastrar função no Admin')
