import os
import asyncio
import json
from datetime import datetime
from typing import Dict, List
import pytz
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import twitchio
from twitchio.ext import commands
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de la aplicación Flask
app = Flask(__name__)
CORS(app)

# Configuración de zona horaria
SANTIAGO_TZ = pytz.timezone('America/Santiago')

# Almacenamiento de datos de usuarios
current_viewers: Dict[str, Dict] = {}  # Usuarios actualmente viendo
left_viewers: List[Dict] = []  # Usuarios que salieron
all_history: List[Dict] = []  # Historial completo

# Lista de bots a excluir (agrega aquí los nombres de tus bots)
EXCLUDED_BOTS = [
    'blackcraneo',  # El bot principal
    'streamelements',  # StreamElements
    'streamlabs',  # StreamLabs
    'nightbot',  # Nightbot
    'moobot',  # Moobot
    'fossabot',  # Fossabot
    'wizebot',  # Wizebot
    'deepbot',  # Deepbot
    'creatisbot', #Creatisbot
    # Agrega aquí los nombres de tus bots personalizados
]

class TwitchTracker(commands.Bot):
    def __init__(self):
        super().__init__(
            token=os.getenv('TWITCH_OAUTH', 'sdbw6mijgytm5bfcwhzq3uk5orn2j5'),
            prefix='!',
            initial_channels=['blackcraneo']
        )
        self.channel_name = 'blackcraneo'
    
    async def event_ready(self):
        print(f'✅ Conectado a Twitch como {self.nick}')
        print(f'📺 Rastreando canal: {self.channel_name}')
        print(f'🕐 Hora local Santiago: {get_santiago_time()}')
    
    async def event_join(self, channel, user):
        # Excluir bots de la lista
        if user.name.lower() in [bot.lower() for bot in EXCLUDED_BOTS]:
            print(f'🤖 Bot excluido: {user.name}')
            return
        
        join_time = get_santiago_time()
        
        # Crear datos del usuario
        user_data = {
            'username': user.name,
            'join_time': join_time,
            'leave_time': None,
            'duration': None,
            'status': 'viendo'
        }
        
        # Agregar a usuarios actuales
        current_viewers[user.name] = user_data
        
        # Agregar al historial
        history_entry = {
            **user_data,
            'action': 'entró'
        }
        all_history.append(history_entry)
        
        print(f'👋 {user.name} entró al stream a las {join_time}')
    
    async def event_part(self, channel, user):
        # Excluir bots de la lista
        if user.name.lower() in [bot.lower() for bot in EXCLUDED_BOTS]:
            print(f'🤖 Bot excluido: {user.name}')
            return
        
        leave_time = get_santiago_time()
        
        # Verificar si el usuario estaba en la lista
        if user.name in current_viewers:
            user_data = current_viewers[user.name]
            
            # Calcular duración
            duration = calculate_duration(user_data['join_time'], leave_time)
            
            # Crear entrada de salida
            leave_data = {
                'username': user.name,
                'join_time': user_data['join_time'],
                'leave_time': leave_time,
                'duration': duration,
                'status': 'salió'
            }
            
            # Agregar a la lista de usuarios que salieron
            left_viewers.append(leave_data)
            
            # Agregar al historial
            history_entry = {
                **leave_data,
                'action': 'salió'
            }
            all_history.append(history_entry)
            
            # Remover de usuarios actuales
            del current_viewers[user.name]
            
            print(f'👋 {user.name} salió del stream a las {leave_time} (Estuvo: {duration})')

def get_santiago_time() -> str:
    """Obtiene la hora actual en Santiago, Chile"""
    now = datetime.now(SANTIAGO_TZ)
    return now.strftime('%Y-%m-%d %H:%M:%S')

def calculate_duration(start_time: str, end_time: str) -> str:
    """Calcula la duración entre dos timestamps"""
    start = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
    end = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
    
    duration = end - start
    hours = int(duration.total_seconds() // 3600)
    minutes = int((duration.total_seconds() % 3600) // 60)
    seconds = int(duration.total_seconds() % 60)
    
    return f"{hours}h {minutes}m {seconds}s"

# Crear instancia del bot
bot = TwitchTracker()

# Rutas de la API
@app.route('/')
def dashboard():
    """Dashboard principal"""
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Twitch Viewer Tracker - Blackcraneo</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #1a1a1a 0%, #2d1b1b 50%, #1a1a1a 100%);
                color: #ffffff;
                min-height: 100vh;
                padding: 20px;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
            }
            
            .header {
                text-align: center;
                margin-bottom: 30px;
                background: rgba(139, 0, 0, 0.3);
                padding: 20px;
                border-radius: 15px;
                border: 2px solid #8b0000;
            }
            
            .header h1 {
                font-size: 2.5em;
                color: #ff4444;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.8);
                margin-bottom: 10px;
            }
            
            .header h2 {
                color: #ff6666;
                margin-bottom: 10px;
            }
            
            .current-time {
                font-size: 1.2em;
                color: #ffaaaa;
                background: rgba(139, 0, 0, 0.2);
                padding: 10px;
                border-radius: 10px;
                display: inline-block;
            }
            
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            
            .stat-card {
                background: linear-gradient(145deg, #2a1a1a, #1a1a1a);
                padding: 25px;
                border-radius: 15px;
                text-align: center;
                border: 2px solid #8b0000;
                box-shadow: 0 8px 25px rgba(139, 0, 0, 0.3);
                transition: transform 0.3s ease;
            }
            
            .stat-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 12px 35px rgba(139, 0, 0, 0.4);
            }
            
            .stat-number {
                font-size: 3em;
                font-weight: bold;
                color: #ff4444;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.8);
                margin-bottom: 10px;
            }
            
            .stat-label {
                color: #ffaaaa;
                font-size: 1.1em;
                font-weight: 600;
            }
            
            .panels-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 25px;
                margin-bottom: 30px;
            }
            
            .panel {
                background: linear-gradient(145deg, #2a1a1a, #1a1a1a);
                border-radius: 15px;
                border: 2px solid #8b0000;
                overflow: hidden;
                box-shadow: 0 8px 25px rgba(139, 0, 0, 0.3);
            }
            
            .panel-header {
                background: linear-gradient(90deg, #8b0000, #cc0000);
                padding: 15px 20px;
                text-align: center;
                font-size: 1.3em;
                font-weight: bold;
                color: white;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
            }
            
            .panel-content {
                max-height: 400px;
                overflow-y: auto;
                padding: 15px;
            }
            
            .user-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px;
                margin: 8px 0;
                background: rgba(139, 0, 0, 0.1);
                border-radius: 10px;
                border-left: 4px solid #ff4444;
                transition: all 0.3s ease;
            }
            
            .user-item:hover {
                background: rgba(139, 0, 0, 0.2);
                transform: translateX(5px);
            }
            
            .user-name {
                font-weight: bold;
                color: #ff6666;
                font-size: 1.1em;
            }
            
            .user-time {
                color: #ffaaaa;
                font-size: 0.9em;
            }
            
            .user-duration {
                color: #ff8888;
                font-weight: 600;
                font-size: 0.9em;
            }
            
            .status-viendo {
                border-left-color: #00ff00;
            }
            
            .status-salió {
                border-left-color: #ff4444;
            }
            
            .status-entró {
                border-left-color: #0088ff;
            }
            
            .empty-message {
                text-align: center;
                color: #ffaaaa;
                font-style: italic;
                padding: 20px;
                background: rgba(139, 0, 0, 0.1);
                border-radius: 10px;
                border: 1px dashed #8b0000;
            }
            
            .scrollbar-custom {
                scrollbar-width: thin;
                scrollbar-color: #8b0000 #2a1a1a;
            }
            
            .scrollbar-custom::-webkit-scrollbar {
                width: 8px;
            }
            
            .scrollbar-custom::-webkit-scrollbar-track {
                background: #2a1a1a;
                border-radius: 4px;
            }
            
            .scrollbar-custom::-webkit-scrollbar-thumb {
                background: #8b0000;
                border-radius: 4px;
            }
            
            .scrollbar-custom::-webkit-scrollbar-thumb:hover {
                background: #cc0000;
            }
            
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.7; }
                100% { opacity: 1; }
            }
            
            .pulse {
                animation: pulse 2s infinite;
            }
            
            @media (max-width: 768px) {
                .panels-grid {
                    grid-template-columns: 1fr;
                }
                
                .stats-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
                
                .header h1 {
                    font-size: 2em;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎮 Twitch Viewer Tracker</h1>
                <h2>Canal: Blackcraneo</h2>
                <div class="current-time" id="current-time"></div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number" id="espectadores">0</div>
                    <div class="stat-label">Espectadores</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="viendo">0</div>
                    <div class="stat-label">Viendo Ahora</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="salieron">0</div>
                    <div class="stat-label">Salieron</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="total-historial">0</div>
                    <div class="stat-label">Total Historial</div>
                </div>
            </div>
            
            <div class="panels-grid">
                <div class="panel">
                    <div class="panel-header">👥 Viendo Ahora</div>
                    <div class="panel-content scrollbar-custom" id="viendo-list">
                        <div class="empty-message">Esperando usuarios...</div>
                    </div>
                </div>
                
                <div class="panel">
                    <div class="panel-header">🚪 Salieron Recientemente</div>
                    <div class="panel-content scrollbar-custom" id="salieron-list">
                        <div class="empty-message">Nadie ha salido aún</div>
                    </div>
                </div>
                
                <div class="panel">
                    <div class="panel-header">📊 Historial Completo</div>
                    <div class="panel-content scrollbar-custom" id="historial-list">
                        <div class="empty-message">Historial vacío</div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            function updateTime() {
                const now = new Date();
                const santiagoTime = new Intl.DateTimeFormat('es-CL', {
                    timeZone: 'America/Santiago',
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                }).format(now);
                document.getElementById('current-time').textContent = santiagoTime;
            }
            
            function updateStats() {
                fetch('/api/stats')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('espectadores').textContent = data.espectadores;
                        document.getElementById('viendo').textContent = data.viendo;
                        document.getElementById('salieron').textContent = data.salieron;
                        document.getElementById('total-historial').textContent = data.total_historial;
                    });
            }
            
            function updateViendo() {
                fetch('/api/viendo')
                    .then(response => response.json())
                    .then(data => {
                        const list = document.getElementById('viendo-list');
                        list.innerHTML = '';
                        
                        if (data.users.length === 0) {
                            list.innerHTML = '<div class="empty-message">Esperando usuarios...</div>';
                            return;
                        }
                        
                        data.users.forEach(user => {
                            const item = document.createElement('div');
                            item.className = 'user-item status-viendo';
                            item.innerHTML = `
                                <div>
                                    <div class="user-name">${user.username}</div>
                                    <div class="user-time">Entró: ${user.join_time}</div>
                                </div>
                                <div class="pulse">🟢</div>
                            `;
                            list.appendChild(item);
                        });
                    });
            }
            
            function updateSalieron() {
                fetch('/api/salieron')
                    .then(response => response.json())
                    .then(data => {
                        const list = document.getElementById('salieron-list');
                        list.innerHTML = '';
                        
                        if (data.users.length === 0) {
                            list.innerHTML = '<div class="empty-message">Nadie ha salido aún</div>';
                            return;
                        }
                        
                        data.users.slice(-10).reverse().forEach(user => {
                            const item = document.createElement('div');
                            item.className = 'user-item status-salió';
                            item.innerHTML = `
                                <div>
                                    <div class="user-name">${user.username}</div>
                                    <div class="user-time">Salió: ${user.leave_time}</div>
                                    <div class="user-duration">Estuvo: ${user.duration}</div>
                                </div>
                                <div>🔴</div>
                            `;
                            list.appendChild(item);
                        });
                    });
            }
            
            function updateHistorial() {
                fetch('/api/historial')
                    .then(response => response.json())
                    .then(data => {
                        const list = document.getElementById('historial-list');
                        list.innerHTML = '';
                        
                        if (data.history.length === 0) {
                            list.innerHTML = '<div class="empty-message">Historial vacío</div>';
                            return;
                        }
                        
                        data.history.slice(-20).reverse().forEach(entry => {
                            const item = document.createElement('div');
                            item.className = `user-item status-${entry.status}`;
                            
                            let actionText = '';
                            let icon = '';
                            if (entry.action === 'entró') {
                                actionText = `Entró: ${entry.join_time}`;
                                icon = '🟢';
                            } else if (entry.action === 'salió') {
                                actionText = `Salió: ${entry.leave_time}`;
                                icon = '🔴';
                            }
                            
                            item.innerHTML = `
                                <div>
                                    <div class="user-name">${entry.username}</div>
                                    <div class="user-time">${actionText}</div>
                                    ${entry.duration ? `<div class="user-duration">Estuvo: ${entry.duration}</div>` : ''}
                                </div>
                                <div>${icon}</div>
                            `;
                            list.appendChild(item);
                        });
                    });
            }
            
            // Actualizar cada segundo
            setInterval(updateTime, 1000);
            setInterval(updateStats, 2000);
            setInterval(updateViendo, 3000);
            setInterval(updateSalieron, 3000);
            setInterval(updateHistorial, 5000);
            
            // Cargar datos iniciales
            updateTime();
            updateStats();
            updateViendo();
            updateSalieron();
            updateHistorial();
        </script>
    </body>
    </html>
    ''')

@app.route('/api/stats')
def get_stats():
    """Obtiene estadísticas generales"""
    espectadores = len(current_viewers)
    viendo = len(current_viewers)
    salieron = len(left_viewers)
    total_historial = len(all_history)
    
    return jsonify({
        'espectadores': espectadores,
        'viendo': viendo,
        'salieron': salieron,
        'total_historial': total_historial,
        'timestamp': get_santiago_time()
    })

@app.route('/api/viendo')
def get_viendo():
    """Obtiene usuarios que están viendo actualmente"""
    users = []
    for username, user_data in current_viewers.items():
        users.append({
            'username': username,
            'join_time': user_data['join_time'],
            'current_time': get_santiago_time()
        })
    
    return jsonify({
        'count': len(users),
        'users': users,
        'timestamp': get_santiago_time()
    })

@app.route('/api/salieron')
def get_salieron():
    """Obtiene usuarios que salieron"""
    return jsonify({
        'count': len(left_viewers),
        'users': left_viewers,
        'timestamp': get_santiago_time()
    })

@app.route('/api/historial')
def get_historial():
    """Obtiene el historial completo"""
    return jsonify({
        'count': len(all_history),
        'history': all_history,
        'timestamp': get_santiago_time()
    })

def run_bot():
    """Ejecuta el bot de Twitch en segundo plano"""
    asyncio.run(bot.run())

if __name__ == '__main__':
    import threading
    
    # Iniciar el bot en un hilo separado
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Iniciar el servidor Flask
    port = int(os.getenv('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False)
