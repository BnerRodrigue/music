# Analisador de Estrutura Musical (MVP)

MVP que detecta automaticamente a estrutura de uma musica (MP3) usando
tecnicas de Music Information Retrieval (Beat Tracking, Chroma Features,
Self-Similarity Matrix e Segmentacao Estrutural via Laplacian Segmentation),
sem nenhuma IA generativa. O usuario renomeia manualmente cada secao
detectada e pode exportar o resultado em TXT.

Sem login. Sem banco de dados. Sem persistencia de arquivos: tudo vive
apenas durante a sessao da pagina no navegador.

## Estrutura do projeto

```
music-structure-analyzer/
├── backend/
│   ├── app.py                # Servidor Flask (rotas + upload temporario)
│   ├── audio_analysis.py      # Todo o processamento MIR (librosa/scipy/sklearn)
│   └── requirements.txt
└── frontend/
    ├── index.html
    └── static/
        ├── css/style.css
        └── js/script.js
```

## Como rodar (passo a passo)

1. Tenha Python 3.10+ instalado.
2. Abra um terminal na pasta `music-structure-analyzer/backend`.
3. (Recomendado) crie um ambiente virtual:
   ```
   python -m venv venv
   ```
4. Ative o ambiente virtual:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`
5. Instale as dependencias:
   ```
   pip install -r requirements.txt
   ```
6. Também é necessário ter o **ffmpeg** instalado no sistema (usado internamente
   para decodificar MP3):
   - Windows: baixe em https://ffmpeg.org e adicione ao PATH.
   - macOS: `brew install ffmpeg`
   - Linux (Debian/Ubuntu): `sudo apt install ffmpeg`
7. Inicie o servidor:
   ```
   python app.py
   ```
8. Abra o navegador em: `http://localhost:5000`

## Deploy em producao (frontend no Netlify + backend no Render)

O Netlify so hospeda arquivos estaticos e funcoes serverless leves. O
backend deste projeto usa librosa/scipy/scikit-learn para analisar audio,
o que nao roda dentro dos limites do Netlify Functions. Por isso a
arquitetura de producao e:

    Frontend (HTML/CSS/JS) -> Netlify
    Backend (Flask + analise de audio) -> Render.com

### Passo 1 - Subir o codigo para o GitHub

1. Crie um repositorio novo no GitHub (pode ser privado).
2. Envie TODA a pasta `music-structure-analyzer` (com `backend/`,
   `frontend/`, `netlify.toml` etc.) para esse repositorio.

### Passo 2 - Hospedar o backend no Render

1. Acesse https://render.com e crie uma conta (pode usar login do GitHub).
2. Clique em "New +" -> "Web Service".
3. Selecione o repositorio que voce acabou de criar.
4. Em "Root Directory", digite: `backend`
5. Em "Runtime", selecione: `Python 3`
6. Em "Build Command", digite: `pip install -r requirements.txt`
7. Em "Start Command", digite: `gunicorn app:app --timeout 120`
8. Escolha o plano "Free".
9. Clique em "Create Web Service" e aguarde o deploy terminar.
10. Quando terminar, copie a URL gerada, algo como:
    `https://music-structure-analyzer.onrender.com`

Observacao: no plano gratuito do Render o servidor "dorme" apos um tempo
sem uso, entao a primeira requisicao depois de um tempo parado pode
demorar ~30-60s para acordar. Isso e normal.

### Passo 3 - Editar 1 arquivo antes de publicar o frontend

1. Abra o arquivo `frontend/static/js/config.js`.
2. Troque a linha:
   ```
   window.API_BASE_URL = '';
   ```
   por (usando a URL que voce copiou do Render, SEM barra no final):
   ```
   window.API_BASE_URL = 'https://music-structure-analyzer.onrender.com';
   ```
3. Salve o arquivo e envie essa alteracao para o GitHub (`git add`,
   `git commit`, `git push`).

### Passo 4 - Hospedar o frontend no Netlify

**Opcao A - via GitHub (recomendado, com deploy automatico):**

1. Acesse https://app.netlify.com e crie uma conta (pode usar login do GitHub).
2. Clique em "Add new site" -> "Import an existing project".
3. Selecione o mesmo repositorio do GitHub.
4. O Netlify vai detectar o arquivo `netlify.toml` automaticamente
   (base = `frontend`, publish = `.`). Nao precisa mudar nada.
5. Clique em "Deploy site".
6. Pronto! O Netlify vai te dar uma URL publica, algo como:
   `https://seu-projeto.netlify.app`

**Opcao B - drag and drop (mais rapido, sem deploy automatico):**

1. Acesse https://app.netlify.com/drop
2. Arraste a pasta `frontend` (a pasta inteira) para a area indicada.
3. Pronto, o Netlify ja publica e devolve a URL.
   (Se atualizar o codigo depois, arraste a pasta de novo.)

### Passo 5 - Testar

1. Abra a URL do Netlify no navegador.
2. Envie um MP3 e clique em "Analisar Musica".
3. Se aparecer erro de rede, confira se `window.API_BASE_URL` em
   `config.js` esta com a URL certa do Render e sem barra no final.

## Limitações conhecidas do MVP (pontos de evolucao futura)

- Compasso: assumido como 4/4 por padrao (deteccao real de compasso
  exigiria downbeat tracking, ex.: madmom).
- Numero de "tipos" de secao (A, B, C...): estimado automaticamente por
  heuristica de eigengap, pode nao ser perfeito em todas as musicas.
- Proximos passos sugeridos: sincronizacao de letra, deteccao automatica
  de refrao (por frequencia de repeticao), exportacao em PDF.
