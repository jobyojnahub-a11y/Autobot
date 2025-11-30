import os
import json
import asyncio
import aiohttp
import base64
from flask import Flask, render_template_string, request, jsonify, redirect, session
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import yt_dlp
from datetime import datetime
import secrets

# Flask App for Admin Panel
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Database (JSON files for simplicity)
DB_FILE = 'database.json'

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {'channels': {}, 'batches': {}, 'admin_password': 'admin123'}

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

# HTML Templates
ADMIN_LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Login</title>
    <style>
        body { font-family: Arial; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 300px; }
        h2 { text-align: center; color: #1a73e8; margin-bottom: 30px; }
        input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }
        button { width: 100%; padding: 12px; background: #1a73e8; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #1557b0; }
        .error { color: red; text-align: center; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🔐 Admin Login</h2>
        <form method="POST">
            <input type="password" name="password" placeholder="Enter Admin Password" required>
            <button type="submit">Login</button>
        </form>
        {% if error %}
        <p class="error">{{ error }}</p>
        {% endif %}
    </div>
</body>
</html>
"""

ADMIN_PANEL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial; background: #f0f2f5; }
        .header { background: #1a73e8; color: white; padding: 20px; display: flex; justify-content: space-between; align-items: center; }
        .container { max-width: 1200px; margin: 20px auto; padding: 0 20px; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab { padding: 12px 24px; background: white; border: none; cursor: pointer; border-radius: 5px; font-size: 16px; }
        .tab.active { background: #1a73e8; color: white; }
        .content { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .card { background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #1a73e8; }
        .card h3 { margin-bottom: 10px; color: #333; }
        .badge { display: inline-block; padding: 5px 12px; background: #e3f2fd; color: #1a73e8; border-radius: 15px; font-size: 12px; margin: 5px; }
        input, select, textarea { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; }
        button { padding: 12px 24px; background: #1a73e8; color: white; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }
        button:hover { background: #1557b0; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #c82333; }
        .logout { background: #dc3545; padding: 10px 20px; border-radius: 5px; color: white; text-decoration: none; }
        .hidden { display: none; }
        .connection { background: #e8f5e9; padding: 10px; margin: 5px 0; border-radius: 5px; display: flex; justify-content: space-between; align-items: center; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Rarestudy Bot Admin Panel</h1>
        <a href="/logout" class="logout">Logout</a>
    </div>
    
    <div class="container">
        <div class="tabs">
            <button class="tab active" onclick="showTab('channels')">📺 Channels</button>
            <button class="tab" onclick="showTab('batches')">📚 Batches</button>
            <button class="tab" onclick="showTab('connections')">🔗 Connections</button>
        </div>
        
        <div id="channels-tab" class="content">
            <h2>Manage Channels</h2>
            <div id="channels-list"></div>
            <hr style="margin: 30px 0;">
            <h3>Add New Channel</h3>
            <input type="text" id="channel-id" placeholder="Channel ID (e.g., -1001234567890)">
            <input type="text" id="channel-name" placeholder="Channel Name">
            <button onclick="addChannel()">Add Channel</button>
        </div>
        
        <div id="batches-tab" class="content hidden">
            <h2>Manage Batches</h2>
            <div id="batches-list"></div>
            <hr style="margin: 30px 0;">
            <h3>Add New Batch</h3>
            <input type="text" id="batch-id" placeholder="Batch ID">
            <input type="text" id="batch-name" placeholder="Batch Name">
            <textarea id="batch-token" placeholder="Session Token (cookie)" rows="4"></textarea>
            <button onclick="addBatch()">Add Batch</button>
        </div>
        
        <div id="connections-tab" class="content hidden">
            <h2>Channel-Batch Connections</h2>
            <div id="connections-list"></div>
            <hr style="margin: 30px 0;">
            <h3>Create Connection</h3>
            <select id="connect-channel"></select>
            <select id="connect-batch"></select>
            <button onclick="createConnection()">Connect</button>
        </div>
    </div>
    
    <script>
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.content').forEach(c => c.classList.add('hidden'));
            event.target.classList.add('active');
            document.getElementById(tab + '-tab').classList.remove('hidden');
            loadData();
        }
        
        async function loadData() {
            const res = await fetch('/api/data');
            const data = await res.json();
            
            const channelsList = document.getElementById('channels-list');
            channelsList.innerHTML = '';
            for (const [id, channel] of Object.entries(data.channels)) {
                channelsList.innerHTML += `
                    <div class="card">
                        <h3>${channel.name}</h3>
                        <p><strong>ID:</strong> ${id}</p>
                        <p><strong>Connected Batches:</strong> ${channel.batches.length}</p>
                        ${channel.batches.map(b => `<span class="badge">${data.batches[b]?.name || b}</span>`).join('')}
                        <br><button class="btn-danger" onclick="deleteChannel('${id}')">Delete</button>
                    </div>
                `;
            }
            
            const batchesList = document.getElementById('batches-list');
            batchesList.innerHTML = '';
            for (const [id, batch] of Object.entries(data.batches)) {
                batchesList.innerHTML += `
                    <div class="card">
                        <h3>${batch.name}</h3>
                        <p><strong>Batch ID:</strong> ${id}</p>
                        <button class="btn-danger" onclick="deleteBatch('${id}')">Delete</button>
                    </div>
                `;
            }
            
            const connectionsList = document.getElementById('connections-list');
            connectionsList.innerHTML = '';
            for (const [id, channel] of Object.entries(data.channels)) {
                for (const batchId of channel.batches) {
                    connectionsList.innerHTML += `
                        <div class="connection">
                            <span>📺 ${channel.name} ↔️ 📚 ${data.batches[batchId]?.name || batchId}</span>
                            <button class="btn-danger" onclick="removeConnection('${id}', '${batchId}')">Remove</button>
                        </div>
                    `;
                }
            }
            
            const channelSelect = document.getElementById('connect-channel');
            const batchSelect = document.getElementById('connect-batch');
            channelSelect.innerHTML = '<option value="">Select Channel</option>';
            batchSelect.innerHTML = '<option value="">Select Batch</option>';
            for (const [id, channel] of Object.entries(data.channels)) {
                channelSelect.innerHTML += `<option value="${id}">${channel.name}</option>`;
            }
            for (const [id, batch] of Object.entries(data.batches)) {
                batchSelect.innerHTML += `<option value="${id}">${batch.name}</option>`;
            }
        }
        
        async function addChannel() {
            const id = document.getElementById('channel-id').value;
            const name = document.getElementById('channel-name').value;
            await fetch('/api/channel', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id, name})
            });
            loadData();
        }
        
        async function addBatch() {
            const id = document.getElementById('batch-id').value;
            const name = document.getElementById('batch-name').value;
            const token = document.getElementById('batch-token').value;
            await fetch('/api/batch', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id, name, token})
            });
            loadData();
        }
        
        async function createConnection() {
            const channel = document.getElementById('connect-channel').value;
            const batch = document.getElementById('connect-batch').value;
            await fetch('/api/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({channel, batch})
            });
            loadData();
        }
        
        async function deleteChannel(id) {
            if (confirm('Delete this channel?')) {
                await fetch(`/api/channel/${id}`, {method: 'DELETE'});
                loadData();
            }
        }
        
        async function deleteBatch(id) {
            if (confirm('Delete this batch?')) {
                await fetch(`/api/batch/${id}`, {method: 'DELETE'});
                loadData();
            }
        }
        
        async function removeConnection(channel, batch) {
            await fetch('/api/disconnect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({channel, batch})
            });
            loadData();
        }
        
        loadData();
    </script>
</body>
</html>
"""

# Flask Routes
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect('/login')
    return render_template_string(ADMIN_PANEL_HTML)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = load_db()
        if request.form['password'] == db['admin_password']:
            session['logged_in'] = True
            return redirect('/')
        return render_template_string(ADMIN_LOGIN_HTML, error='Invalid password')
    return render_template_string(ADMIN_LOGIN_HTML)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/login')

@app.route('/api/data')
def get_data():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(load_db())

@app.route('/api/channel', methods=['POST'])
def add_channel():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = load_db()
    data = request.json
    db['channels'][data['id']] = {'name': data['name'], 'batches': []}
    save_db(db)
    return jsonify({'success': True})

@app.route('/api/channel/<channel_id>', methods=['DELETE'])
def delete_channel(channel_id):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = load_db()
    db['channels'].pop(channel_id, None)
    save_db(db)
    return jsonify({'success': True})

@app.route('/api/batch', methods=['POST'])
def add_batch():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = load_db()
    data = request.json
    db['batches'][data['id']] = {'name': data['name'], 'token': data['token']}
    save_db(db)
    return jsonify({'success': True})

@app.route('/api/batch/<batch_id>', methods=['DELETE'])
def delete_batch(batch_id):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = load_db()
    db['batches'].pop(batch_id, None)
    save_db(db)
    return jsonify({'success': True})

@app.route('/api/connect', methods=['POST'])
def connect():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = load_db()
    data = request.json
    if data['batch'] not in db['channels'][data['channel']]['batches']:
        db['channels'][data['channel']]['batches'].append(data['batch'])
    save_db(db)
    return jsonify({'success': True})

@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = load_db()
    data = request.json
    if data['batch'] in db['channels'][data['channel']]['batches']:
        db['channels'][data['channel']]['batches'].remove(data['batch'])
    save_db(db)
    return jsonify({'success': True})

# Telegram Bot Functions
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /check command"""
    chat_id = str(update.effective_chat.id)
    db = load_db()
    
    print(f"📥 Received /check from chat_id: {chat_id}")
    
    if chat_id not in db['channels']:
        await update.message.reply_text(f'❌ Channel not registered!\n\nYour Chat ID: `{chat_id}`\n\nAdd this ID in admin panel.', parse_mode='Markdown')
        return
    
    channel = db['channels'][chat_id]
    if not channel['batches']:
        await update.message.reply_text('❌ No batch connected to this channel.')
        return
    
    batch_id = channel['batches'][0]
    batch = db['batches'].get(batch_id)
    
    if not batch:
        await update.message.reply_text('❌ Batch not found.')
        return
    
    await update.message.reply_text(f'🔍 Checking batch: {batch["name"]}...')
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'cookie': f'session={batch["token"]}'
            }
            
            async with session.get(f'https://rarestudy.site/subjects/{batch_id}', headers=headers) as resp:
                html = await resp.text()
                
            import re
            ended_classes = re.findall(r'handleVideo\(\'Ended\', \'(/media/[^\']+)', html)
            
            if not ended_classes:
                await update.message.reply_text('✅ No new completed classes today.')
                return
            
            await update.message.reply_text(f'📚 Found {len(ended_classes)} completed class(es). Processing...')
            
            for media_path in ended_classes[:2]:
                try:
                    encoded = media_path.split('/')[-1]
                    async with session.get(f'https://rarestudy.site/video-data?encoded={encoded}', headers=headers) as resp:
                        video_data = await resp.json()
                    
                    if not video_data.get('success'):
                        continue
                    
                    async with session.get(f'https://pdablu-yourl.wasmer.app/?data={video_data["data"]}') as resp:
                        url_data = await resp.json()
                    
                    m3u8_url = url_data.get('m3u8_url')
                    if not m3u8_url:
                        continue
                    
                    status_msg = await update.message.reply_text('⬇️ Downloading video...')
                    output_file = f'video_{int(datetime.now().timestamp())}.mp4'
                    
                    ydl_opts = {
                        'format': 'best',
                        'outtmpl': output_file,
                        'quiet': True,
                        'no_warnings': True,
                    }
                    
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([m3u8_url]))
                    
                    if os.path.exists(output_file):
                        await status_msg.edit_text('⬆️ Uploading video...')
                        
                        with open(output_file, 'rb') as video:
                            await context.bot.send_video(
                                chat_id=chat_id,
                                video=video,
                                caption=f'📹 Class Video\n⏰ {datetime.now().strftime("%d/%m/%Y %H:%M")}',
                                supports_streaming=True
                            )
                        
                        os.remove(output_file)
                        await status_msg.edit_text('✅ Video uploaded!')
                    else:
                        await status_msg.edit_text('❌ Download failed!')
                        
                except Exception as e:
                    print(f"❌ Error: {str(e)}")
                    await update.message.reply_text(f'❌ Error: {str(e)[:100]}')
                    
    except Exception as e:
        print(f"❌ Main Error: {str(e)}")
        await update.message.reply_text(f'❌ Error: {str(e)}')

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        '👋 Welcome to Rarestudy Bot!\n\n'
        'Commands:\n'
        '/check - Check for new classes\n\n'
        'Admin Panel: Access via your Render URL'
    )

# Global bot application
bot_app = None

async def start_bot_async():
    """Start bot in async context"""
    global bot_app
    BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
    
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ BOT_TOKEN not set!")
        return
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler('start', start_command))
    bot_app.add_handler(CommandHandler('check', check_command))
    
    print("✅ Telegram bot starting...")
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)
    print("✅ Bot is running!")

def run_bot():
    """Run bot in new event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_bot_async())
    loop.run_forever()

if __name__ == '__main__':
    import threading
    
    # Start bot in separate thread with new event loop
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
