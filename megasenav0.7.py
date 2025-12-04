import streamlit as st
import pandas as pd
import requests
import os
import plotly.express as px
import random
from typing import List, Dict, Any, Tuple

# --- Configurações e Variáveis ---
API_URL = "https://loteriascaixa-api.herokuapp.com/api/megasena"
CSV_FILE_PREMIOS = "megasena_premios_municipios.csv"
CSV_FILE_DEZENAS = "megasena_dezenas_frequencia.csv"
TODAS_DEZENAS = [str(i).zfill(2) for i in range(1, 61)]


# --- 1. Funções de Obtenção e Processamento de Dados ---

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
def load_and_process_data(url: str, file_path_premios: str, file_path_dezenas: str) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """
    Baixa os dados da API, processa e armazena/carrega os arquivos CSV.
    Retorna: (DF Prêmios, DF Dezenas, Lista de Dados Brutos).
    """
    df_analise_premios = pd.DataFrame()
    df_analise_dezenas = pd.DataFrame()
    data_bruta = []
    
    arquivos_locais = [file_path_premios, file_path_dezenas]
    carregado_completo = all(os.path.exists(f) for f in arquivos_locais)

    if carregado_completo:
        try:
            # st.info("Carregando dados processados dos arquivos locais...")
            
            df_premios_raw = pd.read_csv(file_path_premios)
            df_analise_premios = process_premios_dataframe(df_premios_raw)
            
            df_analise_dezenas = pd.read_csv(file_path_dezenas)
            df_analise_dezenas['dezena_int'] = df_analise_dezenas['dezena'].astype(int)
            
            # Tenta baixar a data_bruta para garantir que a lista de sorteios esteja atualizada
            response = requests.get(url, timeout=30)
            data_bruta = response.json()
            return df_analise_premios, df_analise_dezenas, data_bruta
        except Exception as e:
            st.warning(f"Erro ao carregar arquivos CSV ou API ({e}). Baixando dados da API para reprocessamento.")
    
    # 2. Baixar e Processar
    # st.info("Baixando dados da API e processando...")
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
        concurso = sorteio.get('concurso')

        # --- PROCESSAMENTO DE PRÊMIOS (MUNICÍPIOS) ---
        local_ganhadores = sorteio.get('localGanhadores')
        if local_ganhadores and isinstance(local_ganhadores, list):
            for ganhador in local_ganhadores:
                quantidade = ganhador.get('quantidade', 1) 
                municipio = ganhador.get('municipio')
                uf = ganhador.get('uf')
                
                if municipio and uf:
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
    
    # Criação e Salvamento dos DataFrames
    
    # 1. DataFrame de Prêmios (Análise Municipal)
    df_premios_raw = pd.DataFrame(registros_premios)
    if not df_premios_raw.empty:
        df_premios_raw.dropna(subset=['municipio', 'uf'], inplace=True) 
        
        df_premios_raw.to_csv(file_path_premios, index=False)
        # st.success(f"Dados de prêmios crus salvos em: {file_path_premios}")
        
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
        # st.success(f"Dados de dezenas processados e salvos em: {file_path_dezenas}")
    

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

def analisar_sorteios_gerais(data_bruta: list) -> dict:
    """
    Realiza a análise básica dos sorteios (Total e Período).
    """
    if not data_bruta: return {}
    
    df_bruto = pd.json_normalize(data_bruta)
    
    total_sorteios = len(df_bruto)
    
    # Processa as datas para obter o período
    df_bruto['data'] = pd.to_datetime(df_bruto['data'], format='%d/%m/%Y', errors='coerce')
    
    primeiro_sorteio = df_bruto['data'].min().strftime('%d/%m/%Y') if not df_bruto['data'].min() is pd.NaT else 'N/A'
    ultimo_sorteio = df_bruto['data'].max().strftime('%d/%m/%Y') if not df_bruto['data'].max() is pd.NaT else 'N/A'
    
    return {
        'total_sorteios': total_sorteios,
        'primeiro_sorteio': primeiro_sorteio,
        'ultimo_sorteio': ultimo_sorteio,
    }

# --- 3. Lógica de Sugestão e Análise de Jogos ---

def normalize_game(jogo: List[str] | List[int]) -> str:
    """
    Formata a lista de dezenas (strings ou ints) em uma string padronizada e ordenada: '01-02-03-04-05-06'.
    """
    jogo_str = [str(d).zfill(2) for d in jogo]
    return '-'.join(sorted(jogo_str))

def formatar_jogo_display(jogo: str):
    """
    Formata a string padronizada ('01-02-03-04-05-06') para exibição ('01 - 02 - 03 - 04 - 05 - 06').
    """
    return ' - '.join(jogo.split('-'))

def sugerir_jogos(df_dezenas: pd.DataFrame, num_jogos: int) -> Dict[str, List[str]]:
    """
    Gera N sugestões de jogos para cada categoria (Mais, Menos, Misturadas) 
    com base na frequência das dezenas.
    Retorna: {'Categoria': [jogo_normalizado_1, jogo_normalizado_2, ...]}
    """
    if df_dezenas.empty:
        return {}
    
    df_sorted = df_dezenas.sort_values(by='ocorrencias', ascending=False)
    
    # Garante que há pelo menos 10 dezenas para fazer as amostras TOP/BOTTOM
    if df_sorted.shape[0] < 10:
        todas = df_sorted['dezena'].tolist()
        if len(todas) < 6:
             return {}
        
        # Se os dados são insuficientes, apenas sugere jogos aleatórios
        jogos_mais = [normalize_game(random.sample(todas, 6)) for _ in range(num_jogos)]
        jogos_menos = [normalize_game(random.sample(todas, 6)) for _ in range(num_jogos)]
        jogos_misto = [normalize_game(random.sample(todas, 6)) for _ in range(num_jogos)]
        
        return {
            "Mais Sorteadas (Top 10)": jogos_mais,
            "Menos Sorteadas (Bottom 10)": jogos_menos,
            "Misturadas (3 Top 10 / 3 Bottom 10)": jogos_misto
        }

    # Dezenas para amostragem
    top_10 = df_sorted['dezena'].head(10).tolist()
    bottom_10 = df_sorted['dezena'].tail(10).tolist()
    
    # 1. Jogo com Mais Sorteadas (amostra do Top 10)
    jogos_mais = []
    for _ in range(num_jogos):
        jogo = random.sample(top_10, 6)
        jogos_mais.append(normalize_game(jogo))

    # 2. Jogo com Menos Sorteadas (amostra do Bottom 10)
    jogos_menos = []
    for _ in range(num_jogos):
        jogo = random.sample(bottom_10, 6)
        jogos_menos.append(normalize_game(jogo))

    # 3. Jogo Misto (3 Top 10 / 3 Bottom 10)
    jogos_misto = []
    for _ in range(num_jogos):
        parte_top = random.sample(top_10, 3)
        parte_bottom = random.sample(bottom_10, 3)
        jogo = parte_top + parte_bottom
        random.shuffle(jogo)
        jogos_misto.append(normalize_game(jogo))
    
    return {
        "Mais Sorteadas (Top 10)": jogos_mais,
        "Menos Sorteadas (Bottom 10)": jogos_menos,
        "Misturadas (3 Top 10 / 3 Bottom 10)": jogos_misto
    }

@st.cache_data
def analisar_repeticao_jogos(data_bruta: List[Dict[str, Any]]) -> Tuple[int, Dict[str, List[int]]]:
    """
    Verifica se algum conjunto de 6 dezenas já se repetiu no histórico e
    cria um mapa de todos os sorteios (jogo padronizado -> concursos).
    Retorna: (Número de Repetições, Mapa de Sorteios).
    """
    if not data_bruta:
        return 0, {}

    # Mapeia a sequência normalizada (string) para uma lista de concursos que a sortearam
    mapa_sorteios: Dict[str, List[int]] = {}
    
    for sorteio in data_bruta:
        concurso = sorteio.get('concurso')
        dezenas = sorteio.get('dezenas')
        
        if dezenas and len(dezenas) == 6:
            jogo_normalizado = normalize_game(dezenas)
            
            if jogo_normalizado in mapa_sorteios:
                mapa_sorteios[jogo_normalizado].append(concurso)
            else:
                mapa_sorteios[jogo_normalizado] = [concurso]
    
    # Conta repetições (jogos que foram sorteados mais de uma vez)
    # total_repeticoes é a soma de (ocorrências - 1) para jogos com mais de 1 ocorrência
    total_repeticoes = sum(len(concursos) - 1 for concursos in mapa_sorteios.values() if len(concursos) > 1)

    return total_repeticoes, mapa_sorteios

def verificar_sugestao_historico(jogo_normalizado: str, mapa_sorteios: Dict[str, List[int]]) -> str:
    """
    Verifica se o jogo sugerido já foi sorteado no histórico e retorna o resultado formatado.
    """
    if jogo_normalizado in mapa_sorteios:
        concursos = mapa_sorteios[jogo_normalizado]
        return f"**SIM!** Sorteado nos Concursos: {', '.join(map(str, concursos))}"
    else:
        return "**NÃO.** Jogo inédito no histórico."
            
    return "Erro de verificação"


# --- 4. Layout do Dashboard Streamlit ---

st.set_page_config(layout="wide", page_title="Análise Mega-Sena", page_icon="💰")

st.title("💰 Dashboard de Análise de Premiações e Dezenas da Mega-Sena")
st.caption("Dados obtidos da API: https://loteriascaixa-api.herokuapp.com/api/megasena")

# Carregar e Processar os Dados
df_analise_premios, df_analise_dezenas, data_bruta = load_and_process_data(API_URL, CSV_FILE_PREMIOS, CSV_FILE_DEZENAS)

# ----------------------------------------------------
# --- Análise de Sorteios Gerais (Básica) ---
# ----------------------------------------------------
st.markdown("---")
st.header("📊 Análise Geral dos Sorteios")

analise_geral = analisar_sorteios_gerais(data_bruta)

if analise_geral and analise_geral['total_sorteios'] > 0:
    col_analise_1, col_analise_2, col_analise_3 = st.columns(3)
    
    col_analise_1.metric(label="Total de Sorteios Analisados", 
                        value=f"{analise_geral['total_sorteios']:,}")
    
    col_analise_2.metric(label="Período - Primeiro Sorteio", 
                        value=analise_geral['primeiro_sorteio'])
                        
    col_analise_3.metric(label="Período - Último Sorteio", 
                        value=analise_geral['ultimo_sorteio'])
    
else:
    st.error("Não foi possível realizar a análise geral dos sorteios (dados ausentes ou incompletos).")


# ----------------------------------------------------
# --- Seção 1: Análise de Frequência das Dezenas Sorteadas ---
# ----------------------------------------------------
st.markdown("---")
st.header("🔢 Análise de Frequência das Dezenas Sorteadas")

if not df_analise_dezenas.empty:
    
    # Elemento Interativo 1: Slider de Dezenas
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

    # 1.2 Sugestão de Jogos e Verificação de Histórico
    st.header("🎯 Sugestão de Jogos e Verificação de Repetição")
    
    # Elemento Interativo 2: Slider de Sugestões
    num_sugestoes = st.slider(
        '**Número de Sugestões de Jogos (por categoria)**',
        min_value=1,
        max_value=30,
        value=1,
        step=1,
        key='slider_sugestoes'
    )

    # Lógica para gerar ou regerar os jogos
    # Usa a session_state para persistir jogos até que o botão ou slider seja alterado
    if 'jogos_sugeridos' not in st.session_state or st.button("Gerar Novos Jogos Sugeridos", type="primary"):
        st.session_state['jogos_sugeridos'] = sugerir_jogos(df_analise_dezenas, num_sugestoes)
        
    # Se o slider for alterado, regera os jogos automaticamente
    if st.session_state.get('last_num_sugestoes', 1) != num_sugestoes:
         st.session_state['jogos_sugeridos'] = sugerir_jogos(df_analise_dezenas, num_sugestoes)
         st.session_state['last_num_sugestoes'] = num_sugestoes


    # Carregar análise de repetição
    total_repeticoes, mapa_sorteios = analisar_repeticao_jogos(data_bruta)
    jogos_sugeridos = st.session_state['jogos_sugeridos']
    
    # ----------------------------------------------------
    # --- ANÁLISE DE REPETIÇÃO DE JOGOS VENCEDORES ---
    # ----------------------------------------------------
    st.subheader("Análise Histórica de Repetição de Sequências")
    st.info(f"Em um total de **{analise_geral.get('total_sorteios', 0)}** sorteios analisados, a Mega-Sena já teve **{total_repeticoes}** repetição(ões) de jogos vencedores (o mesmo conjunto de 6 dezenas) em concursos diferentes.")
    st.caption("A probabilidade de um jogo de 6 dezenas se repetir é de 1 em 50.063.860. (Fonte: Matemática)")
    
    st.markdown("---")
    
    # ----------------------------------------------------
    # --- VERIFICAÇÃO DE SUGESTÕES NO HISTÓRICO ---
    # ----------------------------------------------------
    st.subheader(f"Verificação das {num_sugestoes} Sugestões no Histórico da Mega-Sena")
    
    # Exibir resultados
    col_tipos = st.columns(3)
    
    categorias = ["Mais Sorteadas (Top 10)", "Menos Sorteadas (Bottom 10)", "Misturadas (3 Top 10 / 3 Bottom 10)"]
    icones = ["🌟", "📉", "🔄"]
    
    for i, categoria in enumerate(categorias):
        with col_tipos[i]:
            st.markdown(f"### {icones[i]} {categoria}")
            if categoria in jogos_sugeridos and jogos_sugeridos[categoria]:
                # Cria uma sub-coluna ou expander para cada sugestão
                for j, jogo_normalizado in enumerate(jogos_sugeridos[categoria]):
                    st.markdown(f"**Sugestão {j+1}:** {formatar_jogo_display(jogo_normalizado)}")
                    resultado = verificar_sugestao_historico(jogo_normalizado, mapa_sorteios)
                    st.markdown(f"**Já Sorteado?** {resultado}")
                    st.markdown("---", help="Separador de Jogos")
            else:
                st.info("Nenhuma sugestão gerada para esta categoria.")
        
else:
    st.error("Não foi possível carregar dados de dezenas sorteadas para esta análise.")

# ----------------------------------------------------
# --- Seção 2: Análise de Prêmios por Local (MUNICÍPIOS) ---
# ----------------------------------------------------

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
        
        # Elemento Interativo 3: Slider de Municípios
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
        if list_estados:
            # Elemento Interativo 4: Dropdown de Estados
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
        
        max_pie_value = min(15, n_cidades_estado)
        min_pie_value = 1
        
        top_n_pie = 0 
        
        if n_cidades_estado == 0:
            st.info(f"O estado de {estado_selecionado} não possui cidades premiadas válidas registradas.")
            top_n_pie = 0
        elif n_cidades_estado == 1:
            st.info(f"O estado de {estado_selecionado} possui apenas 1 cidade premiada.")
            top_n_pie = 1
        else:
            # Elemento Interativo 5: Slider de Cidades (Gráfico de Pizza)
            current_slider_value = st.session_state.get('slider_pie', default=8)
            default_value = min(max(current_slider_value, min_pie_value), max_pie_value)

            top_n_pie = st.slider(
                'Top N de Cidades no Gráfico de Pizza (Porcentagem)',
                min_value=min_pie_value,
                max_value=max_pie_value, 
                value=default_value,
                step=1,
                key='slider_pie' 
            )
        
    with col_interativo_pie:
        if estado_selecionado and n_cidades_estado > 0:
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