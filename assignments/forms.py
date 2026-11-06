from decimal import Decimal

from django import forms
from django.db.models import Max

from core.files import clean_display_name, schedule_file_delete
from core.services import normalise_text
from core.validators import validate_attachment, validate_submission

from .models import Assignment

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
FILE_INPUT = "block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-indigo-700"
DEADLINE_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]


class AssignmentForm(forms.ModelForm):
    """UC10. The instance must be created with its course already set (see views)."""

    deadline = forms.DateTimeField(
        input_formats=DEADLINE_FORMATS,
        widget=forms.DateTimeInput(attrs={"class": INPUT, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        help_text="Submissions after this time are still accepted but marked late.",
    )
    attachment = forms.FileField(
        required=False,
        validators=[validate_attachment],
        widget=forms.FileInput(attrs={"class": FILE_INPUT}),
        help_text="Optional.",
    )
    remove_attachment = forms.BooleanField(required=False, label="Remove the current attachment")

    class Meta:
        model = Assignment
        fields = ["title", "instructions", "deadline", "max_marks", "attachment"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT}),
            "instructions": forms.Textarea(attrs={"class": INPUT, "rows": 6}),
            "max_marks": forms.NumberInput(attrs={"class": INPUT, "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_attachment = self.instance.attachment.name if self.instance.pk and self.instance.attachment else ""
        if not self._old_attachment:
            del self.fields["remove_attachment"]

    def clean_title(self):
        value = normalise_text(self.cleaned_data["title"])
        if not value:
            raise forms.ValidationError("Title is required.")
        return value

    def clean_instructions(self):
        value = self.cleaned_data["instructions"].strip()
        if not value:
            raise forms.ValidationError("Instructions are required.")
        return value

    def clean_max_marks(self):
        value = self.cleaned_data["max_marks"]
        if value is None or value < 1:
            raise forms.ValidationError("Maximum marks must be at least 1.")
        if self.instance.pk:
            highest = self.instance.submissions.aggregate(m=Max("marks"))["m"]
            if highest is not None and Decimal(value) < highest:
                raise forms.ValidationError(
                    f"Maximum marks cannot be lower than marks already awarded ({highest.normalize():f})."
                )
        return value

    def save(self, commit=True):
        assignment = super().save(commit=False)
        upload = self.files.get("attachment")
        if upload is not None:
            assignment.attachment_name = clean_display_name(upload.name)
        elif self.cleaned_data.get("remove_attachment"):
            assignment.attachment = ""
            assignment.attachment_name = ""
        assignment.save()
        new_name = assignment.attachment.name if assignment.attachment else ""
        if self._old_attachment and self._old_attachment != new_name:
            schedule_file_delete(assignment.attachment.storage, self._old_attachment)
        return assignment


class SubmissionForm(forms.Form):
    """UC16 - the student's file. Type, size and real content are validated server-side."""

    file = forms.FileField(
        label="Completed work",
        validators=[validate_submission],
        widget=forms.FileInput(attrs={"class": FILE_INPUT}),
    )


class ReviewForm(forms.Form):
    """UC12 - marks within 0..max_marks and written feedback."""

    marks = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=6,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT, "step": "0.01", "min": "0"}),
    )
    feedback = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": INPUT, "rows": 5}))

    def __init__(self, *args, assignment, **kwargs):
        super().__init__(*args, **kwargs)
        self.assignment = assignment
        self.fields["marks"].help_text = f"Between 0 and {assignment.max_marks}."
        self.fields["marks"].widget.attrs["max"] = str(assignment.max_marks)

    def clean_marks(self):
        marks = self.cleaned_data["marks"]
        if marks < 0 or marks > self.assignment.max_marks:
            raise forms.ValidationError(f"Marks must be between 0 and {self.assignment.max_marks}.")
        return marks

    def clean_feedback(self):
        return self.cleaned_data["feedback"].strip()
