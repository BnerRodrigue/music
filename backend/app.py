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
from werkzeug.exceptions import HTTPException

import audio_analysis

# Pasta do frontend (HTML/CSS/JS estatico)
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

app = Flask(__name__, static_folder=None)

# CORS feito manualmente (sem flask-cors) - ver funcao add_cors_headers() logo
# abaixo. Evita qualquer conflito entre bibliotecas na hora de decidir quem
# adiciona o header em cada resposta.

# "Aquece" as funcoes de audio (forca a compilacao JIT do numba) antes do
# servidor comecar a aceitar requisicoes de verdade - ver comentario
# detalhado na funcao audio_analysis.warmup(). Isso acontece uma unica vez,
# na inicializacao do processo.
audio_analysis.warmup()

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

@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def analyze_audio():
    # Requisicao de "preflight" do CORS - o navegador manda isso antes do
    # POST de verdade para perguntar se pode prosseguir. Respondemos vazio,
    # com status 204, e o after_request abaixo adiciona os headers de CORS.
    if request.method == 'OPTIONS':
        return '', 204

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
        # Registra o traceback completo no log do servidor (aba "Logs" do
        # Render) para facilitar o diagnostico, alem de devolver uma
        # mensagem resumida ao navegador.
        app.logger.exception('Falha ao analisar o audio')
        return jsonify({'error': f'Falha ao analisar o audio: {exc}'}), 500

    finally:
        # Garante que o arquivo temporario seja removido mesmo se algo falhar
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.errorhandler(Exception)
def handle_any_error(exc):
    """
    Rede de seguranca: se qualquer erro NAO PREVISTO acontecer (ex.: estouro
    de memoria ao processar um MP3 muito longo), o Flask ainda responde com
    um JSON de erro (com os headers de CORS aplicados normalmente) em vez de
    o worker simplesmente cair sem resposta - e isso ultimo que faz o
    navegador exibir um erro de CORS mesmo quando o CORS esta certo.

    Erros HTTP "normais" do proprio Flask (404 pagina nao encontrada, 405
    metodo nao permitido, etc.) NAO passam por aqui como erro 500 - mantemos
    o status original deles, so garantindo que o CORS tambem seja aplicado.

    Tambem registramos o traceback completo no log do servidor (visivel na
    aba "Logs" do Render), pois a mensagem enviada ao navegador e resumida.
    """
    if isinstance(exc, HTTPException):
        return exc

    app.logger.exception('Erro nao tratado ao processar requisicao')
    return jsonify({'error': f'Erro interno ao processar a requisicao: {exc}'}), 500


@app.after_request
def add_cors_headers(response):
    """
    Reforco manual dos headers de CORS em TODA resposta que passa pelo
    Flask (sucesso, erro 4xx/5xx tratado, ou preflight OPTIONS) - garante
    que o navegador nunca bloqueie por falta desse header, independente de
    qualquer comportamento da biblioteca flask-cors.
    """
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


if __name__ == '__main__':
    # debug=True apenas para desenvolvimento local.
    # Em producao (Render), quem sobe o servidor e o gunicorn (ver Procfile),
    # este bloco so roda quando voce executa "python app.py" na sua maquina.
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, port=port)
