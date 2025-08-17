from flask import Flask, request, jsonify, render_template
import gunicorn
import rapidfuzz
import requests
import re
import os
import aiml
import json
from rapidfuzz import fuzz
from datetime import datetime  # Importar datetime

app = Flask(__name__)

if __name__ == '__main__':
    app.run()

# Caminhos dos arquivos JSON
EXEMPLO_FILE_PATH = "exemplo.json"
USUARIO_FILE_PATH = "usuario.json"  # Assumindo que este é o segundo arquivo JSON mencionado
SUGESTOES_FILE_PATH = "sugestoes.json"  # Novo arquivo para as sugestões

# Carregar o arquivo de sugestões ao iniciar o aplicativo
sugestoes_respostas = {}
try:
    with open(SUGESTOES_FILE_PATH, "r", encoding="utf-8") as f:
        sugestoes_data = json.load(f)
        sugestoes_respostas = sugestoes_data.get("respostas_sugeridas", {})
except FileNotFoundError:
    print(f"Arquivo '{SUGESTOES_FILE_PATH}' não encontrado. O chatbot não oferecerá sugestões automáticas.")
except Exception as e:
    print(f"Erro ao carregar '{SUGESTOES_FILE_PATH}': {e}")

if not os.path.exists("aiml"):
    print("A pasta 'aiml' não existe. Crie a pasta e coloque seus arquivos AIML nela.")
else:
    arquivos = os.listdir("aiml")
    print("Arquivos AIML encontrados:", arquivos)

# Inicializar o AIML
bot = aiml.Kernel()


def carregar_aiml():
    for root, dirs, files in os.walk("aiml"):
        for file in files:
            if file.endswith(".aiml"):
                caminho = os.path.join(root, file)
                print(f"Carregando: {caminho}")
                try:
                    bot.learn(caminho)
                except Exception as e:
                    print(f"Erro ao carregar {caminho}: {e}")


carregar_aiml()


def atualizar_variaveis_aiml(dados_usuario):
    experiencias_texto = " | ".join([exp.get('conteudo', '') for exp in dados_usuario])
    bot.setBotPredicate("experiencias", experiencias_texto)


# Função para carregar experiências de ambos os arquivos
def carregar_experiencias():
    todas_experiencias = []
    for path in [EXEMPLO_FILE_PATH, USUARIO_FILE_PATH]:  # Adicione usuario.json aqui
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        todas_experiencias.extend(data)
                    else:
                        print(f"Aviso: O arquivo '{path}' não contém uma lista no nível raiz.")
        except json.JSONDecodeError:
            print(f"Erro de decodificação JSON no arquivo: {path}. Verifique a formatação.")
        except Exception as e:
            print(f"Erro ao carregar experiências de '{path}': {e}")
    return todas_experiencias


# Função para obter resposta personalizada do JSON
def resposta_experiencia_usuario(mensagem):
    todas_experiencias = carregar_experiencias()  # Carrega de ambos os arquivos
    mensagem_lower = mensagem.lower()
    for exp in todas_experiencias:
        titulo = exp.get("titulo", "").lower()
        score = fuzz.partial_ratio(titulo, mensagem_lower)
        if score > 80:  # ajuste a sensibilidade conforme necessário
            return exp.get('conteudo'), titulo  # Retorna o conteúdo e o título para buscar sugestões
    return None, None  # Retorna None, None se não encontrar


# Função para gerar resposta baseada na emoção do usuário
def gerar_resposta(mensagem, emocao_usuario):
    if emocao_usuario == "feliz":
        return "Que bom que você está feliz! Como posso ajudar você hoje?"
    elif emocao_usuario == "curioso":
        return "Fico feliz com sua curiosidade! Sobre o que gostaria de saber mais?"
    elif emocao_usuario == "triste":
        return "Sinto muito que você esteja triste. Posso ajudar em alguma coisa?"
    else:
        return None


@app.route("/")
def index():
    return render_template("chat.html")


@app.route("/salvar", methods=["POST"])
def salvar_experiencia():
    data = request.json
    titulo = data.get("titulo")
    historia = data.get("historia")
    experiencia = {
        "titulo": titulo,
        "conteudo": historia,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Salvar em usuario.json (ou outro arquivo específico para novas entradas do usuário)
    try:
        current_usuario_data = []
        if os.path.exists(USUARIO_FILE_PATH):
            with open(USUARIO_FILE_PATH, "r", encoding="utf-8") as f:
                current_usuario_data = json.load(f)
                if not isinstance(current_usuario_data, list):  # Garante que é uma lista
                    current_usuario_data = []
        current_usuario_data.append(experiencia)
        with open(USUARIO_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(current_usuario_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Erro ao salvar em {USUARIO_FILE_PATH}:", e)
        return jsonify({"message": "Erro ao salvar a experiência."})

    # Atualizar variáveis AIML (recarregar todas as experiências, incluindo a nova)
    todas_experiencias = carregar_experiencias()
    atualizar_variaveis_aiml(todas_experiencias)

    return jsonify({"message": "Experiência registrada com sucesso!"})


@app.route("/exemplo_experiencia", methods=["GET"])
def exemplo_experiencia():
    experiencias = carregar_experiencias()  # Carrega de ambos os arquivos
    if experiencias:
        # Encontre a experiência mais recente (ou qualquer uma para exemplo)
        exemplo = experiencias[-1]
        conteudo_exemplo = exemplo.get("conteudo", "Nenhuma experiência registrada.")
        return jsonify({"exemplo": conteudo_exemplo})
    else:
        return jsonify({"exemplo": "Nenhuma experiência registrada."})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message", "").strip()
    emocao_usuario = data.get("emotion", "").lower()

    user_input_lower = user_input.lower()

    # Inicializa as sugestões de resposta
    sugestoes = []

    if not user_input:
        return jsonify({"response": "Por favor, escreva algo!", "source": "Bot"})

    # =========================
    # Lógica para registrar experiência (prioridade alta)
    # =========================
    if re.search(r'(registrar|adicionar|guardar)\s+experiencia', user_input_lower):
        experiencia_match = re.search(r'(?:registrar|adicionar|guardar)\s+experiencia[:\-]?\s*(.+)', user_input_lower)
        if experiencia_match:
            nova_experiencia = experiencia_match.group(1).strip()
            # Salvar no arquivo usuario.json
            current_usuario_data = []
            if os.path.exists(USUARIO_FILE_PATH):
                with open(USUARIO_FILE_PATH, "r", encoding="utf-8") as f:
                    current_usuario_data = json.load(f)
                    if not isinstance(current_usuario_data, list):
                        current_usuario_data = []
            current_usuario_data.append({
                "titulo": nova_experiencia,
                "conteudo": nova_experiencia,
                "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            try:
                with open(USUARIO_FILE_PATH, "w", encoding="utf-8") as f:
                    json.dump(current_usuario_data, f, ensure_ascii=False, indent=4)
                # Atualizar variáveis AIML (recarregar tudo)
                todas_experiencias = carregar_experiencias()
                atualizar_variaveis_aiml(todas_experiencias)
                return jsonify({"response": "Experiência registrada com sucesso!", "source": "Registro"})
            except Exception as e:
                print("Erro ao salvar experiência:", e)
                return jsonify({"response": "Erro ao salvar a experiência."})
        else:
            return jsonify({"response": "Por favor, informe a experiência que deseja registrar."})

    # =========================
    # Tentar responder com AIML
    # =========================
    resposta_aiml = None
    try:
        # A resposta do AIML é case-sensitive para o pattern, mas geralmente queremos
        # checar a sugestão baseada no pattern exato definido no AIML.
        # Converter para maiúsculas para tentar bater com os patterns comuns do AIML.
        pattern_check = user_input.upper()
        resposta_aiml = bot.respond(user_input)

        if resposta_aiml:
            # Verifica se há sugestões para o padrão AIML correspondente
            if "AIML" in sugestoes_respostas and pattern_check in sugestoes_respostas["AIML"]:
                sugestoes = sugestoes_respostas["AIML"][pattern_check]
            return jsonify({"response": resposta_aiml, "source": "AIML", "suggestions": sugestoes})
    except Exception as e:
        print(f"Erro no AIML: {e}")
        resposta_aiml = None  # Garante que a variável é None em caso de erro

    # =========================
    # Se AIML não respondeu, tentar com experiências JSON (correspondência aproximada)
    # =========================
    conteudo_experiencia, titulo_experiencia_encontrado = resposta_experiencia_usuario(user_input)
    if conteudo_experiencia:

        if "JSON" in sugestoes_respostas and titulo_experiencia_encontrado.capitalize() in sugestoes_respostas["JSON"]:
            sugestoes = sugestoes_respostas["JSON"][titulo_experiencia_encontrado.capitalize()]
        return jsonify(
            {"response": f"{conteudo_experiencia}",
             "source": "Experiência", "suggestions": sugestoes})
    '''"Claro, aqui está uma explicação baseada em experiências reais:'''
    # =========================
    # Se não encontrou no JSON de experiência aproximada, tentar busca por título exato
    # =========================
    historia_exata = procurar_em_arquivo(user_input)  # usa a função auxiliar para buscar nos dois arquivos
    if historia_exata:

        if "JSON" in sugestoes_respostas and user_input.capitalize() in sugestoes_respostas["JSON"]:
            sugestoes = sugestoes_respostas["JSON"][user_input.capitalize()]
        return jsonify({"response": historia_exata, "source": "Experiência", "suggestions": sugestoes})

    # =========================
    # Detectar pedido de história por título (regex mais genérico)
    # =========================
    match_titulo = re.search(r'(?:de|sobre|a história de|fale sobre)\s+(.+)', user_input_lower)
    if match_titulo:
        titulo_pedido = match_titulo.group(1).strip()
        # Alterar para usar a função local ""procurar_em_arquivo"
        historia_encontrada = procurar_em_arquivo(titulo_pedido)
        if historia_encontrada:
            # Se a história for encontrada, verifique se há sugestões no JSON de sugestões
            if "JSON" in sugestoes_respostas and titulo_pedido.capitalize() in sugestoes_respostas["JSON"]:
                sugestoes = sugestoes_respostas["JSON"][titulo_pedido.capitalize()]
            return jsonify({"response": historia_encontrada, "source": "Experiência", "suggestions": sugestoes})
        # Note: Se não encontrar, a execução continua para a próxima etapa (resposta emocional ou genérica)
        # para evitar retornar "não encontrei" antes de outras verificações.

    # =========================
    # Tentar gerar resposta emocional
    # =========================
    resposta_emocional = gerar_resposta(user_input, emocao_usuario)
    if resposta_emocional:
        return jsonify({"response": resposta_emocional, "source": "Emocional"})

    # =========================
    # Resposta genérica se nada mais funcionar
    # =========================
    return jsonify({"response": "Desculpe, não entendi sua mensagem. Pode reformular?", "source": "Bot"})


# Função auxiliar para buscar história em ambos os arquivos
def procurar_em_arquivo(titulo_buscado):
    titulo_lower = titulo_buscado.lower()
    for path in [EXEMPLO_FILE_PATH, USUARIO_FILE_PATH]:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    historias = json.load(f)
                    if isinstance(historias, list):
                        for historia in historias:
                            # Tenta correspondência exata para títulos
                            if historia.get("titulo", "").lower() == titulo_lower:
                                return historia.get("conteudo")
        except Exception as e:
            print(f"Erro ao buscar em {path}: {e}")
    return None


# Endpoint para buscar história por título (agora usando a função auxiliar)
@app.route("/historia_por_titulo", methods=["POST"])
def historia_por_titulo():
    data = request.json
    titulo = data.get("titulo", "").strip()
    conteudo = procurar_em_arquivo(titulo)
    if conteudo:
        sugestoes = []
        if "JSON" in sugestoes_respostas and titulo.capitalize() in sugestoes_respostas["JSON"]:
            sugestoes = sugestoes_respostas["JSON"][titulo.capitalize()]
        return jsonify({"historia": conteudo, "suggestions": sugestoes})
    return jsonify({"historia": None, "suggestions": []})



# Remove the test_aiml route and `perguntas_automaticas` dictionary definition
# and related print statements here as they conflict with the main logic.

if __name__ == "__main__":
    # Carregar experiências ao iniciar
    todas_experiencias_iniciais = carregar_experiencias()
    atualizar_variaveis_aiml(todas_experiencias_iniciais)
    app.run(host="127.0.0.1", port=5000, debug=True)