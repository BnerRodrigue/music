"""
app.py
======
Servidor Flask do Analisador de Estrutura Musical.

Regras importantes deste MVP:
  - SEM login / autenticacao.
  - SEM banco de dados.
  - SEM persistencia de arquivos: o MP3 enviado e gravado apenas em um
    arquivo TEMPORARIO, processado, e IMEDIATAMENTE apagado (bloco
    try/finally). Nada fica salvo em disco depois da requisicao.
  - Todo o estado (nomes das secoes escolhidos pelo usuario, etc.) vive
    apenas no navegador (JavaScript), durante a sessao da pagina.
"""

import os
import tempfile

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import audio_analysis

# Pasta do frontend (HTML/CSS/JS estatico)
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

app = Flask(__name__, static_folder=None)

# CORS explicito: permite que o frontend (Netlify, em outro dominio) chame
# esta API. allow_headers/methods amplos evitam bloqueios de preflight (OPTIONS).
CORS(app, resources={r"/api/*": {"origins": "*"}},
     methods=["GET", "POST", "OPTIONS"],
     allow_headers=["Content-Type"])

# Extensoes de audio aceitas nesta versao do MVP
ALLOWED_EXTENSIONS = {'.mp3'}
MAX_CONTENT_LENGTH = 30 * 1024 * 1024  # 30 MB - limite razoavel para um MVP
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH


# ---------------------------------------------------------------------------
# Rotas de frontend (servem os arquivos estaticos)
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'static'), path)


# ---------------------------------------------------------------------------
# Rota principal da API: recebe o MP3 e devolve a analise em JSON
# ---------------------------------------------------------------------------

@app.route('/api/analyze', methods=['POST'])
def analyze_audio():
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado.'}), 400

    uploaded_file = request.files['file']

    if uploaded_file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado.'}), 400

    ext = os.path.splitext(uploaded_file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': 'Formato nao suportado. Envie um arquivo .mp3'}), 400

    # Arquivo temporario: criado, usado e apagado dentro desta mesma requisicao.
    # Nao ha qualquer persistencia em disco depois da resposta ser enviada.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp3')
    try:
        with os.fdopen(tmp_fd, 'wb') as tmp_file:
            uploaded_file.save(tmp_file)

        result = audio_analysis.analyze(tmp_path)
        result['filename'] = uploaded_file.filename

        return jsonify(result), 200

    except Exception as exc:
        # Em um MVP, devolvemos a mensagem de erro de forma simples e direta
        return jsonify({'error': f'Falha ao analisar o audio: {exc}'}), 500

    finally:
        # Garante que o arquivo temporario seja removido mesmo se algo falhar
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.errorhandler(Exception)
def handle_any_error(exc):
    """
    Rede de seguranca: se qualquer erro nao previsto acontecer (ex.: estouro
    de memoria ao processar um MP3 muito longo), o Flask ainda responde com
    um JSON de erro (com os headers de CORS aplicados normalmente) em vez de
    o worker simplesmente cair sem resposta - e isso ultimo que faz o
    navegador exibir um erro de CORS mesmo quando o CORS esta certo.
    """
    return jsonify({'error': f'Erro interno ao processar a requisicao: {exc}'}), 500


if __name__ == '__main__':
    # debug=True apenas para desenvolvimento local.
    # Em producao (Render), quem sobe o servidor e o gunicorn (ver Procfile),
    # este bloco so roda quando voce executa "python app.py" na sua maquina.
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, port=port)
