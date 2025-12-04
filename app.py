from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
import json
import sys
import io
from contextlib import redirect_stdout
import os

from CSPxGA import generate_schedule_from_data

app = Flask(__name__, static_folder='public', static_url_path='')
CORS(app)

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/generate-schedule', methods=['POST'])
def generate_schedule():

    @stream_with_context
    def generate():
        try:
            json_data = request.get_json()
            
            if not json_data:
                yield json.dumps({"error": "No JSON data received"}) + "\n"
                return

            output_buffer = io.StringIO()

            class ProgressWriter:
                def __init__(self):
                    self.buffer = []
                
                def write(self, text):
                    if text.strip():
                        self.buffer.append(f"[PROGRESS] {text.strip()}\n")
                
                def flush(self):
                    pass
                
                def get_messages(self):
                    messages = self.buffer.copy()
                    self.buffer.clear()
                    return messages
            
            progress_writer = ProgressWriter()
 
            old_stdout = sys.stdout
            sys.stdout = progress_writer
            
            try:
                sys.stdout = old_stdout
                yield "[PROGRESS] Starting schedule generation...\n"
                sys.stdout = progress_writer

                result = generate_schedule_from_data(json_data)

                sys.stdout = old_stdout

                for msg in progress_writer.get_messages():
                    yield msg

                if result:
                    yield json.dumps(result) + "\n"
                else:
                    yield json.dumps({"error": "No result generated"}) + "\n"
                
            except Exception as e:
                sys.stdout = old_stdout
                import traceback
                error_detail = traceback.format_exc()
                print(f"ERROR: {error_detail}")
                yield json.dumps({"error": str(e), "details": error_detail}) + "\n"
            
        except Exception as e:
            yield json.dumps({"error": f"Generation failed: {str(e)}"}) + "\n"
    
    return Response(generate(), mimetype='text/plain')

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Schedule Generator API is running (Flask + Python)"})

if __name__ == '__main__':
    print("=" * 60)
    print("Flask Server Starting...")
    print("Server running on: http://localhost:3000")
    print("Send POST requests to: http://localhost:3000/generate-schedule")
    print("=" * 60)
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)
