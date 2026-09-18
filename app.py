import base64
import datetime
import io
import math
import random
import struct
import time
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

# --- MAPEO VISUAL DE NOMBRES ---
NOMBRE_MINERO = {
    "Minero 1": "Minero Óscar",
    "Minero 2": "Minero Pablo"
}

def formatear_nombre_minero(rol_db):
  return NOMBRE_MINERO.get(rol_db, rol_db)


# --- SÍNTESIS NATIVA DE AUDIO (WAV PURO EN MEMORIA) ---
NOTAS_BASE = ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"]

def obtener_frecuencia(nota_nombre, octava=4):
  idx = NOTAS_BASE.index(nota_nombre)
  semitonos_desde_la4 = (idx - 9) + (octava - 4) * 12
  return 440.0 * (2.0 ** (semitonos_desde_la4 / 12.0))

def generar_onda_nota(frecuencia, duracion, timbre="piano", sample_rate=22050):
  num_samples = int(sample_rate * duracion)
  samples = []

  for i in range(num_samples):
    t = i / sample_rate
    # Envolvente básica
    if t < 0.03:
      env = t / 0.03
    else:
      decay_factor = 2.5 if timbre == "piano" else 0.8
      env = math.exp(-decay_factor * (t - 0.03))

    # Síntesis tímbrica con armónicos
    if timbre == "senoide":
      val = math.sin(2 * math.pi * frecuencia * t)
    elif timbre == "violin":
      val = (
          0.6 * math.sin(2 * math.pi * frecuencia * t)
          + 0.3 * math.sin(4 * math.pi * frecuencia * t)
          + 0.15 * math.sin(6 * math.pi * frecuencia * t)
          + 0.1 * math.sin(8 * math.pi * frecuencia * t)
      )
    elif timbre == "voz":
      val = (
          0.5 * math.sin(2 * math.pi * frecuencia * t)
          + 0.35 * math.sin(6 * math.pi * frecuencia * t)
          + 0.2 * math.sin(8 * math.pi * frecuencia * t)
      )
    else:  # piano
      val = (
          0.65 * math.sin(2 * math.pi * frecuencia * t)
          + 0.25 * math.sin(4 * math.pi * frecuencia * t)
          + 0.10 * math.sin(6 * math.pi * frecuencia * t)
      )

    muestra = int(max(min(val * env * 0.75, 0.99), -0.99) * 32767)
    samples.append(muestra)

  return samples

def crear_wav_bytes(samples, sample_rate=22050):
  buffer = io.BytesIO()
  num_channels = 1
  sampwidth = 2
  byte_rate = sample_rate * num_channels * sampwidth
  block_align = num_channels * sampwidth
  data_size = len(samples) * sampwidth

  buffer.write(b"RIFF")
  buffer.write(struct.pack("<I", 36 + data_size))
  buffer.write(b"WAVE")
  buffer.write(b"fmt ")
  buffer.write(struct.pack("<IHHIIHH", 16, 1, num_channels, sample_rate, byte_rate, block_align, 16))
  buffer.write(b"data")
  buffer.write(struct.pack("<I", data_size))

  for s in samples:
    buffer.write(struct.pack("<h", s))

  return buffer.getvalue()

def reproducir_audio_sintetizado(frecuencia, timbre="piano", duracion=1.2):
  samples = generar_onda_nota(frecuencia, duracion, timbre=timbre)
  wav_bytes = crear_wav_bytes(samples)
  b64 = base64.b64encode(wav_bytes).decode()
  uid_audio = uuid.uuid4().hex
  html = f"""
  <audio id="snd_{uid_audio}" autoplay style="display: none;">
      <source src="data:audio/wav;base64,{b64}" type="audio/wav">
  </audio>
  <script>
      var a = document.getElementById("snd_{uid_audio}");
      if(a) {{ a.play().catch(function(e){{}}); }}
  </script>
  """
  st.components.v1.html(html, height=0, width=0)

def reproducir_secuencia_sintetizada(lista_frecuencias, timbre="piano", duracion=0.7, silencio_inter=0.3):
  samples_totales = []
  sample_rate = 22050
  num_silencio = int(sample_rate * silencio_inter)

  for freq in lista_frecuencias:
    samples_nota = generar_onda_nota(freq, duracion, timbre=timbre, sample_rate=sample_rate)
    samples_totales.extend(samples_nota)
    samples_totales.extend([0] * num_silencio)

  wav_bytes = crear_wav_bytes(samples_totales, sample_rate=sample_rate)
  b64 = base64.b64encode(wav_bytes).decode()
  uid_audio = uuid.uuid4().hex
  html = f"""
  <audio id="snd_{uid_audio}" autoplay style="display: none;">
      <source src="data:audio/wav;base64,{b64}" type="audio/wav">
  </audio>
  <script>
      var a = document.getElementById("snd_{uid_audio}");
      if(a) {{ a.play().catch(function(e){{}}); }}
  </script>
  """
  st.components.v1.html(html, height=0, width=0)

def resetear_gimnasio():
  """Limpia todos los contadores, estados y métricas acumuladas del gimnasio auditivo"""
  st.session_state["wong_stats"] = {"total": 0, "aciertos": 0}
  st.session_state["wong_ensayo_activo"] = None
  st.session_state["espectral_stats"] = {"total": 0, "aciertos": 0}
  st.session_state["espectral_ensayo"] = None
  st.session_state["memoria_secuencia"] = []
  st.session_state["memoria_usuario"] = []


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
  try:
    res = (
        supabase.table("categorias")
        .select("nombre")
        .order("id", desc=False)
        .execute()
    )
    if res.data and len(res.data) > 0:
      return [c["nombre"] for c in res.data]
  except Exception:
    pass
  return [
      "Intervalos",
      "Progresiones",
      "Fragmentos",
      "Escalas",
      "Dictado",
      "Acordes",
  ]


def agregar_categoria(nombre):
  try:
    supabase.table("categorias").insert({"nombre": nombre.strip()}).execute()
    return True
  except Exception as e:
    st.error(f"Error al añadir categoría: {e}")
    return False


def eliminar_categoria(nombre):
  try:
    supabase.table("categorias").delete().eq("nombre", nombre).execute()
    return True
  except Exception as e:
    st.error(f"Error al eliminar categoría: {e}")
    return False


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

  valores = [round(float(medias_dict[c]), 1) for c in categorias]

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
              gridcolor="#333333",
          ),
          angularaxis=dict(
              tickfont=dict(size=13, color="#FFFFFF"),
              gridcolor="#333333",
          ),
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

if "vista_publica" not in st.session_state:
  st.session_state["vista_publica"] = "login"

# Inicialización preventiva de variables del gimnasio
if "wong_stats" not in st.session_state:
  st.session_state["wong_stats"] = {"total": 0, "aciertos": 0}
if "wong_ensayo_activo" not in st.session_state:
  st.session_state["wong_ensayo_activo"] = None
if "espectral_stats" not in st.session_state:
  st.session_state["espectral_stats"] = {"total": 0, "aciertos": 0}
if "espectral_ensayo" not in st.session_state:
  st.session_state["espectral_ensayo"] = None
if "memoria_secuencia" not in st.session_state:
  st.session_state["memoria_secuencia"] = []
if "memoria_usuario" not in st.session_state:
  st.session_state["memoria_usuario"] = []

# --- LÓGICA DE MENSAJES FLOTANTES (TOASTS) ---
if "mensaje_toast" in st.session_state:
  st.toast(st.session_state["mensaje_toast"], icon="✅")
  del st.session_state["mensaje_toast"]

# --- PANTALLA DE INICIO (LOGIN O ENTRENAMIENTO AUDITIVO) ---
if st.session_state["rol"] is None:

  # 1. PANTALLA DE INTRODUCCIÓN TEÓRICA
  if st.session_state["vista_publica"] == "entrenamiento_intro":
    st.subheader("📚 Marco Científico del Oído Absoluto en Adultos")
    
    st.markdown("""
> * **Wong, Y. K., et al. (2025).** *Learning fast and accurate absolute pitch judgment in adulthood.* Psychonomic Bulletin & Review, 32, 1676–1688. (Demostró que adultos entrenados con protocolos gamificados alcanzan precisión ≥90% y tiempos de respuesta típicos de poseedores de oído absoluto de cuna).
> * **Van Hedger, S. C., Heald, S. L., & Nusbaum, H. C. (2019).** *Absolute pitch can be learned by some adults.* PLOS ONE, 14(9), e0223047. (Estudio pionero donde adultos alcanzaron niveles genuinos de categorización sin depender de oído relativo en 8 semanas).
> * **Van Hedger, S. C., et al. (2015).** *Auditory working memory as a predictor of absolute pitch learning in adults.* Cognition, 140, 95–110.
> * **Levitin, D. J. (1994).** *Absolute memory for musical pitch: Evidence from the production of learned melodies.* Perception & Psychophysics, 56(4), 414–423. (Descubrimiento del almacenamiento de frecuencia absoluta en memoria implícita en personas sin oído absoluto).
    """)
    
    st.write("---")
    col_avanzar, col_volver = st.columns([2, 1])
    with col_avanzar:
      if st.button("🚀 Entendido, acceder al Gimnasio Auditivo"):
        st.session_state["vista_publica"] = "entrenamiento_gym"
        st.rerun()
    with col_volver:
      if st.button("⬅️ Volver al Login"):
        resetear_gimnasio()
        st.session_state["vista_publica"] = "login"
        st.rerun()

  # 2. PANTALLA DEL GIMNASIO DE OÍDO ABSOLUTO
  elif st.session_state["vista_publica"] == "entrenamiento_gym":
    st.subheader("🧠 Gimnasio de Oído Absoluto (Laboratorio Neuroauditivo)")
    st.caption("Protocolos interactivos en tiempo real con síntesis de audio nativa.")

    if "ejercicio_gym_activo" not in st.session_state:
      st.session_state["ejercicio_gym_activo"] = "wong"

    col_btn1, col_btn2, col_btn3 = st.columns(3)
    with col_btn1:
      if st.button("🎯 Método Wong / Van Hedger", use_container_width=True):
        st.session_state["ejercicio_gym_activo"] = "wong"
        st.rerun()
    with col_btn2:
      if st.button("🎻 Desacoplo Espectral", use_container_width=True):
        st.session_state["ejercicio_gym_activo"] = "espectral"
        st.rerun()
    with col_btn3:
      if st.button("⚡ Memoria de Trabajo", use_container_width=True):
        st.session_state["ejercicio_gym_activo"] = "memoria"
        st.rerun()

    st.write("---")

    # ================= EJERCICIO 1: WONG / VAN HEDGER =================
    if st.session_state["ejercicio_gym_activo"] == "wong":
      st.markdown("### 🎯 Protocolo Wong / Van Hedger (Target vs. Distractor)")
      st.info(
          "**Regla neuroauditiva:** Responde en menos de 2.0 segundos. "
          "Si tardas más, se anula la memoria de croma y tu cerebro recurre al cálculo interválico."
      )

      if "wong_target" not in st.session_state:
        st.session_state["wong_target"] = "Do"

      col_w1, col_w2 = st.columns([1, 2])
      with col_w1:
        target_sel = st.selectbox(
            "Nota Target (Categoría):",
            ["Do", "Fa", "Sol", "La"],
            index=["Do", "Fa", "Sol", "La"].index(st.session_state["wong_target"]),
            key="sel_wong_target"
        )
        if target_sel != st.session_state["wong_target"]:
          st.session_state["wong_target"] = target_sel
          st.session_state["wong_stats"] = {"total": 0, "aciertos": 0}
          st.session_state["wong_ensayo_activo"] = None
          st.rerun()

      with col_w2:
        acc = (st.session_state["wong_stats"]["aciertos"] / st.session_state["wong_stats"]["total"] * 100) if st.session_state["wong_stats"]["total"] > 0 else 0.0
        st.metric(
            label="Precisión Acumulada (Meta: ≥90%)",
            value=f"{round(acc, 1)}%",
            delta=f"{st.session_state['wong_stats']['aciertos']}/{st.session_state['wong_stats']['total']} ensayos"
        )

      st.write("")
      col_p1, _ = st.columns([1, 1])
      with col_p1:
        if st.button("🔊 Lanzar nuevo ensayo", use_container_width=True):
          es_target = random.choice([True, False])
          if es_target:
            nota_tocar = st.session_state["wong_target"]
          else:
            notas_distractoras = [n for n in NOTAS_BASE if n != st.session_state["wong_target"]]
            nota_tocar = random.choice(notas_distractoras)
          
          freq = obtener_frecuencia(nota_tocar, octava=4)
          st.session_state["wong_ensayo_activo"] = {
              "nota": nota_tocar,
              "es_target": es_target,
              "timestamp": time.time(),
              "freq": freq
          }
          reproducir_audio_sintetizado(freq, timbre="piano", duracion=1.0)

      if st.session_state["wong_ensayo_activo"]:
        st.write("---")
        st.write("⏱️ **Elige rápidamente antes de 2 segundos:**")
        col_resp1, col_resp2 = st.columns(2)
        
        with col_resp1:
          if st.button(f"🎯 Es {st.session_state['wong_target']}", use_container_width=True):
            tiempo_reaccion = time.time() - st.session_state["wong_ensayo_activo"]["timestamp"]
            es_target_real = st.session_state["wong_ensayo_activo"]["es_target"]
            st.session_state["wong_stats"]["total"] += 1
            
            if tiempo_reaccion > 2.0:
              st.error(f"⌛ ¡Demasiado lento! ({round(tiempo_reaccion, 2)}s). Límite de ventana absoluta superado.")
            elif es_target_real:
              st.session_state["wong_stats"]["aciertos"] += 1
              st.success(f"✅ ¡Correcto! Tiempo: {round(tiempo_reaccion, 2)}s.")
            else:
              st.error(f"❌ Fallaste. Era {st.session_state['wong_ensayo_activo']['nota']}.")
            st.session_state["wong_ensayo_activo"] = None

        with col_resp2:
          if st.button("🚫 Fuera de rango / Distractor", use_container_width=True):
            tiempo_reaccion = time.time() - st.session_state["wong_ensayo_activo"]["timestamp"]
            es_target_real = st.session_state["wong_ensayo_activo"]["es_target"]
            st.session_state["wong_stats"]["total"] += 1
            
            if tiempo_reaccion > 2.0:
              st.error(f"⌛ ¡Demasiado lento! ({round(tiempo_reaccion, 2)}s). Límite de ventana absoluta superado.")
            elif not es_target_real:
              st.session_state["wong_stats"]["aciertos"] += 1
              st.success(f"✅ ¡Bien visto! Era {st.session_state['wong_ensayo_activo']['nota']} en {round(tiempo_reaccion, 2)}s.")
            else:
              st.error(f"❌ Incorrecto. Era exactamente la nota target ({st.session_state['wong_target']}).")
            st.session_state["wong_ensayo_activo"] = None

    # ================= EJERCICIO 2: DESACOPLO ESPECTRAL =================
    elif st.session_state["ejercicio_gym_activo"] == "espectral":
      st.markdown("### 🎻 Desacoplo Espectral (Invarianza de Croma)")
      st.info(
          "Entrena la identificación de la clase de altura pura (*pitch chroma*) abstrayéndote de los timbres "
          "y de la octava física (3, 4 o 5)."
      )

      col_es1, col_es2 = st.columns([1, 1])
      with col_es1:
        if st.button("🎲 Generar sonido aleatorio", use_container_width=True):
          nota = random.choice(NOTAS_BASE)
          octava = random.choice([3, 4, 5])
          timbre = random.choice(["piano", "senoide", "violin", "voz"])
          freq = obtener_frecuencia(nota, octava)
          
          st.session_state["espectral_ensayo"] = {
              "nota": nota,
              "octava": octava,
              "timbre": timbre,
              "freq": freq
          }
          reproducir_audio_sintetizado(freq, timbre=timbre, duracion=1.3)

      with col_es2:
        acc_esp = (st.session_state["espectral_stats"]["aciertos"] / st.session_state["espectral_stats"]["total"] * 100) if st.session_state["espectral_stats"]["total"] > 0 else 0.0
        st.metric("Aciertos globales", f"{round(acc_esp, 1)}%", f"{st.session_state['espectral_stats']['aciertos']}/{st.session_state['espectral_stats']['total']}")

      if st.session_state["espectral_ensayo"]:
        st.caption(f"Timbre: **{st.session_state['espectral_ensayo']['timbre'].capitalize()}** | Octava: **{st.session_state['espectral_ensayo']['octava']}**")
        if st.button("🔁 Re-escuchar sonido actual"):
          reproducir_audio_sintetizado(
              st.session_state["espectral_ensayo"]["freq"],
              timbre=st.session_state["espectral_ensayo"]["timbre"],
              duracion=1.3
          )

        st.write("¿Qué nota ha sonado?")
        cols_n1 = st.columns(6)
        for i, n in enumerate(NOTAS_BASE[:6]):
          with cols_n1[i]:
            if st.button(n, key=f"btn_esp_{n}", use_container_width=True):
              st.session_state["espectral_stats"]["total"] += 1
              if n == st.session_state["espectral_ensayo"]["nota"]:
                st.session_state["espectral_stats"]["aciertos"] += 1
                st.success(f"🎉 ¡Exacto! Era {n}{st.session_state['espectral_ensayo']['octava']}.")
              else:
                st.error(f"❌ Fallo. La nota correcta era {st.session_state['espectral_ensayo']['nota']}{st.session_state['espectral_ensayo']['octava']}.")
              st.session_state["espectral_ensayo"] = None

        cols_n2 = st.columns(6)
        for i, n in enumerate(NOTAS_BASE[6:]):
          with cols_n2[i]:
            if st.button(n, key=f"btn_esp_{n}", use_container_width=True):
              st.session_state["espectral_stats"]["total"] += 1
              if n == st.session_state["espectral_ensayo"]["nota"]:
                st.session_state["espectral_stats"]["aciertos"] += 1
                st.success(f"🎉 ¡Exacto! Era {n}{st.session_state['espectral_ensayo']['octava']}.")
              else:
                st.error(f"❌ Fallo. La nota correcta era {st.session_state['espectral_ensayo']['nota']}{st.session_state['espectral_ensayo']['octava']}.")
              st.session_state["espectral_ensayo"] = None

    # ================= EJERCICIO 3: MEMORIA DE TRABAJO AUDITIVA =================
    elif st.session_state["ejercicio_gym_activo"] == "memoria":
      st.markdown("### ⚡ Entrenamiento de Memoria de Trabajo Auditiva")
      st.info(
          "Protocolo de retención en memoria operativa (Van Hedger et al., 2015, 2019): "
          "Escucha la secuencia, retenla en mente durante el silencio y reconstrúyela nota a nota."
      )

      longitud_sec = st.slider("Longitud de la secuencia:", min_value=3, max_value=5, value=3)

      col_m1, col_m2 = st.columns(2)
      with col_m1:
        if st.button("🎧 Generar y Escuchar Secuencia", use_container_width=True):
          secuencia = [random.choice(NOTAS_BASE) for _ in range(longitud_sec)]
          st.session_state["memoria_secuencia"] = secuencia
          st.session_state["memoria_usuario"] = []
          frecuencias = [obtener_frecuencia(n, octava=4) for n in secuencia]
          reproducir_secuencia_sintetizada(frecuencias, timbre="piano", duracion=0.7, silencio_inter=0.3)

      with col_m2:
        if st.session_state["memoria_secuencia"]:
          if st.button("🔁 Re-escuchar secuencia", use_container_width=True):
            frecuencias = [obtener_frecuencia(n, octava=4) for n in st.session_state["memoria_secuencia"]]
            reproducir_secuencia_sintetizada(frecuencias, timbre="piano", duracion=0.7, silencio_inter=0.3)

      if st.session_state["memoria_secuencia"]:
        st.write("---")
        st.write(f"Tu secuencia: **{' - '.join(st.session_state['memoria_usuario']) if st.session_state['memoria_usuario'] else '*(Vacía)*'}**")
        
        cols_k1 = st.columns(6)
        for i, n in enumerate(NOTAS_BASE[:6]):
          with cols_k1[i]:
            if st.button(n, key=f"mem_k_{n}", use_container_width=True):
              if len(st.session_state["memoria_usuario"]) < len(st.session_state["memoria_secuencia"]):
                st.session_state["memoria_usuario"].append(n)
                reproducir_audio_sintetizado(obtener_frecuencia(n, 4), timbre="piano", duracion=0.5)
                st.rerun()

        cols_k2 = st.columns(6)
        for i, n in enumerate(NOTAS_BASE[6:]):
          with cols_k2[i]:
            if st.button(n, key=f"mem_k_{n}", use_container_width=True):
              if len(st.session_state["memoria_usuario"]) < len(st.session_state["memoria_secuencia"]):
                st.session_state["memoria_usuario"].append(n)
                reproducir_audio_sintetizado(obtener_frecuencia(n, 4), timbre="piano", duracion=0.5)
                st.rerun()

        st.write("")
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
          if st.button("🧹 Borrar última nota"):
            if st.session_state["memoria_usuario"]:
              st.session_state["memoria_usuario"].pop()
              st.rerun()

        with col_ctrl2:
          if len(st.session_state["memoria_usuario"]) == len(st.session_state["memoria_secuencia"]):
            if st.button("✅ Comprobar Secuencia", use_container_width=True):
              if st.session_state["memoria_usuario"] == st.session_state["memoria_secuencia"]:
                st.success(f"🏆 ¡Secuencia correcta!: {' - '.join(st.session_state['memoria_secuencia'])}")
              else:
                st.error(f"❌ Fallaste. La secuencia era: {' - '.join(st.session_state['memoria_secuencia'])}")
              st.session_state["memoria_secuencia"] = []
              st.session_state["memoria_usuario"] = []

    st.write("---")
    if st.button("⬅️ Salir del Gimnasio y volver al Login"):
      resetear_gimnasio()
      st.session_state["vista_publica"] = "login"
      st.rerun()

  # 3. PANTALLA DE LOGIN CONVENCIONAL
  else:
    st.write("### 🔑 Identifícate para entrar a la mina 🔑")
    opciones_roles = ["Selecciona una opción", "Creador", "Minero Óscar", "Minero Pablo", "Administrador"]
    rol_elegido = st.selectbox("¿Quién eres?", opciones_roles)

    if rol_elegido != "Selecciona una opción":
      password = st.text_input("Introduce tu contraseña de acceso:", type="password")
      if st.button("Entrar"):
        rol_db = (
            "Creador"
            if rol_elegido == "Creador"
            else "Admin"
            if rol_elegido == "Administrador"
            else "Minero 1"
            if rol_elegido == "Minero Óscar"
            else "Minero 2"
        )
        if password == obtener_password(rol_db):
          st.session_state["rol"] = rol_db
          st.session_state["mensaje_toast"] = f"¡Acceso concedido como {formatear_nombre_minero(rol_db)}!"
          st.rerun()
        else:
          st.error("❌ Contraseña incorrecta. Inténtalo de nuevo.")

    st.write("---")
    st.markdown("#### 🎧 Módulo Abierto")
    if st.button("Entrenamiento auditivo", help="Acceso directo al marco científico y gimnasio interactivo de oído absoluto"):
      st.session_state["vista_publica"] = "entrenamiento_intro"
      st.rerun()

# --- USUARIO AUTENTICADO ---
else:
  anuncio_actual = obtener_anuncio()
  if anuncio_actual:
    st.info(f"📢 **Anuncio de la Mina:** {anuncio_actual}")

  with st.sidebar:
    st.write(f"Conectado como: **{formatear_nombre_minero(st.session_state['rol'])}**")
    st.write("---")

    # Menú contextual para el Creador
    if st.session_state["rol"] == "Creador":
      if "minero_seleccionado" not in st.session_state:
        st.session_state["minero_seleccionado"] = "Minero 1"

      st.subheader("🎯 Minero de trabajo")
      minero_opciones_visibles = ["Minero Óscar", "Minero Pablo"]
      minero_sel_visual = st.selectbox(
          "Gestionar ejercicios para:",
          minero_opciones_visibles,
          index=0
          if st.session_state["minero_seleccionado"] == "Minero 1"
          else 1,
      )
      st.session_state["minero_seleccionado"] = "Minero 1" if minero_sel_visual == "Minero Óscar" else "Minero 2"
      st.write("---")

    # Menú contextual para el Admin
    if st.session_state["rol"] == "Admin":
      if "minero_admin_filtro" not in st.session_state:
        st.session_state["minero_admin_filtro"] = "Todos"

      st.subheader("🎯 Filtro de Minero")
      admin_opciones_visibles = ["Todos", "Minero Óscar", "Minero Pablo"]
      index_actual = 0 if st.session_state["minero_admin_filtro"] == "Todos" else (1 if st.session_state["minero_admin_filtro"] == "Minero 1" else 2)
      minero_admin_sel_visual = st.selectbox(
          "Visualizar datos de:",
          admin_opciones_visibles,
          index=index_actual,
      )
      st.session_state["minero_admin_filtro"] = "Todos" if minero_admin_sel_visual == "Todos" else ("Minero 1" if minero_admin_sel_visual == "Minero Óscar" else "Minero 2")
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
      st.session_state["vista_publica"] = "login"
      st.rerun()

  # ================= VISTA ADMINISTRADOR =================
  if st.session_state["rol"] == "Admin":
    admin_filtro = st.session_state.get("minero_admin_filtro", "Todos")
    dest_filtro = None if admin_filtro == "Todos" else admin_filtro
    admin_filtro_visual = formatear_nombre_minero(admin_filtro)

    st.header(f"🛡️ Panel de Control del Administrador ({admin_filtro_visual})")
    (
        pest_stats,
        pest_buzon,
        pest_anuncios,
        pest_control,
        pest_pass,
        pest_danger,
    ) = st.tabs([
        "📊 Estadísticas y Audios",
        "📬 Buzón",
        "📢 Anuncios",
        "⚙️ Control",
        "🔑 Contraseñas",
        "🚨 Peligro",
    ])

    with pest_stats:
      st.subheader(f"📈 Rendimiento del Juego — {admin_filtro_visual}")
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
        st.info(f"Aún no hay pruebas registradas para {admin_filtro_visual}.")
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

          dest_p_visual = formatear_nombre_minero(dest_p)
          titulo = f"{color} [{dest_p_visual}] '{nom_p}' (Archivo: {arch})"
          with st.expander(f"{titulo} - [{est}]"):
            st.write(f"**Destinatario:** {dest_p_visual}")
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
                  caption=f"Foto-respuesta subida por {dest_p_visual}",
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
          remitente_visual = formatear_nombre_minero(remitente)
          with st.container():
            st.markdown(f"**De:** `{remitente_visual}` | **Fecha:** {fecha}")
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
      st.subheader(f"🛠️ Ajustar Pruebas ({admin_filtro_visual})")
      todas_control = obtener_pruebas(destinatario=dest_filtro)
      if todas_control:
        opciones_gestion = {f"[{formatear_nombre_minero(p[12])}] '{p[2]}'": p for p in todas_control}
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
        st.info(f"No hay pruebas registradas bajo el filtro {admin_filtro_visual}.")

      st.write("---")
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
            if agregar_categoria(nueva_cat.strip()):
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
          if eliminar_categoria(cat_a_borrar):
            st.session_state["mensaje_toast"] = (
                f"¡Categoría '{cat_a_borrar}' eliminada!"
            )
            st.rerun()

    with pest_pass:
      st.write(
          f"🔑 **Creador:** `{obtener_password('Creador')}` | 🔑 **Minero Óscar:**"
          f" `{obtener_password('Minero 1')}` | 🔑 **Minero Pablo:**"
          f" `{obtener_password('Minero 2')}`"
      )
      usuario_a_modificar_visual = st.selectbox(
          "Selecciona usuario:", ["Creador", "Minero Óscar", "Minero Pablo", "Admin"]
      )
      usuario_a_modificar = (
          "Minero 1" if usuario_a_modificar_visual == "Minero Óscar"
          else ("Minero 2" if usuario_a_modificar_visual == "Minero Pablo" else usuario_a_modificar_visual)
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
    minero_activo_visual = formatear_nombre_minero(minero_activo)
    st.header(f"🎼 Panel del Creador — {minero_activo_visual}")

    with st.expander(f"📊 Ver radar y estadísticas de {minero_activo_visual}"):
      _, corregidas_c, puntos_c, media_c, radar_c = (
          obtener_estadisticas_globales(destinatario=minero_activo)
      )
      col_cr1, col_cr2, col_cr3 = st.columns(3)
      col_cr1.metric("Completadas", corregidas_c)
      col_cr2.metric("Puntos", f"{puntos_c} pts")
      col_cr3.metric("Media", f"{round(media_c, 2)}/100" if media_c else "N/A")
      st.plotly_chart(generar_grafico_radar(radar_c), use_container_width=True)

    st.write("---")

    st.subheader(f"📤 Subir nueva prueba para {minero_activo_visual}")

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
          f"ℹ️ *{minero_activo_visual} solo verá este nombre tras resolver la prueba.*"
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
          f"ℹ️ *{minero_activo_visual} podrá leer estas indicaciones mientras"
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
        f"Estoy seguro de que quiero subir esta prueba para {minero_activo_visual}.",
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
            f"¡La prueba '{nombre_final}' ha sido asignada a {minero_activo_visual}!"
        )
        st.rerun()
      else:
        st.error("Por favor, sube un archivo de audio primero.")

    st.write("---")

    st.subheader(f"🗑️ Gestionar pruebas pendientes ({minero_activo_visual})")
    pendientes = obtener_pruebas("Pendiente", destinatario=minero_activo)
    if not pendientes:
      st.info(f"No hay pruebas pendientes de resolver para {minero_activo_visual}.")
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
                f"{minero_activo_visual} aún no ha gastado intentos. Puedes borrarla"
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
                f"No puedes borrar esta prueba porque {minero_activo_visual} ya ha"
                f" gastado intentos ({int_rest}/{int_max} restantes)."
            )

    st.write("---")

    st.subheader(f"📝 Pruebas pendientes de corregir ({minero_activo_visual})")
    respondidas = obtener_pruebas("Respondido", destinatario=minero_activo)
    if not respondidas:
      st.info(f"No hay respuestas nuevas de {minero_activo_visual} por corregir.")
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
          f"Justificación de {minero_activo_visual}: **{respuesta_b_c if respuesta_b_c else '*Sin texto de justificación*'}**"
      )

      if foto_b_c:
        st.write(f"📷 **Foto-respuesta adjunta por {minero_activo_visual}:**")
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
              f" {minero_activo_visual}!"
          )
          st.rerun()
        else:
          st.error(
              "Por favor, escribe una justificación o sube una fotografía para"
              " poder enviar la corrección."
          )

    st.write("---")

    st.subheader(f"📚 Historial de pruebas corregidas ({minero_activo_visual})")
    corregidas_creador = obtener_pruebas("Corregido", destinatario=minero_activo)
    if not corregidas_creador:
      st.info(
          f"Aún no hay pruebas corregidas en el historial de {minero_activo_visual}."
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
              f"**Justificación de {minero_activo_visual}:** {resp_b if resp_b else '*Sin texto*'}"
          )
          if foto_b:
            st.image(
                foto_b,
                caption=f"Foto-respuesta de {minero_activo_visual}",
                use_container_width=True,
            )
          st.write("---")
          st.info(f"**Tu corrección:** {corr_a if corr_a else '*Sin texto*'}")
          if foto_a:
            st.image(
                foto_a, caption="Tu solución visual", use_container_width=True
            )
          st.audio(aud_cor)

  # ================= VISTA MINEROS (Minero 1: Óscar / Minero 2: Pablo) =================
  elif st.session_state["rol"] in ["Minero 1", "Minero 2"]:
    minero_actual = st.session_state["rol"]
    minero_actual_visual = formatear_nombre_minero(minero_actual)
    st.header(f"🪨 Panel del Minero ({minero_actual_visual})")

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
