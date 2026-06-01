"""
Módulo de Modelos do Banco de Dados (ORM).

Este arquivo define a estrutura das tabelas no banco de dados utilizando
o SQLAlchemy. Cada classe representa uma tabela, facilitando a manipulação
e a consulta dos dados através de objetos Python.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime

from .database import Base


# ==========================================
# MODELO DE MENSAGENS (HISTÓRICO DO CHAT)
# ==========================================
class MessageDB(Base):
    """
    Representa a tabela de histórico de mensagens.
    Armazena todas as mensagens trocadas entre clientes, atendentes e o sistema.
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String(50), index=True)  # Identificador de quem enviou (Cliente, Atendente, Sistema)
    content = Column(Text)                   # Conteúdo completo da mensagem
    timestamp = Column(DateTime, default=datetime.utcnow)


# ==========================================
# MODELO DE ATENDENTES E USUÁRIOS DO SISTEMA
# ==========================================
class AttendantDB(Base):
    """
    Representa a tabela de usuários do painel (atendentes e administradores/master).
    Armazena as credenciais de acesso e a função (role) de cada usuário.
    """
    __tablename__ = "attendants"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    hashed_password = Column(String(100))            # Senha criptografada (hash bcrypt)
    role = Column(String(20), default="atendente")   # Papel no sistema: 'atendente' ou 'master'


# ==========================================
# MODELO DE TICKETS (ATENDIMENTOS)
# ==========================================
class TicketDB(Base):
    """
    Representa a tabela de chamados (tickets).
    Armazena os dados dos clientes, status do atendimento, quem atendeu 
    e as métricas de qualidade (CSAT, TMA, Resolução).
    """
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, index=True)  # ID único da sessão do WebSocket
    nome = Column(String(100))
    email = Column(String(100))
    whats = Column(String(20))
    protocolo = Column(String(50))
    status = Column(String(20), default="ativo")               # Status do chat: 'ativo' ou 'encerrado'
    atendente = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # ==========================================
    # MÉTRICAS E INDICADORES (PAINEL MASTER)
    # ==========================================
    closed_at = Column(DateTime, nullable=True)    # Data e hora do encerramento para calcular TMA
    avaliacao = Column(Integer, nullable=True)     # Nota de avaliação do cliente (CSAT: 1 a 5)
    resolvido = Column(String(10), nullable=True)  # Resposta do cliente sobre a resolução: "sim" ou "nao"