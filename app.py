import os
import json
import threading
import time
import requests
import sqlite3
from datetime import datetime
from typing import Dict, List, Set
import pytz
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
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

# Clase para manejar la base de datos
class DatabaseManager:
    def __init__(self, db_path='tracker_history.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Inicializa la base de datos y crea las tablas necesarias"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Tabla para historial de usuarios
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL,
                        action TEXT NOT NULL,
                        join_time TEXT,
                        leave_time TEXT,
                        duration TEXT,
                        date_created TEXT NOT NULL,
                        timestamp INTEGER NOT NULL
                    )
                ''')
                
                # Tabla para usuarios actuales
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS current_users (
                        username TEXT PRIMARY KEY,
                        join_time TEXT NOT NULL,
                        last_seen INTEGER NOT NULL
                    )
                ''')
                
                conn.commit()
                print("✅ Base de datos inicializada correctamente")
                
        except Exception as e:
            print(f"❌ Error inicializando base de datos: {e}")
    
    def add_user_entry(self, username, action, join_time=None, leave_time=None, duration=None):
        """Agrega una entrada al historial"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                timestamp = int(time.time())
                date_created = datetime.now(SANTIAGO_TZ).strftime('%d-%m-%y %H:%M:%S')
                
                cursor.execute('''
                    INSERT INTO user_history (username, action, join_time, leave_time, duration, date_created, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (username, action, join_time, leave_time, duration, date_created, timestamp))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"❌ Error agregando entrada: {e}")
            return False
    
    def get_user_history(self, username=None, date_filter=None, limit=100):
        """Obtiene el historial con filtros opcionales"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM user_history WHERE 1=1"
                params = []
                
                if username:
                    query += " AND username LIKE ?"
                    params.append(f"%{username}%")
                
                if date_filter:
                    query += " AND date_created LIKE ?"
                    params.append(f"%{date_filter}%")
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                # Convertir a lista de diccionarios
                history = []
                for row in results:
                    history.append({
                        'id': row[0],
                        'username': row[1],
                        'action': row[2],
                        'join_time': row[3],
                        'leave_time': row[4],
                        'duration': row[5],
                        'date_created': row[6],
                        'timestamp': row[7]
                    })
                
                return history
                
        except Exception as e:
            print(f"❌ Error obteniendo historial: {e}")
            return []
    
    def update_current_user(self, username, join_time):
        """Actualiza o agrega un usuario actual"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                timestamp = int(time.time())
                
                cursor.execute('''
                    INSERT OR REPLACE INTO current_users (username, join_time, last_seen)
                    VALUES (?, ?, ?)
                ''', (username, join_time, timestamp))
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"❌ Error actualizando usuario actual: {e}")
        return False
    
    def remove_current_user(self, username):
        """Remueve un usuario de la lista actual"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM current_users WHERE username = ?', (username,))
                conn.commit()
                return True
                
        except Exception as e:
            print(f"❌ Error removiendo usuario actual: {e}")
            return False
    
    def get_current_users(self):
        """Obtiene la lista de usuarios actuales"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('SELECT username, join_time, last_seen FROM current_users ORDER BY last_seen DESC')
                results = cursor.fetchall()
                
                users = []
                for row in results:
                    users.append({
                        'username': row[0],
                        'join_time': row[1],
                        'last_seen': row[2]
                    })
                
                return users
                
        except Exception as e:
            print(f"❌ Error obteniendo usuarios actuales: {e}")
        return []
    
class TwitchTracker:
    def __init__(self):
        self.channel_name = 'blackcraneo'
        self.oauth_token = os.getenv('TWITCH_OAUTH', '')
        self.running = False
        self.logs = []
        self.max_logs = 50
        
        # Base de datos
        self.db = DatabaseManager()
        
        # Estado de usuarios
        self.previous_users = set()  # Usuarios del ciclo anterior
        self.current_users = set()   # Usuarios del ciclo actual
        self.user_join_times = {}    # Tiempo de entrada de cada usuario
        self.user_last_seen = {}     # Última vez que se vio a cada usuario
        
        # Configuración de polling
        self.poll_interval = 10      # Polling cada 10 segundos (más responsivo)
        self.client_id = 'gp762nuuoqcoxypju8c569th9wz7q5'  # Client ID público
        self.rate_limit_remaining = 800  # Límite de requests por minuto
        self.last_rate_limit_reset = time.time()
        
        # Estadísticas
        self.total_polls = 0
        self.successful_polls = 0
        self.last_poll_time = 0
    
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
    
    def get_api_headers(self):
        """Obtiene headers para requests a la API de Twitch"""
        return {
            'Authorization': f'Bearer {self.oauth_token.replace("oauth:", "")}',
            'Client-Id': self.client_id
        }
    
    def check_rate_limit(self):
        """Verifica y actualiza rate limiting"""
        current_time = time.time()
        
        # Reset rate limit cada minuto
        if current_time - self.last_rate_limit_reset >= 60:
            self.rate_limit_remaining = 800
            self.last_rate_limit_reset = current_time
        
        return self.rate_limit_remaining > 0
    
    def get_chatters_from_api(self):
        """Obtiene lista de chatters usando la API de Twitch"""
        try:
            if not self.check_rate_limit():
                self.add_log('⚠️ Rate limit alcanzado, esperando...')
                return set()
            
            headers = self.get_api_headers()
            
            # Obtener ID del canal
            user_response = requests.get(
                f'https://api.twitch.tv/helix/users?login={self.channel_name}',
                headers=headers,
                timeout=10
            )
            
            if user_response.status_code != 200:
                self.add_log(f'❌ Error obteniendo ID del canal: {user_response.status_code}')
                return set()
            
            user_data = user_response.json()
            if not user_data.get('data'):
                self.add_log('❌ Canal no encontrado')
                return set()
            
            channel_id = user_data['data'][0]['id']
            self.rate_limit_remaining -= 1
            
            # Obtener chatters
            chatters_response = requests.get(
                f'https://api.twitch.tv/helix/chat/chatters?broadcaster_id={channel_id}&moderator_id={channel_id}',
                headers=headers,
                timeout=10
            )
            
            if chatters_response.status_code == 200:
                chatters_data = chatters_response.json()
                chatters = set()
                
                for chatter in chatters_data.get('data', []):
                    username = chatter.get('user_name', '')
                    if username and username.lower() not in [bot.lower() for bot in EXCLUDED_BOTS]:
                        chatters.add(username)
                
                self.rate_limit_remaining -= 1
                self.add_log(f'📊 API: {len(chatters)} chatters detectados - Poll #{self.total_polls}')
                return chatters
                
            elif chatters_response.status_code == 403:
                self.add_log('⚠️ Sin permisos de moderador - usando información del stream')
                return self.get_stream_viewers_fallback()
            else:
                self.add_log(f'❌ Error obteniendo chatters: {chatters_response.status_code}')
                return set()
                
        except Exception as e:
            self.add_log(f'❌ Error en get_chatters_from_api: {e}')
            return set()
    
    def get_stream_viewers_fallback(self):
        """Fallback cuando no hay permisos de moderador"""
        try:
            headers = self.get_api_headers()
            
            response = requests.get(
                f'https://api.twitch.tv/helix/streams?user_login={self.channel_name}',
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    stream_data = data['data'][0]
                    viewer_count = stream_data.get('viewer_count', 0)
                    
                    if viewer_count > 0:
                        # Simular algunos usuarios basado en viewer count
                        simulated_users = set()
                        for i in range(min(viewer_count, 10)):  # Máximo 10 usuarios simulados
                            simulated_users.add(f'viewer_{i+1}')
                        
                        self.add_log(f'📊 Fallback: Stream con {viewer_count} espectadores')
                        return simulated_users
            
            self.rate_limit_remaining -= 1
            return set()
            
        except Exception as e:
            self.add_log(f'❌ Error en fallback: {e}')
            return set()
    
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
            
            # Agregar solo salidas al historial con duración
            self.db.add_user_entry(username, 'salió del stream', user_data['join_time'], leave_time, duration)
            self.db.remove_current_user(username)
            
            left_viewers.append(leave_data)
            
            history_entry = {
                **leave_data,
                'action': 'salió'
            }
            all_history.append(history_entry)
            
            del current_viewers[username]
                        
            self.add_log(f'🚪 {username} salió del stream (Estuvo: {duration}) - Poll #{self.total_polls}')
        
    def start(self):
        """Inicia el tracker con API Polling"""
        self.add_log('🚀 Iniciando Twitch API Tracker...')
        self.add_log(f'📺 Canal: {self.channel_name}')
        self.add_log(f'🔑 OAuth configurado: {bool(self.oauth_token)}')
        self.add_log(f'⏰ Polling cada: {self.poll_interval} segundos')
        
        if not self.oauth_token:
            self.add_log('❌ Error: TWITCH_OAUTH no configurado')
            return
        
        self.running = True
        
        # Iniciar polling
        threading.Thread(target=self.polling_loop, daemon=True).start()
        threading.Thread(target=self.monitor_loop, daemon=True).start()
        self.add_log('🎯 Twitch API Tracker iniciado correctamente')
    
    def polling_loop(self):
        """Loop principal de polling API optimizado"""
        self.add_log('🔄 Iniciando polling API optimizado...')
        
        while self.running:
            try:
                self.total_polls += 1
                self.last_poll_time = time.time()
                
                # Obtener usuarios actuales
                current_users = self.get_chatters_from_api()
                
                if current_users is not None:
                    self.successful_polls += 1
                    self.process_user_changes(current_users)
                
                # Esperar antes del próximo polling
                time.sleep(self.poll_interval)
                
            except Exception as e:
                self.add_log(f'❌ Error en polling_loop: {e}')
                time.sleep(self.poll_interval)
    
    def process_user_changes(self, current_users):
        """Procesa cambios en usuarios (entradas y salidas)"""
        try:
            # Detectar usuarios nuevos (entradas)
            new_users = current_users - self.previous_users
            
            for username in new_users:
                if username not in current_viewers:
                    join_time = get_santiago_time()
                    
                    user_data = {
                        'username': username,
                        'join_time': join_time,
                        'leave_time': None,
                        'duration': None,
                        'status': 'viendo'
                    }
                    
                    current_viewers[username] = user_data
                    self.user_join_times[username] = time.time()
                    
                    # Solo actualizar usuario actual (no agregar entrada de entrada al historial)
                    self.db.update_current_user(username, join_time)
                    
                    # NO agregar entradas al historial - solo salidas
                    # history_entry = {
                    #     **user_data,
                    #     'action': 'entró al stream'
                    # }
                    # all_history.append(history_entry)
                    
                    self.add_log(f'👋 {username} entró al stream - Poll #{self.total_polls}')
            
            # Detectar usuarios que salieron
            left_users = self.previous_users - current_users
            
            for username in left_users:
                if username in current_viewers:
                    self.mark_user_left(username)
            
            # Actualizar estado para próximo ciclo
            self.previous_users = current_users.copy()
            self.current_users = current_users
            
            # Actualizar tiempo de última vista para usuarios activos
            for username in current_users:
                self.user_last_seen[username] = time.time()
                
        except Exception as e:
            self.add_log(f'❌ Error procesando cambios de usuarios: {e}')
    
    
    
    
    
    
    def monitor_loop(self):
        """Loop de monitoreo API polling"""
        self.add_log('🔄 Iniciando monitoreo API polling...')
        
        while self.running:
            try:
                # Estadísticas cada 60 segundos
                time.sleep(60)
                
                if self.running:
                    current_time = time.time()
                    
                    # Estado del polling
                    time_since_last_poll = current_time - self.last_poll_time if self.last_poll_time else 0
                    success_rate = (self.successful_polls / self.total_polls * 100) if self.total_polls > 0 else 0
                    
                    self.add_log(f'📊 API Polling: {self.total_polls} polls totales')
                    self.add_log(f'✅ Tasa de éxito: {success_rate:.1f}%')
                    self.add_log(f'⏰ Último poll: {int(time_since_last_poll)}s atrás')
                    self.add_log(f'🔄 Próximo poll en: {self.poll_interval}s')
                    self.add_log(f'📈 Rate limit restante: {self.rate_limit_remaining}')
                    
                    # Estado de usuarios
                    self.add_log(f'📈 Usuarios actuales: {len(current_viewers)}')
                    self.add_log(f'📋 Historial total: {len(all_history)} entradas')
                    self.add_log(f'👥 Usuarios en chat: {len(self.current_users)}')
                    
                    # Mostrar usuarios recientes
                    if len(current_viewers) > 0:
                        recent_users = list(current_viewers.keys())[-3:]
                        self.add_log(f'👥 Usuarios recientes: {", ".join(recent_users)}')
                    else:
                        self.add_log('💤 Esperando usuarios...')
                
            except Exception as e:
                self.add_log(f'❌ Error en monitor_loop: {e}')
                time.sleep(30)
    

def get_santiago_time() -> str:
    """Obtiene la hora actual en Santiago, Chile"""
    now = datetime.now(SANTIAGO_TZ)
    return now.strftime('%d-%m-%y %H:%M:%S')

def calculate_duration(start_time: str, end_time: str) -> str:
    """Calcula la duración entre dos timestamps"""
    start = datetime.strptime(start_time, '%d-%m-%y %H:%M:%S')
    end = datetime.strptime(end_time, '%d-%m-%y %H:%M:%S')
    
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
                
                <!-- Filtro como panel separado más pequeño -->
                <div class="panel" style="max-height: 80px; margin: 10px 0;">
                    <div class="filters" style="padding: 8px; background: rgba(255, 255, 255, 0.02); border: 1px solid #444; border-radius: 6px;">
                        <div style="display: flex; align-items: center; gap: 8px; justify-content: center;">
                            <input type="text" id="usernameFilter" placeholder="Buscar usuario..." style="padding: 6px 10px; border-radius: 4px; border: 1px solid #666; background: #2a2a2a; color: #fff; font-size: 12px; font-family: 'Segoe UI', Arial, sans-serif; flex: 1; max-width: 250px;">
                            <button onclick="applyFilters()" style="padding: 6px 12px; border-radius: 4px; border: 1px solid #2196F3; background: #2196F3; color: #fff; cursor: pointer; font-size: 12px; font-family: 'Segoe UI', Arial, sans-serif;">🔍</button>
                            <button onclick="clearFilters()" style="padding: 6px 12px; border-radius: 4px; border: 1px solid #666; background: #444; color: #fff; cursor: pointer; font-size: 12px; font-family: 'Segoe UI', Arial, sans-serif;">🗑️</button>
                        </div>
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
                            list.innerHTML = '<div class="empty-message" style="font-size: 12px; padding: 8px; text-align: center; color: #888; font-style: italic;">En espera de usuarios</div>';
                            return;
                        }
                        
                        data.users.slice(-10).reverse().forEach(user => {
                            const item = document.createElement('div');
                            item.className = 'user-item';
                            item.style.padding = '12px';
                            item.style.margin = '8px 0';
                            item.style.background = 'linear-gradient(135deg, #4a1a1a 0%, #6d1b1b 100%)';
                            item.style.borderRadius = '8px';
                            item.style.borderLeft = '4px solid #f44336';
                            item.style.boxShadow = '0 2px 8px rgba(244, 67, 54, 0.3)';
                            item.innerHTML = `
                                <div style="display: flex; align-items: center; justify-content: space-between;">
                                    <span style="color: #f44336; font-weight: bold; font-size: 16px; font-family: 'Segoe UI', Arial, sans-serif;">🚪 ${user.username}</span>
                                    <span style="color: #FFB74D; font-size: 12px; background: rgba(255, 183, 77, 0.2); padding: 4px 8px; border-radius: 12px;">Salió</span>
                                </div>
                                <div style="color: #FFCDD2; font-size: 12px; margin-top: 4px;">Tiempo: ${user.duration || 'N/A'}</div>
                                <div style="color: #B0BEC5; font-size: 11px;">Salió: ${user.leave_time}</div>
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

            function loadHistoryWithFilters(username = '', date = '') {
                const url = `/api/history?username=${encodeURIComponent(username)}&date=${encodeURIComponent(date)}&limit=100`;
                
                fetch(url)
                    .then(response => response.json())
                    .then(data => {
                        const historialList = document.getElementById('historial-list');
                        if (data.history && data.history.length > 0) {
                            historialList.innerHTML = data.history.map(entry => {
                                const duration = entry.duration || '-';
                                
                                return `
                                    <div class="user-item" style="padding: 15px; margin: 10px 0; background: linear-gradient(135deg, #2c1810 0%, #3e2723 100%); border-radius: 10px; border-left: 5px solid #f44336; box-shadow: 0 3px 10px rgba(244, 67, 54, 0.3);">
                                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                                            <span style="color: #f44336; font-weight: bold; font-size: 18px; font-family: 'Segoe UI', Arial, sans-serif;">👤 ${entry.username}</span>
                                            <span style="color: #FFB74D; font-size: 14px; background: rgba(255, 183, 77, 0.2); padding: 4px 10px; border-radius: 15px;">${entry.action}</span>
                                        </div>
                                        <div style="display: flex; justify-content: space-between; color: #B0BEC5; font-size: 13px;">
                                            <span>📅 ${entry.date_created}</span>
                                            <span style="color: #4CAF50; font-weight: bold;">⏱️ ${duration}</span>
                                        </div>
                                    </div>
                                `;
                            }).join('');
                        } else {
                            historialList.innerHTML = '<div class="empty-message">No hay historial disponible</div>';
                        }
                    })
                    .catch(error => console.error('Error cargando historial:', error));
            }

            function applyFilters() {
                const username = document.getElementById('usernameFilter').value;
                // Solo buscar por username (no por fecha ya que solo mostramos salidas)
                loadHistoryWithFilters(username, '');
            }

            function clearFilters() {
                document.getElementById('usernameFilter').value = '';
                loadHistoryWithFilters();
            }

            function loadCurrentUsers() {
                fetch('/api/current-users')
                    .then(response => response.json())
                    .then(data => {
                        const viendoList = document.getElementById('viendo-list');
                        if (data.current_users && data.current_users.length > 0) {
                            viendoList.innerHTML = data.current_users.map(user => 
                                `<div class="user-item" style="padding: 12px; margin: 8px 0; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); border-radius: 8px; border-left: 4px solid #4CAF50; box-shadow: 0 2px 8px rgba(76, 175, 80, 0.3);">
                                    <div style="display: flex; align-items: center; justify-content: space-between;">
                                        <span style="color: #4CAF50; font-weight: bold; font-size: 16px; font-family: 'Segoe UI', Arial, sans-serif;">👤 ${user.username}</span>
                                        <span style="color: #81C784; font-size: 12px; background: rgba(76, 175, 80, 0.2); padding: 4px 8px; border-radius: 12px;">En línea</span>
                                    </div>
                                    <div style="color: #B0BEC5; font-size: 12px; margin-top: 4px;">Entró: ${user.join_time}</div>
                                </div>`
                            ).join('');
                        } else {
                            viendoList.innerHTML = '<div class="empty-message">No hay usuarios actuales</div>';
                        }
                    })
                    .catch(error => console.error('Error cargando usuarios actuales:', error));
            }
            
             // Actualizar cada 3 segundos (más responsivo)
             setInterval(updateTime, 1000);
             setInterval(updateStats, 3000);  // Estadísticas cada 3 segundos
             setInterval(updateViendo, 3000); // Viendo cada 3 segundos
             setInterval(updateSalieron, 3000); // Salieron cada 3 segundos
             setInterval(updateHistorial, 3000); // Historial cada 3 segundos
             setInterval(updateLogs, 3000); // Logs cada 3 segundos
             
             // Cargar datos iniciales
             loadHistoryWithFilters();
             loadCurrentUsers();
            
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

@app.route('/api/status')
def status_endpoint():
    """Endpoint para verificar el estado del sistema API"""
    try:
        return jsonify({
            'status': 'ok',
            'tracker_running': tracker.running,
            'oauth_configured': bool(tracker.oauth_token),
            'channel_name': tracker.channel_name,
            'current_viewers_count': len(current_viewers),
            'total_history_count': len(all_history),
            'poll_interval': tracker.poll_interval,
            'total_polls': tracker.total_polls,
            'successful_polls': tracker.successful_polls,
            'success_rate': (tracker.successful_polls / tracker.total_polls * 100) if tracker.total_polls > 0 else 0,
            'rate_limit_remaining': tracker.rate_limit_remaining,
            'time_since_last_poll': int(time.time() - tracker.last_poll_time) if tracker.last_poll_time else 0,
            'current_chat_users': len(tracker.current_users),
            'logs_count': len(tracker.logs),
            'recent_logs': tracker.logs[-10:] if tracker.logs else [],
            'timestamp': get_santiago_time()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': get_santiago_time()
        })

@app.route('/api/history')
def history_endpoint():
    """Endpoint para obtener historial con filtros"""
    try:
        username_filter = request.args.get('username', '').strip()
        date_filter = request.args.get('date', '').strip()
        limit = int(request.args.get('limit', 100))
        
        # Obtener historial de la base de datos
        history = tracker.db.get_user_history(
            username=username_filter if username_filter else None,
            date_filter=date_filter if date_filter else None,
            limit=limit
        )
        
        return jsonify({
            'status': 'ok',
            'history': history,
            'total_entries': len(history),
            'filters': {
                'username': username_filter,
                'date': date_filter,
                'limit': limit
            },
            'timestamp': get_santiago_time()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': get_santiago_time()
        })

@app.route('/api/current-users')
def current_users_endpoint():
    """Endpoint para obtener usuarios actuales desde la base de datos"""
    try:
        users = tracker.db.get_current_users()
        return jsonify({
            'status': 'ok',
            'current_users': users,
            'total_users': len(users),
            'timestamp': get_santiago_time()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': get_santiago_time()
        })

@app.route('/api/debug')
def debug_endpoint():
    """Endpoint de debugging para diagnosticar problemas IRC"""
    try:
        return jsonify({
            'debug_info': {
                'tracker_running': tracker.running,
                'irc_connected': bool(tracker.socket),
                'oauth_configured': bool(tracker.oauth_token),
                'channel_name': tracker.channel_name,
                'username': tracker.username
            },
            'irc_data': {
                'connected_users_count': len(tracker.connected_users),
                'connected_users_list': list(tracker.connected_users)[:10],  # Primeros 10
                'user_join_times': dict(list(tracker.user_join_times.items())[:5])  # Primeros 5
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

# Función para inicializar el tracker
def initialize_tracker():
    """Inicializa el tracker API de forma segura"""
    try:
        print("=== INICIANDO TWITCH API TRACKER ===")
        tracker.add_log("🚀 Iniciando aplicación API...")
        tracker.add_log(f"📺 Canal: {tracker.channel_name}")
        tracker.add_log(f"🔑 OAuth configurado: {bool(tracker.oauth_token)}")
        tracker.add_log(f"⏰ Polling cada: {tracker.poll_interval} segundos")
        tracker.add_log(f"🔑 OAuth valor: {'***' if tracker.oauth_token else 'NO CONFIGURADO'}")
        
        # Verificar variables de entorno
        oauth_env = os.getenv('TWITCH_OAUTH')
        tracker.add_log(f"📋 TWITCH_OAUTH desde env: {'***' if oauth_env else 'NO CONFIGURADO'}")
        
        # Intentar iniciar el tracker
        tracker.add_log("🔄 Intentando iniciar tracker API...")
        tracker.start()
        
        if tracker.running:
            tracker.add_log("✅ Tracker API iniciado correctamente")
        else:
            tracker.add_log("❌ Tracker API no se pudo iniciar")
            
    except Exception as e:
        print(f"ERROR inicializando tracker API: {e}")
        tracker.add_log(f"❌ Error crítico al inicializar: {e}")
        import traceback
        tracker.add_log(f"❌ Traceback: {traceback.format_exc()}")

# Inicializar el tracker inmediatamente
initialize_tracker()

if __name__ == '__main__':
    # Iniciar el servidor Flask
    port = int(os.getenv('PORT', 3000))
    print(f"🌐 Iniciando servidor en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
