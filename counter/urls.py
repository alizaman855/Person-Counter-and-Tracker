from django.urls import path
from . import views

app_name = 'counter'

urlpatterns = [
    # Main views
    path('', views.dashboard, name='dashboard'),
    path('stream/', views.stream_view, name='stream_view'),
    
    # Video and stats endpoints
    path('video-feed/', views.video_feed, name='video_feed'),
    path('camera-stats/', views.get_camera_stats, name='camera_stats'),
    path('update-stats/', views.update_stats, name='update_stats'),
    
    # Utility endpoints
    path('stream-info/', views.get_stream_url_info, name='stream_info'),
    path('check-status/', views.check_stream_status, name='check_status'),
]