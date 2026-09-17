from rest_framework import serializers
from users.models import *
from rolepermissions.checkers import has_role
from aon_backend.utils import *


class StudentLoginSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length = 255, required=True)
    email = serializers.EmailField(max_length = 255, required=True)
    application_id = serializers.CharField(max_length = 100, required=True)

    class Meta:
        model = User
        fields = ['name', 'email', 'application_id']

    def validate(self, data):
        email = data.get('email').lower()
        application_id = data.get('application_id').strip()

        user = User.objects.filter(email = email, is_deleted = False).first()
        if user is None:
            raise serializers.ValidationError("User Not found with this email!")

        if user.is_active is False:
            raise serializers.ValidationError("User is not active!")

        if user.is_locked():
            raise serializers.ValidationError("User account is locked!")

        try:
            if not has_role(user, globals()["Student"]) and user.role != User.Student:
                raise serializers.ValidationError("Invalid User!")
        except KeyError:
            raise serializers.ValidationError("Invalid Role Type!")

        if not user.application_id or user.application_id.strip().lower() != application_id.lower():
            raise serializers.ValidationError("Invalid Application Id!")

        full_name = " ".join(filter(None, [user.first_name, user.last_name]))
        if " ".join(full_name.split()).lower() != " ".join(data.get('name').split()).lower():
            raise serializers.ValidationError("Invalid Name!")

        self.user = user

        return data
