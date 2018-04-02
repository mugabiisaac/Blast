from django.contrib import admin

from smsconfirmation.models import PhoneConfirmation


@admin.register(PhoneConfirmation)
class PhoneConfirmationAdmin(admin.ModelAdmin):
    list_display = ('phone', 'code', 'created_at', 'updated_at',
                    'is_delivered', 'is_confirmed', 'is_actual')
    list_editable = ('is_confirmed', 'is_delivered',)

    class Meta:
        model = PhoneConfirmation
