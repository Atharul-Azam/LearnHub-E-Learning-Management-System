from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from core.services import normalise_text

from .models import User

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"


class RegistrationForm(forms.Form):
    """UC1. Student and Teacher categories; name, e-mail and password are mandatory."""

    ACCOUNT_TYPES = [(User.Role.STUDENT, "Student"), (User.Role.TEACHER, "Teacher")]

    account_type = forms.ChoiceField(choices=ACCOUNT_TYPES, widget=forms.RadioSelect, label="Account category")
    name = forms.CharField(max_length=150, label="Full name", widget=forms.TextInput(attrs={"class": INPUT, "autocomplete": "name"}))
    email = forms.CharField(max_length=254, label="E-mail address", widget=forms.EmailInput(attrs={"class": INPUT, "autocomplete": "email"}))
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"class": INPUT, "autocomplete": "new-password"}), help_text="At least 8 characters, combining letters and numbers.")

    def clean_name(self):
        name = normalise_text(self.cleaned_data["name"])
        if not name:
            raise forms.ValidationError("Name is required.")
        return name

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        try:
            validate_email(email)
        except forms.ValidationError:
            raise forms.ValidationError("Enter a valid e-mail address.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this e-mail address already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def save(self):
        data = self.cleaned_data
        try:
            with transaction.atomic():
                return User.objects.create_user(
                    email=data["email"], name=data["name"], password=data["password"], role=data["account_type"]
                )
        except IntegrityError:  # two simultaneous registrations with the same e-mail
            self.add_error("email", "An account with this e-mail address already exists.")
            return None


class LoginForm(forms.Form):
    email = forms.CharField(label="E-mail address", widget=forms.EmailInput(attrs={"class": INPUT, "autocomplete": "email", "autofocus": True}))
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"class": INPUT, "autocomplete": "current-password"}))

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class ResendVerificationForm(forms.Form):
    email = forms.CharField(label="E-mail address", widget=forms.EmailInput(attrs={"class": INPUT, "autocomplete": "email"}))

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


# ---------------------------------------------------------------- settings
from django.contrib.auth.forms import PasswordChangeForm  # noqa: E402

from core.validators import validate_avatar  # noqa: E402

FILE_INPUT = "block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-indigo-700"
SELECT = INPUT


class ProfileForm(forms.ModelForm):
    """Edit name, biography, expertise (teachers) and the profile picture. The ID is never editable."""

    profile_picture = forms.ImageField(
        required=False,
        validators=[validate_avatar],
        widget=forms.FileInput(attrs={"class": FILE_INPUT, "accept": "image/png,image/jpeg,image/webp"}),
        help_text="PNG, JPG or WEBP, up to 2 MB.",
    )
    remove_picture = forms.BooleanField(required=False, label="Remove my picture (use the default avatar)")

    class Meta:
        model = User
        fields = ["name", "bio", "expertise", "profile_picture"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT, "autocomplete": "name"}),
            "bio": forms.Textarea(attrs={"class": INPUT, "rows": 4}),
            "expertise": forms.TextInput(attrs={"class": INPUT}),
        }
        labels = {"bio": "Short biography", "expertise": "Expertise / teaching interests"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_picture = self.instance.profile_picture.name if self.instance.profile_picture else ""
        if self.instance.role != User.Role.TEACHER:
            del self.fields["bio"]
            del self.fields["expertise"]
        if not self._old_picture:
            del self.fields["remove_picture"]

    def clean_name(self):
        name = normalise_text(self.cleaned_data["name"])
        if not name:
            raise forms.ValidationError("Name is required.")
        return name

    def save(self, commit=True):
        from core.files import schedule_file_delete

        user = super().save(commit=False)
        if self.cleaned_data.get("remove_picture") and "profile_picture" not in self.files:
            user.profile_picture = ""
        user.save()
        new_name = user.profile_picture.name if user.profile_picture else ""
        if self._old_picture and self._old_picture != new_name:
            schedule_file_delete(user.profile_picture.storage, self._old_picture)
        return user


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT


class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["notify_courses", "notify_assignments", "notify_discussion"]


class AppearanceForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["theme", "font"]
        widgets = {"theme": forms.RadioSelect, "font": forms.Select(attrs={"class": SELECT})}


class DeleteAccountForm(forms.Form):
    password = forms.CharField(label="Your password", strip=False, widget=forms.PasswordInput(attrs={"class": INPUT, "autocomplete": "current-password"}))
    understand = forms.BooleanField(label="I understand that this permanently deletes my account and cannot be undone.")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("The password is incorrect.")
        return password
