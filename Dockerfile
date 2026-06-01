# ==========================================
# CONFIGURAÇÃO DA IMAGEM BASE
# ==========================================
# Usa uma versão leve do Python para otimizar o tamanho final da imagem
FROM python:3.10-slim

# ==========================================
# DIRETÓRIO DE TRABALHO
# ==========================================
# Define a pasta de trabalho (working directory) dentro do container
WORKDIR /app

# ==========================================
# INSTALAÇÃO DE DEPENDÊNCIAS
# ==========================================
# Copia apenas o arquivo de dependências primeiro.
# Isso otimiza o cache do Docker, evitando reinstalar tudo se o código mudar.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# CÓDIGO FONTE E EXPOSIÇÃO DE PORTA
# ==========================================
# Copia todo o código-fonte do seu projeto para dentro do container
COPY . .

# Expõe a porta 8000 para que o host (sua máquina) possa acessar a API
EXPOSE 8000

# ==========================================
# COMANDO DE INICIALIZAÇÃO
# ==========================================
# Comando padrão executado ao iniciar o container (inicia o servidor Uvicorn)
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]