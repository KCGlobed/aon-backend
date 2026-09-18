from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from assessment.models import AssessmentQuestion, AssessmentSection
from content.models import QuestionOption
from session.models import Session


class TestAttempt(models.Model):
    """One student's sitting of one session.

    A student gets a single attempt per session; closing the browser and coming back picks the same
    one up rather than starting again.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = 'In Progress', 'In Progress'
        SUBMITTED = 'Submitted', 'Submitted'

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='test_attempts')
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.IN_PROGRESS)
    candidate_image = models.ImageField(upload_to='candidate/photos/', help_text='Photo of the student, taken as the test is started')
    id_proof_image = models.ImageField(upload_to='candidate/id_proofs/', help_text='Photo of the identity document, taken as the test is started')
    total_marks = models.DecimalField(max_digits=9, decimal_places=2, default=0, help_text='What the student scored across every section')
    max_marks = models.DecimalField(max_digits=9, decimal_places=2, default=0, help_text="The assessment's own total, kept here so an edit to the test later does not rewrite this result")
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    wrong_answers = models.PositiveIntegerField(default=0)
    unanswered = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Test Attempt'
        verbose_name_plural = 'Test Attempts'
        constraints = [
            models.UniqueConstraint(fields=['session', 'student'], name='unique_attempt_per_session_student')
        ]

    def __str__(self):
        return f"{self.session.name} - {self.student.email}"

    @property
    def is_submitted(self):
        return self.status == self.Status.SUBMITTED

    @property
    def percentage(self):
        if not self.max_marks:
            return Decimal('0.00')

        return (Decimal(self.total_marks) / Decimal(self.max_marks) * 100).quantize(Decimal('0.01'))

    def sync_totals(self):
        """Adds the submitted sections up. Sections the student never opened count as unanswered, so
        the question totals always add up to the paper that was set."""
        sections = self.sections.all()
        submitted = [section for section in sections if section.status == TestSectionAttempt.Status.SUBMITTED]

        self.total_marks = sum((section.score for section in submitted), Decimal('0.00'))
        self.correct_answers = sum(section.correct_answers for section in submitted)
        self.wrong_answers = sum(section.wrong_answers for section in submitted)
        self.total_questions = sum(section.total_questions for section in sections)
        self.unanswered = self.total_questions - self.correct_answers - self.wrong_answers
        self.save(update_fields=['total_marks', 'correct_answers', 'wrong_answers',
                                 'total_questions', 'unanswered', 'updated_at'])


class TestSectionAttempt(models.Model):
    """One section of the paper, which is submitted on its own and cannot be reopened afterwards."""

    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        SUBMITTED = 'Submitted', 'Submitted'

    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name='sections')
    assessment_section = models.ForeignKey(AssessmentSection, on_delete=models.PROTECT, related_name='section_attempts')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    score = models.DecimalField(max_digits=9, decimal_places=2, default=0, help_text='Can be below zero where the section carries negative marking')
    max_marks = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    wrong_answers = models.PositiveIntegerField(default=0)
    unanswered = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Test Section Attempt'
        verbose_name_plural = 'Test Section Attempts'
        ordering = ['assessment_section__order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['attempt', 'assessment_section'], name='unique_section_per_attempt')
        ]

    def __str__(self):
        return f"{self.attempt} - {self.assessment_section.section.section_id}"

    @property
    def is_submitted(self):
        return self.status == self.Status.SUBMITTED

    def sync_totals(self):
        """Reads the section's result off the answers that were saved for it."""
        answers = list(self.answers.all())
        self.score = sum((answer.marks_awarded for answer in answers), Decimal('0.00'))
        self.correct_answers = len([answer for answer in answers if answer.is_correct])
        self.wrong_answers = len([answer for answer in answers
                                  if answer.selected_option_id and not answer.is_correct])
        self.unanswered = len([answer for answer in answers if not answer.selected_option_id])
        self.status = self.Status.SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=['score', 'correct_answers', 'wrong_answers', 'unanswered',
                                 'status', 'submitted_at', 'updated_at'])


class TestAnswer(models.Model):
    """What the student put down for one question, and what it was worth.

    Every question in a submitted section gets a row, including the ones left alone, so the paper
    can be read back in full afterwards.
    """

    section_attempt = models.ForeignKey(TestSectionAttempt, on_delete=models.CASCADE, related_name='answers')
    assessment_question = models.ForeignKey(AssessmentQuestion, on_delete=models.PROTECT, related_name='answers')
    selected_option = models.ForeignKey(QuestionOption, on_delete=models.PROTECT, null=True, blank=True, related_name='answers')
    is_correct = models.BooleanField(default=False)
    marks_awarded = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text='The question mark when right, the negative mark when wrong and the section carries it, otherwise zero')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Test Answer'
        verbose_name_plural = 'Test Answers'
        ordering = ['assessment_question__order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['section_attempt', 'assessment_question'], name='unique_answer_per_question')
        ]

    def __str__(self):
        return f"{self.section_attempt} - {self.assessment_question.question.question_code}"


def score_answer(question, selected_option, allow_negative_marking):
    """What one answer is worth.

    Right earns the question's own mark. Wrong costs the question's negative mark, but only where
    the section was set up to carry negative marking. Left alone is worth nothing either way.
    """
    if selected_option is None:
        return False, Decimal('0.00')

    if selected_option.right_option:
        return True, Decimal(question.correct_answer_mark)

    if allow_negative_marking:
        return False, -Decimal(question.negative_mark)

    return False, Decimal('0.00')
