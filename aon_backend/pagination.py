from rest_framework import pagination
from rest_framework.response import Response
from rest_framework import status

class CustomPageNumberPagination(pagination.PageNumberPagination):
    page_size = 20  
    page_size_query_param = 'page_size' 
    max_page_size = 100

    def get_paginated_response(self, data, status_code=status.HTTP_200_OK):
        return Response({
            'success': True,
            'message': 'Success',
            "status": str(status_code),
            'pagination': {
                'total_results': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'next_page': self.get_next_link(),
                'previous_page': self.get_previous_link(),
                'page_size': self.page_size,
            },
            'data': data
        })