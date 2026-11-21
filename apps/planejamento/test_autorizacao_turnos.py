from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.organizacao.autorizacao import filtrar_escopo, setores_do_usuario
from apps.organizacao.models import (Funcao, Setor, Trabalhador, UsuarioSetor, Turno,
    ResponsavelSetor, VinculoLiderTurno, HistoricoAcessoTurno)
from apps.organizacao.turnos import revisar_troca_turno, confirmar_troca_turno
from .models import Tarefa, Alocacao, TurnoTarefa, ObservacaoTarefaTurno, HistoricoTarefa
from .services import alocar_dias, montar_quadro_semanal


@override_settings(OP_APP_TURNOS_ENABLED=True)
class AutorizacaoTurnosTests(TestCase):
    hoje = date(2026, 11, 21)

    @classmethod
    def setUpTestData(cls):
        with patch('apps.organizacao.turnos.timezone.localdate', return_value=cls.hoje):
            call_command('configurar_perfis', stdout=StringIO())
            cls.root = get_user_model().objects.create_superuser(username='root_acessos')
            cls.a = Setor.objects.create(nome='Setor A')
            cls.b = Setor.objects.create(nome='Setor B reservado')
            cls.funcao = Funcao.objects.create(nome='Soldagem')
            cls.t1, cls.t2, cls.t3 = [Turno.objects.get_or_create(codigo=c)[0] for c in ('T1', 'T2', 'T3')]
            cls.c1 = cls.usuario('coord_a', 'Coordenador', cls.a)
            cls.c2 = cls.usuario('coord_b', 'Coordenador', cls.b)
            cls.l1 = cls.usuario('lider_t1', 'Líder', cls.a)
            cls.l2 = cls.usuario('lider_t2', 'Líder', cls.a)
            cls.consulta = cls.usuario('consulta_a', 'Consulta', cls.a)
            cls.admin = cls.usuario('admin_operacional', 'Administrador', cls.a)
            cls.responsavel = ResponsavelSetor(setor=cls.a, usuario=cls.c1)
            cls.responsavel.save(ator=cls.root)
            ResponsavelSetor(setor=cls.b, usuario=cls.c2).save(ator=cls.root)
            cls.v1 = VinculoLiderTurno(usuario=cls.l1, setor=cls.a, turno=cls.t1)
            cls.v1.save(ator=cls.c1)
            cls.v2 = VinculoLiderTurno(usuario=cls.l2, setor=cls.a, turno=cls.t2)
            cls.v2.save(ator=cls.c1)
            cls.w1 = cls.worker('Pessoa T1', cls.a, cls.c1, cls.t1)
            cls.w2 = cls.worker('Pessoa T2 oculta', cls.a, cls.c1, cls.t2)
            cls.wb = cls.worker('Pessoa B oculta', cls.b, cls.c2, cls.t1)
            cls.legado = Trabalhador.objects.create(nome='Pessoa sem turno', setor_principal=cls.a, funcao_principal=cls.funcao)
            cls.f1 = cls.task('Tarefa T1', cls.a, cls.c1, cls.t1)
            cls.f2 = cls.task('Tarefa T2 oculta', cls.a, cls.c1, cls.t2)
            cls.fb = cls.task('Tarefa B oculta', cls.b, cls.c2, cls.t1)
            cls.comum = cls.task('Tarefa compartilhada', cls.a, cls.c1, cls.t1)
            TurnoTarefa(tarefa=cls.comum, turno=cls.t2).save(ator=cls.c1)
            cls.al1 = cls.alloc(cls.w1, cls.f1, cls.c1, cls.t1)
            cls.al2 = cls.alloc(cls.w2, cls.f2, cls.c1, cls.t2)
            cls.alb = cls.alloc(cls.wb, cls.fb, cls.c2, cls.t1)
            ObservacaoTarefaTurno(tarefa=cls.comum, turno=cls.t1, texto='Nota autorizada T1').save(ator=cls.l1)
            ObservacaoTarefaTurno(tarefa=cls.comum, turno=cls.t2, texto='Nota exclusiva T2 oculta').save(ator=cls.l2)

    @classmethod
    def usuario(cls, nome, grupo, setor):
        u = get_user_model().objects.create_user(username=nome, is_staff=True)
        u.groups.add(Group.objects.get(name=grupo))
        UsuarioSetor.objects.create(usuario=u, setor=setor)
        return u

    @classmethod
    def worker(cls, nome, setor, coord, turno):
        w = Trabalhador.objects.create(nome=nome, setor_principal=setor, funcao_principal=cls.funcao)
        r = revisar_troca_turno(ator=coord, trabalhador_id=w.pk, turno_id=turno.pk, vigencia=cls.hoje)
        confirmar_troca_turno(ator=coord, confirmacao=r['confirmacao'])
        return w

    @classmethod
    def task(cls, nome, setor, ator, turno):
        t = Tarefa(titulo=nome, setor=setor, inicio_previsto=cls.hoje - timedelta(days=10), fim_previsto=cls.hoje + timedelta(days=30))
        t.save(ator=ator, turno_operacao=turno)
        return t

    @classmethod
    def alloc(cls, worker, task, ator, turno, dia=None):
        return alocar_dias(ator=ator, trabalhador=worker, tarefa=task, datas=[dia or cls.hoje],
                           funcao_desempenhada=cls.funcao, turno=turno)[0]

    def setUp(self):
        clock = patch('apps.organizacao.turnos.timezone.localdate', return_value=self.hoje)
        clock.start()
        self.addCleanup(clock.stop)

    def test_lider_filtra_pessoas_tarefas_alocacoes_e_observacoes(self):
        self.assertEqual(set(filtrar_escopo(self.l1, Trabalhador.objects.all()).values_list('pk', flat=True)), {self.w1.pk})
        self.assertEqual(set(filtrar_escopo(self.l1, Tarefa.objects.all()).values_list('pk', flat=True)), {self.f1.pk, self.comum.pk})
        self.assertEqual(set(filtrar_escopo(self.l1, Alocacao.objects.all()).values_list('pk', flat=True)), {self.al1.pk})
        self.assertEqual(list(filtrar_escopo(self.l1, ObservacaoTarefaTurno.objects.all()).values_list('texto', flat=True)), ['Nota autorizada T1'])
        self.assertEqual(set(setores_do_usuario(self.l1)), {self.a})

    def test_coordenador_ve_tres_turnos_e_legado_mas_nao_outro_setor(self):
        self.assertEqual(set(filtrar_escopo(self.c1, Trabalhador.objects.all()).values_list('pk', flat=True)), {self.w1.pk, self.w2.pk, self.legado.pk})
        self.assertEqual(set(filtrar_escopo(self.c1, Alocacao.objects.all()).values_list('pk', flat=True)), {self.al1.pk, self.al2.pk})
        with self.assertRaises(PermissionDenied):
            self.alloc(self.wb, self.fb, self.c1, self.t1)

    def test_multiplos_vinculos_concedidos_e_revogados_sem_grupo_global(self):
        v = VinculoLiderTurno(usuario=self.l1, setor=self.a, turno=self.t2)
        v.save(ator=self.c1)
        self.assertIn(self.al2.pk, filtrar_escopo(self.l1, Alocacao.objects.all()).values_list('pk', flat=True))
        v.ativo = False
        v.save(ator=self.c1)
        self.assertNotIn(self.al2.pk, filtrar_escopo(self.l1, Alocacao.objects.all()).values_list('pk', flat=True))
        self.assertEqual(HistoricoAcessoTurno.objects.filter(tipo='vinculo_lider', alteracao__usuario=self.l1.pk).count(), 3)

    def test_lider_sem_vinculo_ou_inativo_nao_herda_escopo_de_consulta(self):
        self.l1.groups.add(Group.objects.get(name='Consulta'))
        self.v1.ativo = False
        self.v1.save(ator=self.c1)
        self.assertFalse(setores_do_usuario(self.l1).exists())
        self.assertFalse(filtrar_escopo(self.l1, Alocacao.objects.all()).exists())
        self.c1.is_active = False
        self.c1.save()
        self.assertFalse(setores_do_usuario(self.c1).exists())

    def test_coordenador_sem_responsabilidade_nao_herda_setor_legado(self):
        u = self.usuario('coord_sem_responsabilidade', 'Coordenador', self.a)
        self.assertFalse(setores_do_usuario(u).exists())
        self.assertFalse(filtrar_escopo(u, Trabalhador.objects.all()).exists())

    def test_responsavel_unico_substituicao_auditada_e_apenas_tecnico(self):
        with self.assertRaises(PermissionDenied):
            ResponsavelSetor(setor=self.b, usuario=self.c1).save(ator=self.c1)
        with self.assertRaises(ValidationError):
            ResponsavelSetor(setor=self.a, usuario=self.c2).save(ator=self.root)
        self.responsavel.usuario = self.c2
        self.responsavel.save(ator=self.root)
        self.assertFalse(setores_do_usuario(self.c1).exists())
        self.assertEqual(set(setores_do_usuario(self.c2)), {self.a, self.b})
        self.assertEqual(HistoricoAcessoTurno.objects.filter(tipo='responsavel', setor=self.a).count(), 2)

    def test_coordenador_nao_concede_outro_setor_ou_muda_grupos(self):
        with self.assertRaises(PermissionDenied):
            VinculoLiderTurno(usuario=self.l1, setor=self.b, turno=self.t1).save(ator=self.c1)
        with self.assertRaises(ValidationError):
            VinculoLiderTurno(usuario=self.c1, setor=self.a, turno=self.t3).save(ator=self.c1)
        self.assertEqual(list(self.c1.groups.values_list('name', flat=True)), ['Coordenador'])
        with self.assertRaises(ValidationError):
            self.v1.turno = self.t3
            self.v1.save(ator=self.c1)

    def test_consulta_somente_leitura_admin_preserva_global_e_nao_gere_vinculos(self):
        self.assertEqual(set(filtrar_escopo(self.consulta, Alocacao.objects.all()).values_list('pk', flat=True)), {self.al1.pk, self.al2.pk})
        self.consulta.user_permissions.add(Permission.objects.get(codename='add_alocacao'))
        with self.assertRaises(PermissionDenied):
            self.alloc(self.w1, self.f1, self.consulta, self.t1, self.hoje + timedelta(days=1))
        self.assertIn(self.alb.pk, filtrar_escopo(self.admin, Alocacao.objects.all()).values_list('pk', flat=True))
        with self.assertRaises(PermissionDenied):
            VinculoLiderTurno(usuario=self.l1, setor=self.a, turno=self.t3).save(ator=self.admin)

    def test_lider_cria_tarefa_do_turno_mas_nao_altera_dados_gerais(self):
        t = self.task('Nova do líder', self.a, self.l1, self.t1)
        self.assertTrue(TurnoTarefa.objects.filter(tarefa=t, turno=self.t1).exists())
        for campo, valor in (('titulo', 'Título indevido'), ('observacoes', 'Nota geral indevida'), ('fim_previsto', self.hoje + timedelta(days=20))):
            with self.subTest(campo=campo):
                atual = Tarefa.objects.get(pk=t.pk)
                setattr(atual, campo, valor)
                with self.assertRaises(PermissionDenied):
                    atual.save(ator=self.l1, turno_operacao=self.t1)
        with self.assertRaises(PermissionDenied):
            self.task('Fora do turno', self.a, self.l1, self.t2)

    def test_alocacao_em_tarefa_de_outro_turno_rejeita_post_direto(self):
        with self.assertRaises(PermissionDenied):
            self.alloc(self.w2, self.f2, self.l1, self.t2, self.hoje + timedelta(days=1))
        with self.assertRaises(PermissionDenied):
            self.alloc(self.w1, self.f2, self.l1, self.t1, self.hoje + timedelta(days=1))
        self.alloc(self.w1, self.f1, self.l1, self.t1, self.hoje + timedelta(days=1))

    def test_observacoes_por_turno_anexadas_sem_apagar_as_gerais(self):
        self.comum.observacoes = 'Observação geral do coordenador'
        self.comum.save(ator=self.c1)
        nova = ObservacaoTarefaTurno(tarefa=self.comum, turno=self.t1, texto='Novo apontamento')
        nova.save(ator=self.l1)
        self.assertEqual(ObservacaoTarefaTurno.objects.filter(tarefa=self.comum).count(), 3)
        with self.assertRaises(PermissionDenied):
            ObservacaoTarefaTurno(tarefa=self.comum, turno=self.t2, texto='Indevida').save(ator=self.l1)
        with self.assertRaises(PermissionDenied):
            nova.texto = 'Reescrever'
            nova.save(ator=self.l1)
        self.comum.refresh_from_db()
        self.assertEqual(self.comum.observacoes, 'Observação geral do coordenador')

    def iniciar(self, tarefa=None):
        t = Tarefa.objects.get(pk=(tarefa or self.comum).pk)
        t.status = Tarefa.Status.EM_ANDAMENTO
        t.save(ator=self.c1)
        return t

    def test_encerramento_bloqueado_por_outro_turno_inclusive_hoje(self):
        for dias in (0, 2):
            with self.subTest(dias=dias):
                t = self.iniciar()
                a = self.alloc(self.w2, t, self.c1, self.t2, self.hoje + timedelta(days=dias))
                antes = t.historico.count()
                t.status = Tarefa.Status.CONCLUIDA
                with self.assertRaises(ValidationError):
                    t.save(ator=self.l1, turno_operacao=self.t1)
                t.refresh_from_db()
                self.assertEqual(t.status, Tarefa.Status.EM_ANDAMENTO)
                self.assertEqual(t.historico.count(), antes)
                a.delete(ator=self.c1)

    def test_encerramento_permitido_sem_outro_turno_e_coordenador_trata_gerais(self):
        t = self.iniciar(self.f1)
        t.status = Tarefa.Status.CONCLUIDA
        t.save(ator=self.l1, turno_operacao=self.t1)
        self.assertEqual(t.historico.last().turno_operacao_id, 'T1')
        with self.assertRaises(PermissionDenied):
            t.status = Tarefa.Status.PENDENTE
            t.save(ator=self.l1, turno_operacao=self.t1)
        t.status = Tarefa.Status.PENDENTE
        t.save(ator=self.c1)
        self.assertEqual(t.status, Tarefa.Status.PENDENTE)

    def test_historico_sem_turno_e_registros_exclusivos_nao_sao_expostos_ao_lider(self):
        self.assertFalse(filtrar_escopo(self.l1, HistoricoTarefa.objects.filter(turno_operacao__isnull=True)).exists())
        self.assertFalse(filtrar_escopo(self.c1, HistoricoTarefa.objects.filter(turno_operacao__isnull=True)).exists())
        # Acrescentar um registro geral, sem apagar a trilha por turno.
        self.f1.observacoes = 'Geral'
        self.f1.save(ator=self.c1)
        self.f1.status = Tarefa.Status.EM_ANDAMENTO
        self.f1.save(ator=self.c1)
        self.assertTrue(filtrar_escopo(self.c1, HistoricoTarefa.objects.filter(turno_operacao__isnull=True)).exists())
        self.assertFalse(filtrar_escopo(self.l1, HistoricoTarefa.objects.filter(turno_operacao__isnull=True)).exists())

    def test_revisao_de_troca_revogada_e_lider_nao_muda_habitual(self):
        with self.assertRaises(PermissionDenied):
            revisar_troca_turno(ator=self.l1, trabalhador_id=self.w1.pk, turno_id='T2', vigencia=self.hoje + timedelta(days=1))
        revisao = revisar_troca_turno(ator=self.c1, trabalhador_id=self.w1.pk, turno_id='T2', vigencia=self.hoje + timedelta(days=1))
        self.responsavel.usuario = self.c2
        self.responsavel.save(ator=self.root)
        with self.assertRaises(PermissionDenied):
            confirmar_troca_turno(ator=self.c1, confirmacao=revisao['confirmacao'])

    def test_lider_com_permissao_avulsa_nao_cadastra_trabalhador(self):
        self.l1.user_permissions.add(Permission.objects.get(codename='change_trabalhador'))
        w = Trabalhador.objects.get(pk=self.w1.pk)
        w.nome = 'Não deve gravar'
        with self.assertRaises(PermissionDenied):
            w.save(ator=self.l1)

    def test_urls_buscas_quadro_e_admin_nao_expoem_outros_turnos(self):
        self.client.force_login(self.l1)
        for nome in ('admin:organizacao_trabalhador_changelist', 'admin:planejamento_tarefa_changelist',
                     'admin:planejamento_alocacao_changelist', 'planejamento:quadro_semanal', 'entrada_operacional'):
            r = self.client.get(reverse(nome), {'semana':self.hoje.isoformat()} if not nome.startswith('admin:') else {})
            self.assertEqual(r.status_code, 200)
            for texto in ('Pessoa T2 oculta', 'Pessoa B oculta', 'Tarefa T2 oculta', 'Nota exclusiva T2 oculta'):
                self.assertNotContains(r, texto)
        for nome, pk in (('admin:organizacao_trabalhador_change', self.w2.pk),
                         ('admin:planejamento_tarefa_change', self.f2.pk),
                         ('admin:planejamento_alocacao_change', self.al2.pk)):
            r = self.client.get(reverse(nome, args=[pk]))
            self.assertIn(r.status_code, (302, 403, 404))
        r = self.client.get(reverse('admin:planejamento_tarefa_change', args=[self.comum.pk]))
        self.assertContains(r, 'Nota autorizada T1')
        self.assertNotContains(r, 'Nota exclusiva T2 oculta')

    def test_admin_vinculo_sem_usuarios_de_outro_setor_e_sem_gestao_de_contas(self):
        self.client.force_login(self.c1)
        r = self.client.get(reverse('admin:organizacao_vinculoliderturno_add'))
        self.assertContains(r, 'lider_t1')
        self.assertNotContains(r, 'coord_b')
        self.assertNotContains(r, 'Setor B reservado')
        for nome in ('admin:auth_user_changelist', 'admin:auth_group_changelist', 'admin:organizacao_responsavelsetor_changelist'):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 403)

    def test_futuro_habitual_filtra_opcoes_pela_data_da_alocacao(self):
        r = revisar_troca_turno(ator=self.c1, trabalhador_id=self.w1.pk, turno_id='T2', vigencia=self.hoje + timedelta(days=3))
        confirmar_troca_turno(ator=self.c1, confirmacao=r['confirmacao'])
        self.assertNotIn(self.w1.pk, filtrar_escopo(self.l2, Trabalhador.objects.all()).values_list('pk', flat=True))
        qs = filtrar_escopo(self.l2, Trabalhador.objects.all(), data_referencia=self.hoje + timedelta(days=3))
        self.assertIn(self.w1.pk, qs.values_list('pk', flat=True))

    def dados_admin_tarefa(self, tarefa, **extras):
        url = reverse('admin:planejamento_tarefa_change', args=[tarefa.pk])
        pagina = self.client.get(url)
        dados = {'titulo': tarefa.titulo, 'descricao': tarefa.descricao, 'setor': tarefa.setor_id,
                 'inicio_previsto': tarefa.inicio_previsto.isoformat(), 'fim_previsto': tarefa.fim_previsto.isoformat(),
                 'status': tarefa.status, 'observacoes': tarefa.observacoes, 'turno_operacao':'T1', **extras}
        for inline in pagina.context['inline_admin_formsets']:
            fs = inline.formset
            dados[f'{fs.prefix}-TOTAL_FORMS'] = str(fs.total_form_count())
            dados[f'{fs.prefix}-INITIAL_FORMS'] = str(fs.initial_form_count())
            for indice, formulario in enumerate(fs.forms):
                if formulario.instance.pk:
                    dados[f'{fs.prefix}-{indice}-id'] = formulario.instance.pk
                    dados[f'{fs.prefix}-{indice}-tarefa'] = tarefa.pk
        return url, dados

    def test_post_admin_cria_tarefa_lider_com_observacao_por_turno(self):
        self.client.force_login(self.l1)
        r = self.client.post(reverse('admin:planejamento_tarefa_add'), {
            'titulo':'Criada na UI', 'descricao':'Inicial', 'setor':self.a.pk,
            'inicio_previsto': self.hoje.isoformat(), 'fim_previsto':(self.hoje + timedelta(days=3)).isoformat(),
            'status':'PENDENTE', 'turno_operacao':'T1', 'observacao_turno':'Apontamento inicial',
            'historico-TOTAL_FORMS':'0', 'historico-INITIAL_FORMS':'0'})
        self.assertEqual(r.status_code, 302)
        t = Tarefa.objects.get(titulo='Criada na UI')
        self.assertTrue(TurnoTarefa.objects.filter(tarefa=t, turno=self.t1).exists())
        self.assertEqual(t.observacoes_por_turno.get().texto, 'Apontamento inicial')
        self.assertEqual(t.observacoes, '')

    def test_post_admin_readonly_nao_altera_dados_gerais(self):
        self.client.force_login(self.l1)
        url, dados = self.dados_admin_tarefa(self.f1, titulo='POST adulterado', observacoes='Não deve substituir', status='EM_ANDAMENTO')
        r = self.client.post(url, dados)
        self.assertEqual(r.status_code, 302)
        self.f1.refresh_from_db()
        self.assertEqual(self.f1.titulo, 'Tarefa T1')
        self.assertEqual(self.f1.observacoes, '')
        self.assertEqual(self.f1.status, 'EM_ANDAMENTO')

    def test_post_admin_encerramento_bloqueado_reapresenta_sem_500(self):
        t = self.iniciar()
        self.alloc(self.w2, t, self.c1, self.t2, self.hoje + timedelta(days=1))
        self.client.force_login(self.l1)
        url, dados = self.dados_admin_tarefa(t, status='CONCLUIDA')
        r = self.client.post(url, dados)
        self.assertContains(r, 'Procure o Coordenador para encerrar')
        t.refresh_from_db()
        self.assertEqual(t.status, 'EM_ANDAMENTO')

    def test_post_alocacao_fora_turno_rejeitado_sem_modificar_registros(self):
        self.client.force_login(self.l1)
        antes = Alocacao.objects.count()
        r = self.client.post(reverse('admin:planejamento_alocacao_add'), {
            'trabalhador':self.w2.pk, 'tarefa':self.f2.pk, 'turno':'T2',
            'data':(self.hoje + timedelta(days=1)).isoformat(), 'funcao_desempenhada':self.funcao.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Alocacao.objects.count(), antes)

    def test_post_coordenador_cria_vinculo_sem_alterar_perfil(self):
        self.client.force_login(self.c1)
        r = self.client.post(reverse('admin:organizacao_vinculoliderturno_add'), {
            'usuario':self.l1.pk, 'setor':self.a.pk, 'turno':'T3', 'ativo':'on'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(list(self.l1.groups.values_list('name', flat=True)), ['Líder'])
        self.assertTrue(VinculoLiderTurno.objects.filter(usuario=self.l1, turno=self.t3, ativo=True).exists())

    def test_perfil_coordenador_nao_amplia_edicao_em_setor_de_vinculo_lider(self):
        self.c1.groups.add(Group.objects.get(name='Líder'))
        UsuarioSetor.objects.create(usuario=self.c1, setor=self.b)
        VinculoLiderTurno(usuario=self.c1, setor=self.b, turno=self.t1).save(ator=self.c2)
        w = Trabalhador.objects.get(pk=self.wb.pk)
        w.nome = 'Alteração indevida'
        with self.assertRaises(PermissionDenied):
            w.save(ator=self.c1)
        self.client.force_login(self.c1)
        r = self.client.get(reverse('admin:organizacao_trabalhador_change', args=[self.wb.pk]))
        self.assertContains(r, 'Pessoa B oculta')
        self.assertNotContains(r, 'name="nome"')
        self.assertIn(self.wb.pk, filtrar_escopo(self.c1, Trabalhador.objects.all()).values_list('pk', flat=True))


    def test_mover_tarefa_exige_responsabilidade_no_setor_original_e_destino(self):
        self.c1.groups.add(Group.objects.get(name='Líder'))
        UsuarioSetor.objects.create(usuario=self.c1, setor=self.b)
        VinculoLiderTurno(usuario=self.c1, setor=self.b, turno=self.t1).save(ator=self.c2)
        original = Tarefa.objects.get(pk=self.fb.pk)
        historicos = original.historico.count()
        original.setor = self.a
        original.titulo = 'Apropriação de tarefa'
        original.status = Tarefa.Status.CANCELADA
        with self.assertRaises(PermissionDenied):
            original.save(ator=self.c1, turno_operacao=self.t1)
        original.refresh_from_db()
        self.assertEqual(original.setor_id, self.b.pk)
        self.assertEqual(original.titulo, 'Tarefa B oculta')
        self.assertEqual(original.status, Tarefa.Status.PENDENTE)
        self.assertEqual(original.historico.count(), historicos)

    def test_edicao_de_alocacao_usa_data_do_registro_no_get_e_no_post(self):
        vigencia = self.hoje + timedelta(days=1)
        revisao = revisar_troca_turno(ator=self.c1, trabalhador_id=self.w1.pk,
                                     turno_id='T2', vigencia=vigencia)
        confirmar_troca_turno(ator=self.c1, confirmacao=revisao['confirmacao'])
        futura = self.alloc(self.w1, self.f2, self.c1, self.t2, vigencia)
        casos = ((self.al1, self.l1, self.hoje + timedelta(days=2)),
                 (futura, self.l2, self.hoje))
        for alocacao, lider, hoje in casos:
            with self.subTest(turno=alocacao.turno_id), patch('apps.organizacao.turnos.timezone.localdate', return_value=hoje):
                self.client.force_login(lider)
                url = reverse('admin:planejamento_alocacao_change', args=[alocacao.pk])
                pagina = self.client.get(url)
                formulario = pagina.context['adminform'].form
                self.assertEqual(pagina.status_code, 200)
                self.assertIn(self.w1.pk, formulario.fields['trabalhador'].queryset.values_list('pk', flat=True))
                resposta = self.client.post(url, {
                    'trabalhador':self.w1.pk, 'tarefa':alocacao.tarefa_id,
                    'data':alocacao.data.isoformat(), 'turno':alocacao.turno_id,
                    'funcao_desempenhada':self.funcao.pk, 'observacao':'Atualização autorizada'})
                self.assertEqual(resposta.status_code, 302)
                alocacao.refresh_from_db()
                self.assertEqual(alocacao.observacao, 'Atualização autorizada')
                self.assertEqual(alocacao.trabalhador_id, self.w1.pk)

    def test_revogacao_invalida_gravacao_aberta_com_usuario_antigo(self):
        self.client.force_login(self.l1)
        self.assertEqual(self.client.get(reverse('admin:planejamento_alocacao_add')).status_code, 200)
        self.v1.ativo = False
        self.v1.save(ator=self.c1)
        antes = Alocacao.objects.count()
        with self.assertRaises(PermissionDenied):
            self.alloc(self.w1, self.f1, self.l1, self.t1, self.hoje + timedelta(days=1))
        self.assertEqual(Alocacao.objects.count(), antes)

    @override_settings(OP_APP_TURNOS_ENABLED=False)
    def test_desabilitar_turnos_fecha_urls_dos_novos_historicos(self):
        self.client.force_login(self.c1)
        for modelo in ('historicoacessoturno', 'mudancaturno'):
            with self.subTest(modelo=modelo):
                resposta = self.client.get(reverse(f'admin:organizacao_{modelo}_changelist'))
                self.assertEqual(resposta.status_code, 403)

    def test_csrf_protege_gestao_de_vinculos(self):
        from django.test import Client
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.c1)
        r = cliente.post(reverse('admin:organizacao_vinculoliderturno_add'), {
            'usuario':self.l1.pk, 'setor':self.a.pk, 'turno':'T3', 'ativo':'on'})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(VinculoLiderTurno.objects.filter(usuario=self.l1, turno=self.t3).exists())


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest import skipUnless
from django.db import close_old_connections, connection, transaction


@skipUnless(connection.vendor == 'postgresql', 'Concorrência exige PostgreSQL')
@override_settings(OP_APP_TURNOS_ENABLED=True)
class AutorizacaoTurnosConcorrenciaTests(TransactionTestCase):
    hoje = AutorizacaoTurnosTests.hoje
    usuario = classmethod(AutorizacaoTurnosTests.usuario.__func__)
    worker = classmethod(AutorizacaoTurnosTests.worker.__func__)
    task = classmethod(AutorizacaoTurnosTests.task.__func__)
    alloc = classmethod(AutorizacaoTurnosTests.alloc.__func__)

    def setUp(self):
        clock = patch('apps.organizacao.turnos.timezone.localdate', return_value=self.hoje)
        clock.start()
        self.addCleanup(clock.stop)
        AutorizacaoTurnosTests.setUpTestData.__func__(type(self))

    def test_planejar_outro_turno_e_encerrar_nao_podem_ambos_confirmar(self):
        t = Tarefa.objects.get(pk=self.comum.pk)
        t.status = Tarefa.Status.EM_ANDAMENTO
        t.save(ator=self.c1)
        barreira = Barrier(2, timeout=10)
        def fechar():
            close_old_connections()
            try:
                obj = Tarefa.objects.get(pk=t.pk)
                obj.status = Tarefa.Status.CONCLUIDA
                barreira.wait()
                obj.save(ator=get_user_model().objects.get(pk=self.l1.pk), turno_operacao=self.t1)
                return 'encerrada'
            except ValidationError:
                return 'encerramento bloqueado'
            finally:
                close_old_connections()
        def planejar():
            close_old_connections()
            try:
                barreira.wait()
                self.alloc(self.w2, self.comum, get_user_model().objects.get(pk=self.c1.pk), self.t2, self.hoje + timedelta(days=1))
                return 'planejada'
            except ValidationError:
                return 'planejamento bloqueado'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(fechar), pool.submit(planejar)
            resultados = [a.result(timeout=20), b.result(timeout=20)]
        self.assertNotEqual(resultados, ['encerrada', 'planejada'])
        t.refresh_from_db()
        if t.status == 'CONCLUIDA':
            self.assertFalse(Alocacao.objects.filter(tarefa=t, turno=self.t2, data__gte=self.hoje).exists())
        else:
            self.assertEqual(resultados, ['encerramento bloqueado', 'planejada'])

    def test_substituicoes_concorrentes_preservam_unico_responsavel_e_trilha(self):
        c3 = self.usuario('coord_substituto', 'Coordenador', self.a)
        barreira = Barrier(2, timeout=10)
        def substituir(usuario):
            close_old_connections()
            try:
                obj = ResponsavelSetor.objects.get(pk=self.responsavel.pk)
                obj.usuario = usuario
                barreira.wait()
                obj.save(ator=get_user_model().objects.get(pk=self.root.pk))
                return 'salva'
            except ValidationError:
                return 'rejeitada'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(substituir, self.c2), pool.submit(substituir, c3)
            resultados = [a.result(timeout=20), b.result(timeout=20)]
        self.assertIn('salva', resultados)
        self.assertEqual(ResponsavelSetor.objects.filter(setor=self.a).count(), 1)
        final = ResponsavelSetor.objects.get(setor=self.a)
        trilha = HistoricoAcessoTurno.objects.filter(setor=self.a, tipo='responsavel').last()
        self.assertEqual(trilha.alteracao['novo'], final.usuario_id)

    def test_revogacao_serializa_com_confirmacao_do_lider(self):
        entrou, liberar, revogou = Event(), Event(), Event()
        def operar():
            close_old_connections()
            try:
                with transaction.atomic():
                    from apps.organizacao.autorizacao import travar_autorizacao
                    lider = travar_autorizacao(self.l1)
                    entrou.set()
                    if not liberar.wait(timeout=10):
                        raise AssertionError('Confirmação não liberada')
                    self.alloc(self.w1, self.f1, lider, self.t1, self.hoje + timedelta(days=1))
                return 'confirmada antes da revogação'
            finally:
                close_old_connections()
        def revogar():
            close_old_connections()
            try:
                if not entrou.wait(timeout=10):
                    raise AssertionError('Operação não iniciou')
                v = VinculoLiderTurno.objects.get(pk=self.v1.pk)
                v.ativo = False
                v.save(ator=get_user_model().objects.get(pk=self.c1.pk))
                revogou.set()
                return 'revogada'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(operar)
            b = pool.submit(revogar)
            try:
                self.assertTrue(entrou.wait(timeout=10))
                self.assertFalse(revogou.wait(timeout=0.2))
            finally:
                liberar.set()
            self.assertEqual(a.result(timeout=20), 'confirmada antes da revogação')
            self.assertEqual(b.result(timeout=20), 'revogada')
        with self.assertRaises(PermissionDenied):
            self.alloc(self.w1, self.f1, self.l1, self.t1, self.hoje + timedelta(days=2))
