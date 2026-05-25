import random
from typing import List, Dict, Set, Tuple
from ..models import Student, Room, ExamRoom, SeatAllocation

def allocate_seats(exam_room: ExamRoom, students: List[Student], gap_columns: bool = True, max_branches_per_room: int = 2) -> List[SeatAllocation]:
    """
    Allocate seats for students in an exam room following these rules:
    1. Mix students from different branches to prevent cheating
    2. Maintain reasonable distance between same-branch students
    3. Respect room capacity limits
    4. Handle special-needs accommodations
    5. Add gaps between students if gap_columns is True
    """
    room = exam_room.room
    total_seats = room.rows * room.columns
    
    # If gap_columns is True, we can only use alternate columns
    effective_columns = (room.columns + 1) // 2 if gap_columns else room.columns
    effective_seats = room.rows * effective_columns
    
    if len(students) > effective_seats:
        raise ValueError(f"Too many students ({len(students)}) for room capacity ({effective_seats} with gaps)")

    # DEBUG: Print what students we received
    print(f"DEBUG: Received {len(students)} students for room {room.name}")
    branch_debug = {}
    for student in students:
        branch_name = student.branch.code
        if branch_name not in branch_debug:
            branch_debug[branch_name] = 0
        branch_debug[branch_name] += 1
    print(f"DEBUG: Branch distribution: {branch_debug}")

    # Group students by branch
    branch_groups: Dict[int, List[Student]] = {}
    special_needs_students: List[Student] = []
    
    for student in students:
        if student.needs_accommodation:
            special_needs_students.append(student)
        else:
            if student.branch.id not in branch_groups:
                branch_groups[student.branch.id] = []
            branch_groups[student.branch.id].append(student)

    # Create a seating grid
    grid = [[None for _ in range(room.columns)] for _ in range(room.rows)]
    allocations = []

    # First, place special needs students in appropriate locations
    for student in special_needs_students:
        row, col = find_accommodation_seat(grid, room, gap_columns)
        if row is not None and col is not None:
            grid[row][col] = student
            allocations.append(SeatAllocation(
                exam_room=exam_room,
                student=student,
                row=row,
                column=col
            ))

    # Use students directly as provided by views.py (already contains exactly 2 branches)
    # Place students using strict alternating column pattern
    place_students_alternating_columns(grid, room, students, gap_columns, allocations, exam_room)

    return allocations

def select_branches_for_room(branch_groups: Dict[int, List[Student]], effective_seats: int, max_branches_per_room: int) -> List[int]:
    """
    Select exactly 2 branches to fill the room optimally.
    Prioritize branches that can fill the room better together.
    """
    if len(branch_groups) < 2:
        return list(branch_groups.keys())
    
    # Sort branches by student count (descending)
    sorted_branches = sorted(branch_groups.items(), key=lambda x: len(x[1]), reverse=True)
    
    # Try different combinations of 2 branches to find the best fit
    best_combination = None
    best_score = -1
    
    for i in range(len(sorted_branches)):
        for j in range(i + 1, len(sorted_branches)):
            branch1_id, branch1_students = sorted_branches[i]
            branch2_id, branch2_students = sorted_branches[j]
            
            total_students = len(branch1_students) + len(branch2_students)
            
            # Only consider combinations that don't exceed capacity
            if total_students <= effective_seats:
                # Score based on how well they fill the room (higher is better)
                fill_ratio = total_students / effective_seats
                # Prefer more balanced branches
                balance = 1 - abs(len(branch1_students) - len(branch2_students)) / max(len(branch1_students), len(branch2_students))
                
                score = fill_ratio * 0.7 + balance * 0.3
                
                if score > best_score:
                    best_score = score
                    best_combination = [branch1_id, branch2_id]
    
    # If no good combination found, fall back to the two largest branches
    if best_combination is None:
        best_combination = [sorted_branches[0][0], sorted_branches[1][0]]
    
    return best_combination

def create_alternating_pattern(branch_groups: Dict[int, List[Student]], selected_branches: List[int]) -> List[Student]:
    """
    Create simple alternating pattern between exactly 2 branches.
    """
    if len(selected_branches) != 2:
        # Fallback to simple mixing if not exactly 2 branches
        all_students = []
        for branch_id in selected_branches:
            all_students.extend(branch_groups[branch_id])
        return all_students
    
    branch1_id, branch2_id = selected_branches
    branch1_students = branch_groups[branch1_id].copy()
    branch2_students = branch_groups[branch2_id].copy()
    
    mixed_students = []
    
    # Simple alternating pattern: Branch1, Branch2, Branch1, Branch2, ...
    # This ensures proper mixing regardless of branch sizes
    while branch1_students or branch2_students:
        # Take from branch1 if available
        if branch1_students:
            mixed_students.append(branch1_students.pop(0))
        
        # Take from branch2 if available
        if branch2_students:
            mixed_students.append(branch2_students.pop(0))
    
    return mixed_students

def find_accommodation_seat(grid: List[List[Student]], room: Room, gap_columns: bool) -> Tuple[int, int]:
    """Find a suitable seat for a student needing accommodation."""
    # Prefer seats near the entrance (first row, or near aisles)
    preferred_seats = []
    
    # If using gaps, only use alternate columns
    if gap_columns:
        for row in range(room.rows):
            for col in range(0, room.columns, 2):  # Skip every other column
                preferred_seats.append((row, col))
    else:
        for row in range(room.rows):
            for col in range(room.columns):
                preferred_seats.append((row, col))
    
    # Sort by proximity to entrance (first row)
    preferred_seats.sort(key=lambda x: x[0])  # Sort by row number
    
    for row, col in preferred_seats:
        if grid[row][col] is None:
            return row, col

    return None, None

def find_next_available_seat(grid: List[List[Student]], room: Room, branch_id: int, gap_columns: bool) -> Tuple[int, int]:
    """Find the next available seat that satisfies seating rules."""
    best_score = float('inf')
    best_position = (None, None)

    for row in range(room.rows):
        for col in range(0, room.columns, 2 if gap_columns else 1):
            if grid[row][col] is None:
                score = calculate_position_score(grid, room, row, col, branch_id)
                if score < best_score:
                    best_score = score
                    best_position = (row, col)

    return best_position

def calculate_position_score(grid: List[List[Student]], room: Room, row: int, col: int, branch_id: int) -> float:
    """Calculate how good a position is (lower is better)."""
    score = 0.0
    
    # Check only immediate neighbors for performance
    neighbors = [
        (row-1, col), (row+1, col), (row, col-1), (row, col+1)
    ]
    
    for r, c in neighbors:
        if 0 <= r < room.rows and 0 <= c < room.columns:
            if grid[r][c] is not None and grid[r][c].branch.id == branch_id:
                score += 10.0  # Heavy penalty for adjacent same-branch
    
    return score

def find_any_available_seat(grid: List[List[Student]], room: Room, gap_columns: bool) -> Tuple[int, int]:
    """Find any available seat in the room."""
    for row in range(room.rows):
        for col in range(0, room.columns, 2 if gap_columns else 1):
            if grid[row][col] is None:
                return row, col
    return None, None

def place_students_alternating_columns(grid, room, mixed_students, gap_columns, allocations, exam_room):
    """
    STRICT Alternating Column Pattern:
    - Each column contains students from ONLY ONE branch
    - Columns alternate between two branches (AIML, CG, AIML, CG...)
    - Fill column-wise (top to bottom), NOT row-wise
    - Proportional distribution for uneven columns
    - Maximum seat utilization with no gaps
    """
    if not mixed_students:
        return
    
    # Group students by branch
    branch_students = {}
    for student in mixed_students:
        if student.branch.id not in branch_students:
            branch_students[student.branch.id] = []
        branch_students[student.branch.id].append(student)
    
    # Get available columns
    usable_cols = list(range(0, room.columns, 2)) if gap_columns else list(range(room.columns))
    
    # Ensure exactly 2 branches
    branch_ids = list(branch_students.keys())
    if len(branch_ids) != 2:
        return  # Must have exactly 2 branches
    
    # Calculate column distribution for uneven columns
    total_cols = len(usable_cols)
    branch1_cols = total_cols // 2 + (total_cols % 2)  # Gets extra column if odd
    branch2_cols = total_cols // 2
    
    # Create alternating column pattern
    col_idx = 0
    branch1_assigned = 0
    branch2_assigned = 0
    
    for col in usable_cols:
        # Determine which branch gets this column based on alternating pattern
        if col_idx % 2 == 0:  # Even index: Branch 1
            if branch1_assigned < branch1_cols:
                current_branch_id = branch_ids[0]
                branch1_assigned += 1
            else:
                # Branch 1 has reached its limit, skip this column
                col_idx += 1
                continue
        else:  # Odd index: Branch 2
            if branch2_assigned < branch2_cols:
                current_branch_id = branch_ids[1]
                branch2_assigned += 1
            else:
                # Branch 2 has reached its limit, skip this column
                col_idx += 1
                continue
        
        # Get students for this branch
        students_in_branch = branch_students[current_branch_id]
        
        # Fill this column top-to-bottom with students from the SAME branch only
        for row in range(room.rows):
            if not students_in_branch:
                break  # No more students from this branch, leave remaining seats empty
            
            if grid[row][col] is None:
                student = students_in_branch.pop(0)
                grid[row][col] = student
                allocations.append(SeatAllocation(
                    exam_room=exam_room,
                    student=student,
                    row=row,
                    column=col
                ))
        
        col_idx += 1