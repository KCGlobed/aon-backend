import re
from django.conf import settings
from django.db import models


class Sections(models.Model):
    name = models.CharField(max_length=255)
    section_id = models.CharField(max_length=50, unique=True, blank=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Section'
        verbose_name_plural = 'Sections'

    def __str__(self):
        return f"{self.section_id} - {self.name}"

    def build_section_prefix(self):
        """Initials of every word in the name: 'Accounting & Finance Fundamentals' -> 'AFF'."""
        words = re.findall(r'[A-Za-z0-9]+', self.name or '')
        prefix = ''.join(word[0] for word in words).upper()[:10]
        return prefix or 'SEC'

    def generate_section_id(self):
        """The bare prefix when it is free, otherwise the prefix with the next free number appended."""
        prefix = self.build_section_prefix()

        if not Sections.objects.filter(section_id=prefix).exclude(pk=self.pk).exists():
            return prefix

        existing = Sections.objects.filter(
            section_id__regex=r'^{}[0-9]+$'.format(prefix)
        ).exclude(pk=self.pk).values_list('section_id', flat=True)

        counter = 0
        for section_id in existing:
            counter = max(counter, int(section_id[len(prefix):]))

        while True:
            counter += 1
            section_id = f"{prefix}{counter}"
            if not Sections.objects.filter(section_id=section_id).exclude(pk=self.pk).exists():
                return section_id

    def save(self, *args, **kwargs):
        if not self.section_id:
            self.section_id = self.generate_section_id()

        super().save(*args, **kwargs)


class Question(models.Model):

    class DifficultyLevel(models.IntegerChoices):
        EASY = 1, 'Easy'
        MEDIUM = 2, 'Medium'
        HARD = 3, 'Hard'

    section = models.ForeignKey(Sections, on_delete=models.PROTECT, related_name='questions')
    question_code = models.CharField(max_length=50, unique=True)
    question_text = models.TextField()
    difficulty_level = models.PositiveSmallIntegerField(choices=DifficultyLevel.choices, default=DifficultyLevel.EASY)
    correct_answer_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    negative_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Question'
        verbose_name_plural = 'Questions'

    def __str__(self):
        return f"{self.question_code} - {self.section.section_id}"


class QuestionOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    option_text = models.TextField()
    right_option = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Question Option'
        verbose_name_plural = 'Question Options'

    def __str__(self):
        return f"{self.question.question_code} - {self.option_text[:50]}"


class QuestionHistory(models.Model):

    class Action(models.TextChoices):
        CREATED = 'Created', 'Created'
        IMPORTED = 'Imported', 'Imported'
        UPDATED = 'Updated', 'Updated'
        STATUS_CHANGED = 'Status Changed', 'Status Changed'
        DELETED = 'Deleted', 'Deleted'

    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True, related_name='history')
    question_code = models.CharField(max_length=50)
    action = models.CharField(max_length=20, choices=Action.choices)
    changes = models.JSONField(default=dict, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='question_changes')
    changed_by_email = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Question History'
        verbose_name_plural = 'Question History'
        ordering = ['-changed_at', '-id']

    def __str__(self):
        return f"{self.question_code} - {self.action}"
