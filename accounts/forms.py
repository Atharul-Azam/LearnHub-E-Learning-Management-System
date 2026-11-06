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
