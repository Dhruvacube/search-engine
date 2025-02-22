"""
Scraps already scrapped sites in database
"""

from django.core.management.base import BaseCommand

from main.com_crawler import crawl, formatter, requests_crawl
from main.models import CrawledWebPages


class Command(BaseCommand):
    help = "Scraps already scrapped sites in database"
    requires_system_checks = output_transaction = True

    def handle(self, *args, **options):
        for i in CrawledWebPages.objects.iterator():
            try:
                self.stdout.write(self.style.NOTICE(f"Started Crawling {i}"))
                update_dict = formatter(crawl(i.url))
                CrawledWebPages.objects.filter(url=i.url).update_or_create(
                    **update_dict)
                self.stdout.write(self.style.SUCCESS("Done"))
            except:
                try:
                    update_dict = formatter(requests_crawl(i.url))
                    CrawledWebPages.objects.filter(url=i.url).update_or_create(
                        **update_dict)
                    self.stdout.write(self.style.SUCCESS("Done"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(e))
