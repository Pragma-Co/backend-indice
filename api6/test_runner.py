from django.test import TransactionTestCase
from django.test.runner import DiscoverRunner


class AllDatabasesRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        TransactionTestCase.databases = "__all__"
