import simpy
import random
import math
import time
from dataclasses import dataclass
import threading
from datetime import datetime
import csv
from enum import Enum

# Configurações globais da simulação
SIM_TIME = 3600  # Tempo total de simulação em segundos
DISTANCES = [100, 200, 300, 400]  # Distâncias dos dispositivos ao gateway em metros
DEVICE_NAMES = ["ESP32-1", "ESP32-2", "ESP32-3", "ESP32-4"]
INITIAL_TEMPS = [27.5, 28.2, 27.8, 28.5]  # Temperaturas iniciais mais adequadas para Amazônia

# Configurações LoRaWAN padrão
DEFAULT_SF = 7  # Spreading Factor (7-12)
DEFAULT_BW = 125  # Bandwidth em kHz (125, 250, 500)
DEFAULT_CR = 5  # Coding Rate (5 para 4/5, 6 para 4/6, etc.)
DEFAULT_TP = 14  # Potência de transmissão em dBm (2-14)

class SeasonType(Enum):
    """Tipos de estação na Amazônia"""
    RAINY = "estação chuvosa"     # Dezembro a Maio
    DRY = "estação seca"          # Junho a Novembro

class AmazonClimate:
    """Simulação de clima amazônico"""
    def __init__(self, env, season=SeasonType.RAINY, vegetation_density=0.8):
        self.env = env
        self.season = season
        self.vegetation_density = vegetation_density  # 0-1 (0: área aberta, 1: floresta densa)
        
        # Parâmetros base determinados pela estação
        if season == SeasonType.RAINY:
            self.base_temp = 28.0
            self.temp_variation = 3.5
            self.base_humidity = 90.0
            self.humidity_variation = 8.0
            self.rain_probability = 0.65
            self.max_rain_intensity = 35.0  # mm/h
        else:  # Estação seca
            self.base_temp = 32.0
            self.temp_variation = 6.5
            self.base_humidity = 70.0
            self.humidity_variation = 15.0
            self.rain_probability = 0.15
            self.max_rain_intensity = 15.0  # mm/h
            
        # Estado atual do clima
        self.current_temperature = self.base_temp
        self.current_humidity = self.base_humidity
        self.is_raining = False
        self.rain_intensity = 0.0  # mm/h
        
        # Iniciar processo de atualização do clima
        self.process = env.process(self.update_weather())
        
    def update_weather(self):
        """Atualiza condições climáticas a cada 10 minutos"""
        while True:
            # Simula variação diurna de temperatura (ciclo de 24h)
            hour_of_day = (time.time() + self.env.now) % 86400 / 3600  # 0-24
            diurnal_factor = math.sin((hour_of_day - 6) * math.pi / 12)  # Pico às 14h
            
            # Temperatura varia com hora do dia + componente aleatório
            self.current_temperature = (
                self.base_temp + 
                diurnal_factor * self.temp_variation + 
                random.uniform(-0.5, 0.5)
            )
            
            # Umidade é inversa à temperatura + componente aleatório
            self.current_humidity = (
                self.base_humidity - 
                diurnal_factor * self.humidity_variation + 
                random.uniform(-3.0, 3.0)
            )
            self.current_humidity = max(40, min(100, self.current_humidity))
            
            # Determina chuva (mais provável com alta umidade)
            humidity_factor = (self.current_humidity - 60) / 40  # 0-1
            adjusted_rain_prob = self.rain_probability * humidity_factor
            
            if random.random() < adjusted_rain_prob:
                self.is_raining = True
                self.rain_intensity = random.uniform(2.0, self.max_rain_intensity)
                duration = random.randint(10, 180)  # Duração de 10 a 180 minutos
                
                # Print informações sobre chuva
                timestamp = datetime.fromtimestamp(time.time() + self.env.now).strftime('%H:%M:%S')
                print(f"[{timestamp}] 🌧️ Chuva iniciada: {self.rain_intensity:.1f} mm/h (prevista para {duration} minutos)")
                
                # Programa o fim da chuva
                def end_rain():
                    self.is_raining = False
                    self.rain_intensity = 0.0
                    timestamp = datetime.fromtimestamp(time.time() + self.env.now).strftime('%H:%M:%S')
                    print(f"[{timestamp}] ☀️ Chuva cessou")
                
                self.env.process(self.delayed_action(duration, end_rain))
            
            # Aguarda 10 minutos antes da próxima atualização
            yield self.env.timeout(600)
    
    def delayed_action(self, delay_minutes, action_func):
        """Executa uma ação após um atraso em minutos"""
        yield self.env.timeout(delay_minutes * 60)
        action_func()
    
    def get_attenuation_factor(self):
        """Retorna um fator de atenuação para comunicação baseado nas condições climáticas"""
        # Chuva atenua significativamente sinal RF em frequências mais altas
        rain_attenuation = self.rain_intensity * 0.2 if self.is_raining else 0
        
        # Alta umidade também afeta o sinal
        humidity_attenuation = (self.current_humidity - 50) * 0.05 if self.current_humidity > 50 else 0
        
        # Vegetação densa bloqueia sinais
        vegetation_attenuation = self.vegetation_density * 5
        
        return rain_attenuation + humidity_attenuation + vegetation_attenuation
    
    def get_current_conditions(self):
        """Retorna um dicionário com as condições climáticas atuais"""
        return {
            'temperature': round(self.current_temperature, 1),
            'humidity': round(self.current_humidity, 1),
            'is_raining': self.is_raining,
            'rain_intensity': round(self.rain_intensity, 1) if self.is_raining else 0,
            'attenuation': round(self.get_attenuation_factor(), 2)
        }

class TemperatureSensor:
    """Simulação de um sensor de temperatura DS18B20 com influências ambientais"""
    def __init__(self, initial_temp=28.0, noise=0.5, drift=0.02, climate=None):
        self.temperature = initial_temp
        self.noise = noise  # Ruído nas medições
        self.drift = drift  # Desvio gradual da temperatura ao longo do tempo
        self.climate = climate  # Referência ao sistema climático
        self.last_failure_check = 0
        self.is_malfunctioning = False
        self.malfunction_duration = 0
        
    def read(self):
        """Simula a leitura do sensor, com ruído, desvio e influências climáticas"""
        now = time.time()
        
        # Verifica se o sensor falhou devido à alta umidade (mais comum na Amazônia)
        if self.climate and not self.is_malfunctioning:
            if now - self.last_failure_check > 60:  # Verifica a cada minuto
                self.last_failure_check = now
                humidity = self.climate.current_humidity
                # Probabilidade de falha aumenta com umidade alta
                failure_prob = ((humidity - 85) / 30) ** 3 if humidity > 85 else 0
                if random.random() < failure_prob:
                    self.is_malfunctioning = True
                    self.malfunction_duration = random.randint(5, 30) * 60  # 5-30 minutos
                    print(f"⚠️ Sensor entrando em falha temporária por {self.malfunction_duration/60:.1f} minutos (umidade: {humidity:.1f}%)")
        
        # Recupera de falha após o tempo determinado
        if self.is_malfunctioning:
            if now - self.last_failure_check > self.malfunction_duration:
                self.is_malfunctioning = False
                print("✅ Sensor recuperado da falha temporária")
            else:
                # Durante falha, retorna leituras muito incorretas ou NaN
                return float('nan') if random.random() < 0.3 else random.uniform(10, 50)
                
        # Se temos clima, acompanha a temperatura ambiente com algum atraso
        if self.climate:
            # Adiciona inércia térmica (o sensor não muda instantaneamente)
            ambient_temp = self.climate.current_temperature
            self.temperature = self.temperature * 0.9 + ambient_temp * 0.1
        else:
            # Sem clima, apenas adiciona um pequeno desvio na temperatura
            self.temperature += random.uniform(-self.drift, self.drift)
        
        # Adiciona ruído à leitura (maior durante chuva devido a interferência)
        noise_factor = 2.0 if (self.climate and self.climate.is_raining) else 1.0
        reading = self.temperature + random.uniform(-self.noise, self.noise) * noise_factor
        
        # Arredonda para uma casa decimal, como um sensor real
        return round(reading, 1)

@dataclass
class LoRaConfig:
    """Configuração de parâmetros LoRaWAN"""
    sf: int  # Spreading Factor
    bw: int  # Bandwidth em kHz
    cr: int  # Coding Rate (5 significa 4/5)
    tp: int  # Potência de transmissão em dBm
    
    @property
    def airtime(self):
        """Calcula o tempo no ar de um pacote com payload de 10 bytes"""
        payload_size = 10  # Tamanho do payload em bytes
        n_preamble = 8  # Número de símbolos do preâmbulo
        
        # Converte BW para Hz
        bw_hz = self.bw * 1000
        
        # Componentes do tempo de transmissão LoRa
        t_preamble = (n_preamble + 4.25) * (2**self.sf / bw_hz)
        
        # Número de símbolos
        payload_symb_nb = 8 + max(math.ceil((8 * payload_size - 4 * self.sf + 28) / (4 * self.sf)) * (self.cr), 0)
        
        # Tempo de payload
        t_payload = payload_symb_nb * (2**self.sf / bw_hz)
        
        # Tempo total no ar em segundos
        airtime = t_preamble + t_payload
        
        return airtime

class LoRaDevice:
    """Dispositivo LoRaWAN (ESP32 com sensor de temperatura)"""
    def __init__(self, env, id, name, gateway, distance, initial_temp, climate):
        self.env = env
        self.id = id
        self.name = name
        self.gateway = gateway
        self.distance = distance  # Distância ao gateway em metros
        self.climate = climate
        self.sensor = TemperatureSensor(initial_temp, climate=climate)
        
        # Configuração LoRa
        self.config = LoRaConfig(sf=DEFAULT_SF, bw=DEFAULT_BW, cr=DEFAULT_CR, tp=DEFAULT_TP)
        
        # Configuração de transmissão
        self.tx_interval = 300  # Intervalo entre transmissões em segundos
        
        # Métricas
        self.packets_sent = 0
        self.packets_received = 0
        self.energy_used = 0  # em mWh
        self.last_rssi = 0
        self.last_snr = 0
        self.latencies = []
        
        # Histórico de dados
        self.history = {
            'timestamp': [],
            'temperature': [],
            'humidity': [],
            'rain': [],
            'rssi': [],
            'snr': [],
            'latency': [],
            'energy': []
        }
        
        # Controles de hardware
        self.battery_level = 100  # percentual de bateria
        self.battery_drain_rate = 0.01  # % por transmissão base
        self.has_power_issues = False
        
        # Inicia o processo de envio periódico
        self.process = env.process(self.run())
        
    def calculate_rssi(self):
        """Calcula o RSSI com base na distância e condições ambientais"""
        # Parâmetros do modelo de propagação
        freq = 868  # Frequência em MHz
        path_loss_exponent = 2.7  # Expoente de perda de caminho (2.0-4.0)
        reference_distance = 1.0  # Distância de referência em metros
        shadowing = random.gauss(0, 3)  # Sombreamento gaussiano em dB
        
        # RSSI a 1m (calculado com a equação de Friis)
        rssi_at_ref = -30  # dBm
        
        # Calcular RSSI na distância atual
        rssi = rssi_at_ref - 10 * path_loss_exponent * math.log10(self.distance / reference_distance) + shadowing
        
        # Adicionar efeito do SF (SFs mais altos têm melhor sensibilidade)
        rssi_sf_bonus = (self.config.sf - 7) * 2.5
        
        # Atenuação devido às condições climáticas
        if self.climate:
            weather_attenuation = self.climate.get_attenuation_factor()
            rssi -= weather_attenuation
        
        return round(rssi + rssi_sf_bonus, 1)
    
    def calculate_snr(self):
        """Calcula o SNR com base em condições simuladas e clima"""
        # Base SNR está relacionada com a distância
        base_snr = 10 - (self.distance / 100)
        
        # Adicionar variação aleatória
        variation = random.uniform(-2, 2)
        
        # SFs mais altos têm melhor desempenho com SNR baixo
        sf_bonus = (self.config.sf - 7) * 0.5
        
        # Fatores climáticos afetam o SNR
        climate_factor = 0
        if self.climate:
            # Chuva reduz SNR significativamente
            if self.climate.is_raining:
                climate_factor -= self.climate.rain_intensity * 0.1
            
            # Alta umidade também degrada o SNR
            if self.climate.current_humidity > 85:
                climate_factor -= (self.climate.current_humidity - 85) * 0.05
        
        return round(base_snr + variation + sf_bonus + climate_factor, 1)
    
    def calculate_energy_consumption(self, tx_time):
        """Calcula o consumo de energia durante uma transmissão"""
        # Consumo em diferentes estados (valores aproximados para ESP32 + módulo LoRa)
        power_tx = 120.0 + (self.config.tp * 5)  # mW durante transmissão (ajustado pela potência)
        power_sleep = 0.1  # mW em sleep mode
        
        # Em clima quente e úmido, o consumo de energia aumenta
        temperature_factor = 1.0
        if self.climate and self.climate.current_temperature > 30:
            temperature_factor += (self.climate.current_temperature - 30) * 0.03
        
        # Energia usada durante a transmissão
        tx_energy = (power_tx * tx_time * temperature_factor) / 3600  # mWh
        
        # Energia usada durante o sleep
        sleep_time = self.tx_interval - tx_time
        sleep_energy = (power_sleep * sleep_time * temperature_factor) / 3600  # mWh
        
        # Simula problemas de energia (mais comuns em alta umidade)
        if self.climate and self.climate.current_humidity > 90 and random.random() < 0.05:
            if not self.has_power_issues:
                self.has_power_issues = True
                print(f"⚡ {self.name}: Problemas detectados na alimentação (alta umidade)")
            tx_energy *= random.uniform(1.5, 2.5)  # Consumo inconsistente por problemas elétricos
        else:
            self.has_power_issues = False
        
        return tx_energy + sleep_energy
    
    def update_battery(self, energy_used):
        """Atualiza o nível de bateria e simula degradação"""
        # Converte energia usada em percentual da bateria
        drain_percentage = self.battery_drain_rate * (energy_used * 30)  # Fator de escala 
        
        # Temperatura alta acelera descarga da bateria 
        if self.climate and self.climate.current_temperature > 32:
            drain_percentage *= 1 + (self.climate.current_temperature - 32) * 0.1
        
        self.battery_level -= drain_percentage
        self.battery_level = max(0, self.battery_level)
        
        # Quando bateria baixa, mostrar aviso
        if self.battery_level < 20 and self.battery_level % 5 < 0.5:
            print(f"🔋 {self.name}: Bateria baixa ({self.battery_level:.1f}%)")
    
    def run(self):
        """Processo principal do dispositivo"""
        while True:
            # Aguarda o intervalo de transmissão
            yield self.env.timeout(self.tx_interval)
            
            # Simula variações no intervalo de transmissão devido a problemas de clock
            # (comum em alta umidade e temperatura da Amazônia)
            if self.climate and self.climate.current_humidity > 90 and random.random() < 0.1:
                drift = random.uniform(-30, 30)
                timestamp = datetime.fromtimestamp(time.time() + self.env.now).strftime('%H:%M:%S')
                print(f"[{timestamp}] ⏱️ {self.name}: Desvio de clock detectado: {drift:.1f}s (alta umidade)")
            
            # Lê o sensor
            temperature = self.sensor.read()
            
            # Obtém dados climáticos (se disponíveis)
            climate_data = self.climate.get_current_conditions() if self.climate else {
                'humidity': None, 'is_raining': False, 'rain_intensity': 0
            }
            
            # Calcula RSSI e SNR
            rssi = self.calculate_rssi()
            snr = self.calculate_snr()
            
            # Calcula tempo de transmissão
            tx_time = self.config.airtime
            
            # Calcula consumo de energia
            energy = self.calculate_energy_consumption(tx_time)
            self.energy_used += energy
            self.update_battery(energy)
            
            # Probabilidade de perda de pacote (baseada na distância, SF e condições climáticas)
            base_loss_prob = min(0.9, self.distance / 5000 * (1 / self.config.sf))
            
            # Fatores climáticos aumentam perda de pacotes
            weather_factor = 1.0
            if self.climate:
                if self.climate.is_raining:
                    weather_factor += (self.climate.rain_intensity / 30) * 0.5
                if self.climate.current_humidity > 85:
                    weather_factor += (self.climate.current_humidity - 85) / 30
            
            packet_loss_prob = min(0.95, base_loss_prob * weather_factor)
            
            # Quando a bateria está baixa, maior probabilidade de perda de pacote
            if self.battery_level < 15:
                packet_loss_prob = min(0.98, packet_loss_prob * 1.5)
            
            # Incrementa contador de pacotes enviados
            self.packets_sent += 1
            
            # Simula transmissão
            tx_start = self.env.now
            latency = tx_time + random.uniform(0, 0.5)  # Adiciona jitter
            
            # Se o valor é NaN (sensor falhou), registre como None no histórico
            temp_value = None if math.isnan(temperature) else temperature
            
            # Registra os valores atuais
            timestamp = datetime.fromtimestamp(time.time() + self.env.now).strftime('%H:%M:%S')
            self.history['timestamp'].append(timestamp)
            self.history['temperature'].append(temp_value)
            self.history['humidity'].append(climate_data['humidity'])
            self.history['rain'].append(climate_data['rain_intensity'] if climate_data['is_raining'] else 0)
            self.history['rssi'].append(rssi)
            self.history['snr'].append(snr)
            self.history['latency'].append(latency * 1000)  # Converte para ms
            self.history['energy'].append(self.energy_used)
            
            # Se o sensor falhou, não envia o pacote
            if math.isnan(temperature):
                print(f"[{timestamp}] {self.name}: ❌ Falha no sensor - pacote não enviado")
                continue
            
            # Determina se o pacote foi recebido
            if random.random() > packet_loss_prob:
                # Pacote recebido com sucesso
                self.packets_received += 1
                self.last_rssi = rssi
                self.last_snr = snr
                self.latencies.append(latency)
                
                # Notifica o gateway
                yield self.env.timeout(latency)
                self.gateway.receive_packet(self, temperature, rssi, snr, latency, climate_data)
            else:
                # Pacote perdido, determina causa provável
                loss_reason = "desconhecida"
                if self.climate and self.climate.is_raining and self.climate.rain_intensity > 20:
                    loss_reason = "chuva forte"
                elif self.climate and self.climate.current_humidity > 90:
                    loss_reason = "alta umidade"
                elif self.distance > 300 and self.config.sf < 10:
                    loss_reason = "distância/SF inadequado"
                elif self.battery_level < 15:
                    loss_reason = "bateria fraca"
                
                print(f"[{timestamp}] {self.name}: ❌ Pacote perdido! Causa provável: {loss_reason}")
    
    @property
    def packet_delivery_ratio(self):
        """Calcula a taxa de entrega de pacotes (PDR)"""
        if self.packets_sent == 0:
            return 0
        return self.packets_received / self.packets_sent
    
    @property
    def packet_loss_ratio(self):
        """Calcula a taxa de perda de pacotes"""
        return 1 - self.packet_delivery_ratio
    
    @property
    def average_latency(self):
        """Calcula a latência média em ms"""
        if not self.latencies:
            return 0
        return sum(self.latencies) * 1000 / len(self.latencies)  # Converte para ms
    
    @property
    def jitter(self):
        """Calcula o jitter (variação na latência) em ms"""
        if len(self.latencies) < 2:
            return 0
        latency_diffs = [abs(self.latencies[i] - self.latencies[i-1]) for i in range(1, len(self.latencies))]
        return sum(latency_diffs) * 1000 / len(latency_diffs)  # Converte para ms

class LoRaGateway:
    """Gateway LoRaWAN central"""
    def __init__(self, env, climate=None):
        self.env = env
        self.climate = climate
        self.devices = []
        self.received_data = []
        self.uptime = 100  # Percentual de tempo ativo
        
        # Iniciar processo de simulação de disponibilidade
        if climate:
            self.process = env.process(self.simulate_availability())
    
    def simulate_availability(self):
        """Simula problemas de disponibilidade do gateway"""
        while True:
            # Condições extremas podem causar quedas no gateway
            if self.climate.is_raining and self.climate.rain_intensity > 25 and random.random() < 0.2:
                # Queda temporária devido a tempestade
                downtime = random.uniform(5, 20)
                self.uptime = 0
                timestamp = datetime.fromtimestamp(time.time() + self.env.now).strftime('%H:%M:%S')
                print(f"[{timestamp}] 🌩️ GATEWAY: Queda temporária devido a tempestade (duração prevista: {downtime:.1f} min)")
                
                # Recuperação após o tempo de queda
                yield self.env.timeout(downtime * 60)
                self.uptime = 100
                timestamp = datetime.fromtimestamp(time.time() + self.env.now).strftime('%H:%M:%S')
                print(f"[{timestamp}] ✅ GATEWAY: Conexão reestabelecida após {downtime:.1f} minutos")
            
            # Verifica degradação por alta umidade
            elif self.climate.current_humidity > 90 and random.random() < 0.1:
                # Degradação temporária
                self.uptime = random.uniform(70, 90)
                timestamp = datetime.fromtimestamp(time.time() + self.env.now).strftime('%H:%M:%S')
                print(f"[{timestamp}] ⚠️ GATEWAY: Degradação de desempenho devido alta umidade (uptime: {self.uptime:.1f}%)")
                
                # Recuperação gradual
                yield self.env.timeout(30 * 60)  # 30 minutos
                self.uptime = 100
            
            # Verifica a cada 15 minutos
            yield self.env.timeout(15 * 60)
        
    def add_device(self, device):
        """Adiciona um dispositivo à lista de dispositivos conectados"""
        self.devices.append(device)
        
    def receive_packet(self, device, temperature, rssi, snr, latency, climate_data=None):
        """Recebe um pacote de um dispositivo"""
        # Verifica se o gateway está disponível
        if hasattr(self, 'uptime') and self.uptime < 100:
            if random.random() > (self.uptime / 100):
                # Gateway indisponível, pacote perdido
                timestamp = datetime.fromtimestamp(time.time() + self.env.now).strftime('%H:%M:%S')
                print(f"[{timestamp}] {device.name}: ⚠️ Pacote recebido pelo gateway mas não processado (gateway instável)")
                return
        
        timestamp = datetime.fromtimestamp(time.time() + self.env.now).strftime('%H:%M:%S')
        
        # Registra os dados recebidos
        packet_data = {
            'timestamp': timestamp,
            'device_id': device.id,
            'device_name': device.name,
            'temperature': temperature,
            'rssi': rssi,
            'snr': snr,
            'latency': latency * 1000,  # ms
            'sf': device.config.sf,
            'bw': device.config.bw,
            'cr': device.config.cr,
        }
        
        # Adiciona dados climáticos se disponíveis
        if climate_data:
            packet_data['humidity'] = climate_data['humidity']
            packet_data['is_raining'] = climate_data['is_raining']
            packet_data['rain_intensity'] = climate_data['rain_intensity']
        
        self.received_data.append(packet_data)
        
        # Formata mensagem de recebimento com dados climáticos quando disponíveis
        climate_info = ""
        if climate_data and climate_data['humidity'] is not None:
            climate_info = f", Umidade={climate_data['humidity']:.1f}%"
            if climate_data['is_raining']:
                climate_info += f", Chuva={climate_data['rain_intensity']:.1f}mm/h"
        
        print(f"[{timestamp}] ✅ Pacote recebido de {device.name}: Temp={temperature}°C, RSSI={rssi}dBm, SNR={snr}dB, Latência={latency*1000:.1f}ms{climate_info}")
        
    def get_stats(self):
        """Retorna estatísticas da rede"""
        stats = {}
        for device in self.devices:
            stats[device.name] = {
                'packets_sent': device.packets_sent,
                'packets_received': device.packets_received,
                'pdr': device.packet_delivery_ratio * 100,  # Percentual
                'plr': device.packet_loss_ratio * 100,  # Percentual
                'avg_latency': device.average_latency,  # ms
                'jitter': device.jitter,  # ms
                'rssi': device.last_rssi,  # dBm
                'snr': device.last_snr,  # dB
                'energy': device.energy_used,  # mWh
                'airtime': device.config.airtime * 1000,  # ms
                'battery': device.battery_level  # %
            }
        return stats

class LoRaNetworkSimulation:
    """Simulação completa da rede LoRaWAN"""
    def __init__(self, season=SeasonType.RAINY, vegetation_density=0.8):
        self.env = simpy.Environment()
        
        # Cria o sistema climático
        self.climate = AmazonClimate(self.env, season, vegetation_density)
        
        # Cria o gateway com referência ao clima
        self.gateway = LoRaGateway(self.env, self.climate)
        self.devices = []
        
        # Cria os dispositivos
        for i in range(4):
            device = LoRaDevice(
                self.env, 
                id=i+1,
                name=DEVICE_NAMES[i],
                gateway=self.gateway,
                distance=DISTANCES[i],
                initial_temp=INITIAL_TEMPS[i],
                climate=self.climate
            )
            self.devices.append(device)
            self.gateway.add_device(device)
            
        # Para visualização em tempo real
        self.running = False
        self.data_lock = threading.Lock()
    
    def run_simulation(self, duration=SIM_TIME):
        """Executa a simulação por um período determinado"""
        self.running = True
        self.env.run(until=duration)
        self.running = False
    
    def run_in_thread(self, duration=SIM_TIME):
        """Executa a simulação em uma thread separada"""
        sim_thread = threading.Thread(target=self.run_simulation, args=(duration,))
        sim_thread.daemon = True
        sim_thread.start()
        return sim_thread
    
    def get_network_stats(self):
        """Retorna estatísticas da rede"""
        with self.data_lock:
            return self.gateway.get_stats()
    
    def get_all_temperature_data(self):
        """Retorna todos os dados de temperatura dos dispositivos"""
        data = {}
        with self.data_lock:
            for device in self.devices:
                data[device.name] = {
                    'timestamp': device.history['timestamp'].copy(),
                    'temperature': device.history['temperature'].copy(),
                    'humidity': device.history['humidity'].copy(),
                    'rain': device.history['rain'].copy()
                }
        return data
    
    def get_all_metric_data(self):
        """Retorna todos os dados de métricas dos dispositivos"""
        data = {}
        with self.data_lock:
            for device in self.devices:
                data[device.name] = {
                    'timestamp': device.history['timestamp'].copy(),
                    'rssi': device.history['rssi'].copy(),
                    'snr': device.history['snr'].copy(),
                    'latency': device.history['latency'].copy(),
                    'energy': device.history['energy'].copy()
                }
        return data

    def change_device_config(self, device_id, sf=None, bw=None, cr=None, tp=None):
        """Altera a configuração de um dispositivo"""
        device = self.devices[device_id-1]
        if sf is not None:
            device.config.sf = sf
        if bw is not None:
            device.config.bw = bw
        if cr is not None:
            device.config.cr = cr
        if tp is not None:
            device.config.tp = tp
        print(f"Configuração de {device.name} alterada: SF={device.config.sf}, BW={device.config.bw}, CR=4/{device.config.cr}, TP={device.config.tp}dBm")
    
    def export_to_csv(self):
        """Exporta os resultados da simulação para arquivos CSV"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 1. Exportar estatísticas de rede
        stats = self.get_network_stats()
        with open(f'network_stats_{timestamp}.csv', 'w', newline='') as csvfile:
            fieldnames = ['device', 'packets_sent', 'packets_received', 'pdr', 'plr', 
                         'avg_latency', 'jitter', 'rssi', 'snr', 'energy', 'airtime', 'battery']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for device_name, device_stats in stats.items():
                row = {
                    'device': device_name,
                    'packets_sent': device_stats['packets_sent'],
                    'packets_received': device_stats['packets_received'],
                    'pdr': device_stats['pdr'],
                    'plr': device_stats['plr'],
                    'avg_latency': device_stats['avg_latency'],
                    'jitter': device_stats['jitter'],
                    'rssi': device_stats['rssi'],
                    'snr': device_stats['snr'],
                    'energy': device_stats['energy'],
                    'airtime': device_stats['airtime'],
                    'battery': device_stats['battery']
                }
                writer.writerow(row)
        
        # 2. Exportar dados de temperatura e clima
        temp_data = self.get_all_temperature_data()
        with open(f'environmental_data_{timestamp}.csv', 'w', newline='') as csvfile:
            fieldnames = ['timestamp', 'device', 'temperature', 'humidity', 'rain_intensity']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for device_name, data in temp_data.items():
                for i in range(len(data['timestamp'])):
                    writer.writerow({
                        'timestamp': data['timestamp'][i],
                        'device': device_name,
                        'temperature': data['temperature'][i],
                        'humidity': data['humidity'][i],
                        'rain_intensity': data['rain'][i]
                    })
        
        # 3. Exportar dados de métricas
        metric_data = self.get_all_metric_data()
        with open(f'metrics_data_{timestamp}.csv', 'w', newline='') as csvfile:
            fieldnames = ['timestamp', 'device', 'rssi', 'snr', 'latency', 'energy']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for device_name, data in metric_data.items():
                for i in range(len(data['timestamp'])):
                    writer.writerow({
                        'timestamp': data['timestamp'][i],
                        'device': device_name,
                        'rssi': data['rssi'][i],
                        'snr': data['snr'][i],
                        'latency': data['latency'][i],
                        'energy': data['energy'][i]
                    })
        
        # 4. Exportar dados de pacotes recebidos
        with open(f'received_packets_{timestamp}.csv', 'w', newline='') as csvfile:
            # Determina os fieldnames com base no primeiro pacote recebido (que pode ter dados climáticos)
            fieldnames = ['timestamp', 'device_id', 'device_name', 'temperature', 
                         'rssi', 'snr', 'latency', 'sf', 'bw', 'cr']
            
            if self.gateway.received_data and 'humidity' in self.gateway.received_data[0]:
                fieldnames.extend(['humidity', 'is_raining', 'rain_intensity'])
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for packet in self.gateway.received_data:
                writer.writerow(packet)
        
        print(f"\nResultados exportados para arquivos CSV com prefixo timestamp {timestamp}")
        print(f"- network_stats_{timestamp}.csv: Estatísticas gerais da rede")
        print(f"- environmental_data_{timestamp}.csv: Dados de temperatura e clima")
        print(f"- metrics_data_{timestamp}.csv: Métricas de comunicação")
        print(f"- received_packets_{timestamp}.csv: Detalhes dos pacotes recebidos")

def main():
    """Função principal para executar a simulação"""
    # Determina a estação baseada na data atual
    now = datetime.now()
    month = now.month
    is_rainy_season = month in [12, 1, 2, 3, 4, 5]  # Dez-Mai: estação chuvosa
    season = SeasonType.RAINY if is_rainy_season else SeasonType.DRY
    
    print("=" * 70)
    print(f"🌴 SIMULAÇÃO DE REDE LORAWAN NO AMBIENTE AMAZÔNICO")
    print("=" * 70)
    print(f"📅 Data atual: {now.strftime('%d/%m/%Y')}")
    print(f"🌧️ Estação: {season.value}")
    print(f"⏱️ Tempo de simulação: {SIM_TIME} segundos")
    print(f"📡 Dispositivos: {', '.join(DEVICE_NAMES)}")
    print(f"📏 Distâncias: {DISTANCES} metros")
    print(f"⚙️ Configuração padrão: SF={DEFAULT_SF}, BW={DEFAULT_BW}kHz, CR=4/{DEFAULT_CR}, TP={DEFAULT_TP}dBm")
    print("=" * 70 + "\n")
    
    # Cria a simulação com clima amazônico
    simulation = LoRaNetworkSimulation(season=season, vegetation_density=0.8)
    
    # Executa a simulação completa
    simulation.run_simulation(SIM_TIME)
    
    # Exibe estatísticas finais
    stats = simulation.get_network_stats()
    print("\n" + "=" * 70)
    print("📊 ESTATÍSTICAS FINAIS DA REDE LORAWAN")
    print("=" * 70)
    for name, device_stats in stats.items():
        print(f"\n--- {name} ---")
        print(f"Pacotes enviados: {device_stats['packets_sent']}")
        print(f"Pacotes recebidos: {device_stats['packets_received']}")
        print(f"Taxa de entrega (PDR): {device_stats['pdr']:.1f}%")
        print(f"Taxa de perda (PLR): {device_stats['plr']:.1f}%")
        print(f"Latência média: {device_stats['avg_latency']:.2f}ms")
        print(f"Jitter: {device_stats['jitter']:.2f}ms")
        print(f"RSSI: {device_stats['rssi']}dBm")
        print(f"SNR: {device_stats['snr']}dB")
        print(f"Consumo de energia: {device_stats['energy']:.2f}mWh")
        print(f"Tempo no ar: {device_stats['airtime']:.2f}ms")
        print(f"Nível de bateria: {device_stats['battery']:.1f}%")
    
    # Obter condições climáticas finais
    if hasattr(simulation, 'climate'):
        conditions = simulation.climate.get_current_conditions()
        print("\n" + "=" * 70)
        print("🌧️ CONDIÇÕES CLIMÁTICAS FINAIS")
        print("=" * 70)
        print(f"Temperatura: {conditions['temperature']}°C")
        print(f"Umidade: {conditions['humidity']}%")
        print(f"Chuva: {'Sim' if conditions['is_raining'] else 'Não'}")
        if conditions['is_raining']:
            print(f"Intensidade: {conditions['rain_intensity']} mm/h")
        print(f"Atenuação por clima: {conditions['attenuation']} dB")
    
    # Exporta os resultados para CSV
    simulation.export_to_csv()

if __name__ == "__main__":
    main()