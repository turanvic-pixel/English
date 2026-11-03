/* StepEnglish: вместо ФИО — номер по списку/псевдоним + согласие на передачу результатов.
   Подключается в каждом тесте. Поля имени ищутся по id (inp-name*, adv-inp-name, f-name). */
(function () {
  'use strict';
  var KEY = 'pv_consent_v1';
  var NAME_ID = /(^|-)inp-name|^f-name$/;
  var PH_ON = 'Номер по списку (не фамилия!)';
  var PH_OFF = '↑ Сначала поставьте галочку согласия';
  var boxes = [];
  var consent = false;
  try { consent = localStorage.getItem(KEY) === '1'; } catch (e) {}

  function css() {
    if (document.getElementById('pv-style')) return;
    var s = document.createElement('style');
    s.id = 'pv-style';
    s.textContent =
      '.pv-box{display:flex;gap:8px;align-items:flex-start;margin:6px 0 10px;padding:9px 11px;border:1.5px solid #c9b27a;border-radius:10px;background:#fffaf0;color:#3b3220;font:13px/1.35 Arial,sans-serif;text-align:left}' +
      '.pv-box input{margin-top:2px;flex:none;width:18px;height:18px;accent-color:#4C8558}' +
      '.pv-box label{cursor:pointer}' +
      '.pv-box.pv-flash{border-color:#c0392b;background:#fdecea}' +
      'input[data-pv-name]:disabled{opacity:.6;background:#f1efe9}';
    document.head.appendChild(s);
  }

  function apply() {
    boxes.forEach(function (b) {
      b.cb.checked = consent;
      b.inp.disabled = !consent;
      b.inp.placeholder = consent ? PH_ON : PH_OFF;
      if (consent) b.box.classList.remove('pv-flash');
    });
  }

  function setConsent(v) {
    consent = v;
    try { localStorage.setItem(KEY, v ? '1' : '0'); } catch (e) {}
    apply();
  }

  function process(inp) {
    if (inp.dataset.pvName) return;
    inp.dataset.pvName = '1';
    css();
    var box = document.createElement('div');
    box.className = 'pv-box';
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = 'pv-cb-' + boxes.length;
    var lb = document.createElement('label');
    lb.htmlFor = cb.id;
    lb.textContent = 'Я согласен(на) передать преподавателю номер по списку, группу и результаты теста для учёта успеваемости. ' +
      'Настоящие фамилию и имя вводить не нужно.';
    box.appendChild(cb); box.appendChild(lb);
    inp.parentNode.insertBefore(box, inp);
    cb.addEventListener('change', function () { setConsent(cb.checked); });
    // подпись у поля (ai_tutor)
    if (inp.id) {
      var lab = document.querySelector('label[for="' + inp.id + '"]');
      if (lab && /Имя/i.test(lab.textContent)) lab.textContent = 'Номер по списку группы';
    }
    inp.removeAttribute('autocomplete');
    inp.setAttribute('autocomplete', 'off');
    // подсветка согласия, если тест отклонил пустое поле
    new MutationObserver(function () {
      if (inp.disabled && inp.classList.contains('err')) box.classList.add('pv-flash');
    }).observe(inp, { attributes: true, attributeFilter: ['class'] });
    boxes.push({ inp: inp, cb: cb, box: box });
    apply();
  }

  function scan(root) {
    var list = (root || document).querySelectorAll ? (root || document).querySelectorAll('input[type="text"]') : [];
    for (var i = 0; i < list.length; i++) if (NAME_ID.test(list[i].id)) process(list[i]);
  }

  function init() {
    scan(document);
    new MutationObserver(function () { scan(document); }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.body) init(); else document.addEventListener('DOMContentLoaded', init);
})();
