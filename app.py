import datetime
import uuid
import plotly.graph_objects as go
import streamlit as st
from supabase import Client, create_client

# --- CONFIGURACIÓN DE SEGURIDAD SUPABASE ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
  st.error("⚠️ Faltan las credenciales de Supabase en los Secrets de Streamlit.")
  st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# --- FUNCIONES DE ALMACENAMIENTO (SUPABASE STORAGE) ---
def subir_archivo_storage(bytes_file, nombre_original, subcarpeta, content_type):
  """Sube un archivo al bucket 'audios' dentro de una subcarpeta organizada y devuelve su URL pública"""
  if not bytes_file:
    return None

  ext = nombre_original.split(".")[-1] if "." in nombre_original else "bin"
  nombre_unico = f"{subcarpeta}/{uuid.uuid4().hex}.{ext}"

  supabase.storage.from_("audios").upload(
      path=nombre_unico,
      file=bytes_file,
      file_options={"content-type": content_type},
  )

  return supabase.storage.from_("audios").get_public_url(nombre_unico)


# --- FUNCIONES DE BASE DE DATOS (SUPABASE) ---


def obtener_password(rol):
  res = supabase.table("usuarios").select("password").eq("rol", rol).execute()
  return res.data[0]["password"] if res.data else None


def actualizar_password(rol, nueva_pass):
  supabase.table("usuarios").update({"password": nueva_pass}).eq(
      "rol", rol
  ).execute()


def obtener_categorias():
  res = (
      supabase.table("categorias")
      .select("nombre")
      .order("id", desc=False)
      .execute()
  )
  if res.data:
    return [c["nombre"] for c in res.data]
  return [
      "Intervalos",
      "Progresiones",
      "Fragmentos",
      "Escalas",
      "Dictado",
      "Acordes",
  ]


def agregar_categoria(nombre):
  supabase.table("categorias").insert({"nombre": nombre.strip()}).execute()


def eliminar_categoria(nombre):
  supabase.table("categorias").delete().eq("nombre", nombre).execute()


def obtener_pruebas(estado=None, destinatario=None):
  query = supabase.table("pruebas").select("*").order("id", desc=False)
  if estado:
    query = query.eq("estado", estado)
  if destinatario:
    query = query.eq("destinatario", destinatario)
  res = query.execute()

  pruebas_tuplas = []
  for p in res.data:
    pruebas_tuplas.append((
        p["id"],
        p["nombre_archivo"],
        p["nombre_personalizado"],
        p["intentos_maximos"],
        p["intentos_restantes"],
        p["respuesta_b"],
        p["correccion_a"],
        p["puntuacion"],
        p["estado"],
        p["url_audio"],
        p["url_foto_respuesta_b"],
        p["url_foto_correccion_a"],
        p.get("destinatario", "Minero 1"),
        p.get("indicaciones"),
    ))
  return pruebas_tuplas


def restar_intento(id_prueba, intentos_actuales):
  supabase.table("pruebas").update(
      {"intentos_restantes": intentos_actuales - 1}
  ).eq("id", id_prueba).execute()


def guardar_respuesta_b_con_foto(
    id_prueba, respuesta, bytes_foto, nombre_foto="foto.jpg"
):
  url_foto = (
      subir_archivo_storage(bytes_foto, nombre_foto, "respuestas_b", "image/jpeg")
      if bytes_foto
      else None
  )
  data = {"respuesta_b": respuesta, "estado": "Respondido"}
  if url_foto:
    data["url_foto_respuesta_b"] = url_foto

  supabase.table("pruebas").update(data).eq("id", id_prueba).execute()


def guardar_correccion_a_con_foto(
    id_prueba, correccion, puntuacion, bytes_foto, nombre_foto="foto.jpg"
):
  url_foto = (
      subir_archivo_storage(bytes_foto, nombre_foto, "soluciones_a", "image/jpeg")
      if bytes_foto
      else None
  )
  data = {
      "correccion_a": correccion,
      "puntuacion": puntuacion,
      "estado": "Corregido",
  }
  if url_foto:
    data["url_foto_correccion_a"] = url_foto

  supabase.table("pruebas").update(data).eq("id", id_prueba).execute()


def resetear_pruebas():
  supabase.table("pruebas").delete().neq("id", 0).execute()


def borrar_prueba_individual(id_prueba):
  supabase.table("pruebas").delete().eq("id", id_prueba).execute()


def actualizar_intentos_individual(id_prueba, nuevos_intentos):
  supabase.table("pruebas").update({"intentos_restantes": nuevos_intentos}).eq(
      "id", id_prueba
  ).execute()


def obtener_anuncio():
  res = (
      supabase.table("anuncios")
      .select("mensaje")
      .order("id", desc=True)
      .limit(1)
      .execute()
  )
  if res.data and res.data[0]["mensaje"].strip() != "":
    return res.data[0]["mensaje"]
  return None


def actualizar_anuncio(nuevo_mensaje):
  supabase.table("anuncios").insert({"mensaje": nuevo_mensaje}).execute()


def enviar_mensaje_admin(remitente, mensaje):
  fecha_hoy = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
  supabase.table("mensajes_admin").insert({
      "remitente": remitente,
      "mensaje": mensaje,
      "fecha": fecha_hoy,
  }).execute()


def obtener_mensajes_admin():
  res = (
      supabase.table("mensajes_admin")
      .select("id, remitente, mensaje, fecha")
      .order("id", desc=True)
      .execute()
  )
  return [(m["id"], m["remitente"], m["mensaje"], m["fecha"]) for m in res.data]


def borrar_mensaje_admin(id_mensaje):
  supabase.table("mensajes_admin").delete().eq("id", id_mensaje).execute()


def obtener_estadisticas_globales(destinatario=None):
  query = supabase.table("pruebas").select(
      "id, estado, puntuacion, destinatario, nombre_personalizado"
  )
  if destinatario:
    query = query.eq("destinatario", destinatario)
  res_all = query.execute()
  todas = res_all.data

  total = len(todas)
  corregidas_list = [p for p in todas if p["estado"] == "Corregido"]
  corregidas = len(corregidas_list)

  puntos_totales = sum(
      [p["puntuacion"] for p in corregidas_list if p["puntuacion"] is not None]
  )
  nota_media = (puntos_totales / corregidas) if corregidas > 0 else None

  categorias_bd = obtener_categorias()
  stats_cat = {cat: [] for cat in categorias_bd}
  for p in corregidas_list:
    nom = p.get("nombre_personalizado", "")
    punt = p.get("puntuacion")
    if punt is not None:
      for cat in categorias_bd:
        if f"[{cat}]" in nom:
          stats_cat[cat].append(punt)
          break

  medias_radar = {
      cat: (sum(vals) / len(vals) if vals else 0)
      for cat, vals in stats_cat.items()
  }

  return total, corregidas, puntos_totales, nota_media, medias_radar


def generar_grafico_radar(medias_dict):
  categorias = list(medias_dict.keys())
  if not categorias or len(categorias) < 3:
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=200,
        annotations=[
            dict(
                text="Se necesitan al menos 3 categorías para trazar el radar",
                showarrow=False,
                font=dict(color="#888", size=14),
            )
        ],
    )
    return fig

  valores = [round(medias_dict[c], 1) for c in categorias]

  # Cerrar el polígono
  categorias_cerradas = categorias + [categorias[0]]
  valores_cerrados = valores + [valores[0]]

  fig = go.Figure()
  fig.add_trace(
      go.Scatterpolar(
          r=valores_cerrados,
          theta=categorias_cerradas,
          fill="toself",
          fillcolor="rgba(255, 75, 75, 0.45)",
          line=dict(color="#FF4B4B", width=2.5),
          marker=dict(color="#FFFFFF", size=7),
          name="Media de notas",
      )
  )

  fig.update_layout(
      polar=dict(
          radialaxis=dict(
              visible=True,
              range=[0, 100],
              tickfont=dict(size=10, color="#888"),
              gridcolor="#333",
              linecolor="#333",
          ),
          angularaxis=dict(
              tickfont=dict(size=13, color="#FFF", family="sans-serif"),
              gridcolor="#333",
              linecolor="#333",
          ),
          gridshape="polygon",
          bgcolor="rgba(0,0,0,0)",
      ),
      paper_bgcolor="rgba(0,0,0,0)",
      margin=dict(l=40, r=40, t=30, b=30),
      showlegend=False,
      height=340,
  )
  return fig


# --- INTERFAZ GRÁFICA (Streamlit) ---
st.title("⛏️ Tone Miner")

if "rol" not in st.session_state:
  st.session_state["rol"] = None

# --- LÓGICA DE MENSAJES FLOTANTES (TOASTS) ---
if "mensaje_toast" in st.session_state:
  st.toast(st.session_state["mensaje_toast"], icon="✅")
  del st.session_state["mensaje_toast"]

# --- PANTALLA DE LOGIN ---
if st.session_state["rol"] is None:
  st.write("### 🔑 Identifícate para entrar a la mina 🔑")
  rol_elegido = st.selectbox(
      "¿Quién eres?",
      ["Selecciona una opción", "Creador", "Minero 1", "Minero 2", "Administrador"],
  )

  if rol_elegido != "Selecciona una opción":
    password = st.text_input("Introduce tu contraseña de acceso:", type="password")
    if st.button("Entrar"):
      rol_db = (
          "Creador"
          if rol_elegido == "Creador"
          else "Admin"
          if rol_elegido == "Administrador"
          else rol_elegido
      )
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

    # Menú contextual para el Creador
    if st.session_state["rol"] == "Creador":
      if "minero_seleccionado" not in st.session_state:
        st.session_state["minero_seleccionado"] = "Minero 1"

      st.subheader("🎯 Minero de trabajo")
      minero_sel = st.selectbox(
          "Gestionar ejercicios para:",
          ["Minero 1", "Minero 2"],
          index=0
          if st.session_state["minero_seleccionado"] == "Minero 1"
          else 1,
      )
      st.session_state["minero_seleccionado"] = minero_sel
      st.write("---")

    # Menú contextual para el Admin
    if st.session_state["rol"] == "Admin":
      if "minero_admin_filtro" not in st.session_state:
        st.session_state["minero_admin_filtro"] = "Todos"

      st.subheader("🎯 Filtro de Minero")
      minero_admin_sel = st.selectbox(
          "Visualizar datos de:",
          ["Todos", "Minero 1", "Minero 2"],
          index=0
          if st.session_state["minero_admin_filtro"] == "Todos"
          else (
              1
              if st.session_state["minero_admin_filtro"] == "Minero 1"
              else 2
          ),
      )
      st.session_state["minero_admin_filtro"] = minero_admin_sel
      st.write("---")

    with st.expander("⚙️ Cambiar mi contraseña"):
      pass_actual = st.text_input(
          "Contraseña actual", type="password", key="pass_act"
      )
      nueva_pass = st.text_input(
          "Nueva contraseña", type="password", key="pass_nuev"
      )
      if st.button("Actualizar contraseña"):
        if pass_actual == obtener_password(st.session_state["rol"]):
          if nueva_pass.strip():
            actualizar_password(st.session_state["rol"], nueva_pass)
            st.session_state["mensaje_toast"] = (
                "¡Contraseña actualizada con éxito!"
            )
            st.rerun()
          else:
            st.error("La contraseña no puede estar vacía.")
        else:
          st.error("La contraseña actual no coincide.")

    if st.session_state["rol"] in ["Creador", "Minero 1", "Minero 2"]:
      st.write("---")
      with st.expander("📬 Mensaje al Administrador"):
        st.write("¿Tienes algún problema técnico o sugerencia?")
        msg_texto = st.text_area(
            "Escribe tu mensaje aquí:",
            key="msg_to_admin",
            placeholder="Ej: Hola Pablo...",
        )
        if st.button("Enviar al Admin"):
          if msg_texto.strip():
            enviar_mensaje_admin(st.session_state["rol"], msg_texto.strip())
            st.session_state["mensaje_toast"] = (
                "¡Mensaje enviado al Administrador!"
            )
            st.rerun()
          else:
            st.error("Escribe un mensaje antes de enviar.")

    st.write("---")
    if st.button("Cerrar Sesión 🚪"):
      st.session_state["rol"] = None
      st.rerun()

  # ================= VISTA ADMINISTRADOR =================
  if st.session_state["rol"] == "Admin":
    admin_filtro = st.session_state.get("minero_admin_filtro", "Todos")
    dest_filtro = None if admin_filtro == "Todos" else admin_filtro

    st.header(f"🛡️ Panel de Control del Administrador ({admin_filtro})")
    (
        pest_stats,
        pest_buzon,
        pest_anuncios,
        pest_control,
        pest_cats,
        pest_pass,
        pest_danger,
    ) = st.tabs([
        "📊 Estadísticas y Audios",
        "📬 Buzón",
        "📢 Anuncios",
        "⚙️ Control",
        "🏷️ Categorías",
        "🔑 Contraseñas",
        "🚨 Peligro",
    ])

    with pest_stats:
      st.subheader(f"📈 Rendimiento del Juego — {admin_filtro}")
      total, corregidas, puntos_totales, nota_media, medias_radar = (
          obtener_estadisticas_globales(dest_filtro)
      )
      col_t, col_c, col_p, col_m = st.columns(4)
      col_t.metric("Pruebas", total)
      col_c.metric("Completadas", corregidas)
      col_p.metric("Puntos", f"{puntos_totales}")
      col_m.metric(
          "Media", f"{round(nota_media, 2)}/100" if nota_media else "N/A"
      )

      st.write("")
      st.plotly_chart(
          generar_grafico_radar(medias_radar), use_container_width=True
      )

      st.write("---")
      st.subheader("📋 Historial Completo y Auditoría")
      todas_las_pruebas = obtener_pruebas(destinatario=dest_filtro)

      if not todas_las_pruebas:
        st.info(f"Aún no hay pruebas registradas para {admin_filtro}.")
      else:
        for p in todas_las_pruebas:
          (
              id_p,
              arch,
              nom_p,
              int_max,
              int_rest,
              resp_b,
              corr_a,
              punt,
              est,
              url_audio,
              foto_b,
              foto_a,
              dest_p,
              indic_p,
          ) = p
          color = (
              "🟡"
              if est == "Pendiente"
              else "🟠"
              if est == "Respondido"
              else "🟢"
          )

          titulo = f"{color} [{dest_p}] '{nom_p}' (Archivo: {arch})"
          with st.expander(f"{titulo} - [{est}]"):
            st.write(f"**Destinatario:** {dest_p}")
            st.write(
                f"**Intentos restantes:** {int_rest}/{int_max} (Gastados:"
                f" {int_max - int_rest})"
            )
            if indic_p:
              st.info(f"💡 **Indicaciones:** {indic_p}")
            st.write(
                f"**Justificación de B:** {resp_b if resp_b else '*Sin responder*'}"
            )
            if foto_b:
              st.image(
                  foto_b,
                  caption=f"Foto-respuesta subida por {dest_p}",
                  use_container_width=True,
              )
            st.write(
                f"**Justificación de A:** {corr_a if corr_a else '*Sin corregir*'}"
            )
            if foto_a:
              st.image(
                  foto_a,
                  caption="Foto-corrección subida por el Creador",
                  use_container_width=True,
              )
            st.write(
                f"**Nota final:** {f'{punt}/100' if punt is not None else '*Sin puntuar*'}"
            )

            st.write("🎧 **Auditar Audio (Controles Completos):**")
            st.audio(url_audio)

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
      st.write(
          "**Anuncio actual visible:**"
          f" {f'\"{anuncio_actual}\"' if anuncio_actual else '*Desactivado*'}"
      )
      nuevo_msj = st.text_area(
          "Escribe el comunicado (deja en blanco para ocultar):",
          placeholder="¡Mensaje para los amigos!",
      )

      col_an1, col_an2 = st.columns(2)
      with col_an1:
        if st.button("Actualizar / Publicar Anuncio"):
          actualizar_anuncio(nuevo_msj.strip())
          if nuevo_msj.strip() == "":
            st.session_state["mensaje_toast"] = "¡Anuncio desactivado!"
          else:
            st.session_state["mensaje_toast"] = (
                "¡Anuncio publicado correctamente!"
            )
          st.rerun()
      with col_an2:
        if st.button("Desactivar Anuncio directamente"):
          actualizar_anuncio("")
          st.session_state["mensaje_toast"] = "¡Anuncio desactivado!"
          st.rerun()

    with pest_control:
      st.subheader(f"🛠️ Ajustar Pruebas ({admin_filtro})")
      todas_control = obtener_pruebas(destinatario=dest_filtro)
      if todas_control:
        opciones_gestion = {f"[{p[12]}] '{p[2]}'": p for p in todas_control}
        seleccion_gestion = st.selectbox(
            "Selecciona una prueba:", list(opciones_gestion.keys())
        )
        prueba_g = opciones_gestion[seleccion_gestion]
        id_g, _, nom_g, int_max_g, int_rest_g, _, _, _, _, _, _, _, _, _ = (
            prueba_g
        )

        col_g1, col_g2 = st.columns(2)
        with col_g1:
          st.write("🔧 **Modificar Intentos**")
          nuevos_intentos_g = st.number_input(
              "Nuevos intentos:",
              min_value=0,
              max_value=20,
              value=int_rest_g,
              key=f"int_{id_g}",
          )
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
      else:
        st.info(f"No hay pruebas registradas bajo el filtro {admin_filtro}.")

    with pest_cats:
      st.subheader("🏷️ Gestión de Categorías")
      cats_actuales = obtener_categorias()
      st.write(f"Categorías activas actualmente: **{', '.join(cats_actuales)}**")

      col_c1, col_c2 = st.columns(2)
      with col_c1:
        st.write("➕ **Añadir nueva categoría**")
        nueva_cat = st.text_input(
            "Nombre de la categoría:",
            placeholder="Ej: Ritmo, Modos...",
            key="input_nueva_cat",
        )
        if st.button("Añadir categoría"):
          if nueva_cat.strip() and nueva_cat.strip() not in cats_actuales:
            agregar_categoria(nueva_cat.strip())
            st.session_state["mensaje_toast"] = (
                f"¡Categoría '{nueva_cat.strip()}' añadida!"
            )
            st.rerun()
          else:
            st.error("Escribe un nombre válido y que no exista.")

      with col_c2:
        st.write("🗑️ **Eliminar categoría**")
        cat_a_borrar = st.selectbox(
            "Selecciona categoría para eliminar:",
            cats_actuales,
            key="sel_del_cat",
        )
        if st.button("Eliminar categoría"):
          eliminar_categoria(cat_a_borrar)
          st.session_state["mensaje_toast"] = (
              f"¡Categoría '{cat_a_borrar}' eliminada!"
          )
          st.rerun()

    with pest_pass:
      st.write(
          f"🔑 **Creador:** `{obtener_password('Creador')}` | 🔑 **Minero 1:**"
          f" `{obtener_password('Minero 1')}` | 🔑 **Minero 2:**"
          f" `{obtener_password('Minero 2')}`"
      )
      usuario_a_modificar = st.selectbox(
          "Selecciona usuario:", ["Creador", "Minero 1", "Minero 2", "Admin"]
      )
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

  # ================= VISTA CREADOR =================
  elif st.session_state["rol"] == "Creador":
    minero_activo = st.session_state.get("minero_seleccionado", "Minero 1")
    st.header(f"🎼 Panel del Creador — {minero_activo}")

    with st.expander(f"📊 Ver radar y estadísticas de {minero_activo}"):
      _, corregidas_c, puntos_c, media_c, radar_c = (
          obtener_estadisticas_globales(destinatario=minero_activo)
      )
      col_cr1, col_cr2, col_cr3 = st.columns(3)
      col_cr1.metric("Completadas", corregidas_c)
      col_cr2.metric("Puntos", f"{puntos_c} pts")
      col_cr3.metric("Media", f"{round(media_c, 2)}/100" if media_c else "N/A")
      st.plotly_chart(generar_grafico_radar(radar_c), use_container_width=True)

    st.write("---")

    st.subheader(f"📤 Subir nueva prueba para {minero_activo}")

    if "up_nombre_creador" not in st.session_state:
      st.session_state["up_nombre_creador"] = str(uuid.uuid4())

    nombre_personalizado_input = st.text_input(
        "Nombre de la prueba (Opcional):",
        key=st.session_state["up_nombre_creador"],
    )
    st.caption(
        "ℹ️ *Si dejas este campo vacío, la prueba se nombrará automáticamente"
        " con la fecha de hoy.*"
    )

    if "up_check_obra_creador" not in st.session_state:
      st.session_state["up_check_obra_creador"] = str(uuid.uuid4())
    mostrar_campo_obra = st.checkbox(
        "Nombre de obra", key=st.session_state["up_check_obra_creador"]
    )

    nombre_obra_input = ""
    if mostrar_campo_obra:
      if "up_obra_creador" not in st.session_state:
        st.session_state["up_obra_creador"] = str(uuid.uuid4())
      nombre_obra_input = st.text_input(
          "Nombre de la obra musical del fragmento:",
          placeholder="Ej: Quinteto con piano en do mayor - Medtner",
          key=st.session_state["up_obra_creador"],
      )
      st.caption(
          f"ℹ️ *{minero_activo} solo verá este nombre tras resolver la prueba.*"
      )

    if "up_check_indic_creador" not in st.session_state:
      st.session_state["up_check_indic_creador"] = str(uuid.uuid4())
    mostrar_campo_indic = st.checkbox(
        "Indicaciones para el ejercicio",
        key=st.session_state["up_check_indic_creador"],
    )

    indicaciones_input = ""
    if mostrar_campo_indic:
      if "up_indic_creador" not in st.session_state:
        st.session_state["up_indic_creador"] = str(uuid.uuid4())
      indicaciones_input = st.text_area(
          "Indicaciones / Pistas para el Minero:",
          placeholder="Ej: Fíjate bien en el bajo a partir del compás 3...",
          key=st.session_state["up_indic_creador"],
      )
      st.caption(
          f"ℹ️ *{minero_activo} podrá leer estas indicaciones mientras"
          " resuelve el ejercicio.*"
      )

    lista_categorias_disp = ["Ninguna"] + obtener_categorias()
    categoria_elegida = st.selectbox(
        "Categoría del ejercicio:", lista_categorias_disp
    )

    if "up_audio_creador" not in st.session_state:
      st.session_state["up_audio_creador"] = str(uuid.uuid4())

    archivo_subido = st.file_uploader(
        "Elige el audio (.mp3, .wav, .acc)",
        type=["mp3", "wav", "acc"],
        key=st.session_state["up_audio_creador"],
    )

    if "up_solucion_creador" not in st.session_state:
      st.session_state["up_solucion_creador"] = str(uuid.uuid4())
    foto_solucion_subida = st.file_uploader(
        "Sube la foto con la solución (Opcional):",
        type=["png", "jpg", "jpeg"],
        key=st.session_state["up_solucion_creador"],
    )

    intentos = st.number_input(
        "¿Cuántos intentos de escucha tiene?",
        min_value=1,
        max_value=10,
        value=3,
    )

    if "up_check_creador" not in st.session_state:
      st.session_state["up_check_creador"] = str(uuid.uuid4())

    confirmacion_subida = st.checkbox(
        f"Estoy seguro de que quiero subir esta prueba para {minero_activo}.",
        key=st.session_state["up_check_creador"],
    )

    if st.button("Subir prueba al servidor", disabled=not confirmacion_subida):
      if archivo_subido is not None:
        bytes_audio = archivo_subido.read()
        nombre_archivo = archivo_subido.name

        nombre_final = nombre_personalizado_input.strip()
        if not nombre_final:
          hoy = datetime.date.today().strftime("%d/%m/%Y")
          nombre_final = f"Prueba {hoy}"

        if categoria_elegida != "Ninguna":
          nombre_final = f"[{categoria_elegida}] {nombre_final}"

        if mostrar_campo_obra and nombre_obra_input.strip():
          nombre_final = f"{nombre_final} | Obra: {nombre_obra_input.strip()}"

        url_audio = subir_archivo_storage(
            bytes_audio, nombre_archivo, "audios", archivo_subido.type
        )

        url_foto_solucion = None
        if foto_solucion_subida is not None:
          bytes_solucion = foto_solucion_subida.read()
          url_foto_solucion = subir_archivo_storage(
              bytes_solucion,
              foto_solucion_subida.name,
              "soluciones_a",
              foto_solucion_subida.type,
          )

        supabase.table("pruebas").insert({
            "nombre_archivo": nombre_archivo,
            "nombre_personalizado": nombre_final,
            "url_audio": url_audio,
            "url_foto_correccion_a": url_foto_solucion,
            "indicaciones": (
                indicaciones_input.strip()
                if mostrar_campo_indic and indicaciones_input.strip()
                else None
            ),
            "intentos_maximos": intentos,
            "intentos_restantes": intentos,
            "estado": "Pendiente",
            "destinatario": minero_activo,
        }).execute()

        # Limpia los campos y la casilla
        st.session_state["up_audio_creador"] = str(uuid.uuid4())
        st.session_state["up_solucion_creador"] = str(uuid.uuid4())
        st.session_state["up_nombre_creador"] = str(uuid.uuid4())
        st.session_state["up_check_obra_creador"] = str(uuid.uuid4())
        st.session_state["up_check_indic_creador"] = str(uuid.uuid4())
        if "up_obra_creador" in st.session_state:
          st.session_state["up_obra_creador"] = str(uuid.uuid4())
        if "up_indic_creador" in st.session_state:
          st.session_state["up_indic_creador"] = str(uuid.uuid4())
        st.session_state["up_check_creador"] = str(uuid.uuid4())

        st.session_state["mensaje_toast"] = (
            f"¡La prueba '{nombre_final}' ha sido asignada a {minero_activo}!"
        )
        st.rerun()
      else:
        st.error("Por favor, sube un archivo de audio primero.")

    st.write("---")

    st.subheader(f"🗑️ Gestionar pruebas pendientes ({minero_activo})")
    pendientes = obtener_pruebas("Pendiente", destinatario=minero_activo)
    if not pendientes:
      st.info(f"No hay pruebas pendientes de resolver para {minero_activo}.")
    else:
      for p in pendientes:
        id_p, arch, nom_p, int_max, int_rest, _, _, _, _, _, _, _, _, indic_p = (
            p
        )
        with st.expander(f"🎵 {nom_p}"):
          if indic_p:
            st.info(f"💡 **Indicaciones asociadas:** {indic_p}")
          if int_max == int_rest:
            st.write(
                f"{minero_activo} aún no ha gastado intentos. Puedes borrarla"
                " si la subiste por error."
            )
            if st.button(
                f"Borrar definitivamente '{nom_p}'", key=f"del_creador_{id_p}"
            ):
              borrar_prueba_individual(id_p)
              st.session_state["mensaje_toast"] = (
                  f"¡La prueba '{nom_p}' ha sido eliminada!"
              )
              st.rerun()
          else:
            st.warning(
                f"No puedes borrar esta prueba porque {minero_activo} ya ha"
                f" gastado intentos ({int_rest}/{int_max} restantes)."
            )

    st.write("---")

    st.subheader(f"📝 Pruebas pendientes de corregir ({minero_activo})")
    respondidas = obtener_pruebas("Respondido", destinatario=minero_activo)
    if not respondidas:
      st.info(f"No hay respuestas nuevas de {minero_activo} por corregir.")
    else:
      opciones_corregir = {f"'{r[2]}'": r for r in respondidas}
      seleccion_corregir = st.selectbox(
          "Selecciona qué respuesta quieres revisar:",
          list(opciones_corregir.keys()),
      )

      (
          id_c,
          _,
          nom_c,
          int_max_c,
          int_rest_c,
          respuesta_b_c,
          _,
          _,
          _,
          url_audio_c,
          foto_b_c,
          foto_a_c,
          _,
          indic_c,
      ) = opciones_corregir[seleccion_corregir]

      st.write(
          f"📊 **Intentos gastados por el minero:** {int_max_c - int_rest_c} de"
          f" {int_max_c}"
      )
      if indic_c:
        st.info(f"💡 **Indicaciones que tuvo el alumno:** {indic_c}")

      st.warning(
          f"Justificación de {minero_activo}: **{respuesta_b_c if respuesta_b_c else '*Sin texto de justificación*'}**"
      )

      if foto_b_c:
        st.write(f"📷 **Foto-respuesta adjunta por {minero_activo}:**")
        st.image(foto_b_c, use_container_width=True)

      st.write("🎧 **Escucha la progresión para corregir:**")
      st.audio(url_audio_c)

      if foto_a_c:
        st.write("📷 **Foto de solución subida previamente con la prueba:**")
        st.image(foto_a_c, use_container_width=True)

      st.write("### 📝 Califica la prueba")

      if "up_foto_creador" not in st.session_state:
        st.session_state["up_foto_creador"] = str(uuid.uuid4())
      if "up_texto_creador" not in st.session_state:
        st.session_state["up_texto_creador"] = str(uuid.uuid4())
      if "up_check_correccion" not in st.session_state:
        st.session_state["up_check_correccion"] = str(uuid.uuid4())

      foto_creador = st.file_uploader(
          "Sube/Actualiza una foto con la solución (Opcional):",
          type=["png", "jpg", "jpeg"],
          key=st.session_state["up_foto_creador"],
      )
      feedback = st.text_area(
          "Justificación (Opcional):",
          placeholder="Ej: ¡Buen trabajo! Pero hay que picar más piedra...",
          key=st.session_state["up_texto_creador"],
      )
      puntos_dados = st.slider(
          "Asigna una puntuación:", min_value=0, max_value=100, value=0
      )

      confirmacion_correccion = st.checkbox(
          "Confirmo que la corrección y la nota son definitivas.",
          key=st.session_state["up_check_correccion"],
      )

      if st.button("Enviar Corrección", disabled=not confirmacion_correccion):
        if feedback.strip() or foto_creador is not None or foto_a_c is not None:
          bytes_foto_creador = (
              foto_creador.read() if foto_creador is not None else None
          )
          nombre_f = (
              foto_creador.name if foto_creador is not None else "foto.jpg"
          )
          guardar_correccion_a_con_foto(
              id_c,
              feedback.strip(),
              puntos_dados,
              bytes_foto_creador,
              nombre_f,
          )

          # Limpia los campos y la casilla
          st.session_state["up_foto_creador"] = str(uuid.uuid4())
          st.session_state["up_texto_creador"] = str(uuid.uuid4())
          st.session_state["up_check_correccion"] = str(uuid.uuid4())

          st.session_state["mensaje_toast"] = (
              f"¡Calificación de {puntos_dados}/100 enviada correctamente a"
              f" {minero_activo}!"
          )
          st.rerun()
        else:
          st.error(
              "Por favor, escribe una justificación o sube una fotografía para"
              " poder enviar la corrección."
          )

    st.write("---")

    st.subheader(f"📚 Historial de pruebas corregidas ({minero_activo})")
    corregidas_creador = obtener_pruebas("Corregido", destinatario=minero_activo)
    if not corregidas_creador:
      st.info(
          f"Aún no hay pruebas corregidas en el historial de {minero_activo}."
      )
    else:
      filtro_cat = st.text_input(
          "🔍 Buscar por categoría o título (Ej: Intervalos):",
          placeholder="Filtra tus pruebas...",
          key="filtro_creador",
      )

      for c in corregidas_creador:
        (
            id_cor,
            arch,
            nom_cor,
            int_max,
            int_rest,
            resp_b,
            corr_a,
            punt_cor,
            est,
            aud_cor,
            foto_b,
            foto_a,
            _,
            indic_cor,
        ) = c

        if filtro_cat and filtro_cat.lower() not in nom_cor.lower():
          continue

        intentos_gastados = int_max - int_rest
        with st.expander(f"🎵 {nom_cor} — ⭐ Nota: {punt_cor}/100"):
          st.write(f"📊 **Intentos gastados:** {intentos_gastados} de {int_max}")
          if indic_cor:
            st.info(f"💡 **Indicaciones proporcionadas:** {indic_cor}")
          st.write(
              f"**Justificación de {minero_activo}:** {resp_b if resp_b else '*Sin texto*'}"
          )
          if foto_b:
            st.image(
                foto_b,
                caption=f"Foto-respuesta de {minero_activo}",
                use_container_width=True,
            )
          st.write("---")
          st.info(f"**Tu corrección:** {corr_a if corr_a else '*Sin texto*'}")
          if foto_a:
            st.image(
                foto_a, caption="Tu solución visual", use_container_width=True
            )
          st.audio(aud_cor)

  # ================= VISTA MINEROS (Minero 1 / Minero 2) =================
  elif st.session_state["rol"] in ["Minero 1", "Minero 2"]:
    minero_actual = st.session_state["rol"]
    st.header(f"🪨 Panel del Minero ({minero_actual})")

    _, _, puntos_totales, nota_media, medias_radar = (
        obtener_estadisticas_globales(destinatario=minero_actual)
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Tus Puntos 🏆", f"{puntos_totales} pts")
    col2.metric(
        "Nota Media ⭐",
        f"{round(nota_media, 2)}/100" if nota_media else "N/A",
    )
    col3.metric(
        "Evaluaciones 📝",
        f"{sum([1 for v in medias_radar.values() if v > 0])} activas",
    )

    st.write("")
    st.plotly_chart(
        generar_grafico_radar(medias_radar), use_container_width=True
    )

    st.write("---")

    st.subheader("🎵 Zonas de Minado (Pruebas disponibles)")
    pruebas_disp = obtener_pruebas("Pendiente", destinatario=minero_actual)

    if not pruebas_disp:
      st.info("¡Buen trabajo! No tienes pruebas pendientes de resolver.")
    else:
      opciones_pruebas = {}
      for p in pruebas_disp:
        nombre_mostrado = (
            p[2].split(" | Obra:")[0] if " | Obra:" in p[2] else p[2]
        )
        opciones_pruebas[f"'{nombre_mostrado}'"] = p

      seleccion = st.selectbox(
          "Selecciona la prueba:", list(opciones_pruebas.keys())
      )

      (
          id_prueba,
          _,
          nom_p,
          int_max,
          intentos_restantes,
          _,
          _,
          _,
          _,
          url_audio,
          _,
          _,
          _,
          indic_activa,
      ) = opciones_pruebas[seleccion]

      st.write(f"### 📊 Intentos: **{intentos_restantes} / {int_max}**")

      if indic_activa:
        st.info(f"💡 **Indicaciones del ejercicio:**\n\n{indic_activa}")

      llave = f"reproducir_{id_prueba}"
      if llave not in st.session_state:
        st.session_state[llave] = False

      if st.session_state[llave]:
        reproductor_html = f"""
                <div style="background-color: #1E1E1E; padding: 10px 15px; border-radius: 8px; text-align: center; border: 1px solid #FF4B4B; color: white; font-family: sans-serif; box-sizing: border-box;">
                    <span style="font-size: 20px; display: block; margin-bottom: 2px;">🎵</span>
                    <strong>Reproduciendo audio...</strong>
                    <p style="font-size: 11px; color: #888; margin-top: 2px; margin-bottom: 0px;">Escucha atentamente. Solo sonará una vez.</p>
                    <audio id="minerAudio" autoplay>
                        <source src="{url_audio}">
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
        st.components.v1.html(reproductor_html, height=100)

        if st.button("Terminar audio ⏹️"):
          st.session_state[llave] = False
          st.rerun()

        st.write("")
        st.warning(
            "⚠️ No cierres ni cambies esta pestaña mientras el audio se está"
            " reproduciendo, o se consumirá otro intento."
        )

      elif intentos_restantes > 0:
        if st.button("🔊 Gastar 1 intento y escuchar"):
          restar_intento(id_prueba, intentos_restantes)
          st.session_state[llave] = True
          st.rerun()

      else:
        st.error("❌ ¡Te has quedado sin intentos para esta prueba!")

      st.write("---")

      st.write("### 📝 Envía tu respuesta")

      if "up_foto_minero" not in st.session_state:
        st.session_state["up_foto_minero"] = str(uuid.uuid4())
      if "up_texto_minero" not in st.session_state:
        st.session_state["up_texto_minero"] = str(uuid.uuid4())
      if "up_check_minero" not in st.session_state:
        st.session_state["up_check_minero"] = str(uuid.uuid4())

      foto_respuesta = st.file_uploader(
          "Sube una foto de tu cifrado (Opcional):",
          type=["png", "jpg", "jpeg"],
          key=st.session_state["up_foto_minero"],
      )
      respuesta_usuario = st.text_input(
          "Justificación (Opcional):",
          placeholder="Ej: El primer acorde es tónica...",
          key=st.session_state["up_texto_minero"],
      )

      confirmacion_respuesta = st.checkbox(
          "Estoy seguro de que quiero enviar esta respuesta.",
          key=st.session_state["up_check_minero"],
      )

      if st.button("Enviar respuesta", disabled=not confirmacion_respuesta):
        if respuesta_usuario.strip() or foto_respuesta is not None:
          bytes_foto = (
              foto_respuesta.read() if foto_respuesta is not None else None
          )
          nombre_f = (
              foto_respuesta.name if foto_respuesta is not None else "foto.jpg"
          )
          guardar_respuesta_b_con_foto(
              id_prueba, respuesta_usuario.strip(), bytes_foto, nombre_f
          )
          if f"reproducir_{id_prueba}" in st.session_state:
            del st.session_state[f"reproducir_{id_prueba}"]

          # Limpia los campos y la casilla
          st.session_state["up_foto_minero"] = str(uuid.uuid4())
          st.session_state["up_texto_minero"] = str(uuid.uuid4())
          st.session_state["up_check_minero"] = str(uuid.uuid4())

          st.session_state["mensaje_toast"] = (
              "¡Tu respuesta se ha enviado correctamente!"
          )
          st.rerun()
        else:
          st.error(
              "Por favor, escribe una justificación o sube una fotografía para"
              " poder enviar tu respuesta."
          )

    st.write("---")

    st.subheader("🎒 Historial de prácticas")
    corregidas = obtener_pruebas("Corregido", destinatario=minero_actual)

    if not corregidas:
      st.info("Aún no tienes pruebas corregidas.")
    else:
      for c in corregidas:
        (
            id_cor,
            _,
            nom_cor,
            _,
            _,
            resp_b,
            corr_a,
            punt_cor,
            _,
            aud_cor,
            foto_b,
            foto_a,
            _,
            indic_cor,
        ) = c
        with st.expander(f"🎵 {nom_cor} — ⭐ Nota: {punt_cor}/100"):
          if indic_cor:
            st.info(f"💡 **Indicaciones recibidas:** {indic_cor}")
          st.write(f"**Tu respuesta:** {resp_b if resp_b else '*Sin texto*'}")
          if foto_b:
            st.image(
                foto_b,
                caption="Tu foto-respuesta enviada",
                use_container_width=True,
            )
          st.write("---")
          st.info(
              f"**Corrección:** {corr_a if corr_a else '*Sin texto*'}"
          )
          if foto_a:
            st.image(
                foto_a,
                caption="Solución visual del Creador",
                use_container_width=True,
            )
          st.audio(aud_cor)
