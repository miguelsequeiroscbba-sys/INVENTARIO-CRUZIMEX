import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

st.set_page_config(
    page_title="Gestión de Inventario",
    page_icon="📦",
    layout="wide"
)

# ---------------------------------------------------------
# Conexión a Supabase usando Secrets
# ---------------------------------------------------------
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()
BUCKET_NAME = "archivos-inventario"

# ---------------------------------------------------------
# Funciones auxiliares para Storage
# ---------------------------------------------------------
def listar_archivos():
    try:
        res = supabase.storage.from_(BUCKET_NAME).list()
        # Filtrar solo archivos con extensión .xlsx o .xls
        archivos = [f for f in res if f['name'].endswith(('.xlsx', '.xls'))]
        # Ordenar por fecha de creación (los más recientes primero)
        archivos.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return archivos
    except Exception as e:
        st.error(f"Error al conectar con el bucket de Supabase: {e}")
        return []

def cargar_excel_desde_supabase(nombre_archivo):
    try:
        url = supabase.storage.from_(BUCKET_NAME).get_public_url(nombre_archivo)
        df = pd.read_excel(url)
        return df
    except Exception as e:
        st.error(f"Error al leer el archivo {nombre_archivo}: {e}")
        return None

# ---------------------------------------------------------
# Interfaz Principal (Navegación)
# ---------------------------------------------------------
st.title("📦 Sistema de Consultas de Inventario")

menu = st.sidebar.radio("Navegación", ["🔍 Consultar Inventario", "⚙️ Panel de Administración"])

# ---------------------------------------------------------
# VISTA 1: Consulta de Inventario (Usuario Público)
# ---------------------------------------------------------
if menu == "🔍 Consultar Inventario":
    archivos = listar_archivos()
    
    if not archivos:
        st.info("No hay reportes de inventario subidos aún. Ve al Panel de Administración para subir uno.")
    else:
        # Selector para elegir qué reporte ver
        opciones_archivos = [f['name'] for f in archivos]
        archivo_seleccionado = st.selectbox("Selecciona el reporte de inventario:", opciones_archivos)
        
        if archivo_seleccionado:
            with st.spinner("Cargando inventario..."):
                df = cargar_excel_desde_supabase(archivo_seleccionado)
            
            if df is not None:
                st.success(f"Reporte cargado: **{archivo_seleccionado}** ({len(df)} registros)")
                
                # Buscador
                busqueda = st.text_input("🔎 Buscar por código, descripción o categoría:")
                
                if busqueda:
                    # Filtra en todas las columnas convirtiendo a string
                    mask = df.apply(lambda row: row.astype(str).str.contains(busqueda, case=False).any(), axis=1)
                    df_filtrado = df[mask]
                    st.write(f"Resultados encontrados: **{len(df_filtrado)}**")
                    st.dataframe(df_filtrado, use_container_width=True)
                else:
                    st.dataframe(df, use_container_width=True)

# ---------------------------------------------------------
# VISTA 2: Panel de Administración (Protegido con Password)
# ---------------------------------------------------------
elif menu == "⚙️ Panel de Administración":
    st.subheader("Subir o Actualizar Reportes de Inventario")
    
    password = st.text_input("Ingresa la contraseña de administrador:", type="password")
    
    if password == st.secrets["ADMIN_PASSWORD"]:
        st.success("Acceso concedido.")
        
        archivo_subido = st.file_uploader("Selecciona un archivo Excel (.xlsx)", type=["xlsx", "xls"])
        
        if archivo_subido is not None:
            if st.button("🚀 Subir Archivo a Supabase"):
                with st.spinner("Subiendo archivo..."):
                    try:
                        bytes_data = archivo_subido.getvalue()
                        nombre_archivo = archivo_subido.name
                        
                        # Subir archivo al bucket de Supabase
                        res = supabase.storage.from_(BUCKET_NAME).upload(
                            file=bytes_data,
                            path=nombre_archivo,
                            file_options={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "upsert": "true"}
                        )
                        st.success(f"¡Archivo **{nombre_archivo}** subido y actualizado correctamente en Supabase!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Ocurrió un error al subir el archivo: {e}")
        
        st.markdown("---")
        st.subheader("Archivos almacenados actualmente:")
        archivos = listar_archivos()
        if archivos:
            for arc in archivos:
                st.write(f"- 📄 `{arc['name']}`")
        else:
            st.write("No hay archivos subidos.")
            
    elif password:
        st.error("Contraseña incorrecta.")
