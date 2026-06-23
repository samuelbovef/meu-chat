"""
Módulo Principal da API (Servidor de Chat Profissional com CRM).

Este arquivo gerencia:
- Inicialização do servidor FastAPI.
- Autenticação e registro de atendentes (JWT).
- Geração de métricas e exportação de relatórios (CSV).
- Gerenciamento de conexões em tempo real via WebSockets.
- Regras de negócio de fila (Round-Robin) e transferência de chats.
"""

import os
import csv
import io
import random
from datetime import datetime, timedelta

from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, 
    Depends, HTTPException, status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import jwt
import bcrypt  
from dotenv import load_dotenv

# Importações locais
from .database import engine, Base, SessionLocal
from .models import MessageDB, AttendantDB, TicketDB
from .websocket import manager

# ==========================================
# CONFIGURAÇÃO DO AMBIENTE E BANCO
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

# Configuração de CORS para permitir requisições do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
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
# SEGURANÇA E AUTENTICAÇÃO
# ==========================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha fornecida bate com o hash salvo."""
    password_bytes = plain_password.encode('utf-8')
    hashed_password_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_password_bytes)


def get_password_hash(password: str) -> str:
    """Gera o hash seguro para uma nova senha."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt)
    return hashed_password.decode('utf-8')


def create_access_token(data: dict):
    """Cria um token JWT para o usuário com expiração de 8 horas."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=8)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@app.post("/register")
def register_attendant(username: str, password: str, role: str = "atendente", master_key: str = None, db: Session = Depends(get_db)):
    """Rota para registrar novos atendentes com validação de segurança de Chave Mestra."""
    # 🔒 Camada extra anti-engenharia reversa: Exige a senha mestra para criar usuários
    if master_key != "REGISTRATION_MASTER_KEY":
        raise HTTPException(status_code=403, detail="Acesso proibido. Chave mestra inválida.")

    db_user = db.query(AttendantDB).filter(AttendantDB.username == username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Usuário já existe")
        
    hashed_pwd = get_password_hash(password)
    new_user = AttendantDB(username=username, hashed_password=hashed_pwd, role=role)
    db.add(new_user)
    db.commit()
    return {"message": f"Usuário {username} ({role}) cadastrado com sucesso!"}


@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Rota de login que retorna o token JWT caso as credenciais estejam corretas."""
    user = db.query(AttendantDB).filter(AttendantDB.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
        
    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer", "role": user.role}


# ==========================================
# ROTAS DE AVALIAÇÃO, MÉTRICAS E EXPORTAÇÃO
# ==========================================
class FeedbackModel(BaseModel):
    """Modelo Pydantic para receber dados de avaliação do cliente."""
    avaliacao: int
    resolvido: str


@app.post("/api/feedback/{session_id}")
def save_feedback(session_id: str, feedback: FeedbackModel, db: Session = Depends(get_db)):
    """Salva a nota e a confirmação de resolução enviada pelo cliente no final do chat."""
    ticket = db.query(TicketDB).filter(TicketDB.session_id == session_id).first()
    if ticket:
        ticket.avaliacao = feedback.avaliacao
        ticket.resolvido = feedback.resolvido
        db.commit()
        return {"msg": "Feedback salvo com sucesso"}
    raise HTTPException(status_code=404, detail="Ticket não encontrado")


@app.get("/api/metrics")
def get_metrics(token: str, db: Session = Depends(get_db)):
    """Calcula e retorna as métricas de atendimento (Acesso restrito: Master)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "master":
            raise HTTPException(status_code=403, detail="Acesso negado.")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")
        
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


@app.get("/api/export/clients")
def export_clients(token: str, db: Session = Depends(get_db)):
    """Exporta a base de tickets/clientes em formato CSV (Acesso restrito: Master)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "master":
            raise HTTPException(status_code=403, detail="Acesso negado.")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")
        
    tickets = db.query(TicketDB).all()
    output = io.StringIO()
    output.write('\ufeff')  # BOM para Excel reconhecer acentos
    
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
    """Exporta todas as mensagens do sistema em formato CSV (Acesso restrito: Master)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "master":
            raise HTTPException(status_code=403, detail="Acesso negado.")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")
        
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
def get_chat_history(session_id: str, db: Session = Depends(get_db)):
    """Busca o histórico de mensagens de uma sessão específica."""
    mensagens = db.query(MessageDB).filter(
        MessageDB.sender.contains(session_id) | MessageDB.content.contains(session_id)
    ).all()
    return mensagens


# ==========================================
# HELPERS DE WEBSOCKET / SISTEMA DE FILA
# ==========================================
def get_next_attendant():
    """Retorna o próximo atendente disponível usando lógica Round-Robin."""
    global round_robin_index
    if not online_attendants: 
        return "Fila"
        
    if round_robin_index >= len(online_attendants): 
        round_robin_index = 0
        
    atendente = online_attendants[round_robin_index]
    round_robin_index += 1
    return atendente


async def broadcast_online_attendants():
    """Avisa todos os painéis conectados sobre quem está online no momento."""
    lista_str = ",".join(online_attendants)
    for ws, info in list(connected_users.items()):
        if info["session_id"].startswith("painel_"):
            try: 
                await ws.send_text(f"SYS_ONLINE_USERS|{lista_str}")
            except Exception: 
                pass


async def realocar_tickets(nome_atendente_saindo, db: Session):
    """Redistribui tickets de um atendente que se desconectou."""
    for sid, dados in list(active_tickets.items()):
        if dados['atendente'] == nome_atendente_saindo and dados['status'] == 'ativo':
            novo_atendente = get_next_attendant()
            dados['atendente'] = novo_atendente
            save_or_update_ticket(db, sid, dados)
            
            if novo_atendente != "Fila":
                await enviar_para_cliente(sid, "Sistema", f"O especialista anterior encerrou o turno. Você foi transferido para {novo_atendente}.")
                
                msg_crm = (f"{sid}|{dados['nome']}|{dados['email']}|{dados['whats']}|"
                           f"{dados['protocolo']}|ativo|{novo_atendente}|"
                           f"[Sistema: Sessão Transferida de {nome_atendente_saindo}]")
                await enviar_para_paineis(msg_crm, target_atendente=novo_atendente)
                await atualizar_posicoes_fila(novo_atendente)
            else:
                await enviar_para_cliente(sid, "Sistema", "O atendente encerrou o turno. Você retornou para a fila e será atendido assim que um especialista conectar.")


async def enviar_para_paineis(mensagem, target_atendente=None):
    """Envia uma mensagem para o painel do atendente alvo (ou para o master, que vê tudo)."""
    for ws, info in list(connected_users.items()):
        sid = info["session_id"]
        if sid.startswith("painel_"):
            nome_painel = sid.replace("painel_", "")
            role_painel = info["role"]
            
            # Master recebe tudo
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


async def enviar_para_cliente(cliente_sid, remetente, mensagem):
    """Roteia a mensagem de volta para o WebSocket do cliente correspondente."""
    texto_formatado = f"{cliente_sid}|{remetente}|{mensagem}"
    for ws, info in list(connected_users.items()):
        if info["session_id"] == cliente_sid:
            try: 
                await ws.send_text(texto_formatado)
            except Exception: 
                pass


async def atualizar_posicoes_fila(atendente_alvo):
    """Calcula e informa a posição atual do cliente na fila do seu respectivo atendente."""
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
# ENDPOINT PRINCIPAL DO WEBSOCKET
# ==========================================
@app.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, token: str = None, db: Session = Depends(get_db)):
    """
    Controlador principal de WebSockets para clientes e painéis.
    Gerencia conexão, roteamento de mensagens (CLIENT_DATA, ATENDENTE_REPLY, etc.) e desconexão.
    """
    is_attendant = session_id.startswith("painel_")
    nome_atendente = ""
    role = "cliente"
    
    # 1. VALIDAÇÃO DE AUTENTICAÇÃO (Se for atendente/master)
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

    # 2. CONEXÃO BÁSICA
    await manager.connect(websocket)
    connected_users[websocket] = {"session_id": session_id, "role": role}
    
    # 3. ROTINAS DE ENTRADA DO ATENDENTE
    if is_attendant:
        if role != "master":
            # Marca online e puxa da fila de espera
            if nome_atendente not in online_attendants:
                online_attendants.append(nome_atendente)
                await broadcast_online_attendants() 
                
            for sid, dados in active_tickets.items():
                if dados['status'] == 'ativo' and dados['atendente'] == 'Fila':
                    dados['atendente'] = nome_atendente
                    save_or_update_ticket(db, sid, dados)
                    await enviar_para_cliente(sid, "Sistema", f"O especialista {nome_atendente} assumiu seu atendimento.")
                    await atualizar_posicoes_fila(nome_atendente)
                    
                    msg_crm = (f"{sid}|Sistema|{dados['email']}|{dados['whats']}|"
                               f"{dados['protocolo']}|ativo|{nome_atendente}|[UPDATE_ATENDENTE]")
                    await enviar_para_paineis(msg_crm, target_atendente=nome_atendente)
                    
        # Restaura chamados ativos na tela
        for sid, dados in active_tickets.items():
            if role == "master" or dados['atendente'] == nome_atendente:
                msg_crm = (f"{sid}|{dados['nome']}|{dados['email']}|{dados['whats']}|"
                           f"{dados['protocolo']}|{dados['status']}|{dados['atendente']}|"
                           "[Sistema: Sessão Restaurada]")
                try: 
                    await websocket.send_text(msg_crm)
                except Exception: 
                    pass

        # Restaura chamados encerrados do histórico daquele atendente
        closed_tickets = db.query(TicketDB).filter(TicketDB.status == "encerrado")
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
            
    # 4. LOOP DE RECEBIMENTO DE MENSAGENS
    try:
        while True:
            data = await websocket.receive_text()
            
            # --- MENSAGEM DO CLIENTE ---
            if data.startswith("CLIENT_DATA|"):
                parts = data.split("|", 4) 
                nome = parts[1]
                email = parts[2]
                whatsapp = parts[3]
                msg = parts[4]
                
                # Inicializa ticket novo, se não existir
                if session_id not in active_tickets:
                    protocolo = f"PRT-{datetime.now().year}{datetime.now().month:02d}-{random.randint(1000, 9999)}"
                    atendente_sorteado = get_next_attendant()
                    active_tickets[session_id] = {
                        "nome": nome, "protocolo": protocolo, "email": email, "whats": whatsapp,
                        "status": "ativo", "atendente": atendente_sorteado, "protocolo_informado": False 
                    }
                    save_or_update_ticket(db, session_id, active_tickets[session_id])
                
                dados_ticket = active_tickets[session_id]
                
                # Salva no banco de histórico de mensagens
                identificador = f"Cliente:{nome} ({session_id})"
                nova_msg = MessageDB(sender=identificador, content=f"[{dados_ticket['protocolo']}] Msg: {msg}")
                db.add(nova_msg)
                db.commit()
                
                # Envia protocolo caso seja a primeira interação real
                if msg != "[ENTROU NO CHAT]" and not dados_ticket["protocolo_informado"]:
                    msg_sistema = f"Atendimento iniciado. Seu protocolo é {dados_ticket['protocolo']}."
                    if dados_ticket['atendente'] != "Fila":
                        msg_sistema += f" O(a) atendente {dados_ticket['atendente']} falará com você em instantes!"
                    else:
                        msg_sistema += " Aguarde o próximo especialista disponível."
                        
                    await enviar_para_cliente(session_id, "Sistema", msg_sistema)
                    dados_ticket["protocolo_informado"] = True
                    await atualizar_posicoes_fila(dados_ticket['atendente'])

                # Cliente fechou o atendimento
                if msg == "[CLIENTE ENCERROU O ATENDIMENTO]":
                    active_tickets[session_id]['status'] = 'encerrado'
                    save_or_update_ticket(db, session_id, dados_ticket)
                    msg_crm = (f"{session_id}|Sistema|{dados_ticket['email']}|{dados_ticket['whats']}|"
                               f"{dados_ticket['protocolo']}|encerrado|{dados_ticket['atendente']}|"
                               "[CLIENTE ENCERROU O ATENDIMENTO]")
                    await enviar_para_paineis(msg_crm, target_atendente=dados_ticket['atendente'])
                    await atualizar_posicoes_fila(dados_ticket['atendente'])
                else:
                    # Roteia mensagem para atendente e espelha no cliente
                    msg_crm = (f"{session_id}|{nome}|{dados_ticket['email']}|{dados_ticket['whats']}|"
                               f"{dados_ticket['protocolo']}|{dados_ticket['status']}|"
                               f"{dados_ticket['atendente']}|{msg}")
                    await enviar_para_paineis(msg_crm, target_atendente=dados_ticket['atendente'])
                    await enviar_para_cliente(session_id, nome, msg)
                
            # --- RESPOSTA DO ATENDENTE ---
            elif data.startswith("ATENDENTE_REPLY|"):
                parts = data.split("|", 2) 
                target_session_id = parts[1]
                msg = parts[2]
                
                nova_msg = MessageDB(sender="Atendente", content=f"Para {target_session_id}: {msg}")
                db.add(nova_msg)
                db.commit()
                
                if target_session_id in active_tickets:
                    dados_ticket = active_tickets[target_session_id]
                    nome_quem_respondeu = session_id.replace("painel_", "")
                    msg_crm = (f"{target_session_id}|{nome_quem_respondeu}|{dados_ticket['email']}|"
                               f"{dados_ticket['whats']}|{dados_ticket['protocolo']}|"
                               f"{dados_ticket['status']}|{dados_ticket['atendente']}|{msg}")
                    await enviar_para_paineis(msg_crm, target_atendente=dados_ticket['atendente'])
                    
                await enviar_para_cliente(target_session_id, "Atendente", msg)

            # --- COMANDO: TRANSFERIR CHAT ---
            elif data.startswith("CMD_TRANSFERIR|"):
                parts = data.split("|", 2)
                target_session_id = parts[1]
                novo_atendente = parts[2]
                
                if target_session_id in active_tickets and novo_atendente in online_attendants:
                    dados_ticket = active_tickets[target_session_id]
                    atendente_antigo = dados_ticket['atendente']
                    dados_ticket['atendente'] = novo_atendente
                    save_or_update_ticket(db, target_session_id, dados_ticket)
                    
                    nova_msg_sys = MessageDB(
                        sender=f"Sistema_{target_session_id}", 
                        content=f"Atendimento transferido de {atendente_antigo} para {novo_atendente}."
                    )
                    db.add(nova_msg_sys)
                    db.commit()

                    await enviar_para_cliente(target_session_id, "Sistema", f"Você está sendo transferido para o especialista {novo_atendente}.")
                    msg_crm = (f"{target_session_id}|{dados_ticket['nome']}|{dados_ticket['email']}|"
                               f"{dados_ticket['whats']}|{dados_ticket['protocolo']}|ativo|{novo_atendente}|"
                               f"[Sistema: Sessão Transferida de {atendente_antigo}]")
                    await enviar_para_paineis(msg_crm, target_atendente=novo_atendente)
                    await atualizar_posicoes_fila(novo_atendente)

            # --- COMANDO: INSERIR NOTA INTERNA ---
            elif data.startswith("CMD_NOTA|"):
                parts = data.split("|", 2)
                target_session_id = parts[1]
                nota = parts[2]
                nome_quem_anotou = session_id.replace("painel_", "")
                
                nova_msg = MessageDB(
                    sender=f"Sistema_Nota_{target_session_id}", 
                    content=f"[{nome_quem_anotou}]: {nota}"
                )
                db.add(nova_msg)
                db.commit()
                
                if target_session_id in active_tickets:
                    atendente_atual = active_tickets[target_session_id]['atendente']
                    msg_crm = f"{target_session_id}|Sistema_Nota|- |- |- |ativo|{atendente_atual}|[{nome_quem_anotou}]: {nota}"
                    await enviar_para_paineis(msg_crm, target_atendente=atendente_atual)

            # --- COMANDO: ENCERRAR CHAT ---
            elif data.startswith("CMD_ENCERRAR|"):
                parts = data.split("|", 1)
                target_session_id = parts[1]
                
                if target_session_id in active_tickets:
                    active_tickets[target_session_id]["status"] = "encerrado"
                    dados_ticket = active_tickets[target_session_id]
                    atendente_responsavel = dados_ticket['atendente']
                    save_or_update_ticket(db, target_session_id, dados_ticket)
                    
                    nova_msg_sys = MessageDB(
                        sender=f"Sistema_{target_session_id}", 
                        content=f"Atendimento encerrado pelo especialista {session_id.replace('painel_', '')}."
                    )
                    db.add(nova_msg_sys)
                    db.commit()

                    msg_crm = (f"{target_session_id}|Sistema|{dados_ticket['email']}|{dados_ticket['whats']}|"
                               f"{dados_ticket['protocolo']}|encerrado|{atendente_responsavel}|"
                               "Atendimento finalizado com sucesso.")
                    await enviar_para_paineis(msg_crm, target_atendente=None)
                    await enviar_para_cliente(target_session_id, "Sistema", "O atendente encerrou esta conversa. Obrigado!")
                    await atualizar_posicoes_fila(atendente_responsavel)

            # --- COMANDO: LOGOUT DO ATENDENTE ---
            elif data.startswith("CMD_LOGOUT|"):
                if nome_atendente in online_attendants:
                    online_attendants.remove(nome_atendente)
                    await broadcast_online_attendants()
                    await realocar_tickets(nome_atendente, db)

    # 5. GERENCIAMENTO DE DESCONEXÕES GERAIS
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        if websocket in connected_users:
            info = connected_users[websocket]
            del connected_users[websocket]
        
        # Desconexão de Atendente
        if is_attendant:
            if role != "master":
                still_online = any(u["session_id"] == session_id for u in connected_users.values())
                if not still_online and nome_atendente in online_attendants:
                    online_attendants.remove(nome_atendente)
                    await broadcast_online_attendants()
                    await realocar_tickets(nome_atendente, db)
                    
        # Desconexão de Cliente
        else:
            if session_id in active_tickets and active_tickets[session_id]['status'] == 'ativo':
                active_tickets[session_id]['status'] = 'encerrado'
                dados_ticket = active_tickets[session_id]
                atendente_responsavel = dados_ticket['atendente']
                save_or_update_ticket(db, session_id, dados_ticket)

                nova_msg_sys = MessageDB(sender=f"Sistema_{session_id}", content="O cliente fechou a página ou perdeu a conexão.")
                db.add(nova_msg_sys)
                db.commit()

                msg_crm = (f"{session_id}|Sistema|{dados_ticket['email']}|{dados_ticket['whats']}|"
                           f"{dados_ticket['protocolo']}|encerrado|{atendente_responsavel}|"
                           "[CLIENTE ENCERROU O ATENDIMENTO]")
                await enviar_para_paineis(msg_crm, target_atendente=None) 
                await atualizar_posicoes_fila(atendente_responsavel)

    except RuntimeError:
        pass  # Evita crash ao iterar sobre websockets que caíram repentinamente
