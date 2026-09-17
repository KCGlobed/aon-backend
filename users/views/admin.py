from rest_framework import status
from rest_framework.views import APIView
from django.contrib.auth import authenticate, login
from users.serializers import *
from users.renderers import UserRenderer
from aon_backend.utils import *
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.contrib.auth.models import update_last_login
from aon_backend.permissions import RoleOrPermissionCheck
from aon_backend.pagination import CustomPageNumberPagination
from rest_framework import filters
from rest_framework.permissions import IsAuthenticated


class AdminLoginView(APIView):
    renderer_classes = [UserRenderer]
    def post(self, request, format=None):
        serializer = AdminLoginSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            email = serializer.data.get('email').lower()
            password = serializer.data.get('password')
            user = authenticate(email = email, password = password)
            if user is not None:

                token = get_tokens_for_user(user)
                update_last_login(None, user)

                if user.current_refresh is not None:
                    try:
                        RefreshToken(user.current_refresh).blacklist()
                    except TokenError:
                        pass
                
                user.current_refresh = token['refresh']
                user.save()
          
                return success_response(message="Login Success", data={'token': token, 'user_role': get_user_role(user), "user_id":user.id,"email":user.email,"first_name":user.first_name,"last_name":user.last_name,"phone":user.phone }, status_code=status.HTTP_200_OK)
            else:
                return error_response(message="failed", data = {}, status_code=status.HTTP_400_BAD_REQUEST)
        
        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)
    

class AdminForgotPasswordView(APIView):
    renderer_classes = [UserRenderer]
    def post(self, request, format=None):
        serializer = AdminForgotPasswordSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            return success_response(message="Reset password link sent on email successfully!", data=[], status_code=status.HTTP_200_OK)
        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class UserResetPasswordView(APIView):
    renderer_classes = [UserRenderer]
    def post(self, request, format=None):
        serializer = UserResetPasswordSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            return success_response(message="Password reset successfully!", data=[], status_code=status.HTTP_200_OK)
        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)



class GetOrganizationListingView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated, 
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "organization_listing",
                            [SuperAdmin]
                        )]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['uid',"name"]
    ordering_fields = ['uid',"name",'is_active',"created_at"] 
    def get(self, request, format=None):
        
        users_list = Organization.objects.all()

        uid = request.query_params.get('uid')
        if uid:
            users_list = users_list.filter(uid__icontains=uid)

        name = request.query_params.get('name')
        if name:
            users_list = users_list.filter(name__icontains=name)

        is_active = request.query_params.get('status')
        if is_active:
            users_list = users_list.filter(is_active=is_active)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
                start_datetime_aware = timezone.make_aware(start_datetime, timezone.get_current_timezone())
                users_list = users_list.filter(created_at__gte=start_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid start_date format. Use YYYY-MM-DD.")
                
        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
                end_datetime_aware = timezone.make_aware(end_datetime, timezone.get_current_timezone())
                users_list = users_list.filter(created_at__lte=end_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid end_date format. Use YYYY-MM-DD.")

        search_filter = filters.SearchFilter()
        users_list = search_filter.filter_queryset(request, users_list, self)

        ordering_filter = filters.OrderingFilter()
        users_list = ordering_filter.filter_queryset(request, users_list, self)

        if not users_list.ordered:
            users_list = users_list.order_by('-id')
        
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(users_list, request, view=self)
        serializer = OrganizationListingSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)