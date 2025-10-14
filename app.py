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
            token=os.getenv('TWITCH_OAUTH', '5q6yqt6xcelt56pp8ng5h822walu57'),
            prefix='!',
            initial_channels=['blackcraneo']
        )
        self.channel_name = 'blackcraneo'
    
    async def event_ready(self):
        print(f'✅ Conectado a Twitch como {self.nick}')
        print(f'📺 Rastreando canal: {self.channel_name}')
        print(f'🕐 Hora local Santiago: {get_santiago_time()}')
        
        # Obtener usuarios que ya están en el chat
        await self.load_existing_users()
        
        # Iniciar verificación periódica en segundo plano
        asyncio.create_task(self.periodic_user_check())
        
        # Iniciar verificación de usuarios activos cada 10 segundos
        asyncio.create_task(self.active_user_check())
    
    async def load_existing_users(self):
        """Carga usuarios que ya están en el chat cuando se conecta el bot"""
        try:
            # Esperar un poco para que la conexión se estabilice
            await asyncio.sleep(2)
            
            # Obtener la lista de usuarios del canal
            channel = self.get_channel(self.channel_name)
            if channel:
                print(f'🔍 Obteniendo usuarios del canal: {self.channel_name}')
                
                try:
                    # Intentar obtener usuarios con diferentes métodos
                    users = await channel.chatters()
                    print(f'📊 Usuarios obtenidos del canal: {len(users) if users else 0}')
                    
                    join_time = get_santiago_time()
                    users_loaded = 0
                    
                    if users:
                        for user in users:
                            username = user.name if hasattr(user, 'name') else str(user)
                            
                            # Excluir bots
                            if username.lower() in [bot.lower() for bot in EXCLUDED_BOTS]:
                                print(f'🤖 Bot excluido: {username}')
                                continue
                            
                            # Agregar usuario existente
                            user_data = {
                                'username': username,
                                'join_time': f"{join_time} (ya estaba)",
                                'leave_time': None,
                                'duration': None,
                                'status': 'viendo'
                            }
                            
                            current_viewers[username] = user_data
                            users_loaded += 1
                            
                            # Agregar al historial como usuario existente
                            history_entry = {
                                **user_data,
                                'action': 'ya estaba'
                            }
                            all_history.append(history_entry)
                            
                            print(f'✅ Usuario cargado: {username}')
                    
                    print(f'📋 Total cargados: {users_loaded} usuarios que ya estaban en el chat')
                    
                except Exception as e:
                    print(f'⚠️ Error obteniendo chatters: {e}')
                    print('🔄 El sistema seguirá funcionando con detección en tiempo real')
                
        except Exception as e:
            print(f'⚠️ Error general cargando usuarios existentes: {e}')
    
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
    
    async def event_message(self, message):
        """Detecta cuando alguien envía un mensaje en el chat - MÉTODO PRINCIPAL"""
        user = message.author
        username = user.name
        
        # Excluir bots
        if username.lower() in [bot.lower() for bot in EXCLUDED_BOTS]:
            return
        
        # Si el usuario no está en la lista de viewers, agregarlo INMEDIATAMENTE
        if username not in current_viewers:
            join_time = get_santiago_time()
            
            user_data = {
                'username': username,
                'join_time': f"{join_time} (detectado por chat)",
                'leave_time': None,
                'duration': None,
                'status': 'viendo'
            }
            
            current_viewers[username] = user_data
            
            # Agregar al historial
            history_entry = {
                **user_data,
                'action': 'detectado por chat'
            }
            all_history.append(history_entry)
            
            print(f'💬 {username} detectado por mensaje en chat a las {join_time}')
            print(f'📊 Total usuarios actuales: {len(current_viewers)}')
        else:
            # Usuario ya existe, actualizar último mensaje
            current_viewers[username]['last_activity'] = get_santiago_time()
            print(f'💬 {username} envió mensaje (ya estaba en lista)')
    
    async def event_user_state(self, channel, user):
        """Detecta cambios de estado del usuario"""
        username = user.name
        
        # Excluir bots
        if username.lower() in [bot.lower() for bot in EXCLUDED_BOTS]:
            return
        
        # Si el usuario no está en la lista, agregarlo
        if username not in current_viewers:
            join_time = get_santiago_time()
            
            user_data = {
                'username': username,
                'join_time': f"{join_time} (detectado por estado)",
                'leave_time': None,
                'duration': None,
                'status': 'viendo'
            }
            
            current_viewers[username] = user_data
            
            # Agregar al historial
            history_entry = {
                **user_data,
                'action': 'detectado por estado'
            }
            all_history.append(history_entry)
            
            print(f'👤 {username} detectado por estado a las {join_time}')
            print(f'📊 Total usuarios actuales: {len(current_viewers)}')
    
    async def periodic_user_check(self):
        """Verificación periódica de usuarios activos cada 30 segundos"""
        while True:
            try:
                await asyncio.sleep(30)  # Esperar 30 segundos
                
                # Obtener usuarios del canal periódicamente
                channel = self.get_channel(self.channel_name)
                if channel:
                    try:
                        users = await channel.chatters()
                        if users:
                            current_users = set(user.name if hasattr(user, 'name') else str(user) for user in users)
                            
                            # Agregar usuarios que no están en nuestra lista
                            for username in current_users:
                                if username.lower() not in [bot.lower() for bot in EXCLUDED_BOTS]:
                                    if username not in current_viewers:
                                        join_time = get_santiago_time()
                                        
                                        user_data = {
                                            'username': username,
                                            'join_time': f"{join_time} (detectado periódicamente)",
                                            'leave_time': None,
                                            'duration': None,
                                            'status': 'viendo'
                                        }
                                        
                                        current_viewers[username] = user_data
                                        
                                        history_entry = {
                                            **user_data,
                                            'action': 'detectado periódicamente'
                                        }
                                        all_history.append(history_entry)
                                        
                                        print(f'🔄 {username} detectado en verificación periódica')
                            
                            # Detectar usuarios que salieron (están en nuestra lista pero no en el canal)
                            users_to_remove = []
                            for username in current_viewers.keys():
                                if username not in current_users:
                                    users_to_remove.append(username)
                            
                            for username in users_to_remove:
                                if username.lower() not in [bot.lower() for bot in EXCLUDED_BOTS]:
                                    user_data = current_viewers[username]
                                    leave_time = get_santiago_time()
                                    
                                    # Calcular duración
                                    duration = calculate_duration(user_data['join_time'], leave_time)
                                    
                                    # Crear entrada de salida
                                    leave_data = {
                                        'username': username,
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
                                    del current_viewers[username]
                                    
                                    print(f'👋 {username} salió del stream (detectado periódicamente) a las {leave_time}')
                        
                        print(f'📊 Verificación periódica completada. Total usuarios: {len(current_viewers)}')
                        
                    except Exception as e:
                        print(f'⚠️ Error en verificación periódica: {e}')
                        
            except Exception as e:
                print(f'⚠️ Error en verificación periódica general: {e}')
                await asyncio.sleep(30)
    
    async def active_user_check(self):
        """Verificación de usuarios activos cada 10 segundos"""
        while True:
            try:
                await asyncio.sleep(10)  # Esperar 10 segundos
                
                # Obtener usuarios del canal para verificar actividad
                channel = self.get_channel(self.channel_name)
                if channel:
                    try:
                        users = await channel.chatters()
                        if users:
                            current_users = set(user.name if hasattr(user, 'name') else str(user) for user in users)
                            
                            # Agregar usuarios activos que no están en nuestra lista
                            for username in current_users:
                                if username.lower() not in [bot.lower() for bot in EXCLUDED_BOTS]:
                                    if username not in current_viewers:
                                        join_time = get_santiago_time()
                                        
                                        user_data = {
                                            'username': username,
                                            'join_time': f"{join_time} (detectado activo)",
                                            'leave_time': None,
                                            'duration': None,
                                            'status': 'viendo'
                                        }
                                        
                                        current_viewers[username] = user_data
                                        
                                        history_entry = {
                                            **user_data,
                                            'action': 'detectado activo'
                                        }
                                        all_history.append(history_entry)
                                        
                                        print(f'👁️ {username} detectado como usuario activo')
                        
                        print(f'👁️ Verificación de usuarios activos completada. Total: {len(current_viewers)}')
                        
                    except Exception as e:
                        print(f'⚠️ Error en verificación de usuarios activos: {e}')
                        
            except Exception as e:
                print(f'⚠️ Error en verificación de usuarios activos general: {e}')
                await asyncio.sleep(10)

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
                padding: 10px;
            }
            
            .container {
                max-width: 400px;
                margin: 0 auto;
            }
            
            .time-header {
                text-align: center;
                margin-bottom: 15px;
            }
            
            .current-time {
                font-size: 1.2em;
                color: #ffaaaa;
                background: rgba(139, 0, 0, 0.3);
                padding: 10px 15px;
                border-radius: 8px;
                border: 1px solid #8b0000;
                display: inline-block;
                font-weight: bold;
            }
            
            .header {
                text-align: center;
                margin-top: 15px;
                background: rgba(139, 0, 0, 0.2);
                padding: 10px;
                border-radius: 8px;
                border: 1px solid #8b0000;
            }
            
            .header h1 {
                font-size: 1.2em;
                color: #ff4444;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
                margin-bottom: 5px;
            }
            
            .header h2 {
                color: #ff6666;
                margin-bottom: 0;
                font-size: 0.9em;
            }
            
            .stats-grid {
                display: flex;
                justify-content: center;
                margin-bottom: 20px;
            }
            
            .stat-card {
                background: linear-gradient(145deg, #2a1a1a, #1a1a1a);
                padding: 15px 25px;
                border-radius: 10px;
                text-align: center;
                border: 2px solid #8b0000;
                box-shadow: 0 4px 15px rgba(139, 0, 0, 0.3);
            }
            
            .stat-number {
                font-size: 2.5em;
                font-weight: bold;
                color: #ff4444;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.8);
                margin-bottom: 5px;
            }
            
            .stat-label {
                color: #ffaaaa;
                font-size: 1em;
                font-weight: 600;
            }
            
            .panels-grid {
                display: flex;
                flex-direction: column;
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .panel {
                background: linear-gradient(145deg, #2a1a1a, #1a1a1a);
                border-radius: 10px;
                border: 2px solid #8b0000;
                overflow: hidden;
                box-shadow: 0 4px 15px rgba(139, 0, 0, 0.3);
            }
            
            .panel-header {
                background: linear-gradient(90deg, #8b0000, #cc0000);
                padding: 10px 15px;
                text-align: center;
                font-size: 1.1em;
                font-weight: bold;
                color: white;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
            }
            
            .panel-content {
                max-height: 200px;
                overflow-y: auto;
                padding: 10px;
            }
            
            .user-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 8px 12px;
                margin: 4px 0;
                background: rgba(139, 0, 0, 0.1);
                border-radius: 8px;
                border-left: 3px solid #ff4444;
                transition: all 0.2s ease;
            }
            
            .user-item:hover {
                background: rgba(139, 0, 0, 0.2);
            }
            
            .user-name {
                font-weight: bold;
                color: #ff6666;
                font-size: 1em;
            }
            
            .user-time {
                color: #ffaaaa;
                font-size: 0.8em;
            }
            
            .user-duration {
                color: #ff8888;
                font-weight: 600;
                font-size: 0.8em;
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
            
             .status-ya-estaba {
                 border-left-color: #8888ff;
             }
             
             .status-detectado-por-chat {
                 border-left-color: #ff8800;
             }
             
             .status-detectado-por-estado {
                 border-left-color: #8800ff;
             }
             
             .status-detectado-periódicamente {
                 border-left-color: #00ff88;
             }
             
             .status-detectado-activo {
                 border-left-color: #ffff00;
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
            <div class="time-header">
                <div class="current-time" id="current-time"></div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number" id="espectadores">0</div>
                    <div class="stat-label">Espectadores</div>
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
            
            <div class="header">
                <h1>🎮 Twitch Viewer Tracker</h1>
                <h2>Canal: Blackcraneo</h2>
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
                             } else if (entry.action === 'ya estaba') {
                                 actionText = `Ya estaba: ${entry.join_time}`;
                                 icon = '🔵';
                             } else if (entry.action === 'detectado por chat') {
                                 actionText = `Detectado por chat: ${entry.join_time}`;
                                 icon = '💬';
                             } else if (entry.action === 'detectado por estado') {
                                 actionText = `Detectado por estado: ${entry.join_time}`;
                                 icon = '👤';
                             } else if (entry.action === 'detectado periódicamente') {
                                 actionText = `Detectado periódicamente: ${entry.join_time}`;
                                 icon = '🔄';
                             } else if (entry.action === 'detectado activo') {
                                 actionText = `Detectado activo: ${entry.join_time}`;
                                 icon = '👁️';
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
             setInterval(updateStats, 1000);  // Estadísticas cada 1 segundo
             setInterval(updateViendo, 2000); // Viendo cada 2 segundos
             setInterval(updateSalieron, 2000); // Salieron cada 2 segundos
             setInterval(updateHistorial, 3000); // Historial cada 3 segundos
            
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
