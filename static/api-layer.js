// ===================================================================
// API 层（替换 localStorage）
// ===================================================================
const API_BASE = '';
let authToken = null;

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
  const res = await fetch(API_BASE + path, { ...options, headers: { ...headers, ...options.headers } });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || '请求失败');
  return data;
}

// ===== 用户系统 =====
let currentUser = null;

// ===== 配置 =====
async function getSystemTitle() {
  try { const d = await api('/api/config'); return d.title; } catch(e) { return '威拍拍卖师秘籍'; }
}

function updateAllTitles(title) {
  const loginTitle = document.getElementById('loginTitle');
  if (loginTitle && loginTitle.childNodes[0]) loginTitle.childNodes[0].textContent = title;
  const headerTitle = document.getElementById('headerTitle');
  if (headerTitle) headerTitle.textContent = title;
  document.title = title + ' · 复习练习系统';
  const titleInput = document.getElementById('adminNewTitle');
  if (titleInput) titleInput.value = title;
}

async function changeSystemTitle() {
  const newTitle = document.getElementById('adminNewTitle').value.trim();
  const msgEl = document.getElementById('adminTitleMsg');
  if (!newTitle || newTitle.length < 2) { msgEl.innerHTML = '<span style="color:var(--red);">⚠️ 标题至少2个字符</span>'; return; }
  try {
    await api('/api/config', { method: 'PUT', body: JSON.stringify({ title: newTitle }) });
    updateAllTitles(newTitle);
    msgEl.innerHTML = '<span style="color:var(--green);">✅ 系统标题已更新</span>';
  } catch(e) { msgEl.innerHTML = '<span style="color:var(--red);">⚠️ ' + e.message + '</span>'; }
}

// ===== 登录/登出 =====
async function login() {
  const username = document.getElementById('loginUser').value.trim();
  const password = document.getElementById('loginPass').value;
  const errEl = document.getElementById('loginError');
  if (!username || !password) { errEl.textContent = '⚠️ 请输入账号和密码'; return; }

  try {
    const data = await api('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) });
    authToken = data.token;
    currentUser = { username: data.username, isAdmin: data.isAdmin };
    appState = await loadStateFromServer();

    document.getElementById('loginOverlay').style.display = 'none';
    document.getElementById('app-container').style.display = '';
    document.getElementById('displayUser').textContent = data.username + (data.isAdmin ? ' [管理员]' : '');
    if (data.isAdmin) document.getElementById('nav-admin').style.display = '';

    document.getElementById('loginUser').value = '';
    document.getElementById('loginPass').value = '';
    document.getElementById('loginError').textContent = '';
    init();
  } catch(e) {
    errEl.textContent = '❌ ' + e.message;
  }
}

function logout() {
  if (confirm('确定要退出登录吗？')) {
    authToken = null;
    currentUser = null;
    appState = { errors: {}, progress: {}, reviewSessions: [] };
    document.getElementById('loginOverlay').style.display = '';
    document.getElementById('app-container').style.display = 'none';
    document.getElementById('nav-admin').style.display = 'none';
    shuffleMap = {}; shuffleReverse = {};
    currentQuestions = [];
    switchPanel('practice');
  }
}

// ===== 进度同步 =====
async function loadStateFromServer() {
  try {
    const [pRes, eRes] = await Promise.all([
      api('/api/progress'),
      api('/api/errors')
    ]);
    return { progress: pRes.progress || {}, errors: eRes.errors || {}, reviewSessions: [] };
  } catch(e) {
    return { errors: {}, progress: {}, reviewSessions: [] };
  }
}

function loadState() { return { errors: {}, progress: {}, reviewSessions: [] }; }

async function saveState() {
  if (!authToken) return;
  // 只同步有变化的 progress 和 errors
  const progressToSync = {};
  for (const [qid, entry] of Object.entries(appState.progress)) {
    if (entry._dirty !== false) { progressToSync[qid] = entry; entry._dirty = false; }
  }
  if (Object.keys(progressToSync).length > 0) {
    try { await api('/api/progress', { method: 'PUT', body: JSON.stringify({ progress: progressToSync }) }); } catch(e) {}
  }
}

function setQStatus(qid, status) {
  if (!appState.progress[qid]) appState.progress[qid] = {};
  appState.progress[qid].status = status;
  appState.progress[qid].time = Date.now();
  appState.progress[qid]._dirty = true;
  saveState();
}

function saveErrorEntry(qid, entry) {
  appState.errors[qid] = { ...entry, savedAt: Date.now() };
  // 异步同步到服务端
  api('/api/errors', { method: 'PUT', body: JSON.stringify({ errors: { [qid]: entry } }) }).catch(() => {});
}

function removeErrorEntry(qid) {
  delete appState.errors[qid];
  api('/api/errors/' + encodeURIComponent(qid), { method: 'DELETE' }).catch(() => {});
}

// ===== 管理员功能 =====
async function changeAdminPassword() {
  const oldPw = document.getElementById('adminOldPass').value;
  const new1 = document.getElementById('adminNewPass1').value;
  const new2 = document.getElementById('adminNewPass2').value;
  const msgEl = document.getElementById('adminPwdMsg');
  if (!oldPw || !new1 || !new2) { msgEl.innerHTML = '<span style="color:var(--red);">⚠️ 请填写所有密码字段</span>'; return; }
  if (new1 !== new2) { msgEl.innerHTML = '<span style="color:var(--red);">⚠️ 两次输入的新密码不一致</span>'; return; }
  if (new1.length < 6) { msgEl.innerHTML = '<span style="color:var(--red);">⚠️ 新密码至少6位</span>'; return; }
  try {
    await api('/api/admin/password', { method: 'PUT', body: JSON.stringify({ oldPassword: oldPw, newPassword: new1 }) });
    msgEl.innerHTML = '<span style="color:var(--green);">✅ 管理员密码已更新</span>';
    document.getElementById('adminOldPass').value = '';
    document.getElementById('adminNewPass1').value = '';
    document.getElementById('adminNewPass2').value = '';
  } catch(e) { msgEl.innerHTML = '<span style="color:var(--red);">❌ ' + e.message + '</span>'; }
}

async function addUser() {
  const username = document.getElementById('newUsername').value.trim();
  const password = document.getElementById('newUserPass').value;
  if (!username || !password) { alert('请填写账号和密码'); return; }
  if (username === 'admin') { alert('不能创建名为 admin 的账号'); return; }
  if (password.length < 4) { alert('密码至少4位'); return; }
  try {
    await api('/api/users', { method: 'POST', body: JSON.stringify({ username, password }) });
    document.getElementById('newUsername').value = '';
    document.getElementById('newUserPass').value = '';
    renderAdminUserTable();
  } catch(e) { alert('❌ ' + e.message); }
}

async function deleteUser(username) {
  if (!confirm(`确定要删除用户「${username}」吗？该用户的所有学习记录将被清除。`)) return;
  try {
    await api('/api/users/' + encodeURIComponent(username), { method: 'DELETE' });
    renderAdminUserTable();
  } catch(e) { alert('❌ ' + e.message); }
}

async function resetUserPassword(username) {
  const newPass = prompt(`为「${username}」设置新密码（至少4位）：`);
  if (!newPass || newPass.length < 4) { alert('密码至少4位'); return; }
  try {
    await api('/api/users/' + encodeURIComponent(username) + '/password', { method: 'PUT', body: JSON.stringify({ password: newPass }) });
    alert('✅ 「' + username + '」的密码已重置');
  } catch(e) { alert('❌ ' + e.message); }
}

async function renderAdminUserTable() {
  try {
    const data = await api('/api/users');
    document.getElementById('userCount').textContent = data.users.length;
    let html = '<table class="admin-table"><thead><tr><th>账号</th><th>角色</th><th>创建时间</th><th>操作</th></tr></thead><tbody>';
    data.users.forEach(u => {
      const created = u.createdAt ? new Date(u.createdAt * 1000).toLocaleString('zh-CN') : '—';
      html += `<tr><td>${escHtml(u.username)}</td><td>${u.isAdmin ? '🔧 管理员' : '👤 普通用户'}</td><td>${created}</td><td>`;
      if (!u.isAdmin) {
        html += `<button class="btn-sm" onclick="resetUserPassword('${escHtml(u.username)}')" style="margin-right:6px;">🔑 改密</button>`;
        html += `<button class="btn-sm-del" onclick="deleteUser('${escHtml(u.username)}')">🗑️ 删除</button>`;
      } else {
        html += `<span style="color:var(--text2);font-size:0.8em;">系统账号</span>`;
      }
      html += `</td></tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('userTableContainer').innerHTML = html;
  } catch(e) {}
}

// ===== 教材系统 =====
async function loadBooksFromServer() {
  try { const d = await api('/api/books'); return d.books || []; } catch(e) { return []; }
}

async function loadBooks() { return await loadBooksFromServer(); }

async function renderBookGrid() {
  const books = await loadBooksFromServer();
  const grid = document.getElementById('bookGrid');
  if (!grid) return;
  if (books.length === 0) {
    grid.innerHTML = '<div style="text-align:center;padding:60px;color:var(--text2);grid-column:1/-1;"><p style="font-size:2em;">📭</p><p>暂无教材，请联系管理员上传</p></div>';
    return;
  }
  const typeIcons = { 'pdf': '📄', 'doc': '📝', 'docx': '📝', 'jpg': '🖼️', 'jpeg': '🖼️', 'png': '🖼️' };
  const typeNames = { 'pdf': 'PDF文档', 'doc': 'Word文档', 'docx': 'Word文档', 'jpg': '图片', 'jpeg': '图片', 'png': '图片' };
  let html = '';
  books.forEach(book => {
    const icon = typeIcons[book.type] || '📁';
    html += `<div class="book-card" onclick="openViewer('${book.id}')">`;
    html += `<div class="book-icon">${icon}</div>`;
    html += `<div class="book-name">${escHtml(book.name)}</div>`;
    html += `<div class="book-type">${typeNames[book.type] || book.type} · ${formatSize(book.size || 0)}</div>`;
    html += `</div>`;
  });
  grid.innerHTML = html;
}

function formatSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + 'B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + 'KB';
  return (bytes / 1048576).toFixed(1) + 'MB';
}

function openViewer(bookId) {
  if (!authToken) return;
  const url = API_BASE + '/api/books/' + bookId + '/download?token=' + encodeURIComponent(authToken);
  // 先用 fetch 获取文件信息
  api('/api/books').then(d => {
    const book = (d.books || []).find(b => b.id === bookId);
    if (!book) return;
    document.getElementById('viewerTitle').textContent = book.name;
    const body = document.getElementById('viewerBody');
    const ext = book.type || '';
    const dlUrl = '/api/books/' + bookId + '/download';
    if (ext === 'pdf') {
      body.innerHTML = `<iframe src="${dlUrl}"></iframe>`;
    } else if (ext === 'jpg' || ext === 'jpeg' || ext === 'png') {
      body.innerHTML = `<img src="${dlUrl}" alt="${escHtml(book.name)}">`;
    } else {
      body.innerHTML = `<div class="viewer-unsupported"><p>📝 此格式建议下载查看</p><button onclick="downloadBook('${book.id}')">⬇️ 下载查看</button></div>`;
    }
    document.getElementById('viewerOverlay').style.display = 'flex';
  });
}

function closeViewer() {
  document.getElementById('viewerOverlay').style.display = 'none';
  document.getElementById('viewerBody').innerHTML = '';
}

function downloadBook(bookId) {
  window.open(API_BASE + '/api/books/' + bookId + '/download', '_blank');
}

async function uploadBook() {
  const nameInput = document.getElementById('bookName');
  const fileInput = document.getElementById('bookFileInput');
  const msgEl = document.getElementById('bookAdminMsg');
  const file = fileInput.files[0];
  if (!file) { msgEl.innerHTML = '<span style="color:var(--red);">⚠️ 请选择文件</span>'; return; }
  const name = nameInput.value.trim() || file.name;
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['pdf','doc','docx','jpg','jpeg','png'].includes(ext)) {
    msgEl.innerHTML = '<span style="color:var(--red);">⚠️ 不支持的格式</span>'; return;
  }
  if (file.size > 50 * 1024 * 1024) {
    msgEl.innerHTML = '<span style="color:var(--red);">⚠️ 文件过大（最大50MB）</span>'; return;
  }
  msgEl.innerHTML = '<span style="color:var(--accent2);">⏳ 正在上传...</span>';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    const headers = {};
    if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
    const res = await fetch(API_BASE + '/api/books/upload', { method: 'POST', headers, body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '上传失败');
    msgEl.innerHTML = '<span style="color:var(--green);">✅ 教材已上传</span>';
    nameInput.value = '';
    fileInput.value = '';
    renderBookGrid();
    renderBookAdminTable();
  } catch(e) { msgEl.innerHTML = '<span style="color:var(--red);">⚠️ ' + e.message + '</span>'; }
}

async function deleteBook(bookId) {
  if (!confirm('确定要删除该教材吗？')) return;
  try {
    await api('/api/books/' + bookId, { method: 'DELETE' });
    renderBookGrid();
    renderBookAdminTable();
  } catch(e) { alert('❌ ' + e.message); }
}

async function renameBook(bookId) {
  const newName = prompt('输入新名称：');
  if (!newName || !newName.trim()) return;
  try {
    await api('/api/books/' + bookId + '/rename', { method: 'PUT', body: JSON.stringify({ name: newName.trim() }) });
    renderBookGrid();
    renderBookAdminTable();
  } catch(e) { alert('❌ ' + e.message); }
}

async function renderBookAdminTable() {
  const books = await loadBooksFromServer();
  const container = document.getElementById('bookAdminTable');
  if (!container) return;
  if (books.length === 0) { container.innerHTML = '<p style="color:var(--text2);font-size:0.9em;">暂无教材</p>'; return; }
  const typeNames = { 'pdf': 'PDF', 'doc': 'Word', 'docx': 'Word', 'jpg': '图片', 'jpeg': '图片', 'png': '图片' };
  let html = '<table class="admin-table"><thead><tr><th>名称</th><th>格式</th><th>大小</th><th>上传时间</th><th>操作</th></tr></thead><tbody>';
  books.forEach(b => {
    html += `<tr><td>${escHtml(b.name)}</td><td>${typeNames[b.type] || b.type}</td><td>${formatSize(b.size)}</td>`;
    html += `<td>${new Date(b.uploadedAt * 1000).toLocaleString('zh-CN')}</td>`;
    html += `<td><button class="btn-sm" onclick="renameBook('${b.id}')" style="margin-right:6px;">✏️ 重命名</button>`;
    html += `<button class="btn-sm-del" onclick="deleteBook('${b.id}')">🗑️ 删除</button></td></tr>`;
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

function escHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ===== 键盘 ESC 关闭查看器 =====
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeViewer();
});

// ===== 初始化 =====
getSystemTitle().then(title => updateAllTitles(title));