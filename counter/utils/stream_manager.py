# counter/utils/stream_manager.py
import cv2
import threading
import time
from datetime import datetime
from ..models import Camera, PersonCount
from .counter import PersonCounter

class StreamManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(StreamManager, cls).__new__(cls)
                cls._instance.initialize()
            return cls._instance

    def initialize(self):
        self.streams = {}
        self.frame_buffers = {}
        self.person_counter = PersonCounter()
        self.active_threads = {}

    def start_stream(self, camera_id):
        if camera_id not in self.active_threads:
            thread = threading.Thread(target=self._process_stream, args=(camera_id,))
            thread.daemon = True
            self.active_threads[camera_id] = thread
            thread.start()

    def stop_stream(self, camera_id):
        if camera_id in self.streams:
            self.streams[camera_id].release()
            del self.streams[camera_id]
            if camera_id in self.frame_buffers:
                del self.frame_buffers[camera_id]
            if camera_id in self.active_threads:
                del self.active_threads[camera_id]

    def get_frame(self, camera_id):
        if camera_id not in self.frame_buffers:
            self.start_stream(camera_id)
            time.sleep(0.1)  # Give time for the first frame
        
        return self.frame_buffers.get(camera_id, (None, 0))

    def _process_stream(self, camera_id):
        try:
            camera = Camera.objects.get(id=camera_id)
            cap = cv2.VideoCapture(camera.stream_url)
            
            if not cap.isOpened():
                print(f"Error: Could not open stream for camera {camera_id}")
                return

            self.streams[camera_id] = cap
            last_save_time = time.time()
            
            while camera_id in self.active_threads:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue

                # Process frame and count people
                processed_frame, count = self.person_counter.process_frame(frame, camera_id)
                
                if processed_frame is not None:
                    _, buffer = cv2.imencode('.jpg', processed_frame)
                    self.frame_buffers[camera_id] = (buffer.tobytes(), count)

                # Save count to database every 5 minutes
                current_time = time.time()
                if current_time - last_save_time >= 300:  # 300 seconds = 5 minutes
                    PersonCount.objects.create(
                        camera=camera,
                        count=count,
                        timestamp=datetime.now()
                    )
                    last_save_time = current_time

                time.sleep(0.033)  # ~30 FPS

        except Camera.DoesNotExist:
            print(f"Error: Camera {camera_id} does not exist")
        except Exception as e:
            print(f"Error processing stream for camera {camera_id}: {str(e)}")
        finally:
            self.stop_stream(camera_id)

    def cleanup(self):
        for camera_id in list(self.streams.keys()):
            self.stop_stream(camera_id)