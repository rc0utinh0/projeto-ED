import streamlit as st
import pandas as pd
import requests
import os
import plotly.express as px
import random
from typing import List, Dict, Any

# --- Configurações e Variáveis ---
API_URL = "https://loteriascaixa-api.herokuapp.com/api/megasena"
CSV_FILE_PREMIOS = "megasena_premios_municipios.csv"
CSV_FILE_DEZENAS = "megasena_dezenas_frequencia.csv"
CSV_FILE_STATUS = "megasena_sorteios_status.csv" 
TODAS_DEZENAS = [str(i).zfill(2) for i in range(1, 61)]


# --- 1. Funções de Obtenção e Processamento de Dados ---

def extract_ganhadores(sorteio: Dict[str, Any], acertos: str) -> int:
    """
    Extrai de forma segura a quantidade de ganhadores para 6, 5 ou 4 acertos,
    lidando com chaves ausentes ou nulas.
    """
    try:
        # Acessa a chave 'rateio', que é a principal
        rateio = sorteio.get('rateio')
        if not rateio or not isinstance(rateio, dict):
            return 0
        
        # Acessa a chave específica de acertos ('sena', 'quina', 'quadra')
        premio_detalhe = rateio.get(acertos)
        if not premio_detalhe or not isinstance(premio_detalhe, dict):
            return 0
        
        # Acessa a quantidade de ganhadores
        ganhadores = premio_detalhe.get('quantidadeGanhadores')
        
        # Garante que o valor é um inteiro ou retorna 0
        return int(ganhadores) if ganhadores is not None else 0
        
    except (TypeError, ValueError, AttributeError):
        # Em caso de qualquer erro de estrutura ou conversão, assume 0
        return 0

def process_premios_dataframe(df_premios_raw: pd.DataFrame) -> pd.DataFrame:
    """Aplica filtros e agrega o DataFrame de prêmios crus."""
    if df_premios_raw.empty:
        return pd.DataFrame()

    # Filtra e exclui UFs inválidas
    df_premios_raw['uf'] = df_premios_raw['uf'].str.strip()
    df_premios_raw = df_premios_raw[
        ~df_premios_raw['uf'].isin(['--', 'XX', 'N/A', '', None])
    ].copy()
    
    if df_premios_raw.empty:
        return pd.DataFrame()
        
    df_analise_premios = df_premios_raw.groupby(['uf', 'municipio']).size().reset_index(name='vezes_premiado')
    df_analise_premios['uf_municipio'] = df_analise_premios['uf'] + ' - ' + df_analise_premios['municipio']
    total_por_estado = df_premios_raw.groupby('uf').size().reset_index(name='total_premios_estado')
    df_analise_premios = pd.merge(df_analise_premios, total_por_estado, on='uf', how='left')
    
    return df_analise_premios


@st.cache_data
def load_and_process_data(url: str, file_path_premios: str, file_path_dezenas: str, file_path_status: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list]:
    """
    Baixa os dados da API, processa e armazena/carrega os arquivos CSV.
    Retorna: (DF Prêmios, DF Dezenas, DF Status, Lista de Dados Brutos para Análise de Sorteios).
    """
    df_analise_premios = pd.DataFrame()
    df_analise_dezenas = pd.DataFrame()
    df_analise_status = pd.DataFrame()
    data_bruta = []
    
    # 1. Tenta carregar dos arquivos locais
    carregado_completo = all(os.path.exists(f) for f in [file_path_premios, file_path_dezenas, file_path_status])

    if carregado_completo:
        try:
            st.info("Carregando dados processados dos arquivos locais...")
            
            # DF Prêmios (Carrega o raw e aplica o filtro novamente para robustez)
            df_premios_raw = pd.read_csv(file_path_premios)
            df_analise_premios = process_premios_dataframe(df_premios_raw)
            
            # DF Dezenas
            df_analise_dezenas = pd.read_csv(file_path_dezenas)
            df_analise_dezenas['dezena_int'] = df_analise_dezenas['dezena'].astype(int)
            
            # DF Status
            df_analise_status = pd.read_csv(file_path_status)
            
            # Recarrega dados brutos apenas para a análise geral de sorteios
            response = requests.get(url, timeout=30)
            data_bruta = response.json()
            return df_analise_premios, df_analise_dezenas, df_analise_status, data_bruta
        except Exception as e:
            st.warning(f"Erro ao carregar arquivos CSV ({e}). Baixando dados da API para reprocessamento.")
    
    # 2. Baixar e Processar
    st.info("Baixando dados da API e processando...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data_bruta = response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao acessar a API: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), []

    registros_premios = []
    contagem_dezenas = {d: 0 for d in TODAS_DEZENAS} 
    registros_status = [] 

    for sorteio in data_bruta:
        concurso = sorteio.get('concurso')

        # --- PROCESSAMENTO DE PRÊMIOS (MUNICÍPIOS) ---
        local_ganhadores = sorteio.get('localGanhadores')
        if local_ganhadores and isinstance(local_ganhadores, list):
            for ganhador in local_ganhadores:
                quantidade = ganhador.get('quantidade', 1) 
                municipio = ganhador.get('municipio')
                uf = ganhador.get('uf')
                
                # A coleta inicial aceita N/A, a filtragem será feita depois
                if municipio and uf:
                    # Garantir que os dados de texto estejam limpos o suficiente para o filtro
                    municipio_limpo = municipio.upper().strip()
                    uf_limpo = uf.upper().strip()
                    
                    if municipio_limpo != 'N/A' and uf_limpo != 'N/A':
                        for _ in range(quantidade):
                            registros_premios.append({
                                'concurso': concurso,
                                'data': sorteio.get('data'),
                                'municipio': municipio_limpo, 
                                'uf': uf_limpo 
                            })

        # --- PROCESSAMENTO DE DEZENAS SORTeadAS ---
        dezenas_sorteadas = sorteio.get('dezenas') 
        if dezenas_sorteadas and isinstance(dezenas_sorteadas, list):
            for dezena in dezenas_sorteadas:
                dezena_formatada = str(dezena).zfill(2)
                if dezena_formatada in contagem_dezenas:
                    contagem_dezenas[dezena_formatada] += 1
        
        # --- PROCESSAMENTO DE STATUS DE GANHADORES ---
        ganhadores_sena = extract_ganhadores(sorteio, 'sena')
        ganhadores_quina = extract_ganhadores(sorteio, 'quina')
        ganhadores_quadra = extract_ganhadores(sorteio, 'quadra')

        registros_status.append({
            'concurso': concurso,
            'premiações_sena': ganhadores_sena,
            'premiações_quina': ganhadores_quina,
            'premiações_quadra': ganhadores_quadra
        })
    
    # Criação e Salvamento dos DataFrames
    
    # 1. DataFrame de Prêmios (Análise Municipal)
    df_premios_raw = pd.DataFrame(registros_premios)
    if not df_premios_raw.empty:
        df_premios_raw.dropna(subset=['municipio', 'uf'], inplace=True) 
        
        # Filtra e salva o arquivo raw APÓS a limpeza de N/A 
        df_premios_raw.to_csv(file_path_premios, index=False)
        st.success(f"Dados de prêmios crus salvos em: {file_path_premios}")
        
        # Processa e agrega o DF de análise, aplicando a exclusão de UFs inválidas (--, XX)
        df_analise_premios = process_premios_dataframe(df_premios_raw)
        
        if df_analise_premios.empty:
            st.warning("Nenhum dado de prêmios válido permaneceu após a filtragem de UFs.")


    # 2. DataFrame de Frequência de Dezenas
    df_analise_dezenas = pd.DataFrame(
        list(contagem_dezenas.items()), 
        columns=['dezena', 'ocorrencias']
    )
    if not df_analise_dezenas.empty:
        df_analise_dezenas['dezena'] = df_analise_dezenas['dezena'].astype(str)
        df_analise_dezenas['dezena_int'] = df_analise_dezenas['dezena'].astype(int)
        df_analise_dezenas.to_csv(file_path_dezenas, index=False)
        st.success(f"Dados de dezenas processados e salvos em: {file_path_dezenas}")

    # 3. DataFrame de Status de Premiação
    df_analise_status = pd.DataFrame(registros_status)
    if not df_analise_status.empty:
        df_analise_status['total_premiações'] = (
            df_analise_status['premiações_sena'] + 
            df_analise_status['premiações_quina'] + 
            df_analise_status['premiações_quadra']
        )
        df_analise_status.to_csv(file_path_status, index=False)
        st.success(f"Dados de status de premiações processados e salvos em: {file_path_status}")


    return df_analise_premios, df_analise_dezenas, df_analise_status, data_bruta

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
        
    n_cidades_estado = len(df_estado_completo)
    top_n_ajustado = min(top_n, n_cidades_estado)
    
    df_filtrado = df_estado_completo.sort_values(by='vezes_premiado', ascending=False).head(top_n_ajustado)
    
    if n_cidades_estado > top_n_ajustado and n_cidades_estado > 1:
        # Cria o segmento 'OUTROS'
        outras_cidades_count = df_estado_completo['vezes_premiado'].iloc[top_n_ajustado:].sum()
        outros_df = pd.DataFrame([{'municipio': f'OUTROS ({n_cidades_estado - top_n_ajustado} Cidades)', 'vezes_premiado': outras_cidades_count}])
        
        # Prepara a concatenação
        df_filtrado_aux = df_filtrado.drop(columns=[col for col in ['uf', 'total_premios_estado', 'uf_municipio'] if col in df_filtrado.columns], errors='ignore')
        df_pizza = pd.concat([df_filtrado_aux, outros_df], ignore_index=True)
    else:
        # Se n_cidades_estado <= top_n_ajustado, ou se for zero, não há 'OUTROS'
        df_pizza = df_filtrado.drop(columns=[col for col in ['uf', 'total_premios_estado', 'uf_municipio'] if col in df_filtrado.columns], errors='ignore')

    fig = px.pie(
        df_pizza, values='vezes_premiado', names='municipio',
        title=f'🥧 Distribuição dos Prêmios (Sena) em **{estado}** (Top {top_n_ajustado} + Outros)',
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

def analisar_sorteios_gerais(df_analise_status: pd.DataFrame, data_bruta: list) -> dict:
    """
    Realiza a análise dos sorteios, usando o novo DF_STATUS processado.
    """
    if df_analise_status.empty or not data_bruta: return {}
    
    # Merge com dados brutos para obter datas, etc.
    df_bruto = pd.json_normalize(data_bruta)
    df_bruto['concurso'] = df_bruto['concurso'].astype(str)
    
    # Garante que 'concurso' no status seja string para merge seguro
    df_analise_status['concurso'] = df_analise_status['concurso'].astype(str)
    
    # Merge, mantendo apenas as colunas necessárias do bruto
    df = pd.merge(df_analise_status, df_bruto[['concurso', 'data']], on='concurso', how='left')
    
    if df.empty: return {}
    
    df['data'] = pd.to_datetime(df['data'], format='%d/%m/%Y', errors='coerce')
    
    # Contagem de Sorteios Com Premiação (> 0 ganhadores)
    sorteios_com_sena = df[df['premiações_sena'] > 0].shape[0]
    sorteios_com_quina = df[df['premiações_quina'] > 0].shape[0]
    sorteios_com_quadra = df[df['premiações_quadra'] > 0].shape[0]

    # Análise geral
    total_sorteios = len(df)
    primeiro_sorteio = df['data'].min().strftime('%d/%m/%Y') if not df['data'].min() is pd.NaT else 'N/A'
    ultimo_sorteio = df['data'].max().strftime('%d/%m/%Y') if not df['data'].max() is pd.NaT else 'N/A'
    
    # Mais/Menos premiações gerais (usando a coluna total_premiações do DF_STATUS)
    df_premiações_validas = df[df['total_premiações'] > 0].sort_values(by='total_premiações', ascending=False)

    max_result = {'concurso': 'N/A', 'total': 0}
    min_result = {'concurso': 'N/A', 'total': 0}

    if not df_premiações_validas.empty:
        max_premiações = df_premiações_validas.iloc[0]
        min_premiações = df_premiações_validas.iloc[-1]

        max_result = {'concurso': max_premiações['concurso'], 'total': max_premiações['total_premiações']}
        min_result = {'concurso': min_premiações['concurso'], 'total': min_premiações['total_premiações']}

    return {
        'total_sorteios': total_sorteios,
        'primeiro_sorteio': primeiro_sorteio,
        'ultimo_sorteio': ultimo_sorteio,
        # O resultado da métrica é: Total de Sorteios - Sorteios COM premiados
        'sem_premiações_sena': total_sorteios - sorteios_com_sena,
        'sem_premiações_quina': total_sorteios - sorteios_com_quina,
        'sem_premiações_quadra': total_sorteios - sorteios_com_quadra,
        'max_premiações': max_result,
        'min_premiações': min_result
    }

# --- 3. Lógica de Sugestão de Jogos ---

def formatar_jogo(jogo: list):
    """
    Formata a lista de dezenas (strings de dois dígitos) em uma string.
    """
    jogo_str = [str(d).zfill(2) for d in jogo]
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
    
    if len(top_10) < 6 or len(bottom_10) < 6:
        todas = df_sorted['dezena'].tolist()
        if len(todas) >= 6:
            jogo_mais = random.sample(todas, 6)
            jogo_menos = random.sample(todas, 6)
            jogo_misto = random.sample(todas, 6)
        else:
            return {} 
    else:
        jogo_mais = random.sample(top_10, 6)
        jogo_menos = random.sample(bottom_10, 6)
        
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
df_analise_premios, df_analise_dezenas, df_analise_status, data_bruta = load_and_process_data(API_URL, CSV_FILE_PREMIOS, CSV_FILE_DEZENAS, CSV_FILE_STATUS)

# --- Análise de Sorteios Gerais ---
st.markdown("---")
st.header("📊 Análise Geral dos Sorteios")

# Agora a função analisar_sorteios_gerais usa o DF_STATUS
analise_geral = analisar_sorteios_gerais(df_analise_status, data_bruta)

if analise_geral and analise_geral['total_sorteios'] > 0:
    st.markdown(f"**Total de Sorteios Analisados:** {analise_geral['total_sorteios']:,}")
    st.markdown(f"**Período:** {analise_geral['primeiro_sorteio']} até {analise_geral['ultimo_sorteio']}")
    
    col_analise_1, col_analise_2, col_analise_3 = st.columns(3)
    
    total = analise_geral['total_sorteios']
    
    # 1. Premiações de 6 Acertos (Sena)
    col_analise_1.metric(label="Sorteios Sem Premiação (6 Acertos)", 
                         value=f"{analise_geral['sem_premiações_sena']:,} ({analise_geral['sem_premiações_sena']/total:.1%})",
                         help=f"Total de sorteios com premiação de 6 acertos: {total - analise_geral['sem_premiações_sena']:,}")
    
    # 2. Premiações de 5 Acertos (Quina)
    col_analise_2.metric(label="Sorteios Sem Premiação (5 Acertos)", 
                         value=f"{analise_geral['sem_premiações_quina']:,} ({analise_geral['sem_premiações_quina']/total:.1%})",
                         help=f"Total de sorteios com premiação de 5 acertos: {total - analise_geral['sem_premiações_quina']:,}")
                         
    # 3. Premiações de 4 Acertos (Quadra)
    col_analise_3.metric(label="Sorteios Sem Premiação (4 Acertos)", 
                         value=f"{analise_geral['sem_premiações_quadra']:,} ({analise_geral['sem_premiações_quadra']/total:.1%})",
                         help=f"Total de sorteios com premiação de 4 acertos: {total - analise_geral['sem_premiações_quadra']:,}")
    
    st.markdown("---")

    col_geral_1, col_geral_2 = st.columns(2)
    
    col_geral_1.metric(label="Sorteio com Mais Premiações (Total)", 
                         value=f"{analise_geral['max_premiações']['total']:,}", 
                         delta=f"Concurso {analise_geral['max_premiações']['concurso']}")
                         
    col_geral_2.metric(label="Sorteio com Menos Premiações (Total)", 
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
    col_estados.metric(label="Total de Estados Válidos Premiados", value=f"{total_estados}")

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
        # Garante que a lista de estados não está vazia
        if list_estados:
            estado_selecionado = st.selectbox(
                '**Selecione o Estado (UF):**',
                options=list_estados,
                index=list_estados.index('SP') if 'SP' in list_estados else 0,
                key='dropdown_estado'
            )
        else:
            estado_selecionado = None
            st.warning("Não há estados válidos para seleção após a filtragem.")
        
        df_estado_filtro = df_analise_premios[df_analise_premios['uf'] == estado_selecionado] if estado_selecionado else pd.DataFrame()
        n_cidades_estado = df_estado_filtro.shape[0]
        
        # Define os valores máximo e mínimo para o slider (Top N para o gráfico de pizza)
        max_pie_value = min(15, n_cidades_estado)
        min_pie_value = 1
        
        top_n_pie = 0 
        
        # >>> CORREÇÃO APLICADA AQUI: Condiciona o slider apenas se houver 2 ou mais cidades <<<
        if n_cidades_estado == 0:
            st.info(f"O estado de {estado_selecionado} não possui cidades premiadas válidas registradas.")
            top_n_pie = 0
        elif n_cidades_estado == 1:
            st.info(f"O estado de {estado_selecionado} possui apenas 1 cidade premiada.")
            top_n_pie = 1
        else:
            # Estado tem 2 ou mais cidades, o slider é necessário e funcional
            # Garante que o valor padrão do slider é válido (entre min e max)
            current_slider_value = st.session_state.get('slider_pie', default=8)
            default_value = min(max(current_slider_value, min_pie_value), max_pie_value)

            top_n_pie = st.slider(
                'Top N de Cidades no Gráfico de Pizza (Porcentagem)',
                min_value=min_pie_value,
                # O max_value agora será maior que o min_value (1)
                max_value=max_pie_value, 
                value=default_value,
                step=1,
                key='slider_pie' 
            )
        # >>> FIM DA CORREÇÃO <<<
        
    with col_interativo_pie:
        if estado_selecionado and n_cidades_estado > 0:
            # A função plot_municipios_por_estado usa n_cidades_estado e top_n_pie para determinar se cria o segmento "Outros"
            fig3 = plot_municipios_por_estado(df_analise_premios, estado_selecionado, top_n_pie)
            if fig3:
                st.plotly_chart(fig3, use_container_width=True)
        elif not estado_selecionado:
             st.info("Selecione um estado no menu ao lado para visualizar a distribuição dos prêmios.")

    st.markdown("---")

    st.subheader("Tabela de Dados: Municípios Premiados por Estado")
    st.dataframe(df_analise_premios.sort_values(by=['total_premios_estado', 'vezes_premiado'], ascending=[False, False]), use_container_width=True)
else:
    st.error("Não foi possível carregar dados de prêmios por município para esta análise após a filtragem.")