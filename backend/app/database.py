"""
Módulo de Configuração do Banco de Dados.

Este arquivo é responsável por configurar a conexão com o banco de dados
utilizando o SQLAlchemy. Ele define a URL do banco, inicializa o motor (engine)
de conexão, cria a fábrica de sessões e estabelece a classe base para os modelos ORM.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ==========================================
# CONFIGURAÇÃO DA URL DO BANCO DE DADOS
# ==========================================
# Busca a URL do banco global configurada nas variáveis de ambiente.
# Caso não exista (ex: ambiente de desenvolvimento local), utiliza SQLite como fallback.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chat_history.db")

# Correção de compatibilidade: SQLAlchemy (versões 1.4+) exige "postgresql://" em vez de "postgres://"
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ==========================================
# CRIAÇÃO DO MOTOR (ENGINE)
# ==========================================
# O parâmetro 'check_same_thread' é necessário exclusivamente para o SQLite.
# Para bancos de dados baseados em servidor (ex: PostgreSQL), o engine é instanciado de forma padrão.
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

# ==========================================
# FÁBRICA DE SESSÕES E CLASSE BASE
# ==========================================
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()
