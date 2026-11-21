from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group

from .admin_escopo import EscopoAdminMixin
from .autorizacao import administrador, LIDER, COORDENADOR

from .models import Funcao, Setor, Trabalhador, UsuarioSetor, Turno
from .autorizacao import exigir_escopo_objeto
from .forms_turnos import TrocaTurnoForm
from .turnos import exigir_coordenador, revisar_troca_turno, confirmar_troca_turno


class CadastroAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "ativo")
    list_display_links = ("id", "nome")
    search_fields = ("nome", "descricao")
    list_filter = ("ativo",)
    ordering = ("nome", "pk")


@admin.register(Setor)
class SetorAdmin(EscopoAdminMixin, CadastroAdmin):
    def _lider_restrito(self, request):
        return (not administrador(request.user)
                and request.user.groups.filter(name=LIDER).exists()
                and not request.user.groups.filter(name=COORDENADOR).exists())

    def has_module_permission(self, request):
        return not self._lider_restrito(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return not self._lider_restrito(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return administrador(request.user) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return administrador(request.user) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return administrador(request.user) and super().has_delete_permission(request, obj)


@admin.register(Funcao)
class FuncaoAdmin(SetorAdmin):
    # Funções continuam disponíveis para consulta do Líder; só Setores é ocultado.
    def _lider_restrito(self, request):
        return False


@admin.register(Trabalhador)
class TrabalhadorAdmin(EscopoAdminMixin, CadastroAdmin):
    def get_list_display(self, request):
        campos = super().get_list_display(request)
        if not settings.OP_APP_TURNOS_ENABLED:
            return campos
        return (*campos, 'turno_atual', 'troca_turno') if request.user.groups.filter(name=COORDENADOR).exists() else (*campos, 'turno_atual')

    @admin.display(description='Turno habitual hoje')
    def turno_atual(self, obj):
        return obj.turno_habitual or 'Turno não informado'

    @admin.display(description='Turno')
    def troca_turno(self, obj):
        return format_html('<a href="{}">Revisar troca de turno</a>', reverse('admin:organizacao_trabalhador_turno', args=[obj.pk]))

    def get_urls(self):
        return [path('<int:object_id>/turno/', self.admin_site.admin_view(self.trocar_turno),
                     name='organizacao_trabalhador_turno')] + super().get_urls()

    def trocar_turno(self, request, object_id):
        exigir_coordenador(request.user)
        trabalhador = get_object_or_404(self.get_queryset(request), pk=object_id)
        exigir_escopo_objeto(request.user, trabalhador)
        form = TrocaTurnoForm(request.POST or None)
        revisao = None
        if request.method == 'POST':
            try:
                if request.POST.get('confirmacao'):
                    confirmar_troca_turno(ator=request.user, confirmacao=request.POST['confirmacao'], trabalhador_id=trabalhador.pk)
                    self.message_user(request, 'Turno atualizado por vigência; alocações futuras conferidas e transferidas.', messages.SUCCESS)
                    return redirect('admin:organizacao_trabalhador_changelist')
                if form.is_valid():
                    revisao = revisar_troca_turno(ator=request.user, trabalhador_id=trabalhador.pk,
                        turno_id=form.cleaned_data['turno'].pk, vigencia=form.cleaned_data['vigencia'],
                        classificar_legado=form.cleaned_data['classificar_legado'])
            except ValidationError as erro:
                form.add_error(None, erro)
        return TemplateResponse(request, 'admin/organizacao/trabalhador/troca_turno.html', {
            **self.admin_site.each_context(request), 'opts': self.model._meta,
            'title': 'Revisar troca de turno', 'trabalhador': trabalhador, 'form': form, 'revisao': revisao})

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


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'inicio_referencia', 'fim_referencia', 'horario_aproximado', 'ativo')
    readonly_fields = ('codigo',)

    def has_module_permission(self, request):
        return settings.OP_APP_TURNOS_ENABLED and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
