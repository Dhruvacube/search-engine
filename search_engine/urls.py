from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, re_path

from main.views import home, search_results, submit_site

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="Home"),
    path("submit_site/", submit_site, name="submit site"),
    path("search", search_results, name="search"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
