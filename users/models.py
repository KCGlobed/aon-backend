import uuid
from django.utils import timezone
from django.db import models
from django.contrib.auth.models import BaseUserManager , AbstractBaseUser, PermissionsMixin
from rolepermissions.roles import assign_role
from aon_backend.roles import *

class UserManager(BaseUserManager):
    def create_user(self, email, first_name, last_name, password=None, confirm_password=None, phone=None):
        if not email:
            raise ValueError('Users must have an email address')

        user = self.model(
            email=self.normalize_email(email.lower()),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
        )

        user.set_password(password)
        user.save(using=self._db)
        
        return user
    
    def create_social_user(self, email, name, social_id, social_type):
        if not email:
            raise ValueError('Users must have an email address')
        
        full_name = name.strip()
        
        first_name = ""
        last_name = ""
        
        if full_name:
            # split(' ', 1) splits only at the first space found
            name_parts = full_name.split(' ', 1)
            first_name = name_parts[0]
            if len(name_parts) > 1:
                last_name = name_parts[1]

        user = self.model(
            email=self.normalize_email(email.lower()),
            first_name=first_name,
            last_name=last_name,
        )
        user.social_id = social_id
        user.social_type = social_type
        user.set_password(social_id)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, first_name,last_name, password=None):
        user = self.create_user(
            email.lower(),
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        user.is_admin = True
        user.role = User.SuperAdmin
        user.is_active = True
        user.email_verified = 1
        user.superuser_status = True
        user.save(using=self._db)
        assign_role(user, "SuperAdmin")
        return user


class User(AbstractBaseUser, PermissionsMixin):

    SuperAdmin = 1
    SubAdmin = 2
    Teacher = 3
    Proctor = 4
    Student = 5
    OrganisationAdmin = 6

    ROLE_CHOICES = (
        (SuperAdmin, 'SuperAdmin'),
        (SubAdmin, 'SubAdmin'),
        (Teacher, 'Teacher'),
        (Proctor, 'Proctor'),
        (Student, 'Student'),
        (OrganisationAdmin, 'OrganisationAdmin'),
    )

    SOCIAL_LOGIN_CHOICES = (
        ('Email', 'Email'),
        ('Google', 'Google'),
        ('Facebook', 'Facebook')
    )
    
    uid = models.UUIDField(unique=True, editable=False, default=uuid.uuid4, blank=True, null=True, verbose_name='Public identifier')
    role = models.PositiveSmallIntegerField(choices=ROLE_CHOICES, blank=True, null=True, default=5)
    application_id = models.CharField(max_length=100, blank=True,null=True)
    social_id = models.CharField(max_length=255, blank=True,null=True)
    social_type = models.CharField(max_length=20, choices=SOCIAL_LOGIN_CHOICES, default='Email')
    username = models.CharField(max_length=100, blank=True)
    first_name = models.CharField(max_length=100, blank=True,null=True)
    last_name = models.CharField(max_length=100 ,blank=True,null=True)
    email = models.EmailField(max_length=255,unique=True)
    phone = models.CharField(max_length=100,blank=True,null=True)
    address = models.CharField(max_length=255,blank=True,null=True)
    city = models.CharField(max_length=120,blank=True,null=True)
    state = models.CharField(max_length=120,blank=True,null=True)
    country = models.CharField(max_length=120,blank=True,null=True)
    pincode = models.CharField(max_length=120,blank=True,null=True)
    dob = models.DateField(blank=True, null=True)
    lastlogin = models.BigIntegerField(default=0)
    current_refresh = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    failed_login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    unlocked_on = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    email_verified = models.IntegerField(blank=True, null=True, default=0)
    image = models.ImageField(blank=True, null=True)
    banner_image = models.ImageField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)
    

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name','last_name']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'User'

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def has_module_perms(self, app_label):
        return True

    def is_locked(self):
        if self.locked_until:
            return True
        return False

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        return self.is_admin