# Configuração do piloto no EasyPanel — issue #16

Destino: `industrial.manexlabs.dev`. Este roteiro prepara um piloto sintético em banco novo; não importa o banco local. A issue #16 permanece aberta até evidências no host efetivo e ensaio de recuperação.

## 1. Projeto e banco

No EasyPanel, criar projeto **op-industrial** (nome proposto; conferir se já existe). Dentro dele, criar serviço **Postgres**, chamado **db**, selecionando explicitamente a imagem PostgreSQL 17. Definir banco e usuário próprios do projeto; conferir persistência e privilégios. Não publicar a porta 5432 para a Internet nem criar domínio público para o banco.

Em Credentials, identificar o **host interno**, porta, nome do banco, usuário e senha. Esses valores devem ser preenchidos diretamente no ambiente da aplicação; não enviar senhas no chat. Não presumir que o host seja `localhost` ou simplesmente `db`: usar o valor efetivo informado pelo painel.

## 2. Aplicação

Criar serviço **App**, nome proposto **web**. Configurar origem GitHub:

| Campo | Valor |
| --- | --- |
| Repositório | AldomarAssolin/op-app-industrial |
| Branch | main, depois do merge da preparação; não publicar uma versão sem Dockerfile |
| Caminho de build | Raiz do repositório |
| Builder | Dockerfile |
| Arquivo | Dockerfile |
| Porta HTTP interna | 8000 |
| Comando de início | Manter o CMD da imagem: Gunicorn com config/gunicorn.py |

A imagem usa usuário sem privilégios e WhiteNoise para estáticos. Não montar um volume sobre `/app` ou `/app/staticfiles`, pois isso oculta o código ou os arquivos coletados da imagem. A sonda `/health/` comprova apenas processo HTTP, não conectividade ou migrações do banco. Para aplicação e banco, conferir saúde separadamente.

## 3. Variáveis do serviço App

Usar [.env.piloto.example](../.env.piloto.example) como modelo e preencher diretamente em Environment. Nunca copiar valores sensíveis para o Dockerfile, argumentos de build, README ou repositório. O código usa campos separados, não `DATABASE_URL`.

| Variável | Configuração |
| --- | --- |
| DJANGO_SECRET_KEY | Chave nova exclusiva do piloto, gerada com ferramenta confiável e guardada em local protegido |
| DJANGO_DEBUG | False |
| DJANGO_ALLOWED_HOSTS | industrial.manexlabs.dev,127.0.0.1,localhost |
| POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD | Valores reais do banco do projeto |
| DB_HOST | Host interno efetivo do Postgres no painel |
| DB_PORT | 5432, se essa for a porta interna do serviço |
| DJANGO_SESSION_COOKIE_SECURE | True no host HTTPS |
| DJANGO_CSRF_COOKIE_SECURE | True no host HTTPS |
| DJANGO_SECURE_SSL_REDIRECT | True após conferir HTTPS/proxy |
| DJANGO_TRUST_PROXY_HEADERS | False inicialmente; habilitar apenas após as verificações abaixo |
| DJANGO_CSRF_TRUSTED_ORIGINS | Vazio para origem única; se necessário pela topologia validada, https://industrial.manexlabs.dev |
| WEB_CONCURRENCY | 2 como ponto inicial; ajustar após conferir memória/CPU, não como garantia de capacidade |

Não habilitar `DJANGO_TRUST_PROXY_HEADERS=True` por tentativa e erro. Antes, conferir que a porta do App não está publicada diretamente e que o proxy controlado remove/substitui `X-Forwarded-Proto` externo e informa o esquema correto. Só então habilitar a variável e validar o acesso HTTPS. Gunicorn não interpreta cabeçalhos de esquema por outra configuração; a confiança fica explícita no Django.

Com SSL_REDIRECT=True e confiança ainda desativada, pode haver loop de redirecionamento enquanto o proxy termina TLS. Resolver a topologia/confiança; não desabilitar cookies seguros ou proteção CSRF para contornar o problema. A sonda interna permanece HTTP sem redirecionamento e sem acesso ao banco.

## 4. Primeira subida e inicialização

Depois de preencher as variáveis, fazer Deploy. Conferir build, usuário do contêiner e logs do Gunicorn. No console do serviço App executar, para o banco novo do piloto:

```bash
python manage.py check
python manage.py migrate --noinput
python manage.py configurar_perfis
python manage.py migrate --check
python manage.py createsuperuser
```

Definir a senha do superusuário diretamente no console. Não colocá-la em variável permanente nem no histórico de comandos. Migrações e sincronização de grupos são etapas explícitas: não são executadas automaticamente a cada início de worker. Em atualizações futuras, fazer backup e avaliar migrações antes de executar o procedimento.

O `collectstatic` já ocorre no build com valores descartáveis, sem banco e sem segredos reais. O contêiner falha ao iniciar se as variáveis obrigatórias de execução estiverem ausentes; não usar a chave descartável do build em runtime.

## 5. Domínio e HTTPS

Identificar o IP público efetivo da VPS e a configuração DNS atual. Planejar o registro de `industrial.manexlabs.dev` e verificar se há A/AAAA conflitantes; não adivinhar IP ou alterar outros subdomínios. No serviço App, adicionar domínio associado à porta interna 8000 e configurar HTTPS conforme o painel. Se houver outro proxy/CDN, conferir o percurso completo e a política de certificado.

Validar certificado, redirecionamentos, login/logout, cookies e rejeição de POST sem token no host real. Depois executar:

```bash
python manage.py check --deploy
```

Registrar e resolver os avisos ou justificar cada um. HSTS é uma decisão posterior à validação do HTTPS; não ativar preload/includeSubDomains indiscriminadamente. Este roteiro não declara check --deploy ou HTTPS do servidor como aprovados.

## 6. Contas, backup e aceite

Criar contas nominativas com staff e somente os grupos adequados; cadastrar UsuarioSetor para Líder/Coordenador/Consulta. Não dar superusuário a contas operacionais nem copiar contas QA locais. Usar apenas dados sintéticos na primeira validação.

Definir responsável, frequência, retenção e destino externo protegido dos backups. Gerar backup do banco efetivo, restaurar em outro banco e conferir conteúdo/acessos sem sobrescrever a origem. Banco persistente ou mensagem de backup concluído não comprova recuperação.

Conferir a [matriz do plano](plano-deploy.md), quando incorporada pela PR #17, e registrar host, commit/imagem, data, responsáveis e resultados na issue #16. Sem a matriz e a recuperação aprovadas, não liberar dados reais nem fechar a issue.

## Desenvolvimento e validação do pacote

Ao instalar dependências atualizadas, coletar estáticos antes da suíte:

```bash
python -m pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py test -v 2 --noinput
```

O CI também constrói a imagem e verifica processo, tela de login, CSS e usuário não root com credenciais descartáveis. Isso não substitui aceitação no EasyPanel.

Referências: [App](https://easypanel.io/docs/services/app), [Postgres](https://easypanel.io/docs/services/postgres), [WhiteNoise](https://whitenoise.readthedocs.io/en/stable/django.html), [Gunicorn](https://gunicorn.org/reference/settings/).
