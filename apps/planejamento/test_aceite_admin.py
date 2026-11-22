from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.organizacao.models import Funcao
from .models import TurnoTarefa
from .test_fluxo_operacional import FixtureFluxo
from . import test_autorizacao_turnos as fixtures


@override_settings(OP_APP_TURNOS_ENABLED=True)
class AceiteAdminTests(FixtureFluxo, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.preparar()

    def setUp(self):
        clock = patch('apps.organizacao.turnos.timezone.localdate', return_value=self.hoje)
        clock.start()
        self.addCleanup(clock.stop)

    def tarefa_url(self, tarefa):
        return reverse('admin:planejamento_tarefa_change', args=[tarefa.pk])

    def test_links_readonly_respeitam_perfil_sem_ocultar_valores(self):
        setor_url = reverse('admin:organizacao_setor_change', args=[self.a.pk])
        usuario_url = reverse('admin:auth_user_change', args=[self.c1.pk])
        self.client.force_login(self.l1)
        pagina = self.client.get(self.tarefa_url(self.f1))
        self.assertContains(pagina, self.a.nome)
        self.assertContains(pagina, self.c1.username)
        self.assertNotContains(pagina, f'href="{setor_url}"')
        self.assertNotContains(pagina, f'href="{usuario_url}"')
        self.client.force_login(self.c1)
        pagina = self.client.get(self.tarefa_url(self.f1))
        self.assertContains(pagina, f'href="{setor_url}"')
        self.assertNotContains(pagina, f'href="{usuario_url}"')
        self.client.force_login(self.root)
        pagina = self.client.get(self.tarefa_url(self.f1))
        self.assertContains(pagina, f'href="{usuario_url}"')

    def test_403_amigavel_mantem_status_e_nao_expoe_dados(self):
        self.client.force_login(self.l1)
        for debug in (True, False):
            with self.subTest(debug=debug), override_settings(DEBUG=debug):
                for url in (reverse('admin:organizacao_setor_add'),
                            reverse('admin:auth_user_change', args=[self.c2.pk])):
                    resposta = self.client.get(url)
                    self.assertContains(resposta, 'Acesso não permitido', status_code=403)
                    self.assertContains(resposta, 'Voltar à área de trabalho', status_code=403)
                    self.assertNotContains(resposta, self.c2.username, status_code=403)

    def test_historico_renderiza_nomes_escapados_sem_json(self):
        atividade = Funcao.objects.create(nome='QA Montagem <script>alert(1)</script>')
        self.f1.save(ator=self.c1, atividades=[self.funcao, atividade])
        self.client.force_login(self.c1)
        resposta = self.client.get(self.tarefa_url(self.f1))
        self.assertContains(resposta, 'QA Montagem &lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(resposta, '<script>alert(1)</script>')
        self.assertNotContains(resposta, '&quot;id&quot;')
        historico = next(i for i in resposta.context['inline_admin_formsets'] if i.opts.model._meta.model_name == 'historicotarefa')
        self.assertIn('atividades_resumo', historico.opts.fields)
        self.assertNotIn('atividades', historico.opts.fields)
        self.assertIn(atividade.nome, [a['nome'] for a in self.f1.historico.latest('pk').atividades])

    def test_coordenador_ve_turnos_extras_em_get_antes_e_depois_do_erro(self):
        from apps.organizacao.models import Turno
        TurnoTarefa(tarefa=self.comum, turno=Turno.objects.get(pk='T3')).save(ator=self.c1)
        esperados = set(TurnoTarefa.objects.filter(tarefa=self.comum).values_list('pk', flat=True))
        self.client.force_login(self.c1)
        url = self.tarefa_url(self.comum)
        pagina = self.client.get(url)
        inline = next(i for i in pagina.context['inline_admin_formsets'] if i.opts.model is TurnoTarefa)
        self.assertEqual(set(inline.formset.get_queryset().values_list('pk', flat=True)), esperados)
        self.assertEqual(inline.formset.initial_form_count(), len(esperados))
        helper = fixtures.AutorizacaoTurnosTests.dados_admin_tarefa
        _, dados = helper(self, self.comum)
        dados['atividades_da_tarefa'] = [self.funcao.pk]
        prefixo = inline.formset.prefix
        for n, formulario in enumerate(inline.formset.forms):
            dados[f'{prefixo}-{n}-turno'] = formulario.instance.turno_id
            if formulario.instance.ativo:
                dados[f'{prefixo}-{n}-ativo'] = 'on'
        n = len(esperados)
        dados[f'{prefixo}-TOTAL_FORMS'] = str(n+1)
        dados[f'{prefixo}-{n}-turno'] = 'T3'
        dados[f'{prefixo}-{n}-ativo'] = 'on'
        erro = self.client.post(url, dados)
        self.assertEqual(erro.status_code,200)
        fs = next(i.formset for i in erro.context['inline_admin_formsets'] if i.opts.model is TurnoTarefa)
        self.assertTrue(fs.errors or fs.non_form_errors())
        novamente = self.client.get(url)
        fs = next(i.formset for i in novamente.context['inline_admin_formsets'] if i.opts.model is TurnoTarefa)
        self.assertEqual(set(fs.get_queryset().values_list('pk', flat=True)), esperados)
        self.assertEqual(TurnoTarefa.objects.filter(tarefa=self.comum).count(), len(esperados))
        self.client.force_login(self.l1)
        pagina = self.client.get(url)
        self.assertFalse(any(i.opts.model is TurnoTarefa for i in pagina.context['inline_admin_formsets']))
