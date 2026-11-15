from django.contrib import admin

from .models import HistoricoTarefa, Tarefa


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
