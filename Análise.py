import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Define a pasta onde estão nossos arquivos CSV.
pasta_dados = 'analise'

# Lista para guardar cada tabela de status antes de juntar
lista_de_dataframes = []
print("Iniciando a leitura e combinação dos arquivos de STATUS...")

# Loop que passa por cada arquivo na pasta
for arquivo in os.listdir(pasta_dados):
    if arquivo.startswith('Status_Kelmarsh'):
        caminho_completo = os.path.join(pasta_dados, arquivo)
        try:
            # Lê o CSV, pulando as 9 linhas de metadados
            df_temp = pd.read_csv(caminho_completo, sep=',', skiprows=9)
            # Limpa o '#' do nome da primeira coluna
            df_temp.rename(columns={df_temp.columns[0]: df_temp.columns[0].lstrip('# ')}, inplace=True)
            # Adiciona a coluna com o nome da turbina, extraído do nome do arquivo
            nome_turbina = f"T{arquivo.split('_')[2]}"
            df_temp['Turbine'] = nome_turbina
            lista_de_dataframes.append(df_temp)
        except Exception as e:
            print(f"    - ATENÇÃO: Erro ao ler o arquivo {arquivo}: {e}")

# Junta todas as tabelas da lista em uma só
df_status_completo = pd.concat(lista_de_dataframes, ignore_index=True)
print("\n--- TODOS OS ARQUIVOS DE STATUS FORAM COMBINADOS! ---")

print("\n--- LIMPANDO E PREPARANDO OS DADOS DE STATUS ---")
# Converte a coluna de data e remove linhas com datas inválidas
df_status_completo['Timestamp start'] = pd.to_datetime(df_status_completo['Timestamp start'], errors='coerce')
df_status_completo.dropna(subset=['Timestamp start'], inplace=True)

# Filtra para o período do desafio
df_filtrado = df_status_completo[
    (df_status_completo['Timestamp start'].dt.year >= 2019) &
    (df_status_completo['Timestamp start'].dt.year <= 2021)
].copy()

# Calcula a duração manualmente (Plano B)
print("Calculando a duração de cada evento...")
df_filtrado = df_filtrado.sort_values(by=['Turbine', 'Timestamp start'])
df_filtrado['Duration_Calculada'] = (
    df_filtrado.groupby('Turbine')['Timestamp start'].shift(-1) - df_filtrado['Timestamp start']
).dt.total_seconds()
df_filtrado['Duration_Calculada'].fillna(0, inplace=True)

# Listas para a automação
lista_turbinas = sorted(df_filtrado['Turbine'].unique())
lista_anos = [2019, 2020, 2021]
resultados_disponibilidade = []
print("\n--- CALCULANDO A DISPONIBILIDADE ANUAL (ITEM 1.1) ---")

for turbina in lista_turbinas:
    for ano in lista_anos:
        df_alvo = df_filtrado[(df_filtrado['Turbine'] == turbina) & (df_filtrado['Timestamp start'].dt.year == ano)]
        if df_alvo.empty: continue

        categorias_disponiveis = ['Full Performance', 'Technical Standby', 'Out of Environmental Specification']
        tempo_disponivel_segundos = df_alvo[df_alvo['IEC category'].isin(categorias_disponiveis)][
            'Duration_Calculada'].sum()

        segundos_no_ano = 366 * 24 * 60 * 60 if ano % 4 == 0 else 365 * 24 * 60 * 60
        disponibilidade_percentual = (tempo_disponivel_segundos / segundos_no_ano) * 100 if segundos_no_ano > 0 else 0

        resultados_disponibilidade.append(
            {'Turbina': turbina, 'Ano': ano, 'Disponibilidade (%)': round(disponibilidade_percentual, 2)})

df_resultados = pd.DataFrame(resultados_disponibilidade)
print(df_resultados)

print("\n--- IDENTIFICANDO CAUSAS DE INDISPONIBILIDADE (ITEM 1.2) ---")
categorias_indisponiveis = ['Forced outage', 'Scheduled Maintenance', 'Out of Electrical Specification', 'Requested Shutdown']
df_indisponivel = df_filtrado[df_filtrado['IEC category'].isin(categorias_indisponiveis)].copy()

tempo_parada_por_causa = df_indisponivel.groupby(['Turbine', 'IEC category'])['Duration_Calculada'].sum()
tempo_parada_em_horas = (tempo_parada_por_causa / 3600).round(2)

top3_resultados = tempo_parada_em_horas.groupby('Turbine', group_keys=False).nlargest(3)
print(top3_resultados)

print("\n--- LENDO OS ARQUIVOS DE DADOS DA TURBINA (SCADA) ---")
lista_de_dataframes_scada = []
for arquivo in os.listdir(pasta_dados):
    if arquivo.startswith('Turbine_Data_Kelmarsh'):
        caminho_completo = os.path.join(pasta_dados, arquivo)
        try:
            df_temp = pd.read_csv(caminho_completo, sep=',', skiprows=9)
            df_temp.rename(columns={df_temp.columns[0]: df_temp.columns[0].lstrip('# ')}, inplace=True)
            nome_turbina = f"T{arquivo.split('_')[3]}"
            df_temp['Turbine'] = nome_turbina
            lista_de_dataframes_scada.append(df_temp)
        except Exception as e:
            print(f"    - ATENÇÃO: Erro ao ler o arquivo {arquivo}: {e}")

df_scada = pd.concat(lista_de_dataframes_scada, ignore_index=True)
print("--- ARQUIVOS DE SCADA COMBINADOS! ---")

print("\n--- FILTRANDO DADOS PARA ANÁLISE DE ESTEIRA ---")
df_scada['Date and time'] = pd.to_datetime(df_scada['Date and time'], errors='coerce')
df_scada.dropna(subset=['Date and time'], inplace=True)

# Parâmetros de filtro
direcao_central = 68.38
limite_inferior = direcao_central - 30
limite_superior = direcao_central + 30

# Filtro por direção do vento
timestamps_validos = df_scada[(df_scada['Turbine'] == 'T2') & (df_scada['Wind direction (°)'].between(limite_inferior, limite_superior))]['Date and time']
df_filtrado_dir = df_scada[df_scada['Date and time'].isin(timestamps_validos)].copy()

# Filtro por ângulo de passo
timestamps_pitch_alto = df_filtrado_dir[
    (df_filtrado_dir['Blade angle (pitch position) A (°)'] > 5) |
    (df_filtrado_dir['Blade angle (pitch position) B (°)'] > 5) |
    (df_filtrado_dir['Blade angle (pitch position) C (°)'] > 5)
]['Date and time'].unique()
df_final_esteira = df_filtrado_dir[~df_filtrado_dir['Date and time'].isin(timestamps_pitch_alto)]
print("--- FILTRAGEM CONCLUÍDA ---")

print("\n--- GERANDO A CURVA DE POTÊNCIA ---")
# Garante que as colunas são numéricas
for col in ['Wind speed (m/s)', 'Power (kW)']:
    df_final_esteira[col] = pd.to_numeric(df_final_esteira[col], errors='coerce')
df_final_esteira.dropna(subset=['Wind speed (m/s)', 'Power (kW)'], inplace=True)

# Separa os dados por turbina
t2_data = df_final_esteira[df_final_esteira['Turbine'] == 'T2']
t3_data = df_final_esteira[df_final_esteira['Turbine'] == 'T3']

# Binarização
wind_speed_bins = np.arange(0, 25.5, 0.5)
wind_speed_labels = (wind_speed_bins[:-1] + wind_speed_bins[1:]) / 2
t2_data.loc[:, 'ws_bin'] = pd.cut(t2_data['Wind speed (m/s)'], bins=wind_speed_bins, labels=wind_speed_labels)
t3_data.loc[:, 'ws_bin'] = pd.cut(t3_data['Wind speed (m/s)'], bins=wind_speed_bins, labels=wind_speed_labels)

# Cálculo da curva média
power_curve_t2 = t2_data.groupby('ws_bin', observed=True)['Power (kW)'].mean()
power_curve_t3 = t3_data.groupby('ws_bin', observed=True)['Power (kW)'].mean()

# Plotagem do gráfico
plt.figure(figsize=(12, 7))
plt.plot(power_curve_t2.index.astype(float), power_curve_t2.values, marker='o', linestyle='-', label='T2 (À frente / Upstream)')
plt.plot(power_curve_t3.index.astype(float), power_curve_t3.values, marker='x', linestyle='--', label='T3 (Atrás / Downstream - Afetada pela esteira)')
plt.title('Curva de Potência Comparativa (T2 vs T3) em Condições de Esteira', fontsize=16)
plt.xlabel('Velocidade do Vento (m/s)', fontsize=12)
plt.ylabel('Potência Média Gerada (kW)', fontsize=12)
plt.legend(fontsize=12)
plt.grid(True, which='both', linestyle='--', linewidth=0.5)
plt.show()