/* ==========================================
   FUNÇÃO GLOBAL PARA VISUALIZAÇÃO DE IMAGENS
   ========================================== */
// Dribla o bloqueio de segurança do navegador (CORS/Base64) para abrir anexos.
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
   INICIALIZAÇÃO DO WIDGET DE CHAT
   ========================================== */
document.addEventListener("DOMContentLoaded", function() {
    
    // Variáveis de Estado da Sessão
    let sessionId = gerarSessionId();
    let ws = null; 
    let dadosCliente = {}; 
    let encerradoPeloCliente = false; 
    let aguardandoAvaliacao = false;

    function gerarSessionId() {
        return "cliente_" + Math.random().toString(36).substring(2, 9);
    }

    // Estrutura HTML do Widget
    const widgetHTML = `
        <button id="chat-minimized-btn">Dúvidas? Converse com um especialista</button>
        
        <div id="meu-chat-widget">
            <div id="meu-chat-header">
                <span>Atendimento</span>
                <div class="header-actions">
                    <button id="btn-encerrar-chat">Encerrar</button>
                    <button id="btn-minimizar-chat" title="Minimizar">&minus;</button>
                </div>
            </div>
            
            <div id="meu-chat-form-area" style="padding: 20px; display: flex; flex-direction: column; gap: 12px; background-color: #f8f9fa; height: 350px;">
                <p style="font-size: 14px; color: #555; text-align: center; margin-bottom: 5px;">Preencha seus dados para iniciar:</p>
                <input type="text" id="form-nome" placeholder="Seu Nome Completo" style="padding: 10px; border: 1px solid #ccc; border-radius: 5px; outline: none;">
                <input type="email" id="form-email" placeholder="Seu E-mail" style="padding: 10px; border: 1px solid #ccc; border-radius: 5px; outline: none;">
                <input type="text" id="form-whats" placeholder="Seu WhatsApp" style="padding: 10px; border: 1px solid #ccc; border-radius: 5px; outline: none;">
                <button id="btn-iniciar-chat" style="padding: 12px; background-color: #0056b3; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; margin-top: 5px;">Iniciar Conversa</button>
            </div>

            <div id="meu-chat-messages" style="display: none;"></div>
            
            <div id="meu-chat-input-area" style="display: none;">
                <input type="file" id="meu-chat-file-input" accept=".png, .jpg, .jpeg, .pdf" style="display: none;">
                <button id="meu-chat-attach-btn" title="Enviar Arquivo">📎</button>
                
                <input type="text" id="meu-chat-input" placeholder="Escreva sua mensagem...">
                <button id="meu-chat-btn">Enviar</button>
            </div>
        </div>
    `;
    
    // Injeta o widget na página do cliente
    document.body.insertAdjacentHTML('beforeend', widgetHTML);

    /* ==========================================
       REFERÊNCIAS DO DOM
       ========================================== */
    const btnMinimized = document.getElementById('chat-minimized-btn');
    const mainWidget = document.getElementById('meu-chat-widget');
    const btnMinimizarChat = document.getElementById('btn-minimizar-chat');
    const formArea = document.getElementById('meu-chat-form-area');
    const messagesArea = document.getElementById('meu-chat-messages');
    const inputArea = document.getElementById('meu-chat-input-area');
    const btnIniciar = document.getElementById('btn-iniciar-chat');
    const btnEncerrar = document.getElementById('btn-encerrar-chat');
    const inputField = document.getElementById('meu-chat-input');
    const sendButton = document.getElementById('meu-chat-btn');
    
    // Inputs do Formulário Inicial
    const inputNome = document.getElementById('form-nome');
    const inputWhats = document.getElementById('form-whats');
    const inputEmail = document.getElementById('form-email');
    
    // Controles de Anexo
    const fileInput = document.getElementById('meu-chat-file-input');
    const attachBtn = document.getElementById('meu-chat-attach-btn');

    /* ==========================================
       CONTROLES DE INTERFACE BÁSICA (UI)
       ========================================== */
    btnMinimized.onclick = () => {
        btnMinimized.style.display = 'none';
        mainWidget.style.display = 'flex';
    };

    btnMinimizarChat.onclick = () => {
        mainWidget.style.display = 'none';
        btnMinimized.style.display = 'block';
    };

    function resetWidget() {
        const feedbackBox = document.getElementById('meu-chat-feedback');
        if (feedbackBox) feedbackBox.remove();

        sessionId = gerarSessionId();
        encerradoPeloCliente = false;
        aguardandoAvaliacao = false;
        
        inputNome.value = ''; 
        inputEmail.value = ''; 
        inputWhats.value = ''; 
        inputField.value = '';
        messagesArea.innerHTML = '';
        
        formArea.style.display = 'flex';
        messagesArea.style.display = 'none';
        inputArea.style.display = 'none';
        btnEncerrar.style.display = 'none';
        
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.close();
        }
        ws = null;
    }

    /* ==========================================
       SISTEMA DE FEEDBACK (CSAT)
       ========================================== */
    function mostrarAvaliacao() {
        aguardandoAvaliacao = true;
        inputArea.style.display = 'none';
        btnEncerrar.style.display = 'none';

        const avaliacaoHTML = `
            <div id="meu-chat-feedback" style="padding: 15px; background: #ffffff; border-top: 1px solid #eeeeee; display: flex; flex-direction: column; gap: 10px; align-items: center;">
                <p style="font-size: 13px; font-weight: bold; margin: 0; text-align: center; color: #333;">Como você avalia seu atendimento?</p>
                
                <div style="display: flex; gap: 8px; font-size: 28px; cursor: pointer; color: #cccccc;" id="star-rating">
                    <span data-value="1">☆</span>
                    <span data-value="2">☆</span>
                    <span data-value="3">☆</span>
                    <span data-value="4">☆</span>
                    <span data-value="5">☆</span>
                </div>
                
                <div style="font-size: 13px; margin-top: 5px; color: #333;">
                    <label>Seu problema foi resolvido?</label>
                    <select id="select-resolvido" style="padding: 4px; margin-left: 5px; border: 1px solid #ccc; border-radius: 4px;">
                        <option value="sim">Sim</option>
                        <option value="nao">Não</option>
                    </select>
                </div>
                
                <button id="btn-enviar-feedback" style="width: 100%; padding: 10px; background-color: #10b981; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; margin-top: 10px; transition: background-color 0.2s;">Enviar Avaliação</button>
            </div>
        `;
        
        mainWidget.insertAdjacentHTML('beforeend', avaliacaoHTML);
        messagesArea.scrollTop = messagesArea.scrollHeight;
        
        let notaSelecionada = 0;
        const stars = document.querySelectorAll('#star-rating span');
        
        // Lógica de Preenchimento das Estrelas
        stars.forEach(star => {
            star.onclick = function() {
                notaSelecionada = parseInt(this.getAttribute('data-value'));
                stars.forEach(s => {
                    if (parseInt(s.getAttribute('data-value')) <= notaSelecionada) {
                        s.innerText = '★';
                        s.style.color = '#fbbf24'; // Amarelo
                    } else {
                        s.innerText = '☆';
                        s.style.color = '#cccccc';
                    }
                });
            };
        });

        // Disparo da Nota para a API
        document.getElementById('btn-enviar-feedback').onclick = function() {
            if (notaSelecionada === 0) {
                return alert("Por favor, selecione uma nota de 1 a 5 estrelas.");
            }
            
            const resolvido = document.getElementById('select-resolvido').value;
            
            this.innerText = "Enviando...";
            this.disabled = true;

            fetch(`https://[url host]/api/feedback/${sessionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ avaliacao: notaSelecionada, resolvido: resolvido })
            })
            .then(res => res.json())
            .then(() => {
                alert("Obrigado pelo seu feedback! Isso nos ajuda a melhorar.");
                resetWidget();
            })
            .catch(err => {
                console.error("Erro ao enviar avaliação", err);
                alert("Atendimento finalizado. Obrigado!");
                resetWidget();
            });
        };
    }

    /* ==========================================
       VALIDAÇÃO DE FORMULÁRIO (ENTRADA)
       ========================================== */
    inputNome.addEventListener('input', function() { 
        this.value = this.value.replace(/[^a-zA-ZÀ-ÿ\s]/g, '').toUpperCase(); 
    });
    
    inputEmail.addEventListener('input', function() { 
        this.value = this.value.toLowerCase(); 
    });
    
    inputWhats.addEventListener('input', function() {
        let val = this.value.replace(/\D/g, ''); 
        if (val.length > 2 && val[2] !== '9') {
            val = val.slice(0, 2) + '9' + val.slice(2);
        }
        if (val.length > 11) {
            val = val.slice(0, 11);
        }
        
        let formatado = val;
        if (val.length > 2) formatado = `(${val.slice(0,2)}) ${val.slice(2)}`;
        if (val.length > 7) formatado = `(${val.slice(0,2)}) ${val.slice(2,7)}-${val.slice(7)}`;
        this.value = formatado;
    });

    btnIniciar.onclick = function() {
        const nome = inputNome.value.trim();
        const email = inputEmail.value.trim();
        const whats = inputWhats.value.replace(/\D/g, '');

        if(!nome || !email || !whats) {
            return alert("Por favor, preencha todos os campos obrigatórios.");
        }
        if(!/^[^\s@]+@[^\s@]+\.(com|com\.br|br)$/.test(email)) {
            return alert("Por favor, insira um e-mail válido terminado em .com.br ou .br.");
        }
        if(whats.length !== 11) {
            return alert("O WhatsApp deve conter o DDD + o dígito 9 + o número.");
        }

        dadosCliente = { nome, email, whats };
        encerradoPeloCliente = false; 

        formArea.style.display = 'none';
        messagesArea.style.display = 'flex';
        inputArea.style.display = 'flex';
        btnEncerrar.style.display = 'block';

        conectarServidor();
    };

    /* ==========================================
       CONEXÃO COM WEBSOCKET DO SERVIDOR
       ========================================== */
    function conectarServidor() {
        ws = new WebSocket('wss://[url host]/ws/chat/' + sessionId);

        ws.onopen = () => {
            addMessage('Sistema', 'Conectado! Um atendente falará com você em breve.', 'msg-sistema');
            ws.send(`CLIENT_DATA|${dadosCliente.nome}|${dadosCliente.email}|${dadosCliente.whats}|[ENTROU NO CHAT]`);
        };
        
        ws.onmessage = (event) => {
            const text = event.data;
            const partes = text.split('|');
            
            if(partes.length >= 3) {
                const msgSessao = partes[0];
                const msgRemetente = partes[1];
                const msgTexto = partes.slice(2).join('|'); 

                if(msgSessao === sessionId) {
                    // Quando o atendente encerra, solicita a avaliação do cliente
                    if (msgTexto === '[ATENDENTE ENCERROU O ATENDIMENTO]') {
                        addMessage('Sistema', 'O especialista encerrou o seu atendimento.', 'msg-sistema');
                        mostrarAvaliacao();
                        if(ws && ws.readyState === WebSocket.OPEN) {
                            ws.close();
                        }
                        return; 
                    }

                    if (msgRemetente === 'Atendente') {
                        addMessage('Atendente', msgTexto, 'msg-balao msg-atendente');
                    } else if (msgRemetente === dadosCliente.nome) {
                        addMessage('Você', msgTexto, 'msg-balao msg-voce');
                    } else if (msgRemetente === 'Sistema') {
                        addMessage('Sistema', msgTexto, 'msg-sistema');
                    }
                }
            }
        };

        ws.onclose = () => {
            // Impede que a tela apague caso o cliente perca a conexão 
            // mas ainda precise avaliar o atendimento.
            if (!encerradoPeloCliente && !aguardandoAvaliacao) {
                resetWidget();
            }
        };
    }

    /* ==========================================
       GESTÃO DE ENVIO DE MENSAGENS E ANEXOS
       ========================================== */
    btnEncerrar.onclick = function() {
        if(confirm("Deseja realmente encerrar este atendimento?")) {
            encerradoPeloCliente = true; 
            if(ws && ws.readyState === WebSocket.OPEN) {
                ws.send(`CLIENT_DATA|${dadosCliente.nome}|${dadosCliente.email}|${dadosCliente.whats}|[CLIENTE ENCERROU O ATENDIMENTO]`);
                ws.close();
            }
            mostrarAvaliacao();
        }
    };

    attachBtn.onclick = () => fileInput.click();

    fileInput.addEventListener('change', function() {
        const file = this.files[0];
        if (!file) return;

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
                ws.send(`CLIENT_DATA|${dadosCliente.nome}|${dadosCliente.email}|${dadosCliente.whats}|[ANEXO|${file.name}|${base64Data}]`);
            }
        };
        reader.readAsDataURL(file);
        this.value = ''; 
    });

    function sendMessage() {
        const text = inputField.value.trim();
        if(text !== '' && ws && ws.readyState === WebSocket.OPEN) {
            ws.send(`CLIENT_DATA|${dadosCliente.nome}|${dadosCliente.email}|${dadosCliente.whats}|${text}`);
            inputField.value = ''; 
        }
    }

    sendButton.onclick = sendMessage;
    
    inputField.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    /* ==========================================
       RENDERIZAÇÃO DE MENSAGENS NA TELA
       ========================================== */
    function addMessage(sender, text, classes) {
        const msgDiv = document.createElement('div');
        msgDiv.className = classes;
        
        if (sender === 'Sistema') {
            msgDiv.innerText = text;
        } else {
            // Lógica para detectar e renderizar anexos (Imagem ou PDF)
            if (text.startsWith('[ANEXO|') && text.endsWith(']')) {
                const cleanText = text.slice(7, -1); 
                const firstPipe = cleanText.indexOf('|');
                const fileName = cleanText.substring(0, firstPipe);
                const base64Data = cleanText.substring(firstPipe + 1);

                if (base64Data.startsWith('data:image')) {
                    msgDiv.innerHTML = `<strong>${sender}:</strong><br>
                        <img src="${base64Data}" alt="${fileName}" 
                        style="max-width: 100%; border-radius: 8px; margin-top: 5px; cursor: pointer; border: 1px solid #ddd;" 
                        onclick="window.abrirImagemEmNovaGuia('${base64Data}')">`;
                } else if (base64Data.startsWith('data:application/pdf')) {
                    msgDiv.innerHTML = `<strong>${sender}:</strong><br>
                        <a href="${base64Data}" download="${fileName}" 
                        style="color: #0056b3; text-decoration: underline; font-weight: bold; display: inline-block; margin-top: 5px;">
                        📄 Baixar PDF: ${fileName}</a>`;
                }
            } else {
                msgDiv.innerHTML = `<strong>${sender}:</strong> ${text}`;
            }
        }
        
        messagesArea.appendChild(msgDiv);
        messagesArea.scrollTop = messagesArea.scrollHeight;
    }
});
