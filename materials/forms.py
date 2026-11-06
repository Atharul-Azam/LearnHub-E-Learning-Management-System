from django import forms

from core.files import clean_display_name, schedule_file_delete
from core.services import normalise_text
from core.validators import validate_material

from .models import LearningMaterial

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
FILE_INPUT = "block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-indigo-700"


class MaterialForm(forms.ModelForm):
    """UC9. The instance must be created with its course already set (see views)."""

    file = forms.FileField(
        validators=[validate_material],
        widget=forms.FileInput(attrs={"class": FILE_INPUT}),
        label="File",
    )

    class Meta:
        model = LearningMaterial
        fields = ["title", "file"]
        widgets = {"title": forms.TextInput(attrs={"class": INPUT})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_file = self.instance.file.name if self.instance.pk and self.instance.file else ""
        if self.instance.pk:
            # When editing, leaving the file empty keeps the current one.
            self.fields["file"].required = False
            self.fields["file"].help_text = "Choose a file only if you want to replace the current one."

    def clean_title(self):
        value = normalise_text(self.cleaned_data["title"])
        if not value:
            raise forms.ValidationError("Title is required.")
        return value

    def save(self, commit=True):
        material = super().save(commit=False)
        upload = self.files.get("file")
        if upload is not None:
            material.original_name = clean_display_name(upload.name)
        material.save()
        new_name = material.file.name if material.file else ""
        if self._old_file and self._old_file != new_name:
            schedule_file_delete(material.file.storage, self._old_file)
        return material
