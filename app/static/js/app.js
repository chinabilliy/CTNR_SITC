// 通用确认对话框
document.addEventListener('click', function(e){
  var el = e.target.closest('[data-confirm]');
  if (el && !el.dataset.confirmed) {
    if (!window.confirm(el.getAttribute('data-confirm'))) {
      e.preventDefault();
      e.stopPropagation();
    }
  }
});

// 侧栏分组折叠状态：按菜单 key 记忆，跨页面保持；当前项所在分组强制展开
(function(){
  var KEY = 'nav_fold_state';
  var state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { state = {}; }
  document.querySelectorAll('.nav-tree details[data-nav-key]').forEach(function(d){
    var k = d.getAttribute('data-nav-key');
    if (Object.prototype.hasOwnProperty.call(state, k)) { d.open = !!state[k]; }
    if (!d.open && d.querySelector('.nav-link.active')) { d.open = true; state[k] = true; }
    d.addEventListener('toggle', function(){
      state[k] = d.open;
      try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
    });
  });
})();
