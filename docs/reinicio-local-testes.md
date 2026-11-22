# Reinício do banco local para validar atividades da tarefa

Este roteiro apaga somente os dados do PostgreSQL do projeto Compose local: usuários, vínculos, tarefas e alocações de teste. Não executar na VPS. Produção não deve ser atualizada nesta etapa.

Pare o runserver. No diretório do repositório local, com a branch da PR #42 atualizada e o `.env` local conferido:

```bash
git fetch origin
git switch fix/issue-28-periodo-e-selecao
git pull --ff-only
docker compose config --services
docker compose down --volumes
docker compose up -d --wait db
source .venv/bin/activate
python manage.py migrate --noinput
python manage.py configurar_perfis
python manage.py createsuperuser
python manage.py check
python manage.py runserver
```

O Compose deste projeto possui somente o serviço `db` e o volume `postgres_data`. Confira o diretório e a configuração antes do comando de remoção. Não remova outros volumes Docker nem migrações do repositório. A recriação lê as credenciais atuais do `.env`, evitando a divergência entre senha do volume antigo e configuração local.

Se a versão anterior da PR já foi aplicada, `flush` não basta: ele esvazia registros, mas não recria o esquema modificado desta migração ainda não publicada.

## Massa de teste

1. Cadastre Funções como atividades: Montagem e Soldagem.
2. Prepare setores A/B, turnos, trabalhadores e os vínculos de Coordenador/Líder conforme o guia de autorização de turnos. Recrie as contas de QA; as contas anteriores foram removidas.
3. Crie Eixo THC 95 com datas válidas e ambas as atividades, pelo menu expansível.
4. Em Add alocação diária, confirme a ausência de Atividade de referência, mantendo trabalhador, tarefa, data, turno e observação. As atividades da tarefa aparecem para consulta.
5. Em Planejar, marque dois trabalhadores e quatro dias: revisar deve mostrar oito alocações, sem selecionar atividades e sem duplicar por atividade. Confirme e confira o quadro.
6. Edite uma alocação: atividades não podem ser trocadas nesse formulário.
7. Como Líder, crie uma tarefa com atividades. Depois, confira que os dados gerais, incluindo atividades, não são editáveis.
8. Como Coordenador, altere as atividades da tarefa e confira histórico com autoria, quadro atualizado e invalidação de uma revisão de planejamento aberta antes da mudança.

Nenhum reset de produção está incluído neste roteiro. O banco usado pelos testes automatizados é descartável e independente do banco de desenvolvimento.
