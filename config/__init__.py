import os
from typing import Optional

def get_config():
    """환경에 따른 설정 반환 (Cloud 전용)"""
    environment = os.getenv('ENVIRONMENT', 'cloud')
    
    if environment == 'cloud':
        from .cloud import CloudConfig
        return CloudConfig()
    else:
        # 로컬 환경도 Cloud 설정 사용
        from .cloud import CloudConfig
        return CloudConfig()

class BaseConfig:
    """기본 설정 클래스"""
    
    def __init__(self):
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
        self.SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
        self.CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', '1200'))
        self.CHUNK_OVERLAP = int(os.getenv('CHUNK_OVERLAP', '200'))
        self.EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-large')
        self.LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-3.5-turbo')
