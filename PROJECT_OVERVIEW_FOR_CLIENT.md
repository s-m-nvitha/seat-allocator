# Seat Allocator — Project Overview for Client

## 1. What Is This Project?

**Seat Allocator** is a **web-based exam seating management system** for educational institutions. It lets staff create exams, manage rooms and students, and **automatically assign students to seats** in a fair, mixed-branch way with optional social distancing and special-needs support.

---

## 2. Technical Stack Used

| Layer | Technology | Purpose |
|-------|------------|--------| 
| **Backend** | **Django 5.0** | Web framework: URLs, views, auth, admin, business logic |
| **Database** | **SQLite** (default) | Stores branches, rooms, students, exams, seat allocations |
| **Frontend** | **HTML + Bootstrap 5** | Responsive, mobile-friendly UI |
| **Forms** | **Django Crispy Forms + Bootstrap 5** | Clean, consistent form layout and validation |
| **Data import** | **Pandas** | Read CSV/Excel student lists and bulk import |
| **Export** | **XlsxWriter** | Generate Excel seating reports (room-wise, with special needs) |
| **PDF** | **FPDF2** | PDF generation support (e.g. hall tickets or reports) |
| **Configuration** | **python-dotenv** | Environment variables (e.g. secret key, DB) |
| **Optional** | **Streamlit** | Separate “Exam Seating Visualizer” app (MySQL + optional AI/speech) |

**Summary:** The main application is a **Django website** (Python) with SQLite, Bootstrap UI, and Excel/CSV support. Streamlit is an optional extra for visualization and advanced features.

---

## 3. How It Works — Step by Step

### Step 1: Login
- Only **logged-in staff** can use the system.
- Staff log in via the **Login** page; unauthenticated users are redirected to login.

### Step 2: Dashboard
- After login, staff see a **dashboard** with:
  - Total students, rooms, and exams
  - Recent exams
- From here they can go to rooms, students, and exams.

### Step 3: Manage Branches & Rooms
- **Branches** (e.g. CSE, ECE) are created (via admin or when uploading students).
- **Rooms** are added with:
  - Name, capacity
  - **Rows** and **columns** (e.g. 10 rows × 6 columns)
  - Active/Inactive flag  
- This defines the physical layout used for seat allocation.

### Step 4: Upload Students
- Staff go to **“Upload Students”**.
- They upload a **CSV or Excel** file with columns such as:
  - `roll_number`, `name`, `branch_code`
  - Optional: `needs_accommodation`, `accommodation_details`
- They can select a **single branch** for the file or let the file specify branch per row.
- System **creates or updates** students and links them to branches.
- Errors (e.g. missing roll number) are reported; successful rows are counted.

### Step 5: Create an Exam
- Staff go to **“Exams”** → **“Create Exam”**.
- They enter:
  - Exam name, date, start time, end time
- Exam is saved and linked to the logged-in user.

### Step 6: Allocate Seats for the Exam
- Staff open the exam and choose **“Allocate Seats”**.
- They configure:
  - **Branches** to include (e.g. CSE, ECE for this exam)
  - **Rooms** to use, **or** “auto-select rooms” so the system picks rooms until capacity is enough
  - **Gap columns**: if enabled, only every other column is used (social distancing)
- On submit:
  1. System collects all students from selected branches.
  2. Students are **mixed by branch** (round-robin) so no room has only one branch.
  3. For each room, the **allocation algorithm**:
     - Places **special-needs** students first (e.g. near front/aisle).
     - Then places others so **same-branch students are not too close** (reduces copying).
     - Respects **gap columns** (alternate columns left empty if enabled).
  4. Results are saved as **SeatAllocation** records (exam_room, student, row, column).

### Step 7: View Exam & Room Layout
- **Exam detail** page shows all rooms used for that exam and the list of allocations per room.
- **Room layout API** can return a grid (rows × columns) with student/roll/branch/special-needs for use in visualizations or printouts.

### Step 8: Export to Excel
- Staff can **export** the seating plan to **Excel**.
- File includes:
  - Overview sheet (exam name, date, time)
  - One sheet per room: seat (row, col), roll number, name, branch, special needs
- Useful for invigilators and notice boards.

### Step 9: Optional — Streamlit Visualizer
- A separate **Streamlit** app can connect to a **MySQL** database (if configured) to:
  - List exams and rooms
  - Show **visual room layout** (seats, occupied vs empty, special needs)
  - Optionally use **OpenAI** and **speech recognition** for extra features (e.g. voice queries).

---

## 4. How It Is Useful to the Institute / Public

### For the institute (administration & staff)
- **Saves time:** No manual seating charts; allocation is automatic and repeatable.
- **Fair mixing:** Students from different branches are mixed in each room, reducing exam malpractice.
- **Social distancing:** “Gap columns” option supports exam hall distancing requirements.
- **Special needs:** Students with accommodation needs get priority placement (e.g. front/aisle).
- **Scalable:** Handles many students and rooms; capacity is computed from rows/columns and gap option.
- **Audit trail:** Exams and allocations are stored; you can see who created an exam and when.
- **Reports:** Excel export for invigilators and display; optional PDF for hall tickets or notices.
- **Access control:** Only logged-in staff can manage data and run allocation.

### For students (indirect benefit)
- **Clear seating:** Each student gets a defined seat (room, row, column) before the exam.
- **Less confusion:** Institute can publish or print room-wise lists and layouts.
- **Accommodations:** Special-needs students are placed in suitable seats by design.

### For the public / transparency
- Institute can **publish** seating arrangements (e.g. via exported Excel/PDF) so students and parents know where to go.
- Process is **consistent and rule-based**, which supports fairness and compliance.

---

## 5. One-Page Flow Summary

```
Login → Dashboard
         ↓
    [Manage Rooms]     [Upload Students CSV/Excel]     [Create Exam]
         ↓                        ↓                            ↓
    Room list              Students in DB              Exam list
    (name, rows, cols)     (roll, name, branch,        (name, date, time)
                            special needs)
         ↓                        ↓                            ↓
         └────────────────────────┴──────────────────────────┘
                                    ↓
                    For an exam: [Allocate Seats]
                                    ↓
                    Select branches + rooms (or auto) + gap columns
                                    ↓
                    Algorithm: mix branches, respect gaps & special needs
                                    ↓
                    [View Exam Detail] → [Export Excel]
                                    ↓
                    Invigilators & notice boards use the Excel/PDF
```

---

## 6. Summary Table

| Question | Answer |
|----------|--------|
| **What is it?** | Web app for automatic exam seat allocation with branch mixing and special needs. |
| **Who uses it?** | Institute staff (admin/coordinators). Students benefit via published seating. |
| **Tech stack** | Django, SQLite, Bootstrap 5, Pandas, XlsxWriter, FPDF2; optional Streamlit + MySQL. |
| **Main steps** | Login → Add rooms → Upload students → Create exam → Allocate seats → View/Export. |
| **Why useful?** | Saves time, fair mixing, optional distancing, special needs, Excel/PDF reports, access control. |

You can use this document as-is for client presentations or shorten it to a one-pager using Section 5 and the summary table.
