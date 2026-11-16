from datetime import date
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.organizacao.models import Funcao, Setor, Trabalhador, UsuarioSetor
from .forms import AlocacaoMultidiaForm
from .models import Alocacao, Tarefa
from .services import alocar_dias, consultar_alocacoes


class AlocacaoBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ator = get_user_model().objects.create_superuser(username="gestor_alocacao")
        cls.setor = Setor.objects.create(nome="Caldeiraria")
        cls.funcao = Funcao.objects.create(nome="Soldagem")
        cls.montagem = Funcao.objects.create(nome="Montagem")
        cls.trabalhador = Trabalhador.objects.create(nome="Pessoa Exemplo",
            setor_principal=cls.setor, funcao_principal=cls.funcao)
        cls.tarefa = Tarefa.objects.create(titulo="Eixo THC 95", setor=cls.setor,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))

    def alocar(self, **dados):
        return alocar_dias(**{
            "ator": self.ator, "trabalhador": self.trabalhador, "tarefa": self.tarefa,
            "datas": [date(2026, 11, 2)], "funcao_desempenhada": self.montagem, **dados,
        })


class AlocacaoTests(AlocacaoBase):
    def test_segunda_a_quinta_e_segunda_tarefa_na_terca(self):
        dias = [date(2026, 11, dia) for dia in (2, 3, 4, 5)]
        registros = self.alocar(datas=dias)
        outra = Tarefa.objects.create(titulo="Outro eixo", setor=self.setor,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))
        self.alocar(tarefa=outra, datas=[date(2026, 11, 3)])
        self.assertEqual(Alocacao.objects.count(), 5)
        self.assertEqual(Alocacao.objects.filter(data=date(2026, 11, 3)).count(), 2)
        self.assertEqual([registro.data for registro in registros], dias)
        self.assertTrue(all(registro.funcao_desempenhada == self.montagem for registro in registros))
        self.assertEqual(self.trabalhador.funcao_principal, self.funcao)

    def test_atravessa_semanas_e_respeita_limites_inclusivos(self):
        dias = [self.tarefa.inicio_previsto, date(2026, 11, 9), self.tarefa.fim_previsto]
        self.assertEqual(len(self.alocar(datas=dias)), 3)

    def test_duplicidade_existente_reverte_dias_anteriores_do_lote(self):
        self.alocar(datas=[date(2026, 11, 4)])
        with self.assertRaises(ValidationError):
            self.alocar(datas=[date(2026, 11, 2), date(2026, 11, 4)])
        self.assertEqual(list(Alocacao.objects.values_list("data", flat=True)), [date(2026, 11, 4)])

    def test_constraint_real_bloqueia_duplicata(self):
        registro = self.alocar()[0]
        outro = self.alocar(datas=[date(2026, 11, 3)])[0]
        with self.assertRaises(IntegrityError), transaction.atomic():
            Alocacao.objects.filter(pk=outro.pk).update(data=registro.data)

    def test_datas_invalidas_ou_repetidas_na_selecao(self):
        for dias in ([], ["2026-11-02"], [date(2026, 11, 2)] * 2):
            with self.subTest(dias=dias), self.assertRaises(ValidationError):
                self.alocar(datas=dias)
        self.assertFalse(Alocacao.objects.exists())

    def test_data_fora_do_periodo_reverte_lote(self):
        with self.assertRaises(ValidationError):
            self.alocar(datas=[date(2026, 11, 2), date(2026, 11, 21)])
        self.assertFalse(Alocacao.objects.exists())

    def test_falha_inesperada_no_segundo_dia_reverte_lote(self):
        original = Alocacao.save
        def salvar(objeto, *args, **kwargs):
            if objeto.data == date(2026, 11, 3):
                raise RuntimeError("falha simulada")
            return original(objeto, *args, **kwargs)
        with patch.object(Alocacao, "save", salvar), self.assertRaises(RuntimeError):
            self.alocar(datas=[date(2026, 11, 2), date(2026, 11, 3)])
        self.assertFalse(Alocacao.objects.exists())

    def test_trabalhador_inativo_e_rejeitado_mesmo_com_objeto_antigo(self):
        Trabalhador.objects.filter(pk=self.trabalhador.pk).update(ativo=False)
        with self.assertRaises(ValidationError):
            self.alocar()

    def test_tarefa_encerrada_e_rejeitada_mesmo_com_objeto_antigo(self):
        for status in ("CONCLUIDA", "CANCELADA"):
            with self.subTest(status=status):
                tarefa = Tarefa.objects.get(pk=self.tarefa.pk)
                if tarefa.status != "PENDENTE":
                    tarefa.status = "PENDENTE"
                    tarefa.save()
                if status == "CONCLUIDA":
                    tarefa.status = "EM_ANDAMENTO"
                    tarefa.save()
                tarefa.status = status
                tarefa.save()
                with self.assertRaises(ValidationError):
                    self.alocar()

    def test_autoria_e_verificacao_de_permissoes_no_servidor(self):
        consulta = get_user_model().objects.create_user(username="sem_permissao")
        inativo = get_user_model().objects.create_superuser(username="inativo", is_active=False)
        for ator in (None, AnonymousUser(), consulta, inativo):
            with self.subTest(ator=ator), self.assertRaises(PermissionDenied):
                self.alocar(ator=ator)
        registro = self.alocar()[0]
        self.assertEqual(registro.criado_por, self.ator)
        editor = get_user_model().objects.create_user(username="editor")
        editor.user_permissions.add(Permission.objects.get(
            content_type__app_label="planejamento", codename="change_alocacao"))
        UsuarioSetor.objects.create(usuario=editor, setor=self.setor)
        registro.criado_por = editor  # Tentativa de trocar o criador é ignorada.
        registro.observacao = "Correção"
        registro.save(ator=editor)
        registro.refresh_from_db()
        self.assertEqual(registro.criado_por, self.ator)
        self.assertEqual(registro.alterado_por, editor)
        with self.assertRaises(PermissionDenied):
            registro.delete(ator=editor)

    def test_save_direto_exige_ator_e_aplica_validacoes(self):
        registro = Alocacao(trabalhador=self.trabalhador, tarefa=self.tarefa,
                            data=date(2026, 11, 2), funcao_desempenhada=self.funcao)
        with self.assertRaises(PermissionDenied):
            registro.save()
        registro.save(ator=self.ator)
        registro.data = date(2026, 11, 21)
        with self.assertRaises(ValidationError):
            registro.save(ator=self.ator)
        registro.refresh_from_db()
        self.assertEqual(registro.data, date(2026, 11, 2))

    def test_corrigir_e_remover_quarta_nao_afeta_outros_dias(self):
        registros = self.alocar(datas=[date(2026, 11, dia) for dia in (2, 3, 4, 5)])
        quarta = registros[2]
        quarta.observacao = "Soldagem complementar"
        quarta.funcao_desempenhada = self.funcao
        quarta.save(ator=self.ator)
        self.assertEqual(Alocacao.objects.exclude(pk=quarta.pk).filter(observacao="").count(), 3)
        quarta.delete(ator=self.ator)
        self.assertEqual(list(Alocacao.objects.values_list("data", flat=True)),
                         [date(2026, 11, dia) for dia in (2, 3, 5)])

    def test_save_parcial_nao_persiste_data_fora_do_update(self):
        registro = self.alocar()[0]
        registro.data = date(2026, 11, 21)
        registro.observacao = "Nota"
        registro.save(ator=self.ator, update_fields=["observacao"])
        registro.refresh_from_db()
        self.assertEqual(registro.data, date(2026, 11, 2))
        self.assertEqual(registro.observacao, "Nota")

    def test_replanejamento_nao_pode_deixar_alocacao_fora_do_periodo(self):
        self.alocar(datas=[date(2026, 11, 20)])
        self.tarefa.fim_previsto = date(2026, 11, 19)
        with self.assertRaises(ValidationError):
            self.tarefa.save()
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.fim_previsto, date(2026, 11, 20))
        self.assertEqual(self.tarefa.historico.count(), 1)

    def test_encerrar_tarefa_e_inativar_trabalhador_preserva_registros(self):
        registro = self.alocar()[0]
        self.tarefa.status = "CANCELADA"
        self.tarefa.save()
        self.trabalhador.ativo = False
        self.trabalhador.save()
        self.assertTrue(Alocacao.objects.filter(pk=registro.pk).exists())
        with self.assertRaises(ProtectedError):
            self.trabalhador.delete()
        with self.assertRaises(ProtectedError):
            self.montagem.delete()

    def test_consulta_eficiente_com_periodo_setor_e_permissao(self):
        self.alocar(datas=[date(2026, 11, 2), date(2026, 11, 9)])
        consulta = consultar_alocacoes(ator=self.ator, inicio=date(2026, 11, 2),
                                     fim=date(2026, 11, 6), setor_id=self.setor.pk)
        with self.assertNumQueries(1):
            linhas = [(r.trabalhador.nome, r.tarefa.titulo, r.tarefa.setor.nome,
                       r.funcao_desempenhada.nome, r.criado_por.username) for r in consulta]
        self.assertEqual(len(linhas), 1)
        with self.assertRaises(PermissionDenied):
            consultar_alocacoes(ator=AnonymousUser(), inicio=date(2026, 11, 2), fim=date(2026, 11, 6))


class AlocacaoAdminTests(AlocacaoBase):
    def setUp(self):
        self.client.force_login(self.ator)

    def dados(self, **extras):
        return {"trabalhador": self.trabalhador.pk, "tarefa": self.tarefa.pk,
                "data": "2026-11-02", "funcao_desempenhada": self.montagem.pk,
                "observacao": "Montagem do eixo", **extras}

    def dados_multidia(self, **extras):
        return self.dados(**{"inicio": "2026-11-02", "fim": "2026-11-05",
                             "dias_semana": ["0", "1", "2", "3"], **extras})

    def test_tela_multidia_cria_segunda_a_quinta_e_ignora_autor_enviado(self):
        url = reverse("admin:planejamento_alocacao_varios_dias")
        self.assertEqual(self.client.get(url).status_code, 200)
        resposta = self.client.post(url, self.dados_multidia(criado_por="9999"))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Alocacao.objects.count(), 4)
        self.assertTrue(all(r.criado_por == self.ator for r in Alocacao.objects.all()))

    def test_formulario_multidia_valida_selecao(self):
        for extras in ({"fim": "2026-11-01"}, {"dias_semana": []},
                       {"dias_semana": ["6"]}, {"fim": "2028-11-01"}):
            with self.subTest(extras=extras):
                form = AlocacaoMultidiaForm(self.dados_multidia(**extras))
                self.assertFalse(form.is_valid())

    def test_tela_multidia_exibe_erro_e_nao_cria_lote_parcial(self):
        self.alocar(datas=[date(2026, 11, 4)])
        resposta = self.client.post(reverse("admin:planejamento_alocacao_varios_dias"),
                                   self.dados_multidia())
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["form"].non_field_errors())
        self.assertEqual(Alocacao.objects.count(), 1)

    def test_cadastro_edicao_e_exclusao_de_um_dia_no_admin(self):
        resposta = self.client.post(reverse("admin:planejamento_alocacao_add"), self.dados())
        self.assertEqual(resposta.status_code, 302)
        registro = Alocacao.objects.get()
        resposta = self.client.post(reverse("admin:planejamento_alocacao_change", args=[registro.pk]),
                                   self.dados(observacao="Nota corrigida"))
        self.assertEqual(resposta.status_code, 302)
        registro.refresh_from_db()
        self.assertEqual(registro.observacao, "Nota corrigida")
        resposta = self.client.post(reverse("admin:planejamento_alocacao_delete", args=[registro.pk]),
                                   {"post": "yes"})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Alocacao.objects.exists())

    def test_admin_duplicata_e_data_invalida_sao_erros_de_formulario(self):
        self.alocar()
        for dados in (self.dados(), self.dados(data="2026-11-21")):
            with self.subTest(dados=dados):
                resposta = self.client.post(reverse("admin:planejamento_alocacao_add"), dados)
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context["adminform"].form.errors)
        self.assertEqual(Alocacao.objects.count(), 1)

    def test_consulta_nao_grava_por_tela_padrao_ou_multidia(self):
        usuario = get_user_model().objects.create_user(username="leitor_alocacao", is_staff=True)
        usuario.user_permissions.add(Permission.objects.get(
            content_type__app_label="planejamento", codename="view_alocacao"))
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("admin:planejamento_alocacao_changelist")).status_code, 200)
        for url in ("admin:planejamento_alocacao_add", "admin:planejamento_alocacao_varios_dias"):
            self.assertEqual(self.client.post(reverse(url), self.dados_multidia()).status_code, 403)
        self.assertFalse(Alocacao.objects.exists())

    def test_busca_e_filtros_na_listagem(self):
        registro = self.alocar()[0]
        resposta = self.client.get(reverse("admin:planejamento_alocacao_changelist"), {
            "q": "THC", "tarefa__setor__id__exact": self.setor.pk,
            "funcao_desempenhada__id__exact": self.montagem.pk,
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(list(resposta.context["cl"].queryset), [registro])
        self.assertContains(resposta, "Alocar vários dias")

    def test_erro_tardio_apos_insert_reverte_e_reexibe_formulario(self):
        original = Alocacao.save
        def salvar(objeto, *args, **kwargs):
            original(objeto, *args, **kwargs)
            raise ValidationError("A alocação entrou em conflito com outra gravação.")
        with patch.object(Alocacao, "save", salvar):
            resposta = self.client.post(reverse("admin:planejamento_alocacao_add"), self.dados())
        self.assertEqual(resposta.status_code, 200)
        form = resposta.context["adminform"].form
        self.assertTrue(form.is_bound)
        self.assertIn("conflito", " ".join(form.non_field_errors()))
        self.assertEqual(form["observacao"].value(), "Montagem do eixo")
        self.assertFalse(Alocacao.objects.exists())

    def test_erro_tardio_na_edicao_preserva_registro_e_autoria(self):
        registro = self.alocar(observacao="Original")[0]
        original = Alocacao.save
        chamadas = []
        def salvar(objeto, *args, **kwargs):
            chamadas.append(objeto.pk)
            original(objeto, *args, **kwargs)
            raise ValidationError({"data": ["O prazo foi alterado durante a gravação."]})
        with patch.object(Alocacao, "save", salvar):
            resposta = self.client.post(reverse("admin:planejamento_alocacao_change", args=[registro.pk]),
                                       self.dados(observacao="Correção tentada"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(chamadas, [registro.pk])
        form = resposta.context["adminform"].form
        self.assertIn("prazo", " ".join(form.non_field_errors()))
        self.assertEqual(form["observacao"].value(), "Correção tentada")
        registro.refresh_from_db()
        self.assertEqual(registro.observacao, "Original")
        self.assertEqual(registro.alterado_por, self.ator)

    def test_mudanca_de_tarefa_entre_validacao_e_save_vira_erro_de_formulario(self):
        original = Alocacao.save
        for alteracao in ({"status": "CANCELADA"}, {"inicio_previsto": date(2026, 11, 3)}):
            with self.subTest(alteracao=alteracao):
                def salvar(objeto, *args, **kwargs):
                    Tarefa.objects.filter(pk=self.tarefa.pk).update(**alteracao)
                    return original(objeto, *args, **kwargs)
                with patch.object(Alocacao, "save", salvar):
                    resposta = self.client.post(reverse("admin:planejamento_alocacao_add"), self.dados())
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context["adminform"].form.non_field_errors())
                self.assertFalse(Alocacao.objects.exists())


@skipUnless(connection.vendor == "postgresql", "Concorrência exige PostgreSQL")
class AlocacaoConcorrenciaTests(TransactionTestCase):
    def test_admin_concorrente_retorna_formulario_em_vez_de_erro_500(self):
        ator = get_user_model().objects.create_superuser(username="gestor_admin_concorrencia")
        setor = Setor.objects.create(nome="Caldeiraria")
        funcao = Funcao.objects.create(nome="Soldagem")
        trabalhador = Trabalhador.objects.create(nome="Pessoa Exemplo", setor_principal=setor,
                                                 funcao_principal=funcao)
        tarefa = Tarefa.objects.create(titulo="Eixo THC 95", setor=setor,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))
        clientes = [Client(), Client()]
        for cliente in clientes:
            cliente.force_login(ator)
        barreira = Barrier(2, timeout=10)
        original = Alocacao.save
        def salvar(objeto, *args, **kwargs):
            # Ambos os formulários já passaram por is_valid() neste ponto.
            barreira.wait()
            return original(objeto, *args, **kwargs)
        def enviar(cliente):
            close_old_connections()
            try:
                resposta = cliente.post(reverse("admin:planejamento_alocacao_add"), {
                    "trabalhador": trabalhador.pk, "tarefa": tarefa.pk,
                    "data": "2026-11-02", "funcao_desempenhada": funcao.pk,
                    "observacao": "Dados preservados",
                })
                if resposta.status_code == 200:
                    self.assertContains(resposta, "errorlist")
                    self.assertContains(resposta, "Dados preservados")
                return resposta.status_code
            finally:
                close_old_connections()
        with patch.object(Alocacao, "save", salvar), ThreadPoolExecutor(max_workers=2) as executor:
            futuros = [executor.submit(enviar, cliente) for cliente in clientes]
            resultados = [futuro.result(timeout=20) for futuro in futuros]
        self.assertCountEqual(resultados, [200, 302])
        self.assertEqual(Alocacao.objects.count(), 1)

    def test_duas_operacoes_simultaneas_nao_duplicam_alocacao(self):
        ator = get_user_model().objects.create_superuser(username="gestor_concorrencia")
        setor = Setor.objects.create(nome="Caldeiraria")
        funcao = Funcao.objects.create(nome="Soldagem")
        trabalhador = Trabalhador.objects.create(nome="Pessoa Exemplo", setor_principal=setor,
                                                 funcao_principal=funcao)
        tarefa = Tarefa.objects.create(titulo="Eixo THC 95", setor=setor,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))
        barreira = Barrier(2, timeout=10)
        def operar():
            close_old_connections()
            try:
                barreira.wait()
                alocar_dias(ator=ator, trabalhador=trabalhador, tarefa=tarefa,
                            datas=[date(2026, 11, 2)], funcao_desempenhada=funcao)
                return "criada"
            except ValidationError:
                return "duplicada"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futuros = [executor.submit(operar) for _ in range(2)]
            resultados = [futuro.result(timeout=20) for futuro in futuros]
        self.assertCountEqual(resultados, ["criada", "duplicada"])
        self.assertEqual(Alocacao.objects.count(), 1)
