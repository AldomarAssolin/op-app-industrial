# Páginas públicas para o OAuth do OP-APP Backups

## Transição para a apresentação do produto — issue #23

O endereço específico da integração passa a ser
`https://industrial.manexlabs.dev/integracoes/backup/`. O aviso permanece em
`https://industrial.manexlabs.dev/privacidade/`, sem alteração de finalidade ou escopo.
A página do produto tem habilitação separada, `OP_APP_PRODUCT_HOME_ENABLED`, padrão
`False` para preservar a página inicial anterior durante a transição.

Fazer a mudança em duas etapas, depois de incorporar a entrega na versão apropriada:

1. Implantar o código mantendo `OP_APP_PRODUCT_HOME_ENABLED=False`, a flag existente
   `OP_APP_PUBLIC_PAGES_ENABLED=True` e o contato público válido. A raiz continua
   apresentando a integração, e o novo endereço fica disponível em paralelo.
2. Conferir os dois endereços da integração em janela anônima. No Google Auth Platform,
   atualizar a **Página inicial** do app OP-APP Backups para o endereço específico acima.
   Manter a política de privacidade atual e conferir o salvamento. Não mudar cliente,
   conta de armazenamento, escopos ou chaves.
3. Somente depois, definir `OP_APP_PRODUCT_HOME_ENABLED=True` e fazer novo deploy.
   Conferir a apresentação em `/`, o login e os links da integração no rodapé.

A raiz passa a tratar do planejamento industrial, sem explicação de backup em seu
conteúdo principal. A integração mantém sua apresentação própria e seu aviso; a página
do produto não é anunciada como uma política geral de privacidade do sistema.

Se a integração estiver desativada ou o contato for inválido, as páginas específicas
continuam retornando 404 e seus links não aparecem no rodapé. A apresentação do produto,
quando habilitada, continua disponível sem contato ou integração, e sem acesso ao banco.
Para voltar à apresentação anterior na raiz, desativar somente a nova flag; o endereço
específico da integração e a política continuam disponíveis conforme a configuração
anterior. Não devolver o Branding à raiz enquanto ela apresentar somente o produto.

Veja o [roteiro de validação da página](pagina-publica.md). As instruções abaixo são
o roteiro inicial da integração, preservado com o novo endereço já indicado na tabela.

Esta entrega é um rascunho para revisão do operador. A publicação está desativada por
padrão. Não inclui dados do banco, credenciais, endereços internos ou identificadores
dos backups. O e-mail de contato é definido no ambiente e fica visível publicamente
quando as páginas forem habilitadas.

## Antes de publicar

1. Revisar os textos em `apps/planejamento/templates/planejamento/publico/` e confirmar
   que descrevem as práticas efetivas do operador. O aviso trata da integração de
   backups, sem declarar conformidade jurídica ou aprovação pelo Google.
2. Escolher o e-mail de suporte que será publicado; usar um endereço monitorado.
3. Confirmar o uso de OAuth `drive.file` e rclone crypt, inclusive criptografia dos nomes.
4. Após aprovação e merge, configurar no serviço App do EasyPanel:
   `OP_APP_SUPPORT_EMAIL` com o e-mail público aprovado e
   `OP_APP_PUBLIC_PAGES_ENABLED=True`; fazer Deploy.
5. Conferir as duas páginas em janela anônima, sem login. Sem habilitação ou contato
   válido, ambas retornam 404. As páginas não consultam o banco nem expõem dados operacionais.

## Preenchimento no Google Auth Platform

| Campo | Valor após publicar e validar as páginas |
| --- | --- |
| Nome do app | OP-APP Backups |
| E-mail de suporte | E-mail monitorado aceito pelo Google, coerente com o contato público |
| Página inicial | https://industrial.manexlabs.dev/integracoes/backup/ |
| Política de Privacidade | https://industrial.manexlabs.dev/privacidade/ |
| Domínio autorizado | manexlabs.dev |

Conferir propriedade do domínio na conta/projeto Google quando exigido. A página inicial
explica a integração e vincula o aviso de privacidade. URLs ainda não implantadas não
devem ser informadas como páginas prontas. Publicar essas páginas não garante verificação
ou aceitação pelo Google.

Depois de completar Branding e conseguir publicar o aplicativo OAuth, renovar a
autorização do `opdrive` e validar novamente o acesso. O remote crypt permanece
configurado; não trocar suas senhas. A rotina recorrente de backups continua pendente.

Referências: [Branding](https://support.google.com/cloud/answer/15549049),
[verificação de marca](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification)
e [escopos do Drive](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).
