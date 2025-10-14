# 🚀 DEPLOYMENT EN RAILWAY - TWITCH TRACKER

## 📋 PASOS PARA DESPLEGAR

### 1. **Verificar Variables de Entorno en Railway**
Ve a tu proyecto en Railway y verifica que tengas estas variables:

```
TWITCH_CLIENT_SECRET=tu_client_secret_aqui
PORT=3000
```

### 2. **Verificar Logs en Railway**
1. Ve a tu proyecto en Railway
2. Ve a la pestaña "Deployments"
3. Haz clic en el deployment más reciente
4. Ve a la pestaña "Logs"
5. Deberías ver logs como:
   ```
   === INICIANDO TWITCH TRACKER ===
   [2025-10-14 19:30:00] 🚀 Iniciando aplicación...
   [2025-10-14 19:30:01] 📺 Canal: blackcraneo
   [2025-10-14 19:30:02] 🆔 Client ID: mo983ad8zpisqtkezy4q4ky7qvcoc4
   [2025-10-14 19:30:03] 🔑 Client Secret configurado: True
   [2025-10-14 19:30:04] ✅ Tracker iniciado correctamente
   ```

### 3. **Verificar Estado del Sistema**
Ve a estos endpoints para diagnosticar:

- **Estado básico:** `https://tracker-production-d379.up.railway.app/api/status`
- **Debug completo:** `https://tracker-production-d379.up.railway.app/api/debug`
- **Logs:** `https://tracker-production-d379.up.railway.app/api/logs`

### 4. **Diagnóstico de Problemas**

#### ❌ Si no hay logs:
- Verifica que `TWITCH_CLIENT_SECRET` esté configurado
- Revisa los logs de Railway para errores de inicialización

#### ❌ Si hay error 401:
- El Client Secret es incorrecto o expirado
- Genera uno nuevo en Twitch Dev Console

#### ❌ Si hay error 403:
- No tienes permisos de moderador en el canal
- Como owner del canal, deberías tener todos los permisos

### 5. **Verificar Funcionamiento**
1. Ve a tu dashboard: `https://tracker-production-d379.up.railway.app`
2. Deberías ver logs en el panel "Logs del Sistema"
3. Prueba escribiendo en tu chat de Twitch
4. Dale follow a tu canal desde otra cuenta
5. Revisa si apareces en el dashboard

## 🔧 ENDPOINTS DE DIAGNÓSTICO

### `/api/status` - Estado básico
```json
{
  "status": "ok",
  "tracker_running": true,
  "logs_count": 15,
  "has_token": true,
  "channel_id": "123456789",
  "client_secret_configured": true,
  "recent_logs": [...],
  "timestamp": "2025-10-14 19:30:00"
}
```

### `/api/debug` - Información completa
```json
{
  "debug_info": {...},
  "current_data": {...},
  "tracker_state": {...},
  "logs_count": 15,
  "recent_logs": [...]
}
```

### `/api/logs` - Logs del sistema
```json
{
  "logs": [...],
  "count": 15,
  "timestamp": "2025-10-14 19:30:00"
}
```

## 🎯 RESULTADO ESPERADO

Una vez configurado correctamente, deberías ver:

1. **Logs de inicialización** en Railway
2. **Logs del sistema** en el dashboard
3. **Detección de usuarios** cuando escriban en chat
4. **Historial permanente** de usuarios

## 🚨 SI ALGO NO FUNCIONA

1. Verifica los logs de Railway
2. Revisa el endpoint `/api/status`
3. Confirma que `TWITCH_CLIENT_SECRET` esté configurado
4. Verifica que el canal `blackcraneo` existe
