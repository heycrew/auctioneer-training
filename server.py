#!/usr/bin/env python3
"""威拍拍卖师秘籍 - 后端服务"""
import os, sys, hashlib, hmac, json, time, uuid, base64
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_file, send_from_directory, g
from werkzeug.utils import secure_filename
import sqlite3

app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SECRET_KEY'] = 'weipai-auctioneer-secret-2026'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.db')

# ============================================================
# 数据库
# ============================================================
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id TEXT NOT NULL,
            status TEXT,
            answer_shown INTEGER DEFAULT 0,
            time INTEGER,
            UNIQUE(user_id, question_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id TEXT NOT NULL,
            subject TEXT,
            chapter TEXT,
            title TEXT,
            type TEXT,
            root_cause TEXT DEFAULT '未分类',
            note TEXT DEFAULT '',
            related_page TEXT DEFAULT '',
            saved_at INTEGER,
            UNIQUE(user_id, question_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            size INTEGER DEFAULT 0,
            filename TEXT NOT NULL,
            uploaded_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    ''')
    # 默认管理员
    admin = db.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    if not admin:
        pw = hash_password('funsun2007')
        db.execute("INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?,?,1,?)",
                   ('admin', pw, int(time.time())))
    # 默认标题
    title = db.execute("SELECT * FROM config WHERE key='title'").fetchone()
    if not title:
        db.execute("INSERT INTO config (key, value) VALUES ('title', '威拍拍卖师秘籍')")
    db.commit()
    db.close()

# ============================================================
# 密码
# ============================================================
def hash_password(password):
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return base64.b64encode(salt + key).decode('ascii')

def verify_password(password, stored):
    decoded = base64.b64decode(stored.encode('ascii'))
    salt, key = decoded[:32], decoded[32:]
    new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return hmac.compare_digest(key, new_key)

# ============================================================
# JWT (simple)
# ============================================================
def make_token(user_id, username, is_admin):
    payload = json.dumps({'uid': user_id, 'un': username, 'ia': is_admin, 'exp': int(time.time()) + 86400 * 7})
    sig = hmac.new(app.config['SECRET_KEY'].encode(), payload.encode(), 'sha256').hexdigest()
    return base64.b64encode((payload + '.' + sig).encode()).decode()

def parse_token(token_str):
    try:
        raw = base64.b64decode(token_str.encode()).decode()
        payload, sig = raw.rsplit('.', 1)
        expected = hmac.new(app.config['SECRET_KEY'].encode(), payload.encode(), 'sha256').hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(payload)
        if data['exp'] < time.time():
            return None
        return data
    except:
        return None

# ============================================================
# 认证装饰器
# ============================================================
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        user = parse_token(token)
        if not user:
            return jsonify({'error': '未登录或登录已过期'}), 401
        g.user = user
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        user = parse_token(token)
        if not user or not user.get('ia'):
            return jsonify({'error': '需要管理员权限'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated

# ============================================================
# API - 认证
# ============================================================
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(force=True)
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': '请输入账号和密码'}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    db.close()
    if not user or not verify_password(password, user['password_hash']):
        return jsonify({'error': '账号或密码错误'}), 401

    token = make_token(user['id'], user['username'], bool(user['is_admin']))
    return jsonify({
        'token': token,
        'username': user['username'],
        'isAdmin': bool(user['is_admin']),
    })

# ============================================================
# API - 进度同步
# ============================================================
@app.route('/api/progress', methods=['GET'])
@require_auth
def api_get_progress():
    db = get_db()
    rows = db.execute("SELECT question_id, status, answer_shown, time FROM progress WHERE user_id=?", (g.user['uid'],)).fetchall()
    db.close()
    result = {}
    for r in rows:
        result[r['question_id']] = {
            'status': r['status'],
            'answerShown': bool(r['answer_shown']),
            'time': r['time']
        }
    return jsonify({'progress': result})

@app.route('/api/progress', methods=['PUT'])
@require_auth
def api_save_progress():
    data = request.get_json(force=True)
    db = get_db()
    uid = g.user['uid']
    for qid, entry in data.get('progress', {}).items():
        db.execute("""INSERT INTO progress (user_id, question_id, status, answer_shown, time)
                      VALUES (?,?,?,?,?) ON CONFLICT(user_id, question_id)
                      DO UPDATE SET status=excluded.status, answer_shown=excluded.answer_shown, time=excluded.time""",
                   (uid, qid, entry.get('status'), int(entry.get('answerShown', False)), entry.get('time')))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ============================================================
# API - 错题
# ============================================================
@app.route('/api/errors', methods=['GET'])
@require_auth
def api_get_errors():
    db = get_db()
    rows = db.execute("SELECT * FROM errors WHERE user_id=?", (g.user['uid'],)).fetchall()
    db.close()
    result = {}
    for r in rows:
        result[r['question_id']] = {
            'subject': r['subject'], 'chapter': r['chapter'], 'title': r['title'],
            'type': r['type'], 'rootCause': r['root_cause'], 'note': r['note'],
            'relatedPage': r['related_page'], 'savedAt': r['saved_at']
        }
    return jsonify({'errors': result})

@app.route('/api/errors', methods=['PUT'])
@require_auth
def api_save_errors():
    data = request.get_json(force=True)
    db = get_db()
    uid = g.user['uid']
    for qid, entry in data.get('errors', {}).items():
        db.execute("""INSERT INTO errors (user_id, question_id, subject, chapter, title, type, root_cause, note, related_page, saved_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id, question_id)
                      DO UPDATE SET subject=excluded.subject, chapter=excluded.chapter, title=excluded.title,
                      type=excluded.type, root_cause=excluded.root_cause, note=excluded.note,
                      related_page=excluded.related_page, saved_at=excluded.saved_at""",
                   (uid, qid, entry.get('subject'), entry.get('chapter'), entry.get('title'),
                    entry.get('type'), entry.get('rootCause', '未分类'), entry.get('note', ''),
                    entry.get('relatedPage', ''), entry.get('savedAt')))
    db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/api/errors/<qid>', methods=['DELETE'])
@require_auth
def api_delete_error(qid):
    db = get_db()
    db.execute("DELETE FROM errors WHERE user_id=? AND question_id=?", (g.user['uid'], qid))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ============================================================
# API - 教材
# ============================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/books', methods=['GET'])
@require_auth
def api_get_books():
    db = get_db()
    rows = db.execute("SELECT * FROM books ORDER BY uploaded_at DESC").fetchall()
    db.close()
    books = []
    for r in rows:
        books.append({
            'id': r['id'], 'name': r['name'], 'type': r['type'],
            'size': r['size'], 'uploadedAt': r['uploaded_at']
        })
    return jsonify({'books': books})

def _auth_from_query():
    """允许通过 URL ?token= 参数认证（用于 iframe/img 等无法自定义 Header 的场景）"""
    token = request.args.get('token', '')
    if token:
        user = parse_token(token)
        if user:
            g.user = user
            return True
    return False

@app.route('/api/books/<book_id>/download', methods=['GET'])
def api_download_book(book_id):
    # 🔒 仅支持 Authorization header 认证，禁止 URL ?token= 参数（防止链接分享/源码泄露）
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user = parse_token(token) if token else None
    if not user:
        return jsonify({'error': '未登录或登录已过期'}), 401
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    db.close()
    if not book:
        return jsonify({'error': '教材不存在'}), 404
    filepath = os.path.join(UPLOAD_FOLDER, book['filename'])
    if not os.path.exists(filepath):
        return jsonify({'error': '文件丢失'}), 404
    # 根据文件类型设置 MIME，确保浏览器内嵌预览而非下载
    mime_map = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
        'doc': 'application/msword', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }
    mimetype = mime_map.get(book['type'], 'application/octet-stream')
    response = send_file(filepath, mimetype=mimetype)
    # 强制 inline 显示（不允许浏览器触发下载），RFC 5987 编码处理中文文件名
    from urllib.parse import quote
    safe_name = quote(book['name'])
    response.headers['Content-Disposition'] = 'inline; filename*=UTF-8\'\'%s' % safe_name
    # 🔒 安全头：禁止浏览器嗅探MIME、禁止iframe嵌套外部、禁用缓存
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/books/upload', methods=['POST'])
@require_admin
def api_upload_book():
    if 'file' not in request.files:
        return jsonify({'error': '请选择文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '请选择文件'}), 400
    name = request.form.get('name', '').strip() or file.filename

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': '不支持的格式，仅支持 PDF/Word/JPG/PNG'}), 400

    book_id = 'book_' + str(int(time.time() * 1000))
    safe_name = secure_filename(f"{book_id}.{ext}")
    filepath = os.path.join(UPLOAD_FOLDER, safe_name)
    file.save(filepath)
    file_size = os.path.getsize(filepath)

    db = get_db()
    db.execute("INSERT INTO books (id, name, type, size, filename, uploaded_at) VALUES (?,?,?,?,?,?)",
               (book_id, name, ext, file_size, safe_name, int(time.time())))
    db.commit()
    db.close()
    return jsonify({'ok': True, 'book': {'id': book_id, 'name': name, 'type': ext, 'size': file_size}})

@app.route('/api/books/<book_id>', methods=['DELETE'])
@require_admin
def api_delete_book(book_id):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if book:
        filepath = os.path.join(UPLOAD_FOLDER, book['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)
        db.execute("DELETE FROM books WHERE id=?", (book_id,))
        db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/api/books/<book_id>/rename', methods=['PUT'])
@require_admin
def api_rename_book(book_id):
    data = request.get_json(force=True)
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({'error': '名称不能为空'}), 400
    db = get_db()
    db.execute("UPDATE books SET name=? WHERE id=?", (new_name, book_id))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ============================================================
# API - 用户管理 (admin)
# ============================================================
@app.route('/api/users', methods=['GET'])
@require_admin
def api_get_users():
    db = get_db()
    rows = db.execute("SELECT id, username, is_admin, created_at FROM users ORDER BY created_at").fetchall()
    db.close()
    users = []
    for r in rows:
        users.append({
            'id': r['id'], 'username': r['username'],
            'isAdmin': bool(r['is_admin']), 'createdAt': r['created_at']
        })
    return jsonify({'users': users})

@app.route('/api/users', methods=['POST'])
@require_admin
def api_create_user():
    data = request.get_json(force=True)
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': '账号和密码不能为空'}), 400
    if username == 'admin':
        return jsonify({'error': '不能创建名为 admin 的账号'}), 400
    if len(password) < 4:
        return jsonify({'error': '密码至少4位'}), 400
    db = get_db()
    exist = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if exist:
        db.close()
        return jsonify({'error': '该账号已存在'}), 400
    pw = hash_password(password)
    db.execute("INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?,?,0,?)",
               (username, pw, int(time.time())))
    db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/api/users/<username>', methods=['DELETE'])
@require_admin
def api_delete_user(username):
    if username == 'admin':
        return jsonify({'error': '不能删除管理员账号'}), 400
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if user:
        db.execute("DELETE FROM errors WHERE user_id=?", (user['id'],))
        db.execute("DELETE FROM progress WHERE user_id=?", (user['id'],))
        db.execute("DELETE FROM users WHERE id=?", (user['id'],))
        db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/api/users/<username>/password', methods=['PUT'])
@require_admin
def api_reset_password(username):
    data = request.get_json(force=True)
    new_password = data.get('password', '')
    if len(new_password) < 4:
        return jsonify({'error': '密码至少4位'}), 400
    db = get_db()
    pw = hash_password(new_password)
    db.execute("UPDATE users SET password_hash=? WHERE username=?", (pw, username))
    db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/api/admin/password', methods=['PUT'])
@require_admin
def api_change_admin_password():
    data = request.get_json(force=True)
    old_pw = data.get('oldPassword', '')
    new_pw = data.get('newPassword', '')
    if len(new_pw) < 6:
        return jsonify({'error': '新密码至少6位'}), 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username=?", (g.user['un'],)).fetchone()
    if not user or not verify_password(old_pw, user['password_hash']):
        db.close()
        return jsonify({'error': '原密码错误'}), 400
    pw = hash_password(new_pw)
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (pw, user['id']))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ============================================================
# API - 系统配置
# ============================================================
@app.route('/api/config', methods=['GET'])
def api_get_config():
    db = get_db()
    row = db.execute("SELECT value FROM config WHERE key='title'").fetchone()
    db.close()
    return jsonify({'title': row['value'] if row else '威拍拍卖师秘籍'})

@app.route('/api/config', methods=['PUT'])
@require_admin
def api_update_config():
    data = request.get_json(force=True)
    title = data.get('title', '').strip()
    if len(title) < 2:
        return jsonify({'error': '标题至少2个字符'}), 400
    db = get_db()
    db.execute("INSERT INTO config (key, value) VALUES ('title', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (title,))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ============================================================
# 静态文件
# ============================================================
@app.after_request
def add_header(response):
    # 教材文件请求：添加安全头但不影响预览
    if '/api/books/' in request.path and '/download' in request.path:
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# ============================================================
# 启动
# ============================================================
if __name__ == '__main__':
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    init_db()
    print("数据库初始化完成")
    print("威拍拍卖师秘籍服务端启动...")
    app.run(host='0.0.0.0', port=5000, debug=False)
