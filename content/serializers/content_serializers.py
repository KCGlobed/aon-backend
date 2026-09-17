from rest_framework import serializers
from content.models import *
from aon_backend.utils import *


class SectionListingSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Sections
        fields = ['id', 'name', 'section_id', 'status', 'created_at', 'updated_at']


class SectionCreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=255, required=True)

    class Meta:
        model = Sections
        fields = ['name', 'status']

    def validate_name(self, value):
        name = " ".join(value.split())
        if not name:
            raise serializers.ValidationError("Name cannot be blank!")

        if Sections.objects.filter(name__iexact=name).exists():
            raise serializers.ValidationError("Section with this name already exists!")

        return name


class SectionUpdateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=255, required=True)

    class Meta:
        model = Sections
        fields = ['name', 'status']

    def validate_name(self, value):
        name = " ".join(value.split())
        if not name:
            raise serializers.ValidationError("Name cannot be blank!")

        if Sections.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Section with this name already exists!")

        return name


class SectionStatusSerializer(serializers.ModelSerializer):
    status = serializers.BooleanField(required=True)

    class Meta:
        model = Sections
        fields = ['status']
