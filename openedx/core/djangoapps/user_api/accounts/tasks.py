"""
This file contains celery tasks for user accounts
"""
from __future__ import absolute_import
import os.path

from django.contrib.auth.models import User
from django.core.files.storage import default_storage

from celery.task import task
from celery.utils.log import get_task_logger

from submissions.models import StudentItem, Submission
from student.models import AnonymousUserId


LOGGER = get_task_logger(__name__)


def get_users_sga_submissions(user_ids):
    """
    Returns a QuerySet of all sga submissions belonging to the list of
    user_ids.
    """
    anonymous_user_ids = AnonymousUserId.objects.filter(
        user__id__in=user_ids
    ).values_list(
        'anonymous_user_id', flat=True
    )
    student_item_ids = StudentItem.objects.filter(
        student_id__in=anonymous_user_ids,
        item_type='sga'
    ).values_list(
        'id', flat=True
    )
    submissions = Submission.objects.filter(
        student_item__id__in=student_item_ids
    )
    return submissions


@task
def delete_staff_graded_assignment_files(user_ids):
    """
    Delete files for staff graded assignments (edx-sga) from storage belonging to user_ids.

    Arguments:
        user_ids: list of user ids
    """
    submissions = get_users_sga_submissions(user_ids)

    for submission in submissions:
        filepath = '{item_id}/{sha1}{ext}'.format(
            item_id=submission.student_item.item_id.replace('i4x://', ''),
            sha1=submission.answer['sha1'],
            ext=os.path.splitext(submission.answer['filename'])[1]
        )
        if default_storage.exists(filepath):
            LOGGER.info('Deleting sga file %s...', filepath)
            default_storage.delete(filepath)
