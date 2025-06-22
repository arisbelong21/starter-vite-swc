
from flask import Flask, request, jsonify, render_template
import requests
import os
import json
import logging
from datetime import datetime
import traceback

app = Flask(__name__)

# Telegram configuration
TELEGRAM_BOT_TOKEN = "8072214808:AAGgTqvQ3Sh64oc2zn6oDZ06kd1xegZFb3g"
TELEGRAM_CHAT_ID = "7152303949"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def send_telegram_message(message):
    """Send message to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram notification sent successfully")
        else:
            logger.error(f"Failed to send Telegram message: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

def load_session_cookies(session_file_path):
    """Load cookies from session file"""
    try:
        if not os.path.exists(session_file_path):
            logger.error(f"Session file not found: {session_file_path}")
            return None
        
        with open(session_file_path, 'r') as f:
            session_data = json.load(f)
        
        # Extract cookies from session data
        cookies = {}
        if 'cookies' in session_data:
            for cookie in session_data['cookies']:
                cookies[cookie['name']] = cookie['value']
        elif isinstance(session_data, dict):
            # If session data is directly cookies
            cookies = session_data
        
        logger.info(f"Loaded {len(cookies)} cookies from session")
        return cookies
    except Exception as e:
        logger.error(f"Error loading session cookies: {e}")
        return None

def upload_image_to_threads(image_path, cookies):
    """Upload image to Threads and return media ID"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'X-Instagram-AJAX': '1',
            'X-CSRFToken': cookies.get('csrftoken', ''),
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        with open(image_path, 'rb') as img_file:
            files = {
                'image': ('image.jpg', img_file, 'image/jpeg')
            }
            
            upload_url = 'https://www.threads.net/api/v1/media/upload_photo/'
            response = requests.post(
                upload_url,
                headers=headers,
                cookies=cookies,
                files=files,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'media_id' in result:
                    return result['media_id']
                    
        return None
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        return None

def post_to_threads(akun, caption, image_path=None):
    """Post to Threads using session cookies"""
    try:
        session_file = f"sessions/{akun}.session"
        cookies = load_session_cookies(session_file)
        
        if not cookies:
            return False, "Session file tidak ditemukan atau rusak"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Instagram-AJAX': '1',
            'X-CSRFToken': cookies.get('csrftoken', ''),
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://www.threads.net/'
        }
        
        # Prepare post data
        post_data = {
            'text': caption,
            'publish_mode': 'text_post'
        }
        
        # Handle image upload if provided
        media_id = None
        if image_path and os.path.exists(image_path):
            logger.info(f"Uploading image: {image_path}")
            media_id = upload_image_to_threads(image_path, cookies)
            if media_id:
                post_data['media_id'] = media_id
                post_data['publish_mode'] = 'media_post'
                logger.info(f"Image uploaded with media_id: {media_id}")
            else:
                logger.warning("Failed to upload image, posting text only")
        
        # Make the request to Threads
        post_url = 'https://www.threads.net/api/v1/media/configure_text_post/'
        if media_id:
            post_url = 'https://www.threads.net/api/v1/media/configure_photo/'
        
        response = requests.post(
            post_url,
            headers=headers,
            cookies=cookies,
            data=post_data,
            timeout=30
        )
        
        logger.info(f"Threads API response: {response.status_code}")
        logger.info(f"Response content: {response.text[:200]}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                if result.get('status') == 'ok' or 'media' in result:
                    return True, "Post berhasil dipublikasikan"
                else:
                    return False, f"Threads API error: {result.get('message', 'Unknown error')}"
            except json.JSONDecodeError:
                # Sometimes Threads returns HTML instead of JSON
                if 'threads.net' in response.text:
                    return True, "Post berhasil dipublikasikan"
                else:
                    return False, "Response format tidak valid"
        else:
            return False, f"HTTP error: {response.status_code} - {response.text[:100]}"
            
    except requests.exceptions.Timeout:
        return False, "Request timeout"
    except requests.exceptions.ConnectionError:
        return False, "Connection error"
    except Exception as e:
        logger.error(f"Error posting to Threads: {traceback.format_exc()}")
        return False, f"Internal error: {str(e)}"

@app.route('/post', methods=['POST'])
def post_endpoint():
    """Main endpoint for posting to Threads"""
    start_time = datetime.now()
    
    try:
        # Get JSON data
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No JSON data provided'
            }), 400
        
        akun = data.get('akun', '').strip()
        caption = data.get('caption', '').strip()
        kode = data.get('kode', '').strip()
        
        # Validate required fields
        if not akun:
            return jsonify({
                'success': False,
                'message': 'Field akun diperlukan'
            }), 400
        
        if not caption:
            return jsonify({
                'success': False,
                'message': 'Field caption diperlukan'
            }), 400
        
        logger.info(f"Posting request - Akun: {akun}, Caption length: {len(caption)}, Image: {kode or 'None'}")
        
        # Check session file exists
        session_file_path = f"sessions/{akun}.session"
        if not os.path.exists(session_file_path):
            error_msg = f"Session file tidak ditemukan untuk akun {akun}"
            logger.error(error_msg)
            return jsonify({
                'success': False,
                'message': error_msg
            }), 404
        
        # Check image file if provided
        image_path = None
        if kode:
            image_path = f"uploads/{kode}"
            if not os.path.exists(image_path):
                error_msg = f"File gambar {kode} tidak ditemukan"
                logger.warning(error_msg)
                # Don't return error, just continue without image
                image_path = None
        
        # Send notification to Telegram about attempt
        telegram_message = f"🤖 <b>Threads Post Attempt</b>\n\n"
        telegram_message += f"⏰ Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        telegram_message += f"👤 Account: {akun}\n"
        telegram_message += f"📝 Caption: {caption[:100]}{'...' if len(caption) > 100 else ''}\n"
        telegram_message += f"📸 Image: {kode or 'None'}\n"
        telegram_message += f"🔄 Status: <b>PROCESSING...</b>"
        
        send_telegram_message(telegram_message)
        
        # Attempt to post to Threads
        success, message = post_to_threads(akun, caption, image_path)
        
        # Calculate processing time
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # Log result
        if success:
            logger.info(f"Post successful - Akun: {akun}, Time: {processing_time:.2f}s")
        else:
            logger.error(f"Post failed - Akun: {akun}, Error: {message}, Time: {processing_time:.2f}s")
        
        # Send final notification to Telegram
        final_telegram_message = f"🤖 <b>Threads Post Result</b>\n\n"
        final_telegram_message += f"⏰ Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        final_telegram_message += f"👤 Account: {akun}\n"
        final_telegram_message += f"📝 Caption: {caption[:100]}{'...' if len(caption) > 100 else ''}\n"
        final_telegram_message += f"📸 Image: {kode or 'None'}\n"
        final_telegram_message += f"⚡ Processing: {processing_time:.2f}s\n"
        
        if success:
            final_telegram_message += f"✅ Status: <b>SUCCESS</b>\n"
            final_telegram_message += f"📊 Result: {message}"
        else:
            final_telegram_message += f"❌ Status: <b>FAILED</b>\n"
            final_telegram_message += f"❗ Error: {message}"
        
        send_telegram_message(final_telegram_message)
        
        return jsonify({
            'success': success,
            'message': message,
            'processing_time': f"{processing_time:.2f}s"
        }), 200 if success else 500
        
    except Exception as e:
        error_msg = f"Internal server error: {str(e)}"
        logger.error(f"Unexpected error: {traceback.format_exc()}")
        
        # Send error notification to Telegram
        error_telegram_message = f"🚨 <b>Bot Error</b>\n\n"
        error_telegram_message += f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        error_telegram_message += f"❌ Error: <b>INTERNAL ERROR</b>\n"
        error_telegram_message += f"📊 Details: {str(e)[:200]}{'...' if len(str(e)) > 200 else ''}"
        
        send_telegram_message(error_telegram_message)
        
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/')
def index():
    """Main web interface"""
    try:
        # Get available accounts
        sessions_dir = "sessions"
        if not os.path.exists(sessions_dir):
            os.makedirs(sessions_dir, exist_ok=True)
        
        session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.session')]
        accounts = []
        
        for session_file in session_files:
            username = session_file.replace('.session', '')
            session_path = os.path.join(sessions_dir, session_file)
            
            # Check if session is valid (basic check)
            status = 'aktif'
            try:
                with open(session_path, 'r') as f:
                    session_data = json.load(f)
                    if not session_data or len(session_data) == 0:
                        status = 'mati'
            except:
                status = 'mati'
            
            accounts.append({
                'username': username,
                'session_path': session_path,
                'status': status
            })
        
        return render_template('index.html', accounts=accounts)
    except Exception as e:
        logger.error(f"Error loading index page: {e}")
        return f"Error loading page: {str(e)}", 500

@app.route('/admin')
def admin():
    """Admin panel"""
    return render_template('admin.html')

@app.route('/get_accounts', methods=['GET'])
def get_accounts():
    """Get available accounts"""
    try:
        sessions_dir = "sessions"
        if not os.path.exists(sessions_dir):
            os.makedirs(sessions_dir, exist_ok=True)
        
        session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.session')]
        accounts = []
        
        for session_file in session_files:
            username = session_file.replace('.session', '')
            session_path = os.path.join(sessions_dir, session_file)
            
            # Check if session is valid
            status = 'aktif'
            try:
                with open(session_path, 'r') as f:
                    session_data = json.load(f)
                    if not session_data or len(session_data) == 0:
                        status = 'mati'
            except:
                status = 'mati'
            
            accounts.append({
                'username': username,
                'session_path': session_path,
                'status': status
            })
        
        return jsonify(accounts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload_image', methods=['POST'])
def upload_image():
    """Upload image for posting"""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Generate unique filename
        import uuid
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        
        # Save file
        uploads_dir = "uploads"
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, unique_filename)
        file.save(file_path)
        
        return jsonify({
            'success': True,
            'filename': unique_filename,
            'original_name': file.filename
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    try:
        from flask import send_from_directory
        return send_from_directory('uploads', filename)
    except Exception as e:
        return str(e), 404

@app.route('/post_to_threads', methods=['POST'])
def post_to_threads_web():
    """Web interface for posting to threads"""
    try:
        data = request.get_json()
        akun = data.get('akun', '').strip()
        caption = data.get('caption', '').strip()
        kode = data.get('kode', '').strip()
        
        # Extract username from session path
        if '/' in akun:
            username = os.path.basename(akun).replace('.session', '')
        else:
            username = akun
        
        # Use existing post_to_threads function
        image_path = None
        if kode:
            image_path = f"uploads/{kode}"
            if not os.path.exists(image_path):
                image_path = None
        
        success, message = post_to_threads(username, caption, image_path)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/add_account', methods=['POST'])
def add_account():
    """Add new account manually"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        sessionid = data.get('sessionid', '').strip()
        csrftoken = data.get('csrftoken', '').strip()
        ds_user_id = data.get('ds_user_id', '').strip()
        datr = data.get('datr', '').strip()
        
        if not username:
            return jsonify({
                'success': False,
                'message': 'Username tidak boleh kosong'
            }), 400
            
        if not sessionid:
            return jsonify({
                'success': False,
                'message': 'Session ID wajib diisi'
            }), 400
        
        # Create sessions directory if not exists
        os.makedirs('sessions', exist_ok=True)
        
        # Check if account already exists
        session_file = f"sessions/{username}.session"
        if os.path.exists(session_file):
            return jsonify({
                'success': False,
                'message': f'Akun {username} sudah ada'
            }), 400
        
        # Create session data
        cookies = {
            'sessionid': sessionid
        }
        
        if csrftoken:
            cookies['csrftoken'] = csrftoken
        if ds_user_id:
            cookies['ds_user_id'] = ds_user_id
        if datr:
            cookies['datr'] = datr
        
        # Save session file
        with open(session_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        
        logger.info(f"New account added: {username}")
        
        # Send notification to Telegram
        telegram_message = f"✅ <b>Akun Baru Ditambahkan</b>\n\n"
        telegram_message += f"👤 Username: {username}\n"
        telegram_message += f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        telegram_message += f"📁 File: {session_file}"
        
        send_telegram_message(telegram_message)
        
        return jsonify({
            'success': True,
            'message': f'Akun {username} berhasil ditambahkan'
        })
        
    except Exception as e:
        logger.error(f"Error adding account: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/delete_account', methods=['POST'])
def delete_account():
    """Delete account"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({
                'success': False,
                'message': 'Username tidak boleh kosong'
            }), 400
        
        session_file = f"sessions/{username}.session"
        
        if not os.path.exists(session_file):
            return jsonify({
                'success': False,
                'message': f'Akun {username} tidak ditemukan'
            }), 404
        
        # Delete session file
        os.remove(session_file)
        
        logger.info(f"Account deleted: {username}")
        
        # Send notification to Telegram
        telegram_message = f"🗑️ <b>Akun Dihapus</b>\n\n"
        telegram_message += f"👤 Username: {username}\n"
        telegram_message += f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        telegram_message += f"📁 File: {session_file} (deleted)"
        
        send_telegram_message(telegram_message)
        
        return jsonify({
            'success': True,
            'message': f'Akun {username} berhasil dihapus'
        })
        
    except Exception as e:
        logger.error(f"Error deleting account: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'bot_threadsaris'
    })

@app.route('/status', methods=['GET'])
def status():
    """Status endpoint to check available sessions"""
    try:
        sessions_dir = "sessions"
        if not os.path.exists(sessions_dir):
            os.makedirs(sessions_dir, exist_ok=True)
        
        session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.session')]
        accounts = [f.replace('.session', '') for f in session_files]
        
        uploads_dir = "uploads"
        if not os.path.exists(uploads_dir):
            os.makedirs(uploads_dir, exist_ok=True)
        
        upload_files = os.listdir(uploads_dir)
        
        return jsonify({
            'status': 'online',
            'accounts_available': len(accounts),
            'accounts': accounts,
            'uploaded_files': len(upload_files),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('sessions', exist_ok=True)
    os.makedirs('uploads', exist_ok=True)
    
    # Send startup notification
    startup_message = f"🚀 <b>Bot Started</b>\n\n"
    startup_message += f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    startup_message += f"🔗 Endpoint: https://bot-threadsaris.repl.co/post\n"
    startup_message += f"✅ Status: <b>ONLINE</b>"
    
    send_telegram_message(startup_message)
    
    logger.info("Starting bot_threadsaris server...")
    logger.info("Endpoint available at: https://bot-threadsaris.repl.co/post")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
