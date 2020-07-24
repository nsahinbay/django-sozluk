import hashlib

from contextlib import suppress
from smtplib import SMTPException

from django.contrib import messages as notifications
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import View
from django.views.generic.edit import FormView

from ..forms.auth import ChangeEmailForm, LoginForm, ResendEmailForm, SignUpForm, TerminateAccountForm
from ..models import AccountTerminationQueue, Author, PairedSession, UserVerification
from ..utils import time_threshold
from ..utils.email import send_email_confirmation
from ..utils.mixins import PasswordConfirmMixin
from ..utils.settings import DISABLE_NOVICE_QUEUE, FROM_EMAIL


class Login(LoginView):
    form_class = LoginForm
    template_name = "dictionary/registration/login.html"

    def form_valid(self, form):
        remember_me = form.cleaned_data.get("remember_me", False)

        if remember_me:
            self.request.session.set_expiry(1209600)  # 2 weeks
        else:
            self.request.session.set_expiry(7200)

        # Check if the user cancels account termination.
        with suppress(AccountTerminationQueue.DoesNotExist):
            AccountTerminationQueue.objects.get(author=form.get_user()).delete()
            notifications.info(self.request, _("welcome back. your account was reactivated."), extra_tags="persistent")

        notifications.info(self.request, _("successfully logged in, dear"))
        return super().form_valid(form)


class Logout(LogoutView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            notifications.info(request, _("successfully logged out, dear"))
        return super().dispatch(request)


class SignUp(FormView):
    form_class = SignUpForm
    template_name = "dictionary/registration/signup.html"

    def form_valid(self, form):
        user = form.save(commit=False)
        user.username = form.cleaned_data.get("username").lower()
        user.birth_date = form.cleaned_data.get("birth_date")
        user.gender = form.cleaned_data.get("gender")

        if DISABLE_NOVICE_QUEUE:
            # Make the user an actual author
            user.application_status = Author.APPROVED
            user.is_novice = False

        user.save()
        send_email_confirmation(user, user.email)
        notifications.info(
            self.request,
            _(
                "a confirmation link was sent your e-mail address. by following"
                " this link you can activate and login into your account."
            ),
        )
        return redirect("login")


class ConfirmEmail(View):
    success = False
    template_name = "dictionary/registration/email/confirmation_result.html"

    def get(self, request, token):
        try:
            token_hashed = hashlib.blake2b(token.bytes).hexdigest()
            verification_object = UserVerification.objects.get(
                verification_token=token_hashed, expiration_date__gte=time_threshold(hours=24)
            )
        except UserVerification.DoesNotExist:
            return self.render_to_response()

        author = verification_object.author

        if not author.is_active:
            author.is_active = True
            author.save()
        else:
            author.email = verification_object.new_email
            author.save()

        self.success = True
        UserVerification.objects.filter(author=author).delete()
        return self.render_to_response()

    def render_to_response(self):
        return render(self.request, self.template_name, context={"success": self.success})


class ResendEmailConfirmation(FormView):
    form_class = ResendEmailForm
    template_name = "dictionary/registration/email/resend_form.html"

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        author = Author.objects.get(email=email)
        send_email_confirmation(author, email)
        notifications.info(
            self.request,
            _(
                "a confirmation link was sent your e-mail address. by following"
                " this link you can activate and login into your account."
            ),
        )
        return redirect("login")


class ChangePassword(LoginRequiredMixin, PasswordChangeView):
    success_url = reverse_lazy("user_preferences")
    template_name = "dictionary/user/preferences/password.html"

    def form_valid(self, form):
        message = _(
            "dear %(username)s, your password was changed. If you aware of this"
            " action, there is nothing to worry about. If you didn't do such"
            " action, you can use your e-mail to recover your account."
        ) % {"username": self.request.user.username}

        # Send a 'your password has been changed' message to ensure security.
        try:
            self.request.user.email_user(_("your password was changed."), message, FROM_EMAIL)
        except SMTPException:
            notifications.error(self.request, _("we couldn't handle your request. try again later."))
            return super().form_invalid(form)

        notifications.info(self.request, _("your password was changed"))
        return super().form_valid(form)


class ChangeEmail(LoginRequiredMixin, PasswordConfirmMixin, FormView):
    template_name = "dictionary/user/preferences/email.html"
    form_class = ChangeEmailForm
    success_url = reverse_lazy("user_preferences")

    def form_valid(self, form):
        send_email_confirmation(self.request.user, form.cleaned_data.get("email1"))
        notifications.info(
            self.request, _("your e-mail will be changed after the confirmation."), extra_tags="persistent"
        )
        return redirect(self.success_url)


class TerminateAccount(LoginRequiredMixin, PasswordConfirmMixin, FormView):
    template_name = "dictionary/user/preferences/terminate.html"
    form_class = TerminateAccountForm
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        message = _(
            "dear %(username)s, your account is now frozen. if you have chosen"
            " to delete your account, it will be deleted permanently after 5 days."
            " in case you log in before this time passes, your account will be"
            " reactivated. if you only chose to freeze your account, you may"
            " log in any time to reactivate your account."
        ) % {"username": self.request.user.username}

        # Send a message to ensure security.
        try:
            self.request.user.email_user(_("your account is now frozen"), message, FROM_EMAIL)
        except SMTPException:
            notifications.error(self.request, _("we couldn't handle your request. try again later."))
            return super().form_invalid(form)

        termination_choice = form.cleaned_data.get("state")
        AccountTerminationQueue.objects.create(author=self.request.user, state=termination_choice)
        # Unlike logout(), this invalidates ALL sessions across devices.
        PairedSession.objects.filter(user=self.request.user).delete()
        notifications.info(self.request, _("your request was taken. farewell."))
        return super().form_valid(form)
