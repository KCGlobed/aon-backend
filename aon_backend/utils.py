from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework import status
from rolepermissions.checkers import has_role
from aon_backend.roles import *
from users.models import *
from configuration.models import *
import logging
logger = logging.getLogger()
from urllib.parse import urlparse
import random
import string
from django.db.models import Sum, Count
import math
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from datetime import datetime
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend


CHUNK_SIZE = 1024 * 1024 * 10
ROLE_MAPPING = { SuperAdmin: "SuperAdmin", SubAdmin: "SubAdmin", OrganisationAdmin: "OrganisationAdmin", Teacher: "Teacher", Proctor: "Proctor", Student: "Student", }

URL_ROLE_MAPPING = { SuperAdmin: "SuperAdmin", SubAdmin: "SubAdmin", OrganisationAdmin: "OrganisationAdmin", Teacher: "Teacher", Proctor: "Proctor", Student: "Student", }

URL_ROLE_CLASS_MAPPING = { SuperAdmin: "SuperAdmin", SubAdmin: "SubAdmin", OrganisationAdmin: "OrganisationAdmin", Teacher: "Teacher", Proctor: "Proctor", Student: "Student", }

DEVICES_ROLE_MAPPING = { SuperAdmin: "SuperAdmin", SubAdmin: "SubAdmin", OrganisationAdmin: "OrganisationAdmin", Teacher: "Teacher", Proctor: "Proctor", Student: "Student", }
    
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return (
        x_forwarded_for.split(",")[0]
        if x_forwarded_for
        else request.META.get("REMOTE_ADDR")
    )


def create_response(success, message, data=None, status_code=status.HTTP_200_OK):
    response_data = {
        "success": success,
        "status": str(status_code),
        "message": message,
        "data": data if data is not None else {}
    }
   
    logger.info(f"Response: {message} - Status: {status_code}")
   
    return Response(response_data, status=status_code)
 
def success_response(message, data=None, status_code=status.HTTP_200_OK):
    return create_response(True, message, data, status_code)
 
def error_response(message, data=None, status_code=status.HTTP_400_BAD_REQUEST):
    return create_response(False, message, data, status_code)



def parse_gcs_url(file_url):
    parsed_url = urlparse(file_url)
    if parsed_url.scheme != 'https':
        raise ValidationError("URL must start with 'https://'")
    
    if not parsed_url.netloc.endswith('storage.googleapis.com'):
        raise ValidationError("Invalid Google Cloud Storage URL")

    path_parts = parsed_url.path.lstrip('/').split('/', 1)
    if len(path_parts) != 2:
        raise ValidationError("Invalid GCS URL format")


    bucket_name, object_name = path_parts
    return bucket_name, object_name


def check_domain_match(email, target_domain='kcglobed.com'):
    try:
        domain = email.split('@')[1]
        return domain.lower() == target_domain.lower()
    except IndexError:
        return False
    

def get_user_role(user): 
    all_role_keys = list(ROLE_MAPPING.keys())
    assigned_roles = [
        ROLE_MAPPING[role] 
        for role in all_role_keys 
        if has_role(user, [role])
    ]
    return assigned_roles

def generate_random_password(length=8):
    letters = string.ascii_letters 
    digits = string.digits       
    special_characters = '@#$%&*'
    password = [
        random.choice(special_characters),  
        random.choice(letters),             
        random.choice(digits)
    ]
    all_characters = letters + digits + special_characters
    password += random.choices(all_characters, k=length - 3)
    random.shuffle(password)
    return ''.join(password)


def google_login_token_check(token):
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), settings.SOCIAL_AUTH_GOOGLE_OAUTH2_KEY)
        # Check for a valid issuer
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValidationError('Wrong issuer.')
        return True
    except ValueError as e:
        # id_token.verify_oauth2_token throws ValueError for expired or malformed tokens
        raise ValidationError(f'Token validation failed: {str(e)}')
    except Exception as e:
        raise ValidationError(f'An unexpected error occurred: {str(e)}')
    except ValidationError as e:
        raise ValidationError('error :'+ str(e))
    


def facebook_login_token_check(token):
    try:
        app_id = settings.SOCIAL_AUTH_FACEBOOK_KEY
        app_secret = settings.SOCIAL_AUTH_FACEBOOK_SECRET
        # Get the App Access Token
        app_token_url = f"https://graph.facebook.com/oauth/access_token?client_id={app_id}&client_secret={app_secret}&grant_type=client_credentials"
        app_token_response = requests.get(app_token_url).json()
        app_token = app_token_response['access_token']

        # Debug the user's token
        debug_url = f"https://graph.facebook.com/debug_token?input_token={token}&access_token={app_token}"
        debug_response = requests.get(debug_url).json()

        if debug_response['data']['is_valid'] and debug_response['data']['app_id'] == app_id:
            return True
        else:
            raise ValidationError('Invalid Facebook token.')
            
    except Exception as e:
        raise ValidationError('error :'+ str(e))
    


def getSMTPConfiguration():
    smtp_config = SMTPConfiguration.objects.all().first()
    if not smtp_config:
        raise ValidationError("No SMTP configuration found in the database.")

    if not smtp_config.host:
        raise ValidationError("The SMTP configuration has no host set.")

    if smtp_config.use_tls and smtp_config.use_ssl:
        raise ValidationError("The SMTP configuration cannot have both TLS and SSL turned on. Please turn on only one of them.")

    # The backend is built directly rather than through get_connection(backend=...), which Django
    # refuses once MAILERS is configured, as it is in settings.
    #
    # 'alias' matters: without it the backend treats itself as legacy and falls back on the
    # EMAIL_* settings for anything not passed here, and reading those raises
    # "The EMAIL_TIMEOUT setting is not available when MAILERS is defined". Naming an alias keeps
    # every value coming from the row above. The alias is only a label used in error messages; it
    # is never looked up in MAILERS.
    connection = SMTPEmailBackend(
        alias='smtp_configuration',
        host=smtp_config.host,
        port=smtp_config.port,
        username=smtp_config.username,
        password=smtp_config.password,
        use_tls=smtp_config.use_tls,
        use_ssl=smtp_config.use_ssl,
        timeout=getattr(settings, 'EMAIL_SEND_TIMEOUT', 30),
    )

    connection.open()
    
    return connection


def get_smtp_default_from_email():
    smtp_config = SMTPConfiguration.objects.all().first()
    if not smtp_config:
        raise ValidationError("No SMTP configuration found in the database.")
    return smtp_config.default_from_email