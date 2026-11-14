# Issue #1 — revisão do setup

Revisão em 14/11/2026, baseada no commit `a7584460460ac613174127691aabb2096a391009`.

## Escopo

Conferir `.gitignore`, arquivos sensíveis e correspondência entre README e configuração; tornar a validação reproduzível. Não inclui modelos de negócio, integração com GTH Agents ou preparação para produção.

## Evidências da revisão

- Os 25 arquivos da árvore de `main` foram lidos. Não foram encontrados marcadores de conflito nem arquivos `.env`, bancos locais ou chaves privadas versionados.
- Foram conferidas as árvores dos três commits alcançáveis em `main`: `a758446`, `44a9f34` e `e3fc69f`. Os arquivos de aplicação de `44a9f34` são os mesmos de `a758446`; a outra raiz contém apenas `.gitignore`. As variantes históricas desse arquivo também foram lidas.
- A revisão de conteúdo não encontrou padrões usuais de tokens/chaves privadas. As senhas presentes nos testes são dados sintéticos de teste; os campos sensíveis de `.env.example` estão vazios. Essa revisão não é uma garantia universal de ausência de segredos.
- `git check-ignore` confirmou exclusão de `.env`, `.env.local`, `.env.production`, `.venv/` e bytecode, preservando `.env.example`. O `.gitignore` atual não precisou de alteração.
- `compose.yaml` usa PostgreSQL 17, serviço `db`, volume persistente, healthcheck e publicação em `127.0.0.1:5433`.
- `config/settings.py` lê as mesmas variáveis descritas no README; usa PostgreSQL, carrega `.env` e registra os dois apps e o Admin.
- As pastas globais `static/` e `templates/` não existem. A descrição da árvore no README foi corrigida; a configuração atual usa os templates dos apps.

## Alterações

- `requirements.txt` com versões diretas e transitivas fixadas a partir de instalação isolada em Python 3.12.
- README ajustado à estrutura existente, aos nove testes implementados e à instalação pelo manifesto.
- Workflow `Setup Django e PostgreSQL` usa o próprio `compose.yaml`, aplica migrações e executa a suíte completa em PostgreSQL 17. Não depende de secrets do repositório.

## Validação realizada neste ambiente

| Verificação | Resultado |
| --- | --- |
| Instalação isolada das versões do manifesto | Concluída |
| `python -m pip check` | Sem dependências quebradas |
| `python manage.py check` | Sem problemas |
| `OrganizacaoConfigTests` e `PlanejamentoConfigTests` | 4 testes aprovados; sem acesso ao banco |
| Sintaxe dos arquivos Python e leitura do YAML do workflow | Aprovadas |
| `git diff --check` | Sem erros |
| Docker Compose, migrações e suíte completa em PostgreSQL | Pendente de execução no Actions ou ambiente local; Docker/PostgreSQL indisponíveis neste ambiente |

Os comandos Django acima usaram variáveis descartáveis de revisão, sem credenciais pessoais. A execução local anterior de **9 testes aprovados** permanece como evidência histórica informada na issue, não como resultado desta revisão.

## Critério de fechamento

1. Workflow do commit do PR aprovado: instalação, Compose, PostgreSQL saudável, `check`, `migrate`, verificação de migrações e **9 testes aprovados**.
2. Registrar o link da execução aprovada na issue/PR e incorporar a revisão em `main`.
3. Marcar os dois itens residuais e encerrar a issue #1.

Alternativa local, após seguir a instalação e preencher `.env` conforme o README:

```bash
python -m pip check
docker compose config --quiet
docker compose up -d --wait --wait-timeout 90 db
python manage.py check
python manage.py migrate --noinput
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py test -v 2 --noinput
```

Registrar commit, versões e saída dos comandos, sem publicar `.env` ou a saída expandida de `docker compose config`. Não usar `down -v` no banco local para esta validação.
