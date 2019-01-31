"""
Test cases for image processing Celery tasks
"""
import os

from django.test import TestCase
from django.test.utils import override_settings
import ddt
import mock

from openedx.core.djangolib.testing.utils import skip_unless_lms
from openedx.core.djangoapps.user_api.accounts.image_helpers import get_profile_image_names

from ..tasks import delete_profile_images


@ddt.ddt
@skip_unless_lms
class TestDeleteProfileImages(TestCase):
    """
    Test delete_profile_images task
    """
    @ddt.data(
        (['user_a', 'user_b', 'user_c'])
    )
    @override_settings(CELERY_ALWAYS_EAGER=True)
    @mock.patch('openedx.core.djangoapps.profile_images.tasks.remove_profile_images')
    def test_delete(self, usernames, mock_remove_profile_images):
        """
        Test that remove_profile_images is called with the expected list
        of profile image filenames for all users.
        """
        delete_profile_images.delay(usernames)

        expected_names = []
        for username in usernames:
            expected_names += get_profile_image_names(username).values()

        # flatten the list of called arguments
        deleted_names = []
        called_args = [v[0][0].values() for v in mock_remove_profile_images.call_args_list]
        for args in called_args:
            deleted_names.extend(args)

        self.assertSetEqual(set(expected_names), set(deleted_names))
