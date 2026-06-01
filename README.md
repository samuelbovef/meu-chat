# Meu Chat

Um sistema de atendimento ao cliente em tempo real (Helpdesk/CRM) baseado em WebSockets, desenvolvido para ser leve, rápido e de fácil integração.

## Sobre o Projeto

O "Meu Chat" foi idealizado e desenvolvido com o propósito de auxiliar pequenos empreendedores e profissionais autônomos a profissionalizarem o atendimento aos seus clientes sem a necessidade de arcar com os altos custos de plataformas de chat proprietárias e pagas. 

Este projeto foi construído com foco na eficiência e está sendo disponibilizado para a comunidade open-source. O objetivo é que ele seja uma ferramenta útil e acessível. Incentivamos outros desenvolvedores a utilizarem, estudarem e, principalmente, contribuírem com melhorias, novas funcionalidades e correções de segurança para que o projeto evolua continuamente.

## Estrutura do Repositório

O projeto adota uma arquitetura modular, dividida nos seguintes diretórios principais:

* **backend/**: Contém a API RESTful e o servidor de WebSockets desenvolvidos em Python (FastAPI). Gerencia a autenticação, o roteamento de mensagens, persistência em banco de dados (SQLite via SQLAlchemy) e geração de métricas.
* **dashboard/**: Contém a interface do painel de controle dos atendentes e administradores (Master). Construído com HTML, CSS e Vanilla JavaScript, focando em performance e ausência de dependências pesadas no frontend.
* **widget/**: Contém o código do chat que será embutido no site do cliente final. É composto por arquivos estáticos leves projetados para não impactar o tempo de carregamento da página hospedeira.

## Principais Funcionalidades

* **Comunicação em Tempo Real**: Chat bidirecional utilizando WebSockets.
* **Fila de Atendimento Inteligente**: Distribuição de chamados via algoritmo Round-Robin.
* **Painel CRM Integrado**: Visualização de dados do cliente, histórico e inserção de notas internas.
* **Métricas de Qualidade**: Cálculo de Tempo Médio de Atendimento (TMA), Taxa de Resolução no Primeiro Contato (FCR) e Satisfação do Cliente (CSAT).
* **Auditoria e Exportação**: Monitoramento de chats em tempo real (para perfil Master) e exportação de dados estruturados em CSV.
* **Suporte a Anexos**: Envio e recebimento de imagens e arquivos PDF.

## Como Executar o Projeto

A maneira mais recomendada de executar a aplicação é através do Docker. 

1. Certifique-se de ter o Docker e o Docker Compose instalados.
2. Clone este repositório.
3. Renomeie o arquivo `.env.example` para `.env` e defina uma chave segura para a variável `SECRET_KEY`.
4. Na raiz do projeto, execute o comando:

    docker-compose up -d --build

O servidor backend e os WebSockets estarão operando na porta `8000`.

## Criação de Usuários (Atendentes e Master)

Para garantir a segurança, a aplicação não possui uma tela pública de registro de funcionários. O cadastro inicial de usuários deve ser realizado diretamente pela documentação interativa da API (Swagger UI).

1. Com o servidor rodando, acesse a rota de documentação pelo navegador:
   `http://localhost:8000/docs`
2. Localize o endpoint de registro (`POST /register`).
3. Clique em "Try it out".
4. Preencha os parâmetros requeridos:
   * `username`: Nome de usuário.
   * `password`: Senha de acesso.
   * `role`: Defina como `atendente` para uso padrão, ou `master` para ter privilégios de auditoria e métricas.
5. Execute a requisição para cadastrar o usuário no banco de dados.

Após o cadastro, o acesso ao painel `dashboard` pode ser feito utilizando as credenciais recém-criadas.

## Contribuição

Contribuições são extremamente bem-vindas. Se você deseja ajudar a melhorar o "Meu Chat", siga os passos abaixo:

1. Faça um Fork do projeto.
2. Crie uma Branch para sua feature (`git checkout -b feature/NovaFuncionalidade`).
3. Faça o Commit de suas mudanças (`git commit -m 'Adicionando uma nova funcionalidade'`).
4. Faça o Push para a Branch (`git push origin feature/NovaFuncionalidade`).
5. Abra um Pull Request.

Certifique-se de seguir os padrões de código e manter a estabilidade do sistema ao propor alterações.

## Licença

Este projeto é distribuído sob a licença MIT.

