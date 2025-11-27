import streamlit as st
import pandas as pd
import requests
import os
import plotly.express as px

# --- Configurações e Variáveis ---
API_URL = "https://loteriascaixa-api.herokuapp.com/api/megasena"
CSV_FILE = "megasena_premios_municipios.csv"

# --- 1. Funções de Obtenção e Processamento de Dados ---

@st.cache_data
def load_and_process_data(url: str, file_path: str) -> pd.DataFrame:
    """
    Baixa os dados da API, processa e armazena/carrega o arquivo CSV.
    Acesso corrigido ao campo 'localGanhadores'.
    """
    # 1. Tenta carregar do arquivo local primeiro
    if os.path.exists(file_path):
        st.info("Carregando dados processados do arquivo local...")
        try:
            df_premios = pd.read_csv(file_path)
            if not df_premios.empty:
                # Transforma para a Análise Exploratória (Contagem de Prêmios)
                df_analise = df_premios.groupby(['uf', 'municipio']).size().reset_index(name='vezes_premiado')
                df_analise['uf_municipio'] = df_analise['uf'] + ' - ' + df_analise['municipio']
                total_por_estado = df_premios.groupby('uf').size().reset_index(name='total_premios_estado')
                df_analise = pd.merge(df_analise, total_por_estado, on='uf', how='left')
                return df_analise
        except pd.errors.EmptyDataError:
            st.warning(f"O arquivo {file_path} está vazio. Baixando dados da API novamente.")
        except Exception as e:
            st.warning(f"Erro ao carregar o CSV ({e}). Baixando dados da API novamente.")

    # 2. Se falhar ou não existir, baixa e processa da API
    st.info("Baixando dados da API e processando...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao acessar a API: {e}")
        return pd.DataFrame()

    registros_premios = []

    # Processamento e Extração: Ganhadores por município e estado
    for sorteio in data:
        concurso = sorteio.get('concurso', 'N/A')
        data_sorteio = sorteio.get('data', 'N/A')
        
        # --- CORREÇÃO AQUI: USANDO 'localGanhadores' ---
        local_ganhadores = sorteio.get('localGanhadores')
        
        if local_ganhadores and isinstance(local_ganhadores, list):
            for ganhador in local_ganhadores:
                # O campo 'quantidade' indica quantas vezes aquele município ganhou naquele concurso
                quantidade = ganhador.get('quantidade', 1) 
                municipio = ganhador.get('municipio')
                uf = ganhador.get('uf')
                
                # Registra o prêmio 'quantidade' vezes
                if municipio and uf and municipio != 'N/A' and uf != 'N/A':
                    for _ in range(quantidade):
                        registros_premios.append({
                            'concurso': concurso,
                            'data': data_sorteio,
                            'municipio': municipio.upper().strip(), 
                            'uf': uf.upper().strip() 
                        })

    # Criação do DataFrame
    df_premios = pd.DataFrame(registros_premios)
    
    if df_premios.empty:
        st.warning("Nenhum prêmio da Sena com dados de município/UF foi encontrado na API.")
        return pd.DataFrame()
        
    df_premios.dropna(subset=['municipio', 'uf'], inplace=True) 

    # Salva o resultado processado em CSV
    df_premios.to_csv(file_path, index=False)
    st.success(f"Dados processados e salvos em: {file_path}")

    # Transformação para a Análise Exploratória (Contagem de Prêmios)
    df_analise = df_premios.groupby(['uf', 'municipio']).size().reset_index(name='vezes_premiado')
    df_analise['uf_municipio'] = df_analise['uf'] + ' - ' + df_analise['municipio']
    
    # Adiciona colunas de prêmios totais por estado para ranking
    total_por_estado = df_premios.groupby('uf').size().reset_index(name='total_premios_estado')
    df_analise = pd.merge(df_analise, total_por_estado, on='uf', how='left')
    
    return df_analise

# --- 2. Geração de Visualizações ---

def plot_top_municipios(df: pd.DataFrame, top_n: int):
    """Gera um gráfico de barras para os municípios mais premiados."""
    if df.empty:
        return None
    df_top = df.sort_values(by='vezes_premiado', ascending=False).head(top_n)
    fig = px.bar(
        df_top,
        x='vezes_premiado',
        y='uf_municipio',
        orientation='h',
        title=f'🏆 Top {top_n} Municípios Mais Premiados (Todas as UFs)',
        labels={'vezes_premiado': 'Número de Vezes Premiado', 'uf_municipio': 'Município (UF)'},
        color='uf',
        color_continuous_scale=px.colors.sequential.Viridis
    )
    fig.update_layout(yaxis={'categoryorder': 'total ascending'})
    return fig

def plot_estado_ranking(df: pd.DataFrame):
    """Gera um gráfico de barras para o ranking de estados."""
    if df.empty:
        return None
    df_estado = df[['uf', 'total_premios_estado']].drop_duplicates().sort_values(by='total_premios_estado', ascending=False)
    fig = px.bar(
        df_estado,
        x='uf',
        y='total_premios_estado',
        title='🗺️ Ranking de Estados por Total de Prêmios (Sena)',
        labels={'total_premios_estado': 'Total de Prêmios (Sena)', 'uf': 'Estado (UF)'},
        color='total_premios_estado'
    )
    return fig

def plot_municipios_por_estado(df: pd.DataFrame, estado: str, top_n: int):
    """Gera um gráfico de pizza para a distribuição de prêmios em um estado."""
    if df.empty:
        return None
        
    df_estado_completo = df[df['uf'] == estado]
    if df_estado_completo.empty:
        return None
        
    df_filtrado = df_estado_completo.sort_values(by='vezes_premiado', ascending=False).head(top_n)
    
    # Agrupa o restante em 'Outros' se for maior que top_n
    if len(df_estado_completo) > top_n:
        outras_cidades_count = df_estado_completo['vezes_premiado'].iloc[top_n:].sum()
        outros_df = pd.DataFrame([{'municipio': f'OUTROS ({len(df_estado_completo) - top_n} Cidades)', 'vezes_premiado': outras_cidades_count}])
        df_filtrado_aux = df_filtrado.drop(columns=[col for col in ['uf', 'total_premios_estado', 'uf_municipio'] if col in df_filtrado.columns])
        df_pizza = pd.concat([df_filtrado_aux, outros_df], ignore_index=True)
    else:
        df_pizza = df_filtrado.drop(columns=[col for col in ['uf', 'total_premios_estado', 'uf_municipio'] if col in df_filtrado.columns])

    fig = px.pie(
        df_pizza,
        values='vezes_premiado',
        names='municipio',
        title=f'🥧 Distribuição dos Prêmios (Sena) em **{estado}** (Top {min(top_n, len(df_estado_completo))} + Outros)',
        hole=.3
    )
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig


# --- 3. Layout do Dashboard Streamlit ---

st.set_page_config(layout="wide", page_title="Análise Mega-Sena", page_icon="💰")

## Título Principal
st.title("💰 Dashboard de Análise de Ganhadores da Mega-Sena (Sena)")
st.caption("Dados obtidos da API: https://loteriascaixa-api.herokuapp.com/api/megasena")

# Carregar e Processar os Dados
df_analise = load_and_process_data(API_URL, CSV_FILE)

# Verificação se o DataFrame de análise está vazio
if df_analise.empty:
    st.error("Não foi possível carregar ou processar dados válidos para análise. Verifique a API ou as permissões de arquivo.")
else:
    # --- KPIs (Métricas de Destaque) ---
    st.markdown("---")
    st.header("✨ Métricas de Destaque (KPIs)")
    
    col_total, col_cidades, col_estados = st.columns(3)
    
    total_premios_sena = df_analise['vezes_premiado'].sum()
    total_cidades = df_analise['municipio'].nunique()
    total_estados = df_analise['uf'].nunique()
    
    col_total.metric(label="Total de Prêmios da Sena Registrados", value=f"{total_premios_sena:,.0f}")
    col_cidades.metric(label="Total de Cidades Premiadas", value=f"{total_cidades:,}")
    col_estados.metric(label="Total de Estados Premiados", value=f"{total_estados}")

    st.markdown("---")

    # --- Análise Exploratória e Visualização ---

    # Layout de 2 colunas para os gráficos principais
    col_viz_1, col_viz_2 = st.columns([1, 1])

    with col_viz_1:
        st.header("🌎 Top Municípios Mais Premiados")
        st.markdown("Use o *slider* abaixo para ajustar a quantidade de municípios exibidos.")
        
        # Elemento Interativo 1: Slider
        max_municipios = min(50, df_analise.shape[0])
        top_n_municipios = st.slider(
            'Selecione o Top N de Municípios',
            min_value=5,
            max_value=max_municipios,
            value=10,
            step=5,
            key='slider_municipios'
        )
        
        fig1 = plot_top_municipios(df_analise, top_n_municipios)
        if fig1:
            st.plotly_chart(fig1, use_container_width=True)

    with col_viz_2:
        st.header("🗺️ Ranking de Prêmios por Estado")
        st.markdown("Gráfico com a soma total de prêmios da Sena por Unidade Federativa.")
        fig2 = plot_estado_ranking(df_analise)
        if fig2:
            st.plotly_chart(fig2, use_container_width=True)
    
    st.markdown("---")
    
    st.header("🔍 Detalhe por Estado Selecionado")
    st.markdown("Use a *caixa de seleção* para focar nos municípios de um estado específico e veja a distribuição dos prêmios.")
    
    # Elemento Interativo 2: Caixa de Seleção/Dropdown
    col_interativo_estado, col_interativo_pie = st.columns([1, 3])
    
    list_estados = sorted(df_analise['uf'].unique().tolist())
    
    with col_interativo_estado:
        estado_selecionado = st.selectbox(
            '**Selecione o Estado (UF):**',
            options=list_estados,
            index=list_estados.index('SP') if 'SP' in list_estados else 0,
            key='dropdown_estado'
        )
        
        # Elemento Interativo 3 (Extra): Slider para o gráfico de pizza
        # Recalcula o max_value para evitar erro se houver poucas cidades no estado
        max_pie_value = min(15, df_analise[df_analise['uf'] == estado_selecionado].shape[0])
        top_n_pie = st.slider(
            'Top N de Cidades no Gráfico de Pizza (Porcentagem)',
            min_value=3,
            max_value=max_pie_value,
            value=min(8, max_pie_value),
            step=1,
            key='slider_pie'
        )
        
    with col_interativo_pie:
        if estado_selecionado:
            fig3 = plot_municipios_por_estado(df_analise, estado_selecionado, top_n_pie)
            if fig3:
                st.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")

    st.subheader("📋 Tabela de Dados: Municípios Premiados por Estado")
    st.markdown("Tabela completa com a contagem de prêmios por município e a soma total por estado.")
    
    st.dataframe(df_analise.sort_values(by=['total_premios_estado', 'vezes_premiado'], ascending=[False, False]), use_container_width=True)