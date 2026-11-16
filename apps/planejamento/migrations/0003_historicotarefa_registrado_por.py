from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("planejamento", "0002_alocacao"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="historicotarefa",
            name="registrado_por",
            field=models.ForeignKey(
                blank=True, editable=False, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="historico_tarefas", to=settings.AUTH_USER_MODEL,
                verbose_name="registrado por",
            ),
        ),
    ]
