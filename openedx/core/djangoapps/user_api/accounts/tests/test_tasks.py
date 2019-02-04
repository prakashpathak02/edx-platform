"""
Test cases for Celery tasks
"""
import os

from django.test import TestCase
from django.test.utils import override_settings
import mock

from submissions.models import StudentItem, Submission
from student.models import AnonymousUserId
from student.tests.factories import UserFactory
from openedx.core.djangolib.testing.utils import skip_unless_lms

from ..tasks import delete_staff_graded_assignment_files, get_users_sga_submissions


@skip_unless_lms
class TestDeleteStaffGradedAssignmentFilesTest(TestCase):
    """
    Test delete_staff_graded_assignment_files task
    """
    def setUp(self):
        super(TestDeleteStaffGradedAssignmentFilesTest, self).setUp()
        self.user = UserFactory(username='test', email='test@example.com', password='test')
        self.other_user = UserFactory(username='test2', email='test2@example.com', password='test')

        user_anon_id = AnonymousUserId.objects.create(user=self.user, anonymous_user_id='user_uid')
        other_user_anon_id = AnonymousUserId.objects.create(user=self.other_user, anonymous_user_id='other_user_uid')

        user_item1 = StudentItem.objects.create(
            student_id=user_anon_id.anonymous_user_id,
            item_type='sga',
            course_id='some-course',
            item_id='i4x://some-course+some-module/edx_sga/item-1'
        )
        user_item2 = StudentItem.objects.create(
            student_id=user_anon_id.anonymous_user_id,
            item_type='misc',
            course_id='some-course',
            item_id='some-course+some-module/misc/item-2'
        )
        other_user_item1 = StudentItem.objects.create(
            student_id=other_user_anon_id.anonymous_user_id,
            item_type='sga',
            course_id='some-course',
            item_id='i4x://some-course+some-module/edx_sga/item-3'
        )
        other_user_item2 = StudentItem.objects.create(
            student_id=other_user_anon_id.anonymous_user_id,
            item_type='misc',
            course_id='some-course',
            item_id='some-course+some-module/misc/item-4'
        )

        Submission.objects.create(
            student_item=user_item1, attempt_number=1,
            answer={'sha1': 'beef1', 'filename': 'file.txt'}
        )
        Submission.objects.create(
            student_item=user_item2, attempt_number=1,
            answer={'foo': 'bar'}
        )
        Submission.objects.create(
            student_item=other_user_item1, attempt_number=1,
            answer={'sha1': 'beef2', 'filename': 'file.png'}
        )
        Submission.objects.create(
            student_item=user_item2, attempt_number=1,
            answer={'foo': 'bar'}
        )

    def test_get_users_sga_submissions(self):
        """
        Test that only sga submissions for the user are returned.
        """
        submissions = get_users_sga_submissions([self.user.id])
        self.assertEqual(submissions.count(), 1)

    @override_settings(CELERY_ALWAYS_EAGER=True)
    @mock.patch('openedx.core.djangoapps.user_api.accounts.tasks.default_storage')
    def test_delete(self, mock_storage):
        """
        Test that storage.delete is called with the expected list of
        filenames for all users.
        """
        mock_storage.exists.return_value = True

        delete_staff_graded_assignment_files.delay([self.user.id, self.other_user.id])
        expected_files = [
            'some-course+some-module/edx_sga/item-1/beef1.txt',
            'some-course+some-module/edx_sga/item-3/beef2.png',
        ]
        called_args = [v[0][0] for v in mock_storage.delete.call_args_list]
        self.assertSetEqual(set(expected_files), set(called_args))
