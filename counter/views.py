# counter/views.py
from django.shortcuts import render, get_object_or_404
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum
from django.core.files import File
import cv2
import numpy as np
import time
from datetime import datetime, timedelta
import json
import logging
from .utils.counter import StreamManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize StreamManager
stream_manager = StreamManager()

# Define branch configuration
BRANCH_DICT = {
    "DHA Rahbar": [
        "rtsp://admin:Admin@Zone1@172.24.0.14:554/Streaming/Channels/101?fflags=nobuffer",
        "rtsp://admin:Admin@Zone1@172.24.0.16:554/Streaming/Channels/102?fflags=nobuffer",
        "rtsp://admin:Admin@Zone1@172.24.0.17:554/Streaming/Channels/103?fflags=nobuffer",
        "rtsp://admin:gourmet@123@10.10.20.20:554/Streaming/Channels/104?fflags=nobuffer",
    ],
    "Ali Town": [
        "rtsp://admin:gourmet@123@10.10.20.20:554/Streaming/Channels/101?fflags=nobuffer",
        "rtsp://admin:gourmet@123@10.10.20.20:554/Streaming/Channels/102?fflags=nobuffer",
    ],
    "Sabzazar": [
        "rtsp://admin:gourmet@123@10.10.20.20:554/Streaming/Channels/101?fflags=nobuffer",
        "rtsp://admin:gourmet@123@10.10.20.20:554/Streaming/Channels/102?fflags=nobuffer",
        "rtsp://admin:gourmet@123@10.10.20.20:554/Streaming/Channels/103?fflags=nobuffer",
    ],
}

def dashboard(request):
    """
    Main dashboard view showing branch and camera selection
    """
    try:
        context = {
            'branches': BRANCH_DICT.items(),
            'branch_dict': json.dumps(BRANCH_DICT),
        }
        return render(request, 'counter/dashboard.html', context)
    except Exception as e:
        logger.error(f"Error in dashboard view: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)

def video_feed(request):
    """
    Generate video feed with person detection and tracking
    """
    stream_url = request.GET.get('url')
    if not stream_url:
        return JsonResponse({'error': 'No URL provided'}, status=400)

    def generate_frames():
        camera_id = f"camera_{hash(stream_url)}"
        frame_timeout = 10
        last_frame_time = time.time()  # Now this will work correctly

        try:
            while True:
                try:
                    frame_bytes, current_count, total_count = stream_manager.get_frame(camera_id, stream_url)
                    
                    if frame_bytes is not None:
                        last_frame_time = time.time()
                        yield (b'--frame\r\n'
                              b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    else:
                        # Check for timeout
                        if time.time() - last_frame_time > frame_timeout:
                            logger.warning(f"Stream timeout for camera {camera_id}")
                            stream_manager.release_stream(camera_id)
                            break
                        time.sleep(0.1)  # Prevent busy waiting

                except Exception as e:
                    logger.error(f"Error in generate_frames: {e}")
                    time.sleep(1)  # Prevent rapid retries on error
                    continue

        finally:
            # Ensure stream is released when the generator exits
            stream_manager.release_stream(camera_id)

    return StreamingHttpResponse(
        generate_frames(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )
@csrf_exempt
def get_camera_stats(request):
    """
    Get real-time statistics for a camera
    """
    stream_url = request.GET.get('url')
    if not stream_url:
        return JsonResponse({'error': 'No URL provided'}, status=400)
    
    try:
        camera_id = f"camera_{hash(stream_url)}"
        _, current_count, total_count = stream_manager.get_frame(camera_id, stream_url)
        
        return JsonResponse({
            'count': current_count,
            'total': total_count,
            'timestamp': timezone.now().isoformat(),
            'status': 'success'
        })
    except Exception as e:
        logger.error(f"Error getting camera stats: {e}")
        return JsonResponse({
            'error': str(e),
            'status': 'error'
        }, status=500)

def stream_view(request):
    """
    View for displaying a single camera stream
    """
    stream_url = request.GET.get('url')
    branch_name = request.GET.get('branch')
    camera_number = request.GET.get('camera', '1')
    
    if not stream_url or not branch_name:
        return JsonResponse({'error': 'URL and branch name required'}, status=400)
    
    try:
        context = {
            'stream_url': stream_url,
            'branch_name': branch_name,
            'camera_number': camera_number
        }
        return render(request, 'counter/stream.html', context)
    except Exception as e:
        logger.error(f"Error in stream view: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)

@csrf_exempt
def update_stats(request):
    """
    Update statistics for a camera
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        data = json.loads(request.body)
        stream_url = data.get('url')
        count = data.get('count')
        
        if not stream_url or count is None:
            return JsonResponse({'error': 'URL and count required'}, status=400)
        
        # Store the stats (implement according to your needs)
        return JsonResponse({
            'status': 'success',
            'timestamp': timezone.now().isoformat()
        })
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request: {e}")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Error updating stats: {e}")
        return JsonResponse({'error': str(e)}, status=500)

def get_stream_url_info(request):
    """
    Get information about a stream URL
    """
    url = request.GET.get('url')
    if not url:
        return JsonResponse({'error': 'URL required'}, status=400)
    
    try:
        # Find branch and camera number for this URL
        for branch_name, urls in BRANCH_DICT.items():
            if url in urls:
                camera_number = urls.index(url) + 1
                return JsonResponse({
                    'branch': branch_name,
                    'camera_number': camera_number,
                    'url': url,
                    'status': 'success'
                })
        
        return JsonResponse({
            'error': 'URL not found',
            'status': 'error'
        }, status=404)
    except Exception as e:
        logger.error(f"Error getting stream URL info: {e}")
        return JsonResponse({'error': str(e)}, status=500)

def check_stream_status(request):
    """
    Check if a stream is accessible
    """
    url = request.GET.get('url')
    if not url:
        return JsonResponse({'error': 'URL required'}, status=400)
    
    try:
        camera_id = f"camera_{hash(url)}"
        stream = stream_manager.get_stream(camera_id, url)
        
        if stream is None:
            return JsonResponse({
                'status': 'offline',
                'url': url
            })
            
        return JsonResponse({
            'status': 'online',
            'url': url
        })
    except Exception as e:
        logger.error(f"Error checking stream status: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'url': url
        })