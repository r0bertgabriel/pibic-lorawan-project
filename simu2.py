import simpy
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import random
import math

# Simulation parameters
SIM_TIME = 86400  # seconds (24 hours)
AREA_SIZE = 2000  # 2km x 2km area (in meters)
NUM_NODES = 4
GATEWAY_POS = (AREA_SIZE/2, AREA_SIZE/2)  # Gateway at center of the area
TEMP_MEAN = 27.5  # Mean temperature (between 20-35°C)
TEMP_STD = 3.0    # Standard deviation of temperature
TRANSMISSION_INTERVAL = 600  # Send data every 10 minutes

# LoRa parameters
BANDWIDTH = 125000  # 125 kHz
CODING_RATE = 5/4   # 4/5 coding rate
PREAMBLE_LENGTH = 8
N0 = -174           # Thermal noise in dBm/Hz
NF = 6              # Receiver noise figure in dB
SNR_THRESHOLD = {7: -7.5, 8: -10, 9: -12.5, 10: -15, 11: -17.5, 12: -20}  # SNR thresholds per SF
TX_POWER = 14       # Transmission power in dBm
FREQUENCY = 868     # MHz (EU868)

# Path loss model parameters
PL_EXPONENT = 2.8   # Path loss exponent
REF_DISTANCE = 1000 # Reference distance in meters
PL_REF = 107.41     # Path loss at reference distance in dB

class LoRaNode:
    def __init__(self, env, node_id, x, y):
        self.env = env
        self.id = node_id
        self.x = x
        self.y = y
        self.data = []  # Store node data
        self.action = env.process(self.run())
        
    def calculate_distance_to_gateway(self):
        """Calculate Euclidean distance to the gateway"""
        dx = self.x - GATEWAY_POS[0]
        dy = self.y - GATEWAY_POS[1]
        return math.sqrt(dx**2 + dy**2)
        
    def calculate_path_loss(self, distance):
        """Calculate path loss using log-distance model"""
        if distance <= 0:
            distance = 1  # Avoid log(0)
        if distance <= REF_DISTANCE:
            return PL_REF + 10 * PL_EXPONENT * math.log10(distance/REF_DISTANCE)
        else:
            return PL_REF + 10 * PL_EXPONENT * math.log10(distance/REF_DISTANCE)
    
    def calculate_rssi(self, path_loss):
        """Calculate RSSI based on path loss"""
        return TX_POWER - path_loss
    
    def calculate_snr(self, rssi):
        """Calculate Signal-to-Noise Ratio"""
        noise_power = N0 + 10 * math.log10(BANDWIDTH) + NF
        return rssi - noise_power
    
    def select_sf(self, snr):
        """Select appropriate spreading factor based on SNR"""
        for sf in sorted(SNR_THRESHOLD.keys()):
            if snr >= SNR_THRESHOLD[sf]:
                return sf
        return 12  # Use highest SF if SNR is too low
    
    def calculate_airtime(self, sf, payload_size):
        """Calculate LoRa transmission time in milliseconds"""
        n_payload = 8 + max(math.ceil((8 * payload_size - 4 * sf + 28 + 16)/(4 * sf)) * CODING_RATE, 0)
        t_symbol = (2**sf)/BANDWIDTH
        t_preamble = (PREAMBLE_LENGTH + 4.25) * t_symbol
        t_payload = n_payload * t_symbol
        return (t_preamble + t_payload) * 1000  # Convert to ms
    
    def calculate_packet_loss_probability(self, snr, sf):
        """Calculate probability of packet loss based on SNR and SF"""
        if snr >= SNR_THRESHOLD[sf] + 5:
            return 0.01  # Very good signal, very low loss
        elif snr >= SNR_THRESHOLD[sf] + 2:
            return 0.05  # Good signal
        elif snr >= SNR_THRESHOLD[sf]:
            return 0.15  # Acceptable signal
        elif snr >= SNR_THRESHOLD[sf] - 2:
            return 0.4   # Poor signal
        else:
            return 0.8   # Very poor signal
    
    def run(self):
        """Process to simulate node behavior"""
        while True:
            # Wait for next transmission interval
            yield self.env.timeout(TRANSMISSION_INTERVAL)
            
            # Current timestamp
            timestamp = self.env.now
            
            # Generate temperature reading (normal distribution between 20-35°C)
            temperature = np.random.normal(TEMP_MEAN, TEMP_STD)
            temperature = max(20, min(35, temperature))  # Constrain between 20-35°C
            
            # Calculate network parameters
            distance = self.calculate_distance_to_gateway()
            path_loss = self.calculate_path_loss(distance)
            rssi = self.calculate_rssi(path_loss)
            snr = self.calculate_snr(rssi)
            sf = self.select_sf(snr)
            
            # Calculate data rate (bits per second)
            # Using simplified formula: DR = SF * (BW / 2^SF)
            data_rate = sf * (BANDWIDTH / (2**sf))
            
            # Simulate packet transmission
            payload_size = 10  # 10 bytes for temperature data
            latency = self.calculate_airtime(sf, payload_size)
            
            # Determine if packet is delivered
            packet_loss_prob = self.calculate_packet_loss_probability(snr, sf)
            packet_delivered = random.random() > packet_loss_prob
            
            # Record data
            self.data.append({
                'timestamp': timestamp,
                'device_id': self.id,
                'x': self.x,
                'y': self.y,
                'temperature': temperature,
                'rssi': rssi,
                'snr': snr,
                'sf': sf,
                'data_rate': data_rate,
                'packet_delivered': packet_delivered,
                'latency_ms': latency
            })

def run_simulation():
    # Create simulation environment
    env = simpy.Environment()
    
    # Create nodes with random positions
    nodes = []
    for i in range(NUM_NODES):
        x = random.uniform(0, AREA_SIZE)
        y = random.uniform(0, AREA_SIZE)
        nodes.append(LoRaNode(env, i, x, y))
    
    # Run simulation
    env.run(until=SIM_TIME)
    
    # Collect data from all nodes
    all_data = []
    for node in nodes:
        all_data.extend(node.data)
    
    # Create DataFrame
    df = pd.DataFrame(all_data)
    return df

def visualize_results(df):
    """Create visualization plots"""
    # Set up plot style
    plt.style.use('ggplot')
    
    # Plot 1: Node positions and gateway
    plt.figure(figsize=(10, 8))
    plt.scatter(df['x'].unique(), df['y'].unique(), s=100, c='blue', marker='o', label='Nodes')
    plt.scatter([GATEWAY_POS[0]], [GATEWAY_POS[1]], s=200, c='red', marker='^', label='Gateway')
    for node_id in df['device_id'].unique():
        node_data = df[df['device_id'] == node_id].iloc[0]
        plt.annotate(f"Node {node_id}", (node_data['x'], node_data['y']), 
                     textcoords="offset points", xytext=(0,10), ha='center')
    plt.xlim(0, AREA_SIZE)
    plt.ylim(0, AREA_SIZE)
    plt.title('LoRaWAN Node Deployment')
    plt.xlabel('X position (m)')
    plt.ylabel('Y position (m)')
    plt.legend()
    plt.savefig('node_positions.png')
    
    # Plot 2: Temperature readings over time
    plt.figure(figsize=(12, 6))
    for node_id in df['device_id'].unique():
        node_data = df[df['device_id'] == node_id]
        plt.plot(node_data['timestamp'], node_data['temperature'], label=f'Node {node_id}')
    plt.title('Temperature Readings Over Time')
    plt.xlabel('Time (s)')
    plt.ylabel('Temperature (°C)')
    plt.legend()
    plt.savefig('temperature_readings.png')
    
    # Plot 3: RSSI values by node
    plt.figure(figsize=(12, 6))
    for node_id in df['device_id'].unique():
        node_data = df[df['device_id'] == node_id]
        plt.plot(node_data['timestamp'], node_data['rssi'], label=f'Node {node_id}')
    plt.title('RSSI Values Over Time')
    plt.xlabel('Time (s)')
    plt.ylabel('RSSI (dBm)')
    plt.legend()
    plt.savefig('rssi_values.png')
    
    # Plot 4: Packet delivery ratio by node
    plt.figure(figsize=(10, 6))
    node_ids = df['device_id'].unique()
    delivery_ratios = []
    
    for node_id in node_ids:
        node_data = df[df['device_id'] == node_id]
        delivery_ratio = node_data['packet_delivered'].mean() * 100
        delivery_ratios.append(delivery_ratio)
    
    plt.bar([str(id) for id in node_ids], delivery_ratios)
    plt.title('Packet Delivery Ratio by Node')
    plt.xlabel('Node ID')
    plt.ylabel('Delivery Ratio (%)')
    plt.ylim(0, 100)
    plt.savefig('packet_delivery.png')

if __name__ == "__main__":
    # Run simulation
    print("Starting LoRaWAN simulation...")
    results = run_simulation()
    
    # Save results to CSV
    results.to_csv('lorawan_simulation_results.csv', index=False)
    print(f"Simulation complete. {len(results)} data points collected.")
    
    # Visualize results
    print("Generating visualization plots...")
    visualize_results(results)
    print("Visualization complete. Check the current directory for CSV and PNG files.")
    
    # Display summary statistics
    print("\nSummary Statistics:")
    print(f"Average Temperature: {results['temperature'].mean():.2f}°C")
    print(f"Average RSSI: {results['rssi'].mean():.2f} dBm")
    print(f"Average SNR: {results['snr'].mean():.2f} dB")
    print(f"Packet Delivery Ratio: {results['packet_delivered'].mean()*100:.2f}%")
    print(f"Average Latency: {results['latency_ms'].mean():.2f} ms")