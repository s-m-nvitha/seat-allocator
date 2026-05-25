from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('rooms/', views.room_list, name='room_list'),
    path('rooms/create/', views.room_create, name='room_create'),
    path('students/upload/', views.student_upload, name='student_upload'),
    path('exams/', views.exam_list, name='exam_list'),
    path('exams/create/', views.exam_create, name='exam_create'),
    path('exams/<int:exam_id>/allocate/', views.allocate_seats_view, name='allocate_seats'),
    path('exams/<int:exam_id>/', views.exam_detail, name='exam_detail'),
    path('api/rooms/<int:room_id>/layout/', views.get_room_layout, name='room_layout'),
    path('exam/<int:exam_id>/export/excel/', views.export_excel, name='export_excel'),
] 