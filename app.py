from __future__ import annotations
import os
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px
from dotenv import load_dotenv

from core.canvas_client import CanvasClient, CanvasAPIError
from core.analytics import normalize_enrollments, normalize_assignments, normalize_submissions, build_student_summary
from core.reports import excel_bytes, pdf_bytes, individual_pdf_bytes, DEV
from core.storage import save_snapshot, load_history, save_followup, load_followups, delete_followup

load_dotenv()
st.set_page_config(page_title='AVE Canvas Analytics Pro 2.0', page_icon='assets/app_icon.ico', layout='wide')

LOGO_AVE = 'assets/logo_ave.png'
LOGO_UVG = 'assets/logo_uvg.png'
RISK_ORDER = ['Bajo','Medio','Alto']

st.markdown('''
<style>
.block-container {padding-top: 1.0rem; max-width: 1500px;}
[data-testid="stSidebar"] {background: linear-gradient(180deg, #F4F7FB 0%, #EEF2F7 100%);} 
.ave-title {font-size: 2.0rem; font-weight: 800; color:#172B85; margin-bottom:0;}
.ave-subtitle {font-size: 1rem; color:#475569; margin-top:0;}
.kpi-card {border:1px solid #E5E7EB;border-radius:18px;padding:16px;background:#fff;box-shadow:0 2px 12px rgba(15,23,42,.06)}
.kpi-label {font-size:.82rem;color:#64748B;}
.kpi-value {font-size:1.65rem;font-weight:800;color:#172B85;}
.section-note {background:#F8FAFC;border-left:5px solid #00A83B;padding:12px;border-radius:12px;color:#334155;}
.footer {font-size:.80rem;color:#64748B;text-align:center;margin-top:20px;}
</style>
''', unsafe_allow_html=True)

for key, default in {'client':None,'courses':[],'analysis':None,'last_user':None}.items():
    if key not in st.session_state: st.session_state[key] = default

with st.sidebar:
    cols = st.columns(2)
    if Path(LOGO_AVE).exists(): cols[0].image(LOGO_AVE, use_container_width=True)
    if Path(LOGO_UVG).exists(): cols[1].image(LOGO_UVG, use_container_width=True)
    st.markdown('### Configuración Canvas')
    st.caption('AVE Canvas Analytics Pro 2.0')
    canvas_url = st.text_input('URL Canvas', value=os.getenv('CANVAS_URL', 'https://uvg.instructure.com'))
    token = st.text_input('Token de acceso', value=os.getenv('CANVAS_TOKEN', ''), type='password')
    generated_by = st.text_input('Nombre de quien genera el informe', value='')
    st.divider()
    st.markdown('### Parámetros académicos')
    daily_hours = st.number_input('Meta mínima diaria de conexión (horas)', min_value=0.5, max_value=12.0, value=2.0, step=0.5)
    course_start = st.date_input('Fecha de inicio del curso', value=date.today())
    only_business = st.checkbox('Calcular meta solo con días hábiles', value=False)
    analysis_date = st.date_input('Fecha de corte del análisis', value=date.today())
    st.divider()
    if st.button('Probar conexión / cargar cursos', use_container_width=True, type='primary'):
        try:
            c = CanvasClient(canvas_url, token)
            me = c.whoami()
            courses = c.courses()
            st.session_state.client = c
            st.session_state.courses = courses
            st.session_state.last_user = me.get('name', 'usuario Canvas')
            st.success(f'Conexión correcta: {st.session_state.last_user}')
        except Exception as e:
            st.error(f'No se pudo conectar: {e}')
    st.caption(f'Desarrollador: {DEV}')

st.markdown('<p class="ave-title">Herramienta profesional de seguimiento académico AVE</p>', unsafe_allow_html=True)
st.markdown('<p class="ave-subtitle">Dashboard ejecutivo, riesgo integral, bitácora de intervención, reportes y automatización desde Canvas.</p>', unsafe_allow_html=True)

if not st.session_state.client:
    st.info('Ingrese la URL de Canvas y el token en la barra lateral. Luego presione “Probar conexión / cargar cursos”.')
    st.stop()

client: CanvasClient = st.session_state.client
courses = st.session_state.courses or []
if not courses:
    st.warning('No se encontraron cursos activos con este token.')
    st.stop()

course_options = {f"{c.get('name','Sin nombre')} | ID {c.get('id')}": c for c in courses}
selected_course_label = st.selectbox('Seleccione curso', list(course_options.keys()))
course = course_options[selected_course_label]
course_id = course.get('id')
course_name = course.get('name','Curso')

try:
    sections = client.sections(course_id)
except Exception:
    sections = []
section_options = {'Todas las secciones': None}
for s in sections:
    section_options[f"{s.get('name','Sección')} | ID {s.get('id')}"] = s
selected_section_label = st.selectbox('Seleccione sección', list(section_options.keys()))
section = section_options[selected_section_label]
section_id = section.get('id') if section else None
section_name = section.get('name') if section else 'Todas las secciones'

colA, colB, colC = st.columns([1.15,1,2.5])
with colA:
    generate = st.button('Generar análisis Pro 2.0', type='primary', use_container_width=True)
with colB:
    clear = st.button('Limpiar resultados', use_container_width=True)
if clear:
    st.session_state.analysis = None
    st.rerun()

if generate:
    progress = st.progress(0, text='Conectando con Canvas...')
    try:
        analysis_dt = datetime.combine(analysis_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        progress.progress(10, text='Extrayendo estudiantes e inscripciones...')
        enrollments = client.enrollments(course_id, section_id)
        enroll_df = normalize_enrollments(enrollments, analysis_dt, course_start, daily_hours, only_business)
        valid_ids = set(enroll_df['user_id'].dropna().astype(int).tolist()) if not enroll_df.empty else set()
        progress.progress(30, text='Extrayendo actividades publicadas...')
        assignments = client.assignments(course_id)
        assign_df = normalize_assignments(assignments)
        progress.progress(50, text='Extrayendo entregas y estados...')
        submissions = client.submissions(course_id)
        sub_df = normalize_submissions(submissions)
        if section_id and valid_ids and not sub_df.empty:
            sub_df = sub_df[sub_df['user_id'].isin(valid_ids)]
        progress.progress(72, text='Calculando índice integral de riesgo AVE...')
        summary = build_student_summary(enroll_df, sub_df, analysis_dt)
        created_at = datetime.now().isoformat(timespec='seconds')
        save_snapshot(summary, course_id, course_name, section_id, section_name, created_at)
        hist = load_history(course_id, section_id)
        followups = load_followups(course_id, section_id)
        st.session_state.analysis = {
            'summary': summary,
            'submissions': sub_df,
            'assignments': assign_df,
            'history': hist,
            'followups': followups,
            'course_name': course_name,
            'course_id': course_id,
            'section_name': section_name,
            'section_id': section_id,
            'analysis_date': str(analysis_date),
            'generated_by': generated_by,
        }
        progress.progress(100, text='Análisis finalizado')
        st.success('Análisis Pro 2.0 generado correctamente.')
    except CanvasAPIError as e:
        st.error(f'Canvas devolvió un error: {e}')
    except Exception as e:
        st.error(f'Ocurrió un error durante el análisis: {e}')

analysis = st.session_state.analysis
if not analysis:
    st.stop()

summary = analysis['summary']
sub_df = analysis['submissions']
assign_df = analysis['assignments']
hist = load_history(course_id, section_id)
followups = load_followups(course_id, section_id)
analysis['history'] = hist
analysis['followups'] = followups

if summary.empty:
    st.warning('No hay estudiantes para analizar.')
    st.stop()

risk_counts = summary['riesgo_integral'].value_counts().to_dict()
pend_tot = int(summary.get('pendientes', pd.Series([0])).sum())
atr_tot = int(summary.get('atrasadas', pd.Series([0])).sum())
avg_adv = float(summary.get('porcentaje_avance', pd.Series([0])).mean())
urgent = int((summary.get('segmento_ave', pd.Series([])) == 'Intervención inmediata').sum())

st.markdown('### Resumen ejecutivo')
kpis = [
    ('Estudiantes', len(summary)),
    ('Riesgo alto', risk_counts.get('Alto', 0)),
    ('Riesgo medio', risk_counts.get('Medio', 0)),
    ('Intervención hoy', urgent),
    ('Pendientes', pend_tot),
    ('Atrasadas', atr_tot),
    ('Avance promedio', f'{avg_adv:.1f}%'),
]
cols = st.columns(len(kpis))
for col, (label, value) in zip(cols, kpis):
    col.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>', unsafe_allow_html=True)

st.divider()

tab_inicio, tab_riesgo, tab_est, tab_ent, tab_hist, tab_bit, tab_msg, tab_rep, tab_conf = st.tabs([
    'Inicio', 'Riesgo académico', 'Estudiantes', 'Entregas', 'Historial', 'Bitácora', 'Mensajes', 'Reportes', 'Configuración'
])

with tab_inicio:
    st.markdown('<div class="section-note"><b>Lectura ejecutiva:</b> el sistema prioriza estudiantes por desconexión, cumplimiento de horas, actividades pendientes, atrasadas, avance y puntaje integral. El objetivo es convertir el rol del asesor en un proceso medible, trazable y accionable.</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        fig = px.histogram(summary, x='riesgo_integral', category_orders={'riesgo_integral': RISK_ORDER}, title='Distribución de riesgo integral')
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        seg = summary['segmento_ave'].value_counts().reset_index()
        seg.columns = ['segmento_ave','cantidad']
        fig = px.bar(seg, x='cantidad', y='segmento_ave', orientation='h', title='Segmentación AVE')
        fig.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
    c3, c4 = st.columns(2)
    with c3:
        fig = px.scatter(summary, x='horas_sin_actividad', y='porcentaje_avance', size='puntaje_riesgo', hover_name='estudiante', color='riesgo_integral', title='Riesgo vs avance')
        st.plotly_chart(fig, use_container_width=True)
    with c4:
        top = summary.sort_values('puntaje_riesgo', ascending=False).head(20)
        fig = px.bar(top, x='puntaje_riesgo', y='estudiante', orientation='h', title='Top 20 prioridad de atención')
        fig.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig, use_container_width=True)

with tab_riesgo:
    st.markdown('### Centro de alerta temprana')
    mode = st.radio('Vista', ['Todos los riesgos', 'Solo Alto y Medio', 'Intervención inmediata'], horizontal=True)
    risk_view = summary.copy()
    if mode == 'Solo Alto y Medio':
        risk_view = risk_view[risk_view['riesgo_integral'].isin(['Alto','Medio'])]
    if mode == 'Intervención inmediata':
        risk_view = risk_view[risk_view['segmento_ave'].eq('Intervención inmediata')]
    risk_view = risk_view.sort_values(['puntaje_riesgo','horas_sin_actividad','pendientes','atrasadas'], ascending=[False,False,False,False])
    cols_show = [c for c in ['estudiante','correo','riesgo_integral','segmento_ave','puntaje_riesgo','horas_sin_actividad','tiempo_total_horas','deficit_horas','pendientes','atrasadas','porcentaje_avance','accion_recomendada'] if c in risk_view.columns]
    st.dataframe(risk_view[cols_show], use_container_width=True, hide_index=True)
    st.download_button('Descargar alertas CSV', risk_view[cols_show].to_csv(index=False).encode('utf-8-sig'), file_name=f'alertas_ave_{course_id}.csv', mime='text/csv', use_container_width=True)

with tab_est:
    st.markdown('### Base completa de estudiantes')
    risk_filter = st.multiselect('Filtrar riesgo integral', RISK_ORDER, default=RISK_ORDER)
    seg_filter = st.multiselect('Filtrar segmento AVE', sorted(summary['segmento_ave'].dropna().unique().tolist()), default=sorted(summary['segmento_ave'].dropna().unique().tolist()))
    filtered = summary[summary['riesgo_integral'].isin(risk_filter) & summary['segmento_ave'].isin(seg_filter)]
    st.dataframe(filtered, use_container_width=True, hide_index=True)

with tab_ent:
    st.markdown('### Actividades y entregas')
    c1, c2 = st.columns(2)
    with c1:
        st.caption('Actividades publicadas')
        st.dataframe(assign_df, use_container_width=True, hide_index=True)
    with c2:
        st.caption('Detalle de entregas')
        st.dataframe(sub_df, use_container_width=True, hide_index=True)

with tab_hist:
    st.markdown('### Historial y evolución')
    st.dataframe(hist, use_container_width=True, hide_index=True)
    if not hist.empty:
        hist2 = hist.copy()
        hist2['created_at_dt'] = pd.to_datetime(hist2['created_at'], errors='coerce')
        trend = hist2.dropna(subset=['created_at_dt']).groupby([hist2['created_at_dt'].dt.date, 'riesgo_integral']).size().reset_index(name='cantidad')
        if not trend.empty:
            fig = px.line(trend, x='created_at_dt', y='cantidad', color='riesgo_integral', markers=True, title='Evolución histórica del riesgo')
            st.plotly_chart(fig, use_container_width=True)
        last_two = hist2.sort_values('created_at_dt').groupby('user_id').tail(2)
        st.info('El historial permite detectar recuperación, reincidencia o deterioro al comparar cortes de análisis guardados en la base local.')

with tab_bit:
    st.markdown('### Bitácora de intervención del asesor')
    st.caption('Registra contactos, resultados y próximas acciones por estudiante. Esta información queda almacenada localmente en SQLite y se incluye en el Excel Pro.')
    student_options = {f"{r['estudiante']} | {r.get('correo','')} | ID {r['user_id']}": r for _, r in summary.iterrows()}
    selected_student = st.selectbox('Estudiante', list(student_options.keys()))
    stu = student_options[selected_student]
    with st.form('followup_form', clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        medio = c1.selectbox('Medio de contacto', ['Canvas','Correo','Llamada','WhatsApp institucional','Reunión','Otro'])
        motivo = c2.selectbox('Motivo', ['Riesgo alto','Riesgo medio','Desconexión','Actividad pendiente','Actividad vencida','Baja conexión','Bajo avance','Otro'])
        resultado = c3.selectbox('Resultado', ['Contactado','No respondió','Respondió','Se comprometió','Requiere apoyo','Escalado a coordinación','Otro'])
        proxima_accion = st.text_input('Próxima acción', value='Dar seguimiento en el próximo corte')
        fecha_proxima = st.date_input('Fecha próxima acción', value=date.today() + timedelta(days=1))
        obs = st.text_area('Observaciones')
        save_btn = st.form_submit_button('Guardar en bitácora', type='primary')
        if save_btn:
            save_followup(course_id, course_name, section_id, section_name, stu['user_id'], stu['estudiante'], stu.get('correo',''), medio, motivo, resultado, proxima_accion, fecha_proxima, obs, generated_by)
            st.success('Seguimiento guardado correctamente.')
            st.rerun()
    followups = load_followups(course_id, section_id)
    st.markdown('#### Registros guardados')
    st.dataframe(followups, use_container_width=True, hide_index=True)
    if not followups.empty:
        del_id = st.number_input('ID de registro a eliminar', min_value=0, value=0, step=1)
        if st.button('Eliminar registro seleccionado') and del_id > 0:
            delete_followup(del_id)
            st.success('Registro eliminado.')
            st.rerun()

with tab_msg:
    st.markdown('### Mensajes inteligentes por caso')
    templates = {
        'Riesgo alto': 'Hola {nombre}, espero que estés bien. Al revisar el seguimiento del curso, observé que presentas riesgo alto por desconexión, entregas pendientes o bajo avance. Te recomiendo ingresar hoy a Canvas, revisar los módulos activos y priorizar las actividades vencidas o próximas. Estoy pendiente para apoyarte si tienes alguna dificultad.',
        'Riesgo medio': 'Hola {nombre}, noté que tu actividad reciente o avance requiere atención. Te recomiendo ingresar hoy a Canvas y avanzar con las actividades pendientes para mantenerte al día. Cualquier duda, estoy pendiente para apoyarte.',
        'Entrega vencida': 'Hola {nombre}, observé que tienes una o más actividades vencidas. Te sugiero revisar Canvas hoy y organizar un plan de entrega para evitar que esto afecte tu avance del curso.',
        'Recuperación positiva': 'Hola {nombre}, felicidades por retomar actividad en el curso. Continúa revisando Canvas diariamente y mantén tus entregas al día. Sigue adelante.',
    }
    tipo = st.selectbox('Tipo de mensaje', list(templates.keys()))
    msg_student_key = st.selectbox('Generar para estudiante', list(student_options.keys()), key='msg_student')
    msg_stu = student_options[msg_student_key]
    msg = templates[tipo].format(nombre=msg_stu.get('nombre') or msg_stu.get('estudiante'))
    st.text_area('Mensaje listo para copiar', msg, height=150)
    contact_all = summary[summary['riesgo_integral'].isin(['Alto','Medio'])].sort_values(['puntaje_riesgo','horas_sin_actividad'], ascending=[False,False])
    st.markdown('#### Listado completo para contacto')
    contact_cols = [c for c in ['estudiante','correo','riesgo_integral','segmento_ave','puntaje_riesgo','horas_sin_actividad','pendientes','atrasadas','accion_recomendada'] if c in contact_all.columns]
    st.dataframe(contact_all[contact_cols], use_container_width=True, hide_index=True)

with tab_rep:
    st.markdown('### Exportables profesionales')
    c1, c2 = st.columns(2)
    with c1:
        xlsx = excel_bytes(summary, sub_df, hist, followups)
        st.download_button('Descargar Excel Pro completo', xlsx, file_name=f'reporte_pro_ave_{course_id}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
    with c2:
        pdf = pdf_bytes(summary, course_name, section_name, generated_by, str(analysis_date))
        st.download_button('Descargar PDF ejecutivo Pro', pdf, file_name=f'informe_ejecutivo_pro_ave_{course_id}.pdf', mime='application/pdf', use_container_width=True)
    st.markdown('#### Ficha individual PDF')
    individual_key = st.selectbox('Seleccione estudiante para ficha individual', list(student_options.keys()), key='indiv')
    ind_stu = student_options[individual_key].to_dict() if hasattr(student_options[individual_key], 'to_dict') else dict(student_options[individual_key])
    indiv_pdf = individual_pdf_bytes(ind_stu, sub_df, followups, course_name, section_name, generated_by, str(analysis_date))
    clean_name = ''.join(ch for ch in str(ind_stu.get('estudiante','estudiante')) if ch.isalnum() or ch in (' ','_','-')).strip().replace(' ','_')[:60]
    st.download_button('Descargar ficha individual PDF', indiv_pdf, file_name=f'ficha_{clean_name}.pdf', mime='application/pdf', use_container_width=True)

with tab_conf:
    st.markdown('### Configuración y automatización')
    st.info('Para producción se recomienda guardar CANVAS_URL y CANVAS_TOKEN en los Secrets de Streamlit Cloud o variables de entorno, no escribir el token directamente en archivos.')
    st.markdown('''
**Automatización diaria sugerida:**

1. Ejecutar la app en un servidor o Streamlit Cloud.
2. Programar revisión diaria manual o con tarea externa.
3. Descargar Excel/PDF de corte.
4. Registrar intervenciones en la bitácora.
5. Usar historial para comparar recuperación o deterioro semanal.

**Módulos Pro 2.0 incluidos:** dashboard ejecutivo, índice integral de riesgo, segmentación AVE, bitácora, historial, mensajes inteligentes, PDF ejecutivo, ficha individual y Excel con bitácora.
''')

st.markdown(f'<div class="footer">Desarrollador: {DEV} | Universidad del Valle de Guatemala - AVE</div>', unsafe_allow_html=True)
