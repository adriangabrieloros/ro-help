from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User, Group
from django.utils.translation import ugettext_lazy as _
from django.utils.html import format_html
from django.utils import timezone
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from admin_auto_filters.filters import AutocompleteFilter

from .models import NGO, NGONeed, PersonalRequest, NGOHelper, ResourceTag, RegisterNGORequest


class NGOFilter(AutocompleteFilter):
    title = "NGO"
    field_name = "ngo"


class ActiveNGONeedFilter(SimpleListFilter):
    title = _("active")
    parameter_name = "ngoneed__resolved_on"

    def lookups(self, request, model_admin):
        return [("active", "active"), ("resolved", "resolved"), ("closed", "closed")]

    def queryset(self, request, queryset):
        value = str(self.value()).lower() if self.value() else ""

        if value == "active":
            return queryset.active()

        if value == "resolved":
            return queryset.resolved()

        if value == "closed":
            return queryset.closed()

        return queryset


@admin.register(NGO)
class NGOAdmin(admin.ModelAdmin):
    icon_name = 'home_work'
    list_per_page = 25

    list_display = ("name", "email", "phone", "city", "county", "created")
    list_filter = (
        "city",
        "county",
    )
    search_fields = (
        "name",
        "email",
    )

    def get_queryset(self, request):
        user = request.user
        qs = super(NGOAdmin, self).get_queryset(request)
        if 'Admin' not in user.groups.values_list('name', flat=True):
            return qs.filter(users__in=[user])
        else:
            return qs

    def get_readonly_fields(self, request, obj=None):
        if obj:
            user = request.user
            if 'Admin' not in user.groups.values_list('name', flat=True):
                return ["users"]
        return []


class NGOHelperInline(admin.TabularInline):
    model = NGOHelper
    fields = ("name", "email", "message", "phone", "read")
    can_delete = False
    can_add = False
    verbose_name_plural = _("Helpers")
    readonly_fields = ["name", "email", "message", "phone"]
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False

    # def get_readonly_fields(self, request, obj=None):
    #     # if obj:
    #         # if obj.factura.exists():
    #             # return self.get_fields(request, obj)
    #     return ["name", "email", "message", "phone"]


@admin.register(NGONeed)
class NGONeedAdmin(admin.ModelAdmin):
    icon_name = 'transfer_within_a_station'
    list_per_page = 25

    list_display = ("title", "ngo", "urgency", "kind", "created",
                    "responses", "resolved_on", "closed_on")
    list_filter = (NGOFilter, ActiveNGONeedFilter, "urgency",
                   "kind", "ngo__city", "ngo__county")
    readonly_fields = ["resolved_on", "closed_on"]
    inlines = [NGOHelperInline]
    actions = ["resolve_need", "close_need"]
    search_fields = (
        "ngo__name",
        "ngo__email",
    )

    class Media:
        pass

    def get_queryset(self, request):
        user = request.user
        qs = super(NGONeedAdmin, self).get_queryset(request)
        if 'Admin' not in user.groups.values_list('name', flat=True):
            return qs.filter(ngo__users__in=[user])
        else:
            return qs

    def get_form(self, request, obj=None, **kwargs):
        form = super(NGONeedAdmin, self).get_form(request, obj, **kwargs)
        user = request.user
        if 'Admin' not in user.groups.values_list('name', flat=True):
            ngos_pks = user.ngos.values_list('pk', flat=True)
            try:
                form.base_fields['ngo'].queryset = NGO.objects.filter(
                    pk__in=ngos_pks)
            except:
                pass
        return form

    def get_changeform_initial_data(self, request):
        user = request.user
        if user.ngos.count() == 1:
            return {'ngo': user.ngos.all()[0].pk}

    def responses(self, obj):
        all_helpers = obj.helpers.count()
        new_helpers = obj.helpers.filter(read=False).count()
        if new_helpers:
            html = f"<span><a href='/admin/hub/ngoneed/{obj.pk}/change/'>{all_helpers} ({new_helpers} new)</a></span>"
        else:
            html = f"<span><a href='/admin/hub/ngoneed/{obj.pk}/change/'>{all_helpers}</a></span>"
        return format_html(html)

    responses.short_description = _("Helpers")

    def resolve_need(self, request, queryset):
        c = 0
        for need in queryset:
            need.resolved_on = timezone.now()
            need.save()
            c += 1

        if c == 1:
            user_msg = f"{c} need resolved"
        else:
            user_msg = f"{c} needs resolved"
        return self.message_user(request, user_msg, level=messages.INFO)

    resolve_need.short_description = _("Resolve need")

    def close_need(self, request, queryset):
        c = 0
        for need in queryset:
            need.closed_on = timezone.now()
            need.save()
            c += 1

        if c == 1:
            user_msg = f"{c} need closed"
        else:
            user_msg = f"{c} needs closed"
        return self.message_user(request, user_msg, level=messages.INFO)

    close_need.short_description = _("Close need")


@admin.register(ResourceTag)
class ResourceTagAdmin(admin.ModelAdmin):
    icon_name = "filter_vintage"


# @admin.register(PersonalRequest)
# class PersonalRequestAdmin(admin.ModelAdmin):
#     icon_name = "face"


from django.core.mail import EmailMultiAlternatives
@admin.register(RegisterNGORequest)
class RegisterNGORequestAdmin(admin.ModelAdmin):
    icon_name = "add_circle"
    list_display = ["name", "county", "city", "active", "resolved_on"]
    actions = ["create_account"]
    readonly_fields = ["active", "resolved_on"]

    def create_account(self, request, queryset):
        c = 0
        ngo_group = Group.objects.get(name="ONG")
        for ngo in queryset:
            if ngo.resolved_on == None:
                user, created = User.objects.get_or_create(username=ngo.email)
                if created:
                    user.first_name = " ".join(ngo.contact_name.split(" ")[0:-1])
                    user.last_name = ngo.contact_name.split(" ")[-1]
                    user.email = ngo.email
                    user.set_password(get_random_string())
                    user.is_staff = True
                    user.groups.add(ngo_group)
                    user.save()
                    reset_form = PasswordResetForm({'email': user.email})
                    assert reset_form.is_valid()
                    reset_form.save(
                        request=request,
                        use_https=request.is_secure(),
                        subject_template_name='registration/password_reset_subject.txt',
                        email_template_name='registration/password_reset_email.html',
                    )
                new_ngo, created = NGO.objects.get_or_create(
                    name=ngo.name,
                    description=ngo.description,
                    email=ngo.email,
                    phone=ngo.contact_phone,
                    avatar=ngo.avatar,
                    address=ngo.address,
                    city=ngo.city,
                    county=ngo.county
                    )
                new_ngo.users.add(user)   
                c += 1

                ngo.resolved_on = timezone.now()
                ngo.active = True
                ngo.save()

        if c == 1:
            user_msg = f"{c} ngo activated"
        else:
            user_msg = f"{c} ngos activated"
        return self.message_user(request, user_msg, level=messages.INFO)

    create_account.short_description = _("Create account")


