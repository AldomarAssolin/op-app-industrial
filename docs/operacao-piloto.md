# Operação e recuperação do piloto — issue #16

Atualizado em 20/11/2026. Política escolhida por Manex: **backup diário e retenção de 30 dias**. Horário inicial preparado: 03:00 de Brasília, com atraso aleatório de até dez minutos. Meta inicial de perda de dados: até 24 horas, condicionada a backups bem-sucedidos; falhas precisam de intervenção. Responsável e meta de recuperação ainda precisam de confirmação do operador.

Este é um roteiro executável para o host Ubuntu da VPS. A existência dos arquivos no repositório não comprova instalação, agendamento ou execução no servidor. Continuam válidas as evidências e limitações do [registro de 17/11](implantacao-2026-11-17.md).

## 1. Renovar e conferir o Drive

Como o usuário que configurou rclone na VPS (root, nesta implantação):

```bash
rclone config reconnect opdrive:
```

Sem navegador na VPS, responder `n` e executar no PC o comando `rclone authorize ...` completo fornecido, preservando os argumentos. Autorizar com a mesma conta de armazenamento anterior. Colar o token diretamente na VPS; nunca enviar para chat, GitHub ou logs. Não recriar o crypt nem trocar senhas.

```bash
rclone lsf opbackup:
```

Confirmar o backup anterior. Guardar fora da VPS, em local protegido e recuperável, cliente OAuth/configuração necessários e as duas senhas do crypt (incluindo o salt). `rclone.conf` contém credenciais recuperáveis: não é seguro publicá-lo. A perda das chaves torna a cópia cifrada inutilizável.

## 2. Instalar a rotina revisada no host

Usar checkout da versão aprovada, na raiz do projeto. Não executar comandos de instalação de uma PR ainda em revisão. Anotar o SHA com `git rev-parse HEAD`; os caminhos abaixo são destinos de instalação propostos, não evidências de recursos existentes.

```bash
install -d -m 0700 /opt/op-app-ops /var/lib/op-app-backup
install -m 0700 ops/backup.py /opt/op-app-ops/backup.py
install -m 0644 ops/op-app-backup.service /etc/systemd/system/op-app-backup.service
install -m 0644 ops/op-app-backup.timer /etc/systemd/system/op-app-backup.timer
test -e /etc/op-app-backup.env || install -m 0600 ops/backup.env.example /etc/op-app-backup.env
```

Editar `/etc/op-app-backup.env` diretamente no host: preencher o nome efetivo do serviço Swarm do Postgres e do banco. Manter `OP_BACKUP_REMOTE=opbackup:op-app-diario` e retenção 30. O exemplo não contém senhas. Conferir que o remoto é crypt:

```bash
rclone listremotes --long
systemd-analyze verify /etc/systemd/system/op-app-backup.service /etc/systemd/system/op-app-backup.timer
systemctl daemon-reload
systemctl start op-app-backup.service
systemctl show op-app-backup.service -p Result -p ExecMainStatus
journalctl -u op-app-backup.service -n 30 --no-pager
```

É necessário Python 3 do sistema, Docker e rclone acessíveis ao root. Não há dependência de bibliotecas Python externas. O serviço acessa o socket Docker, equivalente a privilégios administrativos; instalar somente código revisado e manter os arquivos sob controle do root. A rotina espera exatamente um contêiner local do banco. Em Swarm com mais de um nó, instalar/executar no nó do banco e rever o agendamento se a tarefa mudar de nó.

Somente após `Result=success`, `ExecMainStatus=0` e conferência do arquivo no remoto:

```bash
rclone lsf opbackup:op-app-diario
cat /var/lib/op-app-backup/last-success
systemctl enable --now op-app-backup.timer
systemctl list-timers op-app-backup.timer --all
```

O timer usa UTC explicitamente e executa uma vez após retorno da máquina se perdeu o horário. Antes de manutenção ou migração, gerar também uma cópia manual com `systemctl start op-app-backup.service` e conferir o resultado. Não iniciar duas cópias simultâneas: o script usa trava exclusiva.

## 3. Garantias e limites da rotina

- Recusa destino cujo remoto não seja crypt e usa subpasta dedicada `op-app-diario`.
- Gera dump custom com `pg_dump`, confere índice, calcula SHA-256 e envia dump e manifesto pelo crypt.
- Baixa novamente os dois arquivos e confere o hash e o manifesto antes da retenção.
- Mantém cópia local em diretório privado. Arquivos locais são dump em claro, protegidos por permissões; criptografia do armazenamento do host é uma medida separada.
- Remove apenas nomes gerados pela rotina com data anterior a 30 dias, na subpasta dedicada e no diretório local. Não remove o backup manual anterior nem outros arquivos.
- Falhas encerram o serviço com código diferente de zero; não atualizam o marcador de sucesso. Falhas antes da validação externa não iniciam retenção. Uma falha na própria limpeza pode deixar retenção parcialmente aplicada; cópia atual permanece.

Download e hash não substituem restauração. O dump contém objetos do banco, não as roles globais, a configuração do painel, as chaves Django ou as credenciais do crypt. Guardar separadamente e conferir como recriar a conta da aplicação, permissões, variáveis e serviços.

## 4. Acompanhar falhas e atraso

O operador deve conferir diariamente resultado e idade do marcador; ele representa a última execução integralmente concluída, não apenas a criação local de um arquivo:

```bash
systemctl show op-app-backup.service -p Result -p ExecMainStatus
systemctl list-timers op-app-backup.timer --all
python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
p = Path('/var/lib/op-app-backup/last-success')
if not p.exists():
    raise SystemExit('FALHA: nenhum backup integralmente confirmado')
age = (datetime.now(timezone.utc) - datetime.fromisoformat(p.read_text().strip())).total_seconds() / 3600
print(f'Idade do ultimo sucesso: {age:.1f} horas')
if age < 0 or age > 26:
    raise SystemExit('FALHA: horario inconsistente ou backup atrasado; investigar')
PY
```

O journal e a consulta acima são sinalização local, **não notificação ativa**. Escolher e validar um canal de alerta monitorado antes de depender de operação sem acompanhamento diário. Em falha, preservar cópias anteriores, investigar Drive/OAuth, espaço, serviço e logs; repetir manualmente e confirmar recuperação. Não descartar backups para resolver um upload que falhou.

## 5. Ensaio de recuperação sem sobrescrever a origem

Identificar exatamente um contêiner do banco e outro do App; preencher variáveis na sessão SSH, sem publicar seus valores internos. Baixar um dump e seu manifesto do crypt em diretório privado. Selecionar um nome real listado pelo rclone, sem adivinhar o timestamp:

```bash
umask 077
OP_DRILL_DIR=$(mktemp -d)
read -r -p 'Nome do dump da rotina: ' OP_DUMP_NAME
rclone copyto "opbackup:op-app-diario/$OP_DUMP_NAME" "$OP_DRILL_DIR/$OP_DUMP_NAME"
rclone copyto "opbackup:op-app-diario/$OP_DUMP_NAME.sha256" "$OP_DRILL_DIR/$OP_DUMP_NAME.sha256"
(cd "$OP_DRILL_DIR" && sha256sum --check "$OP_DUMP_NAME.sha256")
```

Só avançar se o hash for válido. Definir `OP_DB_CONTAINER` e `OP_WEB_CONTAINER` por inventário local; conferir que cada variável tem exatamente um ID. Criar banco novo com nome exclusivo; anotar a conta limitada da aplicação em `OP_APP_DB_ROLE`:

```bash
OP_RESTORE_DB="op_restore_$(date -u +%Y%m%dT%H%M%SZ)"
OP_RESTORE_STARTED=$(date +%s)
docker exec -u postgres "${OP_DB_CONTAINER:?}" createdb --no-password -U postgres --template=template0 --owner="${OP_APP_DB_ROLE:?}" "${OP_RESTORE_DB:?}"
```

Se `createdb` falhar, parar: não reutilizar um banco existente. Somente depois de sua criação bem-sucedida:

```bash
docker exec -i -u postgres "${OP_DB_CONTAINER:?}" pg_restore --no-password -U postgres --dbname="${OP_RESTORE_DB:?}" --single-transaction --exit-on-error < "$OP_DRILL_DIR/${OP_DUMP_NAME:?}"
```

Se restaurar com sucesso, conferir migrações da cópia por substituição de ambiente apenas no processo:

```bash
docker exec -e POSTGRES_DB="${OP_RESTORE_DB:?}" "${OP_WEB_CONTAINER:?}" python manage.py migrate --check
```

Conferir contagens e relações de usuários/grupos/setores, trabalhadores, tarefas, histórico e alocações do snapshot. Não esperar que contagens do banco vivo permaneçam iguais se houve alterações depois do dump. Para ensaio com conteúdo, criar previamente casos sintéticos aprovados (tarefa e alocação em mais de um dia) e registrar seu estado antes de gerar a cópia. Não criar massa sintética no banco com dados reais sem planejamento.

Para conferir telas da cópia, criar App de recuperação isolado e com acesso restrito, apontando apenas para o banco restaurado. Não trocar as variáveis do App ativo para testar. Registrar login com conta adequada, quadro semanal e restrições por setor. Não expor a cópia com credenciais herdadas a um domínio público de teste.

Ao concluir todos os passos e conferências, medir `$(($(date +%s) - OP_RESTORE_STARTED))` segundos e registrar escopo/resultado. Não declarar RTO atendido apenas porque `pg_restore` terminou. Preservar ou remover a cópia por procedimento explícito, conferindo o nome; não incluir exclusão automática neste roteiro.

## 6. HSTS gradual, release e reversão

O código aceita `DJANGO_SECURE_HSTS_SECONDS`, inteiro não negativo, padrão 0. Após novo deploy e conferência de HTTPS/certificado, configurar inicialmente `3600` no App e fazer deploy. `includeSubDomains` e preload permanecem desativados. HTTPS válido deve apresentar `Strict-Transport-Security: max-age=3600`; não elevar a duração enquanto o período inicial não for observado. Desabilitar a variável não apaga imediatamente a política já armazenada pelo navegador.

```bash
curl -I --max-time 15 https://industrial.manexlabs.dev/health/
curl -I --max-time 15 http://industrial.manexlabs.dev/admin/
```

Esperar saúde HTTP 200, cabeçalho HSTS no HTTPS e redirecionamento para HTTPS no segundo comando. No console do App: `python manage.py check --deploy` e `python manage.py migrate --check`. Registrar quaisquer avisos restantes, sem silenciar para obter resultado artificialmente limpo.

Antes de cada release: registrar SHA/imagem atual e alvo, backup confirmado e migrações propostas. No EasyPanel, implantar a referência aprovada; executar migrações e `configurar_perfis` em etapa controlada quando necessário. Conferir saúde, login, estáticos e papéis. Em falha, voltar à imagem anterior somente se compatível com o esquema; não executar migração reversa ou restaurar sobre o banco ativo por tentativa. Migração incompatível exige janela de recuperação planejada, preservando o estado que falhou.

## 7. Checklist para encerrar a #16

- [ ] OAuth renovado; acesso e recuperação confirmados depois da publicação.
- [ ] Segredos de recuperação guardados fora da VPS e recuperáveis.
- [ ] Serviço instalado e execução manual integral aprovada.
- [ ] Timer habilitado e execução agendada observada; retenção conferida.
- [ ] Responsável por operação/suporte confirmado; acompanhamento e canal de falha definidos.
- [ ] Restauração com conteúdo sintético e relações conferida; tempo medido e meta de recuperação acordada.
- [ ] HTTPS, HSTS/avisos, cookies, CSRF, estáticos, contas e escopo setorial conferidos no host efetivo.
- [ ] Versão publicada, reversão, evidências e autorização dos dados registradas.

Itens preparados no Git não são evidências de execução. Encerrar a #16 somente após aceite do operador; uso de dados reais depende de decisão específica.

Referências: [rclone headless](https://rclone.org/remote_setup/), [crypt](https://rclone.org/crypt/), [listremotes](https://rclone.org/commands/rclone_listremotes/), [PostgreSQL — dump/restauração](https://www.postgresql.org/docs/17/backup-dump.html), [Django — HSTS](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-hsts-seconds).
