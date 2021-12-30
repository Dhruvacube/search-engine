import os
import time
import urllib
from functools import lru_cache
from typing import Optional

import nltk
import pymongo
import requests
import spacy
from asgiref.sync import sync_to_async
from bs4 import BeautifulSoup
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.html import escape, escapejs, strip_tags
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET, require_http_methods
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from requests import get, utils
from textblob import TextBlob

from crawler.common_user_agent import return_random_user_agent

from .models import CrawledWebPages, ToBeCrawledWebPages

nlp = spacy.load("en_core_web_md")
stop_words = set(stopwords.words("english"))


@sync_to_async
@require_GET
@cache_page(60 * 15)
def home(request):
    auto_suggestions = None
    if request.session.get("recorded_keywords"):
        auto_suggestions = request.session.get("recorded_keywords")
    return render(request, "index.html",
                  {"auto_suggestions": auto_suggestions})


@sync_to_async
@require_http_methods(["GET", "POST"])
@cache_page(60 * 15)
def submit_site(request):
    if request.method == "POST":
        site = request.POST.get("site_url")
        ToBeCrawledWebPages.objects.filter(url=site).update_or_create(url=site)
        messages.success(request, "The crawling data was updated :)")
    return render(request, "submit_site.html")


@sync_to_async
@require_GET
@cache_page(60 * 15)
def search_results(request):
    @lru_cache
    def search(
        term: str,
        num_results: Optional[int] = 15,
        lang: Optional[str] = "en",
        proxy=None,
    ) -> list:
        headers = utils.default_headers()
        headers.update({
            "User-Agent": return_random_user_agent(),
        })

        def fetch_results(search_term, number_results, language_code):
            escaped_search_term = search_term.replace(" ", "+")

            google_url = "https://www.google.com/search?q={}&num={}&hl={}".format(
                escaped_search_term, number_results + 1, language_code)
            proxies = None
            if proxy:
                if proxy[:5] == "https":
                    proxies = {"https": proxy}
                else:
                    proxies = {"http": proxy}
            response = get(google_url, headers=headers, proxies=proxies)
            return response.text

        def keywords_gen_and_rank(body: str):
            doc = nlp(body)
            keywords = list(doc.ents)
            tf_score = {}
            for each_word in body.split():
                each_word = each_word.replace(".", "")
                if each_word not in stop_words:
                    if each_word in tf_score:
                        tf_score[each_word] += 1
                    else:
                        tf_score[each_word] = 1
            tf_score.update(
                (x, y / int(len(body.split()))) for x, y in tf_score.items())
            keyword_ranking = tf_score
            return keywords, keyword_ranking

        def parse_results(raw_html):
            soup = BeautifulSoup(raw_html, "html.parser")
            result_block = soup.find_all("div", attrs={"class": "g"})
            for result in result_block:
                link = result.find("a", href=True)
                title = result.find("h3")
                description_soup = BeautifulSoup(str(result), "html.parser")
                description = description_soup.find("div",
                                                    attrs={"class": "VwiC3b"})
                if link and title:
                    try:
                        keywords_data = keywords_gen_and_rank(
                            description.getText())
                    except:
                        keywords_data = []
                    model = CrawledWebPages(
                        url=link["href"],
                        keywords_ranking=keywords_data[-1]
                        if keywords_data else keywords_data,
                        keywords_in_site=keywords_data[0]
                        if keywords_data else keywords_data,
                    )
                    try:
                        model.title = title.getText()
                    except:
                        pass
                    try:
                        model.stripped_request_body = description.getText()
                    except:
                        pass
                    try:
                        doc = nlp(description.getText())
                        model.keywords_in_site = list(doc.ents)
                    except:
                        pass
                    model.uses = 1
                    try:
                        model.save()
                    except:
                        pass
                    yield model

        html = fetch_results(term, num_results, lang)
        return list(parse_results(html))

    # Sanitize Data
    query = strip_tags(escape(escapejs(request.GET.get("q"))))

    # Add Auto Suggestions
    auto_suggestions = None
    if request.session.get("recorded_keywords"):
        auto_suggestions = request.session.get("recorded_keywords") + [query]
    else:
        auto_suggestions = [query]
        request.session["recorded_keywords"] = auto_suggestions
    query_correct = TextBlob(query).correct().__str__()
    start_time = time.time()

    data1 = CrawledWebPages.objects.filter(
        Q(url__icontains=query_correct.lower())
        | Q(ip_address__icontains=query_correct.lower())
        | Q(title__icontains=query_correct.lower())
        | Q(keywords_meta_tags__icontains=query_correct.lower())
        | Q(keywords_in_site__icontains=query_correct.lower())
        | Q(stripped_request_body__icontains=query_correct.lower())
        | Q(keywords_ranking=[query_correct.lower()]))
    data2 = CrawledWebPages.objects.filter(
        Q(url__icontains=request.GET.get("q"))
        | Q(ip_address__icontains=request.GET.get("q"))
        | Q(title__icontains=request.GET.get("q"))
        | Q(keywords_meta_tags__icontains=request.GET.get("q"))
        | Q(keywords_in_site__icontains=request.GET.get("q"))
        | Q(stripped_request_body__icontains=request.GET.get("q"))
        | Q(keywords_ranking=[request.GET.get("q")]))

    client = pymongo.MongoClient(os.environ.get("DATABASE_URL"))
    db = client["search"]
    print(
        list(db["CrawledWebPages"].find(
            {"$text": {
                "$search": request.GET.get("q")
            }})))

    results = list(set(list(data1.iterator()) + list(data2.iterator())))
    if results > 0:
        search(request.GET.get("q"))
    else:
        results = search(request.GET.get("q"))

    end_time = time.time()
    data_fetched = len(results)

    page = int(request.GET.get("page", 1))
    paginator = Paginator(results, 10)
    try:
        results = paginator.page(page)
    except PageNotAnInteger:
        results = paginator.page(1)
    except EmptyPage:
        results = paginator.page(paginator.num_pages)
    page_range = paginator.get_elided_page_range(number=page)
    spelling_msg_display = False
    if query != query_correct:
        auto_suggestions += [query_correct]
        spelling_msg_display = True
    return render(
        request,
        "results.html",
        {
            "value_in_input": request.GET.get("q"),
            "title": query,
            "data_fetched": data_fetched,
            "corrected_input": query_correct,
            "spelling_msg_display": spelling_msg_display,
            "results": results,
            "time": end_time - start_time,
            "auto_suggestions": auto_suggestions,
            "page_range": page_range,
        },
    )
