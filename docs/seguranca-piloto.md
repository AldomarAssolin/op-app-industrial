# Perfis, escopo e validação do MVP — issue #6

## Política operacional

| Perfil Django | Leitura | Gravações |
| --- | --- | --- |
| Administrador | Todos os setores | Cadastros operacionais, tarefas e alocações |
| Coordenador | Setores vinculados | Trabalhadores, tarefas e alocações |
| Líder | Setores vinculados | Tarefas e alocações |
| Consulta | Setores vinculados | Nenhuma |
| Superusuário de configuração | Todos | Também usuários, grupos e vínculos UsuarioSetor |

O menu do Líder contém apenas Funções, Trabalhadores, Tarefas e Alocações diárias. Setores não ficam acessíveis para esse perfil, nem por URL direta ou popup, mesmo com permissões individuais de setor concedidas por engano. A escolha do setor autorizado dentro da tarefa continua disponível. Coordenador conserva sua consulta de setores; criar/editar/excluir setores segue exclusivo do Administrador/superusuário.

Funções profissionais não são grupos de autorização. Um trabalhador não exige conta. O perfil Administrador é operacional: não recebe gestão de usuários/grupos nem concessão de setores. Essas telas exigem superusuário, inclusive se uma permissão individual for concedida por engano.

Grupos concedem operações; UsuarioSetor delimita dados para os perfis restritos. Administrador e superusuário têm escopo global. Sem vínculo, os demais perfis não veem registros setoriais. Funções profissionais formam um catálogo global de leitura; só Administrador/superusuário o altera. O sistema admite múltiplos grupos e prevalece a união dos perfis elevados; não combine Consulta com um perfil de escrita se deseja acesso somente leitura. Consulta sozinho continua bloqueado para escrita mesmo com permissão individual extra.

## Configuração inicial

Após configurar ambiente e aplicar migrações:

```bash
python manage.py migrate
python manage.py configurar_perfis
python manage.py createsuperuser
```

O comando sincroniza apenas as permissões dos quatro grupos nomeados. É idempotente e substitui customizações de permissões nesses grupos; não altera usuários, flags staff, grupos de outras aplicações ou vínculos. Execute após migrate, inclusive no ambiente de testes de aceitação.

Com o superusuário, criar contas nominativas de piloto, ativar **staff**, atribuir o grupo apropriado e cadastrar **Organização → Acessos de usuários a setores**. Grupos Consulta/Líder/Coordenador sem vínculos ficam sem dados setoriais. Não conceder superusuário para contornar erro de configuração.

## Fronteiras protegidas

Listagens, buscas, filtros, detalhes, histórico, opções de FK e POSTs do Admin usam a política compartilhada. Acesso por ID fora do escopo não retorna o objeto. Uma transferência precisa permitir tanto o setor anterior quanto o novo: não basta trocar os parâmetros enviados. O formulário de vários dias também restringe suas opções.

Alocações exigem acesso ao setor da tarefa **e** ao setor principal do trabalhador. Participação entre setores é possível apenas quando ambos estiverem autorizados. Consulta semanal e serviço de consulta seguem a mesma regra. Isso restringe a possibilidade multissetorial anteriormente documentada.

Tarefas gravadas pelo Admin registram o usuário autenticado nas novas fotografias de histórico. Registros históricos anteriores ou criados por rotinas de configuração confiáveis podem ter autor vazio; não se inventa autoria retroativa. Histórico de setor anterior não autorizado é ocultado no inline.

Alocações preservam criado_por e substituem alterado_por pelo ator real; valores de autoria enviados pelo cliente são ignorados. Regras de status, período, unicidade, inativação, rollback e proteção de exclusão continuam no servidor.

O código de aplicação deve usar atores autenticados nas operações de gravação. Tarefa.save(ator=...) e Alocacao.save(ator=...)/delete(ator=...) verificam as políticas. Cadastro via Admin também verifica origem/destino. Chamadas ORM sem contexto em rotinas de seed/migração, bulk e SQL direto são interfaces administrativas confiáveis, não APIs para usuários. Nenhum endpoint público foi criado.

## Configuração e dados

.env continua ignorado e .env.example contém campos sensíveis vazios. SECRET_KEY vazia agora falha explicitamente na inicialização. Cookies de sessão são HttpOnly/SameSite=Lax; cookies seguros e redirecionamento HTTPS têm flags explícitas no ambiente. O Compose mantém PostgreSQL em 127.0.0.1:5433; não publicar essa porta.

Para piloto HTTPS: DEBUG=False, ALLOWED_HOSTS somente com o host real e as três flags de cookies/SSL=True após validar a terminação TLS. Não foi habilitada confiança automática em cabeçalhos de proxy. Rever proxy e redirecionamento na infraestrutura real antes de habilitar as flags, evitando loops. Rodar check --deploy nessa configuração e avaliar os avisos; o setup local não é um deploy empresarial.

Usar somente nomes/atividades sintéticos na aceitação. Antes do piloto: definir responsável pelo ambiente, suporte e cópia/restauração do banco; criar backup e testar restauração em banco separado. Autorização de dados reais, se necessária futuramente, é uma decisão separada. O aplicativo não libera máquinas, não valida NR12 e não substitui autorização técnica ou de segurança.

## Aceitação local dos novos perfis

A validação local do quadro da issue #5 foi informada pelo usuário em 16/11/2026. Isso não é aprovação dos novos perfis da issue #6.

Preparar dois setores sintéticos A/B, um trabalhador e uma tarefa em cada, e contas nominativas dos quatro perfis. Vincular Líder/Coordenador/Consulta somente ao setor A.

| Cenário | Resultado esperado | Evidência manual |
| --- | --- | --- |
| Líder abre listagem, filtros, detalhe e histórico de A | Consulta permitida | Pendente |
| Líder tenta ID de tarefa/alocação de B e altera parâmetro de setor | Sem objeto/dados de B | Pendente |
| Líder cria/edita tarefa e alocação de A | Permitido; autoria real | Pendente |
| Líder envia IDs de tarefa/trabalhador de B pelo formulário e pelo multidiário | Rejeitado, sem lote parcial | Pendente |
| Consulta tenta POST de criação/edição/exclusão | Acesso negado, sem mudança | Pendente |
| Coordenador cadastra/inativa trabalhador de A e tenta transferir para B | A permitido; B rejeitado | Pendente |
| Administrador operacional acessa A/B e tenta gerir usuário/grupo/vínculo | Operação global permitida; gestão de acesso negada | Pendente |
| Quadro semanal, segunda–quinta e segunda tarefa na terça | Duas tarefas preservadas; setores respeitados | Pendente |
| Dias fora do prazo, duplicata e tarefa encerrada | Erro de formulário, sem gravação parcial | Pendente |
| Cookies, logout, sessão e CSRF no host real do piloto | Configuração conferida no navegador | Pendente |

Registrar data, commit testado, papel utilizado e resultado (sem senhas ou dados reais). A suíte automatizada cobre os cenários de autorização, mas não substitui a aceitação manual pedida na issue.

## Critério de fechamento

Código e CI/revisão aprovados são uma parte da entrega. Manter a issue #6 aberta até aprovação dos cenários manuais acima e registro da configuração do piloto. Nenhum ambiente empresarial ou integração externa é implantado por esta alteração.

## Diagnóstico da conta usada na validação

Para testar Líder, usar uma conta com apenas o grupo Líder, ativa e staff, sem flag de superusuário e sem grupo Administrador. Superusuário e associação a Administrador continuam concedendo poderes administrativos por definição; o rótulo ou nome de usuário “líder” não limita esses poderes. Atualizar o repositório, executar configurar_perfis, reiniciar o servidor e sair/entrar com a conta correta antes de repetir a validação. O comando sincroniza grupos, mas não remove grupos extras nem altera is_superuser de contas existentes.
