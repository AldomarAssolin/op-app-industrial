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

from .admin_escopo import EscopoAdminMixin, GravacaoValidadaAdminMixin
from .autorizacao import administrador, LIDER, COORDENADOR

from .models import (Funcao, Setor, Trabalhador, UsuarioSetor, Turno,
    ResponsavelSetor, VinculoLiderTurno, HistoricoAcessoTurno, MudancaTurno)
from .autorizacao import exigir_escopo_objeto, coordenador_no_setor, filtrar_escopo, pode_manter_equipe
from .forms_turnos import TrocaTurnoForm, TrabalhadorCadastroForm
from .turnos import exigir_coordenador, revisar_troca_turno, confirmar_troca_turno, criar_trabalhador_com_turno


class CadastroAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "ativo")
    list_display_links = ("id", "nome")
    search_fields = ("nome", "descricao")
    list_filter = ("ativo",)
    ordering = ("nome", "pk")


@admin.register(Setor)
class SetorAdmin(EscopoAdminMixin, CadastroAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if settings.OP_APP_TURNOS_ENABLED and self.model is Setor and not administrador(request.user):
            return qs.filter(responsavel_operacional__usuario=request.user)
        return qs

    def _lider_restrito(self, request):
        return (not administrador(request.user)
                and request.user.groups.filter(name=LIDER).exists()
                and not request.user.groups.filter(name=COORDENADOR).exists())

    def has_module_permission(self, request):
        if settings.OP_APP_TURNOS_ENABLED and self.model is Setor and not administrador(request.user):
            return request.user.groups.filter(name=COORDENADOR).exists() and ResponsavelSetor.objects.filter(usuario=request.user).exists()
        return not self._lider_restrito(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        if settings.OP_APP_TURNOS_ENABLED and self.model is Setor and not administrador(request.user):
            if obj is not None and not coordenador_no_setor(request.user, obj.pk):
                return False
            if obj is None and not self.has_module_permission(request):
                return False
        return not self._lider_restrito(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return administrador(request.user) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return administrador(request.user) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return administrador(request.user) and super().has_delete_permission(request, obj)


@admin.register(Funcao)
class FuncaoAdmin(SetorAdmin):
    change_form_template = 'admin/organizacao/funcao/change_form.html'
    change_list_template = 'admin/organizacao/funcao/change_list.html'

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'nome':
            kwargs['help_text'] = 'Nome da atividade necessária à tarefa. Exemplos: Montagem, Soldagem, Usinagem.'
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    # Funções continuam disponíveis para consulta do Líder; só Setores é ocultado.
    def _lider_restrito(self, request):
        return False


class TurnoHabitualFilter(admin.SimpleListFilter):
    title = 'turno habitual hoje'
    parameter_name = 'turno_habitual'

    def lookups(self, request, model_admin):
        return [('T1', 'T1'), ('T2', 'T2'), ('T3', 'T3'), ('nao_informado', 'Turno não informado')]

    def queryset(self, request, queryset):
        if self.value() == 'nao_informado':
            return queryset.filter(_turno_vigente__isnull=True)
        if self.value() in ('T1', 'T2', 'T3'):
            return queryset.filter(_turno_vigente=self.value())
        return queryset


class HistoricoHabitualInline(admin.TabularInline):
    model = MudancaTurno
    extra = 0
    fields = ('vigencia', 'turno_anterior', 'turno_novo', 'registrado_por', 'registrado_em', 'alocacoes_transferidas')
    readonly_fields = fields
    can_delete = False

    def has_view_permission(self, request, obj=None):
        return bool(settings.OP_APP_TURNOS_ENABLED and obj is not None and (
            administrador(request.user) or coordenador_no_setor(request.user, obj.setor_principal_id)))

    def get_queryset(self, request):
        return filtrar_escopo(request.user, super().get_queryset(request))

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Trabalhador)
class TrabalhadorAdmin(GravacaoValidadaAdminMixin, EscopoAdminMixin, CadastroAdmin):
    change_form_template = 'admin/organizacao/trabalhador/change_form.html'
    def change_view(self, request, object_id, form_url='', extra_context=None):
        contexto = dict(extra_context or {})
        if settings.OP_APP_TURNOS_ENABLED:
            obj = self.get_object(request, object_id)
            if obj is not None and (request.user.is_superuser or coordenador_no_setor(request.user, obj.setor_principal_id)):
                contexto['form_troca_turno'] = TrocaTurnoForm()
                contexto['url_troca_turno'] = reverse('admin:organizacao_trabalhador_turno', args=[obj.pk])
        return super().change_view(request, object_id, form_url, contexto)

    def get_form(self, request, obj=None, **kwargs):
        if settings.OP_APP_TURNOS_ENABLED and obj is None:
            kwargs['form'] = TrabalhadorCadastroForm
        return super().get_form(request, obj, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        campos = super().get_readonly_fields(request, obj)
        if settings.OP_APP_TURNOS_ENABLED and obj is not None:
            pode_trocar = request.user.is_superuser or coordenador_no_setor(request.user, obj.setor_principal_id)
            return (*campos, 'turno_atual', *(('gerenciar_turno',) if pode_trocar else ()))
        return campos

    @admin.display(description='Atualização de turno')
    def gerenciar_turno(self, obj):
        return self.troca_turno(obj)

    def get_inlines(self, request, obj):
        if settings.OP_APP_TURNOS_ENABLED and obj and (
                administrador(request.user) or coordenador_no_setor(request.user, obj.setor_principal_id)):
            return (HistoricoHabitualInline,)
        return ()

    def get_list_filter(self, request):
        campos = super().get_list_filter(request)
        if settings.OP_APP_TURNOS_ENABLED and pode_manter_equipe(request.user):
            return (*campos, TurnoHabitualFilter)
        return campos

    def save_model(self, request, obj, form, change):
        if settings.OP_APP_TURNOS_ENABLED and not change:
            criar_trabalhador_com_turno(ator=request.user, trabalhador=obj,
                                       turno=form.cleaned_data.get('turno_inicial'))
            return
        return super().save_model(request, obj, form, change)

    def get_list_display(self, request):
        campos = super().get_list_display(request)
        if not settings.OP_APP_TURNOS_ENABLED:
            return campos
        @admin.display(description='Troca de turno')
        def troca_autorizada(obj):
            if request.user.is_superuser or coordenador_no_setor(request.user, obj.setor_principal_id):
                return self.troca_turno(obj)
            return 'Procure o Coordenador do setor'
        return (*campos, 'turno_atual', troca_autorizada) if pode_manter_equipe(request.user) else (*campos, 'turno_atual')

    @admin.display(description='Turno habitual hoje')
    def turno_atual(self, obj):
        return obj.turno_habitual or 'Turno não informado'

    @admin.display(description='Turno')
    def troca_turno(self, obj):
        return format_html('<a href="{}">Revisar troca de turno</a>', reverse('admin:organizacao_trabalhador_turno', args=[obj.pk]))

    def has_add_permission(self, request):
        return super().has_add_permission(request) and (not settings.OP_APP_TURNOS_ENABLED or pode_manter_equipe(request.user))

    def has_change_permission(self, request, obj=None):
        if settings.OP_APP_TURNOS_ENABLED:
            permitido = pode_manter_equipe(request.user) if obj is None else (administrador(request.user) or coordenador_no_setor(request.user, obj.setor_principal_id))
            if not permitido:
                return False
        return super().has_change_permission(request, obj)


    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'funcao_principal':
            kwargs['help_text'] = 'Referência organizacional do cadastro Funções (atividades). Não comprova competência e não limita as atividades da tarefa.'
        if settings.OP_APP_TURNOS_ENABLED and db_field.name == 'setor_principal' and not administrador(request.user):
            kwargs['queryset'] = Setor.objects.filter(responsavel_operacional__usuario=request.user)
            return admin.ModelAdmin.formfield_for_foreignkey(self, db_field, request, **kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_urls(self):
        return [path('<int:object_id>/turno/', self.admin_site.admin_view(self.trocar_turno),
                     name='organizacao_trabalhador_turno')] + super().get_urls()

    def trocar_turno(self, request, object_id):
        exigir_coordenador(request.user)
        trabalhador = get_object_or_404(self.get_queryset(request), pk=object_id)
        exigir_coordenador(request.user, trabalhador.setor_principal_id)
        exigir_escopo_objeto(request.user, trabalhador)
        form = TrocaTurnoForm(request.POST or None)
        revisao = None
        if request.method == 'POST':
            try:
                if request.POST.get('confirmacao'):
                    confirmar_troca_turno(ator=request.user, confirmacao=request.POST['confirmacao'], trabalhador_id=trabalhador.pk)
                    self.message_user(request, 'Turno atualizado por vigência; alocações futuras conferidas e transferidas.', messages.SUCCESS)
                    return redirect('admin:organizacao_trabalhador_change', trabalhador.pk)
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


@admin.register(ResponsavelSetor)
class ResponsavelSetorAdmin(GravacaoValidadaAdminMixin, admin.ModelAdmin):
    list_display = ('setor', 'usuario')

    def has_module_permission(self, request):
        return settings.OP_APP_TURNOS_ENABLED and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    has_add_permission = has_module_permission
    has_change_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return ('setor',) if obj else ()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'usuario':
            kwargs['queryset'] = get_user_model().objects.filter(is_active=True, groups__name=COORDENADOR)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.save(ator=request.user)


@admin.register(VinculoLiderTurno)
class VinculoLiderTurnoAdmin(GravacaoValidadaAdminMixin, EscopoAdminMixin, admin.ModelAdmin):
    list_display = ('usuario', 'setor', 'turno', 'ativo')
    list_select_related = ('usuario', 'setor', 'turno')
    fields = ('usuario', 'setor', 'turno', 'ativo')

    def has_module_permission(self, request):
        return settings.OP_APP_TURNOS_ENABLED and (request.user.is_superuser or (
            request.user.groups.filter(name=COORDENADOR).exists()
            and ResponsavelSetor.objects.filter(usuario=request.user).exists()))

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self.has_module_permission(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return ('usuario', 'setor', 'turno') if obj else ()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        setores = Setor.objects.all() if request.user.is_superuser else Setor.objects.filter(responsavel_operacional__usuario=request.user)
        if db_field.name == 'usuario':
            kwargs['queryset'] = get_user_model().objects.filter(is_active=True, groups__name=LIDER,
                setores_permitidos__setor__in=setores).distinct()
        elif db_field.name == 'setor':
            kwargs['queryset'] = setores
            return admin.ModelAdmin.formfield_for_foreignkey(self, db_field, request, **kwargs)
        elif db_field.name == 'turno':
            kwargs['queryset'] = Turno.objects.filter(ativo=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.save(ator=request.user)


@admin.register(HistoricoAcessoTurno)
class HistoricoAcessoTurnoAdmin(EscopoAdminMixin, admin.ModelAdmin):
    list_display = ('registrado_em', 'setor', 'tipo', 'registrado_por')
    readonly_fields = ('registrado_em', 'setor', 'tipo', 'registrado_por', 'alteracao')

    def has_module_permission(self, request):
        return settings.OP_APP_TURNOS_ENABLED and (request.user.is_superuser or request.user.groups.filter(name=COORDENADOR).exists())

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MudancaTurno)
class MudancaTurnoAdmin(EscopoAdminMixin, admin.ModelAdmin):
    list_display = ('trabalhador', 'vigencia', 'turno_anterior', 'turno_novo', 'registrado_por', 'alocacoes_transferidas')
    readonly_fields = ('trabalhador', 'vigencia', 'turno_anterior', 'turno_novo', 'registrado_por', 'registrado_em', 'alocacoes_transferidas')

    def has_module_permission(self, request):
        return settings.OP_APP_TURNOS_ENABLED and (request.user.is_superuser or request.user.groups.filter(name=COORDENADOR).exists())

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
