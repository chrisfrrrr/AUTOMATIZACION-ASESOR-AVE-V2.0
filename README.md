# AVE Canvas Analytics Pro 2.0

Aplicación profesional en Streamlit para automatizar el seguimiento académico de estudiantes en Canvas.

## Funciones principales

- Conexión a Canvas mediante URL institucional y token.
- Selección de curso y sección.
- Extracción de estudiantes, última actividad, tiempo total, tareas y entregas.
- Cálculo de riesgo de desconexión:
  - Bajo: 0 a 24 horas sin actividad.
  - Medio: más de 24 y hasta 72 horas.
  - Alto: más de 72 horas o sin registro.
- Cálculo de cumplimiento de meta mínima diaria de conexión.
- Índice Integral de Riesgo AVE.
- Segmentación automática:
  - Activo estable.
  - Observación preventiva.
  - Baja conexión.
  - Bajo avance.
  - Entrega vencida.
  - Sin registro de actividad.
  - Intervención inmediata.
- Dashboard ejecutivo con gráficas.
- Centro de alerta temprana.
- Bitácora de seguimiento del asesor.
- Historial local en SQLite.
- Mensajes inteligentes por tipo de caso.
- Exportación a Excel Pro.
- Exportación a PDF ejecutivo Pro.
- Ficha individual PDF por estudiante.

## Instalación local

```bash
pip install -r requirements.txt
streamlit run app.py
```

En Windows también puede ejecutarse:

```bat
INICIAR_APP_WINDOWS.bat
```

## Variables recomendadas

Puede crear un archivo `.env` local o usar Secrets en Streamlit Cloud:

```env
CANVAS_URL=https://uvg.instructure.com
CANVAS_TOKEN=pegue_aqui_su_token
```

## Seguridad

El token de Canvas debe protegerse como contraseña. No se recomienda subir tokens a GitHub. Use variables de entorno o Secrets de Streamlit Cloud.

## Desarrollador

Ing. Christian Pocol, Ingeniero Electrónico.
