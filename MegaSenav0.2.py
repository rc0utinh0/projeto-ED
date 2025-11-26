import streamlit as st
import pandas as pd
import requests
import json
import os
import matplotlib.pyplot as plt
from collections import Counter
import random
from datetime import datetime 

# Configuração da página deve ser a primeira chamada Streamlit
st.set_page_config(page_title="Dashboard Mega Sena", layout="wide")

# ----------------------------------------------------------
# FUNÇÃO PARA BAIXAR DADOS DA API E SALVAR LOCALMENTE
# ----------------------------------------------------------
def baixar_dados():
    url = "https://loteriascaixa-api.herokuapp.com/api/megasena"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status() 

        dados = response.json()
        with open("mega_sena.json", "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
        st.success("Dados atualizados com sucesso da API!")
        return dados
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao acessar API ou salvar o arquivo: {e}")
        return None

# ----------------------------------------------------------
# CARREGAR DADOS DO ARQUIVO
# ----------------------------------------------------------
@st.cache_data(ttl=3600) 
def carregar_dados():
    if os.path.exists("mega_sena.json"):
        with open("mega_sena.json", "r", encoding="utf-8") as f:
            st.info("Carregando dados do arquivo local...")
            return json.load(f)
    else:
        st.warning("Arquivo local não encontrado. Tentando baixar da API...")
        return baixar_dados()
    
# Função auxiliar para extrair o valor de ganhadores (por acerto) do 'rateio'
def get_ganhadores(rateio_list, acertos):
    """Extrai o número de ganhadores de um nível de acerto específico dentro da lista 'rateio'."""
    if isinstance(rateio_list, list):
        for item in rateio_list:
            if item.get('acertos') == acertos:
                return item.get('ganhadores', 0)
    return 0

# ----------------------------------------------------------
# PROCESSAR DADOS
# ----------------------------------------------------------
dados = carregar_dados()

if dados is None:
    st.stop()

df = pd.DataFrame(dados)

# ----------------------------------------------------------
# 1. RENOMEAR E CONVERTER COLUNA DE DATA (dataApuracao)
# ----------------------------------------------------------
if 'data' in df.columns:
    df = df.rename(columns={'data': 'data_concurso'})
    df['data_concurso'] = pd.to_datetime(df['data_concurso'], format='%d/%m/%Y', errors='coerce')
else:
    df['data_concurso'] = pd.NaT 
    st.warning("A chave 'dataApuracao' não foi encontrada na API. A análise de datas pode estar incompleta.")


# ----------------------------------------------------------
# 2. NORMALIZAÇÃO DE DADOS ANINHADOS (rateio -> ganhadores)
# ----------------------------------------------------------
if 'rateio' in df.columns:
    df['ganhadores'] = df['rateio'].apply(lambda x: get_ganhadores(x, 6)) # Sena (6 acertos)
    df['ganhadores_quina'] = df['rateio'].apply(lambda x: get_ganhadores(x, 5)) # Quina (5 acertos)
    df['ganhadores_quadra'] = df['rateio'].apply(lambda x: get_ganhadores(x, 4)) # Quadra (4 acertos)
else:
    df['ganhadores'] = 0 
    df['ganhadores_quina'] = 0
    df['ganhadores_quadra'] = 0


# Conversão de tipos de colunas relevantes
colunas_numericas = ["concurso", "ganhadores", "ganhadores_quina", "ganhadores_quadra", "valor_acumulado"]
for col in colunas_numericas:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

# ----------------------------------------------------------
# 3. PROCESSAMENTO ESPECÍFICO (Dezenas e Frequência)
# ----------------------------------------------------------

for i in range(1, 7):
    df[f"dezena_{i}"] = df["dezenas"].apply(lambda x: int(x[i-1]) if isinstance(x, list) and len(x) >= i else 0)

todas_dezenas = []
for linha in df["dezenas"]:
    try:
        todas_dezenas.extend([int(x) for x in linha])
    except:
        continue

contador = Counter(todas_dezenas)
frequencias = pd.DataFrame(sorted(contador.items()), columns=["dezena", "frequencia"])

# 4. Processamento de Cidades Premiadas (rateio -> ganhadores_cidade)
def extrair_cidades_premiadas(df):
    """Extrai e conta a frequência de todos os municípios ganhadores de 6 acertos."""
    todas_cidades = []
    
    if 'rateio' in df.columns:
        # Filtra apenas os concursos que tiveram ganhadores de 6 dezenas (Sena)
        df_ganhadores = df[df['ganhadores'] > 0]
        
        for index, row in df_ganhadores.iterrows():
            rateio = row['rateio']
            # Encontra as informações da Sena (6 acertos)
            sena_info = next((item for item in rateio if item.get('acertos') == 6), None)
            
            if sena_info:
                # O campo com as cidades é 'ganhadores_cidade'
                ganhadores_cidade_lista = sena_info.get('ganhadores_cidade', [])
                
                for ganhador in ganhadores_cidade_lista:
                    cidade = ganhador.get('cidade')
                    uf = ganhador.get('uf')
                    
                    # Cria a string Município - UF
                    if cidade and uf:
                        cidade_uf = f"{cidade.strip()} - {uf.strip()}"
                        todas_cidades.append(cidade_uf)
    
    # Conta a frequência de cada cidade
    cidades_frequencia = Counter(todas_cidades)
    df_cidades = pd.DataFrame(cidades_frequencia.items(), columns=['municipio_uf', 'total_premios'])
    
    # Remove entradas vazias ou incompletas, se houver
    df_cidades = df_cidades[~df_cidades['municipio_uf'].str.contains(' - UF')]
    
    return df_cidades.sort_values(by='total_premios', ascending=False)

df_cidades_premiadas = extrair_cidades_premiadas(df)

# ----------------------------------------------------------
# INTERFACE STREAMLIT
# ----------------------------------------------------------
# TEMA VISUAL
st.markdown(
    """
    <style>
    body {
        background-color: #0f1116;
        color: #e3e3e3;
    }
    .stMetric {
        background-color: #1b1e24;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #00ff73;
        box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
    }
    .st-emotion-cache-1avcm0g {
        border-bottom: 2px solid #00ff73;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📊 Dashboard Interativo – Mega Sena")
st.markdown("Análise completa dos resultados da Mega Sena com insights dinâmicos e sugestões de jogos.")

# ----------------------------------------------------------
# KPIs
# ----------------------------------------------------------
st.markdown("---")
col1, col2, col3 = st.columns(3)

total_concursos = df.shape[0]
maior_premio = df["valor_acumulado"].max() if "valor_acumulado" in df.columns else None
concursos_com_sena = df[df["ganhadores"] > 0].shape[0]

col1.metric("Total de Concursos", total_concursos)
if maior_premio is not None:
    col2.metric("Maior Prêmio Acumulado (R$)", f"R$ {maior_premio:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
col3.metric("Concursos com Ganhador (Sena)", concursos_com_sena)

st.markdown("---")

# ----------------------------------------------------------
# SIDEBAR / INTERAÇÃO (Adicionando a nova aba)
# ----------------------------------------------------------
st.sidebar.header("Opções de Análise")
tipo_analise = st.sidebar.radio(
    "Selecione o tipo de análise:",
    ["Métricas dos Concursos", "Números mais sorteados", "Frequência por número", "**Municípios Ganhadores**", "Sugestão de jogos"]
)

# ----------------------------------------------------------
# NOVA ABA: MUNICÍPIOS GANHADORES (Análise 3 migrada)
# ----------------------------------------------------------
if tipo_analise == "**Municípios Ganhadores**":
    st.subheader("🏙️ Municípios com Mais Premiações da Sena (6 acertos)")
    
    if not df_cidades_premiadas.empty:
        
        st.markdown(f"**Total de Municípios com Ganhadores de Sena:** **{df_cidades_premiadas.shape[0]}**")
        
        # Filtro para Top N (mantido para visualização)
        top_cidades = st.slider("Selecione o Top N de Municípios para o Gráfico", 1, df_cidades_premiadas.shape[0], 10)
        
        # --- Gráfico ---
        dados_plot = df_cidades_premiadas.head(top_cidades)
        
        fig, ax = plt.subplots(figsize=(10, max(5, top_cidades * 0.5))) 
        
        cores = ['#00ff73', '#ff00aa', '#00aaff', '#ffcc00']
        ax.barh(dados_plot["municipio_uf"], dados_plot["total_premios"], color=cores * (len(dados_plot)//len(cores) + 1))
        
        for i, (cidade, total) in enumerate(zip(dados_plot["municipio_uf"], dados_plot["total_premios"])):
            ax.annotate(str(total), (total, i), va='center', ha='left', xytext=(5, 0), textcoords='offset points', fontsize=9)
            
        ax.set_xlabel("Total de Prêmios (Sena)")
        ax.set_ylabel("Município - UF")
        ax.invert_yaxis() 
        ax.set_title(f"Top {top_cidades} Municípios com Mais Ganhadores da Sena")
        st.pyplot(fig)
        
        st.markdown("---")
        
        # --- Tabela Completa ---
        st.markdown("### 📜 Tabela Completa de Municípios Ganhadores")
        st.dataframe(df_cidades_premiadas, use_container_width=True, hide_index=True)

    else:
        st.info("Nenhum dado de cidades premiadas encontrado na API.")


# ----------------------------------------------------------
# MÉTRICAS DOS CONCURSOS (Mantido o nome da variável tipo_analise)
# ----------------------------------------------------------
if tipo_analise == "Métricas dos Concursos":
    st.subheader("📋 Métricas Gerais e Histórico dos Concursos")
    
    if 'data_concurso' in df.columns and not df['data_concurso'].isna().all(): 
        
        primeiro_concurso_dt = df["data_concurso"].min()
        ultimo_concurso_dt = df["data_concurso"].max()
        
        primeiro_concurso_str = primeiro_concurso_dt.strftime('%d/%m/%Y')
        ultimo_concurso_str = ultimo_concurso_dt.strftime('%d/%m/%Y')
        
        st.markdown(f"**Primeiro Concurso Analisado:** **{primeiro_concurso_str}**")
        st.markdown(f"**Último Concurso Analisado:** **{ultimo_concurso_str}**")
        
        st.markdown("---")
        
        colA, colB, colC = st.columns(3)
        
        concursos_6_acertos = df[df["ganhadores"] > 0].shape[0]
        concursos_5_acertos = df[df["ganhadores_quina"] > 0].shape[0]
        concursos_4_acertos = df[df["ganhadores_quadra"] > 0].shape[0]
        
        concursos_sem_ganhadores = df[(df["ganhadores"] == 0) & 
                                      (df["ganhadores_quina"] == 0) & 
                                      (df["ganhadores_quadra"] == 0)].shape[0]
        
        colA.metric("Concursos com 6 Acertos", concursos_6_acertos, delta=f"{concursos_6_acertos/total_concursos*100:.2f}% do total")
        colB.metric("Concursos com 5 Acertos", concursos_5_acertos, delta=f"{concursos_5_acertos/total_concursos*100:.2f}% do total")
        colC.metric("Concursos com 4 Acertos", concursos_4_acertos, delta=f"{concursos_4_acertos/total_concursos*100:.2f}% do total")
        
        st.markdown(f"**Total de Concursos SEM Ganhadores (6, 5 ou 4 acertos):** **{concursos_sem_ganhadores}**")
    else:
        st.warning("Dados de concurso não carregados ou nenhuma data válida encontrada para o histórico.")


# ----------------------------------------------------------
# ANÁLISE 1 – NÚMEROS MAIS SORTEADOS
# ----------------------------------------------------------
if tipo_analise == "Números mais sorteados":
    st.subheader("🔢 Top Números Mais Sorteados")

    top_n = st.slider("Quantidade de números no ranking", 5, 60, 10)

    fig, ax = plt.subplots(figsize=(10, 5))
    dados_plot = frequencias.sort_values("frequencia", ascending=False).head(top_n)
    ax.bar(dados_plot["dezena"].astype(str), dados_plot["frequencia"], color='#00ff73')
    
    for p in ax.patches:
        ax.annotate(str(int(p.get_height())), (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='bottom', fontsize=8, xytext=(0, 5), textcoords='offset points')
                    
    ax.set_xlabel("Número")
    ax.set_ylabel("Frequência")
    ax.set_title(f"Top {top_n} Dezenas por Frequência de Sorteio")
    st.pyplot(fig)

# ----------------------------------------------------------
# ANÁLISE 2 – FREQUÊNCIA DE TODAS AS DEZENAS
# ----------------------------------------------------------
if tipo_analise == "Frequência por número":
    st.subheader("📈 Frequência completa de todas as dezenas (1 a 60)")

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(frequencias["dezena"], frequencias["frequencia"], marker="o", color='#00aaff', linestyle='-')
    ax.set_xticks(range(1, 61))
    ax.set_xticklabels(range(1, 61), rotation=90, fontsize=8)
    
    top_5 = frequencias.sort_values("frequencia", ascending=False).head(5)
    bottom_5 = frequencias.sort_values("frequencia", ascending=True).head(5)
    
    for idx, row in pd.concat([top_5, bottom_5]).drop_duplicates().iterrows():
         ax.annotate(f"{row['frequencia']}", (row['dezena'], row['frequencia']), textcoords='offset points', 
                     xytext=(0, 5), ha='center', fontsize=7, color='red' if row['dezena'] in bottom_5['dezena'].tolist() else 'green',
                     fontweight='bold')
                     
    ax.set_xlabel("Número")
    ax.set_ylabel("Frequência")
    ax.set_title("Histórico de Frequência de Sorteio por Dezena")
    st.pyplot(fig)


# ----------------------------------------------------------
# ANÁLISE 4 – SUGESTÃO DE JOGOS
# ----------------------------------------------------------
if tipo_analise == "Sugestão de jogos":
    st.subheader("🎯 Sugestão automática de jogos")

    metodo = st.radio("Escolha o método de geração:", [
        "Números mais sorteados (High Frequency)",
        "Mistura de frequências (Mixed)",
        "Números aleatórios"
    ])

    qtde_jogos = st.slider("Quantidade de jogos", 1, 10, 3)

    jogos = []

    if metodo == "Números mais sorteados (High Frequency)":
        base = frequencias.sort_values("frequencia", ascending=False).head(30)["dezena"].tolist()
        for _ in range(qtde_jogos):
            jogos.append(sorted(random.sample(base, 6)))

    elif metodo == "Mistura de frequências (Mixed)":
        for _ in range(qtde_jogos):
            mais = random.sample(frequencias.sort_values("frequencia", ascending=False).head(20)["dezena"].tolist(), 3)
            menos = random.sample(frequencias.sort_values("frequencia", ascending=True).head(40)["dezena"].tolist(), 3)
            jogos.append(sorted(list(set(mais + menos))))

    else:  # Números Aleatórios
        for _ in range(qtde_jogos):
            jogos.append(sorted(random.sample(range(1, 61), 6)))

    st.write("### 🎰 Jogos sugeridos:")
    for jogo in jogos:
        st.markdown(f"#### **{jogo}**")