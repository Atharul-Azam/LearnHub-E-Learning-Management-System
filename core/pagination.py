from django.conf import settings
from django.core.paginator import Paginator


def paginate(request, queryset, per_page=None):
    """Return ``(page_obj, querystring_without_page)`` for the current request."""
    paginator = Paginator(queryset, per_page or settings.PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()
