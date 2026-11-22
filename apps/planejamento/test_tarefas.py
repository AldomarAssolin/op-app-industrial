from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apps.organizacao.models import Setor
from .models import HistoricoTarefa, Tarefa


class TarefaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.setor = Setor.objects.create(nome="Caldeiraria")

    def criar(self, **dados):
        return Tarefa.objects.create(**{
            "titulo": "  Eixo   THC 95 ", "setor": self.setor,
            "inicio_previsto": date(2026, 11, 2), "fim_previsto": date(2026, 11, 20),
            **dados,
        })

    def test_tarefa_multissemanal_e_registro_inicial(self):
        tarefa = self.criar()
        self.assertEqual(tarefa.titulo, "Eixo THC 95")
        self.assertEqual(tarefa.status, Tarefa.Status.PENDENTE)
        registro = tarefa.historico.get()
        self.assertEqual(registro.status, tarefa.status)
        self.assertEqual(registro.inicio_previsto, tarefa.inicio_previsto)
        self.assertEqual(registro.fim_previsto, tarefa.fim_previsto)
        self.assertEqual(registro.setor, self.setor)

    def test_campos_obrigatorios_e_valores_invalidos(self):
        for campo, valor in (("titulo", " \t "), ("titulo", "x" * 201),
                             ("setor", None), ("inicio_previsto", None),
                             ("fim_previsto", "invalido"), ("status", "INEXISTENTE")):
            with self.subTest(campo=campo, valor=valor):
                with self.assertRaises(ValidationError) as erro:
                    self.criar(**{campo: valor})
                self.assertIn(campo, erro.exception.message_dict)
        self.assertEqual(Tarefa.objects.count(), 0)
        self.assertEqual(HistoricoTarefa.objects.count(), 0)

    def test_mesmo_dia_e_titulos_repetidos_sao_permitidos(self):
        for _ in range(2):
            self.criar(fim_previsto=date(2026, 11, 2))
        self.assertEqual(Tarefa.objects.count(), 2)

    def test_periodo_invertido_na_criacao_e_edicao_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            self.criar(fim_previsto=date(2026, 11, 1))
        tarefa = self.criar()
        tarefa.inicio_previsto = date(2026, 11, 21)
        with self.assertRaises(ValidationError):
            tarefa.save()
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.inicio_previsto, date(2026, 11, 2))
        self.assertEqual(tarefa.historico.count(), 1)

    def test_banco_rejeita_periodo_e_status_invalidos(self):
        tarefa = self.criar()
        for dados in ({"fim_previsto": date(2026, 11, 1)}, {"status": "INEXISTENTE"}):
            with self.subTest(dados=dados):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Tarefa.objects.filter(pk=tarefa.pk).update(**dados)

    def test_todas_as_transicoes_permitidas_e_bloqueadas(self):
        permitidas = {
            "PENDENTE": {"EM_ANDAMENTO", "CANCELADA"},
            "EM_ANDAMENTO": {"CONCLUIDA", "CANCELADA"},
            "CONCLUIDA": {"PENDENTE"},
            "CANCELADA": {"PENDENTE"},
        }
        for origem in Tarefa.Status.values:
            for destino in Tarefa.Status.values:
                with self.subTest(origem=origem, destino=destino):
                    tarefa = self.criar()
                    if origem in {"EM_ANDAMENTO", "CONCLUIDA"}:
                        tarefa.status = "EM_ANDAMENTO"
                        tarefa.save()
                    if origem in {"CONCLUIDA", "CANCELADA"}:
                        tarefa.status = origem
                        tarefa.save()
                    quantidade = tarefa.historico.count()
                    tarefa.status = destino
                    if destino == origem or destino in permitidas[origem]:
                        tarefa.save()
                        self.assertEqual(tarefa.historico.count(), quantidade + (destino != origem))
                    else:
                        with self.assertRaises(ValidationError):
                            tarefa.save()
                    tarefa.refresh_from_db()
                    esperado = destino if destino == origem or destino in permitidas[origem] else origem
                    self.assertEqual(tarefa.status, esperado)

    def test_nova_tarefa_deve_ser_pendente(self):
        for status in ("EM_ANDAMENTO", "CONCLUIDA", "CANCELADA"):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                self.criar(status=status)

    def test_prazo_vencido_nao_conclui_automaticamente(self):
        tarefa = self.criar(inicio_previsto=date(2000, 1, 1), fim_previsto=date(2000, 1, 2))
        tarefa.observacoes = "Aguardando material"
        tarefa.save()
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, Tarefa.Status.PENDENTE)
        self.assertEqual(tarefa.historico.count(), 1)

    def test_replanejamento_registra_periodo_e_setor_anteriores(self):
        tarefa = self.criar()
        outro = Setor.objects.create(nome="Montagem")
        tarefa.fim_previsto = date(2026, 12, 4)
        tarefa.setor = outro
        tarefa.save()
        registros = list(tarefa.historico.all())
        self.assertEqual(len(registros), 2)
        self.assertEqual(registros[0].fim_previsto, date(2026, 11, 20))
        self.assertEqual(registros[0].setor, self.setor)
        self.assertEqual(registros[1].fim_previsto, date(2026, 12, 4))
        with self.assertRaises(ProtectedError):
            self.setor.delete()

    def test_tarefa_encerrada_exige_reabertura_para_replanejar(self):
        for status in ("CONCLUIDA", "CANCELADA"):
            with self.subTest(status=status):
                tarefa = self.criar()
                if status == "CONCLUIDA":
                    tarefa.status = "EM_ANDAMENTO"
                    tarefa.save()
                tarefa.status = status
                tarefa.save()
                tarefa.fim_previsto = date(2026, 12, 4)
                with self.assertRaises(ValidationError):
                    tarefa.save()
                tarefa.status = "PENDENTE"
                tarefa.save()
                tarefa.refresh_from_db()
                self.assertEqual(tarefa.fim_previsto, date(2026, 12, 4))

    def test_descricao_editavel_e_salvar_sem_mudanca_nao_duplica_historico(self):
        tarefa = self.criar()
        tarefa.descricao = "Montagem e soldagem"
        tarefa.observacoes = "Conferir desenho"
        tarefa.save()
        tarefa.save()
        self.assertEqual(tarefa.historico.count(), 1)

    def test_save_parcial_registra_apenas_o_que_foi_persistido(self):
        tarefa = self.criar()
        tarefa.status = "EM_ANDAMENTO"
        tarefa.fim_previsto = date(2026, 12, 4)
        tarefa.save(update_fields=["status"])
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.fim_previsto, date(2026, 11, 20))
        self.assertEqual(tarefa.historico.last().fim_previsto, tarefa.fim_previsto)
        self.assertEqual(tarefa.historico.last().status, "EM_ANDAMENTO")

    def test_falha_no_historico_reverte_gravacao(self):
        tarefa = self.criar()
        with patch.object(HistoricoTarefa, "save", side_effect=RuntimeError("falha simulada")):
            tarefa.status = "EM_ANDAMENTO"
            with self.assertRaises(RuntimeError):
                tarefa.save()
            with self.assertRaises(RuntimeError):
                self.criar()
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, "PENDENTE")
        self.assertEqual(Tarefa.objects.count(), 1)
        self.assertEqual(tarefa.historico.count(), 1)

    def test_historico_impede_exclusao_individual_e_em_lote(self):
        tarefa = self.criar()
        with self.assertRaises(ProtectedError):
            tarefa.delete()
        with self.assertRaises(ProtectedError):
            Tarefa.objects.filter(pk=tarefa.pk).delete()
        with self.assertRaises(ProtectedError):
            self.setor.delete()


class TarefaAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(username="admin_tarefa")
        from apps.organizacao.models import Funcao
        cls.atividade = Funcao.objects.create(nome="Montagem")
        cls.setor = Setor.objects.create(nome="Caldeiraria")

    def setUp(self):
        self.client.force_login(self.admin)

    def dados(self, tarefa=None, **extras):
        registros = list(tarefa.historico.all()) if tarefa else []
        dados = {"atividades_da_tarefa":[self.atividade.pk], "titulo": "Eixo THC 95", "setor": self.setor.pk,
                "inicio_previsto": "2026-11-02", "fim_previsto": "2026-11-20",
                "status": "PENDENTE", "historico-TOTAL_FORMS": str(len(registros)),
                "historico-INITIAL_FORMS": str(len(registros)), **extras}
        for i, registro in enumerate(registros):
            dados[f"historico-{i}-id"] = registro.pk
            dados[f"historico-{i}-tarefa"] = tarefa.pk
        return dados

    def url(self, acao, tarefa=None):
        return reverse(f"admin:planejamento_tarefa_{acao}", args=[tarefa.pk] if tarefa else None)

    def test_cadastro_replanejamento_e_ciclo_no_admin(self):
        self.assertEqual(self.client.post(self.url("add"), self.dados()).status_code, 302)
        tarefa = Tarefa.objects.get()
        for status in ("EM_ANDAMENTO", "CONCLUIDA", "PENDENTE", "CANCELADA"):
            dados = self.dados(tarefa=tarefa, status=status, fim_previsto="2026-12-04")
            self.assertEqual(self.client.post(self.url("change", tarefa), dados).status_code, 302)
            tarefa.refresh_from_db()
            self.assertEqual(tarefa.status, status)
        self.assertEqual(tarefa.historico.count(), 5)

    def test_erros_de_datas_e_transicao_aparecem_no_formulario(self):
        tarefa = Tarefa.objects.create(titulo="Eixo THC 95", setor=self.setor,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))
        for dados, campo in ((self.dados(fim_previsto="2026-11-01"), "fim_previsto"),
                             (self.dados(status="CONCLUIDA"), "status"),
                             (self.dados(fim_previsto="invalido"), "fim_previsto")):
            with self.subTest(campo=campo):
                resposta = self.client.post(self.url("change", tarefa), dados)
                self.assertEqual(resposta.status_code, 200)
                self.assertIn(campo, resposta.context["adminform"].form.errors)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, "PENDENTE")
        self.assertEqual(tarefa.historico.count(), 1)

    def test_busca_por_titulo_e_filtro_por_setor_e_status(self):
        self.client.post(self.url("add"), self.dados())
        tarefa = Tarefa.objects.get()
        outro = Setor.objects.create(nome="Usinagem")
        Tarefa.objects.create(titulo="Eixo THC 95", setor=outro,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))
        resposta = self.client.get(self.url("changelist"), {
            "q": "THC 95", "setor__id__exact": self.setor.pk, "status__exact": "PENDENTE",
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(list(resposta.context["cl"].queryset), [tarefa])

    def test_historico_somente_leitura_e_sem_exclusao(self):
        self.client.post(self.url("add"), self.dados())
        tarefa = Tarefa.objects.get()
        resposta = self.client.get(self.url("change", tarefa))
        inline = resposta.context["inline_admin_formsets"][0]
        self.assertFalse(inline.has_add_permission)
        self.assertFalse(inline.has_change_permission)
        self.assertFalse(inline.has_delete_permission)
        dados = self.dados(tarefa=tarefa)
        dados["historico-0-status"] = "CONCLUIDA"
        dados["historico-0-DELETE"] = "on"
        self.assertEqual(self.client.post(self.url("change", tarefa), dados).status_code, 302)
        self.assertEqual(tarefa.historico.get().status, "PENDENTE")
        self.assertEqual(self.client.post(self.url("delete", tarefa), {"post": "yes"}).status_code, 403)
        self.assertTrue(Tarefa.objects.filter(pk=tarefa.pk).exists())

    def test_permissao_de_consulta_nao_permite_alterar_status(self):
        self.client.post(self.url("add"), self.dados())
        tarefa = Tarefa.objects.get()
        consulta = get_user_model().objects.create_user(username="consulta_tarefa", is_staff=True)
        consulta.user_permissions.add(Permission.objects.get(
            content_type__app_label="planejamento", codename="view_tarefa"))
        self.client.force_login(consulta)
        self.assertEqual(self.client.get(self.url("changelist")).status_code, 200)
        self.assertEqual(self.client.post(self.url("change", tarefa),
                                         self.dados(status="EM_ANDAMENTO")).status_code, 403)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, "PENDENTE")
