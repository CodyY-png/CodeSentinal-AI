'use strict';

let scan = null;
let scanVersion = 0;
let moduleVersion = 0;

function generationMessage(text) {
  $('generation-message').textContent = text;
}

function showCandidate(code, findings = []) {
  $('candidate-result').hidden = !code;
  $('candidate-code').textContent = code || '';
  $('reviewed-code').value = code || '';
  $('review-confirm').checked = false;
  $('run-candidate').disabled = true;
  const list = $('findings');
  list.replaceChildren();
  if (!code) return;
  list.append(el('h3', '模型診斷'));
  if (!findings.length) list.append(el('p', '這份報告沒有列出具體疑點。'));
  for (const finding of findings) {
    const section = el('section', undefined, 'test');
    section.append(el('h4', finding.title), el('p', '狀態：待執行驗證'));
    const fields = el('dl');
    for (const [key, label] of [
      ['input', '測試輸入'], ['expected', '推測的預期結果'],
      ['predicted', '依程式碼推估的結果'], ['basis', '推測依據'],
      ['reproduction', '重現方式'], ['suggestion', '修正建議']
    ]) {
      fields.append(el('dt', label), el('dd', finding[key]));
    }
    section.append(fields);
    list.append(section);
  }
}

function moduleUrl() {
  return `/generation/${scan.id}/modules/${$('module-select').value}`;
}

async function showModule() {
  const version = ++moduleVersion;
  $('request-details').hidden = true;
  $('generation-actions').hidden = true;
  $('send-confirm').checked = false;
  $('generate').disabled = true;
  showCandidate(null);
  try {
    const data = await api(moduleUrl(), {headers: reportHeaders()});
    if (version !== moduleVersion) return;
    const payload = data.request;
    $('request-preview').textContent = JSON.stringify({
      ...payload, ...(payload.input ? {input: JSON.parse(payload.input)} : {})
    }, null, 2);
    $('request-details').hidden = false;
    $('send-label').textContent = scan.provider === 'ollama'
      ? '同意將預覽內容交給伺服器的本機 Ollama'
      : '同意將預覽內容送到 OpenAI';
    $('generation-actions').hidden = !scan.configured || Boolean(data.candidate);
    showCandidate(data.candidate, data.findings);
  } catch (error) {
    if (version === moduleVersion) generationMessage(error.message);
  }
}

function reportHeaders() {
  return scan?.access_token ? {'X-Report-Token': scan.access_token} : {};
}

$('project').addEventListener('input', () => {
  scanVersion++;
  moduleVersion++;
  scan = null;
  $('generation-content').hidden = true;
  generationMessage('專案路徑已變更，請重新掃描。');
});

async function scanProject(file) {
  const version = ++scanVersion;
  moduleVersion++;
  $('scan').disabled = true;
  $('project-zip').disabled = true;
  $('generation-content').hidden = true;
  generationMessage('正在掃描 Python 模組…');
  try {
    const data = await api(file ? '/generation/uploads' : '/generation/previews', {
      method: 'POST',
      headers: {'Content-Type': file ? 'application/zip' : 'application/json'},
      body: file || JSON.stringify({project: $('project').value.trim() || '.'})
    }, 60000);
    if (version !== scanVersion) return;
    scan = data;
    const options = scan.modules.map((entry, index) =>
      Object.assign(el('option', entry.path), {value: String(index + 1)}));
    $('module-select').replaceChildren(...options);
    $('skipped-list').replaceChildren(...scan.skipped.map(entry =>
      el('li', `${entry.path} — ${entry.reason}`)));
    $('skipped-modules').hidden = !scan.skipped.length;
    $('generation-content').hidden = false;
    const setup = scan.configured ? '請選擇模組查看請求。' : '設定 Ollama 模型或 OpenAI 金鑰後即可生成。';
    generationMessage(`找到 ${scan.modules.length} 個模組，略過 ${scan.skipped.length} 個檔案。${setup}`);
    await showModule();
  } catch (error) {
    if (version === scanVersion) generationMessage(error.message);
  } finally {
    $('scan').disabled = false;
    $('project-zip').disabled = false;
    $('project-zip').value = '';
  }
}

$('scan').addEventListener('click', () => scanProject(null));
$('project-zip').addEventListener('change', () => {
  const file = $('project-zip').files[0];
  if (file) scanProject(file);
});

$('module-select').addEventListener('change', showModule);
$('review-confirm').addEventListener('change', () => {
  $('run-candidate').disabled = !$('review-confirm').checked;
});
$('reviewed-code').addEventListener('input', () => {
  $('review-confirm').checked = false;
  $('run-candidate').disabled = true;
});
$('run-candidate').addEventListener('click', async () => {
  if (!$('review-confirm').checked) return;
  $('review-confirm').checked = false;
  $('run-candidate').disabled = true;
  try {
    const task = await api(moduleUrl() + '/analyses', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({confirm: true, code: $('reviewed-code').value})
    });
    selected = task.id;
    message('候選測試任務已建立，結果會自動更新。');
    await refresh();
    $('result-title').scrollIntoView({block: 'nearest'});
  } catch (error) {
    message(error.message, true);
  }
});
$('send-confirm').addEventListener('change', () => {
  $('generate').disabled = !$('send-confirm').checked;
});
$('generate').addEventListener('click', async () => {
  if (!$('send-confirm').checked) return;
  const version = moduleVersion;
  $('generate').disabled = true;
  $('send-confirm').checked = false;
  $('send-confirm').disabled = true;
  generationMessage('正在生成候選測試…');
  try {
    const data = await api(moduleUrl(), {
      method: 'POST',
      headers: {'Content-Type': 'application/json', ...reportHeaders()},
      body: JSON.stringify({confirm: true})
    }, scan.provider === 'ollama' ? 310000 : 100000);
    if (version !== moduleVersion) return;
    showCandidate(data.candidate, data.findings);
    $('generation-actions').hidden = true;
    generationMessage('候選測試已產生。');
  } catch (error) {
    if (version === moduleVersion) generationMessage(error.message);
  } finally {
    $('send-confirm').disabled = false;
  }
});
