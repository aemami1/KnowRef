#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, codecs, os, json, time


infobox_pattern = re.compile('{{.*?}}')
invalid_title_pattern = re.compile('[0-9a-zA-Z]+')

# try to include wikipedia service pages (mainly from Namespaces)
ignore_wikipedia_service_pages = re.compile(
    r'('
    r'^(book|category|draft|education_program|file|help|media|mediawiki|module|portal|talk|template|'
    r'timedtext|topic|user|wikipedia|special|p|ISO[_-][0-9_-]+|UN[/]LOCODE)'
    r'([ _]talk)?[:])|'
    r'^(main_page$|list_of_)|'
    r'.*?[.](jp[e]?g|png|gif)$'
    , re.IGNORECASE)

# DON"T USE simple body heuristics for disambiguation!
# some pages have expressions like "may refer to" in the first paragraph without actually being disambiguation pages;
# see, e.g., Major_depressive_disorder.
# ignore_disambiguation_pages = re.compile(r'^.*?(may( also)?|commonly) refers? to.*?\n', re.IGNORECASE)


class Wiki2Plain:

    def __init__(self, wiki):
        self.wiki = wiki
        
        self.text = wiki
        self.text = self.unhtml(self.text)
        self.text = self.unwiki(self.text)
        self.text = self.punctuate(self.text)
        self.text = self.remove_infobox(self.text)
    
    def __str__(self):
        return self.text
    
    def unwiki(self, wiki):
        """
        Remove wiki markup from the text.
        """
        wiki = re.sub(r'(?i)\{\{IPA(\-[^\|\{\}]+)*?\|([^\|\{\}]+)(\|[^\{\}]+)*?\}\}', lambda m: m.group(2), wiki)
        # wiki = re.sub(r'(?i)\{\{Lang(\-[^\|\{\}]+)*?\|([^\|\{\}]+)(\|[^\{\}]+)*?\}\}', lambda m: m.group(2), wiki)
        wiki = re.sub(r'(?i)\{\{Lang.*?\}\}', '', wiki)
        wiki = re.sub(r'\{\{[^\{\}]+\}\}', '', wiki)
        wiki = re.sub(r'(?m)\{\{[^\{\}]+\}\}', '', wiki)
        wiki = re.sub(r'(?m)\{\|[^\{\}]*?\|\}', '', wiki)
        wiki = re.sub(r'(?i)\[\[Category:[^\[\]]*?\]\]', '', wiki)
        wiki = re.sub(r'(?i)\[\[Image:[^\[\]]*?\]\]', '', wiki)
        wiki = re.sub(r'(?i)\[\[File:[^\[\]]*?\]\]', '', wiki)
        wiki = re.sub(r'\[\[[^\[\]]*?\|([^\[\]]*?)\]\]', lambda m: m.group(1), wiki)
        wiki = re.sub(r'\[\[([^\[\]]+?)\]\]', lambda m: m.group(1), wiki)
        wiki = re.sub(r'\[\[([^\[\]]+?)\]\]', '', wiki)
        wiki = re.sub(r'(?i)File:[^\[\]]*?', '', wiki)
        wiki = re.sub(r'\[[^\[\]]*? ([^\[\]]*?)\]', lambda m: m.group(1), wiki)
        wiki = re.sub(r"''+", '', wiki)
        wiki = re.sub(r'(?m)^\*$', '', wiki)
        
        return wiki
    
    def unhtml(self, html):
        """
        Remove HTML from the text.
        """
        html = re.sub(r'(?i)&nbsp;', ' ', html)
        html = re.sub(r'(?i)<br[ \\]*?>', '\n', html)
        html = re.sub(r'(?m)<!--.*?--\s*>', '', html)
        html = re.sub(r'(?i)<ref[^>]*>[^>]*<\/ ?ref>', '', html)
        html = re.sub(r'(?m)<.*?>', '', html)
        html = re.sub(r'(?i)&amp;', '&', html)
        
        return html
    
    def punctuate(self, text):
        """
        Convert every text part into well-formed one-space
        separate paragraph.
        """
        text = re.sub(r'\r\n|\n|\r', '\n', text)
        text = re.sub(r'\n\n+', '\n\n', text)
        
        parts = text.split('\n\n')
        partsParsed = []
        
        for part in parts:
            part = part.strip()
            
            if len(part) == 0:
                continue
            
            partsParsed.append(part)
        
        return '\n\n'.join(partsParsed)

    def remove_infobox(self, text):
        return re.sub(infobox_pattern, '', text)
    
    def image(self):
        """
        Retrieve the first image in the document.
        """
        # match = re.search(r'(?i)\|?\s*(image|img|image_flag)\s*=\s*(<!--.*-->)?\s*([^\\/:*?<>"|%]+\.[^\\/:*?<>"|%]{3,4})', self.wiki)
        match = re.search(r'(?i)([^\\/:*?<>"|% =]+)\.(gif|jpg|jpeg|png|bmp)', self.wiki)
        
        if match:
            return '%s.%s' % match.groups()
        
        return None

def get_main_section(text):
    detail_start_pos = text.find('==')
    if detail_start_pos >= 0:
        return text[:detail_start_pos]
    else:
        return text

def do_test(in_path, out_path):
    with codecs.open(in_path, encoding='utf-8') as reader:
        with codecs.open(out_path, encoding='utf-8', mode='w') as writer:
            writer.write(Wiki2Plain(reader.read()).text)

def do_batch(in_trec, out_dir):
    import Corpus
    reader = Corpus.TRECReader()
    reader.open(in_trec)
    doc = reader.next()
    count = 1;
    entry_per_file = 10000
    json_list = []
    start_time = time.time()
    while doc:
        plain = Wiki2Plain(get_main_section(doc.text))
        text = plain.text

        body_start_pos = text.find('\n')
        if body_start_pos > 0:
            title = text[:body_start_pos]
            body = text[body_start_pos:] 
            if not title.count(':') or not re.match(invalid_title_pattern, title.split(':')[0]):
                json_list.append({'id': str(count), 'title': title.strip(), 'body': body.strip()})
                if count % entry_per_file == 0:
                    out_path = os.path.join(out_dir, str(count / entry_per_file) + '.json')
                    print('writing', out_path)
                    with codecs.open(out_path, encoding='utf-8', mode='w') as writer:
                       json.dump(json_list, writer, indent=2, ensure_ascii=False) 
                       json_list = []
                    print(count, title, time.time() - start_time)
                count += 1
        doc = reader.next()
    reader.close()

def do_count_length(in_trec, out_path):
    import Corpus
    reader = Corpus.TRECReader()
    reader.open(in_trec)
    doc = reader.next()
    count = 1;
    entry_per_file = 10000
    json_list = []
    start_time = time.time()
    with codecs.open(out_path, encoding='utf8', mode='w') as writer:
        while doc:
            length = len(doc.text)
            if '#redirect' in doc.text.lower():
                doc = reader.next()
                continue
            plain = Wiki2Plain(get_main_section(doc.text))
            text = plain.text

            body_start_pos = text.find('\n')
            if body_start_pos > 0:
                title = text[:body_start_pos]
                writer.write(u'%s\t%d\n' % (title, length))
                writer.flush()

            doc = reader.next()
    reader.close()



if __name__ == '__main__':
    import sys
    option = sys.argv[1]
    argv = sys.argv[2:]
    if option == '--test':
        do_test(*argv)
    elif option == '--batch':
        do_batch(*argv)
    elif option == '--count-length':
        do_count_length(*argv)
    elif option == '--collect-infobox':
        do_collect_infobox(*argv)
   
