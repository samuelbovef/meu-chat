"""
Módulo de Configuração do Banco de Dados.

Este arquivo é responsável por configurar a conexão com o banco de dados
utilizando o SQLAlchemy. Ele define a URL do banco, inicializa o motor (engine)
de conexão, cria a fábrica de sessões e estabelece a classe base para os modelos ORM.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# ==========================================
# CONFIGURAÇÃO DA URL DO BANCO DE DADOS
# ==========================================
# Busca a URL do banco global (Supabase) configurada no Render.
# Se estiver rodando localmente no seu PC sem a variável, usa o SQLite como plano B.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chat_history.db")

# Correção de compatibilidade: O SQLAlchemy exige "postgresql://" em vez de "postgres://"
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ==========================================
# CRIAÇÃO DO MOTOR (ENGINE)
# ==========================================
# O parâmetro 'check_same_thread' só é compatível com SQLite. 
# Para o PostgreSQL (Supabase), criamos o engine limpo.
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

# ==========================================
# FÁBRICA DE SESSÕES (SESSION MAKER)
# ==========================================
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ==========================================
# CLASSE BASE PARA MODELOS ORM
# ==========================================
Base = declarative_base()
