"""
Módulo de Configuração do Banco de Dados.

Este arquivo é responsável por configurar a conexão com o banco de dados
utilizando o SQLAlchemy. Ele define a URL do banco, inicializa o motor (engine)
de conexão, cria a fábrica de sessões e estabelece a classe base para os modelos ORM.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# ==========================================
# CONFIGURAÇÃO DA URL DO BANCO DE DADOS
# ==========================================
# Define o banco de dados SQLite local.
# O arquivo 'chat_history.db' será criado automaticamente na raiz do projeto.
SQLALCHEMY_DATABASE_URL = "sqlite:///./chat_history.db"

# ==========================================
# CRIAÇÃO DO MOTOR (ENGINE)
# ==========================================
# O 'engine' gerencia a conexão física com o banco de dados.
# O parâmetro 'check_same_thread=False' é necessário apenas para o SQLite,
# permitindo que múltiplas threads compartilhem a mesma conexão (muito útil em APIs).
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# ==========================================
# FÁBRICA DE SESSÕES (SESSION MAKER)
# ==========================================
# 'SessionLocal' é uma classe fábrica de sessões. Cada instância criada a partir
# dela será uma sessão de banco de dados independente.
# autocommit=False e autoflush=False garantem que o desenvolvedor tenha controle
# total e explícito sobre quando salvar os dados (commit).
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ==========================================
# CLASSE BASE PARA MODELOS ORM
# ==========================================
# 'Base' é a classe raiz que todos os modelos de banco de dados (tabelas) irão herdar.
# O SQLAlchemy usará essa base para mapear as classes Python para tabelas no banco de dados.
Base = declarative_base()