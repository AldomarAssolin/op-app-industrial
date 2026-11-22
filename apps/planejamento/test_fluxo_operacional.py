from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from urllib.parse import urlencode, parse_qs, urlsplit
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection, close_old_connections
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from apps.organizacao.models import Trabalhador, VinculoLiderTurno
from . import test_autorizacao_turnos as fixtures_turnos
from .models import Alocacao, Tarefa, ConfirmacaoPlanejamento, HistoricoTurnoAlocacao
from .fluxo import revisar_planejamento, confirmar_planejamento
from .forms import PlanejarForm
from .services import montar_quadro_semanal


class FixtureFluxo:
    hoje = fixtures_turnos.AutorizacaoTurnosTests.hoje
    usuario = classmethod(fixtures_turnos.AutorizacaoTurnosTests.usuario.__func__)
    worker = classmethod(fixtures_turnos.AutorizacaoTurnosTests.worker.__func__)
    task = classmethod(fixtures_turnos.AutorizacaoTurnosTests.task.__func__)
    alloc = classmethod(fixtures_turnos.AutorizacaoTurnosTests.alloc.__func__)

    @classmethod
    def preparar(cls):
        with patch('apps.organizacao.turnos.timezone.localdate', return_value=cls.hoje):
            fixtures_turnos.AutorizacaoTurnosTests.setUpTestData.__func__(cls)
            cls.w3 = cls.worker('Segunda pessoa T1', cls.a, cls.c1, cls.t1)

    def dados(self, **extras):
        return {'tarefa':str(self.comum.pk), 'trabalhadores':[str(self.w1.pk),str(self.w3.pk)],
            'inicio':str(self.hoje+timedelta(days=2)), 'fim':str(self.hoje+timedelta(days=5)),
            'dias_semana':['0','1','2','3'], 'turno':'T1', 'atividades':[str(self.funcao.pk)],
            'observacao':'Planejamento de teste', **extras}

    def revisar(self, ator=None, **extras):
        ator = ator or self.l1
        form = PlanejarForm(self.dados(**extras), ator=ator)
        self.assertTrue(form.is_valid(), form.errors)
        return revisar_planejamento(ator=ator, dados=form.cleaned_data)


@override_settings(OP_APP_TURNOS_ENABLED=True)
class FluxoOperacionalTests(FixtureFluxo, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.preparar()

    def setUp(self):
        clock = patch('apps.organizacao.turnos.timezone.localdate', return_value=self.hoje)
        clock.start()
        self.addCleanup(clock.stop)
        self.url = reverse('planejamento:planejar')
        self.client.force_login(self.l1)

    def test_periodo_visivel_e_trabalhadores_com_checkboxes_no_escopo(self):
        resposta = self.client.get(self.url, {'tarefa':self.comum.pk, 'inicio':'2026-11-23'})
        self.assertContains(resposta, 'data-inicio="2026-11-11"')
        self.assertContains(resposta, 'data-fim="2026-12-21"')
        self.assertContains(resposta, '11/11/2026 a 21/12/2026')
        self.assertContains(resposta, 'type="checkbox" name="trabalhadores"')
        self.assertNotContains(resposta, '<select name="trabalhadores"')
        self.assertNotContains(resposta, self.wb.nome)
        self.assertNotContains(resposta, self.w2.nome)
        self.assertContains(resposta, 'planejamento/js/planejar.')
        self.assertNotContains(resposta, 'planejamento/js/turno_trabalhador.')

    def test_erro_de_periodo_preserva_pessoas_e_informa_limites_sem_gravar(self):
        antes = Alocacao.objects.count()
        resposta = self.client.post(self.url, self.dados(fim='2026-12-24'))
        self.assertContains(resposta, 'período previsto da tarefa: 11/11/2026 a 21/12/2026')
        for pessoa in (self.w1, self.w3):
            self.assertContains(resposta, f'value="{pessoa.pk}"')
        self.assertEqual(set(resposta.context['form']['trabalhadores'].value()), {str(self.w1.pk),str(self.w3.pk)})
        self.assertContains(resposta, 'checked')
        self.assertEqual(Alocacao.objects.count(), antes)
        self.assertIsNone(resposta.context['revisao'])

    def test_multiplas_atividades_nao_duplicam_equipe_e_aparecem_no_quadro(self):
        from apps.organizacao.models import Funcao
        montagem = Funcao.objects.create(nome='Montagem')
        revisao = self.revisar(atividades=[self.funcao.pk, montagem.pk])
        self.assertEqual(len(revisao['linhas']), 8)
        recibo, novo = confirmar_planejamento(ator=self.l1, token=revisao['token'])
        self.assertTrue(novo)
        self.assertEqual(recibo.quantidade, 8)
        for alocacao in Alocacao.objects.filter(tarefa=self.comum):
            self.assertEqual({a.pk for a in alocacao.atividades_da_tarefa}, {self.funcao.pk, montagem.pk})
        quadro = self.client.get(reverse('planejamento:quadro_semanal'), {'semana':'2026-11-23'})
        self.assertContains(quadro, 'Atividades da tarefa')
        self.assertContains(quadro, 'Soldagem, Montagem')
        confirmar_planejamento(ator=self.l1, token=revisao['token'])
        self.assertEqual(Alocacao.objects.filter(tarefa=self.comum).count(), 8)

    def test_selecao_atividades_obrigatoria_e_opcao_invalida_nao_grava(self):
        for atividades in ([], ['999999']):
            resposta = self.client.post(self.url, self.dados(atividades=atividades))
            self.assertEqual(resposta.status_code, 200)
            self.assertIn('atividades', resposta.context['form'].errors)
            self.assertIsNone(resposta.context['revisao'])
        self.assertFalse(ConfirmacaoPlanejamento.objects.exists())

    def test_atividade_alterada_apos_revisao_exige_nova_conferencia(self):
        from apps.organizacao.models import Funcao
        atividade = Funcao.objects.create(nome='Montagem')
        token = self.revisar(atividades=[self.funcao.pk, atividade.pk])['token']
        atividade.nome = 'Montagem final'
        atividade.save()
        resposta = self.client.post(self.url, {'confirmacao':token})
        self.assertContains(resposta, 'Os dados mudaram')
        self.assertFalse(ConfirmacaoPlanejamento.objects.exists())
        self.assertEqual(set(resposta.context['form']['atividades'].value()), {self.funcao.pk, atividade.pk})

    def test_correcao_preserva_e_permite_alterar_conjunto_sem_duplicar(self):
        from apps.organizacao.models import Funcao
        atividade = Funcao.objects.create(nome='Montagem')
        confirmar_planejamento(ator=self.l1, token=self.revisar(atividades=[self.funcao.pk, atividade.pk])['token'])
        alocacao = Alocacao.objects.filter(tarefa=self.comum).first()
        url = reverse('planejamento:corrigir_alocacao', args=[alocacao.pk])
        pagina = self.client.get(url)
        self.assertEqual(set(pagina.context['form']['atividades'].value()), {self.funcao.pk, atividade.pk})
        resposta = self.client.post(url, {'versao':pagina.context['form']['versao'].value(),
            'trabalhador':alocacao.trabalhador_id, 'data':alocacao.data.isoformat(),
            'atividades':[atividade.pk], 'observacao':'Revisão de atividades'})
        self.assertEqual(resposta.status_code,302)
        alocacao.refresh_from_db()
        self.assertEqual([a.pk for a in alocacao.atividades_da_tarefa], [atividade.pk])
        self.assertEqual(Alocacao.objects.filter(tarefa=self.comum).count(),8)

    def test_cadastro_funcoes_explica_atividades_na_listagem_e_no_formulario(self):
        self.client.force_login(self.root)
        for nome in ('admin:organizacao_funcao_changelist', 'admin:organizacao_funcao_add'):
            resposta = self.client.get(reverse(nome))
            self.assertContains(resposta, 'Funções são as atividades necessárias à tarefa')
            self.assertContains(resposta, 'não avalia competências')

    def test_atividade_adicional_protegida_e_rollback_do_conjunto(self):
        from apps.organizacao.models import Funcao
        from django.db.models.deletion import ProtectedError
        from .models import AtividadeAlocacao
        atividade = Funcao.objects.create(nome='Montagem')
        revisao = self.revisar(atividades=[self.funcao.pk, atividade.pk])
        original = Alocacao.save
        def falhar(obj, *args, **kwargs):
            if obj.trabalhador_id == self.w3.pk:
                raise ValidationError('Falha controlada')
            return original(obj, *args, **kwargs)
        with patch.object(Alocacao, 'save', falhar), self.assertRaises(ValidationError):
            confirmar_planejamento(ator=self.l1, token=revisao['token'])
        self.assertFalse(AtividadeAlocacao.objects.exists())
        self.assertFalse(ConfirmacaoPlanejamento.objects.exists())
        confirmar_planejamento(ator=self.l1, token=revisao['token'])
        with self.assertRaises(ProtectedError):
            atividade.delete()

    def test_revisao_nao_grava_confirmacao_atomica_e_reenvio_idempotente(self):
        antes = Alocacao.objects.count()
        pagina = self.client.post(self.url, self.dados())
        self.assertContains(pagina, '8 alocações')
        self.assertEqual(Alocacao.objects.count(), antes)
        token = pagina.context['revisao']['token']
        resposta = self.client.post(self.url, {'confirmacao':token})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('2026-11-23', resposta.url)
        self.assertEqual(Alocacao.objects.count(), antes+8)
        self.assertEqual(ConfirmacaoPlanejamento.objects.get().quantidade, 8)
        self.assertEqual(set(Alocacao.objects.filter(tarefa=self.comum).values_list('criado_por_id',flat=True)), {self.l1.pk})
        self.assertEqual(self.client.post(self.url, {'confirmacao':token}).status_code,302)
        self.assertEqual(Alocacao.objects.count(), antes+8)

    def test_duas_tarefas_no_mesmo_dia_permanecem_possiveis(self):
        self.alloc(self.w1, self.f1, self.c1, self.t1, self.hoje+timedelta(days=2))
        recibo, novo = confirmar_planejamento(ator=self.l1,token=self.revisar()['token'])
        self.assertTrue(novo)
        self.assertEqual(recibo.quantidade,8)
        self.assertEqual(Alocacao.objects.filter(trabalhador=self.w1,data=self.hoje+timedelta(days=2)).count(),2)

    def test_duplicidade_em_um_dia_rejeita_lote_sem_recibo(self):
        revisao = self.revisar()
        self.alloc(self.w3,self.comum,self.c1,self.t1,self.hoje+timedelta(days=3))
        antes = Alocacao.objects.count()
        with self.assertRaises(ValidationError):
            confirmar_planejamento(ator=self.l1,token=revisao['token'])
        self.assertEqual(Alocacao.objects.count(),antes)
        self.assertFalse(ConfirmacaoPlanejamento.objects.exists())

    def test_rollback_de_falha_no_meio_do_lote_inclui_historico(self):
        revisao = self.revisar()
        antes, historico = Alocacao.objects.count(), HistoricoTurnoAlocacao.objects.count()
        original = Alocacao.save
        def falhar(obj,*args,**kwargs):
            if obj.trabalhador_id == self.w3.pk:
                raise ValidationError('Falha controlada')
            return original(obj,*args,**kwargs)
        with patch.object(Alocacao,'save',falhar), self.assertRaises(ValidationError):
            confirmar_planejamento(ator=self.l1,token=revisao['token'])
        self.assertEqual(Alocacao.objects.count(),antes)
        self.assertEqual(HistoricoTurnoAlocacao.objects.count(),historico)
        self.assertFalse(ConfirmacaoPlanejamento.objects.exists())

    def test_tarefa_alterada_apos_revisao_exige_nova_conferencia(self):
        token=self.revisar()['token']
        t=Tarefa.objects.get(pk=self.comum.pk)
        t.titulo='Título atualizado'
        t.save(ator=self.c1)
        resposta=self.client.post(self.url,{'confirmacao':token})
        self.assertContains(resposta,'Os dados mudaram')
        self.assertFalse(ConfirmacaoPlanejamento.objects.exists())
        self.assertEqual(resposta.context['form']['observacao'].value(),'Planejamento de teste')

    def test_estado_inatividade_e_revogacao_sao_revalidados(self):
        for caso in ('status','inativo','revogacao'):
            with self.subTest(caso=caso):
                token=self.revisar()['token']
                if caso=='status':
                    self.comum.status='CANCELADA';self.comum.save(ator=self.c1)
                elif caso=='inativo':
                    self.w3.ativo=False;self.w3.save(ator=self.c1)
                else:
                    self.v1.ativo=False;self.v1.save(ator=self.c1)
                with self.assertRaises((ValidationError,PermissionDenied)):
                    confirmar_planejamento(ator=self.l1,token=token)
                self.assertFalse(ConfirmacaoPlanejamento.objects.exists())
                if caso=='status':
                    self.comum.status='PENDENTE';self.comum.save(ator=self.c1)
                elif caso=='inativo':
                    self.w3.ativo=True;self.w3.save(ator=self.c1)

    def test_token_adulterado_expirado_e_de_outra_conta_rejeitados(self):
        token=self.revisar()['token']
        with self.assertRaises(ValidationError):
            confirmar_planejamento(ator=self.l1,token=token+'x')
        with self.assertRaises(ValidationError):
            confirmar_planejamento(ator=self.l2,token=token)
        with patch('django.core.signing.time.time',return_value=99999999999),self.assertRaises(ValidationError):
            confirmar_planejamento(ator=self.l1,token=token)
        self.assertFalse(ConfirmacaoPlanejamento.objects.exists())

    def test_opcoes_e_post_nao_expoem_outro_turno_ou_setor(self):
        pagina=self.client.get(self.url)
        self.assertNotContains(pagina,'Pessoa T2 oculta')
        self.assertNotContains(pagina,'Pessoa B oculta')
        resposta=self.client.post(self.url,self.dados(trabalhadores=[self.w2.pk]))
        self.assertEqual(resposta.status_code,200)
        self.assertIsNone(resposta.context['revisao'])
        self.assertNotContains(resposta,'Pessoa T2 oculta')
        self.assertFalse(ConfirmacaoPlanejamento.objects.exists())

    def test_consulta_e_csrf_e_metodos(self):
        self.client.force_login(self.consulta)
        self.consulta.user_permissions.add(Permission.objects.get(codename='add_alocacao'))
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.client.force_login(self.l1)
        self.assertEqual(self.client.put(self.url).status_code,405)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.l1)
        self.assertEqual(csrf.post(self.url,self.dados()).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code,302)

    def test_limite_e_dias_invalidos(self):
        form=PlanejarForm(self.dados(inicio='2026-11-26',fim='2026-11-23'),ator=self.l1)
        self.assertFalse(form.is_valid())
        form=PlanejarForm(self.dados(dias_semana=['9']),ator=self.l1)
        self.assertFalse(form.is_valid())

    def test_filtros_combinados_dia_relativo_e_retorno_entre_semanas(self):
        dia=self.hoje+timedelta(days=2)
        a=self.alloc(self.w1,self.comum,self.c1,self.t1,dia)
        self.alloc(self.w2,self.comum,self.c1,self.t2,dia)
        self.client.force_login(self.c1)
        params={'semana':str(dia),'setor':self.a.pk,'turno':'T1','trabalhador':self.w1.pk,
                'tarefa':self.comum.pk,'dia':'0','status':'PENDENTE','fim_semana':'on'}
        pagina=self.client.get(reverse('planejamento:quadro_semanal'),params)
        self.assertEqual(pagina.status_code,200)
        self.assertEqual(len(pagina.context['colunas']),1)
        self.assertFalse(pagina.context['mostrar_fim_semana'])
        self.assertEqual(pagina.context['colunas'][0]['data'],dia)
        self.assertEqual(len(pagina.context['linhas']),1)
        consulta=parse_qs(urlsplit(pagina.context['url_proxima']).query)
        self.assertEqual(consulta['dia'],['0'])
        self.assertEqual(consulta['semana'],['2026-11-30'])
        self.assertContains(pagina,'estado atual da tarefa')
        self.assertIn('retorno=',pagina.context['linhas'][0]['celulas'][0]['url_corrigir'])
        limpar=parse_qs(urlsplit(pagina.context['url_limpar']).query)
        self.assertEqual(set(limpar),{'semana'})

    def test_filtros_indevidos_e_limites_da_consulta(self):
        url=reverse('planejamento:quadro_semanal')
        for chave,valor in (('setor',self.b.pk),('tarefa',self.fb.pk),('trabalhador',self.wb.pk),('turno','T3'),('dia','7'),('status','invalido')):
            with self.subTest(chave=chave):
                r=self.client.get(url,{'semana':str(self.hoje),chave:valor})
                self.assertEqual(r.status_code,400)
                self.assertNotContains(r,'Pessoa B oculta',status_code=400)
        with self.assertRaises(PermissionDenied):
            montar_quadro_semanal(ator=self.l1,semana=self.hoje,trabalhador_id=self.wb.pk)

    def test_filtro_sem_resultado_distingue_semana_vazia(self):
        url=reverse('planejamento:quadro_semanal')
        r=self.client.get(url,{'semana':str(self.hoje),'status':'CONCLUIDA'})
        self.assertContains(r,'combinação de filtros')
        r=self.client.get(url,{'semana':str(self.hoje+timedelta(days=30))})
        self.assertNotContains(r,'Nenhuma alocação corresponde à combinação')

    def test_quadro_historico_conserva_trabalhador_que_mudou_habitual(self):
        from apps.organizacao.turnos import revisar_troca_turno,confirmar_troca_turno
        revisao=revisar_troca_turno(ator=self.c1,trabalhador_id=self.w1.pk,turno_id='T2',vigencia=self.hoje+timedelta(days=1))
        confirmar_troca_turno(ator=self.c1,confirmacao=revisao['confirmacao'])
        with patch('apps.organizacao.turnos.timezone.localdate',return_value=self.hoje+timedelta(days=2)):
            r=self.client.get(reverse('planejamento:quadro_semanal'),{'semana':str(self.hoje),'trabalhador':self.w1.pk})
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'Pessoa T1')

    def test_correcao_preserva_contexto_e_demais_dias(self):
        outra=self.alloc(self.w1,self.f1,self.c1,self.t1,self.hoje+timedelta(days=2))
        url=reverse('planejamento:corrigir_alocacao',args=[self.al1.pk])
        retorno=urlencode({'semana':str(self.hoje),'turno':'T1','dia':'5'})
        pagina=self.client.get(url,{'retorno':retorno})
        versao=pagina.context['form']['versao'].value()
        resposta=self.client.post(url,{'versao':versao,'retorno':retorno,'trabalhador':self.w1.pk,
            'data':str(self.hoje),'atividades':[self.funcao.pk],'observacao':'Corrigido'})
        self.assertEqual(resposta.status_code,302)
        self.assertIn('turno=T1',resposta.url)
        self.assertIn('dia=5',resposta.url)
        self.al1.refresh_from_db();outra.refresh_from_db()
        self.assertEqual(self.al1.observacao,'Corrigido')
        self.assertNotEqual(outra.observacao,'Corrigido')
        self.assertEqual(self.al1.alterado_por,self.l1)

    def test_correcao_stale_e_url_oculta_nao_gravam(self):
        url=reverse('planejamento:corrigir_alocacao',args=[self.al1.pk])
        versao=self.client.get(url).context['form']['versao'].value()
        obj=Alocacao.objects.get(pk=self.al1.pk);obj.observacao='Mais recente';obj.save(ator=self.c1)
        r=self.client.post(url,{'versao':versao,'trabalhador':self.w1.pk,'data':str(self.hoje),
            'atividades':[self.funcao.pk],'observacao':'Antigo'})
        self.assertContains(r,'A alocação mudou')
        obj.refresh_from_db();self.assertEqual(obj.observacao,'Mais recente')
        self.assertEqual(self.client.get(reverse('planejamento:corrigir_alocacao',args=[self.al2.pk])).status_code,404)

    def test_correcao_em_tarefa_encerrada_reapresenta_erro_sem_500(self):
        for status in ('CANCELADA', 'CONCLUIDA'):
            with self.subTest(status=status):
                tarefa=self.task('Tarefa para encerrar '+status,self.a,self.c1,self.t1)
                alocacao=self.alloc(self.w1,tarefa,self.c1,self.t1)
                url=reverse('planejamento:corrigir_alocacao',args=[alocacao.pk])
                versao=self.client.get(url).context['form']['versao'].value()
                if status=='CONCLUIDA':
                    tarefa.status='EM_ANDAMENTO';tarefa.save(ator=self.c1)
                tarefa.status=status;tarefa.save(ator=self.c1)
                resposta=self.client.post(url,{'versao':versao,'trabalhador':self.w1.pk,
                    'tarefa':self.fb.pk,'data':str(self.hoje),
                    'atividades':[self.funcao.pk],'observacao':'Não salvar'})
                self.assertContains(resposta,'Reabra a tarefa')
                alocacao.refresh_from_db()
                self.assertEqual(alocacao.tarefa_id,tarefa.pk)
                self.assertNotEqual(alocacao.observacao,'Não salvar')
                self.assertNotContains(resposta,'Tarefa B oculta')

    def test_remocao_exige_post_preserva_outros_dias_e_historico(self):
        url=reverse('planejamento:remover_alocacao',args=[self.al1.pk])
        pagina=self.client.get(url)
        self.assertTrue(Alocacao.objects.filter(pk=self.al1.pk).exists())
        r=self.client.post(url,{'versao':pagina.context['versao']})
        self.assertEqual(r.status_code,302)
        self.assertFalse(Alocacao.objects.filter(pk=self.al1.pk).exists())
        self.assertTrue(Alocacao.objects.filter(pk=self.al2.pk).exists())
        self.assertTrue(HistoricoTurnoAlocacao.objects.filter(trabalhador=self.w1,tarefa=self.f1,alocacao__isnull=True).exists())

    def test_consulta_nao_recebe_correcao_e_post_forjado_rejeita(self):
        self.client.force_login(self.consulta)
        self.consulta.user_permissions.add(Permission.objects.get(codename='change_alocacao'))
        url=reverse('planejamento:corrigir_alocacao',args=[self.al1.pk])
        self.assertEqual(self.client.get(url).status_code,403)
        pagina=self.client.get(reverse('planejamento:quadro_semanal'),{'semana':str(self.hoje)})
        self.assertNotContains(pagina,'>Corrigir</a>')
        self.assertNotContains(pagina,'>Remover</a>')

    @override_settings(OP_APP_TURNOS_ENABLED=False)
    def test_fluxo_preserva_compatibilidade_sem_turnos(self):
        r=self.revisar(ator=self.c1)
        recibo,novo=confirmar_planejamento(ator=self.c1,token=r['token'])
        self.assertTrue(novo)
        self.assertEqual(recibo.quantidade,8)
        self.assertFalse(Alocacao.objects.filter(tarefa=self.comum).exclude(turno=None).exists())


@skipUnless(connection.vendor=='postgresql','Concorrência exige PostgreSQL')
@override_settings(OP_APP_TURNOS_ENABLED=True)
class FluxoConcorrenciaTests(FixtureFluxo,TransactionTestCase):
    def setUp(self):
        clock=patch('apps.organizacao.turnos.timezone.localdate',return_value=self.hoje)
        clock.start();self.addCleanup(clock.stop)
        self.preparar()

    def test_confirmacoes_identicas_concorrentes_gravam_um_lote(self):
        token=self.revisar()['token'];barreira=Barrier(2,timeout=10)
        def confirmar():
            close_old_connections()
            try:
                ator=get_user_model().objects.get(pk=self.l1.pk)
                barreira.wait()
                return confirmar_planejamento(ator=ator,token=token)[1]
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a,b=pool.submit(confirmar),pool.submit(confirmar)
            self.assertEqual(sorted([a.result(timeout=30),b.result(timeout=30)]),[False,True])
        self.assertEqual(ConfirmacaoPlanejamento.objects.count(),1)
        self.assertEqual(Alocacao.objects.filter(tarefa=self.comum).count(),8)
