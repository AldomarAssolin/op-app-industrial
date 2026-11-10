# OP-APP | Planejamento Operacional Industrial

Sistema independente para **planejamento e distribuição diária de trabalhadores em tarefas industriais**, com consulta consolidada por semana. O projeto busca evoluir o planejamento hoje realizado em planilhas, preservando a simplicidade do processo operacional.

> **Estado do projeto:** fase inicial de estruturação (Issue #001). Os modelos de negócio, CRUDs e a visualização semanal descritos abaixo são **requisitos planejados**, não funcionalidades já entregues.

## 1. Objetivo e contexto

O primeiro módulo do OP-APP apoiará coordenadores e líderes na distribuição de trabalhadores entre tarefas de produção. Uma tarefa pode durar dias ou semanas, receber vários trabalhadores e compartilhar um mesmo trabalhador com outras tarefas no mesmo dia.

Exemplo de planejamento de origem:

| Trabalhador | Função na atividade | Tarefa | Dias |
| --- | --- | --- | --- |
| Aldomar | Montagem/Soldagem | Eixo THC 95 | Segunda a quinta |

No modelo proposto, essa linha representa **quatro alocações diárias** vinculadas à mesma tarefa. A consulta semanal reunirá as alocações em uma grade semelhante à planilha.

O OP-APP é **independente do GTH Agents**: possui repositório, banco de dados, configuração, autenticação e evolução próprios. Uma eventual integração futura deverá ocorrer por interfaces explícitas (por exemplo, API REST), sem compartilhar tabelas entre os sistemas.

## 2. Escopo

### Issue #001: estrutura inicial

- Projeto Django e aplicativos `organizacao` e `planejamento`.
- PostgreSQL em Docker Compose para desenvolvimento local.
- Aplicação Django executada em ambiente virtual Python (`.venv`).
- Configurações sensíveis por variáveis de ambiente.
- Django Admin e autenticação nativa.
- Testes básicos de carregamento dos aplicativos, acesso ao banco e autenticação.

### Próximas entregas (ainda não implementadas)

| Módulo | Responsabilidade |
| --- | --- |
| Organização | Cadastro de setores, funções e trabalhadores |
| Planejamento | Cadastro de tarefas e alocações diárias |
| Consulta semanal | Exibição de alocações por trabalhador, tarefa e dia, com filtros por semana e setor |
| Autorização operacional | Restrições de acesso por papel e setor |

**Fora do MVP inicial:** controle de horas e produtividade, manutenção, cadastro técnico de equipamentos, ordens de produção completas, React, API pública e integração com o GTH Agents.

## 3. Tecnologias e arquitetura

- **Python:** 3.12 (ambiente de referência do projeto).
- **Django:** linha 5.2 LTS.
- **Banco de dados:** PostgreSQL 17.
- **Driver:** `psycopg` 3.
- **Configuração local:** `python-dotenv`.
- **Interface inicial:** Django Admin; telas específicas com Django Templates quando implementadas.
- **Testes:** framework nativo do Django (`SimpleTestCase` e `TestCase`).
- **Infraestrutura local:** banco em Docker Compose, Django executado no host.

```text
Navegador
   |
   v
Django (host Linux / .venv; porta 8000)
   |
   v
PostgreSQL (Docker; 127.0.0.1:5433)
```

### Organização prevista

```text
op-app-industrial/
├── apps/
│   ├── __init__.py
│   ├── organizacao/
│   │   ├── apps.py
│   │   ├── models.py
│   │   └── tests.py
│   └── planejamento/
│       ├── apps.py
│       ├── models.py
│       └── tests.py
├── config/
│   ├── settings.py
│   └── urls.py
├── docs/
├── static/
├── templates/
├── .env.example
├── .gitignore
├── compose.yaml
├── manage.py
└── README.md
```

> A árvore acima é a **estrutura de referência**; confirme os arquivos existentes no repositório antes de considerar qualquer item implementado.

## 4. Requisitos de desenvolvimento

- Python 3.12 e `venv`.
- Docker Engine com plugin Docker Compose.
- Git.
- Portas `8000` (Django) e `5433` (PostgreSQL) disponíveis no computador.

## 5. Instalação e execução local

Execute os comandos a partir da raiz do repositório.

### 5.1 Criar e ativar o ambiente virtual

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install 'Django>=5.2,<5.3' 'psycopg[binary]>=3,<4' python-dotenv
```

> Caso o repositório passe a fornecer `pyproject.toml` ou `requirements.txt` com dependências fixadas, prefira instalar pelo manifesto versionado para garantir reprodutibilidade.

### 5.2 Configurar as variáveis de ambiente

```bash
cp .env.example .env
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Preencha `DJANGO_SECRET_KEY` com a chave gerada e `POSTGRES_PASSWORD` com uma senha **local**, não versionada.

Exemplo de chaves esperadas em `.env.example`:

```dotenv
DJANGO_SECRET_KEY=
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

POSTGRES_DB=op_app_dev
POSTGRES_USER=op_app_user
POSTGRES_PASSWORD=

DB_HOST=127.0.0.1
DB_PORT=5433
```

O arquivo `.env` **não deve** ser enviado ao Git. Confirme que o `.gitignore` contempla `.env`, `.venv/` e arquivos temporários de Python. Não use os valores locais em produção.

### 5.3 Iniciar o PostgreSQL

```bash
docker compose config --quiet
docker compose up -d db
docker compose ps
```

Na configuração de desenvolvimento prevista, o PostgreSQL é acessado somente por `127.0.0.1:5433`. Aguarde o serviço `db` apresentar estado saudável (*healthy*), caso o `healthcheck` esteja configurado.

### 5.4 Aplicar migrações e iniciar o Django

```bash
python manage.py check
python manage.py migrate
python manage.py runserver
```

Endereços locais:

- Aplicação: <http://127.0.0.1:8000/>
- Administração: <http://127.0.0.1:8000/admin/>

> A rota `/` pode responder com 404 enquanto não houver uma página inicial. Isso não significa, por si só, falha no setup. O Django Admin exige um usuário administrativo para acesso; se necessário, crie-o localmente com `python manage.py createsuperuser`.

### 5.5 Parar os serviços

Pare o Django com `Ctrl+C` no terminal e o banco com:

```bash
docker compose down
```

**Atenção:** `docker compose down -v` também remove volumes declarados e pode apagar os dados locais do PostgreSQL. Evite utilizá-lo sem intenção explícita de reiniciar o banco.

## 6. Testes automatizados

Os testes de infraestrutura propostos na Issue #001 verificam:

- Registro dos aplicativos `organizacao` e `planejamento`.
- Uso do backend PostgreSQL.
- Execução de consulta SQL simples.
- Persistência de usuário pelo ORM.
- Autenticação básica do Django.
- Redirecionamento de usuário anônimo no Django Admin.

Execute a suíte completa:

```bash
python manage.py test --verbosity=2
```

Ou cada aplicativo separadamente:

```bash
python manage.py test apps.organizacao -v 2
python manage.py test apps.planejamento -v 2
```

Verificações auxiliares:

```bash
python manage.py check
python manage.py showmigrations
```

**Banco de testes:** testes que usam `TestCase` criam e descartam um banco separado (habitualmente `test_op_app_dev`). O usuário de PostgreSQL precisa ter permissão para criar o banco de testes. **Nunca configure esses testes para utilizar o banco de produção.**

> A suíte sugerida contém 9 testes quando todos os testes de infraestrutura previamente planejados forem adicionados. A quantidade efetiva e o resultado devem ser confirmados por execução local; este README não os declara aprovados.

## 7. Decisões de domínio (planejadas)

- Uma **tarefa** pode durar vários dias ou semanas.
- Uma tarefa pode envolver **múltiplos trabalhadores**.
- Um trabalhador pode ser alocado a **múltiplas tarefas no mesmo dia**.
- A entidade `Alocacao` relacionará trabalhador, tarefa e **uma data**; a seleção de um intervalo de dias pela interface gerará os registros correspondentes.
- A combinação `(trabalhador, tarefa, data)` deverá ser única para evitar duplicações acidentais.
- A **semana** será inicialmente um filtro de consulta, sem tabela própria.
- Equipes serão dinâmicas, formadas pelas alocações, sem cadastro de equipes fixas no MVP.
- Função profissional e perfil de acesso serão conceitos distintos.

Essas decisões orientam as próximas issues e **ainda não representam funcionalidades existentes**.

## 8. Segurança e limites do projeto

- Não versionar senhas, chaves, tokens ou o arquivo `.env`.
- Restringir o banco de desenvolvimento a `127.0.0.1`.
- Manter `DJANGO_DEBUG=True` apenas em ambiente local.
- Aplicar autorização no backend; esconder controles de interface não substitui controle de acesso.
- Utilizar dados fictícios durante a implementação e validação inicial.
- Qualquer uso de dados ou processos reais na empresa depende de autorização e de definição das responsabilidades de operação e suporte.
- Este setup **não constitui uma configuração pronta para produção**.

## 9. Fluxo de desenvolvimento

Branch de referência para esta etapa:

```text
feature/issue-001-django-setup
```

Antes de abrir um pull request:

```bash
python manage.py check
python manage.py test --verbosity=2
git status
```

Um teste só deve ser marcado como aprovado após sua execução. Commits e merges devem ocorrer com a documentação e as configurações revisadas.

## 10. Roadmap inicial

| Issue | Entrega | Situação |
| --- | --- | --- |
| #001 | Estrutura Django, PostgreSQL, ambiente e testes | Em desenvolvimento / validação |
| #002 | Cadastros de setores, funções e trabalhadores | Planejada |
| #003 | Gestão de tarefas | Planejada |
| #004 | Alocações diárias | Planejada |
| #005 | Visualização semanal | Planejada |
| #006 | Permissões e validação do MVP | Planejada |

*As identificações acima seguem o planejamento desta conversa; verifique a numeração real das issues no GitHub antes de criar referências automáticas.*

## 11. Documentação

As decisões de arquitetura, regras de negócio e guias técnicos serão mantidos em `docs/`. O README deve continuar sendo o ponto de entrada do projeto, sem acumular toda a especificação funcional.

---

**OP-APP**: planejamento industrial com foco em organização, rastreabilidade e evolução incremental.
