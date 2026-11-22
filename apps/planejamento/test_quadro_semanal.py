from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.organizacao.models import Funcao, Setor, Trabalhador, UsuarioSetor
from .models import Tarefa
from .services import alocar_dias, consultar_alocacoes, montar_quadro_semanal, semana_de


class QuadroSemanalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(username="gestor_quadro")
        cls.leitor = get_user_model().objects.create_user(username="leitor_quadro", is_staff=True)
        cls.leitor.user_permissions.add(Permission.objects.get(
            content_type__app_label="planejamento", codename="view_alocacao"))
        cls.setor = Setor.objects.create(nome="Caldeiraria")
        cls.outro_setor = Setor.objects.create(nome="Setor reservado")
        UsuarioSetor.objects.create(usuario=cls.leitor, setor=cls.setor)
        cls.funcao = Funcao.objects.create(nome="Montagem/Soldagem")
        cls.trabalhador = Trabalhador.objects.create(nome="Aldomar",
            setor_principal=cls.setor, funcao_principal=cls.funcao)
        cls.tarefa = Tarefa.objects.create(titulo="Eixo THC 95", setor=cls.setor,
            inicio_previsto=date(2026, 10, 26), fim_previsto=date(2026, 11, 20))

    def alocar(self, datas, **dados):
        return alocar_dias(**{"ator": self.admin, "trabalhador": self.trabalhador,
            "tarefa": self.tarefa, "funcao_desempenhada": self.funcao, "datas": datas, **dados})

    def quadro(self, **dados):
        return montar_quadro_semanal(**{"ator": self.leitor, "semana": date(2026, 11, 4), **dados})

    def consultar(self, **dados):
        self.client.force_login(self.leitor)
        return self.client.get(reverse("planejamento:quadro_semanal"),
                               {"semana": "2026-11-04", **dados})

    def dados_reservados(self):
        tarefa = Tarefa.objects.create(titulo="Atividade sigilosa", setor=self.outro_setor,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))
        pessoa = Trabalhador.objects.create(nome="Pessoa reservada", setor_principal=self.outro_setor,
                                            funcao_principal=self.funcao)
        self.alocar([date(2026, 11, 7)], tarefa=tarefa, trabalhador=pessoa, observacao="Nota reservada")

    def test_cenario_segunda_a_quinta(self):
        self.alocar([date(2026, 11, dia) for dia in (2, 3, 4, 5)])
        quadro = self.quadro()
        self.assertEqual(quadro["inicio"], date(2026, 11, 2))
        self.assertEqual(len(quadro["dias"]), 5)
        self.assertEqual(len(quadro["linhas"]), 1)
        linha = quadro["linhas"][0]
        self.assertEqual(linha["trabalhador"].nome, "Aldomar")
        self.assertEqual(linha["funcao"].nome, "Montagem/Soldagem")
        self.assertEqual(linha["tarefa"].titulo, "Eixo THC 95")
        self.assertEqual([bool(c["alocacao"]) for c in linha["celulas"]], [True]*4+[False])

    def test_segunda_tarefa_na_terca_nao_substitui_primeira(self):
        self.alocar([date(2026, 11, 3)])
        outra = Tarefa.objects.create(titulo="Segundo conjunto", setor=self.setor,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))
        self.alocar([date(2026, 11, 3)], tarefa=outra)
        linhas = self.quadro()["linhas"]
        self.assertEqual(len(linhas), 2)
        self.assertTrue(all(linha["celulas"][1]["alocacao"] for linha in linhas))

    def test_atividades_da_tarefa_nao_duplicam_linhas_e_homonimos_nao_sao_mesclados(self):
        self.alocar([date(2026, 11, 2)])
        outra_funcao = Funcao.objects.create(nome="Inspeção")
        self.tarefa.save(atividades=[self.funcao, outra_funcao])
        self.alocar([date(2026, 11, 3)])
        homonimo = Trabalhador.objects.create(nome="Aldomar", setor_principal=self.setor,
                                              funcao_principal=self.funcao)
        self.alocar([date(2026, 11, 2)], trabalhador=homonimo)
        self.assertEqual(len(self.quadro()["linhas"]), 2)
        self.assertTrue(all("Inspeção" in linha["atividades"] for linha in self.quadro()["linhas"]))

    def test_continuidade_entre_tres_semanas_sem_inventar_alocacoes(self):
        self.alocar([date(2026, 10, 30), date(2026, 11, 4), date(2026, 11, 9)])
        for dia in (date(2026, 10, 30), date(2026, 11, 4), date(2026, 11, 9)):
            with self.subTest(dia=dia):
                quadro = self.quadro(semana=dia)
                self.assertEqual(len(quadro["linhas"]), 1)
                alocadas = [c["data"] for c in quadro["linhas"][0]["celulas"] if c["alocacao"]]
                self.assertEqual(alocadas, [dia])
                self.assertEqual(quadro["linhas"][0]["tarefa"].inicio_previsto, date(2026, 10, 26))

    def test_fim_de_semana_automatico_ou_por_selecao(self):
        self.assertEqual(len(self.quadro()["dias"]), 5)
        self.assertEqual(len(self.quadro(fim_semana=True)["dias"]), 7)
        self.alocar([date(2026, 11, 7), date(2026, 11, 8)])
        quadro = self.quadro()
        self.assertEqual(len(quadro["dias"]), 7)
        self.assertTrue(quadro["linhas"][0]["celulas"][6]["alocacao"])

    def test_alocacoes_historicas_permanecem_visiveis(self):
        self.alocar([date(2026, 11, 2)])
        self.tarefa.status = "CANCELADA"
        self.tarefa.save()
        self.trabalhador.ativo = False
        self.trabalhador.save()
        self.assertEqual(len(self.quadro()["linhas"]), 1)

    def test_servico_restringe_escopo_com_ou_sem_filtro(self):
        self.dados_reservados()
        self.alocar([date(2026, 11, 2)])
        registros = consultar_alocacoes(ator=self.leitor, inicio=date(2026, 11, 2), fim=date(2026, 11, 8))
        self.assertEqual(registros.count(), 1)
        with self.assertRaises(PermissionDenied):
            self.quadro(setor_id=self.outro_setor.pk)
        self.assertEqual(len(self.quadro()["dias"]), 5)  # Nem o sábado reservado vaza.
        self.assertEqual(len(self.quadro(ator=self.admin)["linhas"]), 2)

    def test_tela_nao_vaza_nomes_opcoes_ou_observacoes(self):
        self.dados_reservados()
        self.alocar([date(2026, 11, 2)])
        resposta = self.consultar()
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Eixo THC 95")
        for texto in ("Atividade sigilosa", "Setor reservado", "Pessoa reservada", "Nota reservada"):
            self.assertNotContains(resposta, texto)
        negado = self.consultar(setor=self.outro_setor.pk)
        self.assertEqual(negado.status_code, 400)
        self.assertNotIn("Atividade sigilosa", negado.content.decode())

    def test_sem_vinculo_nao_ve_setores_nem_alocacoes(self):
        self.alocar([date(2026, 11, 2)])
        UsuarioSetor.objects.filter(usuario=self.leitor).delete()
        resposta = self.consultar()
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Nenhuma alocação")
        self.assertNotContains(resposta, "Eixo THC 95")
        self.assertNotContains(resposta, "Caldeiraria")

    def test_login_permissao_e_metodo_somente_consulta(self):
        url = reverse("planejamento:quadro_semanal")
        self.assertEqual(self.client.get(url).status_code, 302)
        sem_permissao = get_user_model().objects.create_user(username="sem_acesso_quadro")
        UsuarioSetor.objects.create(usuario=sem_permissao, setor=self.setor)
        self.client.force_login(sem_permissao)
        self.assertEqual(self.client.get(url).status_code, 403)
        with self.assertRaises(PermissionDenied):
            self.quadro(ator=AnonymousUser())
        self.client.force_login(self.leitor)
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_navegacao_preserva_filtro_e_opcao_de_fim_de_semana(self):
        resposta = self.consultar(setor=self.setor.pk, fim_semana="on")
        self.assertEqual(resposta.context["url_anterior"],
                         f"?semana=2026-10-26&setor={self.setor.pk}&fim_semana=on")
        self.assertEqual(resposta.context["url_proxima"],
                         f"?semana=2026-11-09&setor={self.setor.pk}&fim_semana=on")

    def test_semana_atual_e_usada_sem_parametros(self):
        self.client.force_login(self.leitor)
        with patch("apps.planejamento.views.timezone.localdate", return_value=date(2026, 11, 4)):
            resposta = self.client.get(reverse("planejamento:quadro_semanal"))
        self.assertEqual(resposta.context["inicio"], date(2026, 11, 2))

    def test_datas_invalidas_e_limites_de_calendario(self):
        for semana in ("invalida", "", "9999-12-31"):
            with self.subTest(semana=semana):
                self.assertEqual(self.consultar(semana=semana).status_code, 400)
        self.assertIsNone(self.quadro(semana=date.min)["anterior"])
        with self.assertRaises(ValidationError):
            semana_de(date.max)

    def test_consulta_de_muitas_linhas_sem_n_mais_um(self):
        self.alocar([date(2026, 11, dia) for dia in (2, 3, 4, 5)])
        # Superusuário dispensa consulta de permissões; escopo usa subconsulta SQL.
        with self.assertNumQueries(2):
            quadro = self.quadro(ator=self.admin)
            self.assertEqual(quadro["linhas"][0]["tarefa"].setor.nome, "Caldeiraria")

    def test_template_escapa_conteudo_e_oferece_impressao(self):
        self.alocar([date(2026, 11, 2)], observacao="<script>alert(1)</script>")
        resposta = self.consultar()
        self.assertContains(resposta, "&lt;script&gt;")
        self.assertNotContains(resposta, "<script>")
        self.assertContains(resposta, "@media print")
        self.assertContains(resposta, "scope=\"col\"")

    def test_admin_de_vinculos_so_acessivel_com_permissao_propria(self):
        self.client.force_login(self.leitor)
        self.assertEqual(self.client.post(reverse("admin:organizacao_usuariosetor_add"),
            {"usuario": self.leitor.pk, "setor": self.outro_setor.pk}).status_code, 403)
        self.assertFalse(UsuarioSetor.objects.filter(usuario=self.leitor, setor=self.outro_setor).exists())
