#!/usr/bin/env python3
"""
Cloud Run 배포를 위한 단계적 Flask 애플리케이션
"""
import os
import logging
from flask import Flask, jsonify, render_template_string, request, session, redirect, url_for
from functools import wraps
from datetime import datetime

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RAG 시스템 초기화 (지연 로딩)
rag_system = None
storage = None
initialization_complete = False

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

def ensure_initialization():
    """필요할 때만 RAG 시스템 초기화"""
    global rag_system, storage, initialization_complete
    
    if initialization_complete:
        return True
    
    try:
        logger.info("🚀 RAG 시스템 초기화 시작...")
        
        # 환경 변수 확인
        is_cloud_run = os.environ.get('ENVIRONMENT') == 'cloud'
        gcp_project_id = os.environ.get('GCP_PROJECT_ID')
        gcs_bucket_name = os.environ.get('GCS_BUCKET_NAME')
        
        logger.info(f"환경: {'Cloud Run' if is_cloud_run else 'Local'}")
        logger.info(f"프로젝트 ID: {gcp_project_id}")
        logger.info(f"버킷 이름: {gcs_bucket_name}")
        
        if is_cloud_run and gcp_project_id and gcs_bucket_name:
            # Cloud Storage 초기화
            from core.cloud_storage import CloudStorage
            storage = CloudStorage(
                bucket_name=gcs_bucket_name,
                project_id=gcp_project_id,
                is_cloud_run=True
            )
            logger.info("✅ Cloud Storage 초기화 완료")
        else:
            # 로컬 스토리지 초기화
            from core.storage import LocalStorage
            storage = LocalStorage(
                bucket_name=gcs_bucket_name or 'local-bucket',
                project_id=gcp_project_id or 'local-project',
                is_cloud_run=False
            )
            logger.info("✅ 로컬 스토리지 초기화 완료")
        
        # RAG 시스템 초기화
        from core.rag import RAGSystem
        rag_system = RAGSystem(storage=storage)
        logger.info("✅ RAG 시스템 초기화 완료")
        
        initialization_complete = True
        logger.info("✅ 전체 초기화 완료")
        return True
        
    except Exception as e:
        logger.error(f"❌ RAG 시스템 초기화 실패: {e}")
        import traceback
        logger.error(f"❌ 상세 오류: {traceback.format_exc()}")
        return False

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
        .error { color: red; margin: 10px 0; }
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
            {% if error %}
            <div class="error">{{ error }}</div>
            {% endif %}
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
        
        <!-- 채팅 인터페이스 -->
        <div style="margin-top: 30px; border: 1px solid #ddd; padding: 20px; border-radius: 5px;">
            <h3>AI 챗봇</h3>
            <div id="chat-container" style="height: 300px; overflow-y: auto; border: 1px solid #ccc; padding: 10px; margin: 10px 0; background: #f9f9f9;">
                <p><em>질문을 입력해주세요...</em></p>
            </div>
            <form id="chat-form" style="display: flex; gap: 10px;">
                <input type="text" id="question-input" placeholder="질문을 입력하세요..." style="flex: 1; padding: 10px;">
                <button type="submit" style="padding: 10px 20px;">전송</button>
            </form>
        </div>
        {% endif %}
    </div>
    
    <script>
        document.getElementById('chat-form').addEventListener('submit', async function(e) {
            e.preventDefault();
            const question = document.getElementById('question-input').value;
            if (!question.trim()) return;
            
            const chatContainer = document.getElementById('chat-container');
            const questionDiv = document.createElement('div');
            questionDiv.innerHTML = '<strong>질문:</strong> ' + question;
            questionDiv.style.marginBottom = '10px';
            chatContainer.appendChild(questionDiv);
            
            const loadingDiv = document.createElement('div');
            loadingDiv.innerHTML = '<em>답변을 생성 중입니다...</em>';
            loadingDiv.style.color = '#666';
            chatContainer.appendChild(loadingDiv);
            
            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ question: question })
                });
                
                const data = await response.json();
                loadingDiv.remove();
                
                const answerDiv = document.createElement('div');
                answerDiv.innerHTML = '<strong>답변:</strong> ' + (data.answer || data.error || '답변을 생성할 수 없습니다.');
                answerDiv.style.marginBottom = '20px';
                answerDiv.style.padding = '10px';
                answerDiv.style.backgroundColor = '#e8f4f8';
                answerDiv.style.borderRadius = '5px';
                chatContainer.appendChild(answerDiv);
                
                document.getElementById('question-input').value = '';
                chatContainer.scrollTop = chatContainer.scrollHeight;
            } catch (error) {
                loadingDiv.innerHTML = '<em style="color: red;">오류가 발생했습니다: ' + error.message + '</em>';
            }
        });
    </script>
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

@app.route('/api/query', methods=['POST'])
@login_required
def query():
    if not ensure_initialization():
        return jsonify({'error': 'RAG 시스템 초기화에 실패했습니다.'}), 500
    
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({'error': '질문을 입력해주세요.'}), 400
        
        # 세션에서 대화 히스토리 가져오기
        chat_history = session.get('chat_history', [])
        
        # RAG 시스템으로 질의
        answer = rag_system.query(question, chat_history)
        
        # 새 대화를 히스토리에 추가
        new_conversation = {
            'question': question,
            'answer': answer,
            'timestamp': datetime.now().isoformat()
        }
        chat_history.append(new_conversation)
        
        # 최대 50개 대화만 유지
        if len(chat_history) > 50:
            chat_history = chat_history[-50:]
        
        # 세션에 히스토리 저장
        session['chat_history'] = chat_history
        
        return jsonify({
            'answer': answer,
            'question': question,
            'context_used': len(chat_history) - 1
        })
        
    except Exception as e:
        logger.error(f"질의 처리 중 오류: {e}")
        return jsonify({'error': '질의 처리 중 오류가 발생했습니다.'}), 500

@app.route('/admin')
@admin_required
def admin():
    if not ensure_initialization():
        return jsonify({
            'message': 'RAG 시스템 초기화에 실패했습니다.',
            'user': session.get('username'),
            'role': session.get('role')
        })
    
    try:
        files = storage.list_files() if storage else []
        storage_info = storage.get_storage_info() if storage else {}
        rag_status = rag_system.get_status() if rag_system else {}
        
        return jsonify({
            'message': '관리자 페이지입니다.',
            'user': session.get('username'),
            'role': session.get('role'),
            'files': files,
            'storage_info': storage_info,
            'rag_status': rag_status
        })
    except Exception as e:
        logger.error(f"관리자 페이지 로드 중 오류: {e}")
        return jsonify({
            'message': '관리자 페이지 로드 중 오류가 발생했습니다.',
            'user': session.get('username'),
            'role': session.get('role'),
            'error': str(e)
        })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'message': 'Service is running',
        'environment': os.environ.get('ENVIRONMENT', 'unknown'),
        'port': os.environ.get('PORT', 'unknown')
    })

@app.route('/api/upload', methods=['POST'])
@admin_required
def upload_file():
    if not ensure_initialization():
        return jsonify({'error': 'RAG 시스템 초기화에 실패했습니다.'}), 500
    
    try:
        if 'files[]' not in request.files:
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400
        
        files = request.files.getlist('files[]')
        if not files or files[0].filename == '':
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400
        
        uploaded_files = []
        failed_files = []
        
        for file in files:
            try:
                # 파일 형식 검증
                allowed_extensions = {'pdf', 'docx', 'doc', 'txt', 'md'}
                if not ('.' in file.filename and 
                       file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
                    failed_files.append({
                        'filename': file.filename,
                        'error': f'지원하지 않는 파일 형식입니다. 허용된 형식: {", ".join(allowed_extensions)}'
                    })
                    continue
                
                # 파일 크기 검증 (50MB)
                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
                
                if file_size > 50 * 1024 * 1024:
                    failed_files.append({
                        'filename': file.filename,
                        'error': '파일 크기가 너무 큽니다. 최대 크기: 50MB'
                    })
                    continue
                
                # 파일 업로드
                file_url = storage.upload_file(file, file.filename)
                uploaded_files.append({
                    'filename': file.filename,
                    'url': file_url
                })
                
                # 즉시 임베딩
                if rag_system:
                    try:
                        rag_system.add_document(file_url, file.filename)
                        storage.mark_embedding_status(file.filename, True)
                        logger.info(f"✅ 임베딩 완료: {file.filename}")
                    except Exception as e:
                        logger.error(f"❌ 임베딩 실패: {file.filename} - {e}")
                        storage.mark_embedding_status(file.filename, False)
                
            except Exception as e:
                failed_files.append({
                    'filename': file.filename,
                    'error': str(e)
                })
        
        return jsonify({
            'message': f'{len(uploaded_files)}개 파일이 성공적으로 업로드되었습니다.',
            'uploaded_files': uploaded_files,
            'failed_files': failed_files,
            'total_uploaded': len(uploaded_files),
            'total_failed': len(failed_files)
        })
        
    except Exception as e:
        logger.error(f"파일 업로드 중 오류: {e}")
        return jsonify({'error': '파일 업로드 중 오류가 발생했습니다.'}), 500

@app.route('/api/files/<filename>', methods=['DELETE'])
@admin_required
def delete_file(filename):
    if not ensure_initialization():
        return jsonify({'error': 'RAG 시스템 초기화에 실패했습니다.'}), 500
    
    try:
        # URL 디코딩
        import urllib.parse
        decoded_filename = urllib.parse.unquote(filename)
        
        # 파일 삭제
        success = storage.delete_file(decoded_filename)
        if not success:
            return jsonify({'error': '파일을 찾을 수 없거나 삭제할 수 없습니다.'}), 404
        
        # RAG 시스템에서 문서 제거
        if rag_system:
            try:
                rag_system.remove_document(decoded_filename)
                logger.info(f"✅ RAG 시스템에서 문서 제거: {decoded_filename}")
            except Exception as e:
                logger.warning(f"⚠️ RAG 시스템에서 문서 제거 실패: {e}")
        
        return jsonify({'message': '파일이 삭제되었습니다.'})
        
    except Exception as e:
        logger.error(f"파일 삭제 중 오류: {e}")
        return jsonify({'error': '파일 삭제 중 오류가 발생했습니다.'}), 500

@app.route('/api/status')
def status():
    return jsonify({
        'status': 'ok',
        'message': 'Enhanced app with file upload',
        'environment': os.environ.get('ENVIRONMENT', 'unknown'),
        'authenticated': session.get('authenticated', False),
        'username': session.get('username'),
        'rag_initialized': initialization_complete
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting minimal server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
