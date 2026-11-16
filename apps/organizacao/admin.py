from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group

from .admin_escopo import EscopoAdminMixin
from .autorizacao import administrador

from .models import Funcao, Setor, Trabalhador, UsuarioSetor


class CadastroAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "ativo")
    list_display_links = ("id", "nome")
    search_fields = ("nome", "descricao")
    list_filter = ("ativo",)
    ordering = ("nome", "pk")


@admin.register(Setor)
class SetorAdmin(EscopoAdminMixin, CadastroAdmin):
    def has_add_permission(self, request):
        return administrador(request.user) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return administrador(request.user) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return administrador(request.user) and super().has_delete_permission(request, obj)


@admin.register(Funcao)
class FuncaoAdmin(SetorAdmin):
    pass


@admin.register(Trabalhador)
class TrabalhadorAdmin(EscopoAdminMixin, CadastroAdmin):
    list_filter = ("ativo", ("setor_principal", admin.RelatedOnlyFieldListFilter),
                   ("funcao_principal", admin.RelatedOnlyFieldListFilter))
    list_display = ("id", "nome", "setor_principal", "funcao_principal", "ativo")
    search_fields = ("nome", "setor_principal__nome", "funcao_principal__nome")
    list_select_related = ("setor_principal", "funcao_principal")


@admin.register(UsuarioSetor)
class UsuarioSetorAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission

    def has_add_permission(self, request):
        return request.user.is_superuser

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.none()

    list_display = ("usuario", "setor")
    list_filter = ("setor",)
    search_fields = ("usuario__username", "setor__nome")
    list_select_related = ("usuario", "setor")


class SomenteSuperusuarioMixin:
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission

    def has_add_permission(self, request):
        return request.user.is_superuser

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.none()


admin.site.unregister(get_user_model())
admin.site.unregister(Group)


@admin.register(get_user_model())
class UsuarioSeguroAdmin(SomenteSuperusuarioMixin, UserAdmin):
    pass


@admin.register(Group)
class GrupoSeguroAdmin(SomenteSuperusuarioMixin, GroupAdmin):
    pass
