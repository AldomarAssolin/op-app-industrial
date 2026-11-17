# Validação complementar local — issue #6

## Escopo e rastreabilidade

Em 17/11/2026, Manex definiu que o OP-APP permanece **somente local por enquanto**. Não há host HTTPS de piloto a aprovar nesta entrega. A implantação futura, a recuperação do banco efetivo e a autorização para dados reais estão bloqueadas pela [issue #16](https://github.com/AldomarAssolin/op-app-industrial/issues/16).

Checkout limpo criado a partir do repositório; base de aplicação `5227c81be174b3b1d50d5e4b86d300b4b9edb92e`, com os documentos da branch `docs/issue-6-aceitacao-local` (`f5b314067437afe8090548ca54bf40e15ac3b5b0`) e o novo módulo `apps/planejamento/test_aceitacao_http.py`. Código HTTP publicado no commit `d31eabf24acec4546750a4f3196076e80fd28bf4`; o run de CI da PR #15 identifica a revisão final.

Ambiente: Python 3.12.14, Django 5.2.19 e PostgreSQL 17.11. Banco de teste descartável; setores, trabalhadores, tarefas e contas inteiramente sintéticos. O banco e as contas do computador de Manex não foram acessados nesta rodada. A conexão com o navegador local não respondeu.

## Evidência executada

Os cinco testes complementares usam `LiveServerTestCase`, servidor HTTP real e cliente HTTP de biblioteca padrão. O login ocorre pela tela `/admin/login/`, com sessão e token CSRF reais. Não usam `force_login`, não desabilitam CSRF e não são classificados como testes manuais de navegador. O hasher rápido e cookies sem Secure são restritos ao teste HTTP local por `override_settings`; não alteram a configuração da aplicação.

| Cenário HTTP | Evidência e resultado |
| --- | --- |
| Consulta: criar, editar e excluir tarefas e alocações | Seis POSTs com CSRF válido retornaram 403; estado de trabalhadores, tarefas, histórico e alocações permaneceu idêntico. Inclui permissões individuais extras acidentais. |
| Líder: IDs de trabalhador ou tarefa de B | Quatro combinações, em cadastro individual e multidiário: erro de formulário, sem revelar os nomes de B e sem nenhuma alteração no banco. |
| Coordenador: criar pessoa de A | POST válido criou a pessoa no setor A. |
| Coordenador: transferir A → B ou reescrever origem B com destino A | Transferências rejeitadas; estado preservado. |
| CSRF local | POST de alocação sem token retornou 403, sem gravação. |
| Cookies e logout local | Sessão com HttpOnly e SameSite=Lax; logout invalidou a sessão. Reapresentar o cookie antigo redirecionou o quadro para login. |
| Exclusão | Alocação permitida removida; tentativa de excluir tarefa retornou 403 e preservou a tarefa. |

Resultado da suíte completa: **118 testes aprovados**, incluindo os cinco novos testes HTTP e os testes anteriores de integridade, concorrência e autorização. `manage.py check` sem problemas; migrações aplicadas, `makemigrations --check --dry-run` sem alterações e `migrate --check` aprovado. Dependências instaladas a partir de `requirements.txt`.

Reprodução em ambiente de desenvolvimento configurado com PostgreSQL e variáveis de `.env.example`:

```bash
python manage.py check
python manage.py migrate
python manage.py configurar_perfis
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py test -v 2 --noinput
```

Para executar apenas a cobertura HTTP complementar:

```bash
python manage.py test apps.planejamento.test_aceitacao_http -v 2 --noinput
```

O runner cria e destrói o banco de teste; o usuário PostgreSQL do ambiente de desenvolvimento precisa poder criar esse banco. Não executar com credenciais de produção nem apontar ferramentas de teste para o banco operacional.

## Relação com a aceitação anterior

O [relatório de 16/11](aceitacao-local-2026-11-16.md) permanece como evidência manual parcial, sem atribuir retroativamente um SHA ao checkout daquele dia. A rodada de 17/11 acrescenta cobertura HTTP automatizada para os cenários que não foram enviados manualmente no navegador. Não se declara que esses POSTs foram executados manualmente.

Em 17/11/2026, Manex aprovou expressamente o aceite por **evidências combinadas**: navegação manual de 16/11 mais os 118 testes, incluindo HTTP real de 17/11. Esse aceite substitui a repetição manual integral para o escopo somente local da #6. O encerramento fica condicionado à incorporação da PR #15 com CI e revisão aprovados.

O encerramento local, se aceito, não aprova HTTPS, infraestrutura, backup/restauração do banco efetivo ou uso empresarial com dados reais. Essas condições permanecem na #16. Os registros sintéticos criados no computador de Manex em 16/11 continuam preservados; os desta rodada existem somente no banco descartável dos testes.
