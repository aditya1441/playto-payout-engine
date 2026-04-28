from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('core.urls')),
    # Serve React app for all other routes
    re_path(r'^(?!api/|admin/).*$', TemplateView.as_view(template_name='index.html')),
]
