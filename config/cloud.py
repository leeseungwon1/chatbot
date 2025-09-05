from . import BaseConfig

class CloudConfig(BaseConfig):
    """Cloud Run 환경 설정"""
    
    def __init__(self):
        super().__init__()
        self.ENVIRONMENT = 'cloud'
        self.IS_CLOUD_RUN = True
        self.GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'armychatbottest')
        self.GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'chatbot-storage-new')
