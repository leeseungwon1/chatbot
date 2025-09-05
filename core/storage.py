import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from werkzeug.utils import secure_filename
import shutil
import json

logger = logging.getLogger(__name__)

class LocalStorage:
    """로컬 파일 시스템 스토리지 클래스"""
    
    def __init__(self, bucket_name: str, project_id: str, is_cloud_run: bool = False):
        self.bucket_name = bucket_name
        self.project_id = project_id
        self.is_cloud_run = is_cloud_run
        self.local_dir = "./local_storage"
        self.documents_dir = os.path.join(self.local_dir, "documents")
        self.metadata_file = os.path.join(self.local_dir, "files_metadata.json")
        
        # 로컬 디렉토리 생성
        os.makedirs(self.local_dir, exist_ok=True)
        os.makedirs(self.documents_dir, exist_ok=True)
        
        # 메타데이터 파일 초기화
        self._init_metadata()
        
        logger.info(f"✅ 로컬 스토리지 초기화 완료: {self.local_dir}")
    
    def _init_metadata(self):
        """메타데이터 파일 초기화"""
        if not os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
    
    def _load_metadata(self) -> Dict[str, Any]:
        """메타데이터 로드"""
        try:
            if not os.path.exists(self.metadata_file):
                logger.info("📝 메타데이터 파일이 존재하지 않습니다. 새로 생성합니다.")
                return {}
            
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 로드된 데이터가 딕셔너리가 아닌 경우 빈 딕셔너리 반환
            if not isinstance(data, dict):
                logger.error(f"❌ 메타데이터가 딕셔너리가 아닙니다: {type(data)}")
                return {}
                
            return data
        except json.JSONDecodeError as e:
            logger.error(f"❌ 메타데이터 JSON 파싱 실패: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ 메타데이터 로드 실패: {e}")
            return {}
    
    def get_metadata(self) -> Dict[str, Any]:
        """메타데이터 조회 (공개 메서드)"""
        return self._load_metadata()
    
    def _save_metadata(self, metadata: Dict[str, Any]):
        """메타데이터 저장"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ 메타데이터 저장 실패: {e}")
    
    def upload_file(self, file) -> str:
        """Flask FileStorage 객체 업로드"""
        try:
            # 원본 파일명 저장
            original_filename = file.filename
            # 파일명 보안 처리
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{filename}"
            file_path = os.path.join(self.documents_dir, safe_filename)
            
            # 파일 저장
            file.save(file_path)
            
            # 메타데이터에 파일 정보 추가
            metadata = self._load_metadata()
            metadata[safe_filename] = {
                'original_name': original_filename,
                'stored_name': safe_filename,
                'size': os.path.getsize(file_path),
                'uploaded_at': datetime.now().isoformat(),
                'content_type': file.content_type or 'application/octet-stream',
                'has_embedding': False
            }
            self._save_metadata(metadata)
            
            logger.info(f"✅ 파일 업로드 완료: {safe_filename} (원본: {original_filename})")
            return f"local://{safe_filename}"
            
        except Exception as e:
            logger.error(f"❌ 파일 업로드 실패: {e}")
            raise
    
    def upload_multiple_files(self, files) -> List[str]:
        """여러 파일 업로드"""
        uploaded_files = []
        for file in files:
            try:
                file_url = self.upload_file(file)
                uploaded_files.append(file_url)
            except Exception as e:
                logger.error(f"❌ 파일 업로드 실패: {file.filename} - {e}")
        
        return uploaded_files
    
    def delete_file(self, filename: str) -> bool:
        """파일 삭제"""
        try:
            file_path = os.path.join(self.documents_dir, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                
                # 메타데이터에서 제거
                metadata = self._load_metadata()
                if filename in metadata:
                    del metadata[filename]
                    self._save_metadata(metadata)
                
                logger.info(f"✅ 파일 삭제 완료: {filename}")
                return True
            else:
                logger.warning(f"⚠️ 파일이 존재하지 않음: {filename}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 파일 삭제 실패: {filename} - {e}")
            return False
    
    def delete_multiple_files(self, filenames: List[str]) -> Dict[str, bool]:
        """여러 파일 삭제"""
        results = {}
        for filename in filenames:
            results[filename] = self.delete_file(filename)
        return results
    
    def delete_all_files(self) -> bool:
        """모든 파일 삭제"""
        try:
            if os.path.exists(self.documents_dir):
                # 모든 파일 삭제
                shutil.rmtree(self.documents_dir)
                os.makedirs(self.documents_dir, exist_ok=True)
                
                # 메타데이터 초기화
                self._save_metadata({})
            
            logger.info("✅ 전체 파일 삭제 완료")
            return True
            
        except Exception as e:
            logger.error(f"❌ 전체 파일 삭제 실패: {e}")
            return False
    
    def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        """파일 목록 조회"""
        try:
            files = []
            metadata = self._load_metadata()
            
            # 메타데이터가 딕셔너리가 아닌 경우 빈 리스트 반환
            if not isinstance(metadata, dict):
                logger.error(f"❌ 메타데이터가 딕셔너리가 아닙니다: {type(metadata)}")
                return []
            
            for stored_name, file_info in metadata.items():
                # file_info가 딕셔너리가 아닌 경우 건너뛰기
                if not isinstance(file_info, dict):
                    logger.warning(f"⚠️ 파일 정보가 딕셔너리가 아닙니다: {stored_name} - {type(file_info)}")
                    continue
                
                # 필수 필드가 없는 경우 건너뛰기
                if 'original_name' not in file_info or 'size' not in file_info or 'uploaded_at' not in file_info or 'content_type' not in file_info:
                    logger.warning(f"⚠️ 파일 정보에 필수 필드가 없습니다: {stored_name}")
                    continue
                
                if prefix == "" or file_info['original_name'].lower().startswith(prefix.lower()):
                    file_path = os.path.join(self.documents_dir, stored_name)
                    if os.path.exists(file_path):
                        try:
                            stat = os.stat(file_path)
                            files.append({
                                'name': file_info['original_name'],
                                'filename': stored_name,
                                'url': f"local://{stored_name}",
                                'size': file_info['size'],
                                'size_mb': round(file_info['size'] / (1024 * 1024), 2),
                                'created': file_info['uploaded_at'],
                                'updated': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                'content_type': file_info['content_type'],
                                'has_embedding': file_info.get('has_embedding', False)
                            })
                        except (KeyError, TypeError, ValueError) as e:
                            logger.warning(f"⚠️ 파일 정보 처리 중 오류: {stored_name} - {e}")
                            continue
            
            # 업로드 시간 역순으로 정렬
            try:
                files.sort(key=lambda x: x['created'], reverse=True)
            except (KeyError, TypeError) as e:
                logger.warning(f"⚠️ 파일 정렬 중 오류: {e}")
            
            logger.info(f"✅ 파일 목록 조회 완료: {len(files)}개 파일")
            return files
            
        except Exception as e:
            logger.error(f"❌ 파일 목록 조회 실패: {e}")
            return []
    
    def download_file(self, filename: str) -> Optional[bytes]:
        """파일 다운로드"""
        try:
            file_path = os.path.join(self.documents_dir, filename)
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    content = f.read()
                logger.info(f"✅ 파일 다운로드 완료: {filename}")
                return content
            else:
                logger.warning(f"⚠️ 파일이 존재하지 않음: {filename}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 파일 다운로드 실패: {filename} - {e}")
            return None
    
    def mark_embedding_status(self, filename: str, has_embedding: bool):
        """임베딩 상태 표시"""
        try:
            metadata = self._load_metadata()
            
            # 저장된 파일명으로 찾기
            stored_name = None
            for stored, file_info in metadata.items():
                if isinstance(file_info, dict) and file_info.get('original_name') == filename:
                    stored_name = stored
                    break
            
            if stored_name and stored_name in metadata:
                metadata[stored_name]['has_embedding'] = has_embedding
                metadata[stored_name]['updated_at'] = datetime.now().isoformat()
                self._save_metadata(metadata)
                logger.info(f"✅ 임베딩 상태 업데이트: {filename} -> {has_embedding}")
                return True
            else:
                # 원본 파일명으로 찾지 못한 경우, 저장된 파일명으로도 시도
                if filename in metadata:
                    metadata[filename]['has_embedding'] = has_embedding
                    metadata[filename]['updated_at'] = datetime.now().isoformat()
                    self._save_metadata(metadata)
                    logger.info(f"✅ 임베딩 상태 업데이트 (저장된 파일명): {filename} -> {has_embedding}")
                    return True
                else:
                    logger.warning(f"⚠️ 파일을 찾을 수 없음: {filename}")
                    # 디버깅을 위해 메타데이터 키들 출력
                    logger.debug(f"🔍 메타데이터 키들: {list(metadata.keys())}")
                    return False
                
        except Exception as e:
            logger.error(f"❌ 임베딩 상태 업데이트 실패: {filename} - {e}")
            return False

    def get_embedding_stats(self) -> Dict[str, Any]:
        """임베딩 통계 정보 반환"""
        try:
            files = self.list_files()
            total_files = len(files)
            completed_files = sum(1 for f in files if f.get('has_embedding', False))
            pending_files = total_files - completed_files
            
            return {
                'total_files': total_files,
                'completed_files': completed_files,
                'pending_files': pending_files,
                'completion_rate': round((completed_files / total_files * 100), 1) if total_files > 0 else 0
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
        """스토리지 정보 조회"""
        try:
            files = self.list_files()
            
            # files가 리스트가 아닌 경우 빈 리스트로 처리
            if not isinstance(files, list):
                logger.warning(f"⚠️ 파일 목록이 리스트가 아닙니다: {type(files)}")
                files = []
            
            total_size = 0
            files_with_embedding = 0
            
            try:
                total_size = sum(file.get('size', 0) for file in files if isinstance(file, dict))
                files_with_embedding = sum(1 for file in files if isinstance(file, dict) and file.get('has_embedding', False))
            except (TypeError, ValueError) as e:
                logger.warning(f"⚠️ 파일 통계 계산 중 오류: {e}")
                total_size = 0
                files_with_embedding = 0
            
            return {
                'bucket_name': self.bucket_name,
                'project_id': self.project_id,
                'total_files': len(files),
                'total_size': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'files_with_embedding': files_with_embedding,
                'files_without_embedding': len(files) - files_with_embedding,
                'is_cloud_run': self.is_cloud_run,
                'initialized': True,
                'files': files
            }
            
        except Exception as e:
            logger.error(f"❌ 스토리지 정보 조회 실패: {e}")
            return {
                'bucket_name': self.bucket_name,
                'project_id': self.project_id,
                'total_files': 0,
                'total_size': 0,
                'total_size_mb': 0,
                'files_with_embedding': 0,
                'files_without_embedding': 0,
                'is_cloud_run': self.is_cloud_run,
                'initialized': False,
                'error': str(e),
                'files': []
            }
