from urllib.parse import urlparse
from scrapy.crawler import CrawlerProcess
from scrapy.linkextractors import LinkExtractor
from scrapy import signals
from scrapy.utils.project import get_project_settings
from scrapy.spiders import CrawlSpider
from scrapy.crawler import Crawler
from billiard import Process
from twisted.internet import reactor
from .store_data import StoreData

import scrapy
import sys
import os
import json
import random

from subprocess import Popen, PIPE

MAX_DEPTH = 2

class SurfCrawler(CrawlSpider):

    name = "surf_spider"
    urls = dict()

    # root (starting) url

    root_url = None
    
    # list of random proxies to not get blocked
    # (shouldn't really need this)
    proxies_list = []

    def __init__(self, **kw):
        super(SurfCrawler, self).__init__(**kw)
        if not kw.get('domain'):
            return
        self.root_url = kw.get('domain')

    def start(self, url : str):
        self.root_url = url
        self.initialize_data(self.root_url, 0)
        
        print("started\n\n\n\n\n\n\n\n\n")
        # random_proxy = self.get_random_proxy()

        self.urls[self.root_url] = dict()
        self.initialize_data(self.root_url, 0)

        yield scrapy.Request(
            url=self.root_url,
            headers = {'User-Agent': 'Mozilla/5.0'},
            callback=self.crawl_neighbors,
            errback=self.error_handler
        )

    def start_requests(self):

        self.urls[self.root_url] = dict()
        self.initialize_data(self.root_url, 0)

        yield scrapy.Request(
            url=self.unparse(self.root_url),
            headers = {'User-Agent': 'Mozilla/5.0'},
            callback=self.crawl_neighbors,
            errback=self.error_handler
        )

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(CrawlSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def spider_closed(self, spider):
        spider.logger.info("spider closed %s", spider.name)
        self.crawl_finished()

    def crawl_neighbors(self, response):

        # parse the source url...
        source_url = response.url
        source_parser = urlparse(source_url)
        source_url_netloc = source_parser.netloc

        print(source_url_netloc)

        # ignore sites that have a different response from the link
        if(source_url_netloc not in self.urls.keys()):
            print("buggy url")
            return

        self.logger.info("Currently on page: %s", response.url)

        depth = self.urls[source_url_netloc]['depth']

        out_links = []

        for a in response.xpath('//a/@href'):
            
            # get the url, parse the url to get the netloc
            # we store the url in our dictionary to avoid different schemes 
            # being assigned to different keys

            url = a.get()
            parser = urlparse(url)
            url_netloc = parser.netloc

            if(url_netloc != ''):
                # has a netloc

                # check if the url is "external" (includes local subdomains, e.g. maps.google.com)
                if(url_netloc != source_url_netloc):
                    # full_url = parser.scheme + "://" + parser.netloc
                    out_links.append(url_netloc)

                # else doesnt have a netloc
        
        for link in out_links:

            if link not in self.urls.keys():
                # add the outbound link to the "graph"
                if link not in self.urls[source_url_netloc]:
                    
                    self.urls[source_url_netloc]['out_links'].append(link)
                
                if(link not in self.urls.keys()):
                    # crawl the outbound link
                    self.urls[link] = dict()
                    self.initialize_data(link, depth + 1)
                
                self.urls[link]['in_links'].append(source_url_netloc)

                if(self.urls[link]['depth'] <= MAX_DEPTH):

                    yield scrapy.Request(
                        url=self.unparse(link), 
                        headers={'User-Agent': 'Mozilla/5.0'},
                        callback=self.crawl_neighbors,
                        errback=self.error_handler
                    )

    def unparse(self, link):
        unparsed_link = "https://"
        unparsed_link += link
        return unparsed_link

    def parse(self, link):
        parsed_link = link.replace("www.", "")
        return parsed_link

    def crawl_finished(self):
        # crawl is finished

        print("crawl is finished")
       
        self.pprint_urls()
        StoreData(self.urls)

    def pprint_urls(self):
        for key in self.urls.keys():
            print("url: " + key + " depth: " + str(self.urls[key]['depth']))
            print("in_links: " + str(self.urls[key]['in_links']))
            print("out_links: " + str(self.urls[key]['out_links']))
            print()
            
    def initialize_data(self, dict_loc, depth):
        # initialize the data representation for each website/node
        # mainly doing this for depth (crawl to x depth)
        # for now, 'data' is just a list of the outbound links from a website
        self.urls[dict_loc]['in_links'] = []
        self.urls[dict_loc]['out_links'] = []
        self.urls[dict_loc]['depth'] = depth

    def error_handler(self, err):
        print("there was an error...")
        print(err)

class CrawlerRunner(Process):

    def __init__(self, spider):
        Process.__init__(self)
        settings = get_project_settings()
        self.crawler_process = CrawlerProcess(settings)
        self.crawler = self.crawler_process.create_crawler(SurfCrawler)
        self.crawler.signals.connect(reactor.stop, signal=signals.spider_closed)
        self.spider = spider

    def run(self):
        self.crawler.crawl(self.spider)
        self.crawler.start()
        self.crawler.join()

def execute_crawler(url):

    print("Executing new crawler...")
    process = CrawlerProcess(get_project_settings())
    process.crawl(SurfCrawler, domain=url)
    process.start()

def run_spider(url):
    p = Process(target=execute_crawler, args=(url,))  
    p.start()
    p.join()





