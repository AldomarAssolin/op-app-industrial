from django.urls import path

from . import views

app_name = "planejamento"
urlpatterns = [path("semanal/", views.quadro_semanal, name="quadro_semanal")]
