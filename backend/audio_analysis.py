"""
audio_analysis.py
==================
Modulo de Music Information Retrieval (MIR) responsavel por analisar
um arquivo de audio (MP3) e extrair, de forma totalmente algoritmica
(sem IA generativa, sem modelos treinados em texto):

    - Duracao
    - BPM (tempo)
    - Tom (key) aproximado
    - Compasso aproximado (assumido 4/4 por padrao - ver observacao abaixo)
    - Estrutura da musica (secoes) via:
        * Chroma features (harmonia)
        * Self-Similarity Matrix (matriz de autossimilaridade)
        * Segmentacao estrutural via Laplacian Segmentation
          (McFee & Ellis, 2014 - metodo classico usado no ecossistema librosa)
        * Deteccao de repeticoes (secoes com o mesmo cluster = mesma letra)

NENHUM arquivo e salvo em disco de forma permanente: o arquivo enviado
e processado inteiramente em memoria/arquivo temporario e descartado
logo em seguida (ver app.py).

Observacao sobre compasso (time signature):
    A deteccao robusta de compasso (3/4, 6/8, etc.) exige tecnicas mais
    avancadas (ex.: madmom DBNBeatTracker + downbeat tracking). Nesta
    versao MVP assumimos 4/4 como padrao (o mais comum em musica
    popular/gospel) e deixamos um ponto de extensao claro para o futuro.

Observacao sobre memoria (hospedagens gratuitas, ex.: Render free - 512MB):
    O librosa usa a biblioteca "numba" para compilar (JIT) algumas de suas
    funcoes internas na primeira chamada, o que pode consumir bastante
    memoria momentaneamente. Em ambientes com pouca RAM isso pode causar
    "out of memory" (processo morto com SIGKILL). Por isso desativamos o
    JIT do numba abaixo ANTES de importar o librosa - fica um pouco mais
    lento, porem muito mais leve em memoria, o que e o compromisso certo
    para um MVP hospedado em plano gratuito.
"""

import os
os.environ.setdefault('NUMBA_DISABLE_JIT', '1')

import numpy as np
import librosa
import scipy.ndimage
import scipy.linalg
from sklearn.cluster import KMeans

# ---------------------------------------------------------------------------
# Constantes de configuracao da analise
# ---------------------------------------------------------------------------

SAMPLE_RATE = 22050          # taxa de amostragem usada para todo o processamento
BEATS_PER_MEASURE = 4        # assumimos compasso 4/4 (ver observacao no topo do arquivo)
MIN_SEGMENT_MEASURES = 2     # segmentos menores que isso sao fundidos ao vizinho (reduz ruido)
MAX_CLUSTERS = 8             # numero maximo de "tipos" de secao (A, B, C...) a considerar
MIN_CLUSTERS = 3             # numero minimo de "tipos" de secao a considerar
MAX_ANALYSIS_SECONDS = 180   # limite de seguranca (3 min) para nao estourar memoria/tempo
                              # em hospedagens com poucos recursos (ex.: plano free do Render)

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Perfis tonais de Krumhansl-Schmuckler (usados para estimar o tom da musica
# a partir da distribuicao media de energia entre as 12 classes de notas)
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                           2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                           2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def load_audio(file_path):
    """Carrega o audio em mono, na sample rate padrao do projeto.
    Limita a duracao analisada (MAX_ANALYSIS_SECONDS) para nao estourar
    memoria/tempo de CPU em hospedagens com poucos recursos."""
    y, sr = librosa.load(file_path, sr=SAMPLE_RATE, mono=True,
                          duration=MAX_ANALYSIS_SECONDS)
    return y, sr


def get_duration(y, sr):
    """Duracao total da faixa, em segundos."""
    return float(librosa.get_duration(y=y, sr=sr))


def estimate_tempo_and_beats(y, sr):
    """
    Beat tracking: estima o BPM e os instantes (em frames/segundos) de cada
    batida da musica. Usado como base para sincronizar as features de
    harmonia e para calcular a quantidade aproximada de compassos.
    """
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # librosa pode retornar tempo como array em algumas versoes
    tempo = float(np.atleast_1d(tempo)[0])
    return round(tempo), beat_frames, beat_times


def estimate_key(y, sr):
    """
    Estimativa de tom (key) usando o algoritmo de Krumhansl-Schmuckler:

    1. Calculamos o "chromagram" (energia em cada uma das 12 classes de nota
       - C, C#, D, ... - ao longo do tempo).
    2. Tiramos a media temporal -> um "perfil tonal" da musica inteira.
    3. Comparamos (correlacao) esse perfil com os 12 perfis maiores e os 12
       perfis menores de Krumhansl (cada um rotacionado para uma tonica
       diferente).
    4. O perfil com maior correlacao indica o tom mais provavel.
    """
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)

    best_score = -np.inf
    best_key = 'C'
    best_mode = 'Maior'

    for i in range(12):
        major_rot = np.roll(MAJOR_PROFILE, i)
        minor_rot = np.roll(MINOR_PROFILE, i)

        major_score = np.corrcoef(chroma_mean, major_rot)[0, 1]
        minor_score = np.corrcoef(chroma_mean, minor_rot)[0, 1]

        if major_score > best_score:
            best_score = major_score
            best_key = NOTE_NAMES[i]
            best_mode = 'Maior'
        if minor_score > best_score:
            best_score = minor_score
            best_key = NOTE_NAMES[i]
            best_mode = 'Menor'

    return f"{best_key} {best_mode}"


def _estimate_num_clusters(evals):
    """
    Heuristica de "eigengap": olhamos para os menores autovalores do
    Laplaciano e escolhemos k logo apos o maior "salto" (gap) entre eles.
    Isso aproxima quantos "tipos" distintos de secao existem na musica,
    sem que o usuario precise informar esse numero manualmente.
    """
    evals = np.sort(evals)[:MAX_CLUSTERS + 2]
    gaps = np.diff(evals)
    # ignoramos o primeiro autovalor (sempre ~0) na busca do maior salto
    k = int(np.argmax(gaps[MIN_CLUSTERS - 1:MAX_CLUSTERS]) + MIN_CLUSTERS)
    return max(MIN_CLUSTERS, min(k, MAX_CLUSTERS))


def structural_segmentation(y, sr, beat_frames):
    """
    Segmentacao estrutural via "Laplacian Segmentation" (McFee & Ellis, 2014).

    Ideia geral:
      1. Extraimos Chroma (harmonia) sincronizado por batida -> mais estavel
         que analisar frame a frame.
      2. Construimos uma Self-Similarity Matrix (matriz de recorrencia) que
         mede o quao parecido cada instante da musica e de todos os outros.
      3. Construimos tambem uma matriz de similaridade "local" (sequencial),
         baseada em MFCC, que captura a continuidade timbrica.
      4. Combinamos as duas matrizes em um grafo, calculamos o Laplaciano
         normalizado e extraimos seus autovetores (embedding espectral).
      5. Agrupamos (KMeans) os beats no espaco desses autovetores: beats
         que caem no mesmo cluster => pertencem ao mesmo "tipo" de secao
         (isso e o que permite detectar REPETICOES automaticamente).
      6. Convertendo blocos contiguos do mesmo cluster em segmentos de tempo,
         obtemos o mapa da musica (inicio/fim de cada secao + seu rotulo).

    Retorna uma lista de segmentos: [{'start': seg_inicio_s, 'end': seg_fim_s,
    'cluster': id_do_cluster}, ...]
    """
    # --- 1. Features harmonicas (Chroma) sincronizadas por batida ---
    # Usamos chroma_cqt (12 classes de nota) em vez do CQT bruto de alta
    # resolucao: e uma representacao bem mais leve em memoria e ainda
    # suficiente para detectar repeticoes de trechos harmonicos.
    C_db = librosa.feature.chroma_cqt(y=y, sr=sr)

    # garante que existam batidas suficientes para segmentar
    if len(beat_frames) < 8:
        # musica muito curta / deteccao de batida falhou: sem segmentacao,
        # tratamos a faixa inteira como uma unica secao
        duration = get_duration(y, sr)
        return [{'start': 0.0, 'end': duration, 'cluster': 0}]

    Csync = librosa.util.sync(C_db, beat_frames, aggregate=np.median)

    # --- 2. Self-Similarity Matrix (recorrencia) a partir do chroma ---
    R = librosa.segment.recurrence_matrix(Csync, width=3, mode='affinity', sym=True)

    # --- 3. Similaridade sequencial local (MFCC, timbre) ---
    mfcc = librosa.feature.mfcc(y=y, sr=sr)
    Msync = librosa.util.sync(mfcc, beat_frames)
    path_dist = np.sqrt(np.sum(np.diff(Msync, axis=1) ** 2, axis=0))
    sigma = np.median(path_dist) + 1e-8
    path_sim = np.exp(-path_dist / sigma)
    R_path = np.diag(path_sim, k=1) + np.diag(path_sim, k=-1)

    # dimensoes de R e R_path podem diferir em 1 (por causa do diff) -> ajusta
    n = min(R.shape[0], R_path.shape[0])
    R = R[:n, :n]
    R_path = R_path[:n, :n]

    # --- 4. Combinacao ponderada das duas matrizes + Laplaciano normalizado ---
    deg_path = np.sum(R_path, axis=1)
    deg_rec = np.sum(R, axis=1)
    denom = np.sum((deg_path + deg_rec) ** 2) + 1e-8
    mu = float(deg_path.dot(deg_path + deg_rec) / denom)
    mu = min(max(mu, 0.05), 0.95)  # evita degenerar totalmente para um dos lados

    A = mu * R + (1 - mu) * R_path

    degree = np.sum(A, axis=1)
    degree[degree == 0] = 1e-8
    D_inv_sqrt = np.diag(1.0 / np.sqrt(degree))
    L = np.eye(A.shape[0]) - D_inv_sqrt.dot(A).dot(D_inv_sqrt)

    evals, evecs = scipy.linalg.eigh(L)

    # suaviza os autovetores ao longo do tempo (reduz ruido/flutuacoes)
    evecs = scipy.ndimage.median_filter(evecs, size=(9, 1))

    k = _estimate_num_clusters(evals)

    # normalizacao dos autovetores (embedding espectral)
    Cnorm = np.cumsum(evecs ** 2, axis=1) ** 0.5
    X = evecs[:, :k] / (Cnorm[:, k - 1:k] + 1e-8)

    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = km.fit_predict(X)

    # --- 5/6. Converte sequencia de labels por beat em segmentos de tempo ---
    beat_times = librosa.frames_to_time(beat_frames[:n], sr=sr)
    duration = get_duration(y, sr)

    segments = []
    seg_start_idx = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[seg_start_idx]:
            start_t = float(beat_times[seg_start_idx])
            end_t = float(beat_times[i]) if i < len(labels) else duration
            segments.append({
                'start': start_t,
                'end': end_t,
                'cluster': int(labels[seg_start_idx]),
            })
            seg_start_idx = i

    return segments


def merge_short_segments(segments, tempo):
    """
    Funde segmentos muito curtos (ruido de segmentacao) ao segmento vizinho
    mais proximo, com base em uma duracao minima expressa em compassos.
    """
    if not segments:
        return segments

    seconds_per_measure = (60.0 / tempo) * BEATS_PER_MEASURE
    min_duration = seconds_per_measure * MIN_SEGMENT_MEASURES

    merged = [dict(segments[0])]
    for seg in segments[1:]:
        duration = seg['end'] - seg['start']
        if duration < min_duration and merged:
            # funde ao segmento anterior, mantendo o cluster do anterior
            merged[-1]['end'] = seg['end']
        else:
            merged.append(dict(seg))

    return merged


def label_segments(segments):
    """
    Atribui letras (A, B, C, ...) aos segmentos de acordo com a ORDEM DE
    PRIMEIRA APARICAO de cada cluster. Assim, se o cluster 3 aparecer pela
    primeira vez depois do cluster 1, ele ainda vira "Secao B" (2a letra a
    aparecer), preservando a logica de "letras na ordem em que surgem na
    musica" pedida no MVP. Repeticoes do mesmo cluster reutilizam a mesma
    letra automaticamente (deteccao de repeticao).
    """
    cluster_to_letter = {}
    next_letter_idx = 0
    letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

    labeled = []
    for seg in segments:
        cluster = seg['cluster']
        if cluster not in cluster_to_letter:
            cluster_to_letter[cluster] = letters[next_letter_idx % len(letters)]
            next_letter_idx += 1
        labeled.append({
            'start': seg['start'],
            'end': seg['end'],
            'letter': cluster_to_letter[cluster],
        })
    return labeled


def compute_measures(duration_seconds, tempo):
    """Converte uma duracao em segundos para uma quantidade aproximada de
    compassos, assumindo BEATS_PER_MEASURE tempos por compasso."""
    seconds_per_measure = (60.0 / tempo) * BEATS_PER_MEASURE
    if seconds_per_measure <= 0:
        return 0
    return max(1, round(duration_seconds / seconds_per_measure))


def analyze(file_path):
    """
    Funcao principal chamada pelo backend (app.py). Recebe o caminho de um
    arquivo de audio temporario e devolve um dicionario pronto para virar
    JSON, com todos os dados que o frontend precisa exibir.
    """
    # Duracao real do arquivo (sem carregar tudo em memoria), usada para
    # exibicao - mesmo que a analise em si seja limitada a
    # MAX_ANALYSIS_SECONDS por questao de memoria/tempo de CPU.
    full_duration = float(librosa.get_duration(path=file_path))

    y, sr = load_audio(file_path)
    analyzed_duration = get_duration(y, sr)

    tempo, beat_frames, beat_times = estimate_tempo_and_beats(y, sr)
    key = estimate_key(y, sr)

    raw_segments = structural_segmentation(y, sr, beat_frames)
    merged_segments = merge_short_segments(raw_segments, tempo)
    labeled_segments = label_segments(merged_segments)

    sections = []
    occurrence_count = {}
    for seg in labeled_segments:
        letter = seg['letter']
        occurrence_count[letter] = occurrence_count.get(letter, 0) + 1
        seg_duration = seg['end'] - seg['start']
        sections.append({
            'start': seg['start'],
            'end': seg['end'],
            'duration_seconds': round(seg_duration, 1),
            'letter': letter,
            'is_repetition': occurrence_count[letter] > 1,
            'measures': compute_measures(seg_duration, tempo),
        })

    total_measures = compute_measures(full_duration, tempo)

    result = {
        'duration_seconds': round(full_duration, 1),
        'bpm': tempo,
        'key': key,
        'time_signature': '4/4',  # ver observacao no topo do arquivo
        'total_measures_approx': total_measures,
        'sections': sections,
    }

    if full_duration > analyzed_duration + 1:
        # Avisa o frontend que a segmentacao cobre so o trecho inicial
        result['truncated_analysis_seconds'] = round(analyzed_duration, 1)

    return result
