from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """ترقيم موحد — لا إرسال آلاف السجلات دفعة واحدة."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
