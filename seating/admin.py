from django.contrib import admin
from .models import Branch, Room, Student, Exam, ExamRoom, SeatAllocation

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'created_at')
    search_fields = ('name', 'code')
    ordering = ('name',)

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'capacity', 'rows', 'columns', 'is_active')
    search_fields = ('name',)
    list_filter = ('is_active',)
    ordering = ('name',)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('roll_number', 'name', 'branch', 'needs_accommodation')
    search_fields = ('roll_number', 'name')
    list_filter = ('branch', 'needs_accommodation')
    ordering = ('roll_number',)

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'start_time', 'end_time', 'created_by')
    search_fields = ('name',)
    list_filter = ('date', 'created_by')
    ordering = ('-date', 'start_time')

@admin.register(ExamRoom)
class ExamRoomAdmin(admin.ModelAdmin):
    list_display = ('exam', 'room', 'invigilator')
    search_fields = ('exam__name', 'room__name', 'invigilator__username')
    list_filter = ('exam', 'room')
    ordering = ('exam', 'room')

@admin.register(SeatAllocation)
class SeatAllocationAdmin(admin.ModelAdmin):
    list_display = ('exam_room', 'student', 'row', 'column')
    search_fields = ('student__roll_number', 'student__name', 'exam_room__exam__name')
    list_filter = ('exam_room__exam', 'exam_room__room')
    ordering = ('exam_room', 'row', 'column')
