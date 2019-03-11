"""
Run these tests @ Devstack:
    paver test_system -s lms --fast_test --test_id=lms/djangoapps/courseware/management/tests/test_delete_course_references.py
"""
from datetime import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.test.utils import override_settings

from courseware.management.commands import delete_course_references
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase, mixed_store_config
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from edx_solutions_api_integration.models import (
    GroupProfile,
    CourseGroupRelationship,
    CourseContentGroupRelationship
)
from edx_solutions_projects import models as project_models
from gradebook import models as gradebook_models
from progress import models as progress_models

MODULESTORE_CONFIG = mixed_store_config(settings.COMMON_TEST_DATA_ROOT, {})


@override_settings(MODULESTORE=MODULESTORE_CONFIG)
class DeleteCourseReferencesTests(ModuleStoreTestCase):
    """
    Test suite for course reference deletion script
    """

    def setUp(self):
        super(DeleteCourseReferencesTests, self).setUp()
        # Create a course to work with
        self.course = CourseFactory.create(
            start=datetime(2014, 6, 16, 14, 30),
            end=datetime(2020, 1, 16)
        )
        test_data = '<html>{}</html>'.format(str(uuid.uuid4()))

        self.chapter = ItemFactory.create(
            category="chapter",
            parent_location=self.course.location,
            data=test_data,
            due=datetime(2014, 5, 16, 14, 30),
            display_name="Overview"
        )

    def test_delete_course_references_edx_solutions_api_integration(self):
        """
        Test the workflow
        """
        # Set up the data to be removed
        group = Group.objects.create(name='TestGroup')
        group_profile = GroupProfile.objects.create(group=group)

        course_group_relationship = CourseGroupRelationship.objects.create(
            course_id=unicode(self.course.id),
            group=group
        )
        content_group_relationship = CourseContentGroupRelationship.objects.create(
            course_id=unicode(self.course.id),
            content_id=unicode(self.chapter.location),
            group_profile=group_profile
        )

        self.assertEqual(CourseGroupRelationship.objects.filter(id=course_group_relationship.id).count(), 1)
        self.assertEqual(CourseContentGroupRelationship.objects.filter(id=content_group_relationship.id).count(), 1)

        # Run the data migration
        delete_course_references.Command().handle(unicode(self.course.id), 'commit')

        # Validate that the course references were removed
        self.assertEqual(CourseGroupRelationship.objects.filter(id=course_group_relationship.id).count(), 0)
        self.assertEqual(CourseContentGroupRelationship.objects.filter(id=content_group_relationship.id).count(), 0)

    def test_delete_course_references_projects(self):
        project = project_models.Project.objects.create(
            course_id=unicode(self.course.id),
            content_id=unicode(self.chapter.location)
        )
        workgroup = project_models.Workgroup.objects.create(
            project=project,
            name='TEST WORKGROUP'
        )
        workgroup_user = project_models.WorkgroupUser.objects.create(
            workgroup=workgroup,
            user=self.user
        )
        workgroup_review = project_models.WorkgroupReview.objects.create(
            workgroup=workgroup,
            reviewer=self.user,
            question='test',
            answer='test',
            content_id=unicode(self.chapter.location),
        )
        workgroup_peer_review = project_models.WorkgroupPeerReview.objects.create(
            workgroup=workgroup,
            user=self.user,
            reviewer=self.user,
            question='test',
            answer='test',
            content_id=unicode(self.chapter.location),
        )
        workgroup_submission = project_models.WorkgroupSubmission.objects.create(
            workgroup=workgroup,
            user=self.user,
            document_id='test',
            document_url='test',
            document_mime_type='test',
        )
        workgroup_submission_review = project_models.WorkgroupSubmissionReview.objects.create(
            submission=workgroup_submission,
            reviewer=self.user,
            question='test',
            answer='test',
            content_id=unicode(self.chapter.location),
        )

        self.assertEqual(project_models.Project.objects.filter(id=project.id).count(), 1)
        self.assertEqual(project_models.Workgroup.objects.filter(id=workgroup.id).count(), 1)
        self.assertEqual(project_models.WorkgroupUser.objects.filter(id=workgroup_user.id).count(), 1)
        self.assertEqual(project_models.WorkgroupReview.objects.filter(id=workgroup_review.id).count(), 1)
        self.assertEqual(project_models.WorkgroupSubmission.objects.filter(id=workgroup_submission.id).count(), 1)
        self.assertEqual(project_models.WorkgroupSubmissionReview.objects.filter(id=workgroup_submission_review.id).count(), 1)
        self.assertEqual(project_models.WorkgroupPeerReview.objects.filter(id=workgroup_peer_review.id).count(), 1)

        # Run the course deletion command
        delete_course_references.Command().handle(unicode(self.course.id), 'commit')

        # Validate that the course references were removed
        self.assertEqual(project_models.Project.objects.filter(id=project.id).count(), 0)
        self.assertEqual(project_models.Workgroup.objects.filter(id=workgroup.id).count(), 0)
        self.assertEqual(project_models.WorkgroupUser.objects.filter(id=workgroup_user.id).count(), 0)
        self.assertEqual(project_models.WorkgroupReview.objects.filter(id=workgroup_review.id).count(), 0)
        self.assertEqual(project_models.WorkgroupSubmission.objects.filter(id=workgroup_submission.id).count(), 0)
        self.assertEqual(project_models.WorkgroupSubmissionReview.objects.filter(id=workgroup_submission_review.id).count(), 0)
        self.assertEqual(project_models.WorkgroupPeerReview.objects.filter(id=workgroup_peer_review.id).count(), 0)

    def test_delete_course_references_gradebook(self):
        gradebook = gradebook_models.StudentGradebook.objects.create(
            user=self.user,
            course_id=unicode(self.course.id),
            grade=0.65,
            proforma_grade=0.75
        )

        self.assertEqual(gradebook_models.StudentGradebook.objects.filter(id=gradebook.id).count(), 1)
        self.assertEqual(gradebook_models.StudentGradebookHistory.objects.filter(user=self.user, course_id=self.course.id).count(), 1)

        # Run the course deletion command
        delete_course_references.Command().handle(unicode(self.course.id), 'commit')

        # Validate that the course references were removed
        self.assertEqual(gradebook_models.StudentGradebook.objects.filter(id=gradebook.id).count(), 0)
        self.assertEqual(gradebook_models.StudentGradebookHistory.objects.filter(user=self.user, course_id=self.course.id).count(), 0)
