from django.contrib import admin

from .models import Funcao, Setor, Trabalhador, UsuarioSetor


class CadastroAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "ativo")
    list_display_links = ("id", "nome")
    search_fields = ("nome", "descricao")
    list_filter = ("ativo",)
    ordering = ("nome", "pk")


@admin.register(Setor)
class SetorAdmin(CadastroAdmin):
    pass


@admin.register(Funcao)
class FuncaoAdmin(CadastroAdmin):
    pass


@admin.register(Trabalhador)
class TrabalhadorAdmin(CadastroAdmin):
    list_display = ("id", "nome", "setor_principal", "funcao_principal", "ativo")
    search_fields = ("nome", "setor_principal__nome", "funcao_principal__nome")
    list_filter = ("ativo", "setor_principal", "funcao_principal")
    list_select_related = ("setor_principal", "funcao_principal")


@admin.register(UsuarioSetor)
class UsuarioSetorAdmin(admin.ModelAdmin):
    list_display = ("usuario", "setor")
    list_filter = ("setor",)
    search_fields = ("usuario__username", "setor__nome")
    list_select_related = ("usuario", "setor")
