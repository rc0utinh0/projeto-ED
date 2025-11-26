import streamlit as st
import pandas as pd
import requests
import json
import os
import matplotlib.pyplot as plt
from collections import Counter
import random

st.set_page_config(page_title="Dashboard Mega Sena", layout="wide")

# ----------------------------------------------------------
# FUNÇÃO PARA BAIXAR DADOS DA API E SALVAR LOCALMENTE
# ----------------------------------------------------------
def baixar_dados():
    url = "https://loteriascaixa-api.herokuapp.com/api/megasena"  # API pública
    response = requests.get(url)

    if response.status_code == 200:
        dados = response.json()
        with open("mega_sena.json", "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
        return dados
    else:
        st.error("Erro ao acessar API")
        return None

# ----------------------------------------------------------
# CARREGAR DADOS DO ARQUIVO
# ----------------------------------------------------------
def carregar_dados():
    if os.path.exists("mega_sena.json"):
        with open("mega_sena.json", "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return baixar_dados()

# ----------------------------------------------------------
# PROCESSAR DADOS
# ----------------------------------------------------------
dados = carregar_dados()

df = pd.DataFrame(dados)

# Expandir lista de dezenas
for i in range(1, 7):
    df[f"dezena_{i}"] = df["dezenas"].apply(lambda x: int(x[i-1]))

# Todas as dezenas em uma única lista
todas_dezenas = []
for linha in df["dezenas"]:
    todas_dezenas.extend([int(x) for x in linha])

contador = Counter(todas_dezenas)
frequencias = pd.DataFrame(sorted(contador.items()), columns=["dezena", "frequencia"])  

# ----------------------------------------------------------
# FUNÇÕES EXTRAS
# ----------------------------------------------------------

def analise_par_impar():
    pares = [n for n in todas_dezenas if n % 2 == 0]
    impares = [n for n in todas_dezenas if n % 2 != 0]
    return len(pares), len(impares)


def repeticao_dezenas():
    repeticoes = frequencias.sort_values("frequencia", ascending=False).head(10)
    return repeticoes

# ----------------------------------------------------------
# INTERFACE STREAMLIT
# ----------------------------------------------------------
# ----------------------------------------------------------
# KPIs
# ----------------------------------------------------------

col1, col2, col3 = st.columns(3)

total_concursos = df.shape[0]
maior_premio = df["valor_acumulado"].max() if "valor_acumulado" in df.columns else None
media_ganhadores = df["ganhadores"].mean() if "ganhadores" in df.columns else None

col1.metric("Total de Concursos", total_concursos)
if maior_premio:
    col2.metric("Maior Prêmio Acumulado (R$)", f"{maior_premio:,.2f}")
if media_ganhadores:
    col3.metric("Média de Ganhadores", f"{media_ganhadores:.2f}")

# Tema visual
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
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📊 Dashboard Interativo – Mega Sena")
st.markdown("Análise completa dos resultados da Mega Sena com insights dinâmicos e sugestões de jogos.")

st.sidebar.header("Opções de Interação")
tipo_analise = st.sidebar.radio(
    "Selecione a análise:",
    ["Números mais sorteados", "Frequência por número", "Cidades premiadas", "Sugestão de jogos"]
)

# ----------------------------------------------------------
# ANÁLISE 1 – NÚMEROS MAIS SORTEADOS
# ----------------------------------------------------------
if tipo_analise == "Números mais sorteados":
    st.subheader("🔢 Top números mais sorteados")

    top_n = st.slider("Quantidade de números no ranking", 5, 60, 10)

    fig, ax = plt.subplots()
    dados_plot = frequencias.sort_values("frequencia", ascending=False).head(top_n)
    ax.bar(dados_plot["dezena"], dados_plot["frequencia"])
    ax.set_xticks(range(1, 61))
    ax.set_xticklabels(range(1, 61), rotation=90, fontsize=8)
    # labels on top of bars
    for p in ax.patches:
        ax.annotate(str(int(p.get_x()+p.get_width()/2)), (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='bottom', fontsize=7, xytext=(0, 3), textcoords='offset points')
    ax.set_xlabel("Número")
    ax.set_ylabel("Frequência")
    st.pyplot(fig)

# ----------------------------------------------------------
# ANÁLISE 2 – FREQUÊNCIA DE TODAS AS DEZENAS
# ----------------------------------------------------------
if tipo_analise == "Frequência por número":
    st.subheader("📈 Frequência completa de todas as dezenas")

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(frequencias["dezena"], frequencias["frequencia"], marker="o")
    ax.set_xticks(range(1, 61))
    ax.set_xticklabels(range(1, 61), rotation=90, fontsize=8)
    # labels at each point
    for x, y in zip(frequencias["dezena"], frequencias["frequencia"]):
        ax.annotate(str(x), (x, y), textcoords='offset points', xytext=(0,5), ha='center', fontsize=7)
    ax.set_xlabel("Número")
    ax.set_ylabel("Frequência")
    st.pyplot(fig)

# ----------------------------------------------------------
# ANÁLISE 3 – CIDADES PREMIADAS
# ----------------------------------------------------------
if tipo_analise == "Cidades premiadas":
    st.subheader("🏙️ Cidades com mais premiações")

    # Procurar automaticamente colunas prováveis para o local dos ganhadores
    possíveis = [c for c in df.columns if any(k in c.lower() for k in ["local", "cidade", "municipio", "city"]) ]
    coluna_local = None

    # Prefer explicit matches
    for alvo in ["localganhadores", "local_ganhadores", "local_ganhador", "local", "cidade", "municipio", "city"]:
        for c in possíveis:
            if alvo in c.lower():
                coluna_local = c
                break
        if coluna_local:
            break

    # Se não encontrou, tentar inspecionar colunas que contenham strings semelhantes a cidades
    if coluna_local is None and possíveis:
        for c in possíveis:
            sample = df[c].dropna().astype(str).head(50).tolist()
            # detectar padrão como 'Cidade - UF' ou presença de vírgula seguida de sigla
            if any((" - " in s and len(s.split(" - ")[-1]) <= 3) or ("," in s and len(s.split(",")[-1].strip()) <= 3) for s in sample):
                coluna_local = c
                break

    # Tentar extrair de colunas que contenham estruturas (listas/dicts)
    if coluna_local is None:
        for c in df.columns:
            sample = df[c].dropna().head

# ----------------------------------------------------------
# ANÁLISE 4 – SUGESTÃO DE JOGOS
# ----------------------------------------------------------
if tipo_analise == "Sugestão de jogos":
    st.subheader("🎯 Sugestão automática de jogos")

    metodo = st.radio("Escolha o método de geração:", [
        "Números mais sorteados",
        "Mistura de frequências",
        "Números históricos da mesma data"
    ])

    qtde_jogos = st.slider("Quantidade de jogos", 1, 10, 3)

    jogos = []

    if metodo == "Números mais sorteados":
        base = frequencias.sort_values("frequencia", ascending=False).head(30)["dezena"].tolist()
        for _ in range(qtde_jogos):
            jogos.append(sorted(random.sample(base, 6)))

    elif metodo == "Mistura de frequências":
        for _ in range(qtde_jogos):
            mais = random.sample(frequencias.sort_values("frequencia", ascending=False).head(20)["dezena"].tolist(), 3)
            menos = random.sample(frequencias.sort_values("frequencia", ascending=True).head(40)["dezena"].tolist(), 3)
            jogos.append(sorted(mais + menos))

    else:  # mesma data histórica
        datas = df["data_concurso"].unique()
        escolha = st.selectbox("Selecione a data histórica:", datas)
        dezenas_data = df[df["data_concurso"] == escolha]["dezenas"].iloc[0]
        base = [int(x) for x in dezenas_data]
        for _ in range(qtde_jogos):
            jogos.append(sorted(random.sample(base + random.sample(range(1,61), 10), 6)))

    st.write("### Jogos sugeridos:")
    for jogo in jogos:
        st.write(jogo)
