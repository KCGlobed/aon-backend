from rolepermissions.roles import AbstractUserRole


class SuperAdmin(AbstractUserRole):
    available_permissions = { }
    @classmethod
    def get_name(cls):
        return 'SuperAdmin'


class SubAdmin(AbstractUserRole):
    available_permissions = { }
    @classmethod
    def get_name(cls):
        return 'SubAdmin'
    

class Teacher(AbstractUserRole):
    available_permissions = {}
    @classmethod
    def get_name(cls):
        return 'Teacher'


class Proctor(AbstractUserRole):
    available_permissions = {}
    @classmethod
    def get_name(cls):
        return 'Proctor'


class Student(AbstractUserRole):
    available_permissions = {}
    @classmethod
    def get_name(cls):
        return 'Student'
