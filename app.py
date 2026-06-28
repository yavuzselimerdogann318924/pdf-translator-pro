#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════╗
║                   PDF TRANSLATOR PRO — Web Server                 ║
║  Flask + Socket.IO backend with real-time translation progress    ║
║                                                                   ║
║  Signed by Yavuz Selim Erdoğan                                    ║
╚═══════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import uuid
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO

from pdf_translator import PDFTranslator

# ── App Setup ──
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
TRANSLATION_DIR = BASE_DIR / "translations"
HISTORY_FILE = BASE_DIR / ".translation_history.json"

UPLOAD_DIR.mkdir(exist_ok=True)
TRANSLATION_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pdf-translator-pro-secret'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB max

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ── Active Tasks ──
active_tasks = {}  # task_id -> { thread, translator, ... }


# ── Routes ──

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload a PDF file and return page count."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Dosya bulunamadı'}), 400

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'error': 'Geçerli bir PDF dosyası yükleyin'}), 400

    # Save file with unique name to avoid collisions
    safe_name = file.filename
    filepath = UPLOAD_DIR / safe_name

    # If file exists, add suffix
    counter = 1
    while filepath.exists():
        name, ext = os.path.splitext(safe_name)
        filepath = UPLOAD_DIR / f"{name}_{counter}{ext}"
        counter += 1

    file.save(str(filepath))

    # Get page count
    pages = PDFTranslator.get_page_count(str(filepath))
    if pages == 0:
        filepath.unlink(missing_ok=True)
        return jsonify({'success': False, 'error': 'PDF dosyası okunamadı'}), 400

    return jsonify({
        'success': True,
        'filename': filepath.name,
        'pages': pages,
        'size_mb': round(filepath.stat().st_size / (1024 * 1024), 1),
    })


@app.route('/api/translate', methods=['POST'])
def start_translation():
    """Start a translation task in the background."""
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({'success': False, 'error': 'Dosya adı belirtilmedi'}), 400

    filename = data['filename']
    filepath = UPLOAD_DIR / filename

    if not filepath.exists():
        return jsonify({'success': False, 'error': 'Dosya bulunamadı'}), 404

    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'tr')
    workers = min(int(data.get('workers', 4)), 16)
    chunk_size = int(data.get('chunk_size', 4000))
    save_every = int(data.get('save_every', 50))
    start_page = int(data.get('start_page', 0))
    end_page = data.get('end_page')
    if end_page is not None:
        end_page = int(end_page)

    # Output path
    name, ext = os.path.splitext(filename)
    output_name = f"{name}_{target_lang.upper()}{ext}"
    output_path = TRANSLATION_DIR / output_name

    # Cache path
    cache_path = str(BASE_DIR / f".{name}_translation_cache.json")

    task_id = str(uuid.uuid4())[:8]

    # Create translator
    translator = PDFTranslator(
        source_lang=source_lang,
        target_lang=target_lang,
        cache_path=cache_path,
        workers=workers,
        chunk_size=chunk_size,
    )

    def progress_callback(current_page, total_pages, progress, stats, eta, lexical_words=None):
        socketio.emit('translation_progress', {
            'task_id': task_id,
            'current_page': current_page,
            'total_pages': total_pages,
            'progress': round(progress, 1),
            'stats': stats,
            'eta': eta or '—',
        })
        if lexical_words:
            socketio.emit('lexical_chunk', {'words': lexical_words})

    def run_translation():
        try:
            start_time = time.time()
            success = translator.translate_pdf(
                input_path=str(filepath),
                output_path=str(output_path),
                start_page=start_page,
                end_page=end_page,
                save_every=save_every,
                on_progress=progress_callback,
            )

            elapsed = time.time() - start_time

            if success:
                # Add to history
                add_to_history({
                    'original_name': filename,
                    'output_file': output_name,
                    'source': source_lang,
                    'target': target_lang,
                    'pages': PDFTranslator.get_page_count(str(filepath)),
                    'status': 'completed',
                    'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                    'elapsed': f"{int(elapsed)}sn",
                    'stats': translator.translation_manager.stats,
                })

                socketio.emit('translation_complete', {
                    'task_id': task_id,
                    'output_file': output_name,
                    'original_name': filename,
                    'stats': translator.translation_manager.stats,
                    'elapsed': f"{int(elapsed)}sn",
                })
            else:
                socketio.emit('translation_error', {
                    'task_id': task_id,
                    'error': 'Çeviri iptal edildi veya başarısız oldu',
                })
        except Exception as e:
            socketio.emit('translation_error', {
                'task_id': task_id,
                'error': str(e),
            })
        finally:
            active_tasks.pop(task_id, None)

    thread = threading.Thread(target=run_translation, daemon=True)
    active_tasks[task_id] = {
        'thread': thread,
        'translator': translator,
        'filename': filename,
        'start_time': time.time(),
    }
    thread.start()

    return jsonify({
        'success': True,
        'task_id': task_id,
        'output_file': output_name,
    })


@app.route('/api/cancel', methods=['POST'])
def cancel_translation():
    """Cancel an active translation task."""
    data = request.get_json()
    task_id = data.get('task_id')

    if task_id and task_id in active_tasks:
        translator = active_tasks[task_id]['translator']
        translator.cancel()
        return jsonify({'success': True, 'message': 'Çeviri iptal ediliyor...'})

    return jsonify({'success': False, 'error': 'Görev bulunamadı'}), 404


@app.route('/api/preview/<filename>/<int:page>')
def preview_page(filename, page):
    """Render a PDF page as PNG image."""
    # Check in uploads first, then translations
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        filepath = TRANSLATION_DIR / filename
    if not filepath.exists():
        # Also check base directory for existing files
        filepath = BASE_DIR / filename
    if not filepath.exists():
        return jsonify({'error': 'Dosya bulunamadı'}), 404

    img_bytes = PDFTranslator.render_page_image(str(filepath), page, dpi=150)
    if not img_bytes:
        return jsonify({'error': 'Sayfa oluşturulamadı'}), 500

    from io import BytesIO
    return send_file(
        BytesIO(img_bytes),
        mimetype='image/png',
        download_name=f'{filename}_page_{page}.png',
    )


@app.route('/api/download/<filename>')
def download_file(filename):
    """Download a translated PDF."""
    filepath = TRANSLATION_DIR / filename
    if not filepath.exists():
        return jsonify({'error': 'Dosya bulunamadı'}), 404

    return send_file(
        str(filepath),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


@app.route('/api/history')
def get_history():
    """Get translation history."""
    history = load_history()
    return jsonify({'history': history})


@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    """Clear all translation caches."""
    count = 0
    for f in BASE_DIR.glob(".*_translation_cache.json"):
        try:
            f.unlink()
            count += 1
        except Exception:
            pass
    return jsonify({
        'success': True,
        'message': f'{count} önbellek dosyası temizlendi',
    })


@app.route('/api/languages')
def get_languages():
    """Get supported language list."""
    languages = {
        'auto': 'Otomatik Algıla',
        'en': 'İngilizce', 'de': 'Almanca', 'fr': 'Fransızca',
        'es': 'İspanyolca', 'it': 'İtalyanca', 'pt': 'Portekizce',
        'ru': 'Rusça', 'zh-CN': 'Çince', 'ja': 'Japonca',
        'ko': 'Korece', 'ar': 'Arapça', 'nl': 'Hollandaca',
        'pl': 'Lehçe', 'sv': 'İsveççe', 'da': 'Danca',
        'fi': 'Fince', 'el': 'Yunanca', 'cs': 'Çekçe',
        'ro': 'Romence', 'hu': 'Macarca', 'uk': 'Ukraynaca',
        'hi': 'Hintçe', 'tr': 'Türkçe',
    }
    return jsonify(languages)


# ── History Helpers ──

def load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def add_to_history(entry):
    history = load_history()
    history.insert(0, entry)
    # Keep last 50 entries
    history = history[:50]
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── Socket Events ──

@socketio.on('connect')
def handle_connect():
    print(f"  🔌 Client bağlandı")


@socketio.on('disconnect')
def handle_disconnect():
    print(f"  🔌 Client ayrıldı")


# ── Main ──

if __name__ == '__main__':
    import os as _os
    _port = int(_os.environ.get('PORT', 8080))
    print(f"\n{'═' * 60}")
    print(f"  🌐 PDF TRANSLATOR PRO — Web Server")
    print(f"  📁 Upload Dir:  {UPLOAD_DIR}")
    print(f"  📁 Output Dir:  {TRANSLATION_DIR}")
    print(f"{'═' * 60}")
    print(f"  🚀 http://localhost:{_port} adresinde başlatılıyor...\n")

    socketio.run(
        app,
        host='0.0.0.0',
        port=_port,
        debug=False,
        allow_unsafe_werkzeug=True,
    )
