# Registro da implantação — 17/11/2026

Registro das ações acompanhadas com Manex em 17/11/2026, considerando o horário de Brasília. Relacionado à [issue #16](https://github.com/AldomarAssolin/op-app-industrial/issues/16), que permanece aberta.

## Origem e limites das evidências

Os resultados do ambiente hospedado abaixo foram executados e informados por Manex durante o acompanhamento. Não representam inspeção independente do servidor pelo assistente. Não são publicados segredos, tokens, dumps, caminhos de armazenamento ou endereços internos.

A publicação do aplicativo OAuth em Produção é uma configuração da integração de backup; não equivale à verificação de marca pelo Google nem à autorização para utilizar dados reais no OP-APP.

## Entregas incorporadas ao repositório

| Entrega | Registro |
| --- | --- |
| Aceite local de segurança e perfis da issue #6 | PR #15 incorporada; aceite combinado de navegador e testes HTTP, com 118 testes na execução registrada daquela etapa. Issue #6 encerrada |
| Preparação para hospedagem | PR #18 incorporada: Dockerfile, Gunicorn, WhiteNoise, coleta de estáticos, usuário sem privilégios, `/health/`, configuração explícita de proxy e guia EasyPanel |
| Páginas públicas para Branding | PR #19 incorporada: página inicial e privacidade opcionais, habilitadas por ambiente e contato válido; texto e contato aprovados por Manex |

Referência da `main` ao registrar estas ações: `b915f656fd48951b645e1d93cbaa6574483745be`. Essa referência não comprova, por si só, qual imagem estava executando no servidor.

## Validações no ambiente hospedado

| Item | Resultado informado |
| --- | --- |
| Aplicação e domínio | Aplicação publicada em `https://industrial.manexlabs.dev`; healthcheck externo respondeu HTTP 200 e Admin anônimo redirecionou ao login |
| Processo HTTP | Gunicorn iniciou e a sonda interna respondeu HTTP 200 |
| Conectividade do proxy | Houve HTTP 502 durante a configuração; após ajuste de descoberta dos serviços no painel, acesso externo voltou a funcionar e persistiu no novo deploy conferido pelo usuário |
| Banco | Conta da aplicação conferida sem superusuário e sem permissões de criar bancos ou papéis; migrações e configuração inicial executadas |
| Interface | Login e estilos do Admin conferidos no PC e no celular |
| Cookies | Atributos de segurança de sessão e CSRF conferidos pelo usuário, incluindo SameSite=Lax |
| CSRF | POST de teste sem token para o login retornou HTTP 403 |
| Proteção da consulta | Quadro semanal sem sessão autenticada retornou a tela de login |
| Verificação Django | `check --deploy` executado; único aviso apresentado: `security.W004`, relativo a HSTS ainda não configurado |

`/health/` verifica o processo HTTP, não o banco. As verificações acima não substituem toda a matriz de autorização no host efetivo. HSTS continua pendente de decisão e configuração; o aviso não foi resolvido nem silenciado.

## Backup e recuperação

| Etapa | Resultado informado |
| --- | --- |
| Backup lógico | Dump PostgreSQL em formato custom gerado, com aproximadamente 57 KB; índice legível por `pg_restore --list` |
| Restauração | Dump restaurado com sucesso em outro banco, sem sobrescrever a origem |
| Migrações da cópia | `migrate --check` aprovado usando a cópia restaurada |
| Comparação de conteúdo | Contagens iguais nas dez tabelas conferidas: um usuário, quatro grupos e nenhum registro nas demais tabelas avaliadas |
| Cópia externa | rclone instalado no PC e na VPS; acesso ao Google Drive autorizado com cliente OAuth próprio e escopo `drive.file` |
| Criptografia | Remoto crypt configurado para conteúdo e nomes; upload e download de validação realizados |
| Integridade da cópia externa | SHA-256 do arquivo original e do arquivo baixado e descriptografado idênticos, conforme confirmação de Manex |

O ensaio comprovou a recuperação da base inicial. Não houve validação de recuperação de dados operacionais preenchidos. Não foi registrado tempo de recuperação, portanto não há RTO medido.

## OAuth e Branding

- Texto público e contato de suporte aprovados por Manex.
- Acesso ao projeto existente concedido à conta de suporte; e-mail salvo no Branding, conforme confirmação do usuário.
- Aplicativo OAuth alterado de Testando para **Em Produção**, conforme confirmação final de Manex.
- A renovação da autorização do rclone após essa mudança ficou para a próxima sessão.

O guia [oauth-branding.md](oauth-branding.md) descreve a configuração das páginas. Ainda é necessário registrar explicitamente a conferência anônima das duas URLs após o deploy; a publicação do OAuth não é evidência suficiente dessa conferência.

## Retomada e pendências

1. Renovar a autorização do remoto Drive existente na VPS com `rclone config reconnect opdrive:`. No fluxo sem navegador, executar no PC o comando `rclone authorize ...` completo fornecido pela VPS e transferir o token diretamente para ela, sem publicar a credencial. Manter a mesma conta de armazenamento e as chaves do crypt.
2. Conferir acesso ao backup pelo remoto criptografado com `rclone lsf opbackup:`; confirmar leitura após a renovação.
3. Confirmar que as senhas e o salt do crypt estão guardados de forma recuperável fora da VPS. Acesso ao Drive sozinho não permite descriptografar a cópia.
4. Definir frequência, retenção, responsável, perda tolerável de dados e tempo esperado de recuperação. Implementar a rotina e a sinalização de falhas; o backup atual é manual.
5. Consolidar o roteiro reproduzível de backup/restauração e ensaiar recuperação com conteúdo operacional sintético e medição de tempo.
6. Decidir o tratamento do aviso de HSTS e completar as verificações restantes da matriz no ambiente real, incluindo perfis e setores, versão efetivamente publicada e procedimento de reversão.
7. Atualizar o estado geral do README e revisar a PR #17, cujo plano antecede a implantação. Não incorporar como atual a afirmação de que o ambiente ainda não foi implantado.

Nenhuma dessas pendências deve ser marcada como concluída apenas por constar neste registro. A issue #16 permanece aberta e o uso de dados reais depende de autorização separada.
