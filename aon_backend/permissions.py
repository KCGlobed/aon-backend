from rest_framework import permissions
from rolepermissions.checkers import has_permission, has_role
from rolepermissions.roles import get_user_roles


class RoleOrPermissionCheck(permissions.BasePermission):
    message = 'You do not have permission to perform this action.'
    required_permission = None
    required_roles = None
    
    def has_permission(self, request, view):
        
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            self.message = "Authentication required or your account is inactive."
            return False

        permission_to_check = getattr(self, 'required_permission', None) or getattr(view, 'required_permission', None)
        roles_to_check = getattr(self, 'required_roles', None) or getattr(view, 'required_roles', None)
        check_type = getattr(self, 'check_type', False) or getattr(view, 'check_type', False)

        if permission_to_check is None and roles_to_check is None:
            raise ValueError(
                f"{self.__class__.__name__} is configured incorrectly. "
                f"It must have 'required_permission' and/or 'required_roles' set, "
                f"or be created via the factory method."
            )

        permission_check_result = True
        role_check_result = True

        if check_type:
            if permission_to_check == "user_role_specific_permission_list":
                target_user_type = view.kwargs.get('user_type')
                action_suffix = "_listing"
                permission_to_check = f"{target_user_type}{action_suffix}"
            
            elif permission_to_check == "user_role_specific_permission_create":
                target_user_type = view.kwargs.get('user_type')
                action_suffix = "create_"
                permission_to_check = f"{action_suffix}{target_user_type}"

            elif permission_to_check == "user_role_specific_permission_update":
                target_user_type = view.kwargs.get('user_type')
                action_suffix = "update_"
                permission_to_check = f"{action_suffix}{target_user_type}"

            elif permission_to_check == "user_role_specific_permission_delete":
                target_user_type = view.kwargs.get('user_type')
                action_suffix = "delete_"
                permission_to_check = f"{action_suffix}{target_user_type}"


            if permission_to_check is not None and roles_to_check is not None:
                if not has_permission(request.user, permission_to_check) and not has_role(request.user, roles_to_check):
                    self.message = f"You do not have required role/permission to perform this action."
                    permission_check_result = False
            else:
                permission_check_result = False
        else:
            if permission_to_check is not None:
                if not has_permission(request.user, permission_to_check):
                    self.message = f"You do not have the '{permission_to_check}' permission to perform this action."
                    permission_check_result = False

            if permission_check_result and roles_to_check is not None:
                if not has_role(request.user, roles_to_check):
                    role_names = [r.__name__ if hasattr(r, '__name__') else str(r) for r in roles_to_check]
                    self.message = f"You must be one of the following roles: {', '.join(role_names)}."
                    role_check_result = False

        return permission_check_result and role_check_result

    @classmethod
    def for_permission(cls, permission_name, message=None, allow_safe_methods=True):
    
        if not isinstance(permission_name, str) or not permission_name:
            raise ValueError("Permission name must be a non-empty string.")
        new_cls_name = f"Has_{permission_name.replace('_', '').title()}Permission"
        new_cls = type(new_cls_name, (cls,), {
            'required_permission': permission_name,
            'required_roles': None, # Ensure roles are explicitly not required for this instance
            "check_type":False,
            'message': message if message else f"You do not have the '{permission_name}' permission.",
            'allow_safe_methods_without_check': allow_safe_methods,
        })
        return new_cls

    @classmethod
    def for_roles(cls, roles_list, message=None, allow_safe_methods=True):
        if not isinstance(roles_list, (list, tuple)) or not all(roles_list):
            raise ValueError("Roles list must be a non-empty list or tuple of role names/objects.")
        # Generate a descriptive name for the class based on roles
        role_names_for_cls = "_".join([r.__name__ if hasattr(r, '__name__') else str(r) for r in roles_list])
        new_cls_name = f"IsIn_{role_names_for_cls.title()}Role"
        new_cls = type(new_cls_name, (cls,), {
            'required_permission': None, # Ensure permission is explicitly not required for this instance
            'required_roles': roles_list,
            "check_type":False,
            'message': message if message else f"You must be one of the following roles: {', '.join(role_names_for_cls.split('_'))}.",
            'allow_safe_methods_without_check': allow_safe_methods,
        })
        return new_cls

    @classmethod
    def for_permission_and_roles(cls, permission_name, roles_list, message=None, allow_safe_methods=True):
        print(cls)
        if not isinstance(permission_name, str) or not permission_name:
            raise ValueError("Permission name must be a non-empty string.")
        if not isinstance(roles_list, (list, tuple)) or not all(roles_list):
            raise ValueError("Roles list must be a non-empty list or tuple of role names/objects.")

        role_names_for_cls = "_".join([r.__name__ if hasattr(r, '__name__') else str(r) for r in roles_list])
        new_cls_name = f"Has_{permission_name.replace('_', '').title()}_And_{role_names_for_cls.title()}"
        new_cls = type(new_cls_name, (cls,), {
            'required_permission': permission_name,
            'required_roles': roles_list,
            "check_type":False,
            'message': message if message else (
                f"You need the '{permission_name}' permission AND must be one of the roles: "
                f"{', '.join(role_names_for_cls.split('_'))}."
            ),
            'allow_safe_methods_without_check': allow_safe_methods,
        })
        return new_cls
    

    @classmethod
    def for_permission_or_roles(cls, permission_name, roles_list, message=None, allow_safe_methods=True, url_kwarg=None):
        if not isinstance(permission_name, str) or not permission_name:
            raise ValueError("Permission name must be a non-empty string.")
        if not isinstance(roles_list, (list, tuple)) or not all(roles_list):
            raise ValueError("Roles list must be a non-empty list or tuple of role names/objects.")

        role_names_for_cls = "_".join([r.__name__ if hasattr(r, '__name__') else str(r) for r in roles_list])
        new_cls_name = f"Has_{permission_name.replace('_', '').title()}_And_{role_names_for_cls.title()}"
        new_cls = type(new_cls_name, (cls,), {
            'required_permission': permission_name,
            'required_roles': roles_list,
            "check_type":True,
            'message': message if message else (
                f"You need the '{permission_name}' permission AND must be one of the roles: "
                f"{', '.join(role_names_for_cls.split('_'))}."
            ),
            'allow_safe_methods_without_check': allow_safe_methods,
        })
        return new_cls
    


