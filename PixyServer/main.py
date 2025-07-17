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
    
    def __init__(self, interface='I2C', address=0x54, port=5):
        self.interface = interface.upper()
        self.address = address
        self.port = port
        self.connection = None
        
        # PixyCam basic specs
        self.width = 80   # Reduced for testing
        self.height = 60   # Reduced for testing
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
                self.connection = smbus2.SMBus(self.port)
                print("PixyCam I2C connected on bus {}, address 0x{:02X}".format(self.port, self.address))
                
            elif self.interface == 'SPI' and SPI_AVAILABLE:
                self.connection = spidev.SpiDev()
                self.connection.open(0, 0)  # Bus 0, Device 0
                self.connection.max_speed_hz = 2000000  # 2MHz for fast data transfer
                self.connection.mode = 0
                print("PixyCam SPI connected at 2MHz")
                
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
                
            else:
                print("Interface {} not available".format(self.interface))
                return False
            
            # Initialize video mode
            if self.connection:
                return self.init_video_mode()
            
            return False
                
        except Exception as e:
            print("Error connecting to PixyCam: {}".format(e))
            return False
    
    def send_command(self, command, *args):
        """Send command to PixyCam"""
        if not self.connection:
            print("No connection");
            return False
        
        try:
            if self.interface == 'I2C':
                # I2C command structure
                cmd_data = [command] + list(args)
                self.connection.write_i2c_block_data(self.address, 0, cmd_data)
                time.sleep(0.01)  # Small delay for command processing
                
            elif self.interface == 'SPI':
                # SPI command structure  
                cmd_data = [command] + list(args)
                self.connection.writebytes(cmd_data)
                time.sleep(0.01)
                
            elif self.interface == 'UART':
                # UART command structure
                cmd_data = bytes([command] + list(args))
                self.connection.write(cmd_data)
                self.connection.flush()
                time.sleep(0.01)
                
            return True
            
        except Exception as e:
            print("Error sending command 0x{:02X}: {}".format(command, e))
            return False
    
    def init_video_mode(self):
        """Initialize PixyCam for video streaming"""
        try:
            print("Initializing PixyCam video mode...")
            
            # Send initialization commands
            # Command 0x20: Get version
            if self.send_command(0x20):
                print("PixyCam version request sent")
            
            # Command 0x21: Set camera mode to video
            if self.send_command(0x21, 0x01):
                print("PixyCam video mode enabled")
            
            # Give PixyCam time to initialize
            time.sleep(0.5)
            
            return True
            
        except Exception as e:
            print("Error initializing video mode: {}".format(e))
            return False
    
    def read_raw_data(self, size):
        """Read raw bytes from PixyCam"""
        if not self.connection:
            print("No connection in read_raw_data");
            return None
        
        try:
            print("Reading {} bytes from {} interface".format(size, self.interface));
            if self.interface == 'I2C':
                # I2C reads in chunks due to size limitations
                data = bytearray()
                chunk_size = 32  # I2C block read limit
                
                for offset in range(0, size, chunk_size):
                    remaining = min(chunk_size, size - offset)
                    try:
                        print("I2C reading {} bytes at offset {}".format(remaining, offset));
                        chunk = self.connection.read_i2c_block_data(self.address, 0, remaining)
                        data.extend(chunk)
                        print("I2C got {} bytes".format(len(chunk)));
                    except OSError as e:
                        print("I2C error: {}".format(e));
                        # Handle I2C communication errors
                        break
                
                result = bytes(data) if len(data) > 0 else None
                print("I2C total result: {} bytes".format(len(data) if result else 0));
                return result
                
            elif self.interface == 'SPI':
                # SPI can read larger blocks
                try:
                    print("SPI reading {} bytes".format(size));
                    data = self.connection.readbytes(size)
                    print("SPI got {} bytes".format(len(data)));
                    return bytes(data)
                except Exception as e:
                    print("SPI error: {}".format(e));
                    return None
                
            elif self.interface == 'UART':
                # UART serial read
                try:
                    print("UART reading {} bytes".format(size));
                    data = self.connection.read(size)
                    print("UART got {} bytes".format(len(data)));
                    return data if len(data) > 0 else None
                except Exception as e:
                    print("UART error: {}".format(e));
                    return None
                    
        except Exception as e:
            print("Error reading data: {}".format(e))
            return None
    
    def capture_frame(self):
        """Capture raw frame data from PixyCam with proper protocol"""
        try:
            print("Capture frame");
            # Send frame request command
            if not self.send_command(0x22):  # Request frame command
                return None
            
            # Small delay for PixyCam to prepare data
            time.sleep(0.01)
            
            print("Frame request sent");
            # Try to read frame data in chunks for better reliability
            frame_data = bytearray()
            chunk_size = 1024 if self.interface == 'SPI' else 32  # Larger chunks for SPI
            
            print("Chunk size: {}".format(chunk_size));
            print("Frame size: {}".format(self.frame_size));
            chunk_count = 0;
            max_chunks = 100;  # Limit to prevent infinite loop
            
            for chunk_start in range(0, self.frame_size, chunk_size):
                if chunk_count >= max_chunks:
                    print("Reached max chunks ({}), stopping".format(max_chunks));
                    break;
                    
                remaining = min(chunk_size, self.frame_size - chunk_start)
                print("Reading chunk {}: start={}, remaining={}".format(chunk_count, chunk_start, remaining));
                chunk = self.read_raw_data(remaining)
                
                if chunk:
                    frame_data.extend(chunk)
                    print("Chunk {}: got {} bytes".format(chunk_count, len(chunk)));
                else:
                    print("Chunk {}: failed to read data".format(chunk_count));
                    break
                chunk_count += 1;
            
            print("Frame data: {}".format(frame_data));
            # Check if we got a reasonable amount of data
            if len(frame_data) >= self.frame_size // 2:  # At least half the expected data
                self.frame_count += 1
                
                # Create test pattern if data seems invalid
                if len(frame_data) < self.frame_size:
                    print("Partial frame received: {}/{} bytes".format(len(frame_data), self.frame_size))
                    # Pad with test pattern
                    while len(frame_data) < self.frame_size:
                        frame_data.append(0x00)  # Black pixels
                
                # Return frame metadata with raw data
                frame_info = {
                    'frame_id': self.frame_count,
                    'timestamp': time.time(),
                    'width': self.width,
                    'height': self.height,
                    'format': 'RGB565',
                    'data_size': len(frame_data),
                    'raw_data': bytes(frame_data)
                }
                
                print("Frame {} captured: {} bytes".format(self.frame_count, len(frame_data)))
                return frame_info
                
            else:
                # Generate test frame if no data
                return self.generate_test_frame()
                
        except Exception as e:
            print("Error capturing frame: {}".format(e))
            return self.generate_test_frame()
    
    def generate_test_frame(self):
        """Generate a test frame for debugging"""
        try:
            self.frame_count += 1
            
            # Create a simple test pattern (gradient)
            test_data = bytearray()
            for y in range(self.height):
                for x in range(self.width):
                    # Create RGB565 gradient pattern
                    r = (x * 31) // self.width
                    g = (y * 63) // self.height  
                    b = ((x + y) * 31) // (self.width + self.height)
                    
                    # Pack into RGB565 format
                    pixel = (r << 11) | (g << 5) | b
                    test_data.append(pixel & 0xFF)
                    test_data.append((pixel >> 8) & 0xFF)
            
            frame_info = {
                'frame_id': self.frame_count,
                'timestamp': time.time(),
                'width': self.width,
                'height': self.height,
                'format': 'RGB565',
                'data_size': len(test_data),
                'raw_data': bytes(test_data)
            }
            
            print("Test frame {} generated: {} bytes".format(self.frame_count, len(test_data)))
            return frame_info
            
        except Exception as e:
            print("Error generating test frame: {}".format(e))
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
        self.test_mode = False  # Enable test frames if PixyCam fails
        
        # Basic stats
        self.stats = {
            'frames_sent': 0,
            'clients_connected': 0,
            'bytes_sent': 0,
            'uptime': 0,
            'start_time': time.time(),
            'errors': 0,
            'test_frames_sent': 0
        }
        
        print("EV3 Raw Data Streamer initialized")
        
        # Test PixyCam connection
        if self.pixy.connection:
            print("OK PixyCam connection successful")
        else:
            print("FAIL PixyCam connection failed - will use test mode")
            self.test_mode = True
    
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
            consecutive_failures = 0
            max_failures = 10
            
            print("Starting frame capture for client {}".format(address))
            
            while self.running:
                current_time = time.time()
                print("Current time: {}".format(current_time));
                # Control frame rate
                
                if current_time - last_frame_time < frame_interval:
                    time.sleep(0.0001)
                    continue
                print("Frame interval: {}".format(frame_interval));

                # Capture frame (or generate test frame)
                if self.test_mode or not self.pixy.connection:
                    print("Test frame");
                    frame_info = self.pixy.generate_test_frame()
                    if frame_info:
                        self.stats['test_frames_sent'] += 1
                else:
                    print("Frame");
                    frame_info = self.pixy.capture_frame()
                
                if frame_info:
                    # Reset failure counter on success
                    consecutive_failures = 0
                    
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
                            
                            # Debug output every 10 frames
                            if self.stats['frames_sent'] % 10 == 0:
                                print("Sent frame {} to {}".format(self.stats['frames_sent'], address))
                                
                        except (ConnectionResetError, BrokenPipeError):
                            print("Client {} disconnected during send".format(address))
                            break
                else:
                    consecutive_failures += 1
                    print("Frame capture failed ({}/{})".format(consecutive_failures, max_failures))
                    
                    if consecutive_failures >= max_failures:
                        print("Too many consecutive failures, generating test frames")
                        # Switch to test frame mode
                        test_frame = self.pixy.generate_test_frame()
                        if test_frame:
                            packet = self.create_data_packet(test_frame, [])
                            if packet:
                                try:
                                    client_socket.send(packet)
                                    self.stats['frames_sent'] += 1
                                    self.stats['bytes_sent'] += len(packet)
                                    last_frame_time = current_time
                                except (ConnectionResetError, BrokenPipeError):
                                    break
                        consecutive_failures = 0  # Reset counter
                
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
        print("  Left: Toggle test mode")
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
                
                if self.button.left:
                    self.test_mode = not self.test_mode
                    print("Test mode: {}".format('ON' if self.test_mode else 'OFF'))
                    self.sound.tone(500, 100)
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
                print("Test frames: {}".format(stats.get('test_frames_sent', 0)))
                print("Data sent: {:.1f} KB".format(stats['bytes_sent'] / 1024))
                print("Target FPS: {}".format(self.target_fps))
                print("Objects: {}".format('ON' if self.send_objects else 'OFF'))
                print("Test mode: {}".format('ON' if self.test_mode else 'OFF'))
                print("Errors: {}".format(stats['errors']))
                
                time.sleep(10)  # Update every 10 seconds
                
            except Exception as e:
                print("Status error: {}".format(e))
    
    def start(self):
        """Start the streaming server"""
        if not self.pixy.connection and not self.test_mode:
            print("ERROR: PixyCam not connected and test mode disabled!")
            print("Press LEFT button to enable test mode")
            
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