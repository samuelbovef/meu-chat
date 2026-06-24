/**
 * ==========================================
 * APP.JS - CLIENTE FRONT-END DO DASHBOARD
 * ==========================================
 * Controlador principal da interface do painel de atendimento.
 * Gerencia o DOM, conexões WebSocket, gráficos (Chart.js), autenticação
 * e o sistema de notificações push/áudio.
 */

/* ==========================================
   FUNÇÕES GLOBAIS
   ========================================== */

/**
 * Abre uma imagem codificada em Base64 em uma nova aba do navegador.
 * @param {string} base64Data - String contendo os dados da imagem em base64.
 */
window.abrirImagemEmNovaGuia = function(base64Data) {
    fetch(base64Data)
        .then(res => res.blob())
        .then(blob => {
            const blobUrl = URL.createObjectURL(blob);
            window.open(blobUrl, '_blank');
        })
        .catch(err => console.error("Erro ao abrir imagem:", err));
};

/* ==========================================
   INICIALIZAÇÃO DA APLICAÇÃO E VARIÁVEIS
   ========================================== */
document.addEventListener("DOMContentLoaded", () => {
    
    // --- REFERÊNCIAS DO DOM ---
    
    // Telas e Autenticação
    const loginScreen = document.getElementById("login-screen");
    const dashboardScreen = document.getElementById("dashboard-screen");
    const attendantNameInput = document.getElementById("attendant-name");
    const btnLogin = document.getElementById("btn-login");
    const uiAttendantName = document.getElementById("ui-attendant-name");
    const btnLogout = document.getElementById("btn-logout");

    // Painéis Principais
    const chatPanel = document.getElementById("chat-panel");
    const metricsPanel = document.getElementById("metrics-panel");
    const btnShowMetrics = document.getElementById("btn-show-metrics");
    const btnCloseMetrics = document.getElementById("btn-close-metrics");

    // Área de Chat (Mensagens)
    const messagesArea = document.getElementById("messages-area");
    const messageInput = document.getElementById("message-input");
    const sendBtn = document.getElementById("send-btn");
    const currentChatTitle = document.getElementById("current-chat-title");
    const currentChatProtocol = document.getElementById("current-chat-protocol");
    
    // Painel CRM (Lateral Direita)
    const crmPanel = document.getElementById("crm-panel");
    const crmNome = document.getElementById("crm-nome");
    const crmEmail = document.getElementById("crm-email");
    const crmWhats = document.getElementById("crm-whats");
    const btnEncerrarAtendimento = document.getElementById("btn-encerrar-atendimento");
    
    // Ações do CRM
    const transferArea = document.getElementById("transfer-area");
    const transferSelect = document.getElementById("transfer-select");
    const btnTransferir = document.getElementById("btn-transferir");
    const noteArea = document.getElementById("note-area");
    const noteInput = document.getElementById("note-input");
    const btnNota = document.getElementById("btn-nota");
    const fileInput = document.getElementById("attendant-file-input");
    const attachBtn = document.getElementById("attendant-attach-btn");

    // Abas e Listagem Lateral (Fila)
    const btnAtivas = document.getElementById("tab-ativas");
    const btnEncerrados = document.getElementById("tab-encerrados");
    const areaAtivas = document.getElementById("area-ativas");
    const areaEncerrados = document.getElementById("area-encerrados");
    const listAtivas = document.getElementById("client-list");
    const listEncerrados = document.getElementById("closed-list");
    const searchProtocol = document.getElementById("search-protocol");
    
    // Ações exclusivas do modo Master
    const masterActions = document.getElementById("master-actions");
    const btnExportClients = document.getElementById("btn-export-clients");
    const btnExportHistory = document.getElementById("btn-export-history");

    // --- CONFIGURAÇÕES DE ATALHO DE MENSAGEM ---
    const respostasRapidas = {
        "/saudacao": "Olá! Seja muito bem-vindo ao nosso atendimento. Como posso ajudar você hoje?",
        "/aguarde": "Por favor, aguarde um momento enquanto verifico essa informação no nosso sistema.",
        "/despedida": "Agradecemos muito o seu contato! Se precisar de mais alguma coisa, estamos à disposição. Tenha um excelente dia!",
        "/pix": "Nossa chave PIX (CNPJ) é: 00.000.000/0001-00. Por favor, nos envie o comprovante por aqui assim que realizar a transferência."
    };

    // --- ESTADO GLOBAL DA APLICAÇÃO ---
    let chats = {}; 
    let activeSessionId = null;
    let currentTab = "ativas";
    let ws;
    let chartRes = null;
    let chartCsat = null;

    let attendantName = sessionStorage.getItem("attendantName") || "";
    let jwtToken = sessionStorage.getItem("jwtToken") || "";
    let userRole = sessionStorage.getItem("userRole") || "atendente"; 
    
    // Auto-Login se houver sessão válida armazenada no navegador
    if (attendantName && jwtToken) {
        uiAttendantName.innerText = userRole === 'master' ? `Master: ${attendantName}` : attendantName;
        if (userRole === 'master' && masterActions) {
            masterActions.style.display = "block";
        }
        loginScreen.style.display = "none";
        dashboardScreen.style.display = "flex";
        conectarServidor();
    }

    /* ==========================================
       SISTEMA DE NOTIFICAÇÕES (ÁUDIO E PUSH)
       ========================================== */
    // Pede permissão ao sistema operacional logo que o painel carregar
    if (Notification.permission === "default") {
        Notification.requestPermission();
    }

    /**
     * Dispara um aviso sonoro e um balão visual de notificação.
     * @param {string} remetente - Nome de quem enviou a mensagem.
     * @param {string} texto - Prévia da mensagem.
     */
    function dispararNotificacao(remetente, texto) {
        // 1. Toca o alerta sonoro "Plim"
        const audio = new Audio("https://cdn.pixabay.com/download/audio/2021/08/04/audio_0625c1539c.mp3?filename=success-1-6297.mp3");
        audio.play().catch(e => console.log("Áudio bloqueado até o usuário interagir com a tela."));

        // 2. Dispara o balão na tela do computador
        if (Notification.permission === "granted") {
            const notificacao = new Notification(`Nova mensagem de: ${remetente}`, {
                body: texto.length > 50 ? texto.substring(0, 50) + "..." : texto,
                icon: "https://cdn-icons-png.flaticon.com/512/1041/1041916.png"
            });
            
            // Se clicar no balão, a aba do painel abre e ganha o foco
            notificacao.onclick = () => {
                window.focus();
                notificacao.close();
            };
        }
    }

    /* ==========================================
       LÓGICA DE AUTENTICAÇÃO
       ========================================== */
    btnLogin.onclick = async () => {
        const name = attendantNameInput.value.trim();
        const password = document.getElementById("attendant-password").value.trim();
        
        if (!name || !password) {
            return alert("Por favor, digite seu usuário e senha.");
        }
        
        btnLogin.innerText = "Conectando...";
        btnLogin.disabled = true;
        
        try {
            const formData = new URLSearchParams();
            formData.append('username', name);
            formData.append('password', password);

            const response = await fetch("https://[url hospedagem]/login", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: formData
            });

            if (!response.ok) {
                btnLogin.innerText = "Ficar Online";
                btnLogin.disabled = false;
                return alert("Acesso Negado: Usuário ou senha incorretos.");
            }

            const data = await response.json();
            jwtToken = data.access_token;
            attendantName = name;
            userRole = data.role; 
            
            sessionStorage.setItem("jwtToken", jwtToken);
            sessionStorage.setItem("attendantName", name);
            sessionStorage.setItem("userRole", userRole);
            
            uiAttendantName.innerText = userRole === 'master' ? `Master: ${name}` : name;
            
            if (userRole === 'master' && masterActions) {
                masterActions.style.display = "block";
            }
            
            loginScreen.style.display = "none";
            dashboardScreen.style.display = "flex";
            
            conectarServidor();
            telaAguardando(); 
        } catch (error) {
            console.error("Erro na autenticação:", error);
            alert("Erro ao conectar no servidor de autenticação.");
            btnLogin.innerText = "Ficar Online";
            btnLogin.disabled = false;
        }
    };

    btnLogout.onclick = () => {
        if (confirm("Deseja realmente encerrar a sua sessão?")) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(`CMD_LOGOUT|${attendantName}`);
                ws.close();
            }
            sessionStorage.clear(); 
            location.reload(); 
        }
    };

    /* ==========================================
       LÓGICA DO DASHBOARD DE MÉTRICAS E EXPORTAÇÃO
       ========================================== */
    if (btnShowMetrics) {
        btnShowMetrics.onclick = async () => {
            chatPanel.style.display = "none";
            crmPanel.style.display = "none";
            metricsPanel.style.display = "block";

            try {
                // Rota atualizada (/api/dados-painel) para evitar bloqueio do Kaspersky (Erro 499)
                const response = await fetch(`https://[url hospedagem]/api/dados-painel?token=${jwtToken}`);
                const data = await response.json();

                document.getElementById("metric-total").innerText = data.total_atendimentos;
                document.getElementById("metric-tma").innerText = data.tma_minutos + " min";
                document.getElementById("metric-csat").innerText = data.csat + " / 5.0";
                document.getElementById("metric-fcr").innerText = data.taxa_resolucao + "%";

                // Gráfico de Resolução (Pie)
                if (chartRes) chartRes.destroy();
                const ctxRes = document.getElementById('chartResolution').getContext('2d');
                chartRes = new Chart(ctxRes, {
                    type: 'doughnut',
                    data: {
                        labels: ['Resolvido', 'Não Resolvido'],
                        datasets: [{
                            data: [data.taxa_resolucao, 100 - data.taxa_resolucao],
                            backgroundColor: ['#10b981', '#ef4444'],
                            borderWidth: 0
                        }]
                    },
                    options: { 
                        responsive: true, 
                        maintainAspectRatio: false,
                        plugins: { 
                            legend: { position: 'bottom' }, 
                            title: { display: true, text: 'Taxa de Resolução', font: {size: 16} } 
                        } 
                    }
                });

                // Gráfico de CSAT (Barra)
                if (chartCsat) chartCsat.destroy();
                const ctxCsat = document.getElementById('chartCSAT').getContext('2d');
                chartCsat = new Chart(ctxCsat, {
                    type: 'bar',
                    data: {
                        labels: ['Média CSAT'],
                        datasets: [{
                            label: 'Nota',
                            data: [data.csat],
                            backgroundColor: ['#f59e0b'],
                            borderRadius: 6,
                            maxBarThickness: 80
                        }]
                    },
                    options: {
                        responsive: true, 
                        maintainAspectRatio: false,
                        scales: { y: { beginAtZero: true, max: 5 } },
                        plugins: { 
                            legend: { display: false }, 
                            title: { display: true, text: 'Avaliação Média dos Clientes', font: {size: 16} } 
                        }
                    }
                });

            } catch (err) {
                console.error("Erro ao carregar métricas:", err);
                alert("Não foi possível carregar os dados do dashboard.");
            }
        };
    }

    if (btnCloseMetrics) {
        btnCloseMetrics.onclick = () => {
            metricsPanel.style.display = "none";
            chatPanel.style.display = "flex";
            if (activeSessionId) {
                crmPanel.style.display = "flex";
            }
        };
    }

    if (btnExportClients) {
        btnExportClients.onclick = () => {
            window.open(`https://[url hospedagem]/api/export/clients?token=${jwtToken}`, '_blank');
        };
    }
    
    if (btnExportHistory) {
        btnExportHistory.onclick = () => {
            window.open(`https://[url hospedagem]/api/export/history?token=${jwtToken}`, '_blank');
        };
    }

    /* ==========================================
       CONFIGURAÇÃO DO WEBSOCKET
       ========================================== */
    /**
     * Estabelece e gerencia a conexão bidirecional via WebSocket com o servidor.
     */
    function conectarServidor() {
        ws = new WebSocket(`wss://[url hospedagem]/ws/chat/painel_${attendantName}?token=${jwtToken}`);

        ws.onopen = () => {
            console.log("Logado no sistema.");
            telaAguardando();
        };

        ws.onmessage = (event) => {
            const text = event.data;

            if (text.startsWith("SYS_ONLINE_USERS|")) {
                const users = text.split("|")[1].split(",").filter(u => u !== "" && u !== attendantName);
                atualizarMenuTransferencia(users);
                return; 
            }

            const partes = text.split('|');
            if (partes.length >= 3) {
                const msgSessao = partes[0];
                const msgRemetente = partes[1];
                const msgEmail = partes[2] || '-';
                const msgWhats = partes[3] || '-';
                const msgProtocolo = partes[4] || 'Aguardando...';
                const msgStatus = partes[5] || 'ativo';
                const msgAtendente = partes[6] || 'Fila'; 
                const msgTexto = partes.slice(7).join('|') || partes.slice(2).join('|');

                if (msgSessao.startsWith('painel_')) return; 

                // Registra a sessão se for nova
                if (!chats[msgSessao]) {
                    chats[msgSessao] = {
                        nome: (msgRemetente !== 'Atendente' && msgRemetente !== 'Sistema_Nota' && msgRemetente !== 'Sistema') ? msgRemetente : 'Cliente',
                        email: msgEmail,
                        whats: msgWhats,
                        protocolo: msgProtocolo,
                        status: msgStatus,
                        atendente: msgAtendente,
                        messages: [],
                        unread: 0,
                        historicoCarregado: false
                    };
                } else {
                    if (msgEmail !== '-') chats[msgSessao].email = msgEmail;
                    if (msgWhats !== '-') chats[msgSessao].whats = msgWhats;
                    if (msgProtocolo !== 'Aguardando...') chats[msgSessao].protocolo = msgProtocolo;
                    if (msgStatus !== 'ativo') chats[msgSessao].status = msgStatus;
                    chats[msgSessao].atendente = msgAtendente; 
                }

                if (msgTexto === '[UPDATE_ATENDENTE]') {
                    renderClientList();
                    return; 
                }

                if (msgTexto === '[CLIENTE ENCERROU O ATENDIMENTO]') {
                    chats[msgSessao].status = 'encerrado';
                    chats[msgSessao].messages.push({ sender: 'Sistema', text: 'O cliente encerrou o atendimento.' });
                    
                    if (activeSessionId === msgSessao) {
                        renderMessages(); 
                        setTimeout(() => { 
                            if (currentTab === "ativas") btnEncerrados.click(); 
                            verificarFilaEAtender(); 
                        }, 2000); 
                    }
                    renderClientList(); 
                    return; 
                }

                const isRestoredMsg = msgTexto.startsWith('[Sistema: Sessão Restaurada');
                const isTransferMsg = msgTexto.includes('[Sistema: Sessão Transferida');

                if (!isRestoredMsg && !isTransferMsg) {
                    chats[msgSessao].messages.push({ sender: msgRemetente, text: msgTexto });
                    
                    // --- DISPARO DE NOTIFICAÇÃO ---
                    if (msgRemetente !== attendantName && msgRemetente !== 'Sistema' && msgRemetente !== 'Sistema_Nota') {
                        if (document.hidden || activeSessionId !== msgSessao) {
                            dispararNotificacao(msgRemetente, msgTexto);
                        }
                    }
                }

                if (activeSessionId === msgSessao) {
                    renderMessages();
                    currentChatProtocol.innerText = "Protocolo: " + chats[msgSessao].protocolo;
                } else if (chats[msgSessao].status === 'ativo' && !isRestoredMsg) {
                    chats[msgSessao].unread += 1;
                }
                
                renderClientList();
                verificarFilaEAtender(); 
            }
        };
    }

    /* ==========================================
       GESTÃO DE ESTADOS E RENDERIZAÇÃO
       ========================================== */
       
    /**
     * Atualiza o select de transferência com os atendentes online.
     * @param {Array} users - Lista de atendentes conectados.
     */
    function atualizarMenuTransferencia(users) {
        transferSelect.innerHTML = '<option value="">Selecione um colega...</option>';
        if (users.length === 0) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.innerText = "Nenhum atendente online";
            transferSelect.appendChild(opt);
        } else {
            users.forEach(user => {
                const opt = document.createElement("option");
                opt.value = user;
                opt.innerText = user;
                transferSelect.appendChild(opt);
            });
        }
    }

    /**
     * Verifica a fila e abre automaticamente o próximo chat ativo disponível.
     */
    function verificarFilaEAtender() {
        if (userRole === 'master') return;

        if (activeSessionId && chats[activeSessionId] && chats[activeSessionId].status === 'ativo') {
            return;
        }

        const sessoesAtivas = Object.keys(chats).filter(id => chats[id].status === 'ativo');
        
        if (sessoesAtivas.length > 0) {
            abrirChatNaTela(sessoesAtivas[0]);
        } else {
            telaAguardando();
        }
    }

    /**
     * Configura a tela de estado ocioso (aguardando cliente).
     */
    function telaAguardando() {
        activeSessionId = null;
        currentChatTitle.innerText = userRole === 'master' ? "Painel de Auditoria" : "Aguardando próximo cliente...";
        currentChatProtocol.innerText = userRole === 'master' ? "Selecione um chat para inspecionar." : "Fila vazia no momento.";
        
        messagesArea.innerHTML = userRole === 'master' 
            ? '<div class="msg-sistema">Modo Auditoria ativado. Você pode visualizar todos os chats ao vivo.</div>'
            : '<div class="msg-sistema">Você está livre. Assim que um cliente entrar, o chat abrirá aqui automaticamente.</div>';
        
        crmPanel.style.display = "none";
        messageInput.disabled = true;
        sendBtn.disabled = true;
        attachBtn.disabled = true; 
        messageInput.placeholder = "Aguardando...";
        
        renderClientList();
    }

    /* ==========================================
       MANIPULADORES DE EVENTOS DE LISTAGEM E ABAS
       ========================================== */
    btnAtivas.onclick = () => {
        currentTab = "ativas";
        btnAtivas.classList.add("active");
        btnEncerrados.classList.remove("active");
        areaAtivas.style.display = "block";
        areaEncerrados.style.display = "none";
        renderClientList();
    };

    btnEncerrados.onclick = () => {
        currentTab = "encerrados";
        btnEncerrados.classList.add("active");
        btnAtivas.classList.remove("active");
        areaEncerrados.style.display = "block";
        areaAtivas.style.display = "none";
        renderClientList();
    };

    searchProtocol.addEventListener("input", (e) => {
        renderClientList(e.target.value.trim());
    });

    /**
     * Renderiza a lista lateral de clientes (ativos ou encerrados).
     * @param {string} searchQuery - Filtro opcional por protocolo.
     */
    function renderClientList(searchQuery = '') {
        listAtivas.innerHTML = '';
        listEncerrados.innerHTML = '';
        
        for (const [sessaoId, chatData] of Object.entries(chats)) {
            const li = document.createElement('li');
            li.className = `client-item ${activeSessionId === sessaoId ? 'active' : ''}`;
            
            let html = `<span>${chatData.nome}</span>`;
            
            if (userRole === 'master') {
                html += `<br><small style="font-size: 10px; color: #94a3b8; font-weight: bold;">👤 ${chatData.atendente}</small>`;
            }

            if (chatData.unread > 0 && activeSessionId !== sessaoId && chatData.status === 'ativo') {
                html += `<span class="unread-badge">${chatData.unread}</span>`;
            }
            
            li.innerHTML = html;
            
            li.onclick = () => {
                if (chatData.status === 'ativo' && userRole !== 'master') {
                    alert("Modo Automático: Você não pode selecionar clientes manualmente.");
                } else {
                    abrirChatNaTela(sessaoId);
                }
            };
            
            if (chatData.status === 'ativo') {
                listAtivas.appendChild(li);
            } else if (chatData.status === 'encerrado') {
                if (searchQuery === '' || chatData.protocolo.includes(searchQuery)) {
                    listEncerrados.appendChild(li);
                }
            }
        }
    }

    /**
     * Carrega as informações e o histórico de um chat específico na tela principal.
     * @param {string} sessaoId - ID da sessão do cliente.
     */
    async function abrirChatNaTela(sessaoId) {
        metricsPanel.style.display = "none";
        chatPanel.style.display = "flex";
        
        activeSessionId = sessaoId;
        chats[sessaoId].unread = 0; 
        
        currentChatTitle.innerText = `Visualizando: ${chats[sessaoId].nome}`;
        currentChatProtocol.innerText = "Protocolo: " + chats[sessaoId].protocolo;
        
        crmNome.innerText = chats[sessaoId].nome;
        crmEmail.innerText = chats[sessaoId].email;
        crmWhats.innerText = chats[sessaoId].whats;
        crmPanel.style.display = "flex";

        if (userRole === 'master') {
            messageInput.disabled = true;
            sendBtn.disabled = true;
            attachBtn.disabled = true; 
            messageInput.placeholder = "Modo Auditoria: Apenas leitura.";
            btnEncerrarAtendimento.style.display = "none";
            transferArea.style.display = "none";
            noteArea.style.display = "none";
        } else if (chats[sessaoId].status === 'encerrado') {
            messageInput.disabled = true;
            sendBtn.disabled = true;
            attachBtn.disabled = true; 
            messageInput.placeholder = "Atendimento encerrado. Apenas leitura do histórico.";
            btnEncerrarAtendimento.style.display = "none";
            transferArea.style.display = "none";
            noteArea.style.display = "none";
        } else {
            messageInput.disabled = false;
            sendBtn.disabled = false;
            attachBtn.disabled = false; 
            messageInput.placeholder = "Digite sua resposta para o cliente...";
            btnEncerrarAtendimento.style.display = "block";
            transferArea.style.display = "block";
            noteArea.style.display = "block";
            
            if (currentTab !== "ativas") {
                btnAtivas.click();
            }
        }
        
        renderClientList(); 

        // Recuperação do Histórico de Conversa
        if (!chats[sessaoId].historicoCarregado) {
            try {
                const response = await fetch(`https://[url hospedagem]/api/history/${sessaoId}`);
                if (response.ok) {
                    const historico = await response.json();
                    const mensagensRestauradas = [];
                    
                    historico.forEach(msg => {
                        let texto = msg.content.replace(/\[PRT-.*?\] Msg: /, "").replace(/Para .*?: /, "");
                        let remetente = "Sistema";
                        
                        if (msg.sender.startsWith("Sistema_Nota")) {
                            remetente = "Sistema_Nota";
                        } else if (msg.sender.includes("Cliente")) {
                            remetente = chats[sessaoId].nome;
                        } else if (msg.sender === "Atendente") {
                            remetente = "Atendente";
                        }

                        mensagensRestauradas.push({ sender: remetente, text: texto });
                    });
                    
                    chats[sessaoId].messages = mensagensRestauradas.concat(chats[sessaoId].messages);
                    chats[sessaoId].historicoCarregado = true;
                }
            } catch (err) {
                console.error("Erro ao puxar histórico do banco", err);
            }
        }

        renderMessages(); 
    }

    /**
     * Renderiza visualmente os balões de mensagens na tela.
     */
    function renderMessages() {
        messagesArea.innerHTML = '';
        if (!activeSessionId || !chats[activeSessionId]) return;

        chats[activeSessionId].messages.forEach(msg => {
            const msgDiv = document.createElement("div");
            
            let conteudoExibicao = msg.text;
            let heAnexo = false;
            let textoLimpo = msg.text.trim();

            if (textoLimpo.startsWith('[ANEXO|') && textoLimpo.endsWith(']')) {
                heAnexo = true;
                const cleanText = textoLimpo.slice(7, -1); 
                const firstPipe = cleanText.indexOf('|');
                const fileName = cleanText.substring(0, firstPipe);
                const base64Data = cleanText.substring(firstPipe + 1);

                if (base64Data.startsWith('data:image')) {
                    conteudoExibicao = `<br><img src="${base64Data}" alt="${fileName}" style="max-width: 100%; border-radius: 8px; margin-top: 5px; cursor: pointer; border: 1px solid #ddd; max-height: 250px; object-fit: contain;" onclick="window.abrirImagemEmNovaGuia('${base64Data}')">`;
                } else if (base64Data.startsWith('data:application/pdf')) {
                    conteudoExibicao = `<br><a href="${base64Data}" download="${fileName}" style="color: inherit; text-decoration: underline; font-weight: bold; display: inline-block; margin-top: 5px;">📄 Baixar PDF: ${fileName}</a>`;
                }
            }

            if (msg.sender === 'Sistema_Nota') {
                msgDiv.className = "msg-sistema";
                msgDiv.style.backgroundColor = "#fff3cd";
                msgDiv.style.color = "#856404";
                msgDiv.style.border = "1px solid #ffeeba";
                msgDiv.style.padding = "10px";
                msgDiv.style.borderRadius = "5px";
                msgDiv.style.width = "90%";
                msgDiv.innerHTML = `<strong>🔒 Nota Interna:</strong> ${conteudoExibicao}`;
            } 
            else if (msg.sender === 'Sistema') {
                msgDiv.className = "msg-sistema";
                msgDiv.innerText = msg.text;
            } 
            else if (msg.sender === attendantName || msg.sender === 'Atendente') {
                msgDiv.className = "message-box msg-atendente";
                msgDiv.innerHTML = `<strong>Equipe:</strong> ${heAnexo ? conteudoExibicao : msg.text}`;
            } 
            else {
                msgDiv.className = "message-box msg-cliente";
                msgDiv.innerHTML = `<strong>${msg.sender}:</strong> ${heAnexo ? conteudoExibicao : msg.text}`;
            }
            
            messagesArea.appendChild(msgDiv);
        });
        messagesArea.scrollTop = messagesArea.scrollHeight;
    }

    /* ==========================================
       MANIPULADORES DE EVENTOS DE CHAT E AÇÕES
       ========================================== */
       
    messageInput.addEventListener('input', (e) => {
        let texto = e.target.value;
        for (const [atalho, fraseCompleta] of Object.entries(respostasRapidas)) {
            if (texto.includes(atalho)) {
                e.target.value = texto.replace(atalho, fraseCompleta);
            }
        }
    });

    /**
     * Envia a mensagem digitada para o WebSocket.
     */
    function sendMessage() {
        const text = messageInput.value.trim();
        if (text !== "" && activeSessionId) {
            ws.send(`ATENDENTE_REPLY|${activeSessionId}|${text}`);
            messageInput.value = ""; 
        }
    }

    sendBtn.addEventListener("click", sendMessage);
    messageInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            sendMessage();
        }
    });

    attachBtn.onclick = () => fileInput.click();

    fileInput.addEventListener('change', function() {
        const file = this.files[0];
        if (!file) return;

        if (!activeSessionId) {
            alert("Selecione um atendimento ativo primeiro.");
            this.value = '';
            return;
        }

        // Limite de 1MB
        if (file.size > 1 * 1024 * 1024) {
            alert("O arquivo é muito grande. O limite máximo é de 1MB.");
            this.value = '';
            return;
        }

        const validTypes = ['image/png', 'image/jpeg', 'image/jpg', 'application/pdf'];
        if (!validTypes.includes(file.type)) {
            alert("Formato inválido. Apenas PNG, JPG, JPEG e PDF são permitidos.");
            this.value = '';
            return;
        }

        const reader = new FileReader();
        reader.onload = function(e) {
            const base64Data = e.target.result;
            if(ws && ws.readyState === WebSocket.OPEN) {
                ws.send(`ATENDENTE_REPLY|${activeSessionId}|[ANEXO|${file.name}|${base64Data}]`);
            }
        };
        reader.readAsDataURL(file);
        this.value = ''; 
    });

    btnNota.onclick = () => {
        const nota = noteInput.value.trim();
        if (nota && activeSessionId) {
            ws.send(`CMD_NOTA|${activeSessionId}|${nota}`);
            noteInput.value = ""; 
        }
    };

    btnTransferir.onclick = () => {
        const colegaAlvo = transferSelect.value;
        if (!colegaAlvo) {
            return alert("Por favor, selecione um atendente online para transferir.");
        }
        
        if (confirm(`Tem certeza que deseja transferir este cliente para ${colegaAlvo}?`)) {
            ws.send(`CMD_TRANSFERIR|${activeSessionId}|${colegaAlvo}`);
            delete chats[activeSessionId]; 
            verificarFilaEAtender();
            renderClientList();
        }
    };

    btnEncerrarAtendimento.onclick = () => {
        const confirmMsg = "Tem certeza que deseja encerrar este atendimento? O próximo cliente da fila será aberto automaticamente.";
        if (confirm(confirmMsg)) {
            chats[activeSessionId].status = 'encerrado';
            ws.send(`CMD_ENCERRAR|${activeSessionId}`);
            ws.send(`ATENDENTE_REPLY|${activeSessionId}|[ATENDENTE ENCERROU O ATENDIMENTO]`);
            
            if (currentTab === "ativas") {
                btnEncerrados.click();
            }
            verificarFilaEAtender();
            renderClientList();
        }
    };
});
