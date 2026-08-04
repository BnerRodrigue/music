/**
 * script.js
 * =========
 * Toda a logica de interface do Analisador de Estrutura Musical.
 *
 * IMPORTANTE (requisito do projeto):
 *   - Nao ha login e nao ha persistencia.
 *   - Todo o estado abaixo (arquivo selecionado, resultado da analise,
 *     nomes escolhidos pelo usuario para cada secao) vive APENAS em
 *     variaveis JavaScript, em memoria, durante a sessao da pagina.
 *   - Ao atualizar (F5) a pagina, tudo e perdido - por design.
 */

(function () {
  'use strict';

  // -------------------------------------------------------------------
  // Elementos da UI
  // -------------------------------------------------------------------
  const mp3Input = document.getElementById('mp3-input');
  const uploadLabel = document.getElementById('upload-label');
  const analyzeBtn = document.getElementById('analyze-btn');

  const uploadStep = document.getElementById('upload-step');
  const loadingStep = document.getElementById('loading-step');
  const resultStep = document.getElementById('result-step');
  const errorStep = document.getElementById('error-step');

  const progressBar = document.getElementById('progress-bar');
  const loadingText = document.getElementById('loading-text');

  const infoFilename = document.getElementById('info-filename');
  const infoDuration = document.getElementById('info-duration');
  const infoBpm = document.getElementById('info-bpm');
  const infoKey = document.getElementById('info-key');
  const infoTimeSignature = document.getElementById('info-time-signature');
  const infoMeasures = document.getElementById('info-measures');

  const sectionsList = document.getElementById('sections-list');
  const sectionRowTemplate = document.getElementById('section-row-template');

  const exportBtn = document.getElementById('export-btn');
  const resetBtn = document.getElementById('reset-btn');
  const errorResetBtn = document.getElementById('error-reset-btn');
  const errorText = document.getElementById('error-text');

  // -------------------------------------------------------------------
  // Estado em memoria (somente durante a sessao da pagina)
  // -------------------------------------------------------------------
  let selectedFile = null;
  let analysisResult = null; // resposta bruta da API
  // sectionNames[i] guarda o nome ATUAL escolhido pelo usuario para a secao i
  let sectionNames = [];

  // -------------------------------------------------------------------
  // Helpers de UI: alternar entre as 4 etapas visuais
  // -------------------------------------------------------------------
  function showStep(step) {
    [uploadStep, loadingStep, resultStep, errorStep].forEach((el) => {
      el.classList.add('hidden');
      el.classList.remove('flex');
    });
    step.classList.remove('hidden');
    if (step !== uploadStep) {
      step.classList.add('flex');
    }
  }

  function formatTime(totalSeconds) {
    const m = Math.floor(totalSeconds / 60);
    const s = Math.floor(totalSeconds % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  // -------------------------------------------------------------------
  // Etapa 1: selecionar arquivo
  // -------------------------------------------------------------------
  mp3Input.addEventListener('change', () => {
    const file = mp3Input.files[0];
    if (!file) return;

    selectedFile = file;
    uploadLabel.textContent = file.name;
    analyzeBtn.disabled = false;
  });

  // -------------------------------------------------------------------
  // Etapa 2: analisar (envia para o backend Flask)
  // -------------------------------------------------------------------
  analyzeBtn.addEventListener('click', () => {
    if (!selectedFile) return;
    runAnalysis(selectedFile);
  });

  function runAnalysis(file) {
    showStep(loadingStep);
    progressBar.style.width = '0%';
    loadingText.textContent = 'Enviando arquivo...';

    const formData = new FormData();
    formData.append('file', file);

    // API_BASE_URL vem de config.js. Vazio = mesmo dominio (uso local).
    // Em producao, config.js aponta para a URL do backend no Render.
    const apiUrl = `${window.API_BASE_URL || ''}/api/analyze`;

    const xhr = new XMLHttpRequest();
    xhr.open('POST', apiUrl);

    // Progresso real do UPLOAD do arquivo
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 60); // upload = ate 60% da barra
        progressBar.style.width = `${percent}%`;
      }
    });

    xhr.upload.addEventListener('load', () => {
      // upload concluido; o backend agora esta processando o audio
      // (nao temos progresso real dessa etapa, entao animamos ate ~90%)
      progressBar.style.width = '75%';
      loadingText.textContent = 'Analisando estrutura musical (BPM, tom, secoes)...';
    });

    xhr.onload = () => {
      progressBar.style.width = '100%';

      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch (e) {
        showError('Resposta invalida do servidor.');
        return;
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        setTimeout(() => renderResult(data), 200); // pequena pausa para a barra chegar a 100%
      } else {
        showError(data.error || 'Nao foi possivel analisar o arquivo.');
      }
    };

    xhr.onerror = () => {
      showError('Falha de conexao com o servidor.');
    };

    xhr.send(formData);
  }

  function showError(message) {
    errorText.textContent = message;
    showStep(errorStep);
  }

  // -------------------------------------------------------------------
  // Etapa 3: renderizar resultado
  // -------------------------------------------------------------------
  function renderResult(data) {
    analysisResult = data;

    // nome inicial de cada secao = "Secao <letra>" detectada automaticamente;
    // o usuario podera trocar livremente pelos selects
    sectionNames = data.sections.map((sec) => `Seção ${sec.letter}`);

    infoFilename.textContent = data.filename;
    infoDuration.textContent = formatTime(data.duration_seconds);
    infoBpm.textContent = data.bpm;
    infoKey.textContent = data.key;
    infoTimeSignature.textContent = data.time_signature;
    infoMeasures.textContent = data.total_measures_approx;

    sectionsList.innerHTML = '';

    data.sections.forEach((section, index) => {
      const row = sectionRowTemplate.content.cloneNode(true);

      const timestampEl = row.querySelector('.section-timestamp');
      const detectedLabelEl = row.querySelector('.section-detected-label');
      const selectEl = row.querySelector('.section-select');
      const customNameEl = row.querySelector('.section-custom-name');
      const durationEl = row.querySelector('.section-duration');
      const measuresEl = row.querySelector('.section-measures');

      timestampEl.textContent = formatTime(section.start);

      const repetitionSuffix = section.is_repetition ? ' (Repetição)' : '';
      detectedLabelEl.textContent = `Seção ${section.letter}${repetitionSuffix}`;

      durationEl.textContent = `${Math.round(section.duration_seconds)}s`;
      measuresEl.textContent = `${section.measures} compassos`;

      // Ao trocar o select, atualiza o nome guardado em memoria para esta secao
      selectEl.addEventListener('change', () => {
        if (selectEl.value === 'Livre') {
          customNameEl.classList.remove('hidden');
          customNameEl.value = '';
          customNameEl.focus();
          sectionNames[index] = '';
        } else {
          customNameEl.classList.add('hidden');
          sectionNames[index] = selectEl.value;
        }
      });

      customNameEl.addEventListener('input', () => {
        sectionNames[index] = customNameEl.value;
      });

      sectionsList.appendChild(row);
    });

    showStep(resultStep);
  }

  // -------------------------------------------------------------------
  // Exportar TXT
  // -------------------------------------------------------------------
  exportBtn.addEventListener('click', () => {
    if (!analysisResult) return;

    const lines = [];
    lines.push('================================');
    lines.push('Nome:');
    lines.push(analysisResult.filename.replace(/\.mp3$/i, ''));
    lines.push('Duração:');
    lines.push(formatTime(analysisResult.duration_seconds));
    lines.push('Tom:');
    lines.push(analysisResult.key);
    lines.push('BPM:');
    lines.push(String(analysisResult.bpm));
    lines.push('Compasso:');
    lines.push(analysisResult.time_signature);
    lines.push('--------------------------------');

    analysisResult.sections.forEach((section, index) => {
      const name = (sectionNames[index] || '').trim() || `Seção ${section.letter}`;
      lines.push(formatTime(section.start));
      lines.push(name);
    });

    lines.push('================================');

    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    const baseName = analysisResult.filename.replace(/\.mp3$/i, '') || 'estrutura';
    a.download = `${baseName}_estrutura.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  // -------------------------------------------------------------------
  // Resetar (nova analise) - limpa apenas o estado em memoria
  // -------------------------------------------------------------------
  function resetAll() {
    selectedFile = null;
    analysisResult = null;
    sectionNames = [];

    mp3Input.value = '';
    uploadLabel.textContent = 'Selecionar MP3';
    analyzeBtn.disabled = true;

    showStep(uploadStep);
  }

  resetBtn.addEventListener('click', resetAll);
  errorResetBtn.addEventListener('click', resetAll);
})();
