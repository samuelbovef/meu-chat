"""
Módulo de Gerenciamento de Conexões WebSocket.

Este arquivo contém a classe `ConnectionManager`, que atua como o controlador
de tráfego do sistema de chat. Ele gerencia as conexões ativas e fornece
métodos para enviar mensagens individuais ou em broadcast de forma tolerante a falhas.
"""

from fastapi import WebSocket


class ConnectionManager:
    """
    Gerenciador de conexões WebSocket.
    Mantém o controle de todos os clientes e atendentes (painéis) logados, 
    lidando com a aceitação, remoção e envio de mensagens via socket.
    """

    def __init__(self):
        """
        Inicializa o gerenciador criando uma lista vazia para armazenar
        as conexões ativas no momento.
        """
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """
        Aceita uma nova requisição de conexão WebSocket e a registra na 
        lista de conexões ativas (tráfego).
        
        Args:
            websocket (WebSocket): A instância de conexão requisitante.
        """
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """
        Remove uma conexão da lista ativa de forma segura.
        Chamado automaticamente quando um usuário fecha a aba do navegador 
        ou a conexão cai.
        
        Args:
            websocket (WebSocket): A instância de conexão a ser removida.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """
        Envia uma mensagem direta apenas para o sistema de um usuário específico.
        Permite rotear dados, comandos invisíveis ou atualizações de estado do sistema.
        
        Args:
            message (str): O conteúdo da mensagem (texto).
            websocket (WebSocket): A conexão alvo que receberá a mensagem.
        """
        try:
            await websocket.send_text(message)
        except RuntimeError:
            # Captura a exceção silenciosamente caso a conexão já tenha sido encerrada
            pass

    async def broadcast(self, message: str):
        """
        Envia uma mensagem para TODAS as conexões ativas simultaneamente.
        O envio segue o padrão de payload do sistema (ex: Sessão|Nome|Mensagem).
        O frontend, por sua vez, filtrará o que pertence ou não a ele.
        
        Args:
            message (str): A string contendo os dados empacotados.
        """
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except RuntimeError:
                # Evita que o loop quebre e o servidor caia se o navegador 
                # de um dos clientes da lista perder a internet repentinamente.
                pass


# ==========================================
# INSTÂNCIA GLOBAL DO GERENCIADOR
# ==========================================
# Instanciamos o gerenciador principal aqui para que o `main.py` 
# importe a mesma instância mantendo o estado global do tráfego.
manager = ConnectionManager()