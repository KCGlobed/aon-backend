from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from assessment.models import Assessment


class Session(models.Model):
    """A sitting of one assessment: when it opens, and which students are expected.

    The admin picks the test and the moment it starts; when it ends is read off the assessment's
    own duration, so a session can never run longer or shorter than the test it holds.
    """

    class State(models.TextChoices):
        UPCOMING = 'Upcoming', 'Upcoming'
        ONGOING = 'Ongoing', 'Ongoing'
        COMPLETED = 'Completed', 'Completed'

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name='sessions')
    start_datetime = models.DateTimeField(help_text='When the session opens')
    end_datetime = models.DateTimeField(help_text="Worked out from the start time and the assessment's duration; never given by hand")
    duration = models.PositiveIntegerField(help_text="The assessment's duration in minutes, as it stood when the session was saved")
    instructions = models.TextField(blank=True, help_text="Shown in place of the assessment's own instructions when filled in")
    status = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Session'
        verbose_name_plural = 'Sessions'

    def __str__(self):
        return f"{self.name} - {self.assessment.name}"

    def sync_schedule(self):
        """Puts the end time back in step with the start time and the assessment's duration."""
        self.duration = self.assessment.duration
        self.end_datetime = self.start_datetime + timedelta(minutes=self.duration)

    @property
    def state(self):
        """Where the session stands against the clock right now."""
        now = timezone.now()
        if now < self.start_datetime:
            return self.State.UPCOMING

        if now > self.end_datetime:
            return self.State.COMPLETED

        return self.State.ONGOING

    @property
    def has_started(self):
        return timezone.now() >= self.start_datetime


class SessionStudent(models.Model):
    """One student expected at a session, along with how their invite mail went."""

    class EmailStatus(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        SENT = 'Sent', 'Sent'
        FAILED = 'Failed', 'Failed'

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='students')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assessment_sessions')
    email_status = models.CharField(max_length=10, choices=EmailStatus.choices, default=EmailStatus.PENDING,
                                    help_text='Pending until the invite has actually left the mail server')
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.TextField(blank=True, help_text='Why the last invite mail failed; cleared once one gets through')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Session Student'
        verbose_name_plural = 'Session Students'
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['session', 'student'], name='unique_student_per_session')
        ]

    def __str__(self):
        return f"{self.session.name} - {self.student.email}"

    def mark_email_sent(self):
        self.email_status = self.EmailStatus.SENT
        self.email_sent = True
        self.email_sent_at = timezone.now()
        self.email_error = ''
        self.save(update_fields=['email_status', 'email_sent', 'email_sent_at', 'email_error', 'updated_at'])

    def mark_email_failed(self, reason):
        self.email_status = self.EmailStatus.FAILED
        self.email_sent = False
        self.email_error = str(reason)[:1000]
        self.save(update_fields=['email_status', 'email_sent', 'email_error', 'updated_at'])
