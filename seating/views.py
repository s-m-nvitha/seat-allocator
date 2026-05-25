from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.core.exceptions import ValidationError
import pandas as pd
import json
from datetime import datetime
from fpdf import FPDF
import io
import xlsxwriter
from .models import Branch, Room, Student, Exam, ExamRoom, SeatAllocation
from .forms import (
    BranchForm, RoomForm, StudentForm, ExamForm, 
    ExamRoomForm, StudentUploadForm, SeatAllocationConfigForm
)
from .utils.allocation import allocate_seats

@login_required
def dashboard(request):
    context = {
        'total_students': Student.objects.count(),
        'total_rooms': Room.objects.filter(is_active=True).count(),
        'total_exams': Exam.objects.count(),
        'recent_exams': Exam.objects.order_by('-date')[:5]
    }
    return render(request, 'seating/dashboard.html', context)

@login_required
def room_list(request):
    rooms = Room.objects.all()
    return render(request, 'seating/room_list.html', {'rooms': rooms})

@login_required
def room_create(request):
    if request.method == 'POST':
        form = RoomForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Room created successfully.')
            return redirect('room_list')
    else:
        form = RoomForm()
    return render(request, 'seating/room_form.html', {'form': form})


@login_required
def exam_list(request):
    """List all exams with basic details."""
    exams = Exam.objects.all().order_by('-date', '-id')
    return render(request, 'seating/exam_list.html', {'exams': exams})

@login_required
def student_upload(request):
    if request.method == 'POST':
        form = StudentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                file = request.FILES['file']
                selected_branch = form.cleaned_data.get('branch')
                
                if file.name.endswith('.csv'):
                    df = pd.read_csv(file)
                else:  # Excel file
                    df = pd.read_excel(file)

                # Normalise column names so "branch code" -> "branch_code", etc.
                df.columns = [
                    str(col).strip().lower().replace(' ', '_')
                    for col in df.columns
                ]
                
                # Keep track of successes and failures
                created_count = 0
                updated_count = 0
                error_count = 0
                error_messages = []
                
                for _, row in df.iterrows():
                    try:
                        # Determine branch for this row
                        if selected_branch:
                            branch = selected_branch
                        else:
                            branch_code = row.get('branch_code')
                            if not branch_code:
                                raise ValueError("branch_code is required when no branch is selected in the form.")
                            branch, _ = Branch.objects.get_or_create(
                                code=str(branch_code).strip(),
                                defaults={'name': str(branch_code).strip()}
                            )

                        # Try to get existing student or create new one
                        student, created = Student.objects.get_or_create(
                            roll_number=row['roll_number'],
                            defaults={
                                'name': row['name'],
                                'branch': branch,
                                'needs_accommodation': row.get('needs_accommodation', False),
                                'accommodation_details': row.get('accommodation_details', '')
                            }
                        )
                        
                        if not created:
                            # Update existing student
                            student.name = row['name']
                            student.branch = branch
                            student.needs_accommodation = row.get('needs_accommodation', False)
                            student.accommodation_details = row.get('accommodation_details', '')
                            student.save()
                            updated_count += 1
                        else:
                            created_count += 1
                            
                    except Exception as e:
                        error_count += 1
                        roll = row.get('roll_number', 'unknown')
                        error_messages.append(f"Error with roll number {roll}: {str(e)}")
                
                # Prepare success message
                success_msg = []
                if created_count > 0:
                    success_msg.append(f"{created_count} students created")
                if updated_count > 0:
                    success_msg.append(f"{updated_count} students updated")
                
                if success_msg:
                    messages.success(request, ', '.join(success_msg) + '.')
                
                # Show errors if any
                if error_count > 0:
                    messages.warning(request, f"{error_count} errors occurred during upload.")
                    for error in error_messages[:5]:  # Show first 5 errors
                        messages.error(request, error)
                
                return redirect('dashboard')
                
            except Exception as e:
                messages.error(request, f'Error uploading students: {str(e)}')
    else:
        form = StudentUploadForm()
    return render(request, 'seating/student_upload.html', {'form': form})

@login_required
def exam_create(request):
    if request.method == 'POST':
        form = ExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.created_by = request.user
            exam.save()
            messages.success(request, 'Exam created successfully.')
            return redirect('exam_list')
    else:
        form = ExamForm()
    return render(request, 'seating/exam_form.html', {'form': form})

@login_required
def allocate_seats_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    
    if request.method == 'POST':
        form = SeatAllocationConfigForm(request.POST)
        if form.is_valid():
            try:
                branches = form.cleaned_data['branches']
                gap_columns = form.cleaned_data['gap_columns']
                auto_select_rooms = form.cleaned_data.get('auto_select_rooms')
                max_branches_per_room = form.cleaned_data.get('max_branches_per_room', 3)

                # Get all students for selected branches
                all_students = list(
                    Student.objects.filter(branch__in=branches)
                    .select_related('branch')
                    .order_by('branch__code', 'roll_number')
                )

                if not all_students:
                    raise ValidationError("No students found for the selected branches.")

                # Build per-branch student lists
                branch_students = {}
                for s in all_students:
                    branch_students.setdefault(s.branch_id, []).append(s)
                
                # Decide which rooms to use
                if auto_select_rooms:
                    # Calculate minimum rooms needed
                    all_rooms = Room.objects.filter(is_active=True).order_by('-capacity')
                    rooms = calculate_minimum_rooms_needed(all_rooms, all_students, gap_columns)
                else:
                    rooms = form.cleaned_data['rooms']
                    if not rooms:
                        raise ValidationError("Please select at least one room or enable automatic room selection.")
                
                # Create ExamRoom objects
                exam_rooms = []
                for room in rooms:
                    exam_room, created = ExamRoom.objects.get_or_create(exam=exam, room=room)
                    exam_rooms.append(exam_room)
                
                # Clear existing allocations
                for exam_room in exam_rooms:
                    exam_room.seatallocation_set.all().delete()
                
                # GLOBAL OPTIMIZATION: Treat all rooms as single pool
                global_student_allocation(
                    exam_rooms, 
                    branch_students, 
                    gap_columns, 
                    max_branches_per_room
                )
                
                messages.success(request, 'Seating allocated successfully.')
                return redirect('exam_detail', exam_id=exam.id)
            except Exception as e:
                messages.error(request, f'Error allocating seats: {str(e)}')
    else:
        form = SeatAllocationConfigForm(initial={'exam': exam})
    
    return render(request, 'seating/allocate_seats.html', {
        'form': form,
        'exam': exam
    })

@login_required
def exam_detail(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    exam_rooms = exam.examroom_set.all()
    
    # Group allocations by room for easier rendering
    room_allocations = {}
    for exam_room in exam_rooms:
        allocations = exam_room.seatallocation_set.all()
        room_allocations[exam_room.room.name] = {
            'room': exam_room.room,
            'allocations': allocations,
            'invigilator': exam_room.invigilator
        }
    
    return render(request, 'seating/exam_detail.html', {
        'exam': exam,
        'room_allocations': room_allocations
    })

@login_required
def get_room_layout(request, room_id):
    """API endpoint to get room layout with allocations."""
    room = get_object_or_404(Room, id=room_id)
    exam_id = request.GET.get('exam_id')
    
    if exam_id:
        exam_room = get_object_or_404(ExamRoom, exam_id=exam_id, room=room)
        allocations = exam_room.seatallocation_set.select_related('student', 'student__branch')
        
        # Convert allocations to grid format
        grid = [[None for _ in range(room.columns)] for _ in range(room.rows)]
        for allocation in allocations:
            grid[allocation.row][allocation.column] = {
                'student_name': allocation.student.name,
                'roll_number': allocation.student.roll_number,
                'branch': allocation.student.branch.code,
                'needs_accommodation': allocation.student.needs_accommodation
            }
    else:
        grid = [[None for _ in range(room.columns)] for _ in range(room.rows)]
    
    return JsonResponse({
        'rows': room.rows,
        'columns': room.columns,
        'grid': grid
    })

@login_required
def export_excel(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    exam_rooms = exam.examroom_set.all()
    
    # Create Excel file in memory
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    
    # Add formats
    header_format = workbook.add_format({
        'bold': True,
        'align': 'center',
        'bg_color': '#4361ee',
        'font_color': 'white'
    })
    
    cell_format = workbook.add_format({
        'align': 'center',
        'valign': 'vcenter'
    })
    
    special_format = workbook.add_format({
        'align': 'center',
        'valign': 'vcenter',
        'bg_color': '#ef476f',
        'font_color': 'white'
    })
    
    # Create overview sheet
    overview = workbook.add_worksheet('Overview')
    overview.write(0, 0, 'Exam Name:', header_format)
    overview.write(0, 1, exam.name)
    overview.write(1, 0, 'Date:', header_format)
    overview.write(1, 1, exam.date.strftime('%Y-%m-%d'))
    overview.write(2, 0, 'Time:', header_format)
    overview.write(2, 1, f'{exam.start_time} - {exam.end_time}')
    
    # Create room-wise sheets
    for exam_room in exam_rooms:
        sheet = workbook.add_worksheet(exam_room.room.name)
        
        # Write room details
        sheet.merge_range(0, 0, 0, 4, f'Room: {exam_room.room.name}', header_format)
        if exam_room.invigilator:
            sheet.merge_range(1, 0, 1, 4, f'Invigilator: {exam_room.invigilator.get_full_name()}', cell_format)
        
        # Write headers
        headers = ['Seat', 'Roll Number', 'Name', 'Branch', 'Special Needs']
        for col, header in enumerate(headers):
            sheet.write(3, col, header, header_format)
        
        # Write data
        allocations = exam_room.seatallocation_set.all().order_by('row', 'column')
        for row_idx, allocation in enumerate(allocations, start=4):
            fmt = special_format if allocation.student.needs_accommodation else cell_format
            sheet.write(row_idx, 0, f'({allocation.row + 1}, {allocation.column + 1})', fmt)
            sheet.write(row_idx, 1, allocation.student.roll_number, fmt)
            sheet.write(row_idx, 2, allocation.student.name, fmt)
            sheet.write(row_idx, 3, allocation.student.branch.code, fmt)
            sheet.write(row_idx, 4, 'Yes' if allocation.student.needs_accommodation else 'No', fmt)
        
        # Adjust column widths
        sheet.set_column(0, 0, 15)  # Seat
        sheet.set_column(1, 1, 15)  # Roll Number
        sheet.set_column(2, 2, 30)  # Name
        sheet.set_column(3, 3, 10)  # Branch
        sheet.set_column(4, 4, 15)  # Special Needs
    
    workbook.close()
    
    # Generate response
    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="seating_arrangement_{exam_id}.xlsx"'
    
    return response

def calculate_minimum_rooms_needed(all_rooms, all_students, gap_columns):
    """
    Calculate the minimum number of rooms needed to seat all students efficiently.
    Use larger rooms first to minimize the number of rooms used.
    """
    total_students = len(all_students)
    rooms_needed = []
    remaining_students = total_students
    
    # Sort rooms by effective capacity (largest first) to minimize room count
    rooms_with_capacity = []
    for room in all_rooms:
        effective_columns = (room.columns + 1) // 2 if gap_columns else room.columns
        effective_capacity = room.rows * effective_columns
        if effective_capacity > 0:
            rooms_with_capacity.append((room, effective_capacity))
    
    # Sort by capacity descending to use largest rooms first
    rooms_with_capacity.sort(key=lambda x: x[1], reverse=True)
    
    for room, effective_capacity in rooms_with_capacity:
        if remaining_students <= 0:
            break
        
        rooms_needed.append(room)
        remaining_students -= effective_capacity
    
    if remaining_students > 0:
        raise ValidationError(
            f"Not enough room capacity. {remaining_students} students cannot be accommodated."
        )
            
    return rooms_needed

def global_student_allocation(exam_rooms, branch_students, gap_columns, max_branches_per_room):
    """
    MULTI-BRANCH GLOBAL OPTIMIZATION - All 12 Rules Implementation
    
    PRIORITY ORDER:
    (1) No empty seats across all rooms
    (2) Only two branches per room
    (3) Column purity
    (4) Alternating columns
    (5) Balanced usage of all branches
    """
    if not exam_rooms or not branch_students:
        return
    
    # RULE 1: GLOBAL POOL - Treat ALL students from ALL branches as single pool
    all_students = []
    for branch_id, students in branch_students.items():
        all_students.extend(students)
    
    # PRE-CHECK: Count students vs seats
    total_students = len(all_students)
    total_capacity = 0
    room_info = []
    
    for exam_room in exam_rooms:
        room = exam_room.room
        effective_columns = (room.columns + 1) // 2 if gap_columns else room.columns
        effective_capacity = room.rows * effective_columns
        total_capacity += effective_capacity
        
        room_info.append({
            'exam_room': exam_room,
            'room': room,
            'effective_columns': effective_columns,
            'effective_capacity': effective_capacity
        })
    
    # Ensure: students ≤ seats
    if total_students > total_capacity:
        raise ValueError(f"Not enough capacity: {total_students} students > {total_capacity} seats")
    
    # Create mutable copy of branch students for dynamic allocation
    remaining_branch_students = {}
    for branch_id, students in branch_students.items():
        remaining_branch_students[branch_id] = students[:]
    
    # RULE 2-10: MULTI-BRANCH ROOM FORMATION AND ALLOCATION
    multi_branch_room_allocation(
        room_info, remaining_branch_students, gap_columns, max_branches_per_room
    )

def multi_branch_room_allocation(room_info, remaining_branch_students, gap_columns, max_branches_per_room):
    """
    Allocate rooms with dynamic branch selection for each room
    """
    total_allocated = 0
    
    for room_data in room_info:
        exam_room = room_data['exam_room']
        room = room_data['room']
        effective_columns = room_data['effective_columns']
        effective_capacity = room_data['effective_capacity']
        
        # RULE 3: ROOM FORMATION LOGIC - Pick ANY TWO branches with highest remaining students
        available_branches = {
            branch_id: students for branch_id, students in remaining_branch_students.items()
            if students  # Only branches with remaining students
        }
        
        if len(available_branches) == 0:
            break  # No students left
        
        if len(available_branches) == 1:
            # Only one branch left
            branch_ids = list(available_branches.keys())
            primary_branch_id = branch_ids[0]
            secondary_branch_id = None
        else:
            # Sort branches by remaining students (highest first)
            sorted_branches = sorted(
                available_branches.items(), 
                key=lambda x: len(x[1]), 
                reverse=True
            )
            primary_branch_id = sorted_branches[0][0]
            secondary_branch_id = sorted_branches[1][0]
        
        # Calculate how many students this room should take
        remaining_total = sum(len(students) for students in available_branches.values())
        remaining_rooms = len(room_info) - room_info.index(room_data)
        
        if remaining_rooms == 1:
            # Last room gets all remaining students
            students_for_room = min(remaining_total, effective_capacity)
        else:
            # Even distribution across remaining rooms
            avg_per_room = remaining_total // remaining_rooms
            students_for_room = min(avg_per_room, effective_capacity)
        
        # RULE 9: COLUMN DISTRIBUTION - Assign columns proportionally
        primary_students = remaining_branch_students[primary_branch_id]
        secondary_students = remaining_branch_students.get(secondary_branch_id, [])
        
        primary_cols = effective_columns // 2 + (effective_columns % 2)  # Gets extra column if odd
        secondary_cols = effective_columns // 2
        
        # Calculate how many students from each branch for this room
        primary_needed = min(primary_cols * room.rows, len(primary_students))
        secondary_needed = min(secondary_cols * room.rows, len(secondary_students))
        
        # Adjust to fill room completely
        total_needed = primary_needed + secondary_needed
        if total_needed < students_for_room:
            # Need more students - take from branch with more available
            if len(primary_students) >= len(secondary_students):
                additional_primary = min(students_for_room - total_needed, len(primary_students) - primary_needed)
                primary_needed += additional_primary
            else:
                additional_secondary = min(students_for_room - total_needed, len(secondary_students) - secondary_needed)
                secondary_needed += additional_secondary
        
        # Get students for this room
        room_primary = primary_students[:primary_needed]
        room_secondary = secondary_students[:secondary_needed]
        room_students = room_primary + room_secondary
        
        # Update remaining students
        remaining_branch_students[primary_branch_id] = primary_students[primary_needed:]
        if secondary_branch_id:
            remaining_branch_students[secondary_branch_id] = secondary_students[secondary_needed:]
        
        # Allocate this room with strict column rules
        allocate_room_with_two_branches(
            exam_room, room, room_students,
            primary_branch_id, secondary_branch_id, gap_columns
        )
        
        total_allocated += len(room_students)
        
        # RULE 10: LEFTOVER HANDLING - Continue to next room with re-evaluated branches
        print(f"Room {room.name} allocated: {primary_branch_id} ({primary_needed}), {secondary_branch_id} ({secondary_needed})")
    
    # RULE 7: FULL UTILIZATION - Global redistribution for any remaining students
    final_redistribution(room_info, remaining_branch_students, gap_columns)
    
    print(f"Total students allocated across all rooms: {total_allocated}")

def allocate_room_with_two_branches(exam_room, room, room_students, 
                                  primary_branch_id, secondary_branch_id, gap_columns):
    """
    Allocate a room with exactly two branches using strict column rules
    """
    # Group students by branch
    branch_students = {primary_branch_id: [], secondary_branch_id: []}
    for student in room_students:
        if student.branch.id == primary_branch_id:
            branch_students[primary_branch_id].append(student)
        elif secondary_branch_id and student.branch.id == secondary_branch_id:
            branch_students[secondary_branch_id].append(student)
    
    # Get available columns
    usable_cols = list(range(0, room.columns, 2)) if gap_columns else list(range(room.columns))
    
    # RULE 5: Strict alternating pattern between the two selected branches
    col_idx = 0
    for col in usable_cols:
        # RULE 4: Each column = ONLY ONE branch
        if col_idx % 2 == 0:
            # Even column: Primary branch
            current_branch_id = primary_branch_id
        else:
            # Odd column: Secondary branch
            current_branch_id = secondary_branch_id
        
        if current_branch_id is None:
            continue  # No secondary branch
        
        students_in_branch = branch_students.get(current_branch_id, [])
        
        # RULE 6: Fill column-wise (top to bottom)
        for row in range(room.rows):
            if not students_in_branch:
                break  # No more students from this branch
            
            student = students_in_branch.pop(0)
            allocation = SeatAllocation(
                exam_room=exam_room,
                student=student,
                row=row,
                column=col
            )
            allocation.save()
        
        col_idx += 1

def final_redistribution(room_info, remaining_branch_students, gap_columns):
    """
    RULE 7: Full utilization - redistribute any remaining students to fill empty seats
    """
    # Collect all remaining students
    all_remaining = []
    for branch_id, students in remaining_branch_students.items():
        all_remaining.extend(students)
    
    if not all_remaining:
        return  # No students left to redistribute
    
    # Find empty seats across all rooms
    student_idx = 0
    for room_data in room_info:
        exam_room = room_data['exam_room']
        room = room_data['room']
        effective_capacity = room_data['effective_capacity']
        
        # Check current usage
        current_usage = SeatAllocation.objects.filter(exam_room=exam_room).count()
        available_space = effective_capacity - current_usage
        
        if available_space > 0 and student_idx < len(all_remaining):
            # Fill empty seats with remaining students
            students_to_add = all_remaining[student_idx:student_idx + available_space]
            student_idx += available_space
            
            # Allocate remaining students (may break branch rules for full utilization)
            allocate_remaining_anywhere(exam_room, room, students_to_add, gap_columns)
        
        if student_idx >= len(all_remaining):
            break

def allocate_remaining_anywhere(exam_room, room, students, gap_columns):
    """
    Allocate remaining students in any available seats (full utilization priority)
    """
    usable_cols = list(range(0, room.columns, 2)) if gap_columns else list(range(room.columns))
    student_idx = 0
    
    for row in range(room.rows):
        for col in usable_cols:
            if student_idx >= len(students):
                return
            
            # Check if seat is already taken
            if not SeatAllocation.objects.filter(exam_room=exam_room, row=row, column=col).exists():
                allocation = SeatAllocation(
                    exam_room=exam_room,
                    student=students[student_idx],
                    row=row,
                    column=col
                )
                allocation.save()
                student_idx += 1

def strict_global_allocation(room_info, primary_students, secondary_students, 
                         primary_branch_id, secondary_branch_id, gap_columns, max_branches_per_room):
    """
    Strict allocation following all rules exactly
    """
    students_allocated = 0
    total_primary = len(primary_students)
    total_secondary = len(secondary_students)
    
    for room_data in room_info:
        exam_room = room_data['exam_room']
        room = room_data['room']
        effective_columns = room_data['effective_columns']
        effective_capacity = room_data['effective_capacity']
        
        # RULE 8: Calculate column distribution proportionally
        remaining_primary = total_primary - students_allocated
        remaining_secondary = total_secondary - students_allocated
        total_remaining = remaining_primary + remaining_secondary
        
        if total_remaining == 0:
            break
        
        # Calculate how many students this room should get
        remaining_rooms = len(room_info) - room_info.index(room_data)
        if remaining_rooms == 1:
            # Last room gets all remaining students
            students_for_room = min(total_remaining, effective_capacity)
        else:
            # Even distribution
            avg_per_room = total_remaining // remaining_rooms
            students_for_room = min(avg_per_room, effective_capacity)
        
        # Calculate column distribution for this room
        primary_cols = effective_columns // 2 + (effective_columns % 2)  # Gets extra column if odd
        secondary_cols = effective_columns // 2
        
        # Calculate how many students from each branch for this room
        primary_needed = min(primary_cols * room.rows, remaining_primary)
        secondary_needed = min(secondary_cols * room.rows, remaining_secondary)
        
        # Adjust if we need more students to fill room
        total_needed = primary_needed + secondary_needed
        if total_needed < students_for_room:
            # Need more students - take from available branch
            if remaining_primary >= remaining_secondary:
                # Primary has more, take more from primary
                additional_primary = min(students_for_room - total_needed, remaining_primary - primary_needed)
                primary_needed += additional_primary
            else:
                # Secondary has more, take more from secondary
                additional_secondary = min(students_for_room - total_needed, remaining_secondary - secondary_needed)
                secondary_needed += additional_secondary
        
        # Get students for this room
        room_primary = primary_students[:primary_needed]
        room_secondary = secondary_students[:secondary_needed]
        room_students = room_primary + room_secondary
        
        # Update student pools
        primary_students = primary_students[primary_needed:]
        secondary_students = secondary_students[secondary_needed:]
        
        # RULE 3-7: Allocate with strict column rules
        allocate_with_strict_columns(
            exam_room, room, room_students, 
            primary_branch_id, secondary_branch_id, gap_columns
        )
        
        students_allocated += primary_needed + secondary_needed
    
    # RULE 6: FULL UTILIZATION RULE - Global redistribution
    global_redistribution_strict(
        room_info, primary_students + secondary_students, gap_columns, max_branches_per_room
    )

def allocate_with_strict_columns(exam_room, room, room_students, 
                              primary_branch_id, secondary_branch_id, gap_columns):
    """
    Allocate with strict column rules: single branch per column, alternating pattern
    """
    # Group students by branch
    branch_students = {primary_branch_id: [], secondary_branch_id: []}
    for student in room_students:
        if student.branch.id == primary_branch_id:
            branch_students[primary_branch_id].append(student)
        elif secondary_branch_id and student.branch.id == secondary_branch_id:
            branch_students[secondary_branch_id].append(student)
    
    # Get available columns
    usable_cols = list(range(0, room.columns, 2)) if gap_columns else list(range(room.columns))
    
    # RULE 4: Strict alternating pattern
    col_idx = 0
    for col in usable_cols:
        # RULE 3: Each column = ONLY ONE branch
        if col_idx % 2 == 0:
            # Even column: Primary branch
            current_branch_id = primary_branch_id
        else:
            # Odd column: Secondary branch
            current_branch_id = secondary_branch_id
        
        if current_branch_id is None:
            continue  # No secondary branch
        
        students_in_branch = branch_students.get(current_branch_id, [])
        
        # RULE 5: Fill column-wise (top to bottom)
        for row in range(room.rows):
            if not students_in_branch:
                break  # No more students from this branch
            
            student = students_in_branch.pop(0)
            allocation = SeatAllocation(
                exam_room=exam_room,
                student=student,
                row=row,
                column=col
            )
            allocation.save()
        
        col_idx += 1

def global_redistribution_strict(room_info, remaining_students, gap_columns, max_branches_per_room):
    """
    RULE 6: Full utilization - move students to fill empty seats
    """
    if not remaining_students:
        return  # No students left to redistribute
    
    # Find empty seats across all rooms
    for room_data in room_info:
        exam_room = room_data['exam_room']
        room = room_data['room']
        effective_capacity = room_data['effective_capacity']
        
        # Check current usage
        current_usage = SeatAllocation.objects.filter(exam_room=exam_room).count()
        available_space = effective_capacity - current_usage
        
        if available_space > 0 and remaining_students:
            # Fill empty seats with remaining students
            students_to_add = remaining_students[:available_space]
            remaining_students = remaining_students[available_space:]
            
            # Allocate remaining students (may break strict rules for full utilization)
            allocate_remaining_students(exam_room, room, students_to_add, gap_columns)
        
        if not remaining_students:
            break

def allocate_remaining_students(exam_room, room, students, gap_columns):
    """
    Allocate remaining students in any available seats (full utilization priority)
    """
    usable_cols = list(range(0, room.columns, 2)) if gap_columns else list(range(room.columns))
    student_idx = 0
    
    for row in range(room.rows):
        for col in usable_cols:
            if student_idx >= len(students):
                return
            
            # Check if seat is already taken
            if not SeatAllocation.objects.filter(exam_room=exam_room, row=row, column=col).exists():
                allocation = SeatAllocation(
                    exam_room=exam_room,
                    student=students[student_idx],
                    row=row,
                    column=col
                )
                allocation.save()
                student_idx += 1

def try_strict_allocation(room_info, all_students, gap_columns, max_branches_per_room):
    """Try strict allocation first"""
    max_attempts = 3  # Reduced attempts for strict mode
    
    for attempt in range(max_attempts):
        # Clear previous allocations
        for room_data in room_info:
            room_data['exam_room'].seatallocation_set.all().delete()
        
        # Allocate students with strict constraints
        allocation_success = allocate_with_constraints(
            room_info, all_students, gap_columns, max_branches_per_room
        )
        
        if allocation_success:
            # Check if all students allocated
            total_allocated = sum(
                SeatAllocation.objects.filter(exam_room=room_data['exam_room']).count()
                for room_data in room_info
            )
            
            if total_allocated == len(all_students):
                print("Strict allocation successful!")
                return True
    
    return False

def relaxed_allocation(room_info, all_students, gap_columns, max_branches_per_room):
    """
    RELAXED ALLOCATION - Allow rule violations to ensure all students allocated
    """
    # Clear all allocations
    for room_data in room_info:
        room_data['exam_room'].seatallocation_set.all().delete()
    
    students_allocated = 0
    total_students = len(all_students)
    
    # Fill rooms sequentially with relaxed rules
    for room_data in room_info:
        exam_room = room_data['exam_room']
        room = room_data['room']
        effective_capacity = room_data['effective_capacity']
        
        # Calculate how many students to allocate to this room
        remaining_students = total_students - students_allocated
        remaining_rooms = len(room_info) - room_info.index(room_data)
        
        if remaining_rooms == 1:
            students_for_room = min(remaining_students, effective_capacity)
        else:
            avg_per_room = remaining_students // remaining_rooms
            students_for_room = min(avg_per_room, effective_capacity)
        
        if students_for_room == 0:
            continue
        
        # Get students for this room
        room_students = all_students[students_allocated:students_allocated + students_for_room]
        
        # Use relaxed allocation that allows mixing if needed
        try:
            allocations = allocate_seats_relaxed(
                exam_room, 
                room_students, 
                gap_columns=gap_columns, 
                max_branches_per_room=max_branches_per_room
            )
            SeatAllocation.objects.bulk_create(allocations)
            students_allocated += students_for_room
            
        except Exception as e:
            print(f"Relaxed allocation failed for room {room.name}: {e}")
            # Fallback: place students anywhere available
            fallback_allocation(exam_room, room, room_students, gap_columns)
            students_allocated += len(room_students)
    
    # FINAL CHECK: Ensure all students allocated
    final_allocated = sum(
        SeatAllocation.objects.filter(exam_room=room_data['exam_room']).count()
        for room_data in room_info
    )
    
    if final_allocated < total_students:
        # Last resort: place remaining students anywhere
        place_remaining_students(room_info, all_students[final_allocated:], gap_columns)
    
    print(f"Final allocation: {final_allocated}/{total_students} students allocated")

def allocate_seats_relaxed(exam_room, students, gap_columns, max_branches_per_room):
    """
    Relaxed seat allocation that allows mixing if needed
    """
    room = exam_room.room
    grid = [[None for _ in range(room.columns)] for _ in range(room.rows)]
    allocations = []
    
    # Group students by branch
    branch_students = {}
    for student in students:
        if student.branch.id not in branch_students:
            branch_students[student.branch.id] = []
        branch_students[student.branch.id].append(student)
    
    # Get available columns
    usable_cols = list(range(0, room.columns, 2)) if gap_columns else list(range(room.columns))
    
    # Try alternating pattern first
    branch_ids = list(branch_students.keys())
    col_idx = 0
    
    for col in usable_cols:
        if col_idx >= len(branch_ids):
            # Allow branch repetition if needed
            branch_id = branch_ids[col_idx % len(branch_ids)]
        else:
            branch_id = branch_ids[col_idx]
        
        students_in_branch = branch_students.get(branch_id, [])
        
        # Fill column with this branch's students
        for row in range(room.rows):
            if not students_in_branch:
                # Allow mixing in this column if no more students from this branch
                for other_branch_id, other_students in branch_students.items():
                    if other_students:
                        student = other_students.pop(0)
                        grid[row][col] = student
                        allocations.append(SeatAllocation(
                            exam_room=exam_room,
                            student=student,
                            row=row,
                            column=col
                        ))
                        break
                else:
                    break  # No more students at all
            else:
                student = students_in_branch.pop(0)
                grid[row][col] = student
                allocations.append(SeatAllocation(
                    exam_room=exam_room,
                    student=student,
                    row=row,
                    column=col
                ))
        
        col_idx += 1
    
    return allocations

def fallback_allocation(exam_room, room, students, gap_columns):
    """Fallback: place students anywhere available"""
    allocations = []
    usable_cols = list(range(0, room.columns, 2)) if gap_columns else list(range(room.columns))
    
    student_idx = 0
    for row in range(room.rows):
        for col in usable_cols:
            if student_idx < len(students):
                allocations.append(SeatAllocation(
                    exam_room=exam_room,
                    student=students[student_idx],
                    row=row,
                    column=col
                ))
                student_idx += 1
    
    SeatAllocation.objects.bulk_create(allocations)

def place_remaining_students(room_info, remaining_students, gap_columns):
    """Place remaining students in any available seats"""
    student_idx = 0
    
    for room_data in room_info:
        exam_room = room_data['exam_room']
        room = room_data['room']
        usable_cols = list(range(0, room.columns, 2)) if gap_columns else list(range(room.columns))
        
        for row in range(room.rows):
            for col in usable_cols:
                if student_idx < len(remaining_students):
                    # Check if seat is already taken
                    if not SeatAllocation.objects.filter(exam_room=exam_room, row=row, column=col).exists():
                        allocation = SeatAllocation(
                            exam_room=exam_room,
                            student=remaining_students[student_idx],
                            row=row,
                            column=col
                        )
                        allocation.save()
                        student_idx += 1
                
                if student_idx >= len(remaining_students):
                    return

def allocate_with_constraints(room_info, all_students, gap_columns, max_branches_per_room):
    """
    Allocate students following all constraints (Steps 3-7)
    """
    students_allocated = 0
    total_students = len(all_students)
    
    for room_data in room_info:
        exam_room = room_data['exam_room']
        room = room_data['room']
        effective_columns = room_data['effective_columns']
        effective_capacity = room_data['effective_capacity']
        
        # Calculate students for this room
        remaining_rooms = len(room_info) - room_info.index(room_data)
        remaining_students = total_students - students_allocated
        
        if remaining_rooms == 1:
            students_for_room = min(remaining_students, effective_capacity)
        else:
            avg_per_room = remaining_students // remaining_rooms
            students_for_room = min(avg_per_room, effective_capacity)
        
        if students_for_room == 0:
            continue
        
        # Get students for this room
        room_students = all_students[students_allocated:students_allocated + students_for_room]
        
        # Group students by branch for this room
        room_branch_students = {}
        for student in room_students:
            if student.branch.id not in room_branch_students:
                room_branch_students[student.branch.id] = []
            room_branch_students[student.branch.id].append(student)
        
        # Ensure exactly 2 branches per room (Step 4)
        if len(room_branch_students) > 2:
            # Keep only the 2 branches with most students
            sorted_branches = sorted(room_branch_students.items(), key=lambda x: len(x[1]), reverse=True)
            room_branch_students = dict(sorted_branches[:2])
        
        # Allocate using alternating column pattern (Steps 3, 5, 6, 7)
        try:
            allocations = allocate_seats(
                exam_room, 
                room_students, 
                gap_columns=gap_columns, 
                max_branches_per_room=max_branches_per_room
            )
            SeatAllocation.objects.bulk_create(allocations)
            students_allocated += students_for_room
        except Exception as e:
            print(f"Allocation failed for room {room.name}: {e}")
            return False
    
    return students_allocated == total_students

def global_redistribution(exam_rooms, room_info, all_students, gap_columns, max_branches_per_room):
    """
    STEP 8: Move students to fill empty seats - AGGRESSIVE FILLING
    """
    # Find all allocated students
    allocated_student_ids = set()
    for exam_room in exam_rooms:
        allocated_ids = SeatAllocation.objects.filter(exam_room=exam_room).values_list('student_id', flat=True)
        allocated_student_ids.update(allocated_ids)
    
    # Find ALL unallocated students
    unallocated_students = [s for s in all_students if s.id not in allocated_student_ids]
    
    if not unallocated_students:
        return True  # No unallocated students
    
    # AGGRESSIVE SEAT FILLING - Fill every possible empty seat
    student_index = 0
    total_students_to_place = len(unallocated_students)
    
    while student_index < total_students_to_place:
        filled_any = False
        
        for room_data in room_info:
            exam_room = room_data['exam_room']
            effective_capacity = room_data['effective_capacity']
            
            # Check current usage
            current_usage = SeatAllocation.objects.filter(exam_room=exam_room).count()
            available_space = effective_capacity - current_usage
            
            if available_space > 0 and student_index < total_students_to_place:
                # Fill as many seats as possible in this room
                students_to_add = unallocated_students[student_index:student_index + available_space]
                
                try:
                    # Create allocations for these students
                    allocations = []
                    for student in students_to_add:
                        # Find any available seat in this room
                        seat_found = False
                        for row in range(room_data['room'].rows):
                            for col in range(0, room_data['room'].columns, 2 if gap_columns else 1):
                                if not SeatAllocation.objects.filter(exam_room=exam_room, row=row, column=col).exists():
                                    allocation = SeatAllocation(
                                        exam_room=exam_room,
                                        student=student,
                                        row=row,
                                        column=col
                                    )
                                    allocations.append(allocation)
                                    seat_found = True
                                    break
                            if seat_found:
                                break
                        
                        if not seat_found:
                            continue  # No seat found for this student
                    
                    if allocations:
                        SeatAllocation.objects.bulk_create(allocations)
                        student_index += len(students_to_add)
                        filled_any = True
                        
                except Exception as e:
                    print(f"Redistribution failed for room {room_data['room'].name}: {e}")
                    continue
        
        if not filled_any:
            break  # No more seats can be filled
    
    return student_index >= total_students_to_place

def verify_complete_allocation(exam_rooms, total_students, total_capacity):
    """
    STEP 9: Verify all students allocated and no avoidable empty seats
    """
    # Count allocated students
    allocated_count = 0
    for exam_room in exam_rooms:
        allocated_count += SeatAllocation.objects.filter(exam_room=exam_room).count()
    
    # Check if all students allocated
    if allocated_count < total_students:
        print(f"DEBUG: Not all students allocated. {allocated_count}/{total_students}")
        return False
    
    # Check if there are avoidable empty seats
    total_used = allocated_count
    if total_used < total_capacity:
        print(f"DEBUG: Empty seats exist. {total_used}/{total_capacity} used")
        return False
    
    print(f"DEBUG: Verification passed. {allocated_count}/{total_students} allocated, {total_used}/{total_capacity} seats used")
    return True
    
    
def get_students_for_room(remaining_branch_students, effective_capacity, max_branches_per_room):
    """
    Get students for a room ensuring exactly 2 branches per room.
    Simple and forceful approach to guarantee 2 branches.
    """
    if not remaining_branch_students:
        return []
    
    # Filter branches that still have students
    available_branches = {
        bid: students for bid, students in remaining_branch_students.items() 
        if students
    }
    
    print(f"DEBUG: Available branches: {list(available_branches.keys())}")
    
    if len(available_branches) < 2:
        print(f"DEBUG: Less than 2 branches available, returning empty")
        return []
    
    # Take the first 2 available branches (simple and forceful)
    branch_ids = list(available_branches.keys())
    branch1_id = branch_ids[0]
    branch2_id = branch_ids[1]
    
    print(f"DEBUG: Selected branches: {branch1_id}, {branch2_id}")
    
    branch1_students = available_branches[branch1_id].copy()
    branch2_students = available_branches[branch2_id].copy()
    
    # Calculate how many students to take to maximize room utilization
    total_available = len(branch1_students) + len(branch2_students)
    
    # Try to fill the room completely, but don't exceed available students
    total_to_take = min(total_available, effective_capacity)
    
    # For maximum utilization, we want to take as many students as possible
    # Distribute as evenly as possible between the two branches
    if total_available >= effective_capacity:
        # We have enough students to fill the room completely
        half_capacity = effective_capacity // 2
        branch1_count = min(half_capacity, len(branch1_students))
        branch2_count = min(effective_capacity - branch1_count, len(branch2_students))
        
        # If one branch doesn't have enough students, take more from the other
        if len(branch1_students) < half_capacity:
            branch1_count = len(branch1_students)
            branch2_count = min(effective_capacity - branch1_count, len(branch2_students))
        elif len(branch2_students) < half_capacity:
            branch2_count = len(branch2_students)
            branch1_count = min(effective_capacity - branch2_count, len(branch1_students))
    else:
        # We don't have enough students to fill the room completely, take all available
        branch1_count = len(branch1_students)
        branch2_count = len(branch2_students)
    
    print(f"DEBUG: Taking {branch1_count} from branch1, {branch2_count} from branch2")
    
    # Create student list
    students_to_take = []
    students_to_take.extend(branch1_students[:branch1_count])
    students_to_take.extend(branch2_students[:branch2_count])
    
    # Update remaining students
    remaining_branch_students[branch1_id] = branch1_students[branch1_count:]
    remaining_branch_students[branch2_id] = branch2_students[branch2_count:]
    
    print(f"DEBUG: Returning {len(students_to_take)} students total")
    
    return students_to_take
