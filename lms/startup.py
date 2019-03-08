"""
Module for code that should run during LMS startup
"""

import logging

import django
from django.conf import settings

# Force settings to run so that the python path is modified

settings.INSTALLED_APPS  # pylint: disable=pointless-statement

from openedx.core.lib.django_startup import autostartup
from openedx.core.release import doc_version
import analytics

from openedx.core.djangoapps.monkey_patch import django_db_models_options

import xmodule.x_module
import lms_xblock.runtime

from startup_configurations.validate_config import validate_lms_config
from openedx.core.djangoapps.theming.core import enable_theming
from openedx.core.djangoapps.theming.helpers import is_comprehensive_theming_enabled

# edx notifications related imports
from openedx.core.djangoapps.course_groups.scope_resolver import CourseGroupScopeResolver
from student.scope_resolver import CourseEnrollmentsScopeResolver, StudentEmailScopeResolver
from edx_solutions_projects.scope_resolver import GroupProjectParticipantsScopeResolver
from edx_notifications.scopes import register_user_scope_resolver
from edx_notifications.namespaces import register_namespace_resolver
from util.namespace_resolver import CourseNamespaceResolver
from edx_notifications import startup

from microsite_configuration import microsite

log = logging.getLogger(__name__)


def run():
    """
    Executed during django startup
    """
    django_db_models_options.patch()

    # To override the settings before executing the autostartup() for python-social-auth
    if settings.FEATURES.get('ENABLE_THIRD_PARTY_AUTH', False):
        enable_third_party_auth()

    # Comprehensive theming needs to be set up before django startup,
    # because modifying django template paths after startup has no effect.
    if is_comprehensive_theming_enabled():
        enable_theming()

    # We currently use 2 template rendering engines, mako and django_templates,
    # and one of them (django templates), requires the directories be added
    # before the django.setup().
    microsite.enable_microsites_pre_startup(log)

    django.setup()

    autostartup()

    add_mimetypes()

    # Mako requires the directories to be added after the django setup.
    microsite.enable_microsites(log)

    # Initialize Segment analytics module by setting the write_key.
    if settings.LMS_SEGMENT_KEY:
        analytics.write_key = settings.LMS_SEGMENT_KEY

    # register any dependency injections that we need to support in edx_proctoring
    # right now edx_proctoring is dependent on the openedx.core.djangoapps.credit
    if settings.FEATURES.get('ENABLE_SPECIAL_EXAMS'):
        # Import these here to avoid circular dependencies of the form:
        # edx-platform app --> DRF --> django translation --> edx-platform app
        from edx_proctoring.runtime import set_runtime_service
        from lms.djangoapps.instructor.services import InstructorService
        from openedx.core.djangoapps.credit.services import CreditService
        set_runtime_service('credit', CreditService())

        # register InstructorService (for deleting student attempts and user staff access roles)
        set_runtime_service('instructor', InstructorService())

    if settings.FEATURES.get('ENABLE_NOTIFICATIONS', False):
        startup_notification_subsystem()

    if settings.FEATURES.get('EDX_SOLUTIONS_API', False) and \
            settings.FEATURES.get('DISABLE_SOLUTIONS_APPS_SIGNALS', False):
        disable_solutions_apps_signals()

    connect_completion_signal()

    # In order to allow modules to use a handler url, we need to
    # monkey-patch the x_module library.
    # TODO: Remove this code when Runtimes are no longer created by modulestores
    # https://openedx.atlassian.net/wiki/display/PLAT/Convert+from+Storage-centric+runtimes+to+Application-centric+runtimes
    xmodule.x_module.descriptor_global_handler_url = lms_xblock.runtime.handler_url
    xmodule.x_module.descriptor_global_local_resource_url = lms_xblock.runtime.local_resource_url

    # Set the version of docs that help-tokens will go to.
    settings.HELP_TOKENS_LANGUAGE_CODE = settings.LANGUAGE_CODE
    settings.HELP_TOKENS_VERSION = doc_version()

    # validate configurations on startup
    validate_lms_config(settings)


def connect_completion_signal():
    """
    Temporary mechanism to connect the completion signal from edx/completion.
    Should happen automatically in Hawthorn via pluggable apps.
    """
    from completion.handlers import scorable_block_completion
    from lms.djangoapps.grades.signals.signals import PROBLEM_WEIGHTED_SCORE_CHANGED
    PROBLEM_WEIGHTED_SCORE_CHANGED.connect(scorable_block_completion)


def add_mimetypes():
    """
    Add extra mimetypes. Used in xblock_resource.

    If you add a mimetype here, be sure to also add it in cms/startup.py.
    """
    import mimetypes

    mimetypes.add_type('application/vnd.ms-fontobject', '.eot')
    mimetypes.add_type('application/x-font-opentype', '.otf')
    mimetypes.add_type('application/x-font-ttf', '.ttf')
    mimetypes.add_type('application/font-woff', '.woff')


def enable_microsites():
    """
    Calls the enable_microsites function in the microsite backend.
    Here for backwards compatibility
    """
    microsite.enable_microsites(log)


def enable_third_party_auth():
    """
    Enable the use of third_party_auth, which allows users to sign in to edX
    using other identity providers. For configuration details, see
    common/djangoapps/third_party_auth/settings.py.
    """

    from third_party_auth import settings as auth_settings
    auth_settings.apply_settings(settings)


def disable_solutions_apps_signals():
    """
    Disables signals receivers in solutions apps
    """
    from edx_solutions_api_integration.test_utils import SignalDisconnectTestMixin
    SignalDisconnectTestMixin.disconnect_signals()


def startup_notification_subsystem():
    """
    Initialize the Notification subsystem
    """
    try:
        startup.initialize()

        # register the scope resolvers that the runtime will be providing
        # to edx-notifications
        register_user_scope_resolver('course_enrollments', CourseEnrollmentsScopeResolver())
        register_user_scope_resolver('course_group', CourseGroupScopeResolver())
        register_user_scope_resolver('group_project_participants', GroupProjectParticipantsScopeResolver())
        register_user_scope_resolver('group_project_workgroup', GroupProjectParticipantsScopeResolver())
        register_user_scope_resolver('user_email_resolver', StudentEmailScopeResolver())

        # register namespace resolver
        register_namespace_resolver(CourseNamespaceResolver())
    except Exception, ex:
        # Note this will fail when we try to run migrations as manage.py will call startup.py
        # and startup.initialze() will try to manipulate some database tables.
        # We need to research how to identify when we are being started up as part of
        # a migration script
        log.error(
            'There was a problem initializing notifications subsystem. '
            'This could be because the database tables have not yet been created and '
            './manage.py lms syncdb needs to run setup.py. Error was "{err_msg}". Continuing...'.format(err_msg=str(ex))
        )
