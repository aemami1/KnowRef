#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import xml.sax, codecs, functools, time, re
import sys
import json
import argparse
import itertools
import os
import bz2
from joblib import Parallel, delayed

from wiki2plain import Wiki2Plain, ignore_wikipedia_service_pages, get_main_section
from itertools import izip_longest, chain


START = 1465000

def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return izip_longest(*args, fillvalue=fillvalue)


NON_INFOBOX_REGEX = re.compile('{{(not|cite|citation|quote|note|wikipedia:|flag|cquot|reflist|wikiso).*')

def process_to_json(chunk):
    try:
        wjf = WikiJsonFilter([], None, False)
        chunk = [c for c in chunk if c is not None]
        for title, text, revision in chunk:
            wjf.process(title, text, revision)
    except:
        import pdb; pdb.set_trace()
    return wjf

class WikiPageHandler(xml.sax.ContentHandler):
    def __init__(self, make_handler=None):
        self.make_handler = make_handler 
        self.stack = []
        self.text = None
        self.title = None
        self.revisions = []
        self.count = 0
        self.start_time = time.time()
        self.docs = []

    def startElement(self, name, attributes):
        if name == u"page":
            assert self.stack == []
            self.text = None
            self.title = None
            self.revisions = []
        elif name == u"title":
            assert self.stack == [u"page"]
            assert self.title is None
            self.title = u""
        elif name == u"text":
            if self.stack[-1] == u"page" or self.stack[-1] == u'revision':
                self.text = u""
        elif name == u'revision' or name == u'timestamp':
            pass
        else:
            return

        self.stack.append(name)

    def endElement(self, name):
        if len(self.stack) > 0 and name == self.stack[-1]:
            del self.stack[-1]
        if name == u"text" and self.stack == [u'page']:
            # We have the complete article, wait for closing page tag to write it
            pass
        if name == u'page':
            if "#REDIRECT" in self.text:
                return
            self.count += 1
            self.docs.append((self.title, self.text, self.revisions))
            n_jobs = 16
            chunk_size = 200
            if self.count % (chunk_size*n_jobs) == 0:
                if False and os.path.exists("enwiki3/pages%07d.json" % self.count):
                    print("Skipping %07d" % self.count)
                    self.docs = []
                else:
                    # results = Parallel(n_jobs=1)(delayed(process_to_json)(chunk) for chunk in grouper(self.docs, chunk_size))
                    results = [process_to_json(chunk) for chunk in grouper(self.docs, chunk_size)]
                    results = [r.json_file_docs for r in results]
                    results = [l for l in chain(*results)]
                    self.docs = []
                    with bz2.BZ2File("enwiki3/pages%07d.json.bz2" % self.count, 'w') as f_out:
                        f_out.write(json.dumps(results, indent=2, ensure_ascii=False).encode('utf-8'))

                    time_diff = time.time() - self.start_time
                    print(self.count, time_diff, self.count/(time_diff)),
                    sys.stdout.flush()
            

    def characters(self, content):
        assert content is not None and len(content) > 0
        if len(self.stack) == 0:
            return
        if self.stack[-1] == u"title":
            self.title += content
        elif self.stack[-1] == u"text":
            assert self.title is not None
            self.text += content
        elif self.stack[-1] == u'timestamp' and self.stack[-2] == u'revision':
            self.revisions.append(content)


class WikiFilter():
    def is_wiki_service_page(self, title):
        title_underscore = title.replace(' ', '_')
        wikipedia_ignore_page_match = re.match(ignore_wikipedia_service_pages, title_underscore)
        if wikipedia_ignore_page_match:
            return True
        return False


class WikiJsonFilter(WikiFilter):
    def __init__(self, names, json_out=None, is_filter=True):
        self.MAX_DOCS_PER_FILE = 10000

        self.name_set = set(names)
        self.out = json_out
        self.global_doc_id = 0
        self.json_file_docs = []
        self.json_file_docs_count = 0
        self.json_file_id = 0
        self.is_filter = is_filter

    def write_to_fd(self, out_fd):
        if len(self.json_file_docs) == 0:
            return
        if len(self.json_file_docs) == 1:
            json.dump(self.json_file_docs[0], out_fd, indent=2, ensure_ascii=False)
        else:
            json.dump(self.json_file_docs, out_fd, indent=2, ensure_ascii=False)

    def flush_file_contents(self):
        if self.out is None:
            return
        out_current_file_path = os.path.join(self.out, '%04d.json' % self.json_file_id)
        with codecs.open(out_current_file_path, 'w', 'utf-8') as f_out:
            json.dump(self.json_file_docs, f_out, indent=2, ensure_ascii=False)
        self.json_file_id += 1
        # reset file-related counters
        self.json_file_docs = []
        self.json_file_docs_count = 0


    def process(self, title, text, revisions=[]):
        #from IPython.core.debugger import Tracer; Tracer()()
        global_doc_id = self.global_doc_id + 1
        title_underscore = title.replace(' ', '_')

        if not self.is_filter or self.name_set.__contains__(title_underscore):
            title = Wiki2Plain(title_underscore).text
            fullbody = Wiki2Plain(text).text
            body = Wiki2Plain(get_main_section(text)).text
            has_colon_in_title = ':' in title

            # skip current page if it's a wikipedia service page
            if self.is_wiki_service_page(title):
                return

            # Now we have a legitimate document
            #if has_colon_in_title:
                #print(u'WARNING: collecting possibly undesired document having title: %s' % title)

            current_json_doc = {'id': str(global_doc_id), 'title': title.strip(), 'body': body.strip(), 'fullbody' : fullbody.strip()}
            self.global_doc_id += 1
            self.json_file_docs.append(current_json_doc)
            self.json_file_docs_count += 1
            if self.json_file_docs_count == self.MAX_DOCS_PER_FILE:
                # flush file contents
                self.flush_file_contents()


def write_revision(wiki_filter, f_out, title, text, revisions):
    if not wiki_filter.is_wiki_service_page(title):
        f_out.write(title + '\n')
        for revision in revisions:
            f_out.write(revision + '\n')
        f_out.write('-' * 20 + '\n')


def dump_json(f_in, out_dir):
    xml.sax.parse(f_in, WikiPageHandler())
    # flush remaining documents in json_filter internal cache
    if len(json_filter.json_file_docs) > 0:
        json_filter.flush_file_contents()



def match_infobox(text):
    end_position = 0
    matched_text = ''
    start_position = text.find('{{', end_position)
    while start_position >= 0:
        bracket_count = 0
        for i in range(start_position, len(text)):
            if text[i] == '{':
                bracket_count += 1
            elif text[i] == '}':
                bracket_count -= 1
            if not bracket_count:
                end_position = i+1
                break
        if end_position > start_position:
            matched_section = text[start_position: end_position]
            if '\n' in matched_section and not re.match(NON_INFOBOX_REGEX, matched_section):
                matched_text += matched_section + '\n' 
            start_position = text.find('{{', end_position)
        else:
            break
    return matched_text


def dump_infobox(f_out, title, text, reversions = []):
    text = text.lower()
    infobox_text = match_infobox(text).strip()
    body_start_pos = text.find('\n')
    if body_start_pos > 0:
        title = normalize_title(title)
        if title and infobox_text:
            f_out.write(u'%s\n%s\n%s\n' % (title, infobox_text, '-' * 50))


def normalize_title(title):
    result = re.search('( )+\(.+\)$', title)
    if result:
        title = '%s_%s' % (title[:result.start(1)], title[result.end(1):])
    title = re.sub('[ ]+', '_', title)
    return title.lower()


def do_general_dump(in_path, dump_func):
    xml.sax.parse(in_path, WikiPageHandler(dump_func))


def main(args, f_in, out_path):
    if args.dump_json:
        if not os.path.isdir(out_path):
            raise ValueError("With the selected options, the out path must be a directory.")
        dump_json(f_in, out_path)
    else:
        with codecs.open(out_path, 'w', 'utf-8') as f_out:
            wiki_filter = WikiFilter()
            if args.dump_revision:
                do_general_dump(f_in, functools.partial(write_revision, wiki_filter, f_out))
            elif args.dump_infobox:
                do_general_dump(f_in, functools.partial(dump_infobox, f_out))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    option_parser = parser.add_mutually_exclusive_group(required=True)
    option_parser.add_argument('--dump-json', action='store_true', default=False, dest='dump_json')
    option_parser.add_argument('--dump-revision', action='store_true', default=False, dest='dump_revision')
    option_parser.add_argument('--dump-infobox', action='store_true', default=False, dest='dump_infobox')
    parser.add_argument('-i', nargs='?', dest='input', default=sys.stdin, help='input file path. defaults to stdin')
    parser.add_argument('-o', nargs='?', dest='output', required="True", help='output path. It can be a directory or a file depending on the task.')
    args = parser.parse_args(sys.argv[1:])

    # open and close input only if it's not stdin (we don't want to close stdin)
    if args.input is sys.stdin:
        f_in = sys.stdin
        main(args, f_in, args.output)
    else:
        with bz2.BZ2File(args.input, "r", 2 ** 20) as f_in:
            main(args, f_in, args.output)

