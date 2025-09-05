import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from werkzeug.utils import secure_filename
import json
from google.cloud import storage
from google.cloud.exceptions import NotFound

logger = logging.getLogger(__name__)

class CloudStorage:
    """Google Cloud Storage 클래스"""
    
    def __init__(self, bucket_name: str, project_id: str, is_cloud_run: bool = True):
        self.bucket_name = bucket_name
        self.project_id = project_id
        self.is_cloud_run = is_cloud_run
        
        # Cloud Storage 클라이언트 초기화
        try:
            self.client = storage.Client(project=project_id)
            self.bucket = self.client.bucket(bucket_name)
            logger.info(f"✅ Cloud Storage 초기화 완료: {bucket_name}")
        except Exception as e:
            logger.error(f"❌ Cloud Storage 초기화 실패: {e}")
            raise
    
    def upload_file(self, file, filename: str) -> str:
        """파일을 Cloud Storage에 업로드"""
        try:
            # 안전한 파일명 생성
            secure_name = secure_filename(filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stored_filename = f"{timestamp}_{secure_name}"
            
            # Cloud Storage에 업로드
            blob = self.bucket.blob(f"documents/{stored_filename}")
            blob.upload_from_file(file)
            
            # 메타데이터 저장
            metadata = {
                'original_name': filename,
                'stored_name': stored_filename,
                'size': blob.size,
                'uploaded_at': datetime.now().isoformat(),
                'content_type': blob.content_type,
                'has_embedding': False,
                'updated_at': datetime.now().isoformat()
            }
            
            # 메타데이터를 별도 파일로 저장
            metadata_blob = self.bucket.blob(f"metadata/{stored_filename}.json")
            metadata_blob.upload_from_string(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                content_type='application/json'
            )
            
            logger.info(f"✅ 파일 업로드 완료: {filename} -> {stored_filename}")
            return f"gs://{self.bucket_name}/documents/{stored_filename}"
            
        except Exception as e:
            logger.error(f"❌ 파일 업로드 실패: {e}")
            raise
    
    def download_file(self, file_url: str) -> bytes:
        """Cloud Storage에서 파일 다운로드"""
        try:
            if file_url.startswith('gs://'):
                # gs://bucket/path 형식에서 경로 추출
                path = file_url.replace(f"gs://{self.bucket_name}/", "")
                blob = self.bucket.blob(path)
                return blob.download_as_bytes()
            else:
                # 로컬 파일 경로인 경우
                with open(file_url, 'rb') as f:
                    return f.read()
        except Exception as e:
            logger.error(f"❌ 파일 다운로드 실패: {e}")
            raise
    
    def get_metadata(self) -> Dict[str, Any]:
        """모든 파일의 메타데이터 조회"""
        try:
            metadata = {}
            blobs = self.bucket.list_blobs(prefix="metadata/")
            
            for blob in blobs:
                if blob.name.endswith('.json'):
                    try:
                        content = blob.download_as_text()
                        data = json.loads(content)
                        # 파일명에서 .json 제거
                        filename = blob.name.replace("metadata/", "").replace(".json", "")
                        metadata[filename] = data
                    except Exception as e:
                        logger.warning(f"⚠️ 메타데이터 로드 실패: {blob.name} - {e}")
            
            return metadata
        except Exception as e:
            logger.error(f"❌ 메타데이터 조회 실패: {e}")
            return {}
    
    def mark_embedding_status(self, filename: str, has_embedding: bool):
        """임베딩 상태 업데이트"""
        try:
            metadata_blob = self.bucket.blob(f"metadata/{filename}.json")
            
            if metadata_blob.exists():
                # 기존 메타데이터 로드
                content = metadata_blob.download_as_text()
                metadata = json.loads(content)
                
                # 임베딩 상태 업데이트
                metadata['has_embedding'] = has_embedding
                metadata['updated_at'] = datetime.now().isoformat()
                
                # 업데이트된 메타데이터 저장
                metadata_blob.upload_from_string(
                    json.dumps(metadata, ensure_ascii=False, indent=2),
                    content_type='application/json'
                )
                
                logger.info(f"✅ 임베딩 상태 업데이트: {filename} -> {has_embedding}")
            else:
                logger.warning(f"⚠️ 메타데이터 파일을 찾을 수 없음: {filename}")
                
        except Exception as e:
            logger.error(f"❌ 임베딩 상태 업데이트 실패: {e}")
    
    def delete_file(self, filename: str) -> bool:
        """파일 삭제"""
        try:
            # 문서 파일 삭제
            doc_blob = self.bucket.blob(f"documents/{filename}")
            if doc_blob.exists():
                doc_blob.delete()
            
            # 메타데이터 파일 삭제
            metadata_blob = self.bucket.blob(f"metadata/{filename}.json")
            if metadata_blob.exists():
                metadata_blob.delete()
            
            logger.info(f"✅ 파일 삭제 완료: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 파일 삭제 실패: {e}")
            return False
    
    def get_storage_info(self) -> Dict[str, Any]:
        """저장소 정보 조회"""
        try:
            # 버킷 정보
            bucket_info = {
                'name': self.bucket_name,
                'location': self.bucket.location,
                'storage_class': self.bucket.storage_class,
                'created': self.bucket.time_created.isoformat() if self.bucket.time_created else None
            }
            
            # 파일 통계
            doc_blobs = list(self.bucket.list_blobs(prefix="documents/"))
            metadata_blobs = list(self.bucket.list_blobs(prefix="metadata/"))
            
            total_size = sum(blob.size for blob in doc_blobs if blob.size)
            
            return {
                'type': 'cloud_storage',
                'bucket_info': bucket_info,
                'total_files': len(doc_blobs),
                'total_size': total_size,
                'metadata_files': len(metadata_blobs)
            }
            
        except Exception as e:
            logger.error(f"❌ 저장소 정보 조회 실패: {e}")
            return {
                'type': 'cloud_storage',
                'error': str(e)
            }
