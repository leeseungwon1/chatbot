// 관리자 페이지 JavaScript
function deleteFile(filename) {
    if (confirm(`파일 "${filename}"을 삭제하시겠습니까?`)) {
        fetch(`/api/files/${filename}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                alert(data.message);
                location.reload();
            } else {
                alert('파일 삭제 실패: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('파일 삭제 중 오류가 발생했습니다.');
        });
    }
}

function deleteAllFiles() {
    if (confirm('모든 파일을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) {
        fetch('/api/admin/delete-all', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                alert(data.message);
                location.reload();
            } else {
                alert('전체 파일 삭제 실패: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('전체 파일 삭제 중 오류가 발생했습니다.');
        });
    }
}

function rebuildIndex() {
    if (confirm('전체 임베딩을 재구성하시겠습니까? 시간이 오래 걸릴 수 있습니다.')) {
        fetch('/api/admin/rebuild', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                alert(data.message);
                location.reload();
            } else {
                alert('인덱스 재구성 실패: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('인덱스 재구성 중 오류가 발생했습니다.');
        });
    }
}

function updateEmbeddings() {
    if (confirm('새로 업로드된 파일들의 임베딩을 추가하시겠습니까?')) {
        fetch('/api/admin/update-embeddings', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                alert(data.message);
                location.reload();
            } else {
                alert('임베딩 업데이트 실패: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('임베딩 업데이트 중 오류가 발생했습니다.');
        });
    }
}

function clearIndex() {
    if (confirm('모든 임베딩을 초기화하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) {
        fetch('/api/admin/clear-index', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                alert(data.message);
                location.reload();
            } else {
                alert('임베딩 초기화 실패: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('임베딩 초기화 중 오류가 발생했습니다.');
        });
    }
}

function refreshStatus() {
    location.reload();
}

// 사용자 페이지 JavaScript
function loadFileList() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            if (data.storage && data.storage.files) {
                displayFileList(data.storage.files);
            }
        })
        .catch(error => {
            console.error('Error loading file list:', error);
        });
}

function displayFileList(files) {
    const fileListDiv = document.getElementById('files-list');
    if (!fileListDiv) return;
    
    if (files.length === 0) {
        fileListDiv.innerHTML = '<p class="text-muted">업로드된 파일이 없습니다.</p>';
        return;
    }
    
    let html = '';
    files.forEach(file => {
        const icon = getFileIcon(file.name);
        const size = formatFileSize(file.size);
        const date = formatDate(file.updated);
        
        html += `
            <div class="file-item">
                <div class="file-icon">${icon}</div>
                <div class="file-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-details">
                        <span class="file-size">${size}</span>
                        <span class="file-date">${date}</span>
                    </div>
                </div>
            </div>
        `;
    });
    
    fileListDiv.innerHTML = html;
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    switch (ext) {
        case 'pdf': return '📄';
        case 'docx': case 'doc': return '📝';
        case 'txt': return '📃';
        case 'md': return '📖';
        default: return '📁';
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ko-KR');
}

function refreshFileList() {
    loadFileList();
}

function checkSystemStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            const statusDot = document.getElementById('statusDot');
            const statusText = document.getElementById('statusText');
            
            if (statusDot && statusText) {
                if (data.rag_system && data.rag_system.vector_store_initialized) {
                    statusDot.className = 'status-dot online';
                    statusText.textContent = '✅ 시스템 준비됨';
                } else if (data.rag_system && data.rag_system.openai_initialized) {
                    statusDot.className = 'status-dot warning';
                    statusText.textContent = '⚠️ 문서 업로드 필요';
                } else {
                    statusDot.className = 'status-dot offline';
                    statusText.textContent = '❌ 시스템 오프라인';
                }
            }
        })
        .catch(error => {
            console.error('Error checking system status:', error);
        });
}

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', function() {
    // 파일 목록 로드
    if (document.getElementById('files-list')) {
        loadFileList();
    }
});
