import cv2
import mediapipe as mp
import numpy as np
import socket
import joblib
import threading
import time
from shared_vars import current_pose, running, pose_lock
import pygame
import sys
import math

# ==================== SETTING ====================
MODEL_PATH = "rf_pose_model.pkl"
# ==================================================
ESP32_HOST = "esp32.local"
ESP32_PORT = 1234

# Variabel untuk status koneksi ESP
esp_connected = False
client_socket = None

# Inisialisasi pygame untuk simulator
pygame.init()

# Warna
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
GRAY = (200, 200, 200)

# Ukuran window simulator
SIMULATOR_WIDTH = 800
SIMULATOR_HEIGHT = 600

# Buat window simulator
simulator_screen = pygame.display.set_mode((SIMULATOR_WIDTH, SIMULATOR_HEIGHT))
pygame.display.set_caption("Robot DDMR Simulator")

# Parameter robot
robot_width = 60
robot_length = 80
robot_x = SIMULATOR_WIDTH // 2
robot_y = SIMULATOR_HEIGHT // 2
robot_angle = 0  # Dalam derajat
left_wheel_speed = 0
right_wheel_speed = 0
wheel_distance = 50  # Jarak antara roda kiri dan kanan

# Fungsi untuk menggambar robot
def draw_robot():
    # Hitung titik-titik sudut robot berdasarkan posisi dan orientasi
    points = [
        (-robot_length/2, -robot_width/2),
        (robot_length/2, -robot_width/2),
        (robot_length/2, robot_width/2),
        (-robot_length/2, robot_width/2)
    ]
    
    # Rotasikan titik-titik
    rotated_points = []
    for x, y in points:
        x_rot = x * math.cos(math.radians(robot_angle)) - y * math.sin(math.radians(robot_angle))
        y_rot = x * math.sin(math.radians(robot_angle)) + y * math.cos(math.radians(robot_angle))
        rotated_points.append((x_rot + robot_x, y_rot + robot_y))
    
    # Gambar badan robot
    pygame.draw.polygon(simulator_screen, BLUE, rotated_points)
    
    # Gambar garis depan robot
    front_x = robot_length/2 * math.cos(math.radians(robot_angle))
    front_y = robot_length/2 * math.sin(math.radians(robot_angle))
    pygame.draw.line(simulator_screen, RED, 
                    (robot_x, robot_y), 
                    (robot_x + front_x, robot_y + front_y), 3)

def robot_simulator():
    global robot_x, robot_y, robot_angle, left_wheel_speed, right_wheel_speed
    
    clock = pygame.time.Clock()
    base_speed = 3
    turn_ratio = 0.4  # Ratio for wheel speed during turns
    
    while running:
        # Handle pygame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
        
        # Get current pose from shared variable
        with pose_lock:
            pose = current_pose
        
        # Set wheel speeds based on pose - CORRECTED DIRECTIONS
        if pose == "maju":
            left_wheel_speed = base_speed
            right_wheel_speed = base_speed
        elif pose == "mundur":
            left_wheel_speed = -base_speed
            right_wheel_speed = -base_speed
        elif pose == "kiri":  # Corrected left turn
            left_wheel_speed = base_speed * (1 - turn_ratio)
            right_wheel_speed = base_speed
        elif pose == "kanan":  # Corrected right turn
            left_wheel_speed = base_speed
            right_wheel_speed = base_speed * (1 - turn_ratio)
        elif pose == "rotasikanan":  # Corrected right rotation
            left_wheel_speed = base_speed
            right_wheel_speed = -base_speed
        elif pose == "rotasikiri":  # Corrected left rotation
            left_wheel_speed = -base_speed
            right_wheel_speed = base_speed
        else:  # stop
            left_wheel_speed = 0
            right_wheel_speed = 0
        
        # Calculate movement - CORRECTED PHYSICS
        # Linear velocity (average of both wheels)
        linear_velocity = (left_wheel_speed + right_wheel_speed) / 2
        
        # Angular velocity (difference between wheels divided by axle length)
        angular_velocity = (right_wheel_speed - left_wheel_speed) / wheel_distance
        
        # Update robot angle (negative because pygame y-axis is flipped)
        robot_angle -= math.degrees(angular_velocity)
        robot_angle %= 360  # Keep angle within 0-360 degrees
        
        # Update position based on orientation
        robot_x += linear_velocity * math.cos(math.radians(robot_angle))
        robot_y += linear_velocity * math.sin(math.radians(robot_angle))
        
        # Keep robot within screen bounds
        robot_x = max(robot_length/2, min(SIMULATOR_WIDTH - robot_length/2, robot_x))
        robot_y = max(robot_width/2, min(SIMULATOR_HEIGHT - robot_width/2, robot_y))
        
        # Draw everything
        simulator_screen.fill(WHITE)
        
        # Draw grid
        for x in range(0, SIMULATOR_WIDTH, 50):
            pygame.draw.line(simulator_screen, GRAY, (x, 0), (x, SIMULATOR_HEIGHT))
        for y in range(0, SIMULATOR_HEIGHT, 50):
            pygame.draw.line(simulator_screen, GRAY, (0, y), (SIMULATOR_WIDTH, y))
        
        # Draw robot
        draw_robot()
        
        # Display status information
        font = pygame.font.SysFont(None, 36)
        info_texts = [
            f"Pose: {pose}",
            f"Wheels: L={left_wheel_speed:.1f}, R={right_wheel_speed:.1f}",
            f"Angle: {robot_angle:.1f}°",
            f"Position: ({robot_x:.1f}, {robot_y:.1f})"
        ]
        
        for i, text in enumerate(info_texts):
            text_surface = font.render(text, True, BLACK)
            simulator_screen.blit(text_surface, (10, 10 + i * 40))
        
        pygame.display.flip()
        clock.tick(30)  # 30 FPS

try:
    ESP32_IP = socket.gethostbyname(ESP32_HOST)
    print(f"🌐 mDNS {ESP32_HOST} -> {ESP32_IP}")
    
    # Setup koneksi socket ke ESP32
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.settimeout(2)  # Timeout 2 detik untuk koneksi
        client_socket.connect((ESP32_IP, ESP32_PORT))
        esp_connected = True
        print("\u2705 Terhubung ke ESP32!")
    except Exception as e:
        print(f"\u274C Gagal konek ke ESP32: {e}")
        print("\u2139 Simulasi akan tetap berjalan tanpa koneksi ESP32")
        if client_socket:
            client_socket.close()
        client_socket = None
except socket.gaierror:
    print(f"❌ Gagal resolve {ESP32_HOST}. Simulasi akan tetap berjalan tanpa koneksi ESP32")
    client_socket = None

# Load model
model = joblib.load(MODEL_PATH)

# Setup MediaPipe Pose
mp_pose = mp.solutions.pose
pose = mp_pose.Pose()

# Setup kamera
cap = cv2.VideoCapture(0)

# ==================== LOOP UTAMA ====================
def extract_keypoints(results):
    keypoints = []
    if results.pose_landmarks:
        for landmark in results.pose_landmarks.landmark:
            keypoints.extend([landmark.x, landmark.y, landmark.z, landmark.visibility])
    else:
        keypoints = [0] * 132
    return np.array(keypoints)

sim_thread = threading.Thread(target=robot_simulator)
sim_thread.daemon = True  # Jadikan sebagai daemon thread
sim_thread.start()

prev_label = None
try:
    while running:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(image)

        keypoints = extract_keypoints(results)
        X = keypoints.reshape(1, -1)
        label = model.predict(X)[0]

        valid_poses = ["maju", "mundur", "kiri", "kanan", "rotasikanan", "rotasikiri", "stop"]
        if label not in valid_poses:
            label = "stop"

        cv2.putText(frame, f"Pose: {label}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("Pose Detection", frame)

        if label != prev_label:
            with pose_lock:
                current_pose = label
            
            if esp_connected and client_socket:
                try:
                    message = label + "\n"
                    client_socket.sendall(message.encode())
                    print(f"Mengirim ke ESP32: {label}")
                except Exception as e:
                    print(f"Error kirim data: {e}")
                    esp_connected = False
                    if client_socket:
                        client_socket.close()
                    client_socket = None
            
            prev_label = label

        if cv2.waitKey(1) & 0xFF == ord('q'):
            with pose_lock:
                running = False
            break

# ==================== BERSIH-BERSIH ====================
finally:
    cap.release()
    cv2.destroyAllWindows()
    if client_socket:
        client_socket.close()
    with pose_lock:
        running = False
    sim_thread.join()
    pygame.quit()
    print("Program berhenti.")