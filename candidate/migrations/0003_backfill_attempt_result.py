from decimal import Decimal

from django.db import migrations


def backfill_results(apps, schema_editor):
    """Fills in the overall score and the Pass or Fail for papers sat before they were saved.

    The pass mark is taken off the assessment as it stands now, since the sitting itself never
    recorded one. Papers still open are left Pending, which is what they are.
    """
    TestAttempt = apps.get_model('candidate', 'TestAttempt')

    attempts = TestAttempt.objects.select_related('session__assessment').all()
    for attempt in attempts:
        attempt.passing_marks = attempt.session.assessment.passing_marks
        attempt.percentage = (
            (Decimal(attempt.total_marks) / Decimal(attempt.max_marks) * 100).quantize(Decimal('0.01'))
            if attempt.max_marks else Decimal('0.00')
        )

        if attempt.status == 'Submitted':
            attempt.result = 'Pass' if Decimal(attempt.total_marks) >= Decimal(attempt.passing_marks) else 'Fail'
        else:
            attempt.result = 'Pending'

        attempt.save(update_fields=['passing_marks', 'percentage', 'result'])


def clear_results(apps, schema_editor):
    """Nothing to undo: the columns themselves go with the migration that added them."""


class Migration(migrations.Migration):

    dependencies = [
        ('candidate', '0002_testattempt_passing_marks_testattempt_percentage_and_more'),
        ('assessment', '0002_assessment_passing_marks'),
    ]

    operations = [
        migrations.RunPython(backfill_results, clear_results),
    ]
