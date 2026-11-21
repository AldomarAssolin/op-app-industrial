from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .orientacao import proximo_passo
from .forms import AlocacaoMultidiaForm
from .models import Alocacao, HistoricoTarefa, Tarefa, exigir_permissao
from .services import alocar_dias
from apps.organizacao.admin_escopo import EscopoAdminMixin
from apps.organizacao.autorizacao import filtrar_escopo, exigir_escopo_objeto


class HistoricoTarefaInline(EscopoAdminMixin, admin.TabularInline):
    model = HistoricoTarefa
    extra = 0
    fields = ("registrado_em", "registrado_por", "status", "inicio_previsto", "fim_previsto", "setor")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Tarefa)
class TarefaAdmin(EscopoAdminMixin, admin.ModelAdmin):
    list_display = ("id", "titulo", "setor", "inicio_previsto", "fim_previsto", "status")
    list_display_links = ("id", "titulo")
    list_filter = (("setor", admin.RelatedOnlyFieldListFilter), "status", "inicio_previsto", "fim_previsto")
    search_fields = ("titulo", "descricao", "observacoes", "setor__nome")
    list_select_related = ("setor",)
    inlines = (HistoricoTarefaInline,)
    fields = ("titulo", "descricao", "setor", ("inicio_previsto", "fim_previsto"),
              "status", "observacoes")

    def save_model(self, request, obj, form, change):
        obj.save(ator=request.user)

    def has_delete_permission(self, request, obj=None):
        # Use cancelamento; toda tarefa criada já possui histórico protegido.
        return False


@admin.register(Alocacao)
class AlocacaoAdmin(EscopoAdminMixin, admin.ModelAdmin):
    list_display = ("id", "data", "trabalhador", "tarefa", "funcao_desempenhada", "alterado_por")
    list_filter = ("data", ("tarefa__setor", admin.RelatedOnlyFieldListFilter),
                   ("funcao_desempenhada", admin.RelatedOnlyFieldListFilter))
    search_fields = ("trabalhador__nome", "tarefa__titulo", "observacao")
    list_select_related = ("trabalhador", "tarefa", "funcao_desempenhada", "alterado_por")
    readonly_fields = ("criado_por", "alterado_por", "criado_em", "alterado_em")
    change_list_template = "admin/planejamento/alocacao/change_list.html"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'turno' and settings.OP_APP_TURNOS_ENABLED:
            from apps.organizacao.models import Turno
            kwargs.update(queryset=Turno.objects.filter(ativo=True), required=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_exclude(self, request, obj=None):
        return ('turno',) if not settings.OP_APP_TURNOS_ENABLED else ()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as erro:
            if request.method != "POST":
                raise
            # O atomic do Admin já foi revertido. Reapresenta o POST como
            # inválido, sem repetir save_model nem perder os dados digitados.
            request._alocacao_erro_gravacao = " ".join(erro.messages)
            try:
                return super().changeform_view(request, object_id, form_url, extra_context)
            finally:
                del request._alocacao_erro_gravacao

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)
        erro = getattr(request, "_alocacao_erro_gravacao", None)
        if erro is None:
            return form_class

        class FormComConflito(form_class):
            def clean(self):
                dados = super().clean()
                self.add_error(None, erro)
                return dados

        return FormComConflito

    def get_urls(self):
        return [path("varios-dias/", self.admin_site.admin_view(self.alocar_varios_dias),
                     name="planejamento_alocacao_varios_dias")] + super().get_urls()

    def alocar_varios_dias(self, request):
        exigir_permissao(request.user, "add")
        form = AlocacaoMultidiaForm(request.POST or None, ator=request.user)
        if request.method == "POST" and form.is_valid():
            dados = form.cleaned_data
            try:
                registros = alocar_dias(
                    ator=request.user, trabalhador=dados["trabalhador"], tarefa=dados["tarefa"],
                    datas=dados["datas"], funcao_desempenhada=dados["funcao_desempenhada"],
                    turno=dados.get("turno"),
                    observacao=dados["observacao"],
                )
            except ValidationError as erro:
                form.add_error(None, " ".join(erro.messages))
            else:
                for registro in registros:
                    self.log_addition(request, registro, "Alocação de vários dias")
                self.message_user(request, f"{len(registros)} alocações criadas.", messages.SUCCESS)
                return HttpResponseRedirect(reverse("admin:planejamento_alocacao_changelist"))
        return TemplateResponse(request, "admin/planejamento/alocacao/varios_dias.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "title": "Alocar trabalhador em vários dias", "form": form,
            "orientacao": proximo_passo(request.user),
        })

    def save_model(self, request, obj, form, change):
        obj.save(ator=request.user)

    def delete_model(self, request, obj):
        obj.delete(ator=request.user)

    def get_actions(self, request):
        acoes = super().get_actions(request)
        if 'delete_selected' in acoes:
            original, nome, descricao = acoes['delete_selected']
            def excluir_com_verificacao(modeladmin, req, queryset):
                try:
                    with transaction.atomic():
                        return original(modeladmin, req, queryset)
                except ValidationError as erro:
                    modeladmin.message_user(req, ' '.join(erro.messages), messages.ERROR)
                    return HttpResponseRedirect(reverse('admin:planejamento_alocacao_changelist'))
            acoes['delete_selected'] = (excluir_com_verificacao, nome, descricao)
        return acoes

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        from apps.organizacao.models import Trabalhador
        exigir_permissao(request.user, 'delete')
        registros = list(queryset.order_by('pk'))
        tarefas = {obj.tarefa_id for obj in registros}
        trabalhadores = {obj.trabalhador_id for obj in registros}
        # Ordem global do lote: todas as tarefas, todos os trabalhadores, alocações.
        list(Tarefa.objects.select_for_update().filter(pk__in=tarefas).order_by('pk'))
        list(Trabalhador.objects.select_for_update().filter(pk__in=trabalhadores).order_by('pk'))
        atuais = list(self.get_queryset(request).select_for_update().filter(
            pk__in=[obj.pk for obj in registros]).order_by('pk'))
        def estado(obj):
            return (obj.pk, obj.tarefa_id, obj.trabalhador_id, obj.data, obj.turno_id, obj.alterado_em)
        if [estado(obj) for obj in registros] != [estado(obj) for obj in atuais]:
            raise ValidationError('A seleção mudou ou deixou de estar autorizada. Recarregue antes de remover.')
        for obj in atuais:
            obj.delete(ator=request.user)
