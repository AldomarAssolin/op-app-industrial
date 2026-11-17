import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
timeout = 60
accesslog = "-"
errorlog = "-"
# Não registrar query strings: podem conter parâmetros sensíveis.
access_log_format = '%(h)s %(m)s %(U)s %(s)s %(L)s'
# Django controla a confiança no proxy por opt-in; não aceitar esquemas por outra via.
secure_scheme_headers = {}
forwarded_allow_ips = ""
