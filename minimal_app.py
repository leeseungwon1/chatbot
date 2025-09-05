#!/usr/bin/env python3
"""
Cloud Run 배포를 위한 최소한의 Flask 애플리케이션
"""
import os
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# 기본 HTML 템플릿
BASE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Army Chatbot</title>
    <meta charset="utf-8">
</head>
<body>
    <h1>Army Chatbot</h1>
    <p>서비스가 정상적으로 실행 중입니다.</p>
    <p>환경: {{ environment }}</p>
    <p>포트: {{ port }}</p>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(BASE_TEMPLATE, 
                                environment=os.environ.get('ENVIRONMENT', 'unknown'),
                                port=os.environ.get('PORT', 'unknown'))

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'message': 'Service is running',
        'environment': os.environ.get('ENVIRONMENT', 'unknown'),
        'port': os.environ.get('PORT', 'unknown')
    })

@app.route('/api/status')
def status():
    return jsonify({
        'status': 'ok',
        'message': 'Minimal app is running',
        'environment': os.environ.get('ENVIRONMENT', 'unknown')
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting minimal server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
