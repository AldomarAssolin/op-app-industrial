from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .forms import AlocacaoMultidiaForm
from .models import Alocacao, HistoricoTarefa, Tarefa, exigir_permissao
from .services import alocar_dias


class HistoricoTarefaInline(admin.TabularInline):
    model = HistoricoTarefa
    extra = 0
    fields = ("registrado_em", "status", "inicio_previsto", "fim_previsto", "setor")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = ("id", "titulo", "setor", "inicio_previsto", "fim_previsto", "status")
    list_display_links = ("id", "titulo")
    list_filter = ("setor", "status", "inicio_previsto", "fim_previsto")
    search_fields = ("titulo", "descricao", "observacoes", "setor__nome")
    list_select_related = ("setor",)
    inlines = (HistoricoTarefaInline,)
    fields = ("titulo", "descricao", "setor", ("inicio_previsto", "fim_previsto"),
              "status", "observacoes")

    def has_delete_permission(self, request, obj=None):
        # Use cancelamento; toda tarefa criada já possui histórico protegido.
        return False


@admin.register(Alocacao)
class AlocacaoAdmin(admin.ModelAdmin):
    list_display = ("id", "data", "trabalhador", "tarefa", "funcao_desempenhada", "alterado_por")
    list_filter = ("data", "tarefa__setor", "funcao_desempenhada")
    search_fields = ("trabalhador__nome", "tarefa__titulo", "observacao")
    list_select_related = ("trabalhador", "tarefa", "funcao_desempenhada", "alterado_por")
    readonly_fields = ("criado_por", "alterado_por", "criado_em", "alterado_em")
    change_list_template = "admin/planejamento/alocacao/change_list.html"

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
        form = AlocacaoMultidiaForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            dados = form.cleaned_data
            try:
                registros = alocar_dias(
                    ator=request.user, trabalhador=dados["trabalhador"], tarefa=dados["tarefa"],
                    datas=dados["datas"], funcao_desempenhada=dados["funcao_desempenhada"],
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
        })

    def save_model(self, request, obj, form, change):
        obj.save(ator=request.user)

    def delete_model(self, request, obj):
        obj.delete(ator=request.user)

    def delete_queryset(self, request, queryset):
        exigir_permissao(request.user, "delete")
        queryset.delete()
