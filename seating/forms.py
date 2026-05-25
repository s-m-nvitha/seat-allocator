from django import forms
from django.core.validators import FileExtensionValidator
from .models import Branch, Room, Student, Exam, ExamRoom

class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ['name', 'code']

class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name', 'capacity', 'rows', 'columns', 'is_active']

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['roll_number', 'name', 'branch', 'needs_accommodation', 'accommodation_details']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['accommodation_details'].widget.attrs['rows'] = 3
        self.fields['accommodation_details'].required = False

class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ['name', 'date', 'start_time', 'end_time']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

class ExamRoomForm(forms.ModelForm):
    class Meta:
        model = ExamRoom
        fields = ['room', 'invigilator']

class StudentUploadForm(forms.Form):
    file = forms.FileField(
        validators=[FileExtensionValidator(allowed_extensions=['csv', 'xlsx'])]
    )
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        required=False,
        help_text='Optional: if not selected, branch will be read from branch_code column in the file'
    )

class SeatAllocationConfigForm(forms.Form):
    exam = forms.ModelChoiceField(
        queryset=Exam.objects.all(),
        required=True
    )
    rooms = forms.ModelMultipleChoiceField(
        queryset=Room.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )
    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.all(),
        required=True,
        widget=forms.CheckboxSelectMultiple
    )
    gap_columns = forms.BooleanField(
        initial=True,
        required=False,
        help_text='Leave one column gap between students'
    )
    mix_branches = forms.BooleanField(
        initial=True,
        required=False,
        help_text='Mix students from different branches'
    )
    auto_select_rooms = forms.BooleanField(
        initial=False,
        required=False,
        help_text='Automatically select rooms based on total students'
    )
    max_branches_per_room = forms.IntegerField(
        initial=2,
        min_value=2,
        max_value=2,
        required=True,
        help_text='Number of branches to mix per room (exactly 2)'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # When the form is first shown (GET, not bound), preselect sensible defaults
        if not self.is_bound:
            # By default, select all branches (you can uncheck if needed)
            self.fields['branches'].initial = Branch.objects.all()
            # By default, enable automatic room selection
            self.fields['auto_select_rooms'].initial = True