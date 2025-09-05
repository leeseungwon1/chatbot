# 로컬 테스트용 환경 변수 설정
import os

# RAG 시스템 설정
os.environ['CHUNK_SIZE'] = '1200'
os.environ['CHUNK_OVERLAP'] = '200'

# Flask 설정
os.environ['FLASK_ENV'] = 'development'
os.environ['FLASK_DEBUG'] = 'True'

print("✅ 로컬 환경 변수 설정 완료")
print("📁 로컬 스토리지 디렉토리: ./local_storage/")
print("🌐 웹 서버: http://localhost:8080")
print("🚀 이제 python app.py로 실행할 수 있습니다!")
