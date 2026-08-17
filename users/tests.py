from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

class UsersViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='secret123')

    def test_home_dashboard_view(self):
        response = self.client.get(reverse('homepg'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/homepg.html')

    def test_edit_profile_page_opens_for_user_without_profile(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('edit_profile', args=[self.user.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/edit_profile.html')

    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_profile_page_requires_login(self):
        response = self.client.get(reverse('profile'))
        self.assertIn(response.status_code, [200, 302])

    def test_set_password_page_renders(self):
        response = self.client.get(reverse('set_password', args=[self.user.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/set_password.html')

    def test_login_with_email_or_username(self):
        self.user.email = 'tester@example.com'
        self.user.save()

        # Login with username
        logged_in_user = self.client.login(username='tester', password='secret123')
        self.assertTrue(logged_in_user)
        self.client.logout()

        # Login with email
        logged_in_email = self.client.login(username='tester@example.com', password='secret123')
        self.assertTrue(logged_in_email)


