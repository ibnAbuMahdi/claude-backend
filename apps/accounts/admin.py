from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'username', 'user_type', 'is_verified', 'is_active']
    list_filter = ['user_type', 'is_verified', 'is_active', 'agency', 'fleet_owner']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Stika Profile', {
            'fields': ('user_type', 'phone_number', 'is_verified', 'profile_picture', 
                      'date_of_birth', 'address', 'agency', 'fleet_owner')
        }),
    )

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'preferred_language', 'nin', 'bvn']
    search_fields = ['user__email', 'nin', 'bvn']