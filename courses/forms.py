from django import forms

from core.files import schedule_file_delete
from core.services import normalise_text
from core.validators import validate_thumbnail

from .models import Course

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
FILE_INPUT = "block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-indigo-700"


class CourseForm(forms.ModelForm):
    """UC7 / UC8 - title, description, category and thumbnail."""

    thumbnail = forms.ImageField(
        required=False,
        validators=[validate_thumbnail],
        widget=forms.FileInput(attrs={"class": FILE_INPUT, "accept": "image/png,image/jpeg,image/gif,image/webp"}),
        help_text="Optional. PNG, JPG, GIF or WEBP. A default image is used if you skip this.",
    )
    remove_thumbnail = forms.BooleanField(required=False, label="Remove the current thumbnail (use the default image)")

    class Meta:
        model = Course
        fields = ["title", "description", "category", "thumbnail"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 6}),
            "category": forms.TextInput(attrs={"class": INPUT, "list": "category-options", "placeholder": "e.g. Programming"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_thumbnail = self.instance.thumbnail.name if self.instance.pk and self.instance.thumbnail else ""
        if not self.instance.pk or not self._old_thumbnail:
            del self.fields["remove_thumbnail"]

    def clean_title(self):
        value = normalise_text(self.cleaned_data["title"])
        if not value:
            raise forms.ValidationError("Title is required.")
        return value

    def clean_category(self):
        value = normalise_text(self.cleaned_data["category"])
        if not value:
            raise forms.ValidationError("Category is required.")
        return value

    def clean_description(self):
        value = self.cleaned_data["description"].strip()
        if not value:
            raise forms.ValidationError("Description is required.")
        return value

    def save(self, commit=True):
        course = super().save(commit=False)
        if self.cleaned_data.get("remove_thumbnail") and "thumbnail" not in self.files:
            course.thumbnail = ""
        course.save()
        new_name = course.thumbnail.name if course.thumbnail else ""
        if self._old_thumbnail and self._old_thumbnail != new_name:
            schedule_file_delete(course.thumbnail.storage, self._old_thumbnail)
        return course
