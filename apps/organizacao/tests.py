from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Funcao, Setor, Trabalhador


class OrganizacaoConfigTests(SimpleTestCase):
    """Verifica o registro do aplicativo organizacao."""

    def test_app_esta_registrado(self):
        app_config = apps.get_app_config("organizacao")

        self.assertEqual(
            app_config.name,
            "apps.organizacao",
        )

    def test_app_utiliza_configuracao_correta(self):
        app_config = apps.get_app_config("organizacao")

        self.assertEqual(
            app_config.__class__.__name__,
            "OrganizacaoConfig",
        )


class CadastrosTests(TestCase):
    def test_normaliza_espacos_e_unicode_preservando_grafia(self):
        for modelo in (Setor, Funcao):
            with self.subTest(modelo=modelo):
                cadastro = modelo.objects.create(nome="  Inspec\u0327a\u0303o \t Final  ")
                cadastro.refresh_from_db()
                self.assertEqual(cadastro.nome, "Inspeção Final")
                self.assertTrue(cadastro.ativo)

    def test_nome_obrigatorio_e_limite_de_tamanho(self):
        for modelo in (Setor, Funcao):
            for nome in ("", " \t ", None, "x" * 151):
                with self.subTest(modelo=modelo, nome=nome):
                    with self.assertRaises(ValidationError) as erro:
                        modelo.objects.create(nome=nome)
                    self.assertIn("nome", erro.exception.message_dict)

    def test_rejeita_duplicata_normalizada_mesmo_inativa(self):
        for modelo in (Setor, Funcao):
            with self.subTest(modelo=modelo):
                original = modelo.objects.create(nome="Corte Plasma", ativo=False)
                with self.assertRaises(ValidationError):
                    modelo.objects.create(nome="  CORTE   PLASMA ")
                self.assertEqual(modelo.objects.count(), 1)
                original.ativo = True
                original.save()
                self.assertTrue(modelo.objects.get(pk=original.pk).ativo)

    def test_unicidade_tambem_e_garantida_pelo_banco(self):
        for modelo in (Setor, Funcao):
            with self.subTest(modelo=modelo):
                modelo.objects.create(nome="Montagem")
                outro = modelo.objects.create(nome="Usinagem")
                with self.assertRaises(IntegrityError), transaction.atomic():
                    # UPDATE ignora save/full_clean: exercita a constraint real.
                    modelo.objects.filter(pk=outro.pk).update(nome="MONTAGEM")

    def test_edicao_do_proprio_nome_e_descricao(self):
        for modelo in (Setor, Funcao):
            with self.subTest(modelo=modelo):
                cadastro = modelo.objects.create(nome="Soldagem")
                cadastro.nome = "  SOLDAGEM  "
                cadastro.descricao = "Soldagem de conjuntos"
                cadastro.save()
                cadastro.refresh_from_db()
                self.assertEqual(cadastro.nome, "SOLDAGEM")
                self.assertEqual(cadastro.descricao, "Soldagem de conjuntos")


class TrabalhadorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.setor = Setor.objects.create(nome="Caldeiraria")
        cls.funcao = Funcao.objects.create(nome="Soldador")

    def criar(self, **dados):
        return Trabalhador.objects.create(**{
            "nome": "  Pessoa   Exemplo  ",
            "setor_principal": self.setor,
            "funcao_principal": self.funcao,
            **dados,
        })

    def test_homonimos_sao_permitidos_e_identificados_pelo_id(self):
        primeiro = self.criar()
        segundo = self.criar()
        self.assertEqual(primeiro.nome, "Pessoa Exemplo")
        self.assertNotEqual(primeiro.pk, segundo.pk)
        self.assertNotEqual(str(primeiro), str(segundo))
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_exige_nome_setor_e_funcao(self):
        for campo, valor in (("nome", " \t"), ("setor_principal", None),
                             ("funcao_principal", None)):
            with self.subTest(campo=campo):
                with self.assertRaises(ValidationError) as erro:
                    self.criar(**{campo: valor})
                self.assertIn(campo, erro.exception.message_dict)

    def test_rejeita_referencia_inexistente(self):
        trabalhador = Trabalhador(
            nome="Pessoa Exemplo", setor_principal_id=99999,
            funcao_principal=self.funcao,
        )
        with self.assertRaises(ValidationError) as erro:
            trabalhador.save()
        self.assertIn("setor_principal", erro.exception.message_dict)

    def test_protege_setor_e_funcao_com_trabalhador_inativo(self):
        trabalhador = self.criar(ativo=False)
        for cadastro in (self.setor, self.funcao):
            with self.subTest(modelo=type(cadastro)):
                with self.assertRaises(ProtectedError):
                    cadastro.delete()
                with self.assertRaises(ProtectedError):
                    type(cadastro).objects.filter(pk=cadastro.pk).delete()
        trabalhador.refresh_from_db()
        self.assertEqual(trabalhador.setor_principal_id, self.setor.pk)
        self.assertEqual(trabalhador.funcao_principal_id, self.funcao.pk)

    def test_inativacao_preserva_vinculos_sem_cascata(self):
        trabalhador = self.criar()
        for cadastro in (self.setor, self.funcao):
            cadastro.ativo = False
            cadastro.save()
        trabalhador.refresh_from_db()
        self.assertTrue(trabalhador.ativo)
        trabalhador.ativo = False
        trabalhador.save()
        trabalhador.refresh_from_db()
        self.assertFalse(trabalhador.ativo)
        self.assertEqual(trabalhador.setor_principal_id, self.setor.pk)
        self.assertEqual(trabalhador.funcao_principal_id, self.funcao.pk)

    def test_alterar_lotacao_e_reativar_mantem_o_id(self):
        trabalhador = self.criar(ativo=False)
        identidade = trabalhador.pk
        novo_setor = Setor.objects.create(nome="Montagem")
        nova_funcao = Funcao.objects.create(nome="Montador")
        trabalhador.setor_principal = novo_setor
        trabalhador.funcao_principal = nova_funcao
        trabalhador.ativo = True
        trabalhador.save()
        trabalhador.refresh_from_db()
        self.assertEqual(trabalhador.pk, identidade)
        self.assertEqual(trabalhador.setor_principal, novo_setor)
        self.assertEqual(trabalhador.funcao_principal, nova_funcao)
        self.assertTrue(trabalhador.ativo)

    def test_registro_sem_vinculos_pode_ser_excluido(self):
        setor = Setor.objects.create(nome="Setor cadastrado por engano")
        setor.delete()
        self.assertFalse(Setor.objects.filter(nome=setor.nome).exists())


class OrganizacaoAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="admin_teste", password="senha_sintetica_admin",
        )
        cls.setor = Setor.objects.create(nome="Caldeiraria")
        cls.funcao = Funcao.objects.create(nome="Soldador")

    def setUp(self):
        self.client.force_login(self.admin)

    def url(self, modelo, acao, objeto=None):
        return reverse(f"admin:organizacao_{modelo._meta.model_name}_{acao}",
                       args=[objeto.pk] if objeto else None)

    def test_cadastro_edicao_e_inativacao_dos_tres_modelos(self):
        for modelo in (Setor, Funcao, Trabalhador):
            with self.subTest(modelo=modelo):
                dados = {"nome": "  Novo   Cadastro  ", "ativo": "on"}
                if modelo is Trabalhador:
                    dados.update(setor_principal=self.setor.pk,
                                 funcao_principal=self.funcao.pk)
                resposta = self.client.post(self.url(modelo, "add"), dados)
                self.assertEqual(resposta.status_code, 302)
                objeto = modelo.objects.get(nome="Novo Cadastro")
                self.assertTrue(objeto.ativo)
                dados["nome"] = "Cadastro Editado"
                dados.pop("ativo")
                resposta = self.client.post(self.url(modelo, "change", objeto), dados)
                self.assertEqual(resposta.status_code, 302)
                objeto.refresh_from_db()
                self.assertEqual(objeto.nome, "Cadastro Editado")
                self.assertFalse(objeto.ativo)

    def test_admin_exibe_erro_de_duplicata_sem_gravar(self):
        for modelo, nome in ((Setor, "CALDEIRARIA"), (Funcao, "SOLDADOR")):
            with self.subTest(modelo=modelo):
                resposta = self.client.post(self.url(modelo, "add"),
                                           {"nome": f" {nome} ", "ativo": "on"})
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context["adminform"].form.errors)
                self.assertEqual(modelo.objects.count(), 1)

    def test_admin_permite_homonimos(self):
        dados = {"nome": "Pessoa Exemplo", "setor_principal": self.setor.pk,
                 "funcao_principal": self.funcao.pk, "ativo": "on"}
        for _ in range(2):
            self.assertEqual(self.client.post(self.url(Trabalhador, "add"),
                                             dados).status_code, 302)
        self.assertEqual(Trabalhador.objects.filter(nome="Pessoa Exemplo").count(), 2)

    def test_busca_e_filtro_de_cadastros_auxiliares(self):
        for modelo in (Setor, Funcao):
            with self.subTest(modelo=modelo):
                alvo = modelo.objects.create(nome="Inspeção", descricao="Ensaio visual",
                                             ativo=False)
                resposta = self.client.get(self.url(modelo, "changelist"),
                                           {"q": "Ensaio", "ativo__exact": "0"})
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(list(resposta.context["cl"].queryset), [alvo])

    def test_busca_e_filtros_de_trabalhadores(self):
        alvo = Trabalhador.objects.create(nome="Pessoa Exemplo",
            setor_principal=self.setor, funcao_principal=self.funcao, ativo=False)
        outro_setor = Setor.objects.create(nome="Usinagem")
        outra_funcao = Funcao.objects.create(nome="Operador")
        Trabalhador.objects.create(nome="Outro Trabalhador", setor_principal=outro_setor,
                                   funcao_principal=outra_funcao)
        for busca in ("Pessoa", "Caldeiraria", "Soldador"):
            with self.subTest(busca=busca):
                resposta = self.client.get(self.url(Trabalhador, "changelist"), {
                    "q": busca, "ativo__exact": "0",
                    "setor_principal__id__exact": str(self.setor.pk),
                    "funcao_principal__id__exact": str(self.funcao.pk),
                })
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(list(resposta.context["cl"].queryset), [alvo])

    def test_admin_bloqueia_exclusao_de_registros_vinculados(self):
        Trabalhador.objects.create(nome="Pessoa Exemplo", setor_principal=self.setor,
                                   funcao_principal=self.funcao)
        for objeto in (self.setor, self.funcao):
            with self.subTest(modelo=type(objeto)):
                resposta = self.client.post(self.url(type(objeto), "delete", objeto),
                                           {"post": "yes"})
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context["protected"])
                self.assertTrue(type(objeto).objects.filter(pk=objeto.pk).exists())

    def test_staff_com_consulta_nao_pode_gravar(self):
        consulta = get_user_model().objects.create_user(username="consulta", is_staff=True)
        consulta.user_permissions.add(Permission.objects.get(
            content_type__app_label="organizacao", codename="view_setor"))
        self.client.force_login(consulta)
        self.assertEqual(self.client.get(self.url(Setor, "changelist")).status_code, 200)
        self.assertEqual(self.client.post(self.url(Setor, "add"),
                                         {"nome": "Indevido"}).status_code, 403)
        self.assertEqual(self.client.post(self.url(Setor, "change", self.setor),
                                         {"nome": "Indevido"}).status_code, 403)
        self.setor.refresh_from_db()
        self.assertEqual(self.setor.nome, "Caldeiraria")
