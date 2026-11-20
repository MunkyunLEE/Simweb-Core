import { $, el, api } from './util.js';

const RIGHT_HTML = `
<div class="topbar"><a id="theoryBtn" class="btn ghost" href="/theory.html" target="_blank" rel="noopener">Theory · 원리와 설계</a></div>
<section class="llm">
  <h2>LLM <small id="llmStatus"></small></h2>
  <div class="row two"><label>방식<select id="llmMode"><option value="rule_first">규칙 우선 (모르면 LLM)</option><option value="auto">LLM 우선 (실패 시 규칙)</option><option value="llm">LLM만</option><option value="rule">규칙 기반만</option></select></label><label>모델<input id="llmModel" type="text" placeholder="예: claude-sonnet-5"></label></div>
  <div class="row"><label>엔드포인트 (OpenAI 호환)<input id="llmUrl" type="text" placeholder="비워 두면 규칙 기반만 사용 · 예: https://api.anthropic.com/v1"></label></div>
  <div class="row two"><label>API 키<input id="llmKey" type="password" placeholder="클라우드 API 는 필요"></label><button id="llmSave" class="ghost">적용 · 확인</button></div>
  <div class="row"><button id="llmTest" class="ghost" type="button">실제 응답 테스트</button></div>
  <div id="llmInfo" class="info"></div>
</section>
<section class="chat">
  <h2>조건 · 결과 지시</h2>
  <div id="chips"></div>
  <div id="chatLog"></div>
  <form id="chatForm"><textarea id="chatInput" rows="3"></textarea><button class="primary" type="submit">보내기</button></form>
</section>`;

export function mountRight(aside, opt) {
  aside.innerHTML = RIGHT_HTML;
  if (opt.theory) $('theoryBtn').href = opt.theory;
  $('chatInput').placeholder = opt.placeholder || '';
  const note = opt.note || (() => {});

  async function llmRefresh(save) {
    const body = save ? { url: $('llmUrl').value, model: $('llmModel').value, mode: $('llmMode').value, ...($('llmKey').value ? { key: $('llmKey').value } : {}) } : null;
    const r = save ? await api('/api/llm', { json: body }) : await api('/api/llm');
    $('llmUrl').value = r.llm.url;
    $('llmModel').value = r.llm.model;
    $('llmMode').value = r.llm.mode;
    const s = $('llmStatus');
    renderInfo(r);
    if (!r.llm.url || !r.llm.model) {
      s.textContent = '규칙 기반 사용 · LLM 미설정';
      s.className = '';
    } else if (r.llm.mode === 'rule') {
      s.textContent = '규칙 기반 사용';
      s.className = '';
    } else if (r.llm.mode === 'rule_first') {
      s.textContent = r.status.ok && r.status.has_model ? '규칙 우선 · LLM 대기 중' : '규칙 우선 · LLM 없음';
      s.className = r.status.ok && r.status.has_model ? 'ok' : '';
    } else if (r.status.ok) {
      s.textContent = r.status.has_model ? '연결됨' : `연결됨 · 모델 '${r.llm.model}' 없음`;
      s.className = r.status.has_model ? 'ok' : 'bad';
    } else {
      s.textContent = '연결 안 됨 → 규칙 기반으로 대체';
      s.className = 'bad';
    }
  }

  function renderInfo(r, test) {
    const stt = r.status || {};
    const rows = [];
    const add = (k, v, cls) => {
      const d = document.createElement('div');
      const b = document.createElement('b');
      b.textContent = k + ' ';
      const sp = document.createElement('span');
      sp.textContent = v;
      if (cls) sp.className = cls;
      d.append(b, sp);
      rows.push(d);
    };
    add('연결 대상', `${stt.provider || r.provider || ''} · ${stt.host || ''}`);
    add('모델', r.llm.model || '-', stt.ok ? (stt.has_model ? 'good' : 'badt') : '');
    add('API 키', r.llm.has_key ? '입력됨' : '없음');
    if (r.llm.mode === 'rule') add('현재 방식', 'LLM을 부르지 않고 규칙 기반만 사용 중');
    else if (r.llm.mode === 'rule_first') add('현재 방식', '규칙이 이해한 문장은 즉시 처리, 못 알아들은 문장만 LLM으로 보냄');
    else if (stt.ok) add('서버 응답', `정상 (${stt.ms} ms) · 모델 ${stt.models.length}개 목록${stt.has_model ? '에 선택한 모델이 있음' : '에 선택한 모델이 없음'}`, stt.has_model ? 'good' : 'badt');
    else add('서버 응답', '연결 실패: ' + (stt.error || ''), 'badt');
    if (test) {
      if (test.ok) add('실제 응답', `성공 (${(test.ms / 1000).toFixed(1)}초) · 응답한 모델 ${test.model || '?'} · JSON ${test.json_ok ? '정상' : '아님'} · "${test.reply}"`, test.json_ok ? 'good' : 'badt');
      else add('실제 응답', '실패: ' + test.error, 'badt');
    }
    $('llmInfo').replaceChildren(...rows);
  }

  async function llmTest() {
    const b = $('llmTest');
    b.disabled = true;
    b.textContent = '테스트 중…';
    try {
      await llmRefresh(true);
      const t = await api('/api/llm/test', { method: 'POST' });
      renderInfo(await api('/api/llm'), t.test);
    } catch (e) {
      note(e.message, true);
    }
    b.disabled = false;
    b.textContent = '실제 응답 테스트';
  }

  function addMsg(role, text, extra) {
    const log = $('chatLog');
    const m = el('div', 'msg ' + (role === 'user' ? 'user' : 'bot'));
    if (extra && extra.engine) m.append(el('span', 'tag', extra.engine === 'llm' ? 'LLM · ' + (extra.model || '') : '규칙 기반'));
    m.append(document.createTextNode(text));
    if (extra && extra.ops && extra.ops.length) m.append(el('div', 'ops', extra.ops.map((o) => JSON.stringify(o)).join('\n')));
    if (extra && extra.note) m.append(el('div', 'notetxt', extra.note));
    if (extra && extra.error) m.append(el('div', 'errtxt', '적용 실패: ' + extra.error));
    log.append(m);
    log.scrollTop = log.scrollHeight;
  }

  async function send(text) {
    if (!text.trim()) return;
    if (opt.beforeSend && !opt.beforeSend()) return;
    addMsg('user', text);
    $('chatInput').value = '';
    const wait = el('div', 'msg bot', '');
    const label = document.createElement('span');
    const stop = el('button', 'danger stop', 'LLM 중단');
    stop.type = 'button';
    stop.onclick = () => api('/api/cancel/llm', { method: 'POST' }).catch(() => {});
    wait.append(label, stop);
    const t0 = Date.now();
    const tick = () => (label.textContent = '처리 중… ' + Math.round((Date.now() - t0) / 1000) + '초');
    tick();
    const timer = setInterval(tick, 1000);
    $('chatLog').append(wait);
    try {
      const s = await api('/api/chat', { json: { text } });
      clearInterval(timer);
      wait.remove();
      const c = s.chat;
      addMsg('bot', c.reply || (c.ops.length ? '적용했습니다.' : '적용할 내용이 없습니다.'), c);
      await opt.onState(s, c);
    } catch (e) {
      clearInterval(timer);
      wait.remove();
      if (e.message.includes('중단')) addMsg('bot', e.message);
      else addMsg('bot', '', { error: e.message });
    }
  }

  function chips(prompts) {
    const c = $('chips');
    c.innerHTML = '';
    for (const p of prompts || []) {
      const b = el('button', '', p);
      b.type = 'button';
      b.onclick = () => send(p);
      c.append(b);
    }
  }

  $('llmSave').onclick = () => llmRefresh(true).catch((e) => note(e.message, true));
  $('llmTest').onclick = llmTest;
  $('chatForm').onsubmit = (e) => {
    e.preventDefault();
    send($('chatInput').value);
  };
  $('chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      send($('chatInput').value);
    }
  });
  llmRefresh(false).catch(() => {});
  return { send, chips, addMsg, clear: () => ($('chatLog').innerHTML = ''), llmRefresh };
}
