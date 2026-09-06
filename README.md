# Meu Chat

Um sistema de atendimento ao cliente em tempo real (Helpdesk/CRM) baseado em WebSockets, desenvolvido para ser leve, rápido e de fácil integração.

## Sobre o Projeto

O "Meu Chat" foi idealizado e desenvolvido com o propósito de auxiliar pequenos empreendedores e profissionais autônomos a profissionalizarem o atendimento aos seus clientes sem a necessidade de arcar com os altos custos de plataformas de chat proprietárias e pagas. 

Este projeto foi construído com foco na eficiência e está sendo disponibilizado para a comunidade open-source. O objetivo é que ele seja uma ferramenta útil e acessível. Incentivamos outros desenvolvedores a utilizarem, estudarem e, principalmente, contribuírem com melhorias, novas funcionalidades e correções de segurança para que o projeto evolua continuamente.

## Estrutura do Repositório

O projeto adota uma arquitetura modular, dividida nos seguintes diretórios principais:

* **backend/**: API RESTful e servidor de WebSockets desenvolvidos em Python (FastAPI). Gerencia a autenticação, o roteamento de mensagens, persistência em banco de dados (híbrido PostgreSQL/SQLite via SQLAlchemy) e processamento de métricas.
* **dashboard/**: Interface do painel de controle dos atendentes e administradores (Master). Construído com HTML, CSS e Vanilla JavaScript, focando em performance e ausência de dependências pesadas no frontend.
* **widget/**: Código do chat que será embutido no site do cliente final. Composto por arquivos estáticos leves projetados para não impactar o tempo de carregamento da página hospedeira.

## Principais Funcionalidades

* **Comunicação em Tempo Real**: Chat bidirecional de alta performance utilizando WebSockets.
* **Fila de Atendimento Inteligente**: Distribuição automatizada de chamados via algoritmo Round-Robin.
* **Painel CRM Integrado**: Visualização de dados do cliente, histórico completo e inserção de notas internas ocultas.
* **Métricas de Qualidade**: Cálculo de Tempo Médio de Atendimento (TMA), Taxa de Resolução e Satisfação do Cliente (CSAT) renderizados em gráficos dinâmicos.
* **Alertas em Segundo Plano**: Sistema de notificações visuais (Push API) e alertas sonoros que detectam quando a aba está minimizada ou em segundo plano.
* **Auditoria e Exportação**: Monitoramento de chats em tempo real (perfil Master) e exportação de relatórios estruturados em formato CSV.
* **Suporte a Anexos**: Envio e recebimento de imagens e arquivos PDF convertidos em Base64, limitados a 1MB.

* ## Como Executar o Projeto

A maneira mais recomendada de executar a aplicação em ambiente de desenvolvimento é através do Docker. 

1. Certifique-se de ter o Docker e o Docker Compose instalados em sua máquina.
2. Clone este repositório para o seu ambiente local.
3. Renomeie o arquivo `.env.example` para `.env` e defina uma chave segura para a variável `SECRET_KEY`, além de configurar a `REGISTRATION_MASTER_KEY` desejada.
4. Na raiz do projeto, execute o comando:
   
    ```bash
    docker-compose up -d --build

O servidor backend e os serviços de WebSockets estarão operando na porta 8000.

## Criação de Usuários (Atendentes e Master)

Para garantir a segurança do ecossistema, a aplicação não possui uma tela pública de registro de funcionários. O cadastro inicial de usuários deve ser realizado diretamente pela documentação interativa da API (Swagger UI).

1. Com o servidor rodando, acesse a rota de documentação pelo navegador:
   `http://localhost:8000/docs`
2. Localize o endpoint de registro (`POST /register`).
3. Clique em "Try it out".
4. Preencha os parâmetros requeridos no formulário:
   * `username`: Nome de usuário desejado para o funcionário.
   * `password`: Senha de acesso.
   * `role`: Defina como `atendente` para uso padrão de operação, ou `master` para liberar privilégios administrativos de auditoria e métricas.
   * `master_key`: Informe a chave de validação correspondente à variável `REGISTRATION_MASTER_KEY` definida no seu arquivo de ambiente.
5. Execute a requisição para persistir o usuário no banco de dados.

Após o retorno de sucesso do servidor, o acesso ao painel `dashboard` poderá ser feito utilizando as credenciais recém-criadas.

## Contribuição

Contribuições são extremamente bem-vindas. Se você deseja ajudar a melhorar o "Meu Chat", siga os passos abaixo:

1. Faça um Fork do projeto.
2. Crie uma Branch para sua feature (`git checkout -b feature/NovaFuncionalidade`).
3. Faça o Commit de suas mudanças (`git commit -m 'Adicionando uma nova funcionalidade'`).
4. Faça o Push para a Branch (`git push origin feature/NovaFuncionalidade`).
5. Abre um Pull Request.

Certifique-se de seguir os padrões de código estabelecidos e manter a estabilidade do sistema ao propor alterações.

## Suporte e Serviços

Precisou de ajuda com dúvidas, erros ou suporte? Acesse a Central para abrir um protocolo de atendimento.

<div align="center">

[![Central de Atendimento](https://img.shields.io/badge/ACESSAR_CENTRAL_DE_ATENDIMENTO-24292e?style=for-the-badge&logo=github&logoColor=white)](https://github.com/samuelbovef/suporte)

</div>

---

Distribuído sob a licença **MIT**. É permitida a utilização, modificação e distribuição comercial, desde que mantidos os avisos originais.
