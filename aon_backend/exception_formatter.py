from drf_standardized_errors.formatter import ExceptionFormatter
from drf_standardized_errors.types import ErrorResponse

class CustomExceptionFormatter(ExceptionFormatter):
    def format_error_response(self, error_response: ErrorResponse):
        message = "An error occurred"
        if error_response.type == "validation_error":
            message = "Invalid request"
        elif error_response.type == "client_error":
            message = "Client error"
        elif error_response.type == "server_error":
            message = "Internal server error"

        custom_response = {
            "success": False,
            "message": message,
            "error": {
                "type": error_response.type,
                "errors": [
                    {
                        "code": error.code,
                        "detail": error.detail,
                        "attr": error.attr
                    } for error in error_response.errors
                ]
            }
        }
        return custom_response