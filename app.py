import streamlit as st
import datetime
import base64
from sqlalchemy import text  # IMPORTANTE: Necesario para que PostgreSQL entienda las variables :clave

# --- 1. CONEXIÓN Y CREACIÓN DE TABLAS EN NUBE ---
try:
    conexion_db = st.connection("postgresql", type="sql")
except Exception as e:
    st.error("No se pudo conectar a la base de datos en la nube. Revisa los Secretos en Streamlit Cloud.")
    st.stop()

def inicializar_base_de_datos():
    with conexion_db.session as session:
        # Tabla pruebas compatible con PostgreSQL (BYTEA para imágenes y archivos binarios)
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS pruebas (
                id SERIAL PRIMARY KEY,
                nombre_archivo TEXT,
                bytes_audio BYTEA,
                intentos_maximos INTEGER,
                intentos_restantes INTEGER,
                respuesta_b TEXT,
                correccion_a TEXT,
                puntuacion INTEGER,
                estado TEXT,
                nombre_personalizado TEXT,
                foto_respuesta_b BYTEA,
                foto_correccion_a BYTEA
            )
        """))
        
        # Tabla usuarios
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                rol TEXT PRIMARY KEY,
                password TEXT
            )
        """))
        
        # Tabla anuncios
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS anuncios (
                id SERIAL PRIMARY KEY,
                mensaje TEXT
            )
        """))
        
        # Tabla mensajes_admin
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS mensajes_admin (
                id SERIAL PRIMARY KEY,
                remitente TEXT,
                mensaje TEXT,
                fecha TEXT
            )
        """))
        
        # Insertar usuarios por defecto si no existen
        resultado = session.execute(text("SELECT COUNT(*) FROM usuarios")).fetchone()
        if resultado is None or resultado[0] == 0:
            session.execute(text("INSERT INTO usuarios (rol, password) VALUES ('Creador', 'piano')"))
            session.execute(text("INSERT INTO usuarios (rol, password) VALUES ('Minero', 'oido')"))
            session.execute(text("INSERT INTO usuarios (rol, password) VALUES ('Admin', 'admin')"))
            
        session.commit()

inicializar_base_de_datos()

# --- 2. FUNCIONES DE BASE DE DATOS (NUBE) ---

def obtener_password(rol):
    with conexion_db.session as session:
        resultado = session.execute(text("SELECT password FROM usuarios WHERE rol = :rol"), {"rol": rol}).fetchone()
        return resultado[0] if resultado else None

def actualizar_password(rol, nueva_pass):
    with conexion_db.session as session:
        session.execute(text("UPDATE usuarios SET password = :password WHERE rol = :rol"), {"password": nueva_pass, "rol": rol})
        session.commit()

def obtener_pruebas(estado=None):
    with conexion_db.session as session:
        query = """SELECT id, nombre_archivo, nombre_personalizado, intentos_maximos, 
                          intentos_restantes, respuesta_b, correccion_a, puntuacion, 
                          estado, bytes_audio, foto_respuesta_b, foto_correccion_a 
                   FROM pruebas"""
        if estado:
            query += " WHERE estado = :estado"
            resultado = session.execute(text(query), {"estado": estado}).fetchall()
        else:
            resultado = session.execute(text(query)).fetchall()
        return resultado

def restar_intento(id_prueba, intentos_actuales):
    with conexion_db.session as session:
        session.execute(text("UPDATE pruebas SET intentos_restantes = :intentos WHERE id = :id"), 
                        {"intentos": intentos_actuales - 1, "id": id_prueba})
        session.commit()

def guardar_respuesta_b_con_foto(id_prueba, respuesta, bytes_foto):
    with conexion_db.session as session:
        session.execute(text("""
            UPDATE pruebas 
            SET respuesta_b = :resp, foto_respuesta_b = :foto, estado = 'Respondido' 
            WHERE id = :id
        """), {"resp": respuesta, "foto": bytes_foto, "id": id_prueba})
        session.commit()

def guardar_correccion_a_con_foto(id_prueba, correccion, puntuacion, bytes_foto):
    with conexion_db.session as session:
        session.execute(text("""
            UPDATE pruebas 
            SET correccion_a = :corr, puntuacion = :puntos, foto_correccion_a = :foto, estado = 'Corregido' 
            WHERE id = :id
        """), {"corr": correccion, "puntos": puntuacion, "foto": bytes_foto, "id": id_prueba})
        session.commit()

def resetear_pruebas():
    with conexion_db.session as session:
        session.execute(text("DELETE FROM pruebas"))
        session.commit()

def borrar_prueba_individual(id_prueba):
    with conexion_db.session as session:
        session.execute(text("DELETE FROM pruebas WHERE id = :id"), {"id": id_prueba})
        session.commit()

def actualizar_intentos_individual(id_prueba, nuevos_intentos):
    with conexion_db.session as session:
        session.execute(text("UPDATE pruebas SET intentos_restantes = :intentos WHERE id = :id"), 
                        {"intentos": nuevos_intentos, "id": id_prueba})
        session.commit()

def obtener_anuncio():
    with conexion_db.session as session:
        resultado = session.execute(text("SELECT mensaje FROM anuncios ORDER BY id DESC LIMIT 1")).fetchone()
        if resultado and resultado[0] and resultado[0].strip() != "":
            return resultado[0]
        return None

def actualizar_anuncio(nuevo_mensaje):
    with conexion_db.session as session:
        session.execute(text("INSERT INTO anuncios (mensaje) VALUES (:msj)"), {"msj": nuevo_mensaje})
        session.commit()

def enviar_mensaje_admin(remitente, mensaje):
    with conexion_db.session as session:
        fecha_hoy = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        session.execute(text("INSERT INTO mensajes_admin (remitente, mensaje, fecha) VALUES (:rem, :msj, :fec)"), 
                        {"rem": remitente, "msj": mensaje, "fec": fecha_hoy})
        session.commit()

def obtener_mensajes_admin():
    with conexion_db.session as session:
        return session.execute(text("SELECT id, remitente, mensaje, fecha FROM mensajes_admin ORDER BY id DESC")).fetchall()

def borrar_mensaje_admin(id_mensaje):
    with conexion_db.session as session:
        session.execute(text("DELETE FROM mensajes_admin WHERE id = :id"), {"id": id_mensaje})
        session.commit()

def obtener_estadisticas_globales():
    with conexion_db.session as session:
        total = session.execute(text("SELECT COUNT(*) FROM pruebas")).fetchone()[0]
        corregidas = session.execute(text("SELECT COUNT(*) FROM pruebas WHERE estado = 'Corregido'")).fetchone()[0]
        puntos_totales = session.execute(text("SELECT SUM(puntuacion) FROM pruebas WHERE estado = 'Corregido'")).fetchone()[0] or 0
        nota_media = session.execute(text("SELECT AVG(puntuacion) FROM pruebas WHERE estado = 'Corregido'")).fetchone()[0]
        
        notas_filas = session.execute(text("SELECT puntuacion FROM pruebas WHERE estado = 'Corregido' ORDER BY id DESC")).fetchall()
        notas = [fila[0] for fila in notas_filas]
        racha = 0
        for nota in notas:
            if nota is not None and nota >= 5:
                racha += 1
            else:
                break
        return total, corregidas, puntos_totales, nota_media, racha


# --- 3. INTERFAZ GRÁFICA (Streamlit) ---
st.title("⛏️ Tone Miner")

if "rol" not in st.session_state:
    st.session_state["rol"] = None

# --- LÓGICA DE MENSAJES FLOTANTES (TOASTS) ---
if "mensaje_toast" in st.session_state:
    st.toast(st.session_state["mensaje_toast"], icon="✅")
    del st.session_state["mensaje_toast"]

# --- PANTALLA DE LOGIN ---
if st.session_state["rol"] is None:
    st.write("### 🔑 Identifícate para entrar a la mina")
    rol_elegido = st.selectbox("¿Quién eres?", ["Selecciona una opción", "Amigo A (Creador)", "Amigo B (Minero)", "Administrador"])
    
    if rol_elegido != "Selecciona una opción":
        password = st.text_input("Introduce tu contraseña de acceso:", type="password")
        if st.button("Entrar"):
            rol_db = "Creador" if rol_elegido == "Amigo A (Creador)" else "Minero" if rol_elegido == "Amigo B (Minero)" else "Admin"
            if password == obtener_password(rol_db):
                st.session_state["rol"] = rol_db
                st.session_state["mensaje_toast"] = f"¡Acceso concedido como {rol_db}!"
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta. Inténtalo de nuevo.")

# --- USUARIO AUTENTICADO ---
else:
    anuncio_actual = obtener_anuncio()
    if anuncio_actual:
        st.info(f"📢 **Anuncio de la Mina:** {anuncio_actual}")
    
    with st.sidebar:
        st.write(f"Conectado como: **{st.session_state['rol']}**")
        st.write("---")
        
        with st.expander("⚙️ Cambiar mi contraseña"):
            pass_actual = st.text_input("Contraseña actual", type="password", key="pass_act")
            nueva_pass = st.text_input("Nueva contraseña", type="password", key="pass_nuev")
            if st.button("Actualizar contraseña"):
                if pass_actual == obtener_password(st.session_state["rol"]):
                    if nueva_pass.strip():
                        actualizar_password(st.session_state["rol"], nueva_pass)
                        st.session_state["mensaje_toast"] = "¡Contraseña actualizada con éxito!"
                        st.rerun()
                    else:
                        st.error("La contraseña no puede estar vacía.")
                else:
                    st.error("La contraseña actual no coincide.")
        
        if st.session_state["rol"] in ["Creador", "Minero"]:
            st.write("---")
            with st.expander("📬 Mensaje al Administrador"):
                st.write("¿Tienes algún problema técnico o sugerencia?")
                msg_texto = st.text_area("Escribe tu mensaje aquí:", key="msg_to_admin", placeholder="Ej: Hola Pablo...")
                if st.button("Enviar al Admin"):
                    if msg_texto.strip():
                        enviar_mensaje_admin(st.session_state["rol"], msg_texto.strip())
                        st.session_state["mensaje_toast"] = "¡Mensaje enviado al Administrador!"
                        st.rerun()
                    else:
                        st.error("Escribe un mensaje antes de enviar.")

        st.write("---")
        if st.button("Cerrar Sesión 🚪"):
            st.session_state["rol"] = None
            st.rerun()

    # ================= VISTA ADMINISTRADOR =================
    if st.session_state["rol"] == "Admin":
        st.header("🛡️ Panel de Control del Administrador")
        pest_stats, pest_buzon, pest_anuncios, pest_control, pest_pass, pest_danger = st.tabs([
            "📊 Estadísticas y Audios", "📬 Buzón", "📢 Anuncios", "⚙️ Control", "🔑 Contraseñas", "🚨 Peligro"
        ])
        
        with pest_stats:
            st.subheader("📈 Rendimiento del Juego")
            total, corregidas, puntos_totales, nota_media, racha = obtener_estadisticas_globales()
            col_t, col_c, col_p, col_m, col_r = st.columns(5)
            col_t.metric("Pruebas", total)
            col_c.metric("Completadas", corregidas)
            col_p.metric("Puntos", f"{puntos_totales}")
            col_m.metric("Media", f"{round(nota_media, 2)}/10" if nota_media else "N/A")
            col_r.metric("Racha 🔥", f"{racha}")
                
            st.write("---")
            st.subheader("📋 Historial Completo y Auditoría")
            todas_las_pruebas = obtener_pruebas()
            
            if not todas_las_pruebas:
                st.info("Aún no hay pruebas en la base de datos.")
            else:
                for p in todas_las_pruebas:
                    id_p, arch, nom_p, int_max, int_rest, resp_b, corr_a, punt, est, audio, foto_b, foto_a = p
                    color = "🟡" if est == "Pendiente" else "🟠" if est == "Respondido" else "🟢"
                    
                    titulo = f"{color} '{nom_p}' (Archivo original: {arch})"
                    with st.expander(f"{titulo} - [{est}]"):
                        st.write(f"**Intentos:** {int_rest}/{int_max}")
                        st.write(f"**Justificación de B:** {resp_b if resp_b else '*Sin responder*'}")
                        if foto_b:
                            st.image(bytes(foto_b), caption="Foto-respuesta subida por el Minero", use_container_width=True)
                        st.write(f"**Justificación de A:** {corr_a if corr_a else '*Sin corregir*'}")
                        if foto_a:
                            st.image(bytes(foto_a), caption="Foto-corrección subida por el Creador", use_container_width=True)
                        st.write(f"**Nota final:** {f'{punt}/10' if punt is not None else '*Sin puntuar*'}")
                        
                        st.write("🎧 **Auditar Audio (Controles Completos):**")
                        st.audio(bytes(audio), format="audio/mp3")

        with pest_buzon:
            st.subheader("📬 Mensajes recibidos")
            messages_recibidos = obtener_mensajes_admin()
            if not messages_recibidos:
                st.info("El buzón está vacío.")
            else:
                for m in messages_recibidos:
                    id_m, remitente, mensaje, fecha = m
                    with st.container():
                        st.markdown(f"**De:** `{remitente}` | **Fecha:** {fecha}")
                        st.info(mensaje)
                        if st.button("Marcar como leído / Borrar", key=f"del_msg_{id_m}"):
                            borrar_mensaje_admin(id_m)
                            st.session_state["mensaje_toast"] = "Mensaje archivado."
                            st.rerun()
                        st.write("---")

        with pest_anuncios:
            st.subheader("📢 Tablón de Anuncios")
            st.write(f"**Anuncio actual visible:** {f'\"{anuncio_actual}\"' if anuncio_actual else '*Desactivado*'}")
            nuevo_msj = st.text_area("Escribe el comunicado (deja en blanco para ocultar):", placeholder="¡Mensaje para los amigos!")
            
            col_an1, col_an2 = st.columns(2)
            with col_an1:
                if st.button("Actualizar / Publicar Anuncio"):
                    actualizar_anuncio(nuevo_msj.strip())
                    if nuevo_msj.strip() == "":
                        st.session_state["mensaje_toast"] = "¡Anuncio desactivado!"
                    else:
                        st.session_state["mensaje_toast"] = "¡Anuncio publicado correctamente!"
                    st.rerun()
            with col_an2:
                if st.button("Desactivar Anuncio directamente"):
                    actualizar_anuncio("")
                    st.session_state["mensaje_toast"] = "¡Anuncio desactivado!"
                    st.rerun()

        with pest_control:
            st.subheader("🛠️ Ajustar Pruebas")
            todas_control = obtener_pruebas()
            if todas_control:
                opciones_gestion = {f"'{p[2]}'": p for p in todas_control}
                seleccion_gestion = st.selectbox("Selecciona una prueba:", list(opciones_gestion.keys()))
                prueba_g = opciones_gestion[seleccion_gestion]
                id_g, _, nom_g, int_max_g, int_rest_g, _, _, _, _, _, _, _ = prueba_g
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.write("🔧 **Modificar Intentos**")
                    nuevos_intentos_g = st.number_input("Nuevos intentos:", min_value=0, max_value=20, value=int_rest_g, key=f"int_{id_g}")
                    if st.button("Guardar", key=f"btn_int_{id_g}"):
                        actualizar_intentos_individual(id_g, nuevos_intentos_g)
                        st.session_state["mensaje_toast"] = "¡Intentos modificados!"
                        st.rerun()
                with col_g2:
                    st.write("🗑️ **Eliminar prueba**")
                    if st.button("Borrar definitivamente", key=f"btn_del_{id_g}"):
                        borrar_prueba_individual(id_g)
                        st.session_state["mensaje_toast"] = "¡Prueba eliminada!"
                        st.rerun()

        with pest_pass:
            st.write(f"🔑 **Creador:** `{obtener_password('Creador')}` | 🔑 **Minero:** `{obtener_password('Minero')}`")
            usuario_a_modificar = st.selectbox("Selecciona usuario:", ["Creador", "Minero", "Admin"])
            pass_nueva_admin = st.text_input("Nueva contraseña:", type="password")
            if st.button("Forzar cambio"):
                actualizar_password(usuario_a_modificar, pass_nueva_admin)
                st.session_state["mensaje_toast"] = "¡Contraseña cambiada!"
                st.rerun()

        with pest_danger:
            confirmacion = st.checkbox("Entiendo las consecuencias.")
            if st.button("💥 Resetear base de datos", disabled=not confirmacion):
                resetear_pruebas()
                st.session_state["mensaje_toast"] = "¡Base de datos reseteada!"
                st.rerun()

    # ================= VISTA CREADOR (AMIGO A) =================
    elif st.session_state["rol"] == "Creador":
        st.header("👑 Panel del Creador (Amigo A)")
        
        st.subheader("📤 Subir nueva prueba auditiva")
        nombre_personalizado_input = st.text_input("Nombre de la prueba (Opcional):", placeholder="Ej: Progresión en Re Menor, Blues...")
        st.caption("ℹ️ *Si dejas este campo vacío, la prueba se nombrará automáticamente con la fecha de hoy.*")
        
        archivo_subido = st.file_uploader("Elige el audio (.mp3, .wav)", type=["mp3", "wav"])
        intentos = st.number_input("¿Cuántos intentos de escucha tiene?", min_value=1, max_value=10, value=3)
        
        if st.button("Subir prueba al servidor"):
            if archivo_subido is not None:
                datos_audio = archivo_subido.read()
                nombre_archivo = archivo_subido.name
                
                nombre_final = nombre_personalizado_input.strip()
                if not nombre_final:
                    hoy = datetime.date.today().strftime("%d/%m/%Y")
                    nombre_final = f"Prueba {hoy}"
                
                with conexion_db.session as session:
                    session.execute(text("""
                        INSERT INTO pruebas (nombre_archivo, nombre_personalizado, bytes_audio, intentos_maximos, intentos_restantes, estado)
                        VALUES (:arch, :nom, :audio, :int_max, :int_rest, 'Pendiente')
                    """), {
                        "arch": nombre_archivo,
                        "nom": nombre_final,
                        "audio": datos_audio,
                        "int_max": intentos,
                        "int_rest": intentos
                    })
                    session.commit()
                
                st.session_state["mensaje_toast"] = f"¡La prueba '{nombre_final}' ha sido subida correctamente!"
                st.rerun()
            else:
                st.error("Por favor, sube un archivo de audio primero.")

        st.write("---")
        
        st.subheader("🗑️ Gestionar tus pruebas pendientes")
        pendientes = obtener_pruebas("Pendiente")
        if not pendientes:
            st.info("No tienes pruebas pendientes de resolver.")
        else:
            for p in pendientes:
                id_p, arch, nom_p, int_max, int_rest, _, _, _, _, _, _, _ = p
                with st.expander(f"🎵 {nom_p}"):
                    if int_max == int_rest:
                        st.write("El Minero aún no ha gastado intentos. Puedes borrarla si la subiste por error.")
                        if st.button(f"Borrar definitivamente '{nom_p}'", key=f"del_creador_{id_p}"):
                            borrar_prueba_individual(id_p)
                            st.session_state["mensaje_toast"] = f"¡La prueba '{nom_p}' ha sido eliminada!"
                            st.rerun()
                    else:
                        st.warning(f"No puedes borrar esta prueba porque tu amigo ya ha gastado intentos ({int_rest}/{int_max} restantes).")

        st.write("---")
        
        st.subheader("📝 Pruebas pendientes de corregir")
        respondidas = obtener_pruebas("Respondido")
        if not respondidas:
            st.info("No hay respuestas nuevas de tu amigo por corregir.")
        else:
            opciones_corregir = {f"'{r[2]}'": r for r in respondidas}
            seleccion_corregir = st.selectbox("Selecciona qué respuesta quieres revisar:", list(opciones_corregir.keys()))
            
            id_c, _, nom_c, _, _, respuesta_b_c, _, _, _, bytes_audio_c, foto_b_c, _ = opciones_corregir[seleccion_corregir]
            
            st.warning(f"Justificación de tu amigo: **{respuesta_b_c if respuesta_b_c else '*Sin texto de justificación*'}**")
            
            if foto_b_c:
                st.write("📷 **Foto-respuesta adjunta por el Minero:**")
                st.image(bytes(foto_b_c), use_container_width=True)
            
            st.write("🎧 **Escucha la progresión para corregir:**")
            st.audio(bytes(bytes_audio_c), format="audio/mp3")
            
            st.write("### 📝 Califica la prueba")
            foto_creador = st.file_uploader("Sube una foto con la solución / partitura (Opcional):", type=["png", "jpg", "jpeg"])
            feedback = st.text_area("Justificación (Opcional):", placeholder="Ej: ¡Buen trabajo! El tercer acorde era menor...")
            puntos_dados = st.slider("Asigna una puntuación:", min_value=0, max_value=10, value=10)
            
            if st.button("Enviar Corrección"):
                if feedback.strip() or foto_creador is not None:
                    bytes_foto_creador = foto_creador.read() if foto_creador is not None else None
                    guardar_correccion_a_con_foto(id_c, feedback.strip(), puntos_dados, bytes_foto_creador)
                    st.session_state["mensaje_toast"] = f"¡Calificación de {puntos_dados}/10 enviada correctamente!"
                    st.rerun()
                else:
                    st.error("Por favor, escribe una justificación o sube una fotografía para poder enviar la corrección.")

    # ================= VISTA MINERO (AMIGO B) =================
    elif st.session_state["rol"] == "Minero":
        st.header("⛏️ Panel del Minero (Amigo B)")
        
        _, _, puntos_totales, nota_media, racha = obtener_estadisticas_globales()
        col1, col2, col3 = st.columns(3)
        col1.metric("Tus Puntos 🏆", f"{puntos_totales} pts")
        col2.metric("Nota Media ⭐", f"{round(nota_media, 2)}/10" if nota_media else "N/A")
        col3.metric("Racha 🔥", f"{racha} seguidas")
        
        st.write("---")
        
        st.subheader("🎵 Zonas de Minado (Pruebas disponibles)")
        pruebas_disp = obtener_pruebas("Pendiente")
        
        if not pruebas_disp:
            st.info("¡Buen trabajo! No tienes pruebas pendientes de resolver.")
        else:
            opciones_pruebas = {f"'{p[2]}'": p for p in pruebas_disp}
            seleccion = st.selectbox("Selecciona la prueba:", list(opciones_pruebas.keys()))
            
            id_prueba, _, nom_p, int_max, intentos_restantes, _, _, _, _, bytes_audio, _, _ = opciones_pruebas[seleccion]
            
            st.write(f"### 📊 Intentos: **{intentos_restantes} / {int_max}**")
            
            llave = f"reproducir_{id_prueba}"
            if llave not in st.session_state:
                st.session_state[llave] = False
                
            if st.session_state[llave]:
                audio_base64 = base64.b64encode(bytes(bytes_audio)).decode('utf-8')
                audio_src = f"data:audio/mp3;base64,{audio_base64}"
                
                reproductor_html = f"""
                <div style="background-color: #1E1E1E; padding: 10px 15px; border-radius: 8px; text-align: center; border: 1px solid #FF4B4B; color: white; font-family: sans-serif; box-sizing: border-box;">
                    <span style="font-size: 20px; display: block; margin-bottom: 2px;">🎵</span>
                    <strong>Reproduciendo audio...</strong>
                    <p style="font-size: 11px; color: #888; margin-top: 2px; margin-bottom: 0px;">Escucha atentamente. Solo sonará una vez.</p>
                    <audio id="minerAudio" autoplay>
                        <source src="{audio_src}" type="audio/mp3">
                    </audio>
                </div>
                <script>
                    var audio = document.getElementById('minerAudio');
                    audio.onended = function() {{
                        var buttons = window.parent.document.querySelectorAll('button');
                        for (var i = 0; i < buttons.length; i++) {{
                            if (buttons[i].textContent.includes('Terminar audio ⏹️')) {{
                                buttons[i].click();
                                break;
                            }}
                        }}
                    }};
                </script>
                """
                st.components.v1.html(reproductor_html, height=140)
                
                if st.button("Terminar audio ⏹️"):
                    st.session_state[llave] = False
                    st.rerun()
                
                st.write("")
                st.warning("⚠️ No cierres ni cambies esta pestaña mientras el audio se está reproduciendo, o se consumirá otro intento.")
            
            elif intentos_restantes > 0:
                if st.button("🔊 Gastar 1 intento y escuchar"):
                    restar_intento(id_prueba, intentos_restantes)
                    st.session_state[llave] = True
                    st.rerun()
            
            else:
                st.error("❌ ¡Te has quedado sin intentos para esta prueba!")
                
            st.write("---")
            
            st.write("### 📝 Envía tu respuesta")
            foto_respuesta = st.file_uploader("Sube una foto de tu cifrado (Opcional):", type=["png", "jpg", "jpeg"])
            respuesta_usuario = st.text_input("Justificación (Opcional):", placeholder="Ej: I - V - vi - IV. El tercer acorde tiene tensión...")
            
            if st.button("Enviar respuesta"):
                if respuesta_usuario.strip() or foto_respuesta is not None:
                    bytes_foto = foto_respuesta.read() if foto_respuesta is not None else None
                    guardar_respuesta_b_con_foto(id_prueba, respuesta_usuario.strip(), bytes_foto)
                    if f"reproducir_{id_prueba}" in st.session_state:
                        del st.session_state[f"reproducir_{id_prueba}"]
                    st.session_state["mensaje_toast"] = "¡Tu respuesta se ha enviado correctamente!"
                    st.rerun()
                else:
                    st.error("Por favor, escribe una justificación o sube una fotografía para poder enviar tu respuesta.")

        st.write("---")
        
        st.subheader("🎒 El Baúl de Prácticas (Historial)")
        corregidas = obtener_pruebas("Corregido")
        
        if not corregidas:
            st.info("Aún no tienes pruebas corregidas.")
        else:
            for c in corregidas:
                id_cor, _, nom_cor, _, _, resp_b, corr_a, punt_cor, _, aud_cor, foto_b, foto_a = c
                with st.expander(f"🎵 {nom_cor} — ⭐ Nota: {punt_cor}/10"):
                    st.write(f"**Tu respuesta (Justificación):** {resp_b if resp_b else '*Sin texto*'}")
                    if foto_b:
                        st.image(bytes(foto_b), caption="Tu foto-respuesta enviada", use_container_width=True)
                    st.write("---")
                    st.info(f"**Corrección (Justificación):** {corr_a if corr_a else '*Sin texto*'}")
                    if foto_a:
                        st.image(bytes(foto_a), caption="Solución visual de tu amigo", use_container_width=True)
                    st.audio(bytes(aud_cor), format="audio/mp3")
