#!/usr/bin/env python3
"""
Cloud Run 배포를 위한 단계적 Flask 애플리케이션
"""
import os
from flask import Flask, jsonify, render_template_string, request, session, redirect, url_for
from functools import wraps

app = Flask(__name__)

# Secret Key 설정
SECRET_KEY = os.getenv('SECRET_KEY') or 'dev-secret-key-local'
app.secret_key = SECRET_KEY

# 사용자 계정
USERS = {
    'admin': {'password': 'admin123', 'role': 'admin'},
    'user': {'password': 'user123', 'role': 'user'}
}

# 데코레이터
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            return jsonify({'error': '관리자 권한이 필요합니다.'}), 403
        return f(*args, **kwargs)
    return decorated_function

# 기본 HTML 템플릿
BASE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Army Chatbot</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .status { background: #f0f8ff; padding: 20px; border-radius: 5px; margin: 20px 0; }
        .login-form { background: #f9f9f9; padding: 20px; border-radius: 5px; }
        input[type="text"], input[type="password"] { width: 200px; padding: 5px; margin: 5px; }
        button { padding: 10px 20px; background: #007cba; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background: #005a87; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Army Chatbot</h1>
        <div class="status">
            <p><strong>서비스가 정상적으로 실행 중입니다.</strong></p>
            <p>환경: {{ environment }}</p>
            <p>포트: {{ port }}</p>
            <p>사용자: {{ username if username else '로그인 필요' }}</p>
        </div>
        {% if not username %}
        <div class="login-form">
            <h3>로그인</h3>
            <form method="post" action="/login">
                <input type="text" name="username" placeholder="사용자명" required><br>
                <input type="password" name="password" placeholder="비밀번호" required><br>
                <button type="submit">로그인</button>
            </form>
            <p><small>테스트 계정: admin/admin123 또는 user/user123</small></p>
        </div>
        {% else %}
        <div>
            <p>환영합니다, {{ username }}님!</p>
            <a href="/logout"><button>로그아웃</button></a>
            {% if role == 'admin' %}
            <a href="/admin"><button>관리자 페이지</button></a>
            {% endif %}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(BASE_TEMPLATE, 
                                environment=os.environ.get('ENVIRONMENT', 'unknown'),
                                port=os.environ.get('PORT', 'unknown'),
                                username=session.get('username'),
                                role=session.get('role'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in USERS and USERS[username]['password'] == password:
            session['authenticated'] = True
            session['username'] = username
            session['role'] = USERS[username]['role']
            return redirect(url_for('index'))
        else:
            return render_template_string(BASE_TEMPLATE, 
                                        environment=os.environ.get('ENVIRONMENT', 'unknown'),
                                        port=os.environ.get('PORT', 'unknown'),
                                        error='잘못된 사용자명 또는 비밀번호입니다.')
    
    return render_template_string(BASE_TEMPLATE, 
                                environment=os.environ.get('ENVIRONMENT', 'unknown'),
                                port=os.environ.get('PORT', 'unknown'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin():
    return jsonify({
        'message': '관리자 페이지입니다.',
        'user': session.get('username'),
        'role': session.get('role')
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'message': 'Service is running',
        'environment': os.environ.get('ENVIRONMENT', 'unknown'),
        'port': os.environ.get('PORT', 'unknown')
    })

@app.route('/api/status')
def status():
    return jsonify({
        'status': 'ok',
        'message': 'Enhanced app is running',
        'environment': os.environ.get('ENVIRONMENT', 'unknown'),
        'authenticated': session.get('authenticated', False),
        'username': session.get('username')
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting minimal server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
