import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('assessment', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Session',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('start_datetime', models.DateTimeField(help_text='When the session opens')),
                ('end_datetime', models.DateTimeField(help_text="Worked out from the start time and the assessment's duration; never given by hand")),
                ('duration', models.PositiveIntegerField(help_text="The assessment's duration in minutes, as it stood when the session was saved")),
                ('instructions', models.TextField(blank=True, help_text="Shown in place of the assessment's own instructions when filled in")),
                ('status', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assessment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sessions', to='assessment.assessment')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Session',
                'verbose_name_plural': 'Sessions',
            },
        ),
        migrations.CreateModel(
            name='SessionStudent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_sent', models.BooleanField(default=False)),
                ('email_sent_at', models.DateTimeField(blank=True, null=True)),
                ('email_error', models.TextField(blank=True, help_text='Why the last invite mail failed; cleared once one gets through')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='students', to='session.session')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assessment_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Session Student',
                'verbose_name_plural': 'Session Students',
                'ordering': ['id'],
            },
        ),
        migrations.AddConstraint(
            model_name='sessionstudent',
            constraint=models.UniqueConstraint(fields=('session', 'student'), name='unique_student_per_session'),
        ),
    ]
