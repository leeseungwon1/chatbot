from . import BaseConfig

class LocalConfig(BaseConfig):
    """로컬 개발 환경 설정"""
    
    def __init__(self):
        super().__init__()
        self.ENVIRONMENT = 'local'
        self.IS_CLOUD_RUN = False
        self.GCP_PROJECT_ID = 'local'
        self.GCS_BUCKET_NAME = 'local-storage'
