#!/usr/bin/env python3
"""
Cloud Run 배포를 위한 간단한 테스트 애플리케이션
"""
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def hello():
    return jsonify({
        'message': 'Hello from Cloud Run!',
        'status': 'success',
        'port': os.environ.get('PORT', 'not set')
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
