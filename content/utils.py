from content.models import *


def snapshot_question(question):
    """A plain JSON friendly picture of a question, used to work out what changed."""
    return {
        'section': question.section.name if question.section_id else None,
        'question_code': question.question_code,
        'question_text': question.question_text,
        'difficulty_level': question.get_difficulty_level_display(),
        'correct_answer_mark': str(question.correct_answer_mark),
        'negative_mark': str(question.negative_mark),
        'status': question.status,
        'options': [
            {'option_text': option.option_text, 'right_option': option.right_option}
            for option in question.options.all()
        ],
    }


def diff_snapshots(before, after):
    """{field: {'old': ..., 'new': ...}} for every field whose value actually moved."""
    changes = {}

    for field, new_value in after.items():
        old_value = before.get(field)
        if old_value != new_value:
            changes[field] = {'old': old_value, 'new': new_value}

    return changes


def log_question_history(question, action, user, changes=None, question_code=None):
    return QuestionHistory.objects.create(
        question=question,
        question_code=question_code or (question.question_code if question else ''),
        action=action,
        changes=changes or {},
        changed_by=user if user and user.is_authenticated else None,
        changed_by_email=user.email if user and user.is_authenticated else '',
    )
