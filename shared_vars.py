import threading

current_pose = "stop"
running = True
pose_lock = threading.Lock()

