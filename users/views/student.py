from rest_framework import status
from rest_framework.views import APIView
from users.serializers import *
from users.renderers import UserRenderer
from aon_backend.utils import *
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.contrib.auth.models import update_last_login


class StudentLoginView(APIView):
    renderer_classes = [UserRenderer]
    def post(self, request, format=None):
        serializer = StudentLoginSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            user = serializer.user

            token = get_tokens_for_user(user)
            update_last_login(None, user)

            if user.current_refresh is not None:
                try:
                    RefreshToken(user.current_refresh).blacklist()
                except TokenError:
                    pass

            user.current_refresh = token['refresh']
            user.save()

            return success_response(message="Login Success", data={'token': token, 'user_role': get_user_role(user), "user_id":user.id, "email":user.email, "first_name":user.first_name, "last_name":user.last_name, "phone":user.phone, "application_id":user.application_id}, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)
