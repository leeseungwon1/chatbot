import os
import tempfile
import logging
from typing import List, Optional, Dict, Any
import openai
import requests
import pickle
import json
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

class RAGSystem:
    """향상된 RAG 시스템 - OpenAI API 직접 사용"""
    
    def __init__(self, storage=None, chunk_size: int = 1200, chunk_overlap: int = 200):
        self.storage = storage
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.documents = []
        self.embeddings = []
        self.vector_store = {}
        self.embedding_model = "text-embedding-3-large"
        self.llm_model = "gpt-3.5-turbo"
        
        # 기존 벡터 저장소 로드 (API 키와 무관하게 로드)
        self._load_vector_store()
        
        # OpenAI API 키 설정
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            logger.warning("⚠️ OPENAI_API_KEY가 설정되지 않았습니다. 질의응답 기능은 사용할 수 없습니다.")
        else:
            openai.api_key = self.openai_api_key
            logger.info("✅ OpenAI API 키 설정 완료")
            
        logger.info("✅ RAG 시스템 초기화 완료")
    
    def _load_vector_store(self):
        """벡터 저장소 로드"""
        try:
            if self.storage:
                # Cloud Storage인 경우
                if hasattr(self.storage, 'bucket'):
                    try:
                        vector_blob = self.storage.bucket.blob("vector_store/vector_store.pkl")
                        if vector_blob.exists():
                            vector_data = vector_blob.download_as_bytes()
                            data = pickle.loads(vector_data)
                            self.documents = data.get('documents', [])
                            self.embeddings = data.get('embeddings', [])
                            self.vector_store = data.get('vector_store', {})
                            logger.info(f"✅ Cloud Storage에서 벡터 저장소 로드 완료: {len(self.documents)}개 문서, {len(self.embeddings)}개 임베딩")
                            
                            # 벡터 저장소가 비어있거나 스토리지에 파일이 더 많은 경우 자동 임베딩
                            if self.storage:
                                files = self.storage.list_files()
                                logger.info(f"📁 스토리지에서 {len(files)}개 파일 발견")
                                
                                # 벡터 저장소의 문서 수와 스토리지의 파일 수 비교
                                if len(self.documents) == 0 or len(self.documents) < len(files):
                                    logger.info("🔍 벡터 저장소가 비어있거나 불완전합니다. 기존 파일들을 확인합니다...")
                                    try:
                                        for file_info in files:
                                            try:
                                                file_url = file_info.get('url')
                                                original_name = file_info.get('name')  # 원본 파일명
                                                
                                                if file_url and original_name:
                                                    logger.info(f"📄 자동 임베딩 시작: {original_name}")
                                                    success = self.add_document(file_url, original_name)
                                                    if success:
                                                        logger.info(f"✅ 자동 임베딩 완료: {original_name}")
                                                    else:
                                                        logger.error(f"❌ 자동 임베딩 실패: {original_name}")
                                            except Exception as e:
                                                logger.error(f"❌ 자동 임베딩 중 오류: {file_info.get('name', 'unknown')} - {e}")
                                    except Exception as e:
                                        logger.error(f"❌ 기존 파일 확인 중 오류: {e}")
                        else:
                            logger.warning("⚠️ Cloud Storage에 벡터 저장소 파일이 존재하지 않습니다. 새로 생성해야 합니다.")
                    except Exception as e:
                        logger.error(f"❌ Cloud Storage 벡터 저장소 로드 실패: {e}")
                else:
                    # 로컬 스토리지인 경우
                    vector_file = os.path.join(self.storage.local_dir, "vector_store.pkl")
                    logger.info(f"🔍 벡터 파일 경로: {vector_file}")
                    logger.info(f"🔍 벡터 파일 존재 여부: {os.path.exists(vector_file)}")
                    
                    if os.path.exists(vector_file):
                        with open(vector_file, 'rb') as f:
                            data = pickle.load(f)
                            self.documents = data.get('documents', [])
                            self.embeddings = data.get('embeddings', [])
                            self.vector_store = data.get('vector_store', {})
                        logger.info(f"✅ 로컬 벡터 저장소 로드 완료: {len(self.documents)}개 문서, {len(self.embeddings)}개 임베딩")
                    else:
                        logger.warning("⚠️ 로컬 벡터 저장소 파일이 존재하지 않습니다. 새로 생성해야 합니다.")
            else:
                logger.warning("⚠️ 스토리지가 설정되지 않았습니다.")
        except Exception as e:
            logger.error(f"❌ 벡터 저장소 로드 실패: {e}")
            import traceback
            logger.error(f"❌ 상세 오류: {traceback.format_exc()}")
    
    def _save_vector_store(self):
        """벡터 저장소 저장"""
        try:
            if self.storage:
                data = {
                    'documents': self.documents,
                    'embeddings': self.embeddings,
                    'vector_store': self.vector_store
                }
                
                # Cloud Storage인 경우
                if hasattr(self.storage, 'bucket'):
                    try:
                        vector_blob = self.storage.bucket.blob("vector_store/vector_store.pkl")
                        vector_data = pickle.dumps(data)
                        vector_blob.upload_from_string(vector_data, content_type='application/octet-stream')
                        logger.info("✅ Cloud Storage에 벡터 저장소 저장 완료")
                    except Exception as e:
                        logger.error(f"❌ Cloud Storage 벡터 저장소 저장 실패: {e}")
                else:
                    # 로컬 스토리지인 경우
                    vector_file = os.path.join(self.storage.local_dir, "vector_store.pkl")
                    with open(vector_file, 'wb') as f:
                        pickle.dump(data, f)
                    logger.info("✅ 로컬 벡터 저장소 저장 완료")
        except Exception as e:
            logger.error(f"❌ 벡터 저장소 저장 실패: {e}")
    
    def _get_embedding(self, text: str) -> List[float]:
        """텍스트 임베딩 생성"""
        try:
            response = openai.Embedding.create(
                model=self.embedding_model,
                input=text
            )
            return response['data'][0]['embedding']
        except Exception as e:
            logger.error(f"❌ 임베딩 생성 실패: {e}")
            return []
    
    def _split_text(self, text: str) -> List[str]:
        """텍스트를 청크로 분할 (안전한 버전)"""
        try:
            # 기존 방식으로 안전하게 분할
            chunks = []
            start = 0
            
            while start < len(text):
                end = start + self.chunk_size
                chunk = text[start:end]
                chunks.append(chunk)
                start = end - self.chunk_overlap
                if start >= len(text):
                    break
                    
            return chunks
        except Exception as e:
            logger.error(f"❌ 텍스트 분할 실패: {e}")
            # 오류 시 기본 분할
            return [text[i:i+self.chunk_size] for i in range(0, len(text), self.chunk_size)]
    
    def add_document(self, file_url: str, filename: str) -> bool:
        """문서 추가"""
        try:
            if not self.storage:
                logger.error("❌ 스토리지가 초기화되지 않았습니다")
                return False
            
            # file_url에서 실제 저장된 파일명 추출
            if file_url.startswith('local://'):
                stored_filename = file_url.replace('local://', '')
            else:
                stored_filename = filename
            
            # 파일명에서 실제 파일명 추출 (메타데이터에서 원본명 가져오기)
            actual_filename = stored_filename
            try:
                # 메타데이터에서 원본 파일명 가져오기
                if self.storage:
                    metadata = self.storage.get_metadata()
                    if stored_filename in metadata and 'original_name' in metadata[stored_filename]:
                        original_name = metadata[stored_filename]['original_name']
                        # 확장자 제거
                        if '.' in original_name:
                            actual_filename = original_name.rsplit('.', 1)[0]
                        else:
                            actual_filename = original_name
                        logger.info(f"📄 원본 파일명 사용: {actual_filename}")
                    else:
                        # 메타데이터가 없으면 확장자만 제거
                        if '.' in stored_filename:
                            actual_filename = stored_filename.rsplit('.', 1)[0]
                        logger.info(f"📄 저장된 파일명 사용 (확장자 제거): {actual_filename}")
            except Exception as e:
                logger.warning(f"⚠️ 파일명 추출 실패, 원본 사용: {e}")
                actual_filename = stored_filename
                if '.' in actual_filename:
                    actual_filename = actual_filename.rsplit('.', 1)[0]
            
            logger.info(f"📄 문서 추가 시작: {actual_filename} (저장된 파일명: {stored_filename})")
            
            # 문서 로드
            content = self._load_document(file_url, stored_filename)
            if not content:
                logger.error(f"❌ 문서 로드 실패: {stored_filename}")
                return False
            
            # 텍스트 분할
            chunks = self._split_text(content)
            logger.info(f"📝 텍스트 분할 완료: {len(chunks)}개 청크")
            
            # 각 청크에 대해 임베딩 생성
            for i, chunk in enumerate(chunks):
                embedding = self._get_embedding(chunk)
                if embedding:
                    self.documents.append({
                        'content': chunk,
                        'filename': actual_filename,
                        'stored_filename': stored_filename,
                        'chunk_id': i
                    })
                    self.embeddings.append(embedding)
                    self.vector_store[f"{actual_filename}_{i}"] = embedding
            
            # 벡터 저장소 저장
            self._save_vector_store()
            
            # 스토리지에 임베딩 상태 표시
            self.storage.mark_embedding_status(stored_filename, True)
            
            logger.info(f"✅ 문서 추가 완료: {actual_filename} ({len(chunks)}개 청크)")
            return True
            
        except Exception as e:
            logger.error(f"❌ 문서 추가 실패: {filename} - {e}")
            return False
    
    def _load_document(self, file_url: str, filename: str) -> Optional[str]:
        """문서 로드"""
        try:
            # 파일 확장자 확인
            file_ext = filename.lower().split('.')[-1]
            
            logger.info(f"📖 문서 로드 시작: {filename} (확장자: {file_ext})")
            
            # 임시 파일로 다운로드
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as temp_file:
                if file_url.startswith('local://'):
                    # 로컬 파일에서 다운로드
                    if self.storage:
                        content = self.storage.download_file(filename)
                        if content:
                            temp_file.write(content)
                            logger.info(f"✅ 로컬 파일에서 다운로드: {len(content)} bytes")
                        else:
                            raise ValueError(f"로컬 파일을 읽을 수 없습니다: {filename}")
                elif file_url.startswith('gs://'):
                    # Google Cloud Storage URL에서 다운로드
                    if self.storage and hasattr(self.storage, 'bucket'):
                        # Cloud Storage 클라이언트 사용
                        blob_name = file_url.replace(f"gs://{self.storage.bucket_name}/", "")
                        blob = self.storage.bucket.blob(blob_name)
                        content = blob.download_as_bytes()
                        temp_file.write(content)
                        logger.info(f"✅ Cloud Storage에서 다운로드: {len(content)} bytes")
                    else:
                        raise ValueError("Cloud Storage 클라이언트가 설정되지 않았습니다")
                else:
                    # HTTP URL에서 다운로드
                    response = requests.get(file_url)
                    response.raise_for_status()
                    temp_file.write(response.content)
                    logger.info(f"✅ HTTP URL에서 다운로드: {len(response.content)} bytes")
                
                temp_file_path = temp_file.name
            
            # 파일 내용 읽기
            if file_ext == 'pdf':
                try:
                    import PyPDF2
                    with open(temp_file_path, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        text = ""
                        for page in pdf_reader.pages:
                            text += page.extract_text() + "\n"
                except ImportError:
                    logger.error("❌ PyPDF2가 설치되지 않았습니다")
                    return None
            elif file_ext in ['docx', 'doc']:
                try:
                    import docx2txt
                    text = docx2txt.process(temp_file_path)
                except ImportError:
                    logger.error("❌ docx2txt가 설치되지 않았습니다")
                    return None
            elif file_ext == 'txt':
                with open(temp_file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            else:
                logger.error(f"❌ 지원하지 않는 파일 형식: {file_ext}")
                return None
            
            # 임시 파일 삭제
            os.unlink(temp_file_path)
            
            logger.info(f"✅ 문서 로드 완료: {filename} ({len(text)} 문자)")
            return text
            
        except Exception as e:
            logger.error(f"❌ 문서 로드 실패: {filename} - {e}")
            return None
    
    def query(self, question: str, chat_history: list = None) -> str:
        """질의응답 (맥락 지원)"""
        try:
            logger.info(f"🔍 질의 시작: {question[:50]}...")
            logger.info(f"🔍 현재 임베딩 수: {len(self.embeddings)}")
            logger.info(f"🔍 현재 문서 수: {len(self.documents)}")
            
            if not self.embeddings:
                logger.warning("⚠️ 임베딩이 없습니다. 문서를 먼저 업로드해주세요.")
                return "아직 문서가 추가되지 않았습니다. 먼저 문서를 업로드해주세요."
            
            if not self.openai_api_key:
                logger.warning("⚠️ OpenAI API 키가 설정되지 않았습니다.")
                return "OpenAI API 키가 설정되지 않았습니다. 관리자에게 문의해주세요."
            
            # 파일명 관련 질문에 대한 특별 처리
            filename_keywords = [
                '파일명', '문서명', '저장하고 있는', '업로드된', '문서가 뭐', 
                '저장되어 있는', '문서 목록', '목록', '리스트', '어떤 문서',
                '무슨 문서', '문서들', '파일들', '업로드한', '등록된'
            ]
            if any(keyword in question.lower() for keyword in filename_keywords):
                return self._handle_filename_question(question)
            
            # 질문 임베딩 생성
            question_embedding = self._get_embedding(question)
            if not question_embedding:
                return "질문 처리 중 오류가 발생했습니다."
            
            # 가장 유사한 문서 찾기 (상위 5개로 확장)
            similarities = []
            for i, doc_embedding in enumerate(self.embeddings):
                score = self._cosine_similarity(question_embedding, doc_embedding)
                similarities.append((score, i))
            
            # 유사도 순으로 정렬하고 상위 5개 선택 (검색 정확도 향상)
            similarities.sort(reverse=True)
            top_docs = similarities[:5]
            
            # 디버깅을 위한 로그 추가
            logger.info(f"🔍 검색 결과: 상위 5개 유사도 점수 = {[f'{score:.3f}' for score, _ in top_docs[:5]]}")
            
            if not top_docs or top_docs[0][0] < 0.03:  # 유사도 임계값 더 낮춤
                logger.warning(f"⚠️ 유사도가 너무 낮음: 최고 점수 = {top_docs[0][0] if top_docs else 0}")
                return "관련 문서를 찾을 수 없습니다."
            
            # 상위 문서들의 내용을 결합 (연속된 청크 연결)
            context = ""
            processed_docs = set()  # 중복 처리 방지
            
            for score, idx in top_docs:
                if score > 0.1 and idx not in processed_docs:  # 유사도가 낮은 문서는 제외
                    # 파일명에서 확장자 제거하고 더 명확하게 표시
                    filename = self.documents[idx]['filename']
                    if '.' in filename:
                        display_name = filename.rsplit('.', 1)[0]  # 확장자 제거
                    else:
                        display_name = filename
                    
                    # 연속된 청크들을 찾아서 연결
                    connected_chunks = self._get_connected_chunks(idx, display_name)
                    context += f"\n\n=== {display_name} ===\n{connected_chunks}"
                    
                    # 처리된 청크들 마킹
                    for chunk_idx in self._get_related_chunk_indices(idx):
                        processed_docs.add(chunk_idx)
            
            # 맥락 정보 추가 (이전 대화)
            context_info = ""
            if chat_history:
                relevant_contexts = self._select_relevant_context(question, chat_history)
                if relevant_contexts:
                    context_info = "\n\n이전 대화 맥락:\n"
                    for conv in relevant_contexts:
                        context_info += f"Q: {conv['question']}\nA: {conv['answer']}\n\n"
            
            # OpenAI로 답변 생성
            prompt = f"""다음 문서들을 바탕으로 질문에 답변해주세요.
각 문서의 제목(파일명)을 주의 깊게 살펴보고, 해당 문서와 관련된 내용을 우선적으로 참고해주세요.

**절대 금지사항:**
- 제공된 문서에 없는 조항, 법령, 규정을 언급하지 마세요
- 외부 지식이나 일반적인 법률 지식을 사용하지 마세요
- 시행령, 시행규칙 등 문서에 없는 법령을 언급하지 마세요

중요 지침: 
1. 오직 제공된 문서의 내용만을 사용하여 답변해주세요.
2. "이", "그", "위에서", "앞서", "해당" 등의 참조 표현이 있다면 해당 내용을 찾아 연결해주세요.
3. 단계별 설명이나 순서가 있는 내용은 그 흐름을 유지하여 답변해주세요.
4. 제공된 문서에 질문에 대한 답변이 없다면, 추측하지 말고 "제공된 문서에는 해당 내용이 없습니다"라고 명확히 답변해주세요.
5. 이전 대화에서 언급된 조항이나 규정에 대한 추가 질문인 경우, 이전 답변의 맥락을 참고하여 답변해주세요.
6. "관련 조항", "그것", "해당 내용" 등 맥락 연결 질문의 경우, 이전 대화에서 언급된 주제와 연결하여 답변해주세요.

참고 문서들:{context}{context_info}

질문: {question}

답변:"""
            
            response = openai.ChatCompletion.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "당신은 도움이 되는 AI 어시스턴트입니다. **중요: 오직 제공된 문서의 내용만을 사용하여 답변해주세요.** 외부 지식이나 일반적인 법률 지식을 사용하지 마세요. 사용자가 '전체 내용을 그대로 보여달라'고 요청하면, 해당 조항의 모든 내용을 빠짐없이 완전히 제공해주세요. 각 문서의 제목(파일명)을 주의 깊게 살펴보고, 해당 문서와 관련된 내용을 우선적으로 참고해주세요. 사용자가 '저장하고 있는 문서가 뭐지?', '파일명을 알려달라' 등의 질문을 하면, 참고 문서들에서 파일명(=== 파일명 === 형태)을 찾아서 정확히 알려주세요. **절대로 제공된 문서에 없는 조항, 법령, 규정을 언급하지 마세요.** 문서에 없는 내용은 추측하지 말고, 문서 내용과 이전 대화 맥락만을 바탕으로 답변해주세요. 만약 질문에 대한 답변이 제공된 문서에 없다면, '제공된 문서에는 해당 내용이 없습니다. 더 자세한 정보가 필요하시면 관련 문서를 업로드해주세요.'라고 답변해주세요."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            
            answer = response.choices[0].message.content.strip()
            logger.info(f"✅ 질의응답 완료: {question[:50]}...")
            return answer
            
        except Exception as e:
            logger.error(f"❌ 질의응답 실패: {e}")
            return f"질의응답 중 오류가 발생했습니다: {str(e)}"
    
    def _get_related_chunk_indices(self, chunk_idx: int) -> List[int]:
        """특정 청크와 관련된 모든 청크 인덱스 반환"""
        related_indices = [chunk_idx]
        current_doc = self.documents[chunk_idx]
        filename = current_doc['filename']
        
        # 같은 파일의 모든 청크 찾기
        for i, doc in enumerate(self.documents):
            if doc['filename'] == filename:
                related_indices.append(i)
        
        return related_indices
    
    def _get_connected_chunks(self, chunk_idx: int, display_name: str) -> str:
        """연속된 청크들을 연결해서 반환 (스마트 선택)"""
        current_doc = self.documents[chunk_idx]
        filename = current_doc['filename']
        
        # 같은 파일의 모든 청크들을 chunk_id 순으로 정렬
        same_file_chunks = []
        for i, doc in enumerate(self.documents):
            if doc['filename'] == filename:
                same_file_chunks.append((doc['chunk_id'], i, doc['content']))
        
        # chunk_id 순으로 정렬
        same_file_chunks.sort(key=lambda x: x[0])
        
        # 현재 청크 주변의 청크들을 우선 선택
        current_chunk_id = current_doc['chunk_id']
        selected_chunks = []
        
        # 현재 청크를 중심으로 앞뒤 청크들 선택
        for chunk_id, idx, content in same_file_chunks:
            if abs(chunk_id - current_chunk_id) <= 2:  # 현재 청크 ±2 범위
                selected_chunks.append((chunk_id, idx, content))
        
        # 토큰 제한을 고려하여 최대 3개 청크만 사용
        if len(selected_chunks) > 3:
            selected_chunks = selected_chunks[:3]
        
        # 연속된 청크들을 연결
        connected_content = ""
        for chunk_id, idx, content in selected_chunks:
            connected_content += content + "\n"
        
        logger.info(f"📄 {display_name}: {len(selected_chunks)}개 청크 연결됨 (전체 {len(same_file_chunks)}개 중)")
        return connected_content.strip()
    
    def _handle_filename_question(self, question: str) -> str:
        """파일명 관련 질문 처리"""
        try:
            # 모든 고유한 파일명 수집
            unique_filenames = set()
            for doc in self.documents:
                unique_filenames.add(doc['filename'])
            
            if not unique_filenames:
                return "현재 저장된 문서가 없습니다."
            
            # 파일명 목록 생성
            filename_list = list(unique_filenames)
            filename_list.sort()  # 알파벳 순으로 정렬
            
            if len(filename_list) == 1:
                return f"현재 저장된 문서는 '{filename_list[0]}'입니다."
            else:
                filename_text = "\n".join([f"- {filename}" for filename in filename_list])
                return f"현재 저장된 문서는 총 {len(filename_list)}개입니다:\n\n{filename_text}"
                
        except Exception as e:
            logger.error(f"❌ 파일명 질문 처리 실패: {e}")
            return "파일명 정보를 가져오는 중 오류가 발생했습니다."
    
    def remove_document(self, filename: str) -> bool:
        """문서 제거"""
        try:
            # 해당 파일의 모든 청크 제거
            indices_to_remove = []
            for i, doc in enumerate(self.documents):
                if doc['filename'] == filename:
                    indices_to_remove.append(i)
            
            # 역순으로 제거 (인덱스 변화 방지)
            for i in reversed(indices_to_remove):
                del self.documents[i]
                del self.embeddings[i]
            
            # 벡터 저장소 업데이트
            self.vector_store = {}
            for i, doc in enumerate(self.documents):
                self.vector_store[f"{doc['filename']}_{doc['chunk_id']}"] = self.embeddings[i]
            
            # 저장
            self._save_vector_store()
            
            logger.info(f"✅ 문서 제거 완료: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 문서 제거 실패: {filename} - {e}")
            return False
    
    def rebuild_index(self) -> bool:
        """인덱스 재구성"""
        try:
            # 기존 문서들로 인덱스 재구성
            old_documents = self.documents.copy()
            old_embeddings = self.embeddings.copy()
            
            self.documents = []
            self.embeddings = []
            self.vector_store = {}
            
            for doc in old_documents:
                embedding = self._get_embedding(doc['content'])
                if embedding:
                    self.documents.append(doc)
                    self.embeddings.append(embedding)
                    self.vector_store[f"{doc['filename']}_{doc['chunk_id']}"] = embedding
            
            # 저장
            self._save_vector_store()
            
            logger.info("✅ 인덱스 재구성 완료")
            return True
            
        except Exception as e:
            logger.error(f"❌ 인덱스 재구성 실패: {e}")
            return False
    
    def clear_index(self) -> bool:
        """인덱스 초기화"""
        try:
            self.documents = []
            self.embeddings = []
            self.vector_store = {}
            
            # 저장
            self._save_vector_store()
            
            # 스토리지의 모든 파일 임베딩 상태를 False로 변경
            if self.storage:
                files = self.storage.list_files()
                for file_info in files:
                    self.storage.mark_embedding_status(file_info['filename'], False)
            
            logger.info("✅ 인덱스 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"❌ 인덱스 초기화 실패: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """RAG 시스템 상태 반환"""
        return {
            'total_documents': len(self.documents),
            'total_embeddings': len(self.embeddings),
            'embedding_model': self.embedding_model,
            'llm_model': self.llm_model,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'is_initialized': self.openai_api_key is not None
        }
    
    def get_vector_db_info(self) -> Dict[str, Any]:
        """벡터 DB 상세 정보 반환"""
        if not self.embeddings:
            return {
                'total_vectors': 0,
                'dimensions': 0,
                'db_size_mb': 0,
                'index_type': 'empty'
            }
        
        # 첫 번째 임베딩의 차원 수 확인
        dimensions = len(self.embeddings[0]) if self.embeddings else 0
        
        # 벡터 저장소 파일 크기
        db_size = 0
        if self.storage:
            vector_file = os.path.join(self.storage.local_dir, "vector_store.pkl")
            if os.path.exists(vector_file):
                db_size = os.path.getsize(vector_file)
        
        return {
            'total_vectors': len(self.embeddings),
            'dimensions': dimensions,
            'db_size_mb': round(db_size / (1024**2), 2),
            'index_type': 'pickle',
            'storage_path': self.storage.local_dir if self.storage else 'unknown'
        }
    
    def search_test(self, query: str) -> Dict[str, Any]:
        """검색 테스트 실행"""
        try:
            if not self.embeddings:
                return {
                    'query': query,
                    'results': [],
                    'message': '임베딩이 없습니다.'
                }
            
            # 쿼리 임베딩 생성
            query_embedding = self._get_embedding(query)
            if not query_embedding:
                return {
                    'query': query,
                    'results': [],
                    'message': '쿼리 임베딩 생성에 실패했습니다.'
                }
            
            # 유사도 계산
            similarities = []
            for i, embedding in enumerate(self.embeddings):
                similarity = self._cosine_similarity(query_embedding, embedding)
                similarities.append({
                    'index': i,
                    'similarity': similarity,
                    'document': self.documents[i] if i < len(self.documents) else 'Unknown'
                })
            
            # 유사도 순으로 정렬
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            
            return {
                'query': query,
                'results': similarities[:5],  # 상위 5개 결과
                'total_results': len(similarities),
                'message': '검색 테스트가 완료되었습니다.'
            }
            
        except Exception as e:
            logger.error(f"검색 테스트 실패: {e}")
            return {
                'query': query,
                'results': [],
                'message': f'검색 테스트 실패: {str(e)}'
            }
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """코사인 유사도 계산"""
        try:
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
            
        except Exception as e:
            logger.error(f"코사인 유사도 계산 실패: {e}")
            return 0.0
    
    def _extract_keywords(self, text: str) -> List[str]:
        """텍스트에서 키워드 추출 (개선)"""
        # 한국어 불용어 제거
        stopwords = ['은', '는', '이', '가', '을', '를', '에', '의', '로', '으로', '에서', '에게', '와', '과', '도', '만', '부터', '까지', '한', '두', '세', '네', '다섯', '여섯', '일곱', '여덟', '아홉', '열']
        
        # 간단한 키워드 추출 (공백으로 분리)
        words = text.split()
        keywords = []
        
        for word in words:
            # 불용어 제거 및 길이 체크
            if word not in stopwords and len(word) > 1:
                keywords.append(word)
        
        # 조항 관련 키워드 추가
        if any(keyword in text for keyword in ['조', '항', '호', '목']):
            keywords.extend(['조항', '법조문', '규정'])
        
        return keywords
    
    def _extract_article_info(self, answer_text: str) -> List[str]:
        """답변에서 조항 정보 추출"""
        import re
        
        # 조항 패턴 감지
        patterns = [
            r'제\d+조',
            r'제\d+항',
            r'제\d+호',
            r'제\d+목',
            r'\d+조',
            r'\d+항',
            r'\d+호',
            r'\d+목'
        ]
        
        article_info = []
        for pattern in patterns:
            matches = re.findall(pattern, answer_text)
            article_info.extend(matches)
        
        return article_info
    
    def _select_relevant_context(self, current_question: str, chat_history: list, max_contexts: int = 3) -> list:
        """개선된 맥락 선택 (조항 정보 인식)"""
        try:
            if not chat_history:
                return []
            # 최근 50개 대화만 검색 (성능 최적화)
            recent_history = chat_history[-50:] if len(chat_history) > 50 else chat_history
            
            if not recent_history:
                return []
            
            # 현재 질문의 키워드 추출
            current_keywords = set(self._extract_keywords(current_question))
            
            # 맥락 연결 질문인지 확인 (관련, 조항, 내용 등)
            context_connection_keywords = ['관련', '조항', '내용', '그것', '이것', '해당', '위에서', '앞서']
            is_context_question = any(keyword in current_question for keyword in context_connection_keywords)
            
            # 키워드가 부족하거나 맥락 연결 질문인 경우 최근 대화를 우선 선택
            if not current_keywords or len(current_keywords) < 2 or is_context_question:
                logger.info(f"🔍 맥락 연결 질문 또는 키워드 부족, 최근 대화 우선 선택: {current_keywords}, 맥락질문: {is_context_question}")
                return recent_history[-1:] if recent_history else []
            
            # 조항 관련 질문인지 확인 (더 포괄적으로)
            is_article_question = any(keyword in current_question for keyword in ['조', '항', '호', '목', '몇', '조항', '규정', '내용'])
            
            scored_contexts = []
            
            # 각 대화와 키워드 유사도 계산
            for conv in recent_history:
                conv_text = conv['question'] + ' ' + conv['answer']
                conv_keywords = set(self._extract_keywords(conv_text))
                
                # 기본 키워드 유사도
                overlap = len(current_keywords & conv_keywords)
                
                # 조항 관련 질문인 경우 이전 답변에서 조항 정보 추출
                if is_article_question:
                    article_info = self._extract_article_info(conv['answer'])
                    if article_info:
                        # 조항 정보가 있으면 높은 점수 부여
                        overlap += len(article_info) * 2
                
                if overlap > 0:
                    # 유사도 점수 = 겹치는 키워드 수 / 현재 질문 키워드 수
                    similarity_score = overlap / len(current_keywords) if current_keywords else 0
                    scored_contexts.append((similarity_score, conv))
            
            # 유사도 순으로 정렬하고 상위 N개 선택
            scored_contexts.sort(reverse=True)
            selected_contexts = [conv for _, conv in scored_contexts[:max_contexts]]
            
            logger.info(f"✅ 맥락 선택 완료: {len(selected_contexts)}개 대화 선택 (조항 질문: {is_article_question}, 총 히스토리: {len(chat_history)}개)")
            return selected_contexts
            
        except Exception as e:
            logger.error(f"❌ 맥락 선택 실패: {e}")
            return []
    
    def backup_vectors(self, backup_path: str) -> bool:
        """벡터 저장소 백업"""
        try:
            backup_data = {
                'documents': self.documents,
                'embeddings': self.embeddings,
                'vector_store': self.vector_store,
                'backup_timestamp': datetime.now().isoformat()
            }
            
            with open(backup_path, 'wb') as f:
                pickle.dump(backup_data, f)
            
            logger.info(f"✅ 벡터 저장소 백업 완료: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 벡터 저장소 백업 실패: {e}")
            return False
    
    def restore_vectors(self, backup_path: str) -> bool:
        """벡터 저장소 복원"""
        try:
            with open(backup_path, 'rb') as f:
                backup_data = pickle.load(f)
            
            self.documents = backup_data.get('documents', [])
            self.embeddings = backup_data.get('embeddings', [])
            self.vector_store = backup_data.get('vector_store', {})
            
            # 벡터 저장소 저장
            self._save_vector_store()
            
            logger.info(f"✅ 벡터 저장소 복원 완료: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 벡터 저장소 복원 실패: {e}")
            return False
    
    def update_settings(self, settings: Dict[str, Any]) -> bool:
        """시스템 설정 업데이트"""
        try:
            if 'chunk_size' in settings:
                self.chunk_size = settings['chunk_size']
            if 'chunk_overlap' in settings:
                self.chunk_overlap = settings['chunk_overlap']
            if 'embedding_model' in settings:
                self.embedding_model = settings['embedding_model']
            if 'llm_model' in settings:
                self.llm_model = settings['llm_model']
            
            logger.info("✅ RAG 시스템 설정이 업데이트되었습니다.")
            return True
            
        except Exception as e:
            logger.error(f"❌ 설정 업데이트 실패: {e}")
            return False
    
    def get_settings(self) -> Dict[str, Any]:
        """현재 시스템 설정 반환"""
        return {
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'embedding_model': self.embedding_model,
            'llm_model': self.llm_model,
            'openai_api_key_configured': self.openai_api_key is not None
        }
