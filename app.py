import os
import asyncio
import json
from datetime import datetime
from typing import Dict, List
import pytz
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import requests
import threading
import time
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

class TwitchTracker:
    def __init__(self):
        self.client_id = 'mo983ad8zpisqtkezy4q4ky7qvcoc4'  # Client ID actualizado desde la imagen
        self.client_secret = os.getenv('TWITCH_CLIENT_SECRET', '')
        self.channel_name = 'blackcraneo'
        self.channel_id = None
        self.token = None
        self.token_expires_at = None
        self.headers = {}
        self.running = False
        self.logs = []  # Lista para almacenar logs
        self.max_logs = 50  # Máximo número de logs a mantener
    
    def add_log(self, message):
        """Agrega un mensaje al log"""
        timestamp = get_santiago_time()
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        
        # Mantener solo los últimos logs
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        
        # Imprimir en consola sin emojis para evitar problemas de codificación
        try:
            print(log_entry)
        except UnicodeEncodeError:
            # Si hay problemas con emojis, imprimir sin ellos
            clean_message = ''.join(char for char in message if ord(char) < 128)
            clean_entry = f"[{timestamp}] {clean_message}"
            print(clean_entry)
    
    def get_app_access_token(self):
        """Obtiene un token de aplicación usando Client Credentials Flow"""
        try:
            if not self.client_secret:
                self.add_log('ERROR: TWITCH_CLIENT_SECRET no configurado')
                return False
            
            url = 'https://id.twitch.tv/oauth2/token'
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials'
            }
            
            response = requests.post(url, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                self.token = token_data['access_token']
                self.token_expires_at = time.time() + token_data['expires_in']
                
                # Actualizar headers
                self.headers = {
                    'Authorization': f'Bearer {self.token}',
                    'Client-Id': self.client_id
                }
                
                self.add_log(f'Token de aplicacion obtenido exitosamente')
                self.add_log(f'Token expira en: {token_data["expires_in"]} segundos')
                return True
            else:
                self.add_log(f'ERROR obteniendo token: {response.status_code} - {response.text}')
                return False
                
        except Exception as e:
            self.add_log(f'ERROR en get_app_access_token: {e}')
            return False
    
    def ensure_valid_token(self):
        """Asegura que el token sea válido, lo renueva si es necesario"""
        if not self.token or (self.token_expires_at and time.time() >= self.token_expires_at - 300):
            self.add_log('Token expirado o no existe, renovando...')
            return self.get_app_access_token()
        return True
    
    def mark_user_left(self, username):
        """Marca un usuario como que salió del stream"""
        if username in current_viewers:
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
            
            left_viewers.append(leave_data)
            
            history_entry = {
                **leave_data,
                'action': 'salió'
            }
            all_history.append(history_entry)
            
            del current_viewers[username]
            
            self.add_log(f'🚪 {username} salió del stream (Estuvo: {duration})')
        
    def start(self):
        """Inicia el tracker"""
        self.add_log('🚀 Iniciando Twitch Tracker...')
        self.add_log(f'📺 Canal: {self.channel_name}')
        self.add_log(f'🆔 Client ID: {self.client_id}')
        self.add_log(f'🔑 Client Secret configurado: {bool(self.client_secret)}')
        
        # Obtener token de aplicación
        if not self.get_app_access_token():
            self.add_log('❌ Error: No se pudo obtener token de aplicación')
            return
        
        self.running = True
        
        # Obtener ID del canal
        if self.get_channel_id():
            self.add_log(f'✅ Canal encontrado. ID: {self.channel_id}')
            
            # Cargar usuarios iniciales
            self.load_existing_users()
            
            # Iniciar monitoreo
            threading.Thread(target=self.monitor_loop, daemon=True).start()
            self.add_log('🎯 Twitch Tracker iniciado correctamente')
        else:
            self.add_log('❌ Error: No se pudo obtener el ID del canal')
            self.running = False
    
    def get_channel_id(self):
        """Obtiene el ID del canal usando la API de Twitch"""
        try:
            url = f'https://api.twitch.tv/helix/users?login={self.channel_name}'
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                if data['data']:
                    self.channel_id = data['data'][0]['id']
                    self.add_log(f'✅ ID del canal obtenido: {self.channel_id}')
                    return True
                else:
                    self.add_log('❌ Canal no encontrado en la API')
            else:
                self.add_log(f'❌ Error obteniendo canal: {response.status_code} - {response.text}')
                
        except Exception as e:
            self.add_log(f'❌ Error en get_channel_id: {e}')
        
        return False
    
    def get_chatters(self):
        """Obtiene la lista de chatters del canal usando el endpoint correcto"""
        try:
            # Asegurar token válido
            if not self.ensure_valid_token():
                return []
            
            # Endpoint correcto para obtener chatters
            url = f'https://api.twitch.tv/helix/chat/chatters?broadcaster_id={self.channel_id}&moderator_id={self.channel_id}'
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                chatters = [user['user_name'] for user in data.get('data', [])]
                self.add_log(f"Chatters obtenidos: {len(chatters)} usuarios")
                if chatters:
                    self.add_log(f"Lista de chatters: {', '.join(chatters[:5])}{'...' if len(chatters) > 5 else ''}")
                return chatters
            elif response.status_code == 401:
                self.add_log(f"ERROR: Token OAuth inválido o expirado (401)")
                return []
            elif response.status_code == 403:
                self.add_log(f"ERROR: Sin permisos de moderador (403)")
                return []
            else:
                self.add_log(f"ERROR obteniendo chatters: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            self.add_log(f"ERROR en get_chatters: {e}")
            return []
    
    def get_stream_info(self):
        """Obtiene información del stream actual"""
        try:
            # Asegurar token válido
            if not self.ensure_valid_token():
                return {'is_live': False, 'viewer_count': 0}
            
            url = f'https://api.twitch.tv/helix/streams?user_id={self.channel_id}'
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                if data['data']:
                    stream_data = data['data'][0]
                    viewer_count = stream_data.get('viewer_count', 0)
                    self.add_log(f"Stream activo: {viewer_count} espectadores")
                    self.add_log(f"Título del stream: {stream_data.get('title', 'Sin título')}")
                    return {
                        'is_live': True,
                        'viewer_count': viewer_count,
                        'title': stream_data.get('title', ''),
                        'game_name': stream_data.get('game_name', '')
                    }
                else:
                    # No log de stream offline - el tracker debe funcionar siempre
                    return {'is_live': False, 'viewer_count': 0}
            else:
                self.add_log(f"ERROR obteniendo stream: {response.status_code}")
                return {'is_live': False, 'viewer_count': 0}
                
        except Exception as e:
            self.add_log(f"ERROR en get_stream_info: {e}")
            return {'is_live': False, 'viewer_count': 0}
    
    def get_recent_follows(self):
        """Obtiene follows recientes del canal"""
        try:
            # Asegurar token válido
            if not self.ensure_valid_token():
                return []
            
            url = f'https://api.twitch.tv/helix/users/follows?to_id={self.channel_id}&first=10'
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                follows = data.get('data', [])
                self.add_log(f"Follows recientes: {len(follows)} usuarios")
                if follows:
                    follow_names = [follow['from_name'] for follow in follows[:3]]
                    self.add_log(f"Últimos follows: {', '.join(follow_names)}")
                return follows
            else:
                self.add_log(f"ERROR obteniendo follows: {response.status_code}")
                return []
                
        except Exception as e:
            self.add_log(f"ERROR en get_recent_follows: {e}")
            return []
    
    def load_existing_users(self):
        """Carga usuarios que ya están en el chat cuando se conecta el bot"""
        self.add_log(f'📥 Cargando usuarios existentes del canal: {self.channel_name}')
        
        try:
            chatters = self.get_chatters()
            
            if chatters:
                join_time = get_santiago_time()
                users_loaded = 0
                
                for username in chatters:
                    # Excluir bots
                    if username.lower() in [bot.lower() for bot in EXCLUDED_BOTS]:
                        self.add_log(f'🤖 Bot excluido: {username}')
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
                    
                    self.add_log(f'👤 Usuario cargado: {username}')
                
                self.add_log(f'✅ Total cargados: {users_loaded} usuarios que ya estaban en el chat')
            else:
                self.add_log('⚠️ No se recibieron chatters del canal')
                
        except Exception as e:
            self.add_log(f'❌ Error cargando usuarios existentes: {e}')
        
        self.add_log(f'📊 Estado actual: {len(current_viewers)} usuarios en la lista')
    
    def monitor_loop(self):
        """Loop principal de monitoreo"""
        self.add_log('🔄 Iniciando loop de monitoreo...')
        
        while self.running:
            try:
                time.sleep(5)  # Verificar cada 5 segundos
                
                # Asegurar que el token sea válido
                if not self.ensure_valid_token():
                    self.add_log('❌ Error: No se pudo renovar token, reintentando en 30s...')
                    time.sleep(30)
                    continue
                
                # Log menos frecuente para no saturar
                if len(tracker.logs) < 10 or "Verificando usuarios activos" not in tracker.logs[-1]:
                    self.add_log('🔍 Verificando usuarios activos...')
                
                # Obtener información del stream
                stream_info = self.get_stream_info()
                
                # Obtener chatters del chat
                current_chatters = set(self.get_chatters())
                
                # Obtener follows recientes
                recent_follows = self.get_recent_follows()
                
                # Procesar follows como nuevos espectadores
                self.add_log(f"Procesando {len(recent_follows)} follows recientes...")
                for follow in recent_follows:
                    username = follow['from_name']
                    self.add_log(f"Evaluando follow: {username}")
                    if username.lower() not in [bot.lower() for bot in EXCLUDED_BOTS]:
                        if username not in current_viewers:
                            join_time = get_santiago_time()
                            
                            user_data = {
                                'username': username,
                                'join_time': f"{join_time} (follow detectado)",
                                'leave_time': None,
                                'duration': None,
                                'status': 'viendo'
                            }
                            
                            current_viewers[username] = user_data
                            
                            history_entry = {
                                **user_data,
                                'action': 'detectado por follow'
                            }
                            all_history.append(history_entry)
                            
                            self.add_log(f'👥 {username} detectado por follow')
                        else:
                            self.add_log(f"{username} ya está en la lista de usuarios")
                    else:
                        self.add_log(f"{username} es un bot, excluido")
                
                # Procesar chatters como espectadores activos
                self.add_log(f"Procesando {len(current_chatters)} chatters...")
                for username in current_chatters:
                    self.add_log(f"Evaluando chatter: {username}")
                    if username.lower() not in [bot.lower() for bot in EXCLUDED_BOTS]:
                        if username not in current_viewers:
                            join_time = get_santiago_time()
                            
                            user_data = {
                                'username': username,
                                'join_time': f"{join_time} (chat detectado)",
                                'leave_time': None,
                                'duration': None,
                                'status': 'viendo'
                            }
                            
                            current_viewers[username] = user_data
                            
                            history_entry = {
                                **user_data,
                                'action': 'detectado por chat'
                            }
                            all_history.append(history_entry)
                            
                            self.add_log(f'💬 {username} detectado por chat')
                        else:
                            self.add_log(f"{username} ya está en la lista de usuarios")
                    else:
                        self.add_log(f"{username} es un bot, excluido")
                
                # Detectar usuarios que salieron (si no están en chatters ni follows recientes)
                users_to_remove = []
                for username in current_viewers.keys():
                    if username not in current_chatters:
                        # Verificar si no está en follows recientes
                        in_recent_follows = any(follow['from_name'] == username for follow in recent_follows)
                        if not in_recent_follows:
                            users_to_remove.append(username)
                
                for username in users_to_remove:
                    if username.lower() not in [bot.lower() for bot in EXCLUDED_BOTS]:
                        self.mark_user_left(username)
                
                # Log del estado actual solo cuando hay actividad
                if stream_info['is_live']:
                    self.add_log(f'📊 Estado: {len(current_viewers)} usuarios detectados, {stream_info["viewer_count"]} espectadores totales')
                elif len(current_viewers) > 0:
                    # Solo mostrar estado si hay usuarios detectados
                    self.add_log(f'📊 Estado: {len(current_viewers)} usuarios detectados')
                
                # Log detallado del estado
                self.add_log(f"=== RESUMEN DEL CICLO ===")
                self.add_log(f"Stream en vivo: {stream_info['is_live']}")
                self.add_log(f"Chatters detectados: {len(current_chatters)}")
                self.add_log(f"Follows recientes: {len(recent_follows)}")
                self.add_log(f"Usuarios actuales: {len(current_viewers)}")
                if current_viewers:
                    user_list = list(current_viewers.keys())[:3]
                    self.add_log(f"Usuarios actuales: {', '.join(user_list)}{'...' if len(current_viewers) > 3 else ''}")
                self.add_log(f"Historial total: {len(all_history)} entradas")
                
            except Exception as e:
                self.add_log(f'❌ Error en monitor_loop: {e}')
                time.sleep(5)
    

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
                padding: 5px;
            }
            
            .container {
                max-width: 280px;
                margin: 0 auto;
            }
            
            .time-header {
                text-align: center;
                margin-bottom: 5px;
            }
            
            .current-time {
                font-size: 0.8em;
                color: #ffaaaa;
                background: rgba(139, 0, 0, 0.2);
                padding: 3px 8px;
                border-radius: 4px;
                border: 1px solid #8b0000;
                display: inline-block;
                font-weight: 500;
            }
            
            .header {
                text-align: center;
                margin-top: 5px;
                background: rgba(139, 0, 0, 0.2);
                padding: 4px;
                border-radius: 4px;
                border: 1px solid #8b0000;
            }
            
            .header h1 {
                font-size: 0.85em;
                color: #ff4444;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
                margin-bottom: 2px;
            }
            
            .header h2 {
                color: #ff6666;
                margin-bottom: 0;
                font-size: 0.7em;
            }
            
            .stats-grid {
                display: flex;
                justify-content: center;
                margin-bottom: 6px;
            }
            
            .stat-card {
                background: linear-gradient(145deg, #2a1a1a, #1a1a1a);
                padding: 6px 12px;
                border-radius: 6px;
                text-align: center;
                border: 1px solid #8b0000;
                box-shadow: 0 2px 8px rgba(139, 0, 0, 0.2);
            }
            
            .stat-number {
                font-size: 1.4em;
                font-weight: bold;
                color: #ff4444;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
                margin-bottom: 1px;
            }
            
            .stat-label {
                color: #ffaaaa;
                font-size: 0.75em;
                font-weight: 500;
            }
            
            .panels-grid {
                display: flex;
                flex-direction: column;
                gap: 4px;
                margin-bottom: 8px;
            }
            
            .panel {
                background: linear-gradient(145deg, #2a1a1a, #1a1a1a);
                border-radius: 5px;
                border: 1px solid #8b0000;
                overflow: hidden;
                box-shadow: 0 2px 6px rgba(139, 0, 0, 0.2);
            }
            
            .panel-header {
                background: linear-gradient(90deg, #8b0000, #cc0000);
                padding: 3px 8px;
                text-align: center;
                font-size: 0.8em;
                font-weight: bold;
                color: white;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
            }
            
            .panel-content {
                max-height: 80px;
                overflow-y: auto;
                padding: 4px;
            }
            
            .user-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 2px 6px;
                margin: 1px 0;
                background: rgba(139, 0, 0, 0.1);
                border-radius: 4px;
                border-left: 2px solid #ff4444;
                transition: all 0.2s ease;
            }
            
            .user-item:hover {
                background: rgba(139, 0, 0, 0.2);
            }
            
            .user-name {
                font-weight: bold;
                color: #ff6666;
                font-size: 0.75em;
            }
            
            .user-time {
                color: #ffaaaa;
                font-size: 0.6em;
            }
            
            .user-duration {
                color: #ff8888;
                font-weight: 600;
                font-size: 0.6em;
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
                padding: 4px;
                background: rgba(139, 0, 0, 0.1);
                border-radius: 4px;
                border: 1px dashed #8b0000;
                font-size: 0.7em;
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
                        <div class="empty-message">En espera de usuarios</div>
                    </div>
                </div>
                
                <div class="panel">
                    <div class="panel-header">🚪 Salieron Recientemente</div>
                    <div class="panel-content scrollbar-custom" id="salieron-list">
                        <div class="empty-message">En espera de usuarios</div>
                    </div>
                </div>
                
                <div class="panel">
                    <div class="panel-header">📊 Historial Completo</div>
                    <div class="panel-content scrollbar-custom" id="historial-list">
                        <div class="empty-message">Aún no hay historial</div>
                    </div>
                </div>
            </div>
            
            <div class="panel">
                <div class="panel-header">📋 Logs del Sistema</div>
                <div class="panel-content scrollbar-custom" id="logs-list">
                    <div class="empty-message">Cargando logs...</div>
                </div>
            </div>
            
            <div class="header">
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
                            list.innerHTML = '<div class="empty-message">En espera de usuarios</div>';
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
                            list.innerHTML = '<div class="empty-message">En espera de usuarios</div>';
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
                            list.innerHTML = '<div class="empty-message">Aún no hay historial</div>';
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
                             } else if (entry.action === 'detectado por follow') {
                                 actionText = `Detectado por follow: ${entry.join_time}`;
                                 icon = '👥';
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
            
            function updateLogs() {
                fetch('/api/logs')
                    .then(response => response.json())
                    .then(data => {
                        const list = document.getElementById('logs-list');
                        list.innerHTML = '';
                        
                        if (data.logs.length === 0) {
                            list.innerHTML = '<div class="empty-message">No hay logs disponibles</div>';
                            return;
                        }
                        
                        data.logs.slice(-15).reverse().forEach(log => {
                            const item = document.createElement('div');
                            item.className = 'user-item';
                            item.style.fontSize = '0.7em';
                            item.style.padding = '2px 4px';
                            item.innerHTML = `<div style="color: #ffaaaa; font-family: monospace;">${log}</div>`;
                            list.appendChild(item);
                        });
                    });
            }
            
             // Actualizar cada 5 segundos
             setInterval(updateTime, 1000);
             setInterval(updateStats, 5000);  // Estadísticas cada 5 segundos
             setInterval(updateViendo, 5000); // Viendo cada 5 segundos
             setInterval(updateSalieron, 5000); // Salieron cada 5 segundos
             setInterval(updateHistorial, 5000); // Historial cada 5 segundos
             setInterval(updateLogs, 5000); // Logs cada 5 segundos
            
            // Cargar datos iniciales
            updateTime();
            updateStats();
            updateViendo();
            updateSalieron();
            updateHistorial();
            updateLogs();
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

@app.route('/api/logs')
def get_logs():
    """Obtiene los logs del tracker"""
    return jsonify({
        'logs': tracker.logs,
        'count': len(tracker.logs),
        'timestamp': get_santiago_time()
    })

@app.route('/api/debug')
def debug_endpoint():
    """Endpoint de debugging para diagnosticar problemas"""
    try:
        # Obtener datos en tiempo real
        chatters = tracker.get_chatters() if tracker.channel_id else []
        follows = tracker.get_recent_follows() if tracker.channel_id else []
        stream_info = tracker.get_stream_info() if tracker.channel_id else {'is_live': False}
        
        return jsonify({
            'debug_info': {
                'tracker_running': tracker.running,
                'has_token': bool(tracker.token),
                'channel_id': tracker.channel_id,
                'channel_name': tracker.channel_name,
                'client_secret_configured': bool(tracker.client_secret)
            },
            'current_data': {
                'chatters_count': len(chatters),
                'chatters_list': chatters[:10],  # Primeros 10
                'follows_count': len(follows),
                'follows_list': [f['from_name'] for f in follows[:5]],  # Primeros 5
                'stream_live': stream_info.get('is_live', False),
                'viewer_count': stream_info.get('viewer_count', 0)
            },
            'tracker_state': {
                'current_viewers': len(current_viewers),
                'current_viewers_list': list(current_viewers.keys()),
                'left_viewers': len(left_viewers),
                'total_history': len(all_history)
            },
            'logs_count': len(tracker.logs),
            'recent_logs': tracker.logs[-5:] if tracker.logs else [],
            'timestamp': get_santiago_time()
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'timestamp': get_santiago_time()
        })

# Crear instancia del tracker
tracker = TwitchTracker()

if __name__ == '__main__':
    # Iniciar el tracker
    tracker.start()
    
    # Iniciar el servidor Flask
    port = int(os.getenv('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False)
