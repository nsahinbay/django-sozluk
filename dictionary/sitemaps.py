from django.contrib.flatpages.sitemaps import FlatPageSitemap
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone

from dictionary.conf import settings
from dictionary.models import Announcement, Author, Category, Entry, Topic

# https://docs.djangoproject.com/en/3.0/ref/contrib/sitemaps/#pinging-google


class AnnouncementSitemap(Sitemap):
    changefreq = "yearly"
    priority = 0.5
    protocol = "https"
    def items(self):
        return Announcement.objects.filter(date_created__lte=timezone.now()).order_by("-pk")

    def lastmod(self, obj):
        return obj.date_edited or obj.date_created


class AuthorSiteMap(Sitemap):
    changefreq = "daily"
    priority = 0.5
    limit = 10000
    protocol = "https"
    def items(self):
        return Author.objects_accessible.order_by("-pk")


class EntrySiteMap(Sitemap):
    changefreq = "weekly"
    priority = 0.4
    limit = 10000
    protocol = "https"
    def items(self):
        return Entry.objects.order_by("-date_created")

    def lastmod(self, obj):
        return obj.date_edited or obj.date_created


class TopicSiteMap(Sitemap):
    changefreq = "daily"
    priority = 1
    limit = 10000
    protocol = "https"
    def items(self):
        return Topic.objects_published.order_by("-date_created")

    def lastmod(self, obj):
        return obj.date_created


class CategorySiteMap(Sitemap):
    changefreq = "hourly"
    priority = 0.5
    protocol = "https"
    def items(self):
        return Category.objects.order_by("-weight")


class StaticCategorySiteMap(CategorySiteMap):
    protocol = "https"
    def items(self):
        return [
            category
            for category in settings.NON_DB_CATEGORIES
            if category not in settings.LOGIN_REQUIRED_CATEGORIES and category != "userstats"
        ]

    def location(self, item):
        return reverse("topic_list", kwargs={"slug": item})


class StaticSitemap(Sitemap):
    changefreq = "yearly"
    protocol = "https"
    def items(self):
        return [
            "announcements-index",
            "password_reset",
            "login",
            "register",
            "resend-email",
            "general-report",
            "category_list",
        ]

    def location(self, obj):
        return reverse(obj)


sitemaps = {
    "announcement": AnnouncementSitemap,
    "author": AuthorSiteMap,
    "entry": EntrySiteMap,
    "topic": TopicSiteMap,
    "category": CategorySiteMap,
    "static-category": StaticCategorySiteMap,
    "static": StaticSitemap,
    "flatpages": FlatPageSitemap,
}
