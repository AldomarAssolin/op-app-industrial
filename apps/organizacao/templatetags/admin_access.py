"""Links de consulta respeitam a permissão do destino, inclusive no histórico."""
from django import template
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db import models
from django.utils.html import conditional_escape

register = template.Library()


@register.simple_tag(takes_context=True)
def readonly_com_acesso(context, field):
    try:
        nome = field.field['field']
        metadata = field.form.instance._meta.get_field(nome)
        if isinstance(metadata, (models.ForeignKey, models.OneToOneField)):
            relacionado = getattr(field.form.instance, nome)
            destino = field.model_admin.admin_site._registry.get(metadata.remote_field.model)
            request = context.get('request')
            if relacionado is not None and destino is not None and (
                    request is None or not destino.has_view_or_change_permission(request, relacionado)):
                return conditional_escape(str(relacionado))
    except (FieldDoesNotExist, ObjectDoesNotExist):
        pass
    return field.contents()
