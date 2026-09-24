import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

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

BUCKET_NAME = "Archivos-inventario"

# ---------------------------------------------------------
# Funciones para manejar archivos en Supabase Storage
# ---------------------------------------------------------
def subir_archivo_supabase(bytes_data, nombre_destino):
    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            file=bytes_data,
            path=nombre_destino,
            file_options={
                "content-type": "application/octet-stream",
                "upsert": "true"
            }
        )
        return True
    except Exception as e:
        st.error(f"Error al subir el archivo {nombre_destino}: {e}")
        return False

def cargar_excel_desde_supabase(nombre_archivo):
    try:
        data_bytes = supabase.storage.from_(BUCKET_NAME).download(nombre_archivo)
        
        try:
            df = pd.read_excel(io.BytesIO(data_bytes))
        except Exception:
            try:
                df = pd.read_excel(io.BytesIO(data_bytes), engine='xlrd')
            except Exception:
                df = pd.read_html(io.BytesIO(data_bytes))[0]
                
        return df
    except Exception:
        return None

# Función de limpieza y homogeinización exacta de códigos
def limpiar_codigo(serie):
    return (
        serie.astype(str)
        .str.replace(r'\.0$', '', regex=True)
        .str.strip()
        .str.lstrip('0')
        .str.upper()
    )

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
        st.subheader("📊 Control y Estado de Stock Real")
        
        col_lim, col_blank = st.columns([1.5, 2.5])
        with col_lim:
            limite_bajo_stock = st.number_input("⚙️ Umbral para alertar Poco Stock (unidades):", min_value=1, value=5, step=1)
            
        df_resumen = df_inv.copy()
        
        # 1. Identificar columnas de Inventario Base
        cols_inv = df_resumen.columns.tolist()
        col_codigo = next((c for c in cols_inv if any(k in str(c).upper() for k in ["COD", "CÓDIGO", "ITEM", "MATERIAL"])), cols_inv[0])
        col_stock_ini = next((c for c in cols_inv if any(k in str(c).upper() for k in ["CANT", "STOCK", "SALDO", "EXIST"])), cols_inv[-1])
        
        # Formatear números y clave de inventario
        df_resumen[col_stock_ini] = pd.to_numeric(df_resumen[col_stock_ini], errors='coerce').fillna(0)
        df_resumen['__key_cod__'] = limpiar_codigo(df_resumen[col_codigo])
        
        # 2. Identificar columnas de Ventas Consolidadas
        if df_ventas is not None and not df_ventas.empty:
            cols_vta = df_ventas.columns.tolist()
            
            # Buscar columnas específicas vistas en la imagen ("CÓDIGO ARTÍCULO" y "CANTIDAD")
            col_vta_cod = next((c for c in cols_vta if any(k in str(c).upper() for k in ["CÓDIGO ARTÍCULO", "CODIGO ARTICULO", "CÓDIGO", "COD", "ITEM"])), cols_vta[0])
            col_vta_cant = next((c for c in cols_vta if any(k in str(c).upper() for k in ["CANTIDAD", "CANT", "PEDIDO", "VENTA"])), cols_vta[-1])
            
            # Limpiar datos de ventas
            df_ventas[col_vta_cant] = pd.to_numeric(df_ventas[col_vta_cant], errors='coerce').fillna(0)
            df_ventas['__key_vta_cod__'] = limpiar_codigo(df_ventas[col_vta_cod])
            
            # Agrupar suma de ventas por código
            df_ventas_agrup = df_ventas.groupby('__key_vta_cod__')[col_vta_cant].sum().reset_index()
            df_ventas_agrup.rename(columns={col_vta_cant: 'Preventas Acumuladas'}, inplace=True)
            
            # Unir (Merge) Inventario con Ventas
            df_resumen = pd.merge(
                df_resumen, 
                df_ventas_agrup, 
                left_on='__key_cod__', 
                right_on='__key_vta_cod__', 
                how='left'
            )
            df_resumen['Preventas Acumuladas'] = df_resumen['Preventas Acumuladas'].fillna(0)
            
            if '__key_vta_cod__' in df_resumen.columns:
                df_resumen.drop(columns=['__key_vta_cod__'], inplace=True)
        else:
            df_resumen['Preventas Acumuladas'] = 0

        # Eliminar columna auxiliar de clave
        if '__key_cod__' in df_resumen.columns:
            df_resumen.drop(columns=['__key_cod__'], inplace=True)

        # 3. Cálculos finales
        df_resumen['Stock Disponible Real'] = df_resumen[col_stock_ini] - df_resumen['Preventas Acumuladas']

        def calcular_estado(row):
            disponible = row['Stock Disponible Real']
            if disponible < 0:
                return "⚠️ Quiebre de Stock"
            elif disponible == 0:
                return "🔴 Agotado"
            elif disponible <= limite_bajo_stock:
                return "🟡 Poco Stock"
            else:
                return "🟢 Disponible"

        df_resumen['Estado Stock'] = df_resumen.apply(calcular_estado, axis=1)

        # Ordenar columnas para mostrar en pantalla
        cols_finales = [col_codigo]
        otras_cols = [c for c in df_resumen.columns if c not in [col_codigo, col_stock_ini, 'Preventas Acumuladas', 'Stock Disponible Real', 'Estado Stock']]
        cols_finales.extend(otras_cols)
        cols_finales.extend([col_stock_ini, 'Preventas Acumuladas', 'Stock Disponible Real', 'Estado Stock'])
        df_resumen = df_resumen[cols_finales]

        # Tarjetas Métricas
        total_prod = len(df_resumen)
        cant_disp = len(df_resumen[df_resumen['Estado Stock'] == "🟢 Disponible"])
        cant_poco = len(df_resumen[df_resumen['Estado Stock'] == "🟡 Poco Stock"])
        cant_agotado = len(df_resumen[df_resumen['Estado Stock'] == "🔴 Agotado"])
        cant_quiebre = len(df_resumen[df_resumen['Estado Stock'] == "⚠️ Quiebre de Stock"])

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Items", total_prod)
        m2.metric("🟢 Disponibles", cant_disp)
        m3.metric("🟡 Poco Stock", cant_poco)
        m4.metric("🔴 Agotados", cant_agotado)
        m5.metric("⚠️ Quiebres", cant_quiebre)

        st.markdown("---")

        # Filtros
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            busqueda = st.text_input("🔎 Buscar por código, descripción o cliente:")
        with col_f2:
            filtro_estado = st.multiselect("Filtrar por Estado:", options=["🟢 Disponible", "🟡 Poco Stock", "🔴 Agotado", "⚠️ Quiebre de Stock"])

        df_mostrar = df_resumen.copy()

        if filtro_estado:
            df_mostrar = df_mostrar[df_mostrar['Estado Stock'].isin(filtro_estado)]

        if busqueda:
            mask = df_mostrar.apply(lambda row: row.astype(str).str.contains(busqueda, case=False).any(), axis=1)
            df_mostrar = df_mostrar[mask]

        st.dataframe(
            df_mostrar,
            use_container_width=True,
            column_config={
                "Estado Stock": st.column_config.TextColumn("Estado"),
                "Stock Disponible Real": st.column_config.NumberColumn("Stock Disponible Real", format="%d"),
                "Preventas Acumuladas": st.column_config.NumberColumn("Preventas Acumuladas", format="%d")
            }
        )

        if df_ventas is not None:
            with st.expander("📄 Ver detalle del Excel de Preventas cargado"):
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
        
        with tab1:
            st.markdown("#### Subir Inventario Base Inicial")
            file_inv = st.file_uploader("Selecciona el Excel de Inventario Base", type=["xlsx", "xls"], key="inv_up")
            if file_inv is not None:
                if st.button("🚀 Actualizar Inventario Base"):
                    with st.spinner("Subiendo Inventario Base..."):
                        if subir_archivo_supabase(file_inv.getvalue(), "inventario_base.xlsx"):
                            st.cache_data.clear()
                            st.success("¡Inventario Base actualizado correctamente!")
                            st.balloons()

        with tab2:
            st.markdown("#### Subir / Actualizar Ventas Consolidadas")
            file_ventas = st.file_uploader("Selecciona el Excel de Ventas Consolidadas", type=["xlsx", "xls"], key="ventas_up")
            if file_ventas is not None:
                if st.button("🔄 Actualizar Ventas del Día"):
                    with st.spinner("Actualizando Ventas del Día..."):
                        if subir_archivo_supabase(file_ventas.getvalue(), "ventas_consolidadas.xlsx"):
                            st.cache_data.clear()
                            st.success("¡Ventas actualizadas correctamente!")
                            st.balloons()
                            
    elif password:
        st.error("Contraseña incorrecta.")
