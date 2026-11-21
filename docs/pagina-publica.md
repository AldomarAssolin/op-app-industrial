# Apresentação pública do produto — issue #23

## Entrega

A raiz apresenta o planejamento operacional industrial: equipe, tarefas, alocações e
consulta semanal. O exemplo é fictício, estático e não consulta o banco. As chamadas
levam ao login existente; não há cadastro autônomo, cobrança, DEMO ou promessa de gestão
de horas/capacidade. O Admin e a autorização operacional permanecem os mesmos.

O layout usa Django Templates, fontes do sistema e CSS local incorporado no template,
sem scripts ou serviços de rastreamento. O quadro ilustrativo admite rolagem horizontal
com região nomeada e foco por teclado em telas estreitas. Há link para pular a navegação,
hierarquia de títulos, legenda e cabeçalhos de tabela, e indicação visível de foco.

## Configuração e compatibilidade

| Configuração | Raiz `/` | `/integracoes/backup/` e `/privacidade/` |
| --- | --- | --- |
| Nova flag desativada; integração habilitada e contato válido | Página anterior da integração | Disponíveis |
| Nova flag desativada; integração desativada ou contato inválido | 404, como antes | 404 |
| `OP_APP_PRODUCT_HOME_ENABLED=True`; integração habilitada e contato válido | Apresentação do produto, links específicos no rodapé | Disponíveis |
| `OP_APP_PRODUCT_HOME_ENABLED=True`; integração desativada ou contato inválido | Apresentação do produto sem links/contato da integração | 404 |

Nova flag padrão: `False`. A flag existente `OP_APP_PUBLIC_PAGES_ENABLED` continua
controlando a publicação da integração e a exigência de contato válido. Não remover
essa configuração por confundi-la com a nova página do produto.

Antes de trocar a raiz, seguir a [transição de Branding em duas etapas](oauth-branding.md).
O novo endereço existe para preservar a descrição da integração e suas referências.

## Validação local executada

Em 20/11/2026: 12 testes de páginas públicas e deploy aprovados, sem banco, usando
SimpleTestCase. Cobrem a matriz de habilitação, contato inválido, preservação do legado,
conteúdo específico da integração, ligações, ausência de cookies de sessão/CSRF nas
páginas públicas, métodos GET/HEAD e rejeição de POST, e quadro operacional protegido.
Não representam teste visual nem execução no host de produção.

```bash
python manage.py collectstatic --noinput
python manage.py test apps.planejamento.test_paginas_publicas apps.planejamento.test_deploy -v 2
```

O navegador conectado não conseguiu acessar a prévia neste ambiente. Conferência visual,
navegação por teclado e comportamento responsivo permanecem pendentes; não fechar a issue
somente pelo resultado dos testes de requisição.

## Aceite visual e funcional

- [ ] Conferir desktop, tablet e celular (por exemplo, larguras 1440, 1024, 768 e 390 px), inclusive zoom: sem corte de texto ou rolagem horizontal da página; apenas o quadro ilustrativo pode rolar.
- [ ] Conferir leitura, contraste, rótulo de exemplo fictício e legibilidade do quadro.
- [ ] Usar Tab/Shift+Tab: link de pular navegação, links/botões, região do quadro e rodapé devem ter foco visível e ordem coerente; rolar o quadro pelo teclado.
- [ ] Acionar Como funciona e conferir o destino; os botões Entrar devem alcançar o login existente.
- [ ] Conferir `/integracoes/backup/` e `/privacidade/`, conteúdo e links, antes e depois de habilitar a nova raiz.
- [ ] Conferir anonimato do quadro operacional e comportamento das flags conforme a tabela.
- [ ] Registrar commit/versão e resultados, sem dados, credenciais ou arquivos internos.

## Relação com a versão inicial

A #22 acompanha a publicação do MVP v1.0.0. Esta entrega pertence à evolução de UX
proposta para v1.1.0; sua branch e PR devem permanecer separadas do commit selecionado
para a versão inicial. Não implantar ou incorporar esta evolução inadvertidamente antes
de identificar o marco da release inicial.
