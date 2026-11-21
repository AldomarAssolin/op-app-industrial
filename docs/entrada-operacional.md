# Entrada operacional — issue #24

## Fluxo

Os botões de acesso na página pública agora levam a `/conta/entrar/`. O login utiliza
as contas e sessões existentes do Django, sem novo cadastro ou alteração de permissões.
Sem destino solicitado, a entrada é `/app/`. Um `next` interno válido é preservado;
destinos externos e HTTP a partir de login HTTPS são descartados pelo LoginView nativo.
O acesso direto ao Admin mantém seu próprio login e destino de configuração.

`/app/` e o quadro semanal compartilham navegação, identificação da sessão e saída por
POST com CSRF em `/conta/sair/`. A saída encerra a mesma sessão utilizada pelo Admin.
O quadro anônimo passa a redirecionar para o login operacional.

## Ações

As ações derivam das permissões atuais e dos setores autorizados, usando a política
compartilhada existente. Não há contadores, tarefas ou nomes de outros setores.
Sem setor, a página orienta procurar o responsável pela operação. Sem permissões,
orienta conferir o acesso. Não modifica grupos, usuários, permissões ou vínculos.

| Perfil configurado | Semana | Planejar | Equipe |
| --- | --- | --- | --- |
| Consulta | Consultar | Sem ação de gravação; consulta de tarefas | Consultar |
| Líder | Consultar | Alocações e tarefas no Admin | Consultar, sem cadastro |
| Coordenador | Consultar | Alocações e tarefas no Admin | Consultar e cadastrar conforme permissão |
| Administrador | Consultar todos os setores | Alocações e tarefas no Admin | Consultar e cadastrar conforme permissão |

Os destinos do Admin exigem conta staff e continuam protegidos pelo backend. Uma conta
sem staff pode consultar o quadro se tiver a permissão de leitura e setor; não recebe
atalhos para o Admin. Consulta com permissão avulsa de gravação continua sem ação de
gravação conforme a política existente. Os atalhos não substituem verificações nas URLs.

Nesta entrega, Planejar e Equipe ainda abrem telas existentes do Admin, indicadas nos
rótulos. Fluxos operacionais próprios serão entregas posteriores. O acesso de configuração
ao Admin permanece disponível para contas staff, sujeito às permissões existentes.

## Validação

Testes cobrem login e retorno interno, bloqueio de destino externo/downgrade, senha
incorreta e conta inativa, ações por perfil, conta sem staff/permissões/setor, isolamento
de nomes de setores, política de Consulta, CSRF e encerramento de sessão. A suíte
existente continua cobrindo autorização direta nos destinos.

Roteiro de aceite visual e de uso (registrar o resultado após executar):

- Entrar pelo botão público, conferir `/app/`, usuário e setores permitidos.
- Abrir Ver semana e voltar pelo Início; conferir a mesma navegação.
- Como Consulta, não encontrar Planejar nem Cadastrar trabalhador.
- Como Líder, consultar equipe sem atalho de cadastro; como Coordenador, conferir cadastro.
- Abrir atalhos e conferir que o destino está claramente identificado como Admin.
- Conferir conta sem setor e orientação para o responsável.
- Em tela estreita e com zoom, conferir textos, links e navegação sem corte; no quadro,
  somente a tabela pode necessitar rolagem horizontal.
- Usar Tab/Shift+Tab, conferir foco visível e link Ir para o conteúdo.
- Sair e confirmar que `/app/` e o quadro voltam a exigir login.

Não há migração nem nova variável de ambiente. Implantar o código revisado e conferir os
fluxos. Para reversão de código, usar a imagem anterior aprovada conforme o roteiro de
operação; a base de dados e a configuração das páginas públicas não mudam nesta entrega.
