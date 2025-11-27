import streamlit as st
import pandas as pd
import requests
import os
import plotly.express as px
import random

# --- Configurações e Variáveis ---
API_URL = "https://loteriascaixa-api.herokuapp.com/api/megasena"
CSV_FILE_PREMIOS = "megasena_premios_municipios.csv"
CSV_FILE_DEZENAS = "megasena_dezenas_frequencia.csv"
TODAS_DEZENAS = [str(i).zfill(2) for i in range(1, 61)]


# --- 1. Funções de Obtenção e Processamento de Dados ---

@st.cache_data
def load_and_process_data(url: str, file_path_premios: str, file_path_dezenas: str) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """
    Baixa os dados da API, processa e armazena/carrega os arquivos CSV.
    Retorna: (DF Prêmios, DF Dezenas, Lista de Dados Brutos para Análise de Sorteios).
    """
    # 1. Tenta carregar dos arquivos locais
    df_analise_premios = pd.DataFrame()
    df_analise_dezenas = pd.DataFrame()
    data_bruta = []
    
    carregado_premios = False
    carregado_dezenas = False

    # Tenta carregar os CSVs
    if os.path.exists(file_path_premios) and os.path.exists(file_path_dezenas):
        try:
            df_premios_raw = pd.read_csv(file_path_premios)
            if not df_premios_raw.empty:
                # Transforma para df_analise_premios
                df_analise_premios = df_premios_raw.groupby(['uf', 'municipio']).size().reset_index(name='vezes_premiado')
                df_analise_premios['uf_municipio'] = df_analise_premios['uf'] + ' - ' + df_analise_premios['municipio']
                total_por_estado = df_premios_raw.groupby('uf').size().reset_index(name='total_premios_estado')
                df_analise_premios = pd.merge(df_analise_premios, total_por_estado, on='uf', how='left')
                carregado_premios = True
            
            df_analise_dezenas = pd.read_csv(file_path_dezenas)
            if not df_analise_dezenas.empty:
                df_analise_dezenas['dezena_int'] = df_analise_dezenas['dezena'].astype(int)
                carregado_dezenas = True
            
            if carregado_premios and carregado_dezenas:
                 st.info("Carregando dados processados dos arquivos locais...")
                 # Recarrega dados brutos apenas para a análise geral de sorteios
                 response = requests.get(url, timeout=30)
                 data_bruta = response.json()
                 return df_analise_premios, df_analise_dezenas, data_bruta
        except Exception:
            st.warning("Erro ao carregar arquivos CSV. Baixando dados da API para reprocessamento.")
    
    # 2. Baixar e Processar
    st.info("Baixando dados da API e processando...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data_bruta = response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao acessar a API: {e}")
        return pd.DataFrame(), pd.DataFrame(), []

    registros_premios = []
    contagem_dezenas = {d: 0 for d in TODAS_DEZENAS} 

    for sorteio in data_bruta:
        
        # --- PROCESSAMENTO DE PRÊMIOS (MUNICÍPIOS) ---
        local_ganhadores = sorteio.get('localGanhadores')
        if local_ganhadores and isinstance(local_ganhadores, list):
            for ganhador in local_ganhadores:
                quantidade = ganhador.get('quantidade', 1) 
                municipio = ganhador.get('municipio')
                uf = ganhador.get('uf')
                
                if municipio and uf and municipio != 'N/A' and uf != 'N/A':
                    for _ in range(quantidade):
                        registros_premios.append({
                            'concurso': sorteio.get('concurso'),
                            'data': sorteio.get('data'),
                            'municipio': municipio.upper().strip(), 
                            'uf': uf.upper().strip() 
                        })

        # --- PROCESSAMENTO DE DEZENAS SORTEADAS ---
        dezenas_sorteadas = sorteio.get('dezenas') 
        if dezenas_sorteadas and isinstance(dezenas_sorteadas, list):
            for dezena in dezenas_sorteadas:
                dezena_formatada = str(dezena).zfill(2)
                if dezena_formatada in contagem_dezenas:
                    contagem_dezenas[dezena_formatada] += 1
    
    # Criação e Salvamento dos DataFrames
    
    # DataFrame de Prêmios (Análise Municipal)
    df_premios_raw = pd.DataFrame(registros_premios)
    if not df_premios_raw.empty:
        df_premios_raw.dropna(subset=['municipio', 'uf'], inplace=True) 
        df_premios_raw.to_csv(file_path_premios, index=False)
        st.success(f"Dados de prêmios processados e salvos em: {file_path_premios}")
    
        df_analise_premios = df_premios_raw.groupby(['uf', 'municipio']).size().reset_index(name='vezes_premiado')
        df_analise_premios['uf_municipio'] = df_analise_premios['uf'] + ' - ' + df_analise_premios['municipio']
        total_por_estado = df_premios_raw.groupby('uf').size().reset_index(name='total_premios_estado')
        df_analise_premios = pd.merge(df_analise_premios, total_por_estado, on='uf', how='left')

    # DataFrame de Frequência de Dezenas
    df_analise_dezenas = pd.DataFrame(
        list(contagem_dezenas.items()), 
        columns=['dezena', 'ocorrencias']
    )
    if not df_analise_dezenas.empty:
        df_analise_dezenas['dezena'] = df_analise_dezenas['dezena'].astype(str)
        df_analise_dezenas['dezena_int'] = df_analise_dezenas['dezena'].astype(int)
        df_analise_dezenas.to_csv(file_path_dezenas, index=False)
        st.success(f"Dados de dezenas processados e salvos em: {file_path_dezenas}")

    return df_analise_premios, df_analise_dezenas, data_bruta

# --- 2. Funções de Visualização e Análise ---

def plot_top_municipios(df: pd.DataFrame, top_n: int):
    if df.empty: return None
    df_top = df.sort_values(by='vezes_premiado', ascending=False).head(top_n)
    fig = px.bar(
        df_top, x='vezes_premiado', y='uf_municipio', orientation='h',
        title=f'🏆 Top {top_n} Municípios Mais Premiados (Todas as UFs)',
        labels={'vezes_premiado': 'Número de Vezes Premiado', 'uf_municipio': 'Município (UF)'},
        color='uf', color_continuous_scale=px.colors.sequential.Viridis
    )
    fig.update_layout(yaxis={'categoryorder': 'total ascending'})
    return fig

def plot_estado_ranking(df: pd.DataFrame):
    if df.empty: return None
    df_estado = df[['uf', 'total_premios_estado']].drop_duplicates().sort_values(by='total_premios_estado', ascending=False)
    fig = px.bar(
        df_estado, x='uf', y='total_premios_estado',
        title='🗺️ Ranking de Estados por Total de Prêmios (Sena)',
        labels={'total_premios_estado': 'Total de Prêmios (Sena)', 'uf': 'Estado (UF)'},
        color='total_premios_estado'
    )
    return fig

def plot_municipios_por_estado(df: pd.DataFrame, estado: str, top_n: int):
    if df.empty: return None
    df_estado_completo = df[df['uf'] == estado]
    if df_estado_completo.empty: return None
        
    df_filtrado = df_estado_completo.sort_values(by='vezes_premiado', ascending=False).head(top_n)
    
    if len(df_estado_completo) > top_n:
        outras_cidades_count = df_estado_completo['vezes_premiado'].iloc[top_n:].sum()
        outros_df = pd.DataFrame([{'municipio': f'OUTROS ({len(df_estado_completo) - top_n} Cidades)', 'vezes_premiado': outras_cidades_count}])
        df_filtrado_aux = df_filtrado.drop(columns=[col for col in ['uf', 'total_premios_estado', 'uf_municipio'] if col in df_filtrado.columns])
        df_pizza = pd.concat([df_filtrado_aux, outros_df], ignore_index=True)
    else:
        df_pizza = df_filtrado.drop(columns=[col for col in ['uf', 'total_premios_estado', 'uf_municipio'] if col in df_filtrado.columns])

    fig = px.pie(
        df_pizza, values='vezes_premiado', names='municipio',
        title=f'🥧 Distribuição dos Prêmios (Sena) em **{estado}** (Top {min(top_n, len(df_estado_completo))} + Outros)',
        hole=.3
    )
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig

def plot_dezenas_frequencia(df: pd.DataFrame, title: str, top_n: int):
    """Gera um gráfico de barras para a frequência das dezenas (controlado por Top N)."""
    if df.empty: return None
    
    df_plot = df.sort_values(by='ocorrencias', ascending=False).head(top_n)
    
    fig = px.bar(
        df_plot.sort_values(by='dezena_int'),
        x='dezena', y='ocorrencias',
        title=title,
        labels={'dezena': 'Dezena', 'ocorrencias': 'Frequência (Ocorrências)'},
        color='ocorrencias',
        color_continuous_scale=px.colors.sequential.Sunsetdark
    )
    fig.update_layout(xaxis_tickangle=-90)
    return fig

def analisar_sorteios_gerais(data_bruta: list) -> dict:
    """
    Realiza a análise dos sorteios: datas, sem premiações de Sena, maior/menor número de premiações.
    """
    if not data_bruta: return {}
    
    df = pd.json_normalize(data_bruta)
    
    df['data'] = pd.to_datetime(df['data'], format='%d/%m/%Y', errors='coerce')
    
    df['premiações_sena'] = df.apply(
        lambda row: row.get('rateio.sena.quantidadeGanhadores', 0), axis=1
    ).fillna(0).astype(int)
    
    df['total_premiações'] = df.apply(
        lambda row: row.get('rateio.sena.quantidadeGanhadores', 0) + 
                    row.get('rateio.quina.quantidadeGanhadores', 0) + 
                    row.get('rateio.quadra.quantidadeGanhadores', 0), 
        axis=1
    ).fillna(0).astype(int)
    
    sorteios_sem_sena = df[df['premiações_sena'] == 0].shape[0]
    
    total_sorteios = len(df)
    primeiro_sorteio = df['data'].min().strftime('%d/%m/%Y')
    ultimo_sorteio = df['data'].max().strftime('%d/%m/%Y')
    
    df_premiações_validas = df[df['total_premiações'] > 0]

    if not df_premiações_validas.empty:
        idx_max_premiações = df_premiações_validas['total_premiações'].idxmax()
        idx_min_premiações = df_premiações_validas['total_premiações'].idxmin()

        max_premiações = df_premiações_validas.loc[idx_max_premiações]
        min_premiações = df_premiações_validas.loc[idx_min_premiações]

        max_result = {'concurso': max_premiações['concurso'], 'total': max_premiações['total_premiações']}
        min_result = {'concurso': min_premiações['concurso'], 'total': min_premiações['total_premiações']}
    else:
        max_result = {'concurso': 'N/A', 'total': 0}
        min_result = {'concurso': 'N/A', 'total': 0}

    return {
        'total_sorteios': total_sorteios,
        'primeiro_sorteio': primeiro_sorteio,
        'ultimo_sorteio': ultimo_sorteio,
        'sem_premiações_sena': sorteios_sem_sena,
        'max_premiações': max_result,
        'min_premiações': min_result
    }

# --- 3. Lógica de Sugestão de Jogos (CORRIGIDA) ---

def formatar_jogo(jogo: list):
    """
    Formata a lista de dezenas (que são strings de dois dígitos) em uma string.
    CORREÇÃO: Garantir que os itens da lista sejam strings antes de chamar join().
    Como o `random.sample` retorna os itens da coluna 'dezena' (que são strings),
    e o `sorted()` os converte para inteiro para ordenar se não for especificado,
    é crucial converter para string novamente e garantir o formato zfill(2).
    """
    # Mapeia para string e aplica zfill(2) (caso haja algum inteiro perdido)
    jogo_str = [str(d).zfill(2) for d in jogo]
    # Classifica as dezenas como strings e junta
    return ' - '.join(sorted(jogo_str))

def sugerir_jogos(df_dezenas: pd.DataFrame):
    """
    Gera 3 sugestões de jogos com base na frequência das dezenas.
    """
    if df_dezenas.empty:
        return {}

    df_sorted = df_dezenas.sort_values(by='ocorrencias', ascending=False)
    
    top_10 = df_sorted['dezena'].head(10).tolist()
    bottom_10 = df_sorted['dezena'].tail(10).tolist()
    
    # As listas top_10 e bottom_10 agora contêm strings formatadas ('01', '15', etc.)
    
    if len(top_10) < 6 or len(bottom_10) < 6:
        todas = df_sorted['dezena'].tolist()
        if len(todas) >= 6:
            jogo_mais = random.sample(todas, 6)
            jogo_menos = random.sample(todas, 6)
            jogo_misto = random.sample(todas, 6)
        else:
            return {} 
    else:
        # 1. Mais Sorteadas 
        jogo_mais = random.sample(top_10, 6)
        
        # 2. Menos Sorteadas 
        jogo_menos = random.sample(bottom_10, 6)
        
        # 3. Misturadas 
        parte_top = random.sample(top_10, 3)
        parte_bottom = random.sample(bottom_10, 3)
        
        jogo_misto = parte_top + parte_bottom
        random.shuffle(jogo_misto)
    
    return {
        "Mais Sorteadas (Top 10)": formatar_jogo(jogo_mais),
        "Menos Sorteadas (Bottom 10)": formatar_jogo(jogo_menos),
        "Misturadas (3 Top 10 / 3 Bottom 10)": formatar_jogo(jogo_misto)
    }

# --- 4. Layout do Dashboard Streamlit ---

st.set_page_config(layout="wide", page_title="Análise Mega-Sena", page_icon="💰")

st.title("💰 Dashboard de Análise de Premiações e Dezenas da Mega-Sena")
st.caption("Dados obtidos da API: https://loteriascaixa-api.herokuapp.com/api/megasena")

# Carregar e Processar os Dados
df_analise_premios, df_analise_dezenas, data_bruta = load_and_process_data(API_URL, CSV_FILE_PREMIOS, CSV_FILE_DEZENAS)

# --- Análise de Sorteios Gerais ---
st.markdown("---")
st.header("📊 Análise Geral dos Sorteios")

analise_geral = analisar_sorteios_gerais(data_bruta)

if analise_geral and analise_geral['total_sorteios'] > 0:
    st.markdown(f"**Total de Sorteios Analisados:** {analise_geral['total_sorteios']}")
    st.markdown(f"**Período:** {analise_geral['primeiro_sorteio']} até {analise_geral['ultimo_sorteio']}")
    
    col_analise_1, col_analise_2, col_analise_3 = st.columns(3)
    
    col_analise_1.metric(label="Sorteios Sem Premiação (6 Acertos)", 
                         value=f"{analise_geral['sem_premiações_sena']} ({analise_geral['sem_premiações_sena']/analise_geral['total_sorteios']:.1%})")
    
    col_analise_2.metric(label="Sorteio com Mais Premiações (Total)", 
                         value=f"{analise_geral['max_premiações']['total']:,}", 
                         delta=f"Concurso {analise_geral['max_premiações']['concurso']}")
                         
    col_analise_3.metric(label="Sorteio com Menos Premiações (Total)", 
                         value=f"{analise_geral['min_premiações']['total']:,}", 
                         delta=f"Concurso {analise_geral['min_premiações']['concurso']}",
                         delta_color="inverse")
else:
    st.error("Não foi possível realizar a análise geral dos sorteios (dados ausentes ou incompletos).")


# --- Seção 1: Análise de Dezenas Sorteadas ---
st.markdown("---")
st.header("🔢 Análise de Frequência das Dezenas Sorteadas")

if not df_analise_dezenas.empty:
    
    max_dezenas = df_analise_dezenas.shape[0]
    top_n_dezenas = st.slider(
        'Selecione a quantidade de Dezenas (Top N) para visualização',
        min_value=6,
        max_value=max_dezenas,
        value=30,
        step=6,
        key='slider_dezenas'
    )
    
    st.subheader(f"Frequência de Ocorrência das Top {top_n_dezenas} Dezenas")
    fig_dezenas = plot_dezenas_frequencia(df_analise_dezenas, "", top_n_dezenas)
    st.plotly_chart(fig_dezenas, use_container_width=True)

    # 1.1 Tabela de Top/Bottom
    col_dezenas_1, col_dezenas_2 = st.columns(2)
    df_ordenado = df_analise_dezenas.sort_values(by='ocorrencias', ascending=False).reset_index(drop=True)
    
    with col_dezenas_1:
        st.subheader("Dezenas Mais Sorteadas (Top 10)")
        df_top_clean = df_ordenado.head(10).drop(columns=['dezena_int']).rename(columns={'dezena': 'Dezena', 'ocorrencias': 'Frequência'}).reset_index(drop=True)
        st.dataframe(df_top_clean, use_container_width=True, hide_index=True)
        
    with col_dezenas_2:
        st.subheader("Dezenas Menos Sorteadas (Bottom 10)")
        df_bottom_clean = df_ordenado.tail(10).drop(columns=['dezena_int']).rename(columns={'dezena': 'Dezena', 'ocorrencias': 'Frequência'}).sort_values(by='Frequência', ascending=True).reset_index(drop=True)
        st.dataframe(df_bottom_clean, use_container_width=True, hide_index=True)

    st.markdown("---")

    # 1.2 Sugestão de Jogos
    st.header("🎯 Sugestão de Jogos")
    st.markdown("Baseado na análise de frequência histórica, aqui estão três sugestões de jogos de 6 dezenas. **Clique no botão para gerar um novo jogo aleatório**.")
    
    if st.button("Gerar Novos Jogos Sugeridos", type="primary"):
        st.session_state['jogos_sugeridos'] = sugerir_jogos(df_analise_dezenas)

    if 'jogos_sugeridos' not in st.session_state:
        st.session_state['jogos_sugeridos'] = sugerir_jogos(df_analise_dezenas)
        
    jogos = st.session_state['jogos_sugeridos']
    
    col_sug_1, col_sug_2, col_sug_3 = st.columns(3)
    
    col_sug_1.metric("🎲 Mais Sorteadas (Top 10)", jogos.get("Mais Sorteadas (Top 10)", "N/A"))
    col_sug_2.metric("🎲 Menos Sorteadas (Bottom 10)", jogos.get("Menos Sorteadas (Bottom 10)", "N/A"))
    col_sug_3.metric("🎲 Misturadas", jogos.get("Misturadas (3 Top 10 / 3 Bottom 10)", "N/A"))
    
else:
    st.error("Não foi possível carregar dados de dezenas sorteadas para esta análise.")

# --- Seção 2: Análise de Prêmios por Local (MUNICÍPIOS) ---

st.markdown("---")
st.header("🗺️ Análise de Prêmios por Local")

if not df_analise_premios.empty:
    
    # KPIs
    col_total, col_cidades, col_estados = st.columns(3)
    total_premios_sena = df_analise_premios['vezes_premiado'].sum()
    total_cidades = df_analise_premios['municipio'].nunique()
    total_estados = df_analise_premios['uf'].nunique()
    
    col_total.metric(label="Total de Premiações da Sena Registradas", value=f"{total_premios_sena:,.0f}")
    col_cidades.metric(label="Total de Cidades Premiadas", value=f"{total_cidades:,}")
    col_estados.metric(label="Total de Estados Premiados", value=f"{total_estados}")

    st.markdown("---")

    # Layout de 2 colunas para os gráficos principais
    col_viz_1, col_viz_2 = st.columns([1, 1])

    with col_viz_1:
        st.subheader("Top Municípios Mais Premiados")
        max_municipios = min(50, df_analise_premios.shape[0])
        top_n_municipios = st.slider(
            'Selecione o Top N de Municípios',
            min_value=5,
            max_value=max_municipios,
            value=10,
            step=5,
            key='slider_municipios'
        )
        
        fig1 = plot_top_municipios(df_analise_premios, top_n_municipios)
        if fig1:
            st.plotly_chart(fig1, use_container_width=True)

    with col_viz_2:
        st.subheader("Ranking de Prêmios por Estado")
        fig2 = plot_estado_ranking(df_analise_premios)
        if fig2:
            st.plotly_chart(fig2, use_container_width=True)
    
    st.markdown("---")
    
    st.subheader("Detalhe por Estado Selecionado")
    
    col_interativo_estado, col_interativo_pie = st.columns([1, 3])
    
    list_estados = sorted(df_analise_premios['uf'].unique().tolist())
    
    with col_interativo_estado:
        estado_selecionado = st.selectbox(
            '**Selecione o Estado (UF):**',
            options=list_estados,
            index=list_estados.index('SP') if 'SP' in list_estados else 0,
            key='dropdown_estado'
        )
        
        df_estado_filtro = df_analise_premios[df_analise_premios['uf'] == estado_selecionado]
        max_pie_value = min(15, df_estado_filtro.shape[0])
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
            fig3 = plot_municipios_por_estado(df_analise_premios, estado_selecionado, top_n_pie)
            if fig3:
                st.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")

    st.subheader("Tabela de Dados: Municípios Premiados por Estado")
    st.dataframe(df_analise_premios.sort_values(by=['total_premios_estado', 'vezes_premiado'], ascending=[False, False]), use_container_width=True)
else:
    st.error("Não foi possível carregar dados de prêmios por município para esta análise.")