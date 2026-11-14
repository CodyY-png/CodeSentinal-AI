'use strict';
const $ = id => document.getElementById(id);
const labels = {queued:'等待執行',running:'執行中',passed:'全部通過',tests_failed:'有測試失敗',runner_error:'執行異常',timeout:'執行逾時',interrupted:'執行中斷'};
let selected = null, timer = null, active = false, selectionVersion = 0;
function el(tag, text, className) { const node=document.createElement(tag); if(text!==undefined)node.textContent=text; if(className)node.className=className; return node; }
function badge(status) { return el('span',labels[status] || status,'status '+status); }
function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
async function api(path,options={},timeoutMs=12000){
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),timeoutMs);
  try{const response=await fetch(path,{...options,signal:controller.signal});const data=await response.json();if(!response.ok){throw new Error(typeof data.detail==='string'?data.detail:`請求失敗（${response.status}），請確認輸入。`);}return data;}
  catch(error){if(error.name==='AbortError')throw new Error('連線逾時，請重新整理紀錄，確認任務是否已建立。');throw error;}
  finally{clearTimeout(timeout);}
}
function syncButton(){ $('start').disabled=active; $('start').textContent=active?'測試執行中…':'啟動測試'; }
function renderTask(task){
  $('status').replaceWith(Object.assign(badge(task.status),{id:'status'}));
  const detail=$('detail');detail.replaceChildren();
  detail.append(el('p',`任務 ${task.id}`,'meta'));
  detail.append(el('p', task.project || '內建訂單示範', 'meta'));
  if(!task.result){detail.append(el('p',task.message || (['queued','running'].includes(task.status)?'正在執行測試，結果將自動更新。':'本次任務沒有測試結果。')));return;}
  const result=task.result, counts=result.counts, stats=el('div',undefined,'stats');
  for(const [key,label] of [['passed','通過'],['failed','失敗'],['errors','錯誤'],['skipped','略過']]){const stat=el('div',undefined,'stat');stat.append(el('strong',String(counts[key])),el('span',label));stats.append(stat);}detail.append(stats);
  detail.append(el('p',`執行時間 ${result.duration_seconds} 秒`,'caption'));
  if(result.message)detail.append(el('p',result.message));
  for(const test of result.tests){const row=el('div',undefined,'test'),head=el('div',undefined,'test-heading');head.append(el('span',test.name,'test-name'),badge(test.status==='failed'?'tests_failed':test.status==='errors'?'runner_error':test.status==='skipped'?'略過':test.status));row.append(head,el('small',test.classname));if(test.detail){const expanded=el('details');expanded.append(el('summary','查看執行紀錄'),el('pre',test.detail));row.append(expanded);}detail.append(row);}
}
async function selectTask(id){
  const version=++selectionVersion;selected=id;
  document.querySelectorAll('.history-item').forEach(node=>node.classList.toggle('selected',node.dataset.id===id));
  $('status').textContent='讀取中';
  try{const task=await api('/analyses/'+encodeURIComponent(id));if(version===selectionVersion)renderTask(task);}
  catch(error){if(version===selectionVersion){$('status').textContent='讀取失敗';$('detail').replaceChildren(el('p','無法取得此任務的結果，請重新選取或重新整理。'));message(error.message,true);}}
}
async function refresh(){
  clearTimeout(timer);
  try{
    const data=await api('/analyses');const list=$('history-list');list.replaceChildren();
    active=data.items.some(task=>['queued','running'].includes(task.status));syncButton();
    for(const task of data.items){const button=el('button',undefined,'history-item'+(task.id===selected?' selected':''));button.type='button';button.dataset.id=task.id;const time=el('time',new Date(task.created_at).toLocaleString('zh-TW',{hour12:false}));time.dateTime=task.created_at;button.append(time,badge(task.status),el('span',task.id.slice(0,8),'run-id'));button.addEventListener('click',()=>selectTask(task.id));list.append(button);}
    if(!data.items.length)list.append(el('p','還沒有分析紀錄，按上方按鈕開始。','empty'));
    if(!selected&&data.items.length)selected=data.items[0].id;
    if(selected)await selectTask(selected);
  }catch(error){message('無法更新紀錄。請確認後端仍在執行，再按重新整理。',true);}
  finally{timer=setTimeout(refresh,active?1200:10000);}
}
$('run-form').addEventListener('submit',async event=>{
  event.preventDefault();if(active)return;
  const timeout=Number($('timeout').value);if(!Number.isInteger(timeout)||timeout<1||timeout>300){message('請輸入 1 到 300 秒的整數。',true);return;}
  active=true;syncButton();message('正在建立測試任務…');
  try{const task=await api('/analyses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({timeout,project:$('project').value.trim() || '.'})});selected=task.id;message('任務已建立，結果會自動更新。');}
  catch(error){message(error.message,true);active=false;syncButton();}
  await refresh();
});
$('refresh').addEventListener('click',()=>{message('');refresh();});
async function initializeDashboard() {
  try {
    const settings = await api('/settings');
    $('environment').textContent = settings.remote ? '受邀訪客' : '本機開發環境';
    if (settings.remote) {
      $('generation-message').textContent = '選取 Python ZIP 後會掃描原始碼。診斷疑點會標為待驗證。';
      return;
    }
    document.querySelectorAll('[data-local]').forEach(element => { element.hidden = false; });
    refresh();
  } catch (error) {
    message(error.message, true);
  }
}

initializeDashboard();
