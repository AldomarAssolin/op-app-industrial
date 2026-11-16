from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizacao.models import Setor, Funcao, Trabalhador, UsuarioSetor
from apps.organizacao.autorizacao import setores_do_usuario
from .models import Tarefa, Alocacao
from .services import alocar_dias, consultar_alocacoes


class AutorizacaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("configurar_perfis", stdout=StringIO())
        cls.superusuario = get_user_model().objects.create_superuser(username="bootstrap")
        cls.setor = Setor.objects.create(nome="Setor permitido")
        cls.reservado = Setor.objects.create(nome="Setor reservado")
        cls.funcao = Funcao.objects.create(nome="Soldagem")
        cls.trabalhador = Trabalhador.objects.create(nome="Pessoa permitida",
            setor_principal=cls.setor, funcao_principal=cls.funcao)
        cls.outro_trabalhador = Trabalhador.objects.create(nome="Pessoa reservada",
            setor_principal=cls.reservado, funcao_principal=cls.funcao)
        cls.tarefa = Tarefa.objects.create(titulo="Atividade permitida", setor=cls.setor,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))
        cls.outra_tarefa = Tarefa.objects.create(titulo="Atividade reservada", setor=cls.reservado,
            inicio_previsto=date(2026, 11, 2), fim_previsto=date(2026, 11, 20))
        cls.lider = cls.usuario("lider", "Líder")
        cls.coordenador = cls.usuario("coordenador", "Coordenador")
        cls.consulta = cls.usuario("consulta", "Consulta")
        cls.administrador = cls.usuario("administrador", "Administrador")
        cls.alocacao = cls.alocar(ator=cls.superusuario)[0]
        cls.outra_alocacao = cls.alocar(ator=cls.superusuario,
            trabalhador=cls.outro_trabalhador, tarefa=cls.outra_tarefa)[0]

    @classmethod
    def usuario(cls, nome, grupo):
        usuario = get_user_model().objects.create_user(username=nome, is_staff=True)
        usuario.groups.add(Group.objects.get(name=grupo))
        UsuarioSetor.objects.create(usuario=usuario, setor=cls.setor)
        return usuario

    @classmethod
    def alocar(cls, **dados):
        return alocar_dias(**{
            "ator": cls.lider, "trabalhador": cls.trabalhador, "tarefa": cls.tarefa,
            "datas": [date(2026, 11, 3)], "funcao_desempenhada": cls.funcao, **dados,
        })

    def entrar(self, usuario=None):
        self.client.force_login(usuario or self.lider)

    def dados_alocacao(self, **extras):
        return {"trabalhador": self.trabalhador.pk, "tarefa": self.tarefa.pk,
                "data": "2026-11-04", "funcao_desempenhada": self.funcao.pk, **extras}

    def dados_tarefa(self, tarefa=None, **extras):
        tarefa = tarefa or self.tarefa
        registros = list(tarefa.historico.filter(setor=self.setor))
        dados = {"titulo": tarefa.titulo, "setor": tarefa.setor_id,
                 "inicio_previsto": "2026-11-02", "fim_previsto": "2026-11-20",
                 "status": tarefa.status, "historico-TOTAL_FORMS": str(len(registros)),
                 "historico-INITIAL_FORMS": str(len(registros)), **extras}
        for i, registro in enumerate(registros):
            dados[f"historico-{i}-id"] = registro.pk
            dados[f"historico-{i}-tarefa"] = tarefa.pk
        return dados

    def test_grupos_idempotentes_e_sem_permissoes_de_elevacao(self):
        antes = {g.name: set(g.permissions.values_list("pk", flat=True)) for g in Group.objects.all()}
        call_command("configurar_perfis", stdout=StringIO())
        depois = {g.name: set(g.permissions.values_list("pk", flat=True)) for g in Group.objects.all()}
        self.assertEqual(antes, depois)
        for grupo in Group.objects.all():
            self.assertFalse(grupo.permissions.filter(content_type__app_label="auth").exists())
            self.assertFalse(grupo.permissions.filter(codename__contains="usuariosetor").exists())
        self.assertFalse(self.consulta.has_perm("planejamento.change_tarefa"))
        self.assertTrue(self.lider.has_perm("planejamento.change_tarefa"))
        self.assertFalse(self.lider.has_perm("organizacao.change_trabalhador"))
        self.assertTrue(self.coordenador.has_perm("organizacao.change_trabalhador"))

    def test_administrador_operacional_possui_escopo_global(self):
        self.assertEqual(set(setores_do_usuario(self.administrador)), {self.setor, self.reservado})
        self.entrar(self.administrador)
        resposta = self.client.get(reverse("admin:planejamento_tarefa_changelist"))
        self.assertContains(resposta, "Atividade reservada")

    def test_listagens_buscas_e_filtros_nao_expoem_outro_setor(self):
        self.entrar()
        for nome in ("planejamento_tarefa", "planejamento_alocacao", "organizacao_trabalhador", "organizacao_setor"):
            resposta = self.client.get(reverse(f"admin:{nome}_changelist"))
            self.assertEqual(resposta.status_code, 200)
            for texto in ("Pessoa reservada", "Atividade reservada", "Setor reservado"):
                self.assertNotContains(resposta, texto)
        resposta = self.client.get(reverse("admin:planejamento_tarefa_changelist"),
            {"setor__id__exact": self.reservado.pk, "q": "reservada"})
        self.assertNotContains(resposta, "Atividade reservada")

    def test_detalhe_historico_e_gravacao_de_tarefa_fora_do_escopo(self):
        self.entrar()
        for acao in ("change", "history", "delete"):
            resposta = self.client.get(reverse(f"admin:planejamento_tarefa_{acao}", args=[self.outra_tarefa.pk]))
            self.assertIn(resposta.status_code, (302, 403, 404))
            self.assertNotIn("Atividade reservada", resposta.content.decode())
        self.client.post(reverse("admin:planejamento_tarefa_change", args=[self.outra_tarefa.pk]),
                         self.dados_tarefa(self.outra_tarefa, titulo="Tentativa"))
        self.outra_tarefa.refresh_from_db()
        self.assertEqual(self.outra_tarefa.titulo, "Atividade reservada")

    def test_lider_altera_tarefa_permitida_e_registra_autor(self):
        self.entrar()
        resposta = self.client.post(reverse("admin:planejamento_tarefa_change", args=[self.tarefa.pk]),
                                   self.dados_tarefa(status="EM_ANDAMENTO", registrado_por=self.superusuario.pk))
        self.assertEqual(resposta.status_code, 302)
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.status, "EM_ANDAMENTO")
        self.assertEqual(self.tarefa.historico.last().registrado_por, self.lider)

    def test_troca_de_setor_por_post_nao_amplia_acesso(self):
        self.entrar()
        resposta = self.client.post(reverse("admin:planejamento_tarefa_change", args=[self.tarefa.pk]),
                                   self.dados_tarefa(setor=self.reservado.pk))
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["adminform"].form.errors)
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.setor_id, self.setor.pk)
        self.tarefa.setor = self.reservado
        with self.assertRaises(PermissionDenied):
            self.tarefa.save(ator=self.lider)

    def test_alocacao_cruzada_bloqueada_no_modelo_e_no_lote(self):
        for dados in ({"tarefa": self.outra_tarefa}, {"trabalhador": self.outro_trabalhador}):
            with self.subTest(dados=dados), self.assertRaises(PermissionDenied):
                self.alocar(datas=[date(2026, 11, 4)], **dados)
        self.assertEqual(Alocacao.objects.count(), 2)

    def test_alterar_ou_excluir_registro_reservado_pelo_modelo_e_bloqueado(self):
        registro = Alocacao.objects.get(pk=self.outra_alocacao.pk)
        registro.tarefa = self.tarefa
        registro.trabalhador = self.trabalhador
        with self.assertRaises(PermissionDenied):
            registro.save(ator=self.lider)
        with self.assertRaises(PermissionDenied):
            self.outra_alocacao.delete(ator=self.lider)
        self.assertTrue(Alocacao.objects.filter(pk=self.outra_alocacao.pk).exists())

    def test_admin_alocacao_filtra_escolhas_e_rejeita_ids_forjados(self):
        self.entrar()
        resposta = self.client.get(reverse("admin:planejamento_alocacao_add"))
        self.assertNotContains(resposta, "Atividade reservada")
        self.assertNotContains(resposta, "Pessoa reservada")
        for dados in (self.dados_alocacao(tarefa=self.outra_tarefa.pk),
                      self.dados_alocacao(trabalhador=self.outro_trabalhador.pk)):
            resposta = self.client.post(reverse("admin:planejamento_alocacao_add"), dados)
            self.assertEqual(resposta.status_code, 200)
            self.assertTrue(resposta.context["adminform"].form.errors)

    def test_multidia_filtro_e_post_forjado_nao_vazam_nem_gravam(self):
        self.entrar()
        url = reverse("admin:planejamento_alocacao_varios_dias")
        resposta = self.client.get(url)
        self.assertNotContains(resposta, "Atividade reservada")
        self.assertNotContains(resposta, "Pessoa reservada")
        dados = self.dados_alocacao(tarefa=self.outra_tarefa.pk,
            inicio="2026-11-04", fim="2026-11-05", dias_semana=["2", "3"])
        resposta = self.client.post(url, dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["form"].errors)
        self.assertEqual(Alocacao.objects.count(), 2)

    def test_consulta_nao_grava_mesmo_com_permissao_extra_acidental(self):
        self.consulta.user_permissions.add(Permission.objects.get(
            content_type__app_label="planejamento", codename="change_alocacao"))
        self.entrar(self.consulta)
        resposta = self.client.post(reverse("admin:planejamento_alocacao_change", args=[self.alocacao.pk]),
                                   self.dados_alocacao(observacao="Indevida"))
        self.assertEqual(resposta.status_code, 403)
        registro = Alocacao.objects.get(pk=self.alocacao.pk)
        registro.observacao = "Indevida"
        with self.assertRaises(PermissionDenied):
            registro.save(ator=self.consulta)

    def test_perfis_operacionais_nao_gerenciam_usuarios_grupos_ou_vinculos(self):
        for ator in (self.lider, self.coordenador, self.consulta, self.administrador):
            ator.user_permissions.add(*Permission.objects.filter(
                content_type__app_label="auth", codename__in=["add_user", "change_user", "change_group"]))
            self.entrar(ator)
            for rota in ("admin:auth_user_add", "admin:organizacao_usuariosetor_add"):
                self.assertEqual(self.client.post(reverse(rota), {
                    "is_superuser": "on", "is_staff": "on", "usuario": ator.pk,
                    "setor": self.reservado.pk,
                }).status_code, 403)
            self.assertEqual(self.client.post(reverse("admin:auth_user_change", args=[ator.pk]),
                {"is_superuser": "on", "groups": [Group.objects.get(name="Administrador").pk]}).status_code, 403)
        self.lider.refresh_from_db()
        self.assertFalse(self.lider.is_superuser)
        self.assertFalse(self.lider.groups.filter(name="Administrador").exists())

    def test_coordenador_gerencia_trabalhador_somente_nos_setores_permitidos(self):
        self.entrar(self.coordenador)
        dados = {"nome": "Nova pessoa", "setor_principal": self.setor.pk,
                 "funcao_principal": self.funcao.pk, "ativo": "on"}
        self.assertEqual(self.client.post(reverse("admin:organizacao_trabalhador_add"), dados).status_code, 302)
        dados["setor_principal"] = self.reservado.pk
        resposta = self.client.post(reverse("admin:organizacao_trabalhador_change", args=[self.trabalhador.pk]), dados)
        self.assertEqual(resposta.status_code, 200)
        self.trabalhador.refresh_from_db()
        self.assertEqual(self.trabalhador.setor_principal_id, self.setor.pk)

    def test_historico_de_setor_anterior_nao_vaza_no_inline(self):
        tarefa = self.outra_tarefa
        tarefa.setor = self.setor
        tarefa.save(ator=self.superusuario)
        self.entrar()
        resposta = self.client.get(reverse("admin:planejamento_tarefa_change", args=[tarefa.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Setor reservado")
        inline = resposta.context["inline_admin_formsets"][0]
        self.assertEqual(inline.formset.queryset.count(), 1)

    def test_consulta_semanal_e_servico_preservam_escopo_completo(self):
        self.entrar(self.consulta)
        resposta = self.client.get(reverse("planejamento:quadro_semanal"), {"semana": "2026-11-02"})
        self.assertContains(resposta, "Atividade permitida")
        self.assertNotContains(resposta, "Atividade reservada")
        consulta = consultar_alocacoes(ator=self.consulta, inicio=date(2026, 11, 2), fim=date(2026, 11, 8))
        self.assertEqual(list(consulta), [self.alocacao])

    def test_exclusao_em_lote_nao_remove_registro_de_outro_setor(self):
        self.entrar()
        resposta = self.client.post(reverse("admin:planejamento_alocacao_changelist"), {
            "action": "delete_selected", "_selected_action": [self.alocacao.pk, self.outra_alocacao.pk],
            "post": "yes",
        })
        self.assertIn(resposta.status_code, (200, 302))
        self.assertTrue(Alocacao.objects.filter(pk=self.outra_alocacao.pk).exists())

    def test_csrf_sem_token_e_negado(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.lider)
        self.assertEqual(cliente.post(reverse("admin:planejamento_alocacao_add"),
                                     self.dados_alocacao()).status_code, 403)
