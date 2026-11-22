from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.html import format_html_join
from django.urls import path, reverse

from .orientacao import proximo_passo
from .forms import AlocacaoMultidiaForm, TarefaTurnosForm, TrabalhadorTurnoChoiceField
from .models import Alocacao, HistoricoTarefa, Tarefa, exigir_permissao, TurnoTarefa, ObservacaoTarefaTurno
from .services import alocar_dias
from apps.organizacao.admin_escopo import EscopoAdminMixin, GravacaoValidadaAdminMixin
from apps.organizacao.autorizacao import (filtrar_escopo, exigir_escopo_objeto, administrador,
    coordenador_no_setor, setores_do_usuario, turnos_permitidos, travar_autorizacao)


class HistoricoTarefaInline(EscopoAdminMixin, admin.TabularInline):
    model = HistoricoTarefa
    extra = 0
    fields = ("registrado_em", "registrado_por", "status", "inicio_previsto", "fim_previsto", "setor")
    readonly_fields = fields
    can_delete = False

    def get_fields(self, request, obj=None):
        campos = super().get_fields(request, obj)
        return (*campos, 'turno_operacao') if settings.OP_APP_TURNOS_ENABLED else campos

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TurnoTarefaInline(admin.TabularInline):
    model = TurnoTarefa
    fields = ('turno', 'ativo')
    extra = 0
    can_delete = False

    def _coord(self, request, obj):
        return settings.OP_APP_TURNOS_ENABLED and (administrador(request.user) or (
            obj is not None and coordenador_no_setor(request.user, obj.setor_id)))

    def has_add_permission(self, request, obj=None):
        return self._coord(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._coord(request, obj)

    def has_view_permission(self, request, obj=None):
        return self._coord(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return filtrar_escopo(request.user, super().get_queryset(request))


@admin.register(Tarefa)
class TarefaAdmin(GravacaoValidadaAdminMixin, EscopoAdminMixin, admin.ModelAdmin):
    list_display = ("id", "titulo", "setor", "inicio_previsto", "fim_previsto", "status")
    list_display_links = ("id", "titulo")
    list_filter = (("setor", admin.RelatedOnlyFieldListFilter), "status", "inicio_previsto", "fim_previsto")
    search_fields = ("titulo", "descricao", "observacoes", "setor__nome")
    list_select_related = ("setor",)
    inlines = (HistoricoTarefaInline,)
    fields = ("titulo", "descricao", "setor", ("inicio_previsto", "fim_previsto"),
              "status", "observacoes")

    def _restrito(self, request, obj):
        if not settings.OP_APP_TURNOS_ENABLED or administrador(request.user):
            return False
        if obj is None:
            from apps.organizacao.autorizacao import pode_manter_equipe
            return not pode_manter_equipe(request.user)
        return not coordenador_no_setor(request.user, obj.setor_id)

    def get_fields(self, request, obj=None):
        campos = super().get_fields(request, obj)
        if not settings.OP_APP_TURNOS_ENABLED:
            return campos
        return (*campos, 'turno_operacao', 'observacao_turno', 'historico_observacoes')

    def get_readonly_fields(self, request, obj=None):
        if not settings.OP_APP_TURNOS_ENABLED:
            return super().get_readonly_fields(request, obj)
        gerais = ('titulo', 'descricao', 'setor', 'inicio_previsto', 'fim_previsto', 'observacoes') if obj and self._restrito(request, obj) else ()
        if obj is None and self._restrito(request, obj):
            gerais = ('observacoes',)
        return (*gerais, 'historico_observacoes')

    def get_inlines(self, request, obj):
        if settings.OP_APP_TURNOS_ENABLED and obj and not self._restrito(request, obj):
            return (HistoricoTarefaInline, TurnoTarefaInline)
        return (HistoricoTarefaInline,)

    def get_form(self, request, obj=None, **kwargs):
        if settings.OP_APP_TURNOS_ENABLED:
            kwargs['form'] = TarefaTurnosForm
        base = super().get_form(request, obj, **kwargs)
        if not settings.OP_APP_TURNOS_ENABLED:
            return base
        usuario = request.user
        restrito = self._restrito(request, obj)
        setores = setores_do_usuario(usuario)
        codigos = set()
        for setor in setores:
            codigos |= turnos_permitidos(usuario, setor.pk)
        from apps.organizacao.models import Turno
        class FormDaOperacao(base):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                self.fields['turno_operacao'].queryset = Turno.objects.filter(pk__in=codigos, ativo=True)
                self.fields['turno_operacao'].required = bool(obj is None or restrito)
                if obj is not None and restrito and 'status' in self.fields:
                    proximos = {Tarefa.Status.PENDENTE: Tarefa.Status.EM_ANDAMENTO,
                                Tarefa.Status.EM_ANDAMENTO: Tarefa.Status.CONCLUIDA}
                    permitidos = {obj.status, proximos.get(obj.status)}
                    self.fields['status'].choices = [(v, r) for v, r in Tarefa.Status.choices if v in permitidos]
        return FormDaOperacao

    @admin.display(description='Observações dos turnos autorizados')
    def historico_observacoes(self, obj):
        if not obj.pk:
            return 'As observações serão registradas após a criação.'
        # O queryset é preparado por change_view, sem guardar usuário no ModelAdmin compartilhado.
        registros = getattr(obj, '_observacoes_autorizadas', [])
        return format_html_join('', '<p>{} · {} · {}</p>', ((r.turno_id, r.registrado_em, r.texto) for r in registros)) or 'Nenhuma observação disponível.'

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field)
        if obj is not None and settings.OP_APP_TURNOS_ENABLED:
            obj._observacoes_autorizadas = list(filtrar_escopo(request.user, ObservacaoTarefaTurno.objects.filter(tarefa=obj)))
        return obj

    def save_model(self, request, obj, form, change):
        turno = form.cleaned_data.get('turno_operacao') if settings.OP_APP_TURNOS_ENABLED else None
        obj.save(ator=request.user, turno_operacao=turno)
        if settings.OP_APP_TURNOS_ENABLED and form.cleaned_data.get('observacao_turno'):
            if turno is None:
                raise ValidationError('Selecione o turno da observação.')
            ObservacaoTarefaTurno(tarefa=obj, turno=turno, texto=form.cleaned_data['observacao_turno']).save(ator=request.user)

    def save_formset(self, request, form, formset, change):
        if settings.OP_APP_TURNOS_ENABLED and formset.model == TurnoTarefa:
            for instancia in formset.save(commit=False):
                instancia.save(ator=request.user)
            return
        return super().save_formset(request, form, formset, change)

    def has_add_permission(self, request):
        return super().has_add_permission(request) and (not settings.OP_APP_TURNOS_ENABLED or setores_do_usuario(request.user).exists())

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
    readonly_fields = ("criado_por", "alterado_por", "criado_em", "alterado_em", "atividades_do_planejamento")
    change_list_template = "admin/planejamento/alocacao/change_list.html"

    @admin.display(description='Atividades da tarefa (conjunto)')
    def atividades_do_planejamento(self, obj):
        if not obj or not obj.pk:
            return 'A atividade de referência é escolhida abaixo. Para planejar várias, use Planejar.'
        return obj.atividades_descricao + '. Para alterar o conjunto, use a correção no quadro semanal.'

    class Media:
        js = ('planejamento/js/turno_trabalhador.js',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'funcao_desempenhada':
            kwargs['label'] = 'Atividade de referência da tarefa'
            kwargs['help_text'] = 'Cadastro Funções: trabalhos necessários à tarefa, não competências. Para editar várias atividades, use o quadro semanal.'
        if db_field.name == 'trabalhador' and settings.OP_APP_TURNOS_ENABLED:
            kwargs['form_class'] = TrabalhadorTurnoChoiceField
        if db_field.name == 'turno' and settings.OP_APP_TURNOS_ENABLED:
            from apps.organizacao.models import Turno
            permitidos = set()
            for setor in setores_do_usuario(request.user):
                permitidos |= turnos_permitidos(request.user, setor.pk)
            kwargs.update(queryset=Turno.objects.filter(ativo=True, pk__in=permitidos), required=True)
        campo = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'trabalhador' and settings.OP_APP_TURNOS_ENABLED:
            campo.widget.attrs['data-turno-referencia'] = 'data'
            campo.help_text = 'Turno habitual na data da alocação; sem data, considera hoje.'
        return campo

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
        form = AlocacaoMultidiaForm(request.POST or None, ator=request.user,
                                   initial={'inicio': request.GET.get('inicio', '')})
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
        ator = travar_autorizacao(request.user)
        exigir_permissao(ator, 'delete')
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
