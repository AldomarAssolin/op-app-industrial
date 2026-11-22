from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import StringIO
from threading import Barrier, local
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.organizacao.models import Funcao, MudancaTurno, Setor, Trabalhador, Turno, UsuarioSetor, ResponsavelSetor
from apps.organizacao.turnos import revisar_troca_turno, confirmar_troca_turno
from .models import Alocacao, HistoricoTurnoAlocacao, Tarefa
from .services import alocar_dias, montar_quadro_semanal


class DadosTurnos:
    def preparar(self):
        self.hoje = date(2026, 11, 21)
        self.clock = patch('apps.organizacao.turnos.timezone.localdate', return_value=self.hoje)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        call_command('configurar_perfis', stdout=StringIO())
        self.coord = get_user_model().objects.create_user(username='coordenador_turnos', is_staff=True)
        self.coord.groups.add(Group.objects.get(name='Coordenador'))
        self.lider = get_user_model().objects.create_user(username='lider_turnos', is_staff=True)
        self.lider.groups.add(Group.objects.get(name='Líder'))
        self.setor = Setor.objects.create(nome='Setor autorizado')
        self.outro = Setor.objects.create(nome='Setor reservado')
        self.tecnico = get_user_model().objects.create_superuser(username='tecnico_turnos')
        ResponsavelSetor(setor=self.setor, usuario=self.coord).save(ator=self.tecnico)
        for u in (self.coord, self.lider):
            UsuarioSetor.objects.create(usuario=u, setor=self.setor)
        self.funcao = Funcao.objects.create(nome='Soldagem')
        self.worker = Trabalhador.objects.create(nome='Pessoa', setor_principal=self.setor, funcao_principal=self.funcao)
        self.tarefa = self.criar_tarefa('Atividade A')
        self.tarefa2 = self.criar_tarefa('Atividade B')
        self.t1, _ = Turno.objects.get_or_create(codigo='T1')
        self.t2, _ = Turno.objects.get_or_create(codigo='T2')
        self.t3, _ = Turno.objects.get_or_create(codigo='T3')

    def criar_tarefa(self, titulo, setor=None):
        return Tarefa.objects.create(titulo=titulo, setor=setor or self.setor,
            inicio_previsto=date(2026, 11, 1), fim_previsto=date(2027, 1, 31))

    def revisar(self, turno=None, vigencia=None, **kw):
        return revisar_troca_turno(ator=self.coord, trabalhador_id=self.worker.pk,
            turno_id=(turno or self.t1).pk, vigencia=vigencia or self.hoje, **kw)

    def confirmar(self, revisao):
        return confirmar_troca_turno(ator=self.coord, confirmacao=revisao['confirmacao'], trabalhador_id=self.worker.pk)

    def alocar(self, dia=None, tarefa=None, turno=None):
        return alocar_dias(ator=self.coord, trabalhador=self.worker, tarefa=tarefa or self.tarefa,
            datas=[dia or self.hoje], funcao_desempenhada=self.funcao, turno=turno or self.t1)[0]


@override_settings(OP_APP_TURNOS_ENABLED=True)
class TurnosTests(DadosTurnos, TestCase):
    def setUp(self):
        self.preparar()

    def test_referencias_semeadas_sem_classificar_trabalhadores(self):
        self.assertEqual(list(Turno.objects.values_list('codigo', flat=True)), ['T1', 'T2', 'T3'])
        self.assertTrue(self.t3.horario_aproximado)
        self.assertIsNone(self.worker.turno_habitual)
        self.assertFalse(MudancaTurno.objects.exists())

    def test_troca_futura_nao_muda_hoje_e_nao_reescreve_passado(self):
        self.confirmar(self.revisar())
        antigo = self.alocar()
        self.confirmar(self.revisar(self.t2, self.hoje + timedelta(days=2)))
        self.assertEqual(self.worker.turno_habitual.pk, 'T1')
        self.assertEqual(self.worker.turno_em(self.hoje + timedelta(days=2)).pk, 'T2')
        antigo.refresh_from_db()
        self.assertEqual(antigo.turno_id, 'T1')
        self.assertEqual(antigo.historico_turno.get().turno_novo_id, 'T1')

    def test_transferencia_conjunta_duas_tarefas_mesmo_dia(self):
        self.confirmar(self.revisar())
        self.alocar(self.hoje + timedelta(days=1))
        self.alocar(self.hoje + timedelta(days=1), self.tarefa2)
        revisao = self.revisar(self.t2, self.hoje + timedelta(days=1))
        self.assertEqual(len(revisao['alocacoes']), 2)
        evento = self.confirmar(revisao)
        self.assertEqual(evento.alocacoes_transferidas, 2)
        self.assertEqual(set(Alocacao.objects.values_list('turno_id', flat=True)), {'T2'})
        self.assertEqual(HistoricoTurnoAlocacao.objects.filter(turno_anterior=self.t1, turno_novo=self.t2).count(), 2)
        self.assertTrue(all(a.criado_por_id == self.coord.pk for a in Alocacao.objects.all()))

    def test_horas_referenciais_nao_limitam_datas_operacionais(self):
        self.confirmar(self.revisar(self.t2))
        self.alocar(date(2026, 12, 31), turno=self.t2)
        self.alocar(date(2027, 1, 1), turno=self.t2)
        self.t2.inicio_referencia = None
        self.t2.fim_referencia = None
        self.t2.save()
        self.assertEqual(Alocacao.objects.count(), 2)
        self.assertEqual(set(HistoricoTurnoAlocacao.objects.values_list('turno_novo_id', flat=True)), {'T2'})

    def test_turno_ausente_diferente_e_duplicidade_rejeitados(self):
        self.confirmar(self.revisar())
        with self.assertRaises(ValidationError):
            alocar_dias(ator=self.coord, trabalhador=self.worker, tarefa=self.tarefa,
                datas=[self.hoje], funcao_desempenhada=self.funcao)
        with self.assertRaises(ValidationError):
            self.alocar(turno=self.t2)
        self.alocar()
        with self.assertRaises(ValidationError):
            self.alocar()
        self.alocar(tarefa=self.tarefa2)
        self.assertEqual(Alocacao.objects.count(), 2)

    def test_outro_turno_ou_legado_no_dia_bloqueiam_nova_alocacao(self):
        self.confirmar(self.revisar())
        a = self.alocar()
        # Simula inconsistência preexistente, sem passar pela API de gravação.
        for codigo in ('T2', None):
            Alocacao.objects.filter(pk=a.pk).update(turno_id=codigo)
            with self.subTest(codigo=codigo), self.assertRaises(ValidationError):
                self.alocar(tarefa=self.tarefa2)
        self.assertEqual(Alocacao.objects.count(), 1)

    def test_troca_revalida_revisao_apos_nova_alocacao(self):
        self.confirmar(self.revisar())
        revisao = self.revisar(self.t2, self.hoje + timedelta(days=1))
        self.alocar(self.hoje + timedelta(days=1))
        with self.assertRaises(ValidationError):
            self.confirmar(revisao)
        self.assertEqual(MudancaTurno.objects.count(), 1)
        self.assertEqual(Alocacao.objects.get().turno_id, 'T1')

    def test_falha_no_segundo_registro_reverte_evento_e_todo_lote(self):
        self.confirmar(self.revisar())
        self.alocar(self.hoje + timedelta(days=1))
        self.alocar(self.hoje + timedelta(days=1), self.tarefa2)
        revisao = self.revisar(self.t2, self.hoje + timedelta(days=1))
        original = Alocacao.save
        def falhar(obj, *args, **kw):
            if obj.tarefa_id == self.tarefa2.pk:
                raise ValidationError('Falha concorrente simulada')
            return original(obj, *args, **kw)
        with patch.object(Alocacao, 'save', falhar), self.assertRaises(ValidationError):
            self.confirmar(revisao)
        self.assertEqual(set(Alocacao.objects.values_list('turno_id', flat=True)), {'T1'})
        self.assertEqual(MudancaTurno.objects.count(), 1)
        self.assertEqual(HistoricoTurnoAlocacao.objects.count(), 2)

    def test_coordenador_sem_setor_ou_permissao_revogada_nao_confirma(self):
        revisao = self.revisar()
        ResponsavelSetor.objects.filter(usuario=self.coord).delete()
        with self.assertRaises(PermissionDenied):
            self.confirmar(revisao)
        self.assertFalse(MudancaTurno.objects.exists())

    def test_permissao_revogada_apos_revisao_e_revalidada(self):
        revisao = self.revisar()
        grupo = Group.objects.get(name='Coordenador')
        grupo.permissions.remove(*grupo.permissions.filter(codename='change_trabalhador'))
        with self.assertRaises(PermissionDenied):
            self.confirmar(revisao)
        self.assertFalse(MudancaTurno.objects.exists())

    def test_revisao_expirada_nao_aplica_mudanca(self):
        with patch('django.core.signing.time.time', return_value=1):
            revisao = self.revisar()
        with self.assertRaises(ValidationError):
            self.confirmar(revisao)
        self.assertFalse(MudancaTurno.objects.exists())

    def test_lider_nao_troca_turno_e_token_nao_e_portavel(self):
        with self.assertRaises(PermissionDenied):
            revisar_troca_turno(ator=self.lider, trabalhador_id=self.worker.pk, turno_id='T1', vigencia=self.hoje)
        revisao = self.revisar()
        with self.assertRaises(ValidationError):
            confirmar_troca_turno(ator=self.coord, confirmacao=revisao['confirmacao'], trabalhador_id=999)
        with self.assertRaises(ValidationError):
            confirmar_troca_turno(ator=self.coord, confirmacao=revisao['confirmacao'] + 'adulterado')
        self.assertFalse(MudancaTurno.objects.exists())

    def test_reenvio_inativo_e_vigencia_antiga_nao_sobrescrevem(self):
        revisao = self.revisar()
        self.confirmar(revisao)
        with self.assertRaises(ValidationError):
            self.confirmar(revisao)
        with self.assertRaises(ValidationError):
            self.revisar(self.t2, self.hoje - timedelta(days=1))
        self.t2.ativo = False
        self.t2.save()
        with self.assertRaises(ValidationError):
            self.revisar(self.t2, self.hoje + timedelta(days=1))
        self.assertEqual(MudancaTurno.objects.count(), 1)

    def test_transferencia_nao_mexe_alocacoes_de_outro_setor(self):
        self.confirmar(self.revisar())
        outra = self.criar_tarefa('Reservada', self.outro)
        UsuarioSetor.objects.create(usuario=self.coord, setor=self.outro)
        ResponsavelSetor(setor=self.outro, usuario=self.coord).save(ator=self.tecnico)
        self.alocar(self.hoje + timedelta(days=1), outra)
        ResponsavelSetor.objects.filter(setor=self.outro).delete()
        with self.assertRaises(PermissionDenied):
            self.revisar(self.t2, self.hoje + timedelta(days=1))
        self.assertEqual(Alocacao.objects.get().turno_id, 'T1')

    def test_legado_so_classifica_futuro_com_opcao_explicita(self):
        with self.settings(OP_APP_TURNOS_ENABLED=False):
            a = alocar_dias(ator=self.coord, trabalhador=self.worker, tarefa=self.tarefa,
                datas=[self.hoje + timedelta(days=1)], funcao_desempenhada=self.funcao)[0]
        with self.assertRaises(ValidationError):
            self.revisar()
        revisao = self.revisar(classificar_legado=True)
        self.confirmar(revisao)
        a.refresh_from_db()
        self.assertEqual(a.turno_id, 'T1')
        self.assertIsNone(a.historico_turno.get().turno_anterior_id)

    def test_tarefa_encerrada_e_trabalhador_inativo_bloqueiam_troca(self):
        self.confirmar(self.revisar())
        self.alocar(self.hoje + timedelta(days=1))
        self.tarefa.status = Tarefa.Status.CANCELADA
        self.tarefa.save(ator=self.coord)
        with self.assertRaises(ValidationError):
            self.revisar(self.t2, self.hoje + timedelta(days=1))
        self.worker.ativo = False
        self.worker.save()
        with self.assertRaises(ValidationError):
            self.revisar(self.t2, self.hoje + timedelta(days=1))

    def test_modelos_nao_reescrevem_identidade_e_historico(self):
        self.confirmar(self.revisar())
        self.alocar()
        self.t1.codigo = 'T2'
        with self.assertRaises(ValidationError):
            self.t1.save()
        evento = MudancaTurno.objects.get()
        with self.assertRaises(ValidationError):
            evento.save()
        historico = HistoricoTurnoAlocacao.objects.get()
        with self.assertRaises(ValidationError):
            historico.save()

    def test_remocao_da_alocacao_preserva_marcador_historico(self):
        self.confirmar(self.revisar())
        a = self.alocar()
        a.delete(ator=self.coord)
        h = HistoricoTurnoAlocacao.objects.get()
        self.assertIsNone(h.alocacao_id)
        self.assertEqual(h.turno_novo_id, 'T1')
        self.assertEqual(h.data, self.hoje)

    def test_ui_coordenador_revisa_confirma_e_quadro_identifica_turno(self):
        self.client.force_login(self.coord)
        url = reverse('admin:organizacao_trabalhador_turno', args=[self.worker.pk])
        r = self.client.post(url, {'turno':'T1', 'vigencia':self.hoje.isoformat()})
        self.assertContains(r, 'Confira antes de confirmar')
        token = r.context['revisao']['confirmacao']
        r = self.client.post(url, {'confirmacao':token})
        self.assertEqual(r.status_code, 302)
        self.alocar()
        r = self.client.get(reverse('planejamento:quadro_semanal'), {'semana':self.hoje.isoformat()})
        self.assertContains(r, 'Turno: T1')
        self.client.force_login(self.lider)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_desabilitado_preserva_fluxo_sem_turno_e_bloqueia_troca(self):
        with self.settings(OP_APP_TURNOS_ENABLED=False):
            with self.assertRaises(PermissionDenied):
                self.revisar()
            with self.assertRaises(ValidationError):
                self.alocar()
            a = alocar_dias(ator=self.coord, trabalhador=self.worker, tarefa=self.tarefa,
                datas=[self.hoje], funcao_desempenhada=self.funcao)[0]
            self.assertIsNone(a.turno_id)
            self.client.force_login(self.coord)
            self.assertNotContains(self.client.get(reverse('admin:organizacao_trabalhador_changelist')), 'Revisar troca de turno')


@skipUnless(connection.vendor == 'postgresql', 'Concorrência exige PostgreSQL')
@override_settings(OP_APP_TURNOS_ENABLED=True)
class TurnosConcorrenciaTests(DadosTurnos, TransactionTestCase):
    def setUp(self):
        self.preparar()
        self.confirmar(self.revisar())

    def test_confirmações_de_trocas_concorrentes_nao_reescrevem_mesma_vigencia(self):
        revisoes = [self.revisar(turno, self.hoje + timedelta(days=1)) for turno in (self.t2, self.t3)]
        barreira = Barrier(2, timeout=10)
        def operar(revisao):
            close_old_connections()
            try:
                barreira.wait()
                self.confirmar(revisao)
                return 'confirmada'
            except ValidationError:
                return 'rejeitada'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(operar, revisoes))
        self.assertCountEqual(resultados, ['confirmada', 'rejeitada'])
        self.assertEqual(MudancaTurno.objects.count(), 2)

    def test_turnos_distintos_no_mesmo_dia_serializam_no_trabalhador(self):
        barreira = Barrier(2, timeout=10)
        contexto = local()
        # Isola a garantia diária da regra separada de turno habitual.
        def referencia(worker, dia):
            return Turno.objects.get(pk=contexto.turno)
        def operar(codigo, tarefa):
            close_old_connections()
            try:
                contexto.turno = codigo
                barreira.wait()
                self.alocar(self.hoje + timedelta(days=1), tarefa, Turno.objects.get(pk=codigo))
                return 'confirmada'
            except ValidationError:
                return 'rejeitada'
            finally:
                close_old_connections()
        with patch.object(Trabalhador, 'turno_em', referencia), ThreadPoolExecutor(max_workers=2) as pool:
            futuros = [pool.submit(operar, 'T1', self.tarefa), pool.submit(operar, 'T2', self.tarefa2)]
            resultados = [f.result(timeout=20) for f in futuros]
        self.assertCountEqual(resultados, ['confirmada', 'rejeitada'])
        self.assertEqual(Alocacao.objects.count(), 1)


    def test_exclusao_lote_com_ordem_invertida_nao_deadlocka_com_edicao(self):
        from threading import Event
        from django.contrib import admin
        from django.db import transaction
        from django.test import RequestFactory
        primeiro = self.alocar(self.hoje, self.tarefa2)
        segundo = self.alocar(self.hoje + timedelta(days=1), self.tarefa)
        editar = self.alocar(self.hoje + timedelta(days=2), self.tarefa)
        excluido_b, editor_em_a = Event(), Event()
        original = Alocacao.delete
        def excluir(obj, *args, **kwargs):
            resultado = original(obj, *args, **kwargs)
            if obj.tarefa_id == self.tarefa2.pk:
                excluido_b.set()
                # Com o lote corrigido, A já está bloqueada: editor aguarda o commit.
                # Sem a correção, editor segura A enquanto o lote ainda segura B.
                editor_em_a.wait(timeout=0.5)
            return resultado
        def remover():
            close_old_connections()
            try:
                req = RequestFactory().post('/admin/planejamento/alocacao/')
                req.user = get_user_model().objects.get(pk=self.coord.pk)
                admin.site._registry[Alocacao].delete_queryset(req, Alocacao.objects.filter(pk__in=[primeiro.pk, segundo.pk]))
                return 'removidas'
            finally:
                close_old_connections()
        def mover():
            close_old_connections()
            try:
                if not excluido_b.wait(timeout=10):
                    raise AssertionError('Exclusão não iniciou')
                with transaction.atomic():
                    list(Tarefa.objects.select_for_update().filter(pk=self.tarefa.pk))
                    editor_em_a.set()
                    obj = Alocacao.objects.get(pk=editar.pk)
                    obj.tarefa_id = self.tarefa2.pk
                    obj.save(ator=get_user_model().objects.get(pk=self.coord.pk))
                return 'editada'
            finally:
                close_old_connections()
        with patch.object(Alocacao, 'delete', excluir), ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(remover)
            b = pool.submit(mover)
            self.assertEqual(a.result(timeout=20), 'removidas')
            self.assertEqual(b.result(timeout=20), 'editada')
        self.assertEqual(Alocacao.objects.count(), 1)
        self.assertEqual(Alocacao.objects.get().tarefa_id, self.tarefa2.pk)


class AtivacaoTurnosTests(TestCase):
    def test_configuracao_disponibiliza_opt_in_de_turnos(self):
        import os
        import subprocess
        import sys
        from django.conf import settings
        env = {**os.environ, 'OP_APP_TURNOS_ENABLED':'True', 'DJANGO_SETTINGS_MODULE':'config.settings'}
        r = subprocess.run([sys.executable, 'manage.py', 'check'], cwd=settings.BASE_DIR,
                           env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 0, r.stderr)


class CalendarioOperacionalTests(TestCase):
    def test_data_brasilia_nao_e_o_dia_utc_seguinte(self):
        from datetime import datetime, timezone
        from apps.organizacao.turnos import data_operacional_hoje
        with patch('django.utils.timezone.now', return_value=datetime(2026, 11, 22, 1, tzinfo=timezone.utc)):
            self.assertEqual(data_operacional_hoje(), date(2026, 11, 21))


class MigracaoTurnosTests(TransactionTestCase):
    def test_legado_preservado_e_reversao_bloqueada_apos_classificacao(self):
        from django.db.migrations.executor import MigrationExecutor
        antigos = [('organizacao', '0002_usuariosetor'), ('planejamento', '0003_historicotarefa_registrado_por')]
        novos = [('organizacao', '0004_historicoacessoturno_responsavelsetor_and_more'), ('planejamento', '0007_atividadealocacao_alocacao_atividades_adicionais_and_more')]
        executor = MigrationExecutor(connection)
        executor.migrate(antigos)
        try:
            apps = executor.loader.project_state(antigos).apps
            ator = apps.get_model('auth', 'User').objects.create(username='migracao_turno')
            setor = apps.get_model('organizacao', 'Setor').objects.create(nome='Setor legado')
            funcao = apps.get_model('organizacao', 'Funcao').objects.create(nome='Função legada')
            trabalhador = apps.get_model('organizacao', 'Trabalhador').objects.create(
                nome='Pessoa legada', setor_principal_id=setor.pk, funcao_principal_id=funcao.pk)
            tarefa = apps.get_model('planejamento', 'Tarefa').objects.create(titulo='Tarefa legada',
                setor_id=setor.pk, inicio_previsto=date(2026, 11, 1), fim_previsto=date(2026, 11, 30), status='PENDENTE')
            registro = apps.get_model('planejamento', 'Alocacao').objects.create(trabalhador_id=trabalhador.pk,
                tarefa_id=tarefa.pk, data=date(2026, 11, 22), funcao_desempenhada_id=funcao.pk,
                criado_por_id=ator.pk, alterado_por_id=ator.pk, observacao='Preservar legado')
            executor = MigrationExecutor(connection)
            executor.migrate(novos)
            apps = executor.loader.project_state(novos).apps
            atual = apps.get_model('planejamento', 'Alocacao').objects.get(pk=registro.pk)
            self.assertIsNone(atual.turno_id)
            self.assertEqual(atual.observacao, 'Preservar legado')
            self.assertEqual(atual.criado_por_id, ator.pk)
            self.assertEqual(apps.get_model('organizacao', 'Turno').objects.count(), 3)
            self.assertFalse(apps.get_model('organizacao', 'MudancaTurno').objects.exists())
            apps.get_model('organizacao', 'MudancaTurno').objects.create(trabalhador_id=trabalhador.pk,
                turno_novo_id='T1', registrado_por_id=ator.pk, vigencia=date(2026, 11, 22))
            with self.assertRaisesMessage(RuntimeError, 'Há classificação/histórico de turnos'):
                MigrationExecutor(connection).migrate(antigos)
            self.assertTrue(apps.get_model('planejamento', 'Alocacao').objects.filter(pk=registro.pk).exists())
        finally:
            MigrationExecutor(connection).migrate(novos)
