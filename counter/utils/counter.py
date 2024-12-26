# counter/utils/counter.py
import cv2
import numpy as np
from ultralytics import YOLO
from datetime import datetime
from ..models import PersonCount, Camera
from sort.sort import Sort
import threading
import time
import logging
import torch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoStream:
    def __init__(self, stream_url):
        self.stream_url = stream_url
        self.lock = threading.Lock()
        self.cap = None
        self.last_frame = None
        self.last_read_time = None
        self.is_running = False
        
        # Enable CUDA for OpenCV if available
        self.use_cuda = cv2.cuda.getCudaEnabledDeviceCount() > 0
        if self.use_cuda:
            self.gpu_stream = cv2.cuda_Stream()
            logger.info("CUDA is available for video processing")
        self._connect()

    def _connect(self):
        try:
            with self.lock:
                if self.cap is not None:
                    self.cap.release()
                self.cap = cv2.VideoCapture(self.stream_url)
                if not self.cap.isOpened():
                    raise RuntimeError(f"Failed to open stream: {self.stream_url}")
                # Set buffer size to minimize frame queuing
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.is_running = True
                
                # Enable GPU processing for video capture if available
                if self.use_cuda:
                    self.cap.set(cv2.CAP_PROP_CUDA_DEVICE, 0)
                    
        except Exception as e:
            logger.error(f"Error connecting to stream: {e}")
            self.is_running = False
            raise

    def read(self):
        if not self.is_running:
            return False, None

        with self.lock:
            if self.cap is None:
                return False, None
            try:
                ret, frame = self.cap.read()
                if ret:
                    if self.use_cuda:
                        # Upload frame to GPU memory
                        gpu_frame = cv2.cuda_GpuMat()
                        gpu_frame.upload(frame)
                        # Process frame on GPU
                        gpu_frame = cv2.cuda.cvtColor(gpu_frame, cv2.COLOR_BGR2RGB)
                        # Download back to CPU if needed
                        frame = gpu_frame.download()
                    
                    self.last_frame = frame
                    self.last_read_time = time.time()
                    return True, frame
                else:
                    logger.warning("Failed to read frame, attempting reconnection...")
                    self._connect()
                    return False, None
            except Exception as e:
                logger.error(f"Error reading frame: {e}")
                return False, None

    def release(self):
        with self.lock:
            self.is_running = False
            if self.cap is not None:
                self.cap.release()
                self.cap = None

class PersonCounter:
    def __init__(self):
        # Check for GPU availability
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Using device: {self.device}")
        
        # Initialize YOLO model with GPU support
        self.model = YOLO('yolov8n.pt')
        self.model.to(self.device)  # Move model to GPU
        
        # Configure YOLO for GPU inference
        self.model.conf = 0.25
        self.model.classes = [0]  # person class
        self.model.max_det = 100  # maximum detections per frame
        
        self.person_class_id = 0
        self.tracker = Sort(max_age=20, min_hits=3, iou_threshold=0.25)
        self.unique_ids = set()
        self.colors = {}
        self.lock = threading.Lock()
        
        # Initialize CUDA image processing if available
        self.use_cuda = cv2.cuda.getCudaEnabledDeviceCount() > 0
        if self.use_cuda:
            self.gpu_stream = cv2.cuda_Stream()
            self.gpu_resize = cv2.cuda.resize
            self.gpu_cvtColor = cv2.cuda.cvtColor
            logger.info("CUDA enabled for image processing")

    def _get_color(self, track_id):
        with self.lock:
            if track_id not in self.colors:
                hue = np.random.randint(0, 180)
                self.colors[track_id] = tuple([int(x) for x in cv2.cvtColor(np.uint8([[[hue, 255, 255]]]), cv2.COLOR_HSV2BGR)[0][0]])
            return self.colors[track_id]

    def process_frame(self, frame, camera_id):
        if frame is None:
            return None, 0, 0

        try:
            # Convert frame to GPU tensor if using CUDA
            if self.use_cuda:
                gpu_frame = cv2.cuda_GpuMat()
                gpu_frame.upload(frame)
                
                # Perform GPU-accelerated preprocessing
                gpu_frame = self.gpu_cvtColor(gpu_frame, cv2.COLOR_BGR2RGB)
                frame = gpu_frame.download()

            # Run inference on GPU
            with torch.cuda.amp.autocast():  # Enable automatic mixed precision
                results = self.model(frame, verbose=False)

            # Process detections
            detections = []
            for r in results[0].boxes.data:
                x1, y1, x2, y2, conf, cls = r
                if int(cls) == self.person_class_id:
                    detections.append([x1, y1, x2, y2, conf])

            # Update tracker
            with self.lock:
                if len(detections) > 0:
                    tracked_objects = self.tracker.update(np.array(detections))
                else:
                    tracked_objects = np.empty((0, 5))

            # Create GPU mat for annotated frame if using CUDA
            if self.use_cuda:
                annotated_frame = cv2.cuda_GpuMat()
                annotated_frame.upload(frame.copy())
            else:
                annotated_frame = frame.copy()

            current_ids = set()

            for track in tracked_objects:
                x1, y1, x2, y2, track_id = track
                track_id = int(track_id)
                current_ids.add(track_id)
                
                with self.lock:
                    self.unique_ids.add(track_id)
                
                color = self._get_color(track_id)
                
                # Draw annotations (on CPU as CUDA drawing operations are limited)
                if self.use_cuda:
                    annotated_frame = annotated_frame.download()
                
                cv2.rectangle(
                    annotated_frame,
                    (int(x1), int(y1)),
                    (int(x2), int(y2)),
                    color,
                    2
                )
                
                text = f'ID: {track_id}'
                text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                cv2.rectangle(
                    annotated_frame,
                    (int(x1), int(y1) - text_size[1] - 8),
                    (int(x1) + text_size[0], int(y1)),
                    color,
                    -1
                )
                cv2.putText(
                    annotated_frame,
                    text,
                    (int(x1), int(y1) - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2
                )

                if self.use_cuda:
                    # Re-upload to GPU if needed
                    gpu_annotated = cv2.cuda_GpuMat()
                    gpu_annotated.upload(annotated_frame)
                    annotated_frame = gpu_annotated

            # Get counts
            with self.lock:
                current_count = len(tracked_objects)
                total_unique = len(self.unique_ids)

            # Draw counts (on CPU)
            if self.use_cuda:
                annotated_frame = annotated_frame.download()

            cv2.putText(
                annotated_frame,
                f'Current Count: {current_count}',
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )
            cv2.putText(
                annotated_frame,
                f'Total Unique: {total_unique}',
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )

            # Save count to database
            current_time = datetime.now()
            if current_time.minute % 5 == 0 and current_time.second == 0:
                try:
                    camera = Camera.objects.get(id=camera_id)
                    PersonCount.objects.create(
                        camera=camera,
                        count=current_count,
                        total_count=total_unique,
                        timestamp=current_time
                    )
                except Exception as e:
                    logger.error(f"Error saving to database: {e}")

            return annotated_frame, current_count, total_unique

        except Exception as e:
            logger.error(f"Error in process_frame: {e}")
            return None, 0, 0

class StreamManager:
    def __init__(self):
        self.streams = {}
        self.counter = PersonCounter()
        self.lock = threading.Lock()

    def get_stream(self, camera_id, stream_url):
        with self.lock:
            if camera_id not in self.streams:
                try:
                    stream = VideoStream(stream_url)
                    self.streams[camera_id] = stream
                except Exception as e:
                    logger.error(f"Error creating stream for camera {camera_id}: {e}")
                    return None
            return self.streams[camera_id]

    def release_stream(self, camera_id):
        with self.lock:
            if camera_id in self.streams:
                try:
                    self.streams[camera_id].release()
                    del self.streams[camera_id]
                except Exception as e:
                    logger.error(f"Error releasing stream for camera {camera_id}: {e}")

    def get_frame(self, camera_id, stream_url):
        stream = self.get_stream(camera_id, stream_url)
        if stream is None:
            return None, 0, 0

        try:
            ret, frame = stream.read()
            if not ret:
                self.release_stream(camera_id)
                return None, 0, 0

            processed_frame, current_count, total_count = self.counter.process_frame(frame, camera_id)
            
            if processed_frame is not None:
                try:
                    _, buffer = cv2.imencode('.jpg', processed_frame)
                    return buffer.tobytes(), current_count, total_count
                except Exception as e:
                    logger.error(f"Error encoding frame: {e}")
            
            return None, 0, 0
            
        except Exception as e:
            logger.error(f"Error in get_frame: {e}")
            return None, 0, 0