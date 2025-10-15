#!/usr/bin/env python3
"""
Script para probar la conexión IRC de Twitch
"""

import socket
import time
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def test_irc_connection():
    """Prueba la conexión IRC básica"""
    
    # Configuración
    oauth_token = os.getenv('TWITCH_OAUTH', '')
    username = 'blackcraneo'
    channel = 'blackcraneo'
    
    if not oauth_token:
        print("❌ ERROR: TWITCH_OAUTH no configurado")
        print("Configura la variable TWITCH_OAUTH en tu .env")
        return False
    
    print(f"🔗 Probando conexión IRC...")
    print(f"👤 Usuario: {username}")
    print(f"📺 Canal: {channel}")
    print(f"🔑 OAuth: {'***' if oauth_token else 'NO CONFIGURADO'}")
    
    try:
        # Conectar a IRC
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('irc.chat.twitch.tv', 6667))
        print("✅ Conectado al servidor IRC")
        
        # Autenticación
        sock.send(f'PASS {oauth_token}\r\n'.encode('utf-8'))
        sock.send(f'NICK {username}\r\n'.encode('utf-8'))
        sock.send(f'JOIN #{channel}\r\n'.encode('utf-8'))
        print("✅ Comandos de autenticación enviados")
        
        # Leer respuestas
        for i in range(10):
            data = sock.recv(1024).decode('utf-8')
            print(f"📨 Respuesta {i+1}: {data.strip()}")
            
            if 'Welcome' in data:
                print("✅ Autenticación exitosa!")
                break
            elif 'authentication failed' in data.lower():
                print("❌ Error de autenticación")
                return False
                
            time.sleep(0.5)
        
        # Enviar PING para mantener conexión
        sock.send('PING :tmi.twitch.tv\r\n'.encode('utf-8'))
        print("✅ PING enviado")
        
        # Cerrar conexión
        sock.close()
        print("✅ Conexión cerrada correctamente")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en conexión IRC: {e}")
        return False

if __name__ == '__main__':
    print("=== PRUEBA DE CONEXIÓN IRC TWITCH ===")
    success = test_irc_connection()
    
    if success:
        print("\n🎉 ¡Conexión IRC exitosa!")
        print("El tracker debería funcionar correctamente.")
    else:
        print("\n💥 Conexión IRC falló")
        print("Verifica tu configuración de OAuth.")
