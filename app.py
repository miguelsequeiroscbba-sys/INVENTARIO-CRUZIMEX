import io
import streamlit as st
import pandas as pd

# Configuración de la página
st.set_page_config(page_title="Monitor de Inventario - CBB", layout="wide", page_icon="📦")

st.title("📦 Control de Inventario y Preventas - CBB")
st.markdown("Consulta el estado del inventario, los consolidados por producto y el detalle por cliente en tiempo real.")

# ---------------------------------------------------------
# SIDEBAR: Carga de Archivos y Parámetros
# ---------------------------------------------------------
st.sidebar.header("📁 Carga de Archivos")

archivo_inv = st.sidebar.file_uploader("1. Inventario Base (.xls / .xlsx)", type=["xls", "xlsx"])
archivo_consolidado = st.sidebar.file_uploader("2. Consolidado de Pedidos (.xlsx)", type=["xlsx"])

umbrales_stock = st.sidebar.slider("Límite para alerta de Stock Bajo (unidades)", 1, 50, 10)

# ---------------------------------------------------------
# LÓGICA DE PROCESAMIENTO
# ---------------------------------------------------------
if archivo_inv is not None:
    # 1. Cargar Inventario Base
    try:
        df_inv = pd.read_excel(archivo_inv)
    except Exception:
        archivo_inv.seek(0)
        df_inv = pd.read_html(archivo_inv)[0]

    df_inv.columns = df_inv.columns.astype(str).str.strip()

    # Detección dinámica de columnas en inventario
    col_cod_inv = next(
        (c for c in df_inv.columns if c.upper().strip() in ['COD', 'CÓD', 'ARTÍCULO', 'ARTICULO', 'CODIGO', 'CÓDIGO']), 
        df_inv.columns[0]
    )
    col_stock_inv = next(
        (c for c in df_inv.columns if c.upper().strip() in ['CANT', 'STOCK', 'CANT_INICIAL', 'CANTIDAD']), 
        None
    )

    df_inv['COD'] = df_inv[col_cod_inv].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    if col_stock_inv:
        if df_inv[col_stock_inv].dtype == object:
            df_inv[col_stock_inv] = df_inv[col_stock_inv].astype(str).str.replace(',', '')
        df_inv['CANT_INICIAL'] = pd.to_numeric(df_inv[col_stock_inv], errors='coerce').fillna(0)
    else:
        st.error("❌ No se encontró la columna de cantidad/stock en el inventario base.")
        st.stop()

    # Variables para almacenar consolidados y detalles
    df_pedidos_agrupados = pd.DataFrame()
    df_consolidado_raw = pd.DataFrame()

    # 2. Cargar Consolidado si se ha subido
    if archivo_consolidado is not None:
        df_consolidado_raw = pd.read_excel(archivo_consolidado)
        df_consolidado_raw.columns = df_consolidado_raw.columns.astype(str).str.strip()

        # Limpieza de código y cantidad en el consolidado
        col_cod_cons = next((c for c in df_consolidado_raw.columns if c.upper() in ['CÓDIGO ARTÍCULO', 'CODIGO ARTICULO', 'CODIGO', 'COD']), 'CÓDIGO ARTÍCULO')
        col_cant_cons = next((c for c in df_consolidado_raw.columns if c.upper() in ['CANTIDAD', 'CANT']), 'CANTIDAD')
        col_desc_cons = next((c for c in df_consolidado_raw.columns if 'DESCRIPCI' in c.upper()), 'DESCRIPCIÓN DE ARTÍCULO')

        df_consolidado_raw[col_cod_cons] = df_consolidado_raw[col_cod_cons].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
        
        if df_consolidado_raw[col_cant_cons].dtype == object:
            df_consolidado_raw[col_cant_cons] = df_consolidado_raw[col_cant_cons].astype(str).str.replace(',', '')
        df_consolidado_raw[col_cant_cons] = pd.to_numeric(df_consolidado_raw[col_cant_cons], errors='coerce').fillna(0)

        # Agrupación por SKU
        df_pedidos_agrupados = df_consolidado_raw.groupby(
            col_cod_cons, as_index=False
        ).agg({
            col_desc_cons: 'first',
            col_cant_cons: 'sum'
        }).rename(columns={
            col_cod_cons: 'COD',
            col_cant_cons: 'CANT_PEDIDA',
            col_desc_cons: 'DESCRIPCION'
        }).sort_values(by='CANT_PEDIDA', ascending=False)

        # Cruce con Inventario
        df_resultado = pd.merge(df_inv, df_pedidos_agrupados[['COD', 'CANT_PEDIDA']], on='COD', how='left')
        df_resultado['CANT_PEDIDA'] = df_resultado['CANT_PEDIDA'].fillna(0).astype(int)
    else:
        df_resultado = df_inv.copy()
        df_resultado['CANT_PEDIDA'] = 0

    df_resultado['CANT_ACTUALIZADA'] = df_resultado['CANT_INICIAL'] - df_resultado['CANT_PEDIDA']

    # Clasificación de Estado
    def evaluar_estado(row):
        if row['CANT_PEDIDA'] > 0:
            if row['CANT_ACTUALIZADA'] < 0:
                return "🔴 ALERTA: STOCK INSUFICIENTE"
            elif row['CANT_ACTUALIZADA'] <= umbrales_stock:
                return "🟡 STOCK BAJO"
            return "🟢 CON MOVIMIENTO"
        else:
            return "⚪ SIN MOVIMIENTO"

    df_resultado['ESTADO'] = df_resultado.apply(evaluar_estado, axis=1)

    # ---------------------------------------------------------
    # METRICAS PRINCIPALES (KPIs)
    # ---------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total SKUs Base", len(df_resultado))
    col2.metric("Total Unidades Pedidas", int(df_resultado['CANT_PEDIDA'].sum()))
    col3.metric("Stock Insuficiente", len(df_resultado[df_resultado['ESTADO'].str.contains("INSUFICIENTE")]))
    col4.metric("SKUs Stock Bajo", len(df_resultado[df_resultado['ESTADO'] == "🟡 STOCK BAJO"]))

    st.markdown("---")

    # ---------------------------------------------------------
    # BOTÓN PARA DESCARGAR EL EXCEL COMPLETO
    # ---------------------------------------------------------
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_resultado.to_excel(writer, sheet_name='Inventario_Actualizado', index=False)
        if not df_pedidos_agrupados.empty:
            df_pedidos_agrupados.to_excel(writer, sheet_name='Consolidado_Agrupado', index=False)
        if not df_consolidado_raw.empty:
            df_consolidado_raw.to_excel(writer, sheet_name='Detalle_Por_Cliente', index=False)

    st.sidebar.markdown("---")
    st.sidebar.download_button(
        label="📥 Descargar Reporte en Excel",
        data=buffer.getvalue(),
        file_name="INVENTARIO_ACTUALIZADO.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # ---------------------------------------------------------
    # NAVEGACIÓN POR PESTAÑAS (TABS)
    # ---------------------------------------------------------
    tab1, tab2, tab3 = st.tabs(["📋 Inventario General Actualizado", "📊 Consolidado Agrupado", "👤 Detalle por Cliente"])

    # PESTAÑA 1: INVENTARIO GENERAL
    with tab1:
        st.subheader("🔍 Consultar Estado del Inventario")
        c1, c2 = st.columns([2, 1])
        busqueda = c1.text_input("Buscar por código o descripción:")
        filtro_estado = c2.multiselect("Filtrar por Estado:", options=df_resultado['ESTADO'].unique(), default=df_resultado['ESTADO'].unique())

        df_tab1 = df_resultado[df_resultado['ESTADO'].isin(filtro_estado)]
        if busqueda:
            df_tab1 = df_tab1[
                df_tab1['COD'].str.contains(busqueda, case=False, na=False) |
                df_tab1['DESCRIPCION'].str.contains(busqueda, case=False, na=False)
            ]

        st.dataframe(df_tab1, use_container_width=True, hide_index=True)

    # PESTAÑA 2: CONSOLIDADO AGRUPADO
    with tab2:
        st.subheader("📊 Pedidos Acumulados por Producto")
        if not df_pedidos_agrupados.empty:
            busqueda_p2 = st.text_input("Buscar producto en consolidado:")
            df_tab2 = df_pedidos_agrupados.copy()
            if busqueda_p2:
                df_tab2 = df_tab2[
                    df_tab2['COD'].str.contains(busqueda_p2, case=False, na=False) |
                    df_tab2['DESCRIPCION'].str.contains(busqueda_p2, case=False, na=False)
                ]
            st.dataframe(df_tab2, use_container_width=True, hide_index=True)
        else:
            st.info("ℹ️ Sube el archivo de Consolidado de Pedidos en la barra lateral para ver esta información.")

    # PESTAÑA 3: DETALLE POR CLIENTE
    with tab3:
        st.subheader("👤 Registro Detallado de Pedidos por Cliente")
        if not df_consolidado_raw.empty:
            col_cli, col_prod = st.columns(2)
            
            # Filtro por cliente
            col_cliente_name = next((c for c in df_consolidado_raw.columns if 'CLIENTE' in c.upper()), None)
            if col_cliente_name:
                clientes = ["TODOS"] + list(df_consolidado_raw[col_cliente_name].dropna().unique())
                cliente_sel = col_cli.selectbox("Filtrar por Cliente:", clientes)
            else:
                cliente_sel = "TODOS"

            busqueda_p3 = col_prod.text_input("Buscar en detalle (código o descripción):")

            df_tab3 = df_consolidado_raw.copy()
            if col_cliente_name and cliente_sel != "TODOS":
                df_tab3 = df_tab3[df_tab3[col_cliente_name] == cliente_sel]
            
            if busqueda_p3:
                df_tab3 = df_tab3[
                    df_tab3.astype(str).apply(lambda row: row.str.contains(busqueda_p3, case=False).any(), axis=1)
                ]

            st.dataframe(df_tab3, use_container_width=True, hide_index=True)
        else:
            st.info("ℹ️ Sube el archivo de Consolidado de Pedidos en la barra lateral para ver esta información.")

else:
    st.info("👆 Por favor, sube el archivo de **Inventario Base** en la barra lateral para activar las pestañas de consulta.")