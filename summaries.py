#!/usr/bin/evn python
# -*- coding: utf-8 -*-

import itertools
import os
import requests
import sys
from lxml import html

WAYBACK_HOST = 'https://web.archive.org'
WAYBACK_BASE = WAYBACK_HOST + '/web/20170630022146'
WAYBACK_REWRITE = '<!-- End Wayback Rewrite JS Include -->'
ORIG_BASE = 'https://qualitymeasures.ahrq.gov/search'
QS = 'f_DocType=302&fLockTerm=Measure+Summaries&page=%s'
SUMMARY_BATCH_URL = '%s/%s?%s' % (
    WAYBACK_BASE,
    ORIG_BASE,
    QS
    )
SEARCH_PAGE_COUNT = 127
RESULT_BATCH_FILENAME = 'measures-search-page-%s.html'
NQMC_BASE = 'https://qualitymeasures.ahrq.gov/'
XML_BASE = NQMC_BASE + 'summaries/downloadcontent/nqmc-%s?contentType=xml'


def has_local_search_result(n):
    name = os.path.join(data_dir(), RESULT_BATCH_FILENAME % n)
    return os.path.exists(name)


def fetch_search_page(n):
    if has_local_search_result(n):
        return None
    url = SUMMARY_BATCH_URL % n
    response = requests.get(url)
    print response.status_code, url
    return response.content


def data_dir():
    venv_root = '/'.join(os.path.realpath(sys.executable).split('/')[:-2])
    path = os.path.join(venv_root, 'data', 'nqmc')
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def batch_path(n):
    savepath = data_dir()
    return os.path.join(savepath, RESULT_BATCH_FILENAME % n)


def save_search_page(n, content):
    outfile = open(batch_path(n), 'w')
    outfile.write(content)
    outfile.close()


def get_search_pages():
    """
    Get and persist search pages for NQMC from archive.org.
    This appears to be necessary as search is not working on NQMC site
    as of 2018-07-14.  Archive.org has default search batch size of 20
    summaries per page mirrored, so we obtain those, and save the HTML
    to local filesystem.

    Outside of being simplest path to get links to summaries, this HTML
    is also useful in that it enumerates facets used for filtering,
    which may have relationships (not always 1:1) with controlled
    vocabularies used in summaries themselves.
    """
    for n in range(1, SEARCH_PAGE_COUNT + 1):
        content = fetch_search_page(n)
        if content is not None:
            # we do not have a local copy
            save_search_page(n, content)


def uncached_url(url):
    """Given wayback relative URL, resolve to origin url"""
    return '/'.join(url.split('/')[3:])


def nqmc_id(link):
    meta = link.getparent().getparent().cssselect('ul.item-meta')[0]
    # second meta li in search result has the NQMC identifier
    return meta.findall('li')[1].text.strip()


def xml_doc_url(nqmc_id):
    # strip prefix and cast to int to get rid of leading-zero
    idnum = int(nqmc_id.split(':')[-1])
    return XML_BASE % idnum


def batch_links(n):
    """
    div.results-list contains 0..* div.results-list-item elements, which
    each contain h3.results-list-item-title a with text and href.
    """
    path = batch_path(n)
    with open(path) as infile:
        source = infile.read()
    doc = html.document_fromstring(source)
    measure_links = doc.cssselect('h3.results-list-item-title a')
    return [
        {
            'url': WAYBACK_HOST + link.get('href'),
            'orig_url': uncached_url(link.get('href')),
            'title': link.text,
            'nqmc': nqmc_id(link),
            'xml_url': xml_doc_url(nqmc_id(link)),
            }
        for link in measure_links
        ]


def merged_links():
    batches = []
    for n in range(1, SEARCH_PAGE_COUNT + 1):
        batches.append(batch_links(n))
    return list(itertools.chain(*batches))


def write_xml(dirname, content, identifier):
    with open(os.path.join(dirname, 'data-%s.xml' % identifier), 'w') as out:
        out.write(content)


def write_html(dirname, content):
    with open(os.path.join(dirname, 'index.html'), 'w') as out:
        out.write(content)


def mirror_nqmc(merged):
    base = data_dir()
    with open(os.path.join(base, 'index.html'), 'w') as index_html:
        index_html.seek(0)
        index_html.truncate()
        index_html.write('<!doctype html>\n<html>\n  <head>\n')
        index_html.write('    <title>NQMC Mirror</title>\n  </head>\n')
        index_html.write('<body>\n  <h1>NQMC Mirror</h1>\n  <ul>')
        index_html.flush()
        for link in merged:
            identifier = link.get('nqmc').split(':')[-1]
            dirname = os.path.join(base, link.get('nqmc').replace(':', '_'))
            xml_path = os.path.join(dirname, 'data-%s.xml' % identifier)
            html_path = os.path.join(dirname, 'index.html')
            if not os.path.isdir(dirname):
                os.mkdir(dirname)
            if not os.path.exists(xml_path):
                # get xml document, try first from Wayback, then from Origin:
                xml_url = '/'.join((WAYBACK_BASE, link.get('xml_url')))
                response = requests.get(xml_url)
                if response.status_code == 200:
                    print 'Success downloading XML from Archive.org'
                else:
                    print 'Attempting to fetch XML from origin.'
                    response = requests.get(link.get('xml_url'))
                if response.status_code == 200:
                    content = response.content.split(WAYBACK_REWRITE)[-1]
                    write_xml(dirname, content, identifier)
                    print '\t\t - Successfully wrote XML content.'
                else:
                    print response.status_code, response.url
                    raise
            if not os.path.exists(html_path):
                # get html document:
                response = requests.get(link.get('url'))
                if response.status_code == 200:
                    print 'Success downloading HTML from Archive.org'
                else:
                    print 'Attempting to fetch XML from origin.'
                    response = requests.get(link.get('orig_url'))
                if response.status_code == 200:
                    write_html(dirname, response.content)
                    print '\t\t - Successfully wrote HTML content.'
            idxlink = u'<li>\n' \
                u'<h4>%s — <a href="%s" target="_blank">%s</a></h4>\n' \
                u'<p>As <a href="%s" target="_blank">XML</a></p>\n' \
                u'</li>\n\n' % (
                    link.get('nqmc'),
                    u'%s/index.html' % dirname,
                    link.get('title'),
                    u'%s/data-%s.xml' % (dirname, identifier)
                )
            if os.path.exists(xml_path) and os.path.exists(html_path):
                index_html.write(idxlink.encode('utf-8'))
                index_html.flush()
            elif os.path.exists(xml_path):
                idxlink.replace('<h4>', '<h4>(MISSING HTML)')
                index_html.write(idxlink.encode('utf-8'))
                index_html.flush()
        index_html.write('  </ul>\n</body>\n</html>')


def get_summaries():
    """Get NQMC Measure Summaries, simple data dump of HTML and XML"""
    # Stage 1: get search page XML
    get_search_pages()
    # Stage 2: transform search pages into single manifest measure summary
    #   links and titles, used for later stage fetch of measures
    merged = merged_links()
    # Stage 3: mirror data from merged links, both HTML and XML
    mirror_nqmc(merged)


def main():
    if not hasattr(sys, 'real_prefix'):
        raise RuntimeError('This script must be run in virtualenv.')
    get_summaries()


if __name__ == '__main__':
    main()
