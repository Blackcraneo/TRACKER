# 🎮 Twitch IRC Tracker - Configuración

## ✅ Sistema Implementado

El tracker ahora usa **IRC chat connection** para detectar usuarios reales que están viendo tu stream, sin necesidad de que escriban en el chat.

## 🔧 Configuración Requerida

### 1. OAuth Token para IRC

Necesitas obtener un **OAuth Token** para conectar al chat IRC:

1. Ve a: https://twitchtokengenerator.com/
2. Selecciona **"Chat Bot"** 
3. Autoriza la aplicación
4. Copia el token que aparece

### 2. Variable de Entorno en Railway

En Railway, agrega esta variable:

```
TWITCH_OAUTH=oauth:tu_token_aqui
```

**Importante**: El token debe empezar con `oauth:` (no solo el token)

## 🚀 Cómo Funciona

### Detección de Usuarios
- **JOIN**: Detecta cuando alguien se une al chat
- **PRIVMSG**: Detecta cuando alguien escribe (y los agrega si no estaban)
- **PART**: Detecta cuando alguien sale del chat

### Ventajas del IRC
- ✅ Detecta usuarios que **solo ven** (no necesitan escribir)
- ✅ Detección en tiempo real
- ✅ No requiere permisos de moderador
- ✅ Funciona 24/7 sin renovación de tokens
- ✅ Más preciso que APIs

## 📊 Endpoints Disponibles

- `/api/status` - Estado del sistema IRC
- `/api/debug` - Información detallada de usuarios conectados
- `/api/logs` - Logs del sistema
- `/api/viendo` - Usuarios actualmente viendo
- `/api/salieron` - Usuarios que salieron
- `/api/historial` - Historial completo

## 🔍 Verificación

Para verificar que funciona:

1. Conecta al chat de tu canal
2. Ve a `/api/status` - debe mostrar `irc_connected: true`
3. Ve a `/api/debug` - debe mostrar usuarios en `connected_users_list`

## 🎯 Próximos Pasos

1. **Configura TWITCH_OAUTH** en Railway
2. **Redeploy** la aplicación
3. **Verifica** que se conecte al IRC
4. **Prueba** entrando/saliendo del chat

¡El sistema IRC es mucho más efectivo para detectar usuarios reales! 🎉
