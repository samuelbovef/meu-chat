"""
Módulo Principal da API (Servidor de Chat Profissional com CRM).

Este arquivo gerencia:
- Inicialização do servidor FastAPI.
- Autenticação e registro de atendentes baseada em JWT.
- Geração de métricas e exportação de relatórios (CSV).
- Gerenciamento de conexões em tempo real via WebSockets.
- Regras de negócio de fila (Round-Robin) e transferência de chats.
"""

import csv
import io
import os
import random
from datetime import datetime, timedelta

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import (
    Depends, FastAPI, HTTPException, WebSocket, 
    WebSocketDisconnect, status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Importações locais
from .database import Base, SessionLocal, engine
from .models import AttendantDB, MessageDB, TicketDB
from .websocket import manager

# ==========================================
# CONFIGURAÇÃO DO AMBIENTE E BANCO DE DADOS
# ==========================================
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "chave_insegura_fallback")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# Cria as tabelas no banco de dados, caso não existam
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Servidor de Chat Profissional com CRM",
    docs_url=None if os.getenv("DOCS_URL") == "None" else "/docs",
    redoc_url=None if os.getenv("REDOC_URL") == "None" else "/redoc"
)

# ==========================================
# CONFIGURAÇÃO DE SEGURANÇA E CORS
# ==========================================
origens_raw = os.getenv("ALLOWED_ORIGINS")
ORIGENS_PERMITIDAS = [origem.strip() for origem in origens_raw.split(",")] if origens_raw else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENS_PERMITIDAS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# ESTADOS GLOBAIS EM MEMÓRIA
# ==========================================
active_tickets = {}      # Dicionário de tickets em andamento: {session_id: {dados_do_ticket}}
online_attendants = []   # Lista de nomes de atendentes conectados no momento
connected_users = {}     # Mapeamento de WebSockets conectados: {ws: {"session_id": sid, "role": role}}
round_robin_index = 0    # Índice para controle da distribuição de chamados na fila


# ==========================================
# DEPENDÊNCIAS E EVENTOS DE INICIALIZAÇÃO
# ==========================================
def get_db():
    """Gera uma sessão de banco de dados para a requisição e a fecha ao final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    """Evento executado ao iniciar o servidor para restaurar tickets ativos na memória."""
    db = SessionLocal()
    try:
        active_db_tickets = db.query(TicketDB).filter(TicketDB.status == "ativo").all()
        for t in active_db_tickets:
            active_tickets[t.session_id] = {
                "nome": t.nome, 
                "protocolo": t.protocolo, 
                "email": t.email, 
                "whats": t.whats, 
                "status": t.status, 
                "atendente": t.atendente, 
                "protocolo_informado": True
            }
    finally:
        db.close()


def save_or_update_ticket(db: Session, session_id: str, dados: dict):
    """Cria ou atualiza as informações de um ticket no banco de dados."""
    ticket = db.query(TicketDB).filter(TicketDB.session_id == session_id).first()
    
    if not ticket:
        ticket = TicketDB(
            session_id=session_id, 
            nome=dados["nome"], 
            email=dados["email"],
            whats=dados["whats"], 
            protocolo=dados["protocolo"],
            status=dados["status"], 
            atendente=dados["atendente"]
        )
        db.add(ticket)
    else:
        ticket.status = dados["status"]
        ticket.atendente = dados["atendente"]
        # Marca a hora exata do encerramento para calcular o TMA (Tempo Médio de Atendimento)
        if dados["status"] == "encerrado" and not ticket.closed_at:
            ticket.closed_at = datetime.utcnow()
            
    db.commit()


# ==========================================
# AUTENTICAÇÃO E REGISTRO
# ==========================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha fornecida corresponde ao hash salvo."""
    password_bytes = plain_password.encode('utf-8')
    hashed_password_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_password_bytes)


def get_password_hash(password: str) -> str:
    """Gera o hash seguro para uma nova senha."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt)
    return hashed_password.decode('utf-8')


def create_access_token(data: dict) -> str:
    """Cria um token JWT para o usuário com expiração de 8 horas."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=8)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@app.post("/register")
def register_attendant(
    username: str, 
    password: str, 
    role: str = "atendente", 
    master_key: str = None, 
    db: Session = Depends(get_db)
):
    """Registra novos atendentes com validação dinâmica via chave mestra."""
    chave_verdadeira = os.getenv("REGISTRATION_MASTER_KEY")
    
    if master_key != chave_verdadeira:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Acesso proibido. Chave mestra inválida."
        )

    db_user = db.query(AttendantDB).filter(AttendantDB.username == username).first()
    if db_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário já existe")
        
    hashed_pwd = get_password_hash(password)
    new_user = AttendantDB(username=username, hashed_password=hashed_pwd, role=role)
    db.add(new_user)
    db.commit()
    
    return {"message": f"Usuário {username} ({role}) cadastrado com sucesso!"}


@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Rota de autenticação que retorna o token JWT."""
    user = db.query(AttendantDB).filter(AttendantDB.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário ou senha incorretos")
        
    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer", "role": user.role}


# ==========================================
# ROTAS DA API: FEEDBACK E MÉTRICAS
# ==========================================
class FeedbackModel(BaseModel):
    """Modelo de dados para receber a avaliação do cliente."""
    avaliacao: int
    resolvido: str


@app.post("/api/feedback/{session_id}")
def save_feedback(session_id: str, feedback: FeedbackModel, db: Session = Depends(get_db)):
    """Salva a nota (CSAT) e a confirmação de resolução enviada pelo cliente."""
    ticket = db.query(TicketDB).filter(TicketDB.session_id == session_id).first()
    if ticket:
        ticket.avaliacao = feedback.avaliacao
        ticket.resolvido = feedback.resolvido
        db.commit()
        return {"msg": "Feedback salvo com sucesso"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket não encontrado")


@app.get("/api/dados-painel")
def get_metrics(token: str, db: Session = Depends(get_db)):
    """Calcula e retorna as métricas de atendimento. Acesso restrito aos administradores (Master)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "master":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        
    tickets = db.query(TicketDB).all()
    total_atendimentos = len(tickets)
    
    tma_total = 0
    tma_count = 0
    resolvidos = 0
    avaliacoes = 0
    soma_notas = 0

    for t in tickets:
        # Calcula o Tempo Médio de Atendimento (TMA)
        if t.closed_at and t.created_at:
            diff = (t.closed_at - t.created_at).total_seconds() / 60.0
            tma_total += diff
            tma_count += 1
            
        if t.resolvido == "sim":
            resolvidos += 1
            
        if t.avaliacao:
            soma_notas += t.avaliacao
            avaliacoes += 1
            
    tma = round(tma_total / tma_count, 1) if tma_count > 0 else 0
    taxa_resolucao = round((resolvidos / total_atendimentos) * 100, 1) if total_atendimentos > 0 else 0
    csat = round(soma_notas / avaliacoes, 1) if avaliacoes > 0 else 0

    return {
        "total_atendimentos": total_atendimentos,
        "tma_minutos": tma,
        "taxa_resolucao": taxa_resolucao,
        "csat": csat
    }


# ==========================================
# ROTAS DA API: EXPORTAÇÃO E HISTÓRICO
# ==========================================
@app.get("/api/export/clients")
def export_clients(token: str, db: Session = Depends(get_db)):
    """Exporta a base de tickets/clientes em formato CSV. Acesso restrito."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "master":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        
    tickets = db.query(TicketDB).all()
    output = io.StringIO()
    output.write('\ufeff')  # Inclusão de BOM para o Excel reconhecer a codificação UTF-8
    
    writer = csv.writer(output, delimiter=';') 
    writer.writerow([
        "Data", "Nome", "Email", "WhatsApp", 
        "Protocolo", "Status", "Ultimo Atendente", "CSAT (Nota)", "Resolvido?"
    ])
    
    for t in tickets:
        writer.writerow([
            t.created_at.strftime("%d/%m/%Y %H:%M"), t.nome, t.email, 
            t.whats, t.protocolo, t.status, t.atendente, t.avaliacao, t.resolvido
        ])
        
    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=base_clientes.csv"}
    )


@app.get("/api/export/history")
def export_history(token: str, db: Session = Depends(get_db)):
    """Exporta todas as mensagens do sistema em formato CSV (Auditoria)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "master":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        
    messages = db.query(MessageDB).all()
    output = io.StringIO()
    output.write('\ufeff') 
    
    writer = csv.writer(output, delimiter=';') 
    writer.writerow(["Data", "Remetente", "Mensagem"])
    
    for m in messages:
        writer.writerow([m.timestamp.strftime("%d/%m/%Y %H:%M:%S"), m.sender, m.content])
        
    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=auditoria_chats.csv"}
    )


@app.get("/api/history/{session_id}")
def get_chat_history(session_id: str, token: str, db: Session = Depends(get_db)):
    """Busca o histórico completo de mensagens de uma sessão de atendimento específica."""
    # 1. Valida se quem está chamando a rota é um atendente/master logado
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        
    # 2. Busca exata para evitar que uma string curta vaze dados de outros chats
    mensagens = db.query(MessageDB).filter(
        MessageDB.sender.like(f"%({session_id})%") | MessageDB.content.contains(session_id)
    ).all()
    return mensagens


# ==========================================
# LÓGICA DE NEGÓCIO E FILA DE ATENDIMENTO
# ==========================================
def get_next_attendant() -> str:
    """Implementa a lógica Round-Robin para retornar o próximo atendente disponível."""
    global round_robin_index
    if not online_attendants: 
        return "Fila"
        
    if round_robin_index >= len(online_attendants): 
        round_robin_index = 0
        
    atendente = online_attendants[round_robin_index]
    round_robin_index += 1
    return atendente


async def broadcast_online_attendants():
    """Notifica todos os painéis conectados sobre os atendentes atualmente online."""
    lista_str = ",".join(online_attendants)
    for ws, info in list(connected_users.items()):
        if info["session_id"].startswith("painel_"):
            try: 
                await ws.send_text(f"SYS_ONLINE_USERS|{lista_str}")
            except Exception: 
                pass


async def realocar_tickets(nome_atendente_saindo: str, db: Session):
    """Redistribui os tickets de um atendente que encerrou a conexão ou turno."""
    for sid, dados in list(active_tickets.items()):
        if dados['atendente'] == nome_atendente_saindo and dados['status'] == 'ativo':
            novo_atendente = get_next_attendant()
            dados['atendente'] = novo_atendente
            save_or_update_ticket(db, sid, dados)
            
            if novo_atendente != "Fila":
                mensagem_cliente = f"O especialista anterior encerrou o turno. Você foi transferido para {novo_atendente}."
                await enviar_para_cliente(sid, "Sistema", mensagem_cliente)
                
                msg_crm = (f"{sid}|{dados['nome']}|{dados['email']}|{dados['whats']}|"
                           f"{dados['protocolo']}|ativo|{novo_atendente}|"
                           f"[Sistema: Sessão Transferida de {nome_atendente_saindo}]")
                await enviar_para_paineis(msg_crm, target_atendente=novo_atendente)
                await atualizar_posicoes_fila(novo_atendente)
            else:
                mensagem_retorno = "O atendente encerrou o turno. Você retornou para a fila e será atendido assim que um especialista conectar."
                await enviar_para_cliente(sid, "Sistema", mensagem_retorno)


async def enviar_para_paineis(mensagem: str, target_atendente: str = None):
    """Dispara uma mensagem para o painel de um atendente específico ou administradores."""
    for ws, info in list(connected_users.items()):
        sid = info["session_id"]
        if sid.startswith("painel_"):
            nome_painel = sid.replace("painel_", "")
            role_painel = info["role"]
            
            # Administradores recebem todas as atualizações
            if role_painel == "master":
                try: 
                    await ws.send_text(mensagem)
                except Exception: 
                    pass
                continue
                
            if target_atendente == "Fila": 
                continue
                
            if target_atendente and nome_painel != target_atendente: 
                continue
                
            try: 
                await ws.send_text(mensagem)
            except Exception: 
                pass


async def enviar_para_cliente(cliente_sid: str, remetente: str, mensagem: str):
    """Roteia a resposta ou mensagem de sistema de volta para o cliente final."""
    texto_formatado = f"{cliente_sid}|{remetente}|{mensagem}"
    for ws, info in list(connected_users.items()):
        if info["session_id"] == cliente_sid:
            try: 
                await ws.send_text(texto_formatado)
            except Exception: 
                pass


async def atualizar_posicoes_fila(atendente_alvo: str):
    """Calcula e notifica o cliente sobre a sua posição na fila de espera."""
    tickets_do_atendente = [
        sid for sid, dados in active_tickets.items() 
        if dados['status'] == 'ativo' and dados['atendente'] == atendente_alvo
    ]
    for index, sid in enumerate(tickets_do_atendente):
        posicao_real = index + 1
        if posicao_real > 1: 
            await enviar_para_cliente(sid, "Sistema", f"A fila andou! Sua posição atual é: {posicao_real - 1}º a ser atendido.")
        elif posicao_real == 1:
            await enviar_para_cliente(sid, "Sistema", "Você é o próximo da fila! O atendente já vai falar com você.")


# ==========================================
# ENDPOINT WEBSOCKET: COMUNICAÇÃO CENTRAL
# ==========================================
@app.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    session_id: str, 
    token: str = None
):
    """
    Controlador central de WebSockets para clientes e painéis.
    Gerencia eventos de conexão, roteamento de pacotes (dados e comandos) e desconexão.
    """
    is_attendant = session_id.startswith("painel_")
    nome_atendente = ""
    role = "cliente"
    
    # Validação de Autenticação para atendentes e administradores
    if is_attendant:
        if not token:
            await websocket.close(code=1008)
            return
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            nome_atendente_token = payload.get("sub")
            role = payload.get("role", "atendente")
            nome_atendente = session_id.replace("painel_", "")
            
            if nome_atendente_token != nome_atendente:
                await websocket.close(code=1008)
                return
        except jwt.PyJWTError:
            await websocket.close(code=1008)
            return

    # Efetivação da conexão
    await manager.connect(websocket)
    connected_users[websocket] = {"session_id": session_id, "role": role}
    
    # Lógica de registro para novos atendentes ao entrarem online
    db_startup = SessionLocal()
    try:
        if is_attendant:
            if role != "master":
                # Marca o status do atendente como online
                if nome_atendente not in online_attendants:
                    online_attendants.append(nome_atendente)
                    await broadcast_online_attendants() 
                    
                # Verifica e puxa clientes que estão alocados na fila geral
                for sid, dados in active_tickets.items():
                    if dados['status'] == 'ativo' and dados['atendente'] == 'Fila':
                        dados['atendente'] = nome_atendente
                        save_or_update_ticket(db_startup, sid, dados)
                        await enviar_para_cliente(sid, "Sistema", f"O especialista {nome_atendente} assumiu seu atendimento.")
                        await atualizar_posicoes_fila(nome_atendente)
                        
                        msg_crm = (f"{sid}|Sistema|{dados['email']}|{dados['whats']}|"
                                   f"{dados['protocolo']}|ativo|{nome_atendente}|[UPDATE_ATENDENTE]")
                        await enviar_para_paineis(msg_crm, target_atendente=nome_atendente)
                        
            # Restauração de chamados ativos na interface do atendente
            for sid, dados in active_tickets.items():
                if role == "master" or dados['atendente'] == nome_atendente:
                    msg_crm = (f"{sid}|{dados['nome']}|{dados['email']}|{dados['whats']}|"
                               f"{dados['protocolo']}|{dados['status']}|{dados['atendente']}|"
                               "[Sistema: Sessão Restaurada]")
                    try: 
                        await websocket.send_text(msg_crm)
                    except Exception: 
                        pass

            # Restauração do histórico de chamados encerrados do atendente
            closed_tickets = db_startup.query(TicketDB).filter(TicketDB.status == "encerrado")
            if role != "master":
                closed_tickets = closed_tickets.filter(TicketDB.atendente == nome_atendente)
            
            for t in closed_tickets.all():
                msg_crm = (f"{t.session_id}|{t.nome}|{t.email}|{t.whats}|"
                           f"{t.protocolo}|{t.status}|{t.atendente}|"
                           "[Sistema: Sessão Restaurada]")
                try: 
                    await websocket.send_text(msg_crm)
                except Exception: 
                    pass
    finally:
        db_startup.close()
            
    # Loop contínuo de recepção e roteamento de pacotes
    try:
        while True:
            data = await websocket.receive_text()
            
            # Instancia o banco exclusivamente para esta mensagem
            db_loop = SessionLocal()
            try:
                # --- ROTEAMENTO: Mensagem oriunda do cliente ---
                if data.startswith("CLIENT_DATA|"):
                    parts = data.split("|", 4) 
                    
                    # Trava de Segurança: Se os dados vierem corrompidos, ignora para não derrubar o servidor
                    if len(parts) < 5:
                        continue
                        
                    nome = parts[1]
                    email = parts[2]
                    whatsapp = parts[3]
                    msg = parts[4]
                
                    # Gera novo ticket caso a sessão não esteja mapeada
                    if session_id not in active_tickets:
                        protocolo = f"PRT-{datetime.now().year}{datetime.now().month:02d}-{random.randint(1000, 9999)}"
                        atendente_sorteado = get_next_attendant()
                        active_tickets[session_id] = {
                            "nome": nome, "protocolo": protocolo, "email": email, "whats": whatsapp,
                            "status": "ativo", "atendente": atendente_sorteado, "protocolo_informado": False 
                        }
                        save_or_update_ticket(db_loop, session_id, active_tickets[session_id])
                    
                    dados_ticket = active_tickets[session_id]
                    
                    # Persistência da mensagem na auditoria do banco de dados
                    identificador = f"Cliente:{nome} ({session_id})"
                    nova_msg = MessageDB(sender=identificador, content=f"[{dados_ticket['protocolo']}] Msg: {msg}")
                    db_loop.add(nova_msg)
                    db_loop.commit()
                    
                    # Envio do protocolo na primeira interação válida do cliente
                    if msg != "[ENTROU NO CHAT]" and not dados_ticket["protocolo_informado"]:
                        msg_sistema = f"Atendimento iniciado. Seu protocolo é {dados_ticket['protocolo']}."
                        if dados_ticket['atendente'] != "Fila":
                            msg_sistema += f" O(a) atendente {dados_ticket['atendente']} falará com você em instantes!"
                        else:
                            msg_sistema += " Aguarde o próximo especialista disponível."
                            
                        await enviar_para_cliente(session_id, "Sistema", msg_sistema)
                        dados_ticket["protocolo_informado"] = True
                        await atualizar_posicoes_fila(dados_ticket['atendente'])

                    # Cliente encerrou o chamado pelo seu próprio painel
                    if msg == "[CLIENTE ENCERROU O ATENDIMENTO]":
                        active_tickets[session_id]['status'] = 'encerrado'
                        save_or_update_ticket(db_loop, session_id, dados_ticket)
                        msg_crm = (f"{session_id}|Sistema|{dados_ticket['email']}|{dados_ticket['whats']}|"
                                   f"{dados_ticket['protocolo']}|encerrado|{dados_ticket['atendente']}|"
                                   "[CLIENTE ENCERROU O ATENDIMENTO]")
                        await enviar_para_paineis(msg_crm, target_atendente=dados_ticket['atendente'])
                        await atualizar_posicoes_fila(dados_ticket['atendente'])
                    else:
                        msg_crm = (f"{session_id}|{nome}|{dados_ticket['email']}|{dados_ticket['whats']}|"
                                   f"{dados_ticket['protocolo']}|{dados_ticket['status']}|"
                                   f"{dados_ticket['atendente']}|{msg}")
                        await enviar_para_paineis(msg_crm, target_atendente=dados_ticket['atendente'])
                        await enviar_para_cliente(session_id, nome, msg)
                
                # --- ROTEAMENTO: Mensagem de resposta do atendente ---
                elif data.startswith("ATENDENTE_REPLY|"):
                    parts = data.split("|", 2) 
                    target_session_id = parts[1]
                    msg = parts[2]
                    
                    nova_msg = MessageDB(sender="Atendente", content=f"Para {target_session_id}: {msg}")
                    db_loop.add(nova_msg)
                    db_loop.commit()
                    
                    if target_session_id in active_tickets:
                        dados_ticket = active_tickets[target_session_id]
                        nome_quem_respondeu = session_id.replace("painel_", "")
                        msg_crm = (f"{target_session_id}|{nome_quem_respondeu}|{dados_ticket['email']}|"
                                   f"{dados_ticket['whats']}|{dados_ticket['protocolo']}|"
                                   f"{dados_ticket['status']}|{dados_ticket['atendente']}|{msg}")
                        await enviar_para_paineis(msg_crm, target_atendente=dados_ticket['atendente'])
                        
                    await enviar_para_cliente(target_session_id, "Atendente", msg)

                # --- COMANDO DE SISTEMA: Transferir Chat ---
                elif data.startswith("CMD_TRANSFERIR|"):
                    parts = data.split("|", 2)
                    target_session_id = parts[1]
                    novo_atendente = parts[2]
                    
                    if target_session_id in active_tickets and novo_atendente in online_attendants:
                        dados_ticket = active_tickets[target_session_id]
                        atendente_antigo = dados_ticket['atendente']
                        dados_ticket['atendente'] = novo_atendente
                        save_or_update_ticket(db_loop, target_session_id, dados_ticket)
                        
                        nova_msg_sys = MessageDB(
                            sender=f"Sistema_{target_session_id}", 
                            content=f"Atendimento transferido de {atendente_antigo} para {novo_atendente}."
                        )
                        db_loop.add(nova_msg_sys)
                        db_loop.commit()

                        await enviar_para_cliente(target_session_id, "Sistema", f"Você está sendo transferido para o especialista {novo_atendente}.")
                        msg_crm = (f"{target_session_id}|{dados_ticket['nome']}|{dados_ticket['email']}|"
                                   f"{dados_ticket['whats']}|{dados_ticket['protocolo']}|ativo|{novo_atendente}|"
                                   f"[Sistema: Sessão Transferida de {atendente_antigo}]")
                        await enviar_para_paineis(msg_crm, target_atendente=novo_atendente)
                        await atualizar_posicoes_fila(novo_atendente)

                # --- COMANDO DE SISTEMA: Inserir Nota Interna ---
                elif data.startswith("CMD_NOTA|"):
                    parts = data.split("|", 2)
                    target_session_id = parts[1]
                    nota = parts[2]
                    nome_quem_anotou = session_id.replace("painel_", "")
                    
                    nova_msg = MessageDB(
                        sender=f"Sistema_Nota_{target_session_id}", 
                        content=f"[{nome_quem_anotou}]: {nota}"
                    )
                    db_loop.add(nova_msg)
                    db_loop.commit()
                    
                    if target_session_id in active_tickets:
                        atendente_atual = active_tickets[target_session_id]['atendente']
                        msg_crm = f"{target_session_id}|Sistema_Nota|- |- |- |ativo|{atendente_atual}|[{nome_quem_anotou}]: {nota}"
                        await enviar_para_paineis(msg_crm, target_atendente=atendente_atual)

                # --- COMANDO DE SISTEMA: Encerrar Chat ---
                elif data.startswith("CMD_ENCERRAR|"):
                    parts = data.split("|", 1)
                    target_session_id = parts[1]
                    
                    if target_session_id in active_tickets:
                        active_tickets[target_session_id]["status"] = "encerrado"
                        dados_ticket = active_tickets[target_session_id]
                        atendente_responsavel = dados_ticket['atendente']
                        save_or_update_ticket(db_loop, target_session_id, dados_ticket)
                        
                        nova_msg_sys = MessageDB(
                            sender=f"Sistema_{target_session_id}", 
                            content=f"Atendimento encerrado pelo especialista {session_id.replace('painel_', '')}."
                        )
                        db_loop.add(nova_msg_sys)
                        db_loop.commit()

                        msg_crm = (f"{target_session_id}|Sistema|{dados_ticket['email']}|{dados_ticket['whats']}|"
                                   f"{dados_ticket['protocolo']}|encerrado|{atendente_responsavel}|"
                                   "Atendimento finalizado com sucesso.")
                        await enviar_para_paineis(msg_crm, target_atendente=None)
                        await enviar_para_cliente(target_session_id, "Sistema", "O atendente encerrou esta conversa. Obrigado!")
                        await atualizar_posicoes_fila(atendente_responsavel)

                # --- COMANDO DE SISTEMA: Logout de Atendente ---
                elif data.startswith("CMD_LOGOUT|"):
                    if nome_atendente in online_attendants:
                        online_attendants.remove(nome_atendente)
                        await broadcast_online_attendants()
                        await realocar_tickets(nome_atendente, db_loop)

            except Exception:
                pass
            finally:
                db_loop.close()  # Isso garante que a conexão será encerrada e retornada ao pool

    # Tratamento de interrupção ou perda de conexão da rede
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        if websocket in connected_users:
            info = connected_users[websocket]
            del connected_users[websocket]
            
        db_disconnect = SessionLocal()
        try:
            # Desconexão de Atendente (Painel)
            if is_attendant:
                if role != "master":
                    still_online = any(u["session_id"] == session_id for u in connected_users.values())
                    if not still_online and nome_atendente in online_attendants:
                        online_attendants.remove(nome_atendente)
                        await broadcast_online_attendants()
                        await realocar_tickets(nome_atendente, db_disconnect)
                        
            # Desconexão do Cliente Final (Browser do cliente fechado)
            else:
                if session_id in active_tickets and active_tickets[session_id]['status'] == 'ativo':
                    active_tickets[session_id]['status'] = 'encerrado'
                    dados_ticket = active_tickets[session_id]
                    atendente_responsavel = dados_ticket['atendente']
                    save_or_update_ticket(db_disconnect, session_id, dados_ticket)

                    nova_msg_sys = MessageDB(
                        sender=f"Sistema_{session_id}", 
                        content="O cliente fechou a página ou perdeu a conexão."
                    )
                    db_disconnect.add(nova_msg_sys)
                    db_disconnect.commit()

                    msg_crm = (f"{session_id}|Sistema|{dados_ticket['email']}|{dados_ticket['whats']}|"
                               f"{dados_ticket['protocolo']}|encerrado|{atendente_responsavel}|"
                               "[CLIENTE ENCERROU O ATENDIMENTO]")
                    await enviar_para_paineis(msg_crm, target_atendente=None) 
                    await atualizar_posicoes_fila(atendente_responsavel)
        finally:
            db_disconnect.close()

    except RuntimeError:
        pass  # Evita crash da aplicação caso o iterador do websocket perca a referência subitamente
