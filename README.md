# 🎮 Twitch Viewer Tracker - Blackcraneo

Sistema de rastreo de espectadores en tiempo real para tu canal de Twitch con diseño elegante en rojo carmesí y negro.

## ✨ Características

- 📊 **Tracking en tiempo real** de usuarios que entran y salen del chat
- 🕐 **Hora local de Santiago, Chile** (CLT)
- ⏱️ **Cálculo automático** del tiempo que permanecen en el canal
- 🎨 **Dashboard elegante** con colores rojo carmesí y negro
- 📱 **API REST** para integración con otras aplicaciones
- 🔄 **Actualización automática** sin parpadeos ni conflictos

## 📊 Paneles del Dashboard

### **1. Estadísticas Generales**
- **Espectadores**: Número total de usuarios viendo
- **Viendo Ahora**: Usuarios actualmente en el chat
- **Salieron**: Usuarios que han salido del stream
- **Total Historial**: Total de eventos registrados

### **2. Panel "Viendo Ahora"**
- Lista de usuarios actualmente en el chat
- Hora exacta de entrada
- Indicador visual en tiempo real

### **3. Panel "Salieron Recientemente"**
- Últimos 10 usuarios que salieron
- Hora de salida
- Tiempo total que estuvieron en el stream

### **4. Panel "Historial Completo"**
- Registro completo de entradas y salidas
- Funciona incluso cuando el stream está offline
- Últimos 20 eventos con detalles completos

## 🚀 Deploy en Railway

### **Configuración Automática**
Railway detectará automáticamente que es un proyecto Python y usará las variables que ya tienes configuradas:

- `TWITCH_OAUTH`: sdbw6mijgytm5bfcwhzq3uk5orn2j5
- `TWITCH_CLIENT_ID`: kce866utqoafieyfeto8ef3z30ries
- `TWITCH_CLIENT_SECRET`: sdbw6mijgytm5bfcwhzq3uk5orn2j5

### **Pasos para Deploy**
1. Sube el código a GitHub
2. Conecta con Railway
3. Railway detectará automáticamente las dependencias
4. ¡Listo! Tu aplicación estará funcionando

## 📋 Instalación Local

### **Requisitos**
- Python 3.8 o superior

### **Pasos**
1. **Clonar el repositorio**
```bash
git clone <tu-repositorio>
cd twitch-viewer-tracker
```

2. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

3. **Ejecutar**
```bash
python app.py
```

## 🌐 Endpoints de la API

- `GET /` - Dashboard principal
- `GET /api/stats` - Estadísticas generales
- `GET /api/viendo` - Usuarios viendo actualmente
- `GET /api/salieron` - Usuarios que salieron
- `GET /api/historial` - Historial completo

## 🛠️ Tecnologías

- **Python 3.11**: Lenguaje principal
- **Flask**: Framework web ligero
- **TwitchIO**: Cliente oficial de Twitch
- **Pytz**: Manejo de zonas horarias
- **Gunicorn**: Servidor WSGI para producción

## 🎨 Diseño

- **Colores**: Rojo carmesí (#8B0000) y negro (#1A1A1A)
- **Gradientes**: Efectos visuales elegantes
- **Responsive**: Funciona en móviles y desktop
- **Animaciones**: Transiciones suaves y efectos hover
- **Scrollbars**: Personalizados con el tema

## 📝 Licencia

MIT License

---

**Desarrollado con ❤️ para Blackcraneo**
