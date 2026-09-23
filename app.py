import streamlit as st
import pandas as pd
from supabase import create_client, Client

st.set_page_config(
    page_title="Gestión de Inventario - Cruzimex",
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
# Funciones para manejar archivos en Supabase Storage
# ---------------------------------------------------------
def subir_archivo_supabase(bytes_data, nombre_destino):
    try:
        # Se sube o reemplaza el archivo en el bucket
        supabase.storage.from_(BUCKET_NAME).upload(
            file=bytes_data,
            path=nombre_destino,
            file_options={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "upsert": "true"}
        )
        return True
    except Exception as e:
        st.error(f"Error al subir el archivo {nombre_destino}: {e}")
        return False

def cargar_excel_desde_supabase(nombre_archivo):
    try:
        url = supabase.storage.from_(BUCKET_NAME).get_public_url(nombre_archivo)
        df = pd.read_excel(url)
        return df
    except Exception as e:
        return None

# ---------------------------------------------------------
# Interfaz Principal (Navegación)
# ---------------------------------------------------------
st.title("📦 Sistema de Control e Inventario Real - Cruzimex")

menu = st.sidebar.radio("Navegación", ["🔍 Consultar Inventario Real", "⚙️ Panel de Administración"])

# ---------------------------------------------------------
# VISTA 1: Consulta de Inventario (Usuario / Preventistas)
# ---------------------------------------------------------
if menu == "🔍 Consultar Inventario Real":
    df_inv = cargar_excel_desde_supabase("inventario_base.xlsx")
    df_ventas = cargar_excel_desde_supabase("ventas_consolidadas.xlsx")
    
    if df_inv is None:
        st.warning("⚠️ Todavía no se ha cargado el **Inventario Base**. El administrador debe subirlo en el Panel de Administración.")
    else:
        st.subheader("📊 Stock e Inventario Disponible")
        
        col1, col2 = st.subplots(2)
        with col1:
            st.info("✅ **Inventario Base**: Cargado activamente.")
        with col2:
            if df_ventas is not None:
                st.info("🔄 **Ventas del Día**: Registradas y descontadas.")
            else:
                st.warning("ℹ️ **Ventas del Día**: Sin reportes de ventas aún (mostrando inventario base completo).")
        
        # Mostrar tabla principal
        st.markdown("---")
        busqueda = st.text_input("🔎 Buscar por código de producto, descripción o familia:")
        
        if busqueda:
            mask = df_inv.apply(lambda row: row.astype(str).str.contains(busqueda, case=False).any(), axis=1)
            df_filtrado = df_inv[mask]
            st.write(f"Resultados encontrados: **{len(df_filtrado)}**")
            st.dataframe(df_filtrado, use_container_width=True)
        else:
            st.dataframe(df_inv, use_container_width=True)

        if df_ventas is not None:
            with st.expander("📄 Ver detalle de Ventas Consolidadas Acumuladas"):
                st.dataframe(df_ventas, use_container_width=True)

# ---------------------------------------------------------
# VISTA 2: Panel de Administración (Subida de Excels)
# ---------------------------------------------------------
elif menu == "⚙️ Panel de Administración":
    st.subheader("⚙️ Gestión y Carga de Archivos Excel")
    
    password = st.text_input("Ingresa la contraseña de administrador:", type="password")
    
    if password == st.secrets["ADMIN_PASSWORD"]:
        st.success("Acceso concedido.")
        
        tab1, tab2 = st.tabs(["1️⃣ Inventario Base (Inicio del día)", "2️⃣ Ventas Consolidadas (Periódico)"])
        
        # TAB 1: Inventario Base
        with tab1:
            st.markdown("#### Subir Inventario Base Inicial")
            st.caption("Este archivo se sube idealmente al iniciar el turno/día.")
            file_inv = st.file_uploader("Selecciona el Excel de Inventario Base", type=["xlsx", "xls"], key="inv_up")
            if file_inv is not None:
                if st.button("🚀 Actualizar Inventario Base"):
                    with st.spinner("Subiendo Inventario Base..."):
                        if subir_archivo_supabase(file_inv.getvalue(), "inventario_base.xlsx"):
                            st.success("¡Inventario Base actualizado correctamente en la nube!")
                            st.balloons()

        # TAB 2: Ventas Consolidadas
        with tab2:
            st.markdown("#### Subir / Actualizar Ventas Consolidadas")
            st.caption("Sube este reporte cada vez que descargues las ventas/pedidos de los preventistas para actualizar el saldo disponible.")
            file_ventas = st.file_uploader("Selecciona el Excel de Ventas Consolidadas", type=["xlsx", "xls"], key="ventas_up")
            if file_ventas is not None:
                if st.button("🔄 Actualizar Ventas del Día"):
                    with st.spinner("Actualizando Ventas del Día..."):
                        if subir_archivo_supabase(file_ventas.getvalue(), "ventas_consolidadas.xlsx"):
                            st.success("¡Ventas del Día actualizadas correctamente en la nube!")
                            st.balloons()
                            
    elif password:
        st.error("Contraseña incorrecta.")
