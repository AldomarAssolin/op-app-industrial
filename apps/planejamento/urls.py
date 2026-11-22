from django.urls import path

from . import views
from .views_fluxo import planejar
from .views_correcao import corrigir_alocacao, remover_alocacao

app_name = "planejamento"
urlpatterns = [path("semanal/", views.quadro_semanal, name="quadro_semanal"),
    path("planejar/", planejar, name="planejar"),
    path("alocacoes/<int:pk>/editar/", corrigir_alocacao, name="corrigir_alocacao"),
    path("alocacoes/<int:pk>/remover/", remover_alocacao, name="remover_alocacao")]
