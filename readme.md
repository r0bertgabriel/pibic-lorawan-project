

# Documentação do Simulador LoRaWAN para Ambiente Amazônico

Este documento detalha todos os parâmetros, variáveis e componentes utilizados no arquivo alteracoes.py, que implementa um simulador de rede LoRaWAN em ambiente amazônico.

## Configurações Globais

| Variável | Tipo | Valor | Descrição |
|----------|------|-------|-----------|
| `SIM_TIME` | inteiro | 3600 | Tempo total de simulação em segundos |
| `DISTANCES` | lista | [100, 200, 300, 400] | Distâncias dos dispositivos ao gateway em metros |
| `DEVICE_NAMES` | lista | ["ESP32-1", "ESP32-2", "ESP32-3", "ESP32-4"] | Identificadores dos dispositivos LoRa |
| `INITIAL_TEMPS` | lista | [27.5, 28.2, 27.8, 28.5] | Temperaturas iniciais para sensores (°C) |

## Configurações LoRaWAN Padrão

| Variável | Tipo | Valor | Descrição |
|----------|------|-------|-----------|
| `DEFAULT_SF` | inteiro | 7 | Spreading Factor padrão (7-12) - afeta alcance e taxa de dados |
| `DEFAULT_BW` | inteiro | 125 | Bandwidth padrão em kHz (valores típicos: 125, 250, 500) |
| `DEFAULT_CR` | inteiro | 5 | Coding Rate padrão (5 para 4/5, 6 para 4/6, etc.) |
| `DEFAULT_TP` | inteiro | 14 | Potência de transmissão padrão em dBm (2-14) |

## Classes e Enumerações

### `SeasonType` (Enum)
Representa as estações climáticas da Amazônia.

| Valor | Descrição | Período |
|-------|-----------|---------|
| `RAINY` | Estação chuvosa | Dezembro a Maio |
| `DRY` | Estação seca | Junho a Novembro |

### `AmazonClimate`
Simula condições climáticas da Amazônia com variações temporais realistas.

#### Parâmetros do Construtor
| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `env` | `simpy.Environment` | - | Ambiente de simulação |
| `season` | `SeasonType` | `RAINY` | Estação do ano atual |
| `vegetation_density` | float | 0.8 | Densidade da vegetação (0-1) |

#### Atributos de Vegetação
| Atributo | Tipo | Valor | Descrição |
|----------|------|-------|-----------|
| `tree_density` | float | 0.15 | Árvores por m² (típico de floresta densa) |
| `avg_tree_height` | float | 25.0 | Altura média das árvores em metros |
| `forest_depth_factor` | float | 0.8 | Fator de profundidade da floresta (0-1) |

#### Parâmetros Climáticos
| Atributo | Tipo | Valor (Chuvosa/Seca) | Descrição |
|----------|------|-------------------|-----------|
| `base_temp` | float | 28.0/32.0 | Temperatura base em °C |
| `temp_variation` | float | 3.5/6.5 | Amplitude da variação de temperatura em °C |
| `base_humidity` | float | 90.0/70.0 | Umidade relativa base em % |
| `humidity_variation` | float | 8.0/15.0 | Amplitude da variação de umidade em % |
| `rain_probability` | float | 0.65/0.15 | Probabilidade de ocorrência de chuva |
| `max_rain_intensity` | float | 35.0/15.0 | Intensidade máxima de chuva em mm/h |

#### Métodos Principais
| Método | Parâmetros | Retorno | Descrição |
|--------|------------|---------|-----------|
| `update_weather()` | - | - | Atualiza condições climáticas a cada 10 minutos simulados |
| `get_attenuation_factor()` | `distance=100`, `frequency=915` | float | Calcula atenuação do sinal em dB baseada nas condições atuais |
| `get_current_conditions()` | - | dict | Retorna condições climáticas atuais (temperatura, umidade, chuva) |

### Funções de Propagação de Sinal

#### `calculate_ldplm_path_loss()`
Calcula a perda de percurso usando o modelo Log-Distance.

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `distance_m` | float | - | Distância em metros |
| `freq_mhz` | float | - | Frequência em MHz |
| `ple` | float | - | Path Loss Exponent (2.5-3.8 para florestas) |
| `d0_m` | float | 1.0 | Distância de referência em metros |

#### `calculate_vegetation_attenuation()`
Calcula a atenuação adicional devido à vegetação densa da Amazônia.

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `distance_m` | float | Distância em metros |
| `freq_mhz` | float | Frequência em MHz |
| `tree_density` | float | Densidade de árvores por m² |
| `avg_tree_height` | float | Altura média das árvores em metros |
| `depth_factor` | float | Fator de profundidade da floresta (0-1) |

### `TemperatureSensor`
Simula um sensor de temperatura DS18B20 com características realistas.

#### Parâmetros do Construtor
| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `initial_temp` | float | 28.0 | Temperatura inicial em °C |
| `noise` | float | 0.5 | Ruído nas medições em °C |
| `drift` | float | 0.02 | Desvio gradual da temperatura ao longo do tempo em °C |
| `climate` | `AmazonClimate` | None | Referência ao sistema climático |

#### Atributos Internos
| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `is_malfunctioning` | bool | Indica se o sensor está em falha |
| `malfunction_duration` | int | Duração da falha em segundos |
| `last_failure_check` | float | Timestamp da última verificação de falha |

#### Métodos
| Método | Parâmetros | Retorno | Descrição |
|--------|------------|---------|-----------|
| `read()` | - | float | Simula leitura do sensor com ruído e possíveis falhas |

### `LoRaConfig` (dataclass)
Configuração de parâmetros LoRaWAN.

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `sf` | int | Spreading Factor (7-12) |
| `bw` | int | Bandwidth em kHz (125, 250, 500) |
| `cr` | int | Coding Rate (5 para 4/5, 6 para 4/6, etc.) |
| `tp` | int | Potência de transmissão em dBm (2-14) |

#### Propriedade
| Propriedade | Tipo | Descrição |
|-------------|------|-----------|
| `airtime` | float | Calcula o tempo no ar em segundos para um pacote de 10 bytes |

### `LoRaDevice`
Dispositivo LoRaWAN (ESP32 com sensor de temperatura).

#### Parâmetros do Construtor
| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `env` | `simpy.Environment` | Ambiente de simulação |
| `id` | int | ID do dispositivo |
| `name` | str | Nome do dispositivo |
| `gateway` | `LoRaGateway` | Gateway ao qual o dispositivo se conecta |
| `distance` | float | Distância ao gateway em metros |
| `initial_temp` | float | Temperatura inicial do sensor em °C |
| `climate` | `AmazonClimate` | Referência ao sistema climático |

#### Atributos Principais
| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `config` | `LoRaConfig` | Configuração LoRa do dispositivo |
| `tx_interval` | int | Intervalo entre transmissões em segundos (padrão: 300) |
| `battery_level` | float | Nível de bateria em percentual (0-100) |
| `battery_drain_rate` | float | Taxa de descarga base da bateria |
| `packets_sent` | int | Número de pacotes enviados |
| `packets_received` | int | Número de pacotes recebidos com sucesso |
| `energy_used` | float | Energia total consumida em mWh |
| `history` | dict | Dicionário de histórico de dados (temperaturas, RSSI, etc.) |

#### Métodos Principais
| Método | Parâmetros | Retorno | Descrição |
|--------|------------|---------|-----------|
| `calculate_rssi()` | - | float | Calcula o RSSI com base na distância e condições ambientais |
| `calculate_snr()` | - | float | Calcula o SNR com base em condições simuladas |
| `calculate_energy_consumption()` | `tx_time` | float | Calcula o consumo de energia em mWh |
| `run()` | - | - | Processo principal do dispositivo (transmissão de dados) |

#### Propriedades
| Propriedade | Tipo | Descrição |
|-------------|------|-----------|
| `packet_delivery_ratio` | float | Taxa de entrega de pacotes (0-1) |
| `packet_loss_ratio` | float | Taxa de perda de pacotes (0-1) |
| `average_latency` | float | Latência média em ms |
| `jitter` | float | Jitter (variação na latência) em ms |

### `LoRaGateway`
Gateway LoRaWAN central.

#### Parâmetros do Construtor
| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `env` | `simpy.Environment` | - | Ambiente de simulação |
| `climate` | `AmazonClimate` | None | Referência ao sistema climático |

#### Atributos
| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `devices` | list | Lista de dispositivos conectados |
| `received_data` | list | Lista de dados recebidos dos dispositivos |
| `uptime` | float | Percentual de tempo ativo (0-100) |

#### Métodos
| Método | Parâmetros | Retorno | Descrição |
|--------|------------|---------|-----------|
| `simulate_availability()` | - | - | Simula problemas de disponibilidade do gateway |
| `add_device()` | `device` | - | Adiciona um dispositivo à lista de monitorados |
| `receive_packet()` | `device`, `temperature`, `rssi`, `snr`, `latency`, `climate_data=None` | - | Recebe e processa um pacote de dados |
| `get_stats()` | - | dict | Retorna estatísticas da rede |

### `LoRaNetworkSimulation`
Simulação completa da rede LoRaWAN.

#### Parâmetros do Construtor
| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `season` | `SeasonType` | `RAINY` | Estação do ano para simulação |
| `vegetation_density` | float | 0.8 | Densidade da vegetação (0-1) |

#### Atributos
| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `env` | `simpy.Environment` | Ambiente de simulação |
| `climate` | `AmazonClimate` | Sistema climático simulado |
| `gateway` | `LoRaGateway` | Gateway central da rede |
| `devices` | list | Lista de dispositivos na rede |
| `running` | bool | Flag que indica se a simulação está em execução |
| `data_lock` | `threading.Lock` | Lock para acesso seguro a dados em multithread |

#### Métodos
| Método | Parâmetros | Retorno | Descrição |
|--------|------------|---------|-----------|
| `run_simulation()` | `duration=SIM_TIME` | - | Executa a simulação por um período determinado |
| `run_in_thread()` | `duration=SIM_TIME` | thread | Executa simulação em thread separada |
| `get_network_stats()` | - | dict | Retorna estatísticas atuais da rede |
| `get_all_temperature_data()` | - | dict | Retorna dados de temperatura de todos os dispositivos |
| `get_all_metric_data()` | - | dict | Retorna métricas (RSSI, SNR, etc.) de todos os dispositivos |
| `change_device_config()` | `device_id`, `sf=None`, `bw=None`, `cr=None`, `tp=None` | - | Altera a configuração de um dispositivo |
| `export_to_csv()` | - | - | Exporta resultados da simulação para arquivos CSV |

## Função Principal

### `main()`
Função principal para executar a simulação.

- Determina a estação com base na data atual
- Cria a simulação com clima amazônico
- Executa a simulação
- Exibe estatísticas finais
- Exporta os resultados para CSV

Esta função não recebe parâmetros e não retorna valores, apenas configura e executa todo o processo de simulação.