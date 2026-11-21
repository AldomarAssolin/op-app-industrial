# OP-APP | Planejamento Operacional Industrial

Sistema independente para **planejamento e distribuição diária de trabalhadores em tarefas industriais**, com consulta consolidada por semana. O projeto busca evoluir o planejamento hoje realizado em planilhas, preservando a simplicidade do processo operacional.

> **Estado do projeto:** MVP funcional das issues #1 a #6 implementado e aceito localmente. A aplicação já foi implantada e teve verificações informadas pelo operador; o aceite operacional permanece na issue #16. Consulte o [registro da implantação](docs/implantacao-2026-11-17.md) e o [roteiro de operação e recuperação](docs/operacao-piloto.md).

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

### Módulos e evolução

| Módulo | Responsabilidade |
| --- | --- |
| Organização | Cadastro de setores, funções e trabalhadores no Admin (issue #2) |
| Planejamento | Tarefas/histórico (issue #3) e alocações diárias com seleção multidiária (issue #4) no Admin |
| Consulta semanal | Quadro em `/planejamento/semanal/` com semana, setor autorizado, navegação e impressão (issue #5) |
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

### Organização atual

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
├── .github/workflows/setup.yml
├── docs/issue-001-validacao.md
├── docs/organizacao.md
├── docs/tarefas.md
├── docs/alocacoes.md
├── docs/quadro-semanal.md
├── .env.example
├── .gitignore
├── compose.yaml
├── manage.py
├── requirements.txt
└── README.md
```

> `organizacao` possui os modelos Setor, Funcao e Trabalhador e a migração `0001_initial`; `planejamento` possui Tarefa, HistoricoTarefa e Alocacao, com migrações `0001_initial` e `0002_alocacao`. Os templates de alocação ficam dentro do app. As pastas globais `static/` e `templates/` não existem nesta entrega; `TEMPLATES[0]["DIRS"]` está vazio e os templates do Admin vêm do Django.

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
python -m pip install -r requirements.txt
python -m pip check
```

> `requirements.txt` fixa as dependências diretas e transitivas da revisão do setup. Atualizações devem ser deliberadas e acompanhadas da execução da suíte em PostgreSQL.

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
docker compose up -d --wait --wait-timeout 90 db
docker compose ps
```

Em `compose.yaml`, o PostgreSQL 17 é publicado somente em `127.0.0.1:5433`, com `healthcheck`. O comando acima aguarda o banco ficar saudável. Se o Compose instalado não suportar `--wait`, use `docker compose up -d db` e confira o estado `healthy` em `docker compose ps` antes de continuar.

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

Os nove testes de infraestrutura implementados na issue #1 verificam:

- Registro dos aplicativos `organizacao` e `planejamento`.
- Uso do backend PostgreSQL.
- Execução de consulta SQL simples.
- Persistência de usuário pelo ORM.
- Autenticação básica do Django.
- Redirecionamento de usuário anônimo no Django Admin.

Execute a suíte completa:

```bash
python manage.py collectstatic --noinput
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
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
```

**Banco de testes:** testes que usam `TestCase` criam e descartam um banco separado (habitualmente `test_op_app_dev`). O usuário de PostgreSQL precisa ter permissão para criar o banco de testes. **Nunca configure esses testes para utilizar o banco de produção.**

> A base da issue #1 contém 9 testes: 4 de registro dos apps e 5 de banco/autenticação/Admin. As issues #2 a #5 acrescentam testes de modelos e fluxos do Admin; rode a suíte completa para validar o total atual. A issue #1 registra uma execução local anterior aprovada. Resultados da revisão atual e suas limitações estão em [docs/issue-001-validacao.md](docs/issue-001-validacao.md).

O workflow **Setup Django e PostgreSQL** executa a instalação pelo manifesto, valida o Compose real do projeto, inicia PostgreSQL 17, aplica e confere migrações e roda a suíte em Python 3.12. Os valores de ambiente do CI são descartáveis e não usam credenciais locais. O `down -v` do workflow remove apenas o banco descartável do runner; não é uma instrução de limpeza para seu banco local.

## 7. Decisões de domínio (planejadas)

- Uma **tarefa** pode durar vários dias ou semanas.
- Uma tarefa pode envolver **múltiplos trabalhadores**.
- Um trabalhador pode ser alocado a **múltiplas tarefas no mesmo dia**.
- A entidade `Alocacao` relacionará trabalhador, tarefa e **uma data**; a seleção de um intervalo de dias pela interface gerará os registros correspondentes.
- A combinação `(trabalhador, tarefa, data)` deverá ser única para evitar duplicações acidentais.
- A **semana** será inicialmente um filtro de consulta, sem tabela própria.
- Equipes serão dinâmicas, formadas pelas alocações, sem cadastro de equipes fixas no MVP.
- Função profissional e perfil de acesso serão conceitos distintos.

As regras de tarefas e alocações diárias estão implementadas; o quadro semanal consulta os registros existentes sem tabela própria de semana. Os cadastros organizacionais já estão implementados; consulte [docs/organizacao.md](docs/organizacao.md) para normalização, homônimos, inativação, exclusão protegida e uso no Admin.

### Cadastros organizacionais no Admin

Após aplicar as migrações, entre em `/admin/` e cadastre setores, funções e trabalhadores no grupo **Organização**. Nomes de setores e funções são únicos sem distinção de caixa; trabalhadores admitem homônimos e são identificados por ID. Setor e função principal são obrigatórios. Para descontinuar cadastros, desmarque **Ativo**: os vínculos são preservados. Setores e funções com trabalhadores vinculados não podem ser excluídos.

Veja o roteiro e as decisões em [docs/organizacao.md](docs/organizacao.md).

### Tarefas operacionais no Admin

Em **Planejamento operacional → Tarefas**, cadastre título, setor e período previsto. A tarefa começa pendente; conclusão exige início explícito, cancelamento preserva o cadastro e reabertura retorna a pendente. Prazo vencido não altera status. O histórico registra mudanças de status, período e setor e protege a tarefa contra exclusão. Consulte [docs/tarefas.md](docs/tarefas.md) para a tabela de transições e o exemplo **Eixo THC 95**.

### Alocações diárias

Em **Planejamento operacional → Alocações diárias**, cadastre ou corrija um dia; use **Alocar vários dias** para escolher um período e dias da semana. A mesma pessoa pode participar de tarefas diferentes no mesmo dia. A combinação trabalhador/tarefa/data não se repete, os dias devem estar no prazo e trabalhador inativo ou tarefa encerrada bloqueiam a gravação. O lote é atômico e a autoria vem do usuário autenticado. Alocação não representa jornada exclusiva nem contabiliza horas. Veja [docs/alocacoes.md](docs/alocacoes.md).

### Quadro semanal

Abra `/planejamento/semanal/` ou o link **Quadro semanal** na listagem de alocações. Selecione uma data da semana e um setor autorizado; os links anterior/próxima preservam os filtros. Duas tarefas no mesmo dia aparecem em linhas diferentes. Sábado/domingo são incluídos quando selecionados ou quando há alocações nesses dias. A tela oferece estilo de impressão e exige `view_alocacao`; para usuários comuns, configure os vínculos **Organização → Acessos de usuários a setores**. Sem vínculos, o quadro fica vazio. Veja [docs/quadro-semanal.md](docs/quadro-semanal.md).

A issue #6 estende o escopo às listagens, detalhes, escolhas e gravações do Admin. Configure os grupos com `python manage.py configurar_perfis` após `migrate`; apenas o superusuário atribui contas/grupos/vínculos. Leia [docs/seguranca-piloto.md](docs/seguranca-piloto.md) para a matriz de perfis e o aceite local registrado da issue #6.

## 8. Segurança e limites do projeto

Os perfis são Administrador (operação global), Coordenador, Líder e Consulta (setores vinculados). Consulta não grava. Administrador operacional não gerencia credenciais, grupos ou concessões: essa configuração é exclusiva do superusuário. Alocações exigem autorização tanto para o setor da tarefa quanto para o setor principal do trabalhador. Novas alterações de tarefa pelo Admin registram o ator no histórico.

A issue #6 foi concluída por aceite local combinado de navegador e testes HTTP. A implantação e as pendências operacionais do piloto são acompanhadas separadamente pela issue #16; confira [operação e recuperação](docs/operacao-piloto.md).

- Não versionar senhas, chaves, tokens ou o arquivo `.env`.
- Restringir o banco de desenvolvimento a `127.0.0.1`.
- Manter `DJANGO_DEBUG=True` apenas em ambiente local.
- Aplicar autorização no backend; esconder controles de interface não substitui controle de acesso.
- Utilizar dados fictícios durante a implementação e validação inicial.
- Qualquer uso de dados ou processos reais na empresa depende de autorização e de definição das responsabilidades de operação e suporte.
- Este setup **não constitui uma configuração pronta para produção**.

## 9. Fluxo de desenvolvimento

Criar uma branch por entrega a partir de `main`; incorporar alterações por pull request com verificações e revisão.

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
| #001 | Estrutura Django, PostgreSQL, ambiente e testes | Implementada e validada (9 testes em PostgreSQL) |
| #002 | Cadastros de setores, funções e trabalhadores | Implementados no Admin; validação pelo CI |
| #003 | Gestão de tarefas | Implementada no Admin; validação pelo CI |
| #004 | Alocações diárias | Implementadas no Admin; validação pelo CI |
| #005 | Visualização semanal | Implementada; validação pelo CI |
| #006 | Permissões e validação do MVP | Concluída por aceite local combinado; evidências em docs/ |
| #016 | Implantação e operação do piloto | Aplicação implantada; automação, recuperação e aceite operacional em andamento |

*Numeração conferida nas issues do repositório. Consulte o GitHub para o estado atualizado.*

## 11. Documentação

A [entrada operacional](docs/entrada-operacional.md) reúne o fluxo de login, navegação por permissões e o roteiro de validação da issue #24.

A evolução da apresentação pública está descrita em [docs/pagina-publica.md](docs/pagina-publica.md). Ela tem habilitação própria e transição do Branding em duas etapas; não substituir a página inicial cadastrada no OAuth antes de preparar o endereço específico da integração.

As decisões de arquitetura, regras de negócio e guias técnicos serão mantidos em `docs/`. O README deve continuar sendo o ponto de entrada do projeto, sem acumular toda a especificação funcional.

O [registro da implantação de 17/11/2026](docs/implantacao-2026-11-17.md) reúne as entregas, validações informadas pelo operador, ensaio de recuperação, cópia criptografada no Drive e pendências da issue #16. Consulte esse registro para o andamento da implantação; as referências históricas acima não representam o estado operacional atual.

Para configurar o piloto em industrial.manexlabs.dev, consulte o [roteiro do EasyPanel](docs/easypanel-configuracao.md). Ele descreve banco, aplicação, variáveis, domínio e verificações. Para backups diários, retenção de 30 dias, recuperação e release, consulte o [roteiro operacional](docs/operacao-piloto.md); a issue #16 continua aberta até o aceite operacional.

---

**OP-APP**: planejamento industrial com foco em organização, rastreabilidade e evolução incremental.
