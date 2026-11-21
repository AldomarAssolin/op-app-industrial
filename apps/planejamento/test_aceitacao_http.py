"""Aceitação HTTP complementar: servidor real, login e CSRF sem force_login."""

from datetime import date
from http.cookiejar import CookieJar
from io import StringIO
import secrets
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, Request

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import LiveServerTestCase, override_settings
from django.urls import reverse

from apps.organizacao.models import Funcao, Setor, Trabalhador, UsuarioSetor
from .models import Alocacao, HistoricoTarefa, Tarefa


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class AceitacaoHTTPTests(LiveServerTestCase):
    """Banco de teste descartável; nunca usa contas ou registros do piloto."""

    def setUp(self):
        call_command("configurar_perfis", stdout=StringIO())
        self.a = Setor.objects.create(nome="QA HTTP Setor A")
        self.b = Setor.objects.create(nome="QA HTTP Setor B")
        self.funcao = Funcao.objects.create(nome="QA HTTP Função")
        self.pessoa_a = Trabalhador.objects.create(
            nome="QA HTTP Pessoa A", setor_principal=self.a, funcao_principal=self.funcao)
        self.pessoa_b = Trabalhador.objects.create(
            nome="QA HTTP Pessoa B", setor_principal=self.b, funcao_principal=self.funcao)
        self.tarefa_a = Tarefa.objects.create(titulo="QA HTTP Tarefa A", setor=self.a,
            inicio_previsto=date(2026, 11, 16), fim_previsto=date(2026, 11, 27))
        self.tarefa_b = Tarefa.objects.create(titulo="QA HTTP Tarefa B", setor=self.b,
            inicio_previsto=date(2026, 11, 16), fim_previsto=date(2026, 11, 27))
        self.senha = secrets.token_urlsafe(24)
        self.usuarios = {}
        for nome, grupo in (("lider", "Líder"), ("consulta", "Consulta"),
                            ("coordenador", "Coordenador")):
            usuario = get_user_model().objects.create_user(
                username="qa_http_" + nome, password=self.senha, is_staff=True)
            usuario.groups.add(Group.objects.get(name=grupo))
            UsuarioSetor.objects.create(usuario=usuario, setor=self.a)
            self.usuarios[nome] = usuario
        self.alocacao = Alocacao(trabalhador=self.pessoa_a,
            tarefa=self.tarefa_a, data=date(2026, 11, 16), funcao_desempenhada=self.funcao)
        self.alocacao.save(ator=self.usuarios["lider"])
        self.cookies = CookieJar()
        self.http = build_opener(HTTPCookieProcessor(self.cookies), SemRedirecionamento())

    def requisicao(self, caminho, dados=None, *, csrf=True, headers=None):
        cabecalhos = dict(headers or {})
        corpo = None
        if dados is not None:
            dados = dict(dados)
            if csrf:
                token = next(c.value for c in self.cookies if c.name == "csrftoken")
                dados["csrfmiddlewaretoken"] = token
            corpo = urlencode(dados, doseq=True).encode()
        req = Request(self.live_server_url + caminho, data=corpo, headers=cabecalhos)
        try:
            resposta = self.http.open(req, timeout=10)
        except HTTPError as erro:
            resposta = erro
        with resposta:
            return resposta.code, resposta.read().decode(), resposta.headers

    def entrar(self, papel):
        self.assertEqual(self.requisicao(reverse("admin:login"))[0], 200)
        codigo, _, _ = self.requisicao(reverse("admin:login"), {
            "username": self.usuarios[papel].username, "password": self.senha,
            "next": reverse("admin:index"),
        })
        self.assertEqual(codigo, 302)
        self.assertEqual(self.requisicao(reverse("admin:index"))[0], 200)

    def estado(self):
        return [list(model.objects.order_by("pk").values())
                for model in (Trabalhador, Tarefa, HistoricoTarefa, Alocacao)]

    def dados_alocacao(self, **extras):
        return {"trabalhador": self.pessoa_a.pk, "tarefa": self.tarefa_a.pk,
                "data": "2026-11-17", "funcao_desempenhada": self.funcao.pk, **extras}

    def test_consulta_post_criar_editar_excluir_com_csrf_valido_nao_muda_banco(self):
        # Permissões acidentais não devem sobrepor a política de Consulta.
        self.usuarios["consulta"].user_permissions.add(*Permission.objects.filter(
            content_type__app_label="planejamento"))
        self.entrar("consulta")
        antes = self.estado()
        for modelo, pk, dados in (
            ("tarefa", self.tarefa_a.pk, {"titulo": "Alteração indevida"}),
            ("alocacao", self.alocacao.pk, self.dados_alocacao(observacao="Indevida")),
        ):
            for acao in ("add", "change", "delete"):
                with self.subTest(modelo=modelo, acao=acao):
                    url = reverse(f"admin:planejamento_{modelo}_{acao}",
                                  args=[] if acao == "add" else [pk])
                    codigo, _, _ = self.requisicao(url, {**dados, "post": "yes"})
                    self.assertEqual(codigo, 403)
                    self.assertEqual(self.estado(), antes)

    def test_lider_ids_adulterados_individual_e_multidia_sem_gravacao(self):
        self.entrar("lider")
        antes = self.estado()
        for campo, pk in (("trabalhador", self.pessoa_b.pk), ("tarefa", self.tarefa_b.pk)):
            for multidia in (False, True):
                with self.subTest(campo=campo, multidia=multidia):
                    dados = self.dados_alocacao(**{campo: pk})
                    rota = "admin:planejamento_alocacao_add"
                    if multidia:
                        rota = "admin:planejamento_alocacao_varios_dias"
                        dados.update(inicio="2026-11-17", fim="2026-11-18",
                                     dias_semana=["1", "2"])
                    codigo, html, _ = self.requisicao(reverse(rota), dados)
                    self.assertEqual(codigo, 200)
                    self.assertIn("errorlist", html)
                    self.assertNotIn(self.pessoa_b.nome, html)
                    self.assertNotIn(self.tarefa_b.titulo, html)
                    self.assertEqual(self.estado(), antes)

    def test_coordenador_cria_em_a_e_nao_transfere_entre_a_e_b_por_post(self):
        self.entrar("coordenador")
        dados = {"nome": "QA HTTP Nova pessoa", "ativo": "on",
                 "setor_principal": self.a.pk, "funcao_principal": self.funcao.pk}
        codigo, _, _ = self.requisicao(reverse("admin:organizacao_trabalhador_add"), dados)
        self.assertEqual(codigo, 302)
        novo = Trabalhador.objects.get(nome=dados["nome"])
        self.assertEqual(novo.setor_principal_id, self.a.pk)
        antes = self.estado()
        codigo, html, _ = self.requisicao(
            reverse("admin:organizacao_trabalhador_change", args=[novo.pk]),
            {**dados, "setor_principal": self.b.pk})
        self.assertEqual(codigo, 200)
        self.assertIn("errorlist", html)
        self.assertEqual(self.estado(), antes)
        # Origem reservada continua protegida mesmo enviando destino permitido.
        codigo, html, _ = self.requisicao(
            reverse("admin:organizacao_trabalhador_change", args=[self.pessoa_b.pk]), dados)
        self.assertIn(codigo, (302, 403, 404))
        self.assertNotIn(self.pessoa_b.nome, html)
        self.assertEqual(self.estado(), antes)

    def test_csrf_cookies_e_logout_invalidam_sessao_local(self):
        self.entrar("lider")
        sessao = next(c for c in self.cookies if c.name == "sessionid")
        self.assertTrue(sessao.has_nonstandard_attr("HttpOnly"))
        self.assertEqual(sessao.get_nonstandard_attr("SameSite"), "Lax")
        sessao_antiga = sessao.value
        antes = self.estado()
        codigo, _, _ = self.requisicao(reverse("admin:planejamento_alocacao_add"),
                                      self.dados_alocacao(), csrf=False)
        self.assertEqual(codigo, 403)
        self.assertEqual(self.estado(), antes)
        codigo, _, _ = self.requisicao(reverse("admin:logout"), {})
        self.assertEqual(codigo, 200)
        # Reapresentar o cookie antigo não recupera uma sessão encerrada.
        self.cookies.clear()
        codigo, _, headers = self.requisicao(reverse("planejamento:quadro_semanal"),
                                             headers={"Cookie": "sessionid=" + sessao_antiga})
        self.assertEqual(codigo, 302)
        self.assertIn(reverse("login_operacional"), headers["Location"])

    def test_exclusao_de_alocacao_permitida_e_tarefa_protegida(self):
        self.entrar("lider")
        codigo, _, _ = self.requisicao(
            reverse("admin:planejamento_tarefa_delete", args=[self.tarefa_a.pk]),
            {"post": "yes"})
        self.assertEqual(codigo, 403)
        self.assertTrue(Tarefa.objects.filter(pk=self.tarefa_a.pk).exists())
        codigo, _, _ = self.requisicao(
            reverse("admin:planejamento_alocacao_delete", args=[self.alocacao.pk]),
            {"post": "yes"})
        self.assertEqual(codigo, 302)
        self.assertFalse(Alocacao.objects.filter(pk=self.alocacao.pk).exists())
        self.assertTrue(Tarefa.objects.filter(pk=self.tarefa_a.pk).exists())
