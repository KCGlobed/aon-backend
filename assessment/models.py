from django.conf import settings
from django.db import models
from django.db.models import Sum
from content.models import Question, Sections


class Assessment(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration = models.PositiveIntegerField(help_text='Total duration of the test in minutes')
    number_of_questions = models.PositiveIntegerField(default=0, help_text='Kept in step with the pattern: the questions its sections add up to')
    total_marks = models.DecimalField(max_digits=7, decimal_places=2, default=0, help_text='Kept in step with the pattern: the marks the selected questions carry')
    instructions = models.TextField(blank=True)
    status = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assessments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Assessment'
        verbose_name_plural = 'Assessments'

    def __str__(self):
        return self.name

    def sync_totals(self):
        """The totals follow the question pattern: how many questions its sections ask for, and the
        marks the selected questions themselves carry."""
        self.number_of_questions = sum(section.number_of_questions for section in self.sections.all())
        self.total_marks = self.assessment_questions.aggregate(
            total=Sum('question__correct_answer_mark'))['total'] or 0
        self.save(update_fields=['number_of_questions', 'total_marks', 'updated_at'])


DIFFICULTY_FIELDS = {
    'easy_questions': Question.DifficultyLevel.EASY,
    'medium_questions': Question.DifficultyLevel.MEDIUM,
    'hard_questions': Question.DifficultyLevel.HARD,
}


class AssessmentSection(models.Model):

    class SelectionType(models.TextChoices):
        MANUAL = 'Manual', 'Manual'
        RANDOM = 'Random', 'Random'

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='sections')
    section = models.ForeignKey(Sections, on_delete=models.PROTECT, related_name='assessment_sections')
    number_of_questions = models.PositiveIntegerField()
    allow_negative_marking = models.BooleanField(default=False, help_text="Whether a wrong answer costs the question's own negative mark")
    easy_questions = models.PositiveIntegerField(default=0, help_text='How many of the questions must be Easy')
    medium_questions = models.PositiveIntegerField(default=0, help_text='How many of the questions must be Medium')
    hard_questions = models.PositiveIntegerField(default=0, help_text='How many of the questions must be Hard')
    selection_type = models.CharField(max_length=10, choices=SelectionType.choices, default=SelectionType.RANDOM, help_text='Manual: the admin picks the questions. Random: picked from the question bank.')
    order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Assessment Section'
        verbose_name_plural = 'Assessment Sections'
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['assessment', 'section'], name='unique_section_per_assessment')
        ]

    def __str__(self):
        return f"{self.assessment.name} - {self.section.section_id}"

    @property
    def total_marks(self):
        """What this section is worth, read off the questions it holds."""
        return sum(assessment_question.question.correct_answer_mark
                   for assessment_question in self.questions.all())

    @property
    def difficulty_distribution(self):
        """{difficulty level: how many questions} for every level the admin asked for. Empty when
        no split was given, which means questions of any difficulty will do."""
        distribution = {}
        for field, difficulty_level in DIFFICULTY_FIELDS.items():
            count = getattr(self, field)
            if count:
                distribution[difficulty_level] = count

        return distribution


class AssessmentQuestion(models.Model):
    """A question held by one section of an assessment, whether it was picked by hand or at random."""

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='assessment_questions')
    assessment_section = models.ForeignKey(AssessmentSection, on_delete=models.CASCADE, related_name='questions')
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name='assessment_questions')
    order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Assessment Question'
        verbose_name_plural = 'Assessment Questions'
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['assessment', 'question'], name='unique_question_per_assessment')
        ]

    def __str__(self):
        return f"{self.assessment.name} - {self.question.question_code}"
