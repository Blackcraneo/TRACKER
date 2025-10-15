import os
import json
import socket
import threading
import time
import requests
from datetime import datetime
from typing import Dict, List
import pytz
from flask import Flask, jsonify, render_template_string
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

class TwitchTracker:
    def __init__(self):
        self.channel_name = 'blackcraneo'
        self.username = 'blackcraneo'  # Tu nombre de usuario
        self.oauth_token = os.getenv('TWITCH_OAUTH', '')
        self.socket = None
        self.running = False
        self.logs = []
        self.max_logs = 50
        self.connected_users = set()  # Usuarios conectados al chat
        self.user_join_times = {}  # Tiempo de entrada de cada usuario
        self.connection_attempts = 0  # Contador de intentos de conexión
        self.last_connection_time = 0  # Última conexión exitosa
        self.connection_start_time = 0  # Tiempo de inicio de conexión actual
        self.max_connection_duration = 480  # 8 minutos máximo por conexión
        self.heartbeat_interval = 15  # PING cada 15 segundos
    
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
    
    def connect_to_chat(self):
        """Conecta al chat de Twitch usando IRC con configuración ULTRA persistente"""
        try:
            if not self.oauth_token:
                self.add_log('ERROR: TWITCH_OAUTH no configurado')
                return False
            
            self.connection_attempts += 1
            
            # Cerrar conexión anterior si existe
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            
            # Crear socket con configuración ULTRA persistente
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Configuración ULTRA agresiva para Railway
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)   # 10 segundos
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)   # 5 segundos
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 2)     # 2 intentos
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            
            # Timeout de conexión
            self.socket.settimeout(20)
            
            # Conectar
            self.socket.connect(('irc.chat.twitch.tv', 6667))
            
            # Autenticación RÁPIDA
            self.send_command(f'PASS oauth:{self.oauth_token}')
            time.sleep(0.1)  # Delay mínimo
            self.send_command(f'NICK {self.username}')
            time.sleep(0.1)  # Delay mínimo
            self.send_command(f'JOIN #{self.channel_name}')
            
            # Confirmación inmediata
            time.sleep(0.5)
            
            # PING inmediato
            self.send_command('PING :tmi.twitch.tv')
            
            self.last_connection_time = time.time()
            self.connection_start_time = time.time()
            self.add_log(f'✅ Conectado al IRC (intento #{self.connection_attempts}) - Duración máxima: {self.max_connection_duration}s')
            return True
            
        except Exception as e:
            self.add_log(f'❌ ERROR conectando al chat: {e} (intento #{self.connection_attempts})')
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            return False
    
    def send_command(self, command):
        """Envía un comando al IRC de forma segura"""
        try:
            if self.socket:
                self.socket.send(f'{command}\r\n'.encode('utf-8'))
                return True
        except Exception as e:
            self.add_log(f'❌ Error enviando comando: {e}')
            self.socket = None  # Marcar para reconexión
        return False
    
    def parse_message(self, message):
        """Parsea mensajes IRC de Twitch"""
        try:
            if 'PRIVMSG' in message:
                # Extraer información del usuario
                parts = message.split('PRIVMSG')
                if len(parts) >= 2:
                    user_part = parts[0].split('!')[0].replace(':', '')
                    username = user_part.split('@')[0] if '@' in user_part else user_part
                    
                    # Extraer mensaje
                    msg_part = parts[1].split(':', 1)
                    if len(msg_part) >= 2:
                        chat_message = msg_part[1].strip()
                        return username, chat_message
            
            elif 'JOIN' in message:
                # Usuario se unió al chat
                user_part = message.split('!')[0].replace(':', '')
                username = user_part.split('@')[0] if '@' in user_part else user_part
                return username, 'JOIN'
                
            elif 'PART' in message:
                # Usuario salió del chat
                user_part = message.split('!')[0].replace(':', '')
                username = user_part.split('@')[0] if '@' in user_part else user_part
                return username, 'PART'
                
        except Exception as e:
            self.add_log(f'ERROR parseando mensaje: {e}')
        
        return None, None
    
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
        """Inicia el tracker IRC"""
        self.add_log('🚀 Iniciando Twitch IRC Tracker...')
        self.add_log(f'📺 Canal: {self.channel_name}')
        self.add_log(f'👤 Usuario: {self.username}')
        self.add_log(f'🔑 OAuth configurado: {bool(self.oauth_token)}')
        
        # Conectar al chat
        if not self.connect_to_chat():
            self.add_log('❌ Error: No se pudo conectar al chat')
            return
        
        self.running = True
        
        # Iniciar monitoreo IRC
        threading.Thread(target=self.irc_loop, daemon=True).start()
        threading.Thread(target=self.monitor_loop, daemon=True).start()
        self.add_log('🎯 Twitch IRC Tracker iniciado correctamente')
    
    def irc_loop(self):
        """Loop IRC con reconexión preventiva + heartbeat agresivo"""
        self.add_log('🔄 Iniciando IRC con reconexión preventiva...')
        
        last_ping = time.time()
        last_activity = time.time()
        
        while self.running:
            try:
                current_time = time.time()
                
                # Verificar si necesitamos reconexión preventiva
                if self.socket and self.connection_start_time:
                    connection_duration = current_time - self.connection_start_time
                    if connection_duration >= self.max_connection_duration:
                        self.add_log(f'🔄 Reconexión preventiva (conectado {int(connection_duration)}s)')
                        self.socket = None  # Forzar reconexión
                
                # Verificar conexión
                if not self.socket:
                    self.add_log('🔄 Reconectando al IRC...')
                    if not self.connect_to_chat():
                        self.add_log('❌ Fallo de conexión - reintentando en 2s...')
                        time.sleep(2)  # Espera corta para evitar spam
                        continue
                    else:
                        last_activity = current_time
                        last_ping = current_time
                
                # Timeout para detectar problemas
                self.socket.settimeout(10)
                
                # Recibir datos
                data = self.socket.recv(1024).decode('utf-8')
                
                if not data:
                    self.add_log('❌ Conexión IRC perdida - reconectando...')
                    self.socket = None
                    continue
                
                last_activity = current_time
                
                # Procesar cada línea
                for line in data.split('\r\n'):
                    if line.strip():
                        self.process_irc_message(line.strip())
                        
                # Heartbeat agresivo cada 15 segundos
                if current_time - last_ping >= self.heartbeat_interval:
                    self.add_log(f'💓 Heartbeat (cada {self.heartbeat_interval}s)')
                    if not self.send_command('PING :tmi.twitch.tv'):
                        self.socket = None
                    last_ping = current_time
                        
            except socket.timeout:
                # Timeout - verificar si necesitamos heartbeat
                current_time = time.time()
                if current_time - last_ping >= self.heartbeat_interval:
                    self.add_log('⏰ Timeout - enviando heartbeat')
                    if not self.send_command('PING :tmi.twitch.tv'):
                        self.socket = None
                continue
                
            except Exception as e:
                self.add_log(f'❌ Error en irc_loop: {e} - reconectando...')
                self.socket = None
                time.sleep(2)
    
    def process_irc_message(self, message):
        """Procesa un mensaje IRC"""
        try:
            # PING/PONG para mantener conexión
            if message.startswith('PING'):
                self.send_command('PONG :tmi.twitch.tv')
                return
            
            # Parsear mensaje
            username, action = self.parse_message(message)
            
            if username and action:
                # Excluir bots
                if username.lower() in [bot.lower() for bot in EXCLUDED_BOTS]:
                    return
                
                if action == 'JOIN':
                    self.handle_user_join(username)
                elif action == 'PART':
                    self.handle_user_part(username)
                elif isinstance(action, str) and action != 'JOIN' and action != 'PART':
                    # Mensaje de chat
                    self.handle_user_message(username, action)
                    
        except Exception as e:
            self.add_log(f'❌ Error procesando mensaje IRC: {e}')
    
    def handle_user_join(self, username):
        """Maneja cuando un usuario se une al chat"""
        if username not in self.connected_users:
            self.connected_users.add(username)
            self.user_join_times[username] = get_santiago_time()
            
            # Agregar a current_viewers si no está
            if username not in current_viewers:
                user_data = {
                    'username': username,
                    'join_time': f"{get_santiago_time()} (IRC detectado)",
                    'leave_time': None,
                    'duration': None,
                    'status': 'viendo'
                }
                
                current_viewers[username] = user_data
                
                history_entry = {
                    **user_data,
                    'action': 'detectado por IRC'
                }
                all_history.append(history_entry)
                
                self.add_log(f'👥 {username} detectado por IRC (se unió al chat)')
    
    def handle_user_part(self, username):
        """Maneja cuando un usuario sale del chat"""
        if username in self.connected_users:
            self.connected_users.remove(username)
            if username in self.user_join_times:
                del self.user_join_times[username]
            
            # Marcar como que salió
            self.mark_user_left(username)
    
    def handle_user_message(self, username, message):
        """Maneja cuando un usuario escribe en el chat"""
        # Si no está en connected_users, agregarlo
        if username not in self.connected_users:
            self.connected_users.add(username)
            self.user_join_times[username] = get_santiago_time()
        
        # Asegurar que esté en current_viewers
        if username not in current_viewers:
            user_data = {
                'username': username,
                'join_time': f"{get_santiago_time()} (chat detectado)",
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
    
    
    
    
    
    def monitor_loop(self):
        """Loop de monitoreo con reconexión preventiva"""
        self.add_log('🔄 Iniciando monitoreo con reconexión preventiva...')
        
        while self.running:
            try:
                # Estadísticas cada 60 segundos
                time.sleep(60)
                
                if self.running:
                    # Estado IRC
                    irc_status = "✅ CONECTADO" if self.socket else "❌ DESCONECTADO"
                    current_time = time.time()
                    
                    if self.connection_start_time:
                        connection_duration = current_time - self.connection_start_time
                        time_until_reconnect = max(0, self.max_connection_duration - connection_duration)
                        self.add_log(f'📊 IRC: {irc_status} (conectado {int(connection_duration)}s)')
                        self.add_log(f'⏰ Próxima reconexión en: {int(time_until_reconnect)}s')
                    else:
                        self.add_log(f'📊 IRC: {irc_status}')
                    
                    self.add_log(f'📈 Usuarios detectados: {len(current_viewers)}')
                    self.add_log(f'📋 Historial total: {len(all_history)} entradas')
                    self.add_log(f'🔄 Intentos de conexión: {self.connection_attempts}')
                    self.add_log(f'💓 Heartbeat: cada {self.heartbeat_interval}s')
                    
                    # Mostrar usuarios recientes
                    if len(current_viewers) > 0:
                        recent_users = list(current_viewers.keys())[-3:]
                        self.add_log(f'👥 Usuarios recientes: {", ".join(recent_users)}')
                    else:
                        self.add_log('💤 Esperando usuarios en IRC...')
                
            except Exception as e:
                self.add_log(f'❌ Error en monitor_loop: {e}')
                time.sleep(30)
    

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

@app.route('/api/status')
def status_endpoint():
    """Endpoint para verificar el estado del sistema IRC"""
    try:
        return jsonify({
            'status': 'ok',
            'tracker_running': tracker.running,
            'irc_connected': bool(tracker.socket),
            'oauth_configured': bool(tracker.oauth_token),
            'channel_name': tracker.channel_name,
            'connected_users_count': len(tracker.connected_users),
            'current_viewers_count': len(current_viewers),
            'total_history_count': len(all_history),
            'connection_attempts': tracker.connection_attempts,
            'connection_duration': int(time.time() - tracker.connection_start_time) if tracker.connection_start_time else 0,
            'max_connection_duration': tracker.max_connection_duration,
            'heartbeat_interval': tracker.heartbeat_interval,
            'time_until_reconnect': max(0, tracker.max_connection_duration - (time.time() - tracker.connection_start_time)) if tracker.connection_start_time else 0,
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
    """Inicializa el tracker IRC de forma segura"""
    try:
        print("=== INICIANDO TWITCH IRC TRACKER ===")
        tracker.add_log("🚀 Iniciando aplicación IRC...")
        tracker.add_log(f"📺 Canal: {tracker.channel_name}")
        tracker.add_log(f"👤 Usuario: {tracker.username}")
        tracker.add_log(f"🔑 OAuth configurado: {bool(tracker.oauth_token)}")
        tracker.add_log(f"🔑 OAuth valor: {'***' if tracker.oauth_token else 'NO CONFIGURADO'}")
        
        # Verificar variables de entorno
        oauth_env = os.getenv('TWITCH_OAUTH')
        tracker.add_log(f"📋 TWITCH_OAUTH desde env: {'***' if oauth_env else 'NO CONFIGURADO'}")
        
        # Intentar iniciar el tracker
        tracker.add_log("🔄 Intentando iniciar tracker IRC...")
        tracker.start()
        
        if tracker.running:
            tracker.add_log("✅ Tracker IRC iniciado correctamente")
        else:
            tracker.add_log("❌ Tracker IRC no se pudo iniciar")
            
    except Exception as e:
        print(f"ERROR inicializando tracker IRC: {e}")
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
