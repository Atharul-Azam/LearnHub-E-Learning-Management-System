from django.core.exceptions import ValidationError


class LetterAndNumberValidator:
    """SRS 22.2: passwords must combine letters and numbers."""

    def validate(self, password, user=None):
        has_letter = any(ch.isalpha() for ch in password)
        has_digit = any(ch.isdigit() for ch in password)
        if not (has_letter and has_digit):
            raise ValidationError(
                "The password must contain both letters and numbers.",
                code="password_letters_and_numbers",
            )

    def get_help_text(self):
        return "Your password must contain both letters and numbers."
