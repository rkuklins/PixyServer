#!/usr/bin/env python3
"""
EV3 Lightweight PixyCam Server
Captures RAW data from PixyCam and streams to PC for processing
Minimal dependencies - no OpenCV, no NumPy, no image processing
"""

import socket
import threading
import time
import json
import struct
from collections import deque
from pixycamev3.pixy2 import Pixy2


# EV3 specific imports
try:
    from ev3dev2.sound import Sound
    from ev3dev2.led import Leds
    from ev3dev2.button import Button
    EV3_AVAILABLE = True
except ImportError:
    print("EV3 libraries not available - running in simulation mode")
    EV3_AVAILABLE = False

# PixyCam communication (lightweight)
try:
    import smbus2
    I2C_AVAILABLE = True
except ImportError:
    I2C_AVAILABLE = False
    print("I2C not available - running in simulation mode")



try:
    import spidev
    SPI_AVAILABLE = True
except ImportError:
    SPI_AVAILABLE = False

try:
    import serial
    UART_AVAILABLE = True
except ImportError:
    UART_AVAILABLE = False

class LightweightPixyCam:
    """Minimal PixyCam interface - raw data capture only"""
    
    def __init__(self, interface='I2C', address=0x54, port=3):
        self.interface = interface.upper()
        self.address = address
        self.port = port
        self.connection = None
        
        # PixyCam basic specs
        self.width = 320
        self.height = 200
        self.bytes_per_pixel = 2  # RGB565 format
        self.frame_size = self.width * self.height * self.bytes_per_pixel
        
        # Simple frame counter
        self.frame_count = 0
        
        print("Initializing PixyCam on {} interface...".format(interface))
        self.init_connection()
    
    def init_connection(self):
        """Initialize minimal connection to PixyCam"""
        try:
            if self.interface == 'I2C' and I2C_AVAILABLE:
                #self.connection = Pixy2(port=1, i2c_address=0x54)
                #self.connection.mode = 'SIG1'
                self.connection = smbus2.SMBus(self.port)
                print("PixyCam I2C connected on bus {}, address 0x{:02X}".format(self.port, self.address))
                return True
                
            elif self.interface == 'SPI' and SPI_AVAILABLE:
                self.connection = spidev.SpiDev()
                self.connection.open(0, 0)  # Bus 0, Device 0
                self.connection.max_speed_hz = 2000000  # 2MHz for fast data transfer
                self.connection.mode = 0
                print("PixyCam SPI connected at 2MHz")
                return True
                
            elif self.interface == 'UART' and UART_AVAILABLE:
                uart_device = "/dev/ttyS{}".format(self.port)
                self.connection = serial.Serial(
                    port=uart_device,
                    baudrate=230400,  # High speed UART
                    bytesize=8,
                    parity='N',
                    stopbits=1,
                    timeout=0.1
                )
                print("PixyCam UART connected on {} at 230400 baud".format(uart_device))
                return True
                
            else:
                print("Interface {} not available".format(self.interface))
                return False
                
        except Exception as e:
            print("Error connecting to PixyCam: {}".format(e))
            return False
    
    def read_raw_data(self, size):
        """Read raw bytes from PixyCam"""
        if not self.connection:
            return None
        
        try:
            if self.interface == 'I2C':
                # I2C reads in chunks due to size limitations
                data = bytearray()
                chunk_size = 32  # I2C block read limit
                
                for offset in range(0, size, chunk_size):
                    remaining = min(chunk_size, size - offset)
                    try:
                        chunk = self.connection.read_i2c_block_data(self.address, 0, remaining)
                        data.extend(chunk)
                    except OSError:
                        # Handle I2C communication errors
                        break
                
                return bytes(data) if len(data) > 0 else None
                
            elif self.interface == 'SPI':
                # SPI can read larger blocks
                try:
                    data = self.connection.readbytes(size)
                    return bytes(data)
                except Exception:
                    return None
                
            elif self.interface == 'UART':
                # UART serial read
                try:
                    data = self.connection.read(size)
                    return data if len(data) > 0 else None
                except Exception:
                    return None
                    
        except Exception as e:
            print("Error reading data: {}".format(e))
            return None
    
    def capture_frame(self):
        """Capture raw frame data from PixyCam"""
        try:
            # Simple frame capture - get whatever data is available
            # This is a simplified approach - real implementation would
            # need proper PixyCam protocol commands
            
            # Try to read a frame's worth of data
            frame_data = self.read_raw_data(self.frame_size)
            
            if frame_data and len(frame_data) >= self.frame_size:
                self.frame_count += 1
                
                # Return frame metadata with raw data
                frame_info = {
                    'frame_id': self.frame_count,
                    'timestamp': time.time(),
                    'width': self.width,
                    'height': self.height,
                    'format': 'RGB565',
                    'data_size': len(frame_data),
                    'raw_data': frame_data  # Raw bytes
                }
                return frame_info
            else:
                return None
                
        except Exception as e:
            print("Error capturing frame: {}".format(e))
            return None
    
    def get_simple_objects(self):
        """Get basic object detection data if available"""
        try:
            # Read small amount of data that might contain object blocks
            obj_data = self.read_raw_data(64)
            if not obj_data:
                return []
            
            # Very simple object parsing - look for sync patterns
            objects = []
            
            # Look for PixyCam sync bytes (0x5A 0x5A)
            for i in range(len(obj_data) - 13):
                if obj_data[i] == 0x5A and obj_data[i + 1] == 0x5A:
                    try:
                        # Simple object block parsing
                        signature = obj_data[i + 4] | (obj_data[i + 5] << 8)
                        x = obj_data[i + 6] | (obj_data[i + 7] << 8)
                        y = obj_data[i + 8] | (obj_data[i + 9] << 8)
                        width = obj_data[i + 10] | (obj_data[i + 11] << 8)
                        height = obj_data[i + 12] | (obj_data[i + 13] << 8)
                        
                        # Basic validation
                        if 0 < width < self.width and 0 < height < self.height:
                            objects.append({
                                'signature': signature,
                                'x': x,
                                'y': y,
                                'width': width,
                                'height': height,
                                'timestamp': time.time()
                            })
                    except (IndexError, ValueError):
                        continue
            
            return objects
            
        except Exception as e:
            print("Error getting objects: {}".format(e))
            return []
    
    def close(self):
        """Close connection"""
        if self.connection:
            try:
                if self.interface == 'UART':
                    self.connection.close()
                elif self.interface == 'SPI':
                    self.connection.close()
                print("PixyCam {} connection closed".format(self.interface))
            except Exception as e:
                print("Error closing connection: {}".format(e))

class EV3RawDataStreamer:
    """Lightweight EV3 server that streams raw camera data"""
    
    def __init__(self, host='0.0.0.0', port=8888, pixy_interface='I2C'):
        self.host = host
        self.port = port
        self.running = False
        self.clients = []
        
        # EV3 components (optional)
        if EV3_AVAILABLE:
            self.sound = Sound()
            self.leds = Leds()
            self.button = Button()
        
        # Initialize PixyCam
        self.pixy = LightweightPixyCam(interface=pixy_interface)
        
        # Simple settings
        self.target_fps = 10  # Conservative for EV3
        self.send_objects = True
        self.compress_data = False  # No compression on EV3
        
        # Basic stats
        self.stats = {
            'frames_sent': 0,
            'clients_connected': 0,
            'bytes_sent': 0,
            'uptime': 0,
            'start_time': time.time(),
            'errors': 0
        }
        
        print("EV3 Raw Data Streamer initialized")
    
    def create_data_packet(self, frame_info, objects=None):
        """Create simple data packet with raw frame data"""
        try:
            if not frame_info:
                return None
            
            # Create packet structure
            packet = {
                'type': 'frame_data',
                'timestamp': frame_info['timestamp'],
                'frame_id': frame_info['frame_id'],
                'width': frame_info['width'],
                'height': frame_info['height'],
                'format': frame_info['format'],
                'data_size': frame_info['data_size'],
                'objects': objects if self.send_objects else [],
                'stats': self.get_stats()
            }
            
            # Convert to JSON
            json_data = json.dumps(packet).encode('utf-8')
            
            # Create binary packet: json_size + json_data + raw_data
            raw_data = frame_info['raw_data']
            
            packet_binary = (
                struct.pack('!I', len(json_data)) +  # JSON size
                json_data +                          # JSON metadata
                struct.pack('!I', len(raw_data)) +   # Raw data size
                raw_data                             # Raw frame data
            )
            
            return packet_binary
            
        except Exception as e:
            print("Error creating packet: {}".format(e))
            self.stats['errors'] += 1
            return None
    
    def get_stats(self):
        """Get current statistics"""
        current_time = time.time()
        self.stats['uptime'] = current_time - self.stats['start_time']
        self.stats['clients_connected'] = len(self.clients)
        return self.stats.copy()
    
    def handle_client(self, client_socket, address):
        """Handle client connection - stream raw data"""
        print("Client connected from {}".format(address))
        self.clients.append(client_socket)
        
        # EV3 feedback
        if EV3_AVAILABLE:
            self.sound.beep()
            self.leds.set_color('LEFT', 'GREEN')
        
        try:
            frame_interval = 1.0 / self.target_fps
            last_frame_time = 0
            
            while self.running:
                current_time = time.time()
                
                # Control frame rate
                if current_time - last_frame_time < frame_interval:
                    time.sleep(0.01)
                    continue
                
                # Capture frame
                frame_info = self.pixy.capture_frame()
                
                if frame_info:
                    # Get objects if enabled
                    objects = self.pixy.get_simple_objects() if self.send_objects else []
                    
                    # Create packet
                    packet = self.create_data_packet(frame_info, objects)
                    
                    if packet:
                        try:
                            client_socket.send(packet)
                            self.stats['frames_sent'] += 1
                            self.stats['bytes_sent'] += len(packet)
                            last_frame_time = current_time
                        except (ConnectionResetError, BrokenPipeError):
                            break
                
        except Exception as e:
            print("Error handling client {}: {}".format(address, e))
            self.stats['errors'] += 1
        finally:
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            client_socket.close()
            print("Client {} disconnected".format(address))
            
            if EV3_AVAILABLE:
                self.sound.tone(400, 200)
    
    def start_server(self):
        """Start the TCP server"""
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, self.port))
            server_socket.listen(3)  # Limit concurrent clients
            
            print("EV3 Raw Data Server listening on {}:{}".format(self.host, self.port))
            
            # Startup sound
            if EV3_AVAILABLE:
                self.sound.tone(800, 100)
                time.sleep(0.1)
                self.sound.tone(1000, 100)
            
            while self.running:
                try:
                    client_socket, address = server_socket.accept()
                    
                    # Handle each client in separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except Exception as e:
                    if self.running:
                        print("Error accepting connection: {}".format(e))
                        self.stats['errors'] += 1
            
        except Exception as e:
            print("Server error: {}".format(e))
            self.stats['errors'] += 1
        finally:
            try:
                server_socket.close()
            except:
                pass
    
    def monitor_buttons(self):
        """Monitor EV3 buttons for simple control"""
        if not EV3_AVAILABLE:
            return
        
        print("Button controls:")
        print("  Enter: Toggle object detection")
        print("  Up/Down: Adjust FPS")
        print("  Backspace: Stop server")
        
        while self.running:
            try:
                if self.button.enter:
                    self.send_objects = not self.send_objects
                    print("Object detection: {}".format('ON' if self.send_objects else 'OFF'))
                    self.sound.beep()
                    time.sleep(0.5)
                
                if self.button.up:
                    self.target_fps = min(15, self.target_fps + 1)
                    print("FPS: {}".format(self.target_fps))
                    self.sound.tone(600, 100)
                    time.sleep(0.5)
                
                if self.button.down:
                    self.target_fps = max(2, self.target_fps - 1)
                    print("FPS: {}".format(self.target_fps))
                    self.sound.tone(400, 100)
                    time.sleep(0.5)
                
                if self.button.backspace:
                    print("Stopping server...")
                    self.running = False
                    break
                
                time.sleep(0.1)
                
            except Exception as e:
                print("Button error: {}".format(e))
    
    def status_monitor(self):
        """Simple status display"""
        while self.running:
            try:
                stats = self.get_stats()
                print("\n--- EV3 Camera Server Status ---")
                print("Uptime: {:.0f}s".format(stats['uptime']))
                print("Clients: {}".format(stats['clients_connected']))
                print("Frames sent: {}".format(stats['frames_sent']))
                print("Data sent: {:.1f} KB".format(stats['bytes_sent'] / 1024))
                print("Target FPS: {}".format(self.target_fps))
                print("Objects: {}".format('ON' if self.send_objects else 'OFF'))
                print("Errors: {}".format(stats['errors']))
                
                time.sleep(10)  # Update every 10 seconds
                
            except Exception as e:
                print("Status error: {}".format(e))
    
    def start(self):
        """Start the streaming server"""
        if not self.pixy.connection:
            print("ERROR: PixyCam not connected!")
            return False
        
        self.running = True
        self.stats['start_time'] = time.time()
        
        # Start server thread
        server_thread = threading.Thread(target=self.start_server)
        server_thread.daemon = True
        server_thread.start()
        
        # Start button monitor
        button_thread = threading.Thread(target=self.monitor_buttons)
        button_thread.daemon = True
        button_thread.start()
        
        # Start status monitor
        status_thread = threading.Thread(target=self.status_monitor)
        status_thread.daemon = True
        status_thread.start()
        
        print("EV3 Raw Data Streamer started!")
        print("Streaming raw camera data to PC for processing...")
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.stop()
        
        return True
    
    def stop(self):
        """Stop the server"""
        self.running = False
        
        # Close all client connections
        for client in self.clients[:]:  # Copy list to avoid modification during iteration
            try:
                client.close()
            except:
                pass
        
        # Close PixyCam
        self.pixy.close()
        
        # Shutdown sound
        if EV3_AVAILABLE:
            self.sound.tone(800, 100)
            time.sleep(0.1)
            self.sound.tone(600, 100)
            self.leds.all_off()
        
        print("EV3 Raw Data Streamer stopped")

# Main execution
if __name__ == "__main__":
    print("EV3 Lightweight PixyCam Server")
    print("Captures raw data only - processing done on PC")
    print("=" * 50)
    
    # Configuration
    HOST = '0.0.0.0'  # Listen on all interfaces
    PORT = 8888
    INTERFACE = 'I2C'  # Change to 'SPI' or 'UART' as needed
    
    # Create streamer
    streamer = EV3RawDataStreamer(
        host=HOST,
        port=PORT,
        pixy_interface=INTERFACE
    )
    
    # Configure for EV3 performance
    streamer.target_fps = 8      # Conservative for EV3
    streamer.send_objects = True  # Include basic object data
    
    try:
        print("Starting server on {}:{}".format(HOST, PORT))
        print("Using {} interface".format(INTERFACE))
        
        if streamer.start():
            print("Server started successfully")
        else:
            print("Failed to start server")
            
    except Exception as e:
        print("Error: {}".format(e))
    finally:
        streamer.stop()