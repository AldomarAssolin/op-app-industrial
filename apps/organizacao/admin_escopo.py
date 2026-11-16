from django.core.exceptions import PermissionDenied

from .autorizacao import exigir_escopo_objeto, exigir_operacao, filtrar_escopo


class EscopoAdminMixin:
    def get_queryset(self, request):
        return filtrar_escopo(request.user, super().get_queryset(request))

    def _pode(self, request, operacao, obj=None):
        try:
            exigir_operacao(request.user, f"{self.model._meta.app_label}.{operacao}_{self.model._meta.model_name}")
            if obj is not None:
                exigir_escopo_objeto(request.user, obj)
        except PermissionDenied:
            return False
        return True

    def has_view_permission(self, request, obj=None):
        return self._pode(request, "view", obj) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self._pode(request, "add") and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self._pode(request, "change", obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._pode(request, "delete", obj) and super().has_delete_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        modelo = db_field.remote_field.model
        if modelo._meta.label_lower in {
            "organizacao.setor", "organizacao.trabalhador", "planejamento.tarefa",
        }:
            kwargs["queryset"] = filtrar_escopo(request.user, modelo._default_manager.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        operacao = "change" if change else "add"
        exigir_operacao(request.user, f"{obj._meta.app_label}.{operacao}_{obj._meta.model_name}")
        exigir_escopo_objeto(request.user, obj)
        if change:
            anterior = type(obj).objects.get(pk=obj.pk)
            exigir_escopo_objeto(request.user, anterior)
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        exigir_operacao(request.user, f"{obj._meta.app_label}.delete_{obj._meta.model_name}")
        exigir_escopo_objeto(request.user, obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        exigir_operacao(request.user, f"{self.model._meta.app_label}.delete_{self.model._meta.model_name}")
        permitidos = self.get_queryset(request).filter(pk__in=queryset.values("pk"))
        if permitidos.count() != queryset.count():
            raise PermissionDenied("Seleção fora do escopo autorizado.")
        super().delete_queryset(request, permitidos)
