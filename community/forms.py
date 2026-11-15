from django import forms

from core.services import normalise_text

from .models import Announcement, Post

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"class": INPUT, "rows": 3, "maxlength": 2000})}
        labels = {"body": "Your message"}

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("Write something first.")
        return body


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "body"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT, "maxlength": 150}),
            "body": forms.Textarea(attrs={"class": INPUT, "rows": 4, "maxlength": 3000}),
        }

    def clean_title(self):
        title = normalise_text(self.cleaned_data["title"])
        if not title:
            raise forms.ValidationError("Title is required.")
        return title

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("The announcement text is required.")
        return body
