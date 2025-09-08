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
        
        # Cloud Storage 클라이언트 초기화 (재시도 로직 포함)
        self.client = None
        self.bucket = None
        self._initialize_client_with_retry()
    
    def _initialize_client_with_retry(self, max_retries: int = 3):
        """재시도 로직을 포함한 클라이언트 초기화"""
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 Cloud Storage 클라이언트 초기화 시도 {attempt + 1}/{max_retries}")
                
                # Cloud Storage 클라이언트 초기화 (기본 방식)
                self.client = storage.Client(project=self.project_id)
                self.bucket = self.client.bucket(self.bucket_name)
                
                # 연결 테스트 (간단한 버킷 존재 확인)
                try:
                    bucket_exists = self.bucket.exists()
                    logger.info(f"✅ Cloud Storage 초기화 완료: {self.bucket_name} (버킷 존재: {bucket_exists})")
                    return
                except Exception as test_error:
                    logger.warning(f"⚠️ 연결 테스트 실패, 재시도: {test_error}")
                    raise test_error
                    
            except Exception as e:
                logger.warning(f"⚠️ Cloud Storage 초기화 실패 (시도 {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    import time
                    wait_time = (attempt + 1) * 2  # 2, 4, 6초 대기
                    logger.info(f"⏳ {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Cloud Storage 초기화 최종 실패: {e}")
                    # 초기화 실패해도 클라이언트는 None으로 유지하여 나중에 재시도 가능
                    self.client = None
                    self.bucket = None
                    raise
    
    def upload_file(self, file) -> str:
        """파일을 Cloud Storage에 업로드"""
        try:
            # 원본 파일명 저장
            original_filename = file.filename
            # 안전한 파일명 생성
            secure_name = secure_filename(original_filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stored_filename = f"{timestamp}_{secure_name}"
            
            # Cloud Storage에 업로드
            blob = self.bucket.blob(f"documents/{stored_filename}")
            blob.upload_from_file(file)
            
            # 메타데이터 저장
            metadata = {
                'original_name': original_filename,
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
            
            logger.info(f"✅ 파일 업로드 완료: {original_filename} -> {stored_filename}")
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
                
                if not blob.exists():
                    logger.error(f"❌ 파일이 존재하지 않음: {path}")
                    raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
                
                content = blob.download_as_bytes()
                logger.info(f"✅ Cloud Storage에서 파일 다운로드 성공: {len(content)} bytes")
                return content
            else:
                # 로컬 파일 경로인 경우
                if not os.path.exists(file_url):
                    logger.error(f"❌ 로컬 파일이 존재하지 않음: {file_url}")
                    raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_url}")
                
                with open(file_url, 'rb') as f:
                    content = f.read()
                logger.info(f"✅ 로컬 파일에서 다운로드 성공: {len(content)} bytes")
                return content
        except Exception as e:
            logger.error(f"❌ 파일 다운로드 실패: {e}")
            import traceback
            logger.error(f"❌ 상세 오류: {traceback.format_exc()}")
            raise
    
    def get_metadata(self) -> Dict[str, Any]:
        """모든 파일의 메타데이터 조회 (재시도 로직 포함)"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 클라이언트가 초기화되지 않은 경우 재시도
                if not self.client or not self.bucket:
                    logger.info(f"🔄 클라이언트 재초기화 시도 {attempt + 1}/{max_retries}")
                    try:
                        self._initialize_client_with_retry()
                    except Exception as init_error:
                        logger.error(f"❌ 클라이언트 재초기화 실패: {init_error}")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            return {}
                
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
                logger.warning(f"⚠️ 메타데이터 조회 실패 (시도 {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    import time
                    wait_time = (attempt + 1) * 2
                    logger.info(f"⏳ {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ 메타데이터 조회 최종 실패: {e}")
                    return {}
    
    def mark_embedding_status(self, filename: str, has_embedding: bool):
        """임베딩 상태 업데이트"""
        try:
            # 먼저 원본 파일명으로 메타데이터 찾기
            metadata = self.get_metadata()
            target_metadata_blob = None
            found_filename = None
            
            # 원본 파일명으로 찾기
            for stored_filename, file_metadata in metadata.items():
                if file_metadata.get('original_name') == filename:
                    target_metadata_blob = self.bucket.blob(f"metadata/{stored_filename}.json")
                    found_filename = stored_filename
                    break
            
            # 원본 파일명으로 찾지 못한 경우, 저장된 파일명으로 시도
            if not target_metadata_blob:
                # 저장된 파일명으로 직접 시도
                if filename in metadata:
                    target_metadata_blob = self.bucket.blob(f"metadata/{filename}.json")
                    found_filename = filename
                else:
                    # 확장자 제거하고 시도
                    filename_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
                    for stored_filename, file_metadata in metadata.items():
                        if stored_filename == filename or stored_filename.startswith(filename_without_ext):
                            target_metadata_blob = self.bucket.blob(f"metadata/{stored_filename}.json")
                            found_filename = stored_filename
                            break
            
            if target_metadata_blob and target_metadata_blob.exists():
                # 기존 메타데이터 로드
                content = target_metadata_blob.download_as_text()
                metadata_data = json.loads(content)
                
                # 임베딩 상태 업데이트
                metadata_data['has_embedding'] = has_embedding
                metadata_data['updated_at'] = datetime.now().isoformat()
                
                # 업데이트된 메타데이터 저장
                target_metadata_blob.upload_from_string(
                    json.dumps(metadata_data, ensure_ascii=False, indent=2),
                    content_type='application/json'
                )
                
                logger.info(f"✅ 임베딩 상태 업데이트: {filename} -> {has_embedding} (메타데이터: {found_filename})")
            else:
                logger.warning(f"⚠️ 메타데이터 파일을 찾을 수 없음: {filename}")
                # 디버깅을 위해 메타데이터 목록 출력
                logger.info(f"ℹ️ 사용 가능한 메타데이터 파일들: {list(metadata.keys())}")
                
        except Exception as e:
            logger.error(f"❌ 임베딩 상태 업데이트 실패: {e}")
            import traceback
            logger.error(f"❌ 상세 오류: {traceback.format_exc()}")
    
    def delete_file(self, filename: str) -> bool:
        """파일 삭제"""
        try:
            # 먼저 메타데이터에서 실제 저장된 파일명 찾기
            metadata = self.get_metadata()
            stored_filename = None
            
            # 원본 파일명으로 찾기
            for stored_name, file_metadata in metadata.items():
                if file_metadata.get('original_name') == filename:
                    stored_filename = stored_name
                    break
            
            # 원본 파일명으로 찾지 못한 경우, 저장된 파일명으로 시도
            if not stored_filename:
                stored_filename = filename
            
            # 문서 파일 삭제
            doc_blob = self.bucket.blob(f"documents/{stored_filename}")
            if doc_blob.exists():
                doc_blob.delete()
                logger.info(f"✅ 문서 파일 삭제: {stored_filename}")
            else:
                logger.warning(f"⚠️ 문서 파일을 찾을 수 없음: {stored_filename}")
            
            # 메타데이터 파일 삭제
            metadata_blob = self.bucket.blob(f"metadata/{stored_filename}.json")
            if metadata_blob.exists():
                metadata_blob.delete()
                logger.info(f"✅ 메타데이터 파일 삭제: {stored_filename}.json")
            else:
                logger.warning(f"⚠️ 메타데이터 파일을 찾을 수 없음: {stored_filename}.json")
            
            logger.info(f"✅ 파일 삭제 완료: {filename} (저장된 파일명: {stored_filename})")
            return True
            
        except Exception as e:
            logger.error(f"❌ 파일 삭제 실패: {e}")
            return False
    
    def list_files(self) -> List[Dict[str, Any]]:
        """파일 목록 조회"""
        try:
            files = []
            metadata = self.get_metadata()
            
            for filename, file_metadata in metadata.items():
                files.append({
                    'name': file_metadata.get('original_name', filename),
                    'filename': filename,
                    'size': file_metadata.get('size', 0),
                    'size_mb': round(file_metadata.get('size', 0) / (1024 * 1024), 2),
                    'uploaded_at': file_metadata.get('uploaded_at', ''),
                    'created': file_metadata.get('uploaded_at', ''),
                    'updated': file_metadata.get('updated_at', file_metadata.get('uploaded_at', '')),
                    'has_embedding': file_metadata.get('has_embedding', False),
                    'url': f"gs://{self.bucket_name}/documents/{filename}",
                    'content_type': file_metadata.get('content_type', '')
                })
            
            # 업로드 시간순으로 정렬
            files.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)
            
            logger.info(f"✅ 파일 목록 조회 완료: {len(files)}개 파일")
            return files
            
        except Exception as e:
            logger.error(f"❌ 파일 목록 조회 실패: {e}")
            return []
    
    def delete_multiple_files(self, filenames: List[str]) -> Dict[str, bool]:
        """여러 파일 일괄 삭제"""
        results = {}
        for filename in filenames:
            results[filename] = self.delete_file(filename)
        return results
    
    def delete_all_files(self) -> bool:
        """모든 파일 삭제"""
        try:
            # 문서 파일들 삭제
            doc_blobs = list(self.bucket.list_blobs(prefix="documents/"))
            for blob in doc_blobs:
                blob.delete()
            
            # 메타데이터 파일들 삭제
            metadata_blobs = list(self.bucket.list_blobs(prefix="metadata/"))
            for blob in metadata_blobs:
                blob.delete()
            
            logger.info(f"✅ 모든 파일 삭제 완료: {len(doc_blobs)}개 문서, {len(metadata_blobs)}개 메타데이터")
            return True
            
        except Exception as e:
            logger.error(f"❌ 전체 파일 삭제 실패: {e}")
            return False
    
    def get_embedding_stats(self) -> Dict[str, Any]:
        """임베딩 통계 조회"""
        try:
            metadata = self.get_metadata()
            total_files = len(metadata)
            completed_files = sum(1 for m in metadata.values() if m.get('has_embedding', False))
            pending_files = total_files - completed_files
            completion_rate = (completed_files / total_files * 100) if total_files > 0 else 0
            
            return {
                'total_files': total_files,
                'completed_files': completed_files,
                'pending_files': pending_files,
                'completion_rate': round(completion_rate, 2)
            }
            
        except Exception as e:
            logger.error(f"❌ 임베딩 통계 조회 실패: {e}")
            return {
                'total_files': 0,
                'completed_files': 0,
                'pending_files': 0,
                'completion_rate': 0
            }
    
    def get_storage_info(self) -> Dict[str, Any]:
        """저장소 정보 조회 (재시도 로직 포함)"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 클라이언트가 초기화되지 않은 경우 재시도
                if not self.client or not self.bucket:
                    logger.info(f"🔄 클라이언트 재초기화 시도 {attempt + 1}/{max_retries}")
                    try:
                        self._initialize_client_with_retry()
                    except Exception as init_error:
                        logger.error(f"❌ 클라이언트 재초기화 실패: {init_error}")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            return {
                                'type': 'cloud_storage',
                                'error': f'클라이언트 초기화 실패: {init_error}',
                                'bucket_name': self.bucket_name,
                                'project_id': self.project_id
                            }
                
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
                logger.warning(f"⚠️ 저장소 정보 조회 실패 (시도 {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    import time
                    wait_time = (attempt + 1) * 2
                    logger.info(f"⏳ {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ 저장소 정보 조회 최종 실패: {e}")
                    return {
                        'type': 'cloud_storage',
                        'error': str(e),
                        'bucket_name': self.bucket_name,
                        'project_id': self.project_id
                    }
