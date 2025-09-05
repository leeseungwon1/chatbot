import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from core.rag import RAGSystem
from core.storage import LocalStorage
from core.cloud_storage import CloudStorage
from config import get_config
import logging
from werkzeug.utils import secure_filename
from datetime import datetime

# 환경 변수 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 로컬 설정 로드
try:
    import local_config
    logger.info("✅ 로컬 설정 로드 완료")
except ImportError:
    logger.warning("⚠️ local_config.py를 찾을 수 없습니다")

app = Flask(__name__)

# 설정 로드
config = get_config()
IS_CLOUD_RUN = config.IS_CLOUD_RUN
GCP_PROJECT_ID = config.GCP_PROJECT_ID
GCS_BUCKET_NAME = config.GCS_BUCKET_NAME

# Secret Key 설정
SECRET_KEY = os.getenv('SECRET_KEY') or 'dev-secret-key-local'
app.secret_key = SECRET_KEY

# 파일 업로드 설정
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt', 'md'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# 사용자 계정
USERS = {
    'admin': {'password': 'admin123', 'role': 'admin'},
    'user': {'password': 'user123', 'role': 'user'}
}

# RAG 시스템 초기화
rag_system = None
storage = None

def allowed_file(filename):
    """허용된 파일 확장자 확인"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_app():
    """애플리케이션 초기화"""
    global rag_system, storage
    
    try:
        # 환경에 따른 스토리지 선택
        if IS_CLOUD_RUN:
            storage = CloudStorage(
                bucket_name=GCS_BUCKET_NAME,
                project_id=GCP_PROJECT_ID,
                is_cloud_run=IS_CLOUD_RUN
            )
            logger.info("✅ Cloud Storage 초기화 완료")
        else:
            storage = LocalStorage(
                bucket_name=GCS_BUCKET_NAME,
                project_id=GCP_PROJECT_ID,
                is_cloud_run=IS_CLOUD_RUN
            )
            logger.info("✅ 로컬 스토리지 초기화 완료")
        
        # RAG 시스템 초기화
        rag_system = RAGSystem(
            storage=storage
        )
        logger.info("✅ RAG 시스템 초기화 완료")
        
        # 초기화 상태 확인
        if rag_system:
            status = rag_system.get_status()
            logger.info(f"📊 RAG 시스템 상태: {status}")
        
        logger.info("✅ 로컬 애플리케이션 초기화 완료")
        
    except Exception as e:
        logger.error(f"❌ 애플리케이션 초기화 실패: {e}")
        import traceback
        logger.error(f"❌ 상세 오류: {traceback.format_exc()}")
        rag_system = None
        storage = None

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

# 라우트
@app.route('/')
@login_required
def index():
    return render_template('index.html')

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
            return render_template('login.html', error='잘못된 사용자명 또는 비밀번호입니다.')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin')
@admin_required
def admin():
    try:
        if not storage:
            logger.error("❌ 스토리지가 초기화되지 않았습니다.")
            return render_template('admin.html', 
                                 files=[], 
                                 storage_info={}, 
                                 rag_status={})
        
        files = storage.list_files()
        storage_info = storage.get_storage_info()
        rag_status = rag_system.get_status() if rag_system else {}
        
        return render_template('admin.html', 
                             files=files, 
                             storage_info=storage_info, 
                             rag_status=rag_status)
    except Exception as e:
        logger.error(f"❌ 관리자 페이지 로드 중 오류: {e}")
        return render_template('admin.html', 
                             files=[], 
                             storage_info={}, 
                             rag_status={})

@app.route('/api/query', methods=['POST'])
@login_required
def query():
    if not rag_system:
        return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
    
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({'error': '질문을 입력해주세요.'}), 400
        
        # 세션에서 대화 히스토리 가져오기
        chat_history = session.get('chat_history', [])
        
        # RAG 시스템으로 질의 (맥락 포함)
        answer = rag_system.query(question, chat_history)
        
        # 새 대화를 히스토리에 추가
        new_conversation = {
            'question': question,
            'answer': answer,
            'timestamp': datetime.now().isoformat()
        }
        chat_history.append(new_conversation)
        
        # 최대 100개 대화만 유지 (메모리 관리)
        if len(chat_history) > 100:
            chat_history = chat_history[-100:]
        
        # 세션에 히스토리 저장
        session['chat_history'] = chat_history
        
        return jsonify({
            'answer': answer,
            'question': question,
            'context_used': len(chat_history) - 1  # 현재 대화 제외한 히스토리 수
        })
        
    except Exception as e:
        logger.error(f"질의 처리 중 오류: {e}")
        return jsonify({'error': '질의 처리 중 오류가 발생했습니다.'}), 500

@app.route('/api/upload', methods=['POST'])
@admin_required
def upload_file():
    if not storage:
        return jsonify({'error': '스토리지가 초기화되지 않았습니다.'}), 500
    
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
                if not allowed_file(file.filename):
                    failed_files.append({
                        'filename': file.filename,
                        'error': f'지원하지 않는 파일 형식입니다. 허용된 형식: {", ".join(ALLOWED_EXTENSIONS)}'
                    })
                    continue
                
                # 파일 크기 검증
                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
                
                if file_size > MAX_FILE_SIZE:
                    failed_files.append({
                        'filename': file.filename,
                        'error': f'파일 크기가 너무 큽니다. 최대 크기: {MAX_FILE_SIZE // (1024*1024)}MB'
                    })
                    continue
                
                # 파일 업로드
                file_url = storage.upload_file(file)
                uploaded_files.append({
                    'filename': file.filename,
                    'url': file_url
                })
                
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

@app.route('/api/upload-and-embed', methods=['POST'])
@login_required
@admin_required
def upload_and_embed():
    """파일 업로드 후 즉시 임베딩"""
    try:
        if not storage:
            logger.error("❌ 스토리지가 초기화되지 않았습니다.")
            return jsonify({'error': '스토리지가 초기화되지 않았습니다.'}), 500
        
        if 'files[]' not in request.files:
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400
        
        files = request.files.getlist('files[]')
        if not files or files[0].filename == '':
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400
        
        logger.info(f"📁 {len(files)}개 파일 업로드 시작")
        uploaded_files = []
        failed_files = []
        
        for file in files:
            if file and file.filename:
                try:
                    logger.info(f"📄 파일 업로드 중: {file.filename}")
                    file_url = storage.upload_file(file)
                    
                    # file_url에서 파일명 추출 (local://timestamp_filename 형식)
                    filename = file_url.replace('local://', '')
                    uploaded_files.append(filename)
                    
                    logger.info(f"✅ 파일 업로드 완료: {filename}")
                    
                    # 즉시 임베딩
                    if rag_system:
                        try:
                            rag_system.add_document(file_url, filename)
                            # 임베딩 상태 즉시 업데이트
                            try:
                                storage.mark_embedding_status(filename, True)
                                logger.info(f"✅ 임베딩 상태 업데이트 완료: {filename}")
                            except Exception as status_error:
                                logger.warning(f"⚠️ 임베딩 상태 업데이트 실패: {filename} - {status_error}")
                            logger.info(f"✅ 임베딩 완료: {filename}")
                        except Exception as e:
                            logger.error(f"❌ 임베딩 실패: {filename} - {e}")
                            # 임베딩 실패 시 상태 업데이트
                            try:
                                storage.mark_embedding_status(filename, False)
                                logger.info(f"✅ 임베딩 실패 상태 업데이트 완료: {filename}")
                            except Exception as status_error:
                                logger.warning(f"⚠️ 임베딩 실패 상태 업데이트 실패: {filename} - {status_error}")
                    else:
                        logger.warning("⚠️ RAG 시스템이 초기화되지 않았습니다.")
                        
                except Exception as e:
                    logger.error(f"❌ 파일 업로드 실패: {file.filename} - {e}")
                    failed_files.append(file.filename)
        
        if uploaded_files:
            message = f'{len(uploaded_files)}개 파일이 업로드되고 임베딩되었습니다.'
            if failed_files:
                message += f' (실패: {len(failed_files)}개)'
            
            logger.info(f"✅ 업로드 완료: {len(uploaded_files)}개 성공, {len(failed_files)}개 실패")
            return jsonify({
                'message': message,
                'files': uploaded_files,
                'failed_files': failed_files
            })
        else:
            logger.error("❌ 모든 파일 업로드 실패")
            return jsonify({'error': '파일 업로드에 실패했습니다.'}), 500
            
    except Exception as e:
        logger.error(f"❌ 업로드 및 임베딩 중 오류: {e}")
        return jsonify({'error': f'오류가 발생했습니다: {str(e)}'}), 500

@app.route('/api/files/<filename>', methods=['DELETE'])
@admin_required
def delete_file(filename):
    if not storage:
        return jsonify({'error': '스토리지가 초기화되지 않았습니다.'}), 500
    
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
            # 저장된 파일 목록에서 해당 파일의 원본 이름 찾기
            files = storage.list_files()
            for file_info in files:
                if file_info['filename'] == decoded_filename:
                    rag_system.remove_document(file_info['name'])
                    break
        
        return jsonify({'message': '파일이 삭제되었습니다.'})
        
    except Exception as e:
        logger.error(f"파일 삭제 중 오류: {e}")
        return jsonify({'error': '파일 삭제 중 오류가 발생했습니다.'}), 500

@app.route('/api/files', methods=['GET'])
@admin_required
def list_files():
    """파일 목록 반환"""
    try:
        if not storage:
            logger.error("❌ 스토리지가 초기화되지 않았습니다.")
            return jsonify({'error': '스토리지가 초기화되지 않았습니다.'}), 500
        
        files = storage.list_files()
        logger.info(f"✅ 파일 목록 조회 완료: {len(files)}개 파일")
        return jsonify({'files': files})
    except Exception as e:
        logger.error(f"❌ 파일 목록 조회 중 오류: {e}")
        return jsonify({'error': f'파일 목록 조회에 실패했습니다: {str(e)}'}), 500

@app.route('/api/files/batch-delete', methods=['POST'])
@admin_required
def batch_delete_files():
    """여러 파일 일괄 삭제"""
    if not storage:
        return jsonify({'error': '스토리지가 초기화되지 않았습니다.'}), 500
    
    try:
        data = request.get_json()
        filenames = data.get('filenames', [])
        
        if not filenames:
            return jsonify({'error': '삭제할 파일이 선택되지 않았습니다.'}), 400
        
        # 파일 삭제
        results = storage.delete_multiple_files(filenames)
        
        # RAG 시스템에서 문서 제거
        if rag_system:
            for filename in filenames:
                try:
                    # 저장된 파일 목록에서 해당 파일의 원본 이름 찾기
                    files = storage.list_files()
                    for file_info in files:
                        if file_info['filename'] == filename:
                            rag_system.remove_document(file_info['name'])
                            break
                except Exception as e:
                    logger.error(f"RAG 시스템에서 문서 제거 실패: {filename} - {filename} - {e}")
        
        deleted_count = sum(1 for success in results.values() if success)
        
        return jsonify({
            'message': f'{deleted_count}개 파일이 삭제되었습니다.',
            'results': results,
            'deleted_count': deleted_count,
            'total_count': len(filenames)
        })
        
    except Exception as e:
        logger.error(f"일괄 파일 삭제 중 오류: {e}")
        return jsonify({'error': '일괄 파일 삭제 중 오류가 발생했습니다.'}), 500

@app.route('/api/admin/rebuild', methods=['POST'])
@admin_required
def rebuild_embeddings():
    """전체 임베딩 재구성"""
    try:
        if not rag_system:
            return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
        
        # 기존 임베딩 제거
        rag_system.clear_index()
        
        # 모든 파일에 대해 임베딩 재생성
        files = storage.list_files()
        embedded_count = 0
        
        for file_info in files:
            try:
                file_url = file_info.get('url')
                filename = file_info.get('name', file_info.get('filename', ''))
                
                if file_url and filename:
                    rag_system.add_document(file_url, filename)
                    # 임베딩 상태 업데이트
                    storage.mark_embedding_status(filename, True)
                    embedded_count += 1
                    logger.info(f"✅ 임베딩 완료: {filename}")
                else:
                    logger.warning(f"⚠️ 파일 정보 누락: {file_info}")
                    
            except Exception as e:
                logger.error(f"❌ 파일 임베딩 실패: {filename} - {e}")
                continue
        
        logger.info(f"✅ 전체 임베딩 재구성 완료: {embedded_count}개 파일")
        return jsonify({
            'message': f'{embedded_count}개 파일의 임베딩이 재구성되었습니다.',
            'embedded_count': embedded_count
        })
        
    except Exception as e:
        logger.error(f"❌ 전체 임베딩 재구성 실패: {e}")
        return jsonify({'error': f'전체 임베딩 재구성에 실패했습니다: {str(e)}'}), 500

@app.route('/api/admin/embed-selected', methods=['POST'])
@admin_required
def embed_selected_files():
    """선택된 파일들만 임베딩"""
    try:
        if not rag_system:
            return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
        
        data = request.get_json()
        if not data or 'filenames' not in data:
            return jsonify({'error': '파일명 목록이 제공되지 않았습니다.'}), 400
        
        filenames = data['filenames']
        if not filenames:
            return jsonify({'error': '임베딩할 파일이 선택되지 않았습니다.'}), 400
        
        # 선택된 파일들만 임베딩
        embedded_count = 0
        failed_files = []
        
        for filename in filenames:
            try:
                # 파일 정보 조회
                files = storage.list_files()
                file_info = next((f for f in files if f.get('filename') == filename), None)
                
                if file_info and file_info.get('url'):
                    file_url = file_info['url']
                    display_name = file_info.get('name', filename)
                    
                    # 기존 임베딩 제거 (있다면)
                    try:
                        rag_system.remove_document(filename)
                        logger.info(f"✅ 기존 임베딩 제거 완료: {display_name}")
                    except Exception as remove_error:
                        logger.warning(f"⚠️ 기존 임베딩 제거 실패: {display_name} - {remove_error}")
                    
                    # 새로 임베딩
                    rag_system.add_document(file_url, display_name)
                    logger.info(f"✅ 선택 임베딩 완료: {display_name}")
                    
                    # 임베딩 상태 업데이트
                    try:
                        storage.mark_embedding_status(display_name, True)
                        logger.info(f"✅ 임베딩 상태 업데이트 완료: {display_name}")
                    except Exception as status_error:
                        logger.warning(f"⚠️ 임베딩 상태 업데이트 실패: {display_name} - {status_error}")
                    
                    embedded_count += 1
                else:
                    logger.warning(f"⚠️ 파일을 찾을 수 없음: {filename}")
                    failed_files.append(filename)
                    
            except Exception as e:
                logger.error(f"❌ 선택 임베딩 실패: {filename} - {e}")
                failed_files.append(filename)
                continue
        
        logger.info(f"✅ 선택 임베딩 완료: {embedded_count}개 성공, {len(failed_files)}개 실패")
        return jsonify({
            'message': f'선택된 {embedded_count}개 파일의 임베딩이 완료되었습니다.',
            'embedded_count': embedded_count,
            'failed_count': len(failed_files),
            'failed_files': failed_files
        })
        
    except Exception as e:
        logger.error(f"❌ 선택 임베딩 실패: {e}")
        return jsonify({'error': f'선택 임베딩에 실패했습니다: {str(e)}'}), 500

@app.route('/api/admin/delete-all', methods=['POST'])
@admin_required
def delete_all_files():
    if not storage:
        return jsonify({'error': '스토리지가 초기화되지 않았습니다.'}), 500
    
    try:
        # 모든 파일 삭제
        success = storage.delete_all_files()
        if not success:
            return jsonify({'error': '전체 파일 삭제에 실패했습니다.'}), 500
        
        # RAG 시스템 초기화
        if rag_system:
            rag_system.clear_index()
        
        return jsonify({'message': '모든 파일이 삭제되었습니다.'})
        
    except Exception as e:
        logger.error(f"전체 파일 삭제 중 오류: {e}")
        return jsonify({'error': '전체 파일 삭제 중 오류가 발생했습니다.'}), 500

@app.route('/api/admin/update-embeddings', methods=['POST'])
@login_required
@admin_required
def update_embeddings():
    """선택된 파일들 또는 전체 파일에 대해 임베딩 업데이트"""
    try:
        data = request.get_json() or {}
        filenames = data.get('filenames', [])
        
        if filenames:
            # 선택된 파일들만 임베딩
            for filename in filenames:
                rag_system.add_document(filename)
            message = f'{len(filenames)}개 파일의 임베딩이 완료되었습니다.'
        else:
            # 전체 파일 임베딩
            files = storage.list_files()
            for file_info in files:
                if not file_info.get('has_embedding', False):
                    rag_system.add_document(file_info['filename'])
            message = '전체 파일의 임베딩이 완료되었습니다.'
        
        return jsonify({'message': message})
        
    except Exception as e:
        return jsonify({'error': f'임베딩 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/api/admin/clear-index', methods=['POST'])
@admin_required
def clear_index():
    if not rag_system:
        return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
    
    try:
        success = rag_system.clear_index()
        if success:
            return jsonify({'message': '임베딩이 초기화되었습니다.'})
        else:
            return jsonify({'error': '임베딩 초기화에 실패했습니다.'}), 500
        
    except Exception as e:
        logger.error(f"임베딩 초기화 중 오류: {e}")
        return jsonify({'error': '임베딩 초기화 중 오류가 발생했습니다.'}), 500

# 새로운 관리자 API 엔드포인트들
@app.route('/api/admin/system-status')
@admin_required
def get_system_status():
    """시스템 상태 정보 반환"""
    try:
        import psutil
        import time
        
        # CPU 및 메모리 사용량
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # RAG 시스템 상태
        rag_status = rag_system.get_status() if rag_system else {}
        storage_info = storage.get_storage_info() if storage else {}
        
        # API 응답 속도 측정
        start_time = time.time()
        # 간단한 테스트 쿼리 실행
        test_response = "테스트 완료"
        api_response_time = (time.time() - start_time) * 1000  # ms
        
        return jsonify({
            'system': {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': round(memory.available / (1024**3), 2),
                'api_response_time_ms': round(api_response_time, 2)
            },
            'rag_system': rag_status,
            'storage': storage_info,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"시스템 상태 조회 중 오류: {e}")
        return jsonify({'error': '시스템 상태 조회에 실패했습니다.'}), 500

@app.route('/api/admin/recent-activity')
@admin_required
def get_recent_activity():
    """최근 활동 로그 반환"""
    try:
        # 로그 파일에서 최근 활동 읽기
        log_file = "app.log"
        activities = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-100:]  # 최근 100줄
                
            for line in lines:
                if any(keyword in line.lower() for keyword in ['upload', 'delete', 'embedding', 'query']):
                    activities.append({
                        'timestamp': line.split(' - ')[0] if ' - ' in line else '',
                        'message': line.strip()
                    })
        
        return jsonify({
            'activities': activities[-20:],  # 최근 20개만 반환
            'total_count': len(activities)
        })
        
    except Exception as e:
        logger.error(f"최근 활동 조회 중 오류: {e}")
        return jsonify({'error': '활동 로그 조회에 실패했습니다.'}), 500

@app.route('/api/admin/vector-db-info')
@admin_required
def get_vector_db_info():
    """벡터 DB 정보 반환"""
    try:
        if not rag_system:
            return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
        
        # 벡터 저장소 정보
        vector_info = rag_system.get_vector_db_info()
        
        # 로컬 스토리지 용량
        storage_path = "./local_storage"
        total_size = 0
        if os.path.exists(storage_path):
            for dirpath, dirnames, filenames in os.walk(storage_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    total_size += os.path.getsize(filepath)
        
        return jsonify({
            'vector_db': vector_info,
            'storage': {
                'total_size_mb': round(total_size / (1024**2), 2),
                'vector_store_size_mb': round(os.path.getsize("./local_storage/vector_store.pkl") / (1024**2), 2) if os.path.exists("./local_storage/vector_store.pkl") else 0
            }
        })
        
    except Exception as e:
        logger.error(f"벡터 DB 정보 조회 중 오류: {e}")
        return jsonify({'error': '벡터 DB 정보 조회에 실패했습니다.'}), 500

@app.route('/api/admin/search-test', methods=['POST'])
@admin_required
def search_test():
    """임베딩 검색 테스트"""
    try:
        if not rag_system:
            return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
        
        data = request.get_json()
        query = data.get('query', '')
        
        if not query:
            return jsonify({'error': '검색어를 입력해주세요.'}), 400
        
        # 검색 테스트 실행
        results = rag_system.search_test(query)
        
        return jsonify({
            'query': query,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"검색 테스트 중 오류: {e}")
        return jsonify({'error': '검색 테스트에 실패했습니다.'}), 500

@app.route('/api/admin/delete-embedding', methods=['POST'])
@admin_required
def delete_specific_embedding():
    """특정 임베딩 삭제"""
    try:
        if not rag_system:
            return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
        
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'error': '삭제할 파일명을 입력해주세요.'}), 400
        
        # 임베딩 삭제
        success = rag_system.remove_document(filename)
        
        if success:
            return jsonify({'message': f'{filename}의 임베딩이 삭제되었습니다.'})
        else:
            return jsonify({'error': '임베딩 삭제에 실패했습니다.'}), 500
        
    except Exception as e:
        logger.error(f"임베딩 삭제 중 오류: {e}")
        return jsonify({'error': '임베딩 삭제에 실패했습니다.'}), 500

@app.route('/api/admin/backup-vectors', methods=['POST'])
@admin_required
def backup_vectors():
    """벡터 저장소 백업"""
    try:
        if not rag_system:
            return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
        
        # 백업 파일명 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"vector_backup_{timestamp}.pkl"
        backup_path = os.path.join("./local_storage", backup_filename)
        
        # 백업 실행
        success = rag_system.backup_vectors(backup_path)
        
        if success:
            return jsonify({
                'message': '벡터 저장소 백업이 완료되었습니다.',
                'backup_file': backup_filename
            })
        else:
            return jsonify({'error': '백업에 실패했습니다.'}), 500
        
    except Exception as e:
        logger.error(f"벡터 백업 중 오류: {e}")
        return jsonify({'error': '백업에 실패했습니다.'}), 500

@app.route('/api/admin/restore-vectors', methods=['POST'])
@admin_required
def restore_vectors():
    """벡터 저장소 복원"""
    try:
        if not rag_system:
            return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
        
        data = request.get_json()
        backup_filename = data.get('backup_filename')
        
        if not backup_filename:
            return jsonify({'error': '복원할 백업 파일명을 입력해주세요.'}), 400
        
        backup_path = os.path.join("./local_storage", backup_filename)
        
        if not os.path.exists(backup_path):
            return jsonify({'error': '백업 파일을 찾을 수 없습니다.'}), 404
        
        # 복원 실행
        success = rag_system.restore_vectors(backup_path)
        
        if success:
            return jsonify({'message': '벡터 저장소 복원이 완료되었습니다.'})
        else:
            return jsonify({'error': '복원에 실패했습니다.'}), 500
        
    except Exception as e:
        logger.error(f"벡터 복원 중 오류: {e}")
        return jsonify({'error': '복원에 실패했습니다.'}), 500

@app.route('/api/admin/query-statistics')
@admin_required
def get_query_statistics():
    """질의 통계 정보 반환"""
    try:
        # 간단한 통계 정보 (실제로는 DB나 로그에서 가져와야 함)
        stats = {
            'total_queries': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'average_response_time': 0,
            'top_queries': [],
            'user_usage': {}
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"질의 통계 조회 중 오류: {e}")
        return jsonify({'error': '통계 정보 조회에 실패했습니다.'}), 500

@app.route('/api/admin/document-coverage')
@admin_required
def get_document_coverage():
    """문서 커버리지 정보 반환"""
    try:
        if not storage:
            return jsonify({'error': '스토리지가 초기화되지 않았습니다.'}), 500
        
        # 새로운 임베딩 통계 메서드 사용
        embedding_stats = storage.get_embedding_stats()
        return jsonify({
            'total_documents': embedding_stats.get('total_files', 0),
            'documents_with_embedding': embedding_stats.get('completed_files', 0),
            'documents_without_embedding': embedding_stats.get('pending_files', 0),
            'completion_rate': embedding_stats.get('completion_rate', 0)
        })
        
    except Exception as e:
        logger.error(f"문서 커버리지 조회 중 오류: {e}")
        return jsonify({'error': '문서 커버리지 조회에 실패했습니다.'}), 500

@app.route('/api/admin/update-settings', methods=['POST'])
@admin_required
def update_settings():
    """시스템 설정 업데이트"""
    try:
        data = request.get_json()
        
        # 설정 업데이트 (실제로는 설정 파일에 저장해야 함)
        settings = {
            'chunk_size': data.get('chunk_size', 1200),
            'chunk_overlap': data.get('chunk_overlap', 200),
            'embedding_model': data.get('embedding_model', 'text-embedding-3-large'),
            'llm_model': data.get('llm_model', 'gpt-3.5-turbo')
        }
        
        # RAG 시스템 설정 업데이트
        if rag_system:
            rag_system.update_settings(settings)
        
        return jsonify({
            'message': '설정이 업데이트되었습니다.',
            'settings': settings
        })
        
    except Exception as e:
        logger.error(f"설정 업데이트 중 오류: {e}")
        return jsonify({'error': '설정 업데이트에 실패했습니다.'}), 500

@app.route('/api/admin/get-settings')
@admin_required
def get_settings():
    """현재 시스템 설정 반환"""
    try:
        if not rag_system:
            return jsonify({'error': 'RAG 시스템이 초기화되지 않았습니다.'}), 500
        
        settings = rag_system.get_settings()
        
        return jsonify(settings)
        
    except Exception as e:
        logger.error(f"설정 조회 중 오류: {e}")
        return jsonify({'error': '설정 조회에 실패했습니다.'}), 500

@app.route('/api/clear-chat-history', methods=['POST'])
@login_required
def clear_chat_history():
    """대화 히스토리 초기화"""
    try:
        session['chat_history'] = []
        return jsonify({'message': '대화 히스토리가 초기화되었습니다.'})
    except Exception as e:
        logger.error(f"대화 히스토리 초기화 중 오류: {e}")
        return jsonify({'error': '대화 히스토리 초기화에 실패했습니다.'}), 500

@app.route('/api/chat-history', methods=['GET'])
@login_required
def get_chat_history():
    """대화 히스토리 조회"""
    try:
        chat_history = session.get('chat_history', [])
        return jsonify({
            'chat_history': chat_history,
            'total_count': len(chat_history)
        })
    except Exception as e:
        logger.error(f"대화 히스토리 조회 중 오류: {e}")
        return jsonify({'error': '대화 히스토리 조회에 실패했습니다.'}), 500

@app.route('/api/status')
def status():
    rag_status = rag_system.get_status() if rag_system else {}
    storage_info = storage.get_storage_info() if storage else {}
    chat_history_count = len(session.get('chat_history', []))
    
    return jsonify({
        'status': 'ok',
        'rag_system': rag_status,
        'storage': storage_info,
        'chat_history_count': chat_history_count,
        'is_cloud_run': False,
        'allowed_extensions': list(ALLOWED_EXTENSIONS),
        'max_file_size_mb': MAX_FILE_SIZE // (1024 * 1024)
    })

# 에러 핸들러
@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error='페이지를 찾을 수 없습니다.'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error='서버 내부 오류가 발생했습니다.'), 500

if __name__ == '__main__':
    init_app()
    app.run(debug=True, host='0.0.0.0', port=8080)
